from __future__ import annotations

import copy
import json
import logging
import time
import uuid
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, Optional
from urllib.parse import quote

import httpx
from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

from app.config import settings
from app.openai_content import delta_text, openai_content_to_text
from app.image_utils import image_api_response_to_data_url
from app.chroma_store import recall_block as chroma_recall_block, save_message as chroma_save_message
from app.gena_features import (
    public_static_url,
    post_images_with_optional_reference,
    prepare_image_generation_prompt,
    should_stream_image_gena,
    has_explicit_presentation_style,
    should_stream_presentation,
    stream_presentation_style_prompt,
    stream_image_markdown,
    stream_presentation_pptx,
    user_wants_image_generation,
)
from app.memory_context import (
    digest_turn_to_facts,
    extract_explicit_remember,
    maybe_compress_messages_for_context,
)
from app.memory_store import MemoryStore
from app.log_sanitize import log_chat_json
from app.music_demo import (
    build_mp3_from_prompt,
    melody_notes_from_llm,
    user_wants_music_demo,
)
from app.mws_client import MWSClient
from app.presentation_api import pptx_path, router as presentation_api_router, validate_stem
from app.pptx_pdf import ensure_pptx_pdf
from app.rag_store import RAGStore, extract_embeddable_documents
from app.router_logic import (
    apply_manual_route,
    gena_chat_target,
    inject_router_debug,
    last_user_message,
    normalize_requested_model,
    pick_route_deterministic,
    pick_route_gena,
    strip_gena_assistant_markers,
    _content_to_text,
    message_has_image,
    message_has_audio,
)
from app.web_tools import (
    extract_urls,
    fetch_url_text,
    search_query_from_text,
    should_run_deep_research,
    should_run_web_search,
    strip_trailing_openwebui_follow_ups_json,
    strip_trailing_openwebui_queries_json,
    try_parse_openwebui_follow_ups_json,
    try_parse_openwebui_queries_json,
    web_search_ddg,
)


def _merge_reasoning_text_into_assistant(msg: dict[str, Any]) -> None:
    for key in ("reasoning_content", "reasoning"):
        v = msg.get(key)
        if isinstance(v, str) and v.strip():
            msg["content"] = v
            return


def _normalize_assistant_message_content(msg: dict[str, Any]) -> None:
    c = msg.get("content")
    if isinstance(c, str):
        if not c.strip():
            _merge_reasoning_text_into_assistant(msg)
    elif isinstance(c, list):
        msg["content"] = openai_content_to_text(c, for_delta=False)
    elif c is None:
        msg["content"] = ""

    if not (isinstance(msg.get("content"), str) and (msg.get("content") or "").strip()):
        _merge_reasoning_text_into_assistant(msg)

    if isinstance(msg.get("content"), str):
        t = msg["content"]
        t = strip_trailing_openwebui_follow_ups_json(
            strip_trailing_openwebui_queries_json(t)
        )
        msg["content"] = t


def _ensure_delta_content_for_client(delta: dict[str, Any]) -> None:
    if delta_text(delta):
        return
    for key in ("reasoning_content", "reasoning", "output_text", "text"):
        v = delta.get(key)
        if isinstance(v, str) and v:
            delta["content"] = v
            return


async def _persist_turn_memory(
    user_id: str, last_user_text: str, assistant_text: str
) -> None:
    """После ответа: явное «запомни», LLM-digest фактов и опционально сырой обмен."""
    if not _memory or not last_user_text:
        return
    at = (assistant_text or "").strip()
    if not at:
        return
    try:
        ex = extract_explicit_remember(last_user_text)
        if ex:
            await _memory.add_fact(user_id, ex, tag="explicit")
        chroma_save_message(user_id, "user", last_user_text[:2000])
        chroma_save_message(user_id, "assistant", assistant_text[:4000])
        if settings.memory_llm_digest:
            facts = await digest_turn_to_facts(_client, last_user_text, at)
            for f in facts:
                await _memory.add_fact(user_id, f, tag="fact")
            if (
                not facts
                and not ex
                and settings.memory_raw_fallback
            ):
                await _memory.add_exchange(user_id, last_user_text, assistant_text)
        else:
            await _memory.add_exchange(user_id, last_user_text, assistant_text)
    except Exception as ex:
        logger.debug("memory persist: %s", ex)


def _patch_stream_chunk_for_ui(j: dict[str, Any]) -> None:
    choices = j.get("choices")
    if not isinstance(choices, list) or not choices:
        return
    ch0 = choices[0]
    delta = ch0.get("delta")
    if not isinstance(delta, dict):
        ch0["delta"] = {}
        delta = ch0["delta"]
    _ensure_delta_content_for_client(delta)
    if not delta_text(delta):
        msg = ch0.get("message")
        if isinstance(msg, dict):
            plain = openai_content_to_text(msg.get("content"), for_delta=False)
            if plain:
                delta["content"] = plain
            else:
                for key in ("reasoning_content", "reasoning"):
                    v = msg.get(key)
                    if isinstance(v, str) and v:
                        delta["content"] = v
                        break

    c = delta.get("content")
    if isinstance(c, str):
        s = strip_trailing_openwebui_follow_ups_json(
            strip_trailing_openwebui_queries_json(c)
        )
        if s != c:
            delta["content"] = s
    elif isinstance(c, list):
        plain = openai_content_to_text(c, for_delta=True)
        s = strip_trailing_openwebui_follow_ups_json(
            strip_trailing_openwebui_queries_json(plain)
        )
        if s != plain:
            delta["content"] = s


QUERY_JSON_LEAK_INSTRUCTION = (
    "[Инструкция для модели] Пользователь ждёт обычный связный ответ на языке вопроса. "
    "Не выводи JSON и не используй поле «queries». Не ограничивайся списком поисковых строк — "
    "ответь по существу, используя контекст веб-поиска ниже."
)

FOLLOW_UPS_JSON_LEAK_INSTRUCTION = (
    "[Инструкция для модели] Не выводи JSON с полем «follow_ups». "
    "Ответь обычным текстом на запрос пользователя (включая презентации и уточнения). "
    "Если нужны вопросы пользователю — сформулируй их связным текстом или маркированным списком, без JSON."
)


def _openwebui_json_leak_requires_hold(full: str) -> bool:
    return (
        try_parse_openwebui_queries_json(full) is not None
        or try_parse_openwebui_follow_ups_json(full) is not None
    )


def _leak_queries_for_retry(parsed: list[str], last_text: str) -> list[str]:
    out = [q for q in parsed if (q or "").strip()]
    if out:
        return out[:6]
    q = search_query_from_text(last_text or "")
    if (q or "").strip():
        return [q]
    lt = (last_text or "").strip()
    return [lt[:500]] if lt else ["web search"]


async def _retry_after_queries_json_leak(
    *,
    messages_pre_inject: list[dict[str, Any]],
    extra_parts: list[str],
    parsed_queries: list[str],
    last_text: str,
    new_body_base: dict[str, Any],
    rid: str,
) -> dict[str, Any]:
    qs = _leak_queries_for_retry(parsed_queries, last_text)
    leak_blocks = [web_search_ddg(q) for q in qs]
    leak_fix = "\n\n".join(leak_blocks) + "\n\n" + QUERY_JSON_LEAK_INSTRUCTION
    merged_extra = "\n\n".join(extra_parts) + "\n\n" + leak_fix
    retry_messages = _inject_system(copy.deepcopy(messages_pre_inject), merged_extra)
    retry_body = {**new_body_base, "messages": retry_messages, "stream": False}
    return await _client.post_json(
        "/chat/completions", retry_body, log_context=f"rid={rid} queries-json-retry"
    )


async def _retry_after_follow_ups_json_leak(
    *,
    messages_pre_inject: list[dict[str, Any]],
    extra_parts: list[str],
    new_body_base: dict[str, Any],
    rid: str,
) -> dict[str, Any]:
    merged_extra = "\n\n".join(extra_parts) + "\n\n" + FOLLOW_UPS_JSON_LEAK_INSTRUCTION
    retry_messages = _inject_system(copy.deepcopy(messages_pre_inject), merged_extra)
    retry_body = {**new_body_base, "messages": retry_messages, "stream": False}
    return await _client.post_json(
        "/chat/completions", retry_body, log_context=f"rid={rid} follow-ups-json-retry"
    )


def _configure_logging() -> None:
    level = getattr(logging, settings.log_level, logging.INFO)
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S",
    )
    for name in ("httpx", "httpcore", "httpcore.connection", "hpack"):
        logging.getLogger(name).setLevel(level)


_configure_logging()
logger = logging.getLogger("gpthub")

_TTS_FALLBACK_MP3_CACHE: Optional[bytes] = None


def _tts_fallback_mp3_bytes() -> bytes:
    global _TTS_FALLBACK_MP3_CACHE
    if _TTS_FALLBACK_MP3_CACHE is not None:
        return _TTS_FALLBACK_MP3_CACHE
    p = Path(__file__).resolve().parent.parent / "assets" / "tts_fallback.mp3"
    if p.is_file():
        _TTS_FALLBACK_MP3_CACHE = p.read_bytes()
    else:
        _TTS_FALLBACK_MP3_CACHE = b""
        logger.warning("TTS fallback MP3 missing: %s", p)
    return _TTS_FALLBACK_MP3_CACHE


async def _tts_catalog_model_ids(client: httpx.AsyncClient) -> list[str]:
    base = settings.mws_api_base.rstrip("/")
    try:
        rm = await client.get(
            f"{base}/models",
            headers={"Authorization": f"Bearer {settings.mws_api_key}"},
            timeout=60.0,
        )
        if rm.status_code != 200:
            return []
        data = rm.json().get("data") or []
        ids = [str(m.get("id")) for m in data if m.get("id")]
    except Exception as e:
        logger.debug("TTS catalog GET /models: %s", e)
        return []

    def prio(i: str) -> tuple[int, str]:
        low = i.lower()
        if "tts" in low or "speech" in low or "voice" in low or "dub" in low:
            return (0, i)
        if "whisper" in low:
            return (3, i)
        return (1, i)

    ids.sort(key=prio)
    seen: set[str] = set()
    out: list[str] = []
    for i in ids:
        if i not in seen:
            seen.add(i)
            out.append(i)
    return out[:50]


def _upstream_json_error(e: httpx.HTTPStatusError) -> JSONResponse:
    return JSONResponse(
        {"error": {"message": e.response.text, "type": "upstream_error"}},
        status_code=e.response.status_code,
    )

_models_cache: dict[str, Any] = {"t": 0.0, "data": None}
_memory: Optional[MemoryStore] = None
_rag: Optional[RAGStore] = None
_client = MWSClient()

# TTS: MWS иногда даёт 500 на «чужой» model — перебираем каталог (как при 401/403).
_TTS_CATALOG_RETRY_STATUSES = frozenset({401, 403, 429, 500, 502, 503})


def _bearer_token_from_request(request: Request) -> str:
    h = request.headers.get("authorization") or request.headers.get("Authorization") or ""
    parts = h.split(None, 1)
    if len(parts) != 2 or parts[0].lower() != "bearer":
        return ""
    return (parts[1] or "").strip()


def _mws_api_key_for_audio(request: Request) -> str:
    """Open WebUI шлёт в шлюз Bearer с MWS-ключом (AUDIO_TTS_*/STT); иначе — ключ из env шлюза."""
    tok = _bearer_token_from_request(request)
    # Не прокидывать в MWS сессионный JWT из чужих клиентов (обычно начинается с eyJ).
    if tok and not tok.startswith("eyJ"):
        return tok
    return (settings.mws_api_key or "").strip()


@asynccontextmanager
async def _lifespan(app: FastAPI):
    global _memory, _rag
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    _memory = MemoryStore(str(settings.data_dir / "memory.sqlite"))
    _rag = RAGStore(str(settings.data_dir / "rag.sqlite"))
    yield


app = FastAPI(title="GPTHub Gateway", version="1.0.0", lifespan=_lifespan)


@app.middleware("http")
async def add_request_id_and_timing(request: Request, call_next):
    rid = request.headers.get("x-request-id") or str(uuid.uuid4())
    request.state.request_id = rid
    t0 = time.time()
    response = await call_next(request)
    response.headers["X-Request-ID"] = rid
    logger.info(
        "http %s %s %.3fs rid=%s",
        request.method,
        request.url.path,
        time.time() - t0,
        str(rid)[:12],
    )
    return response


_SSE_HEADERS = {
    "Cache-Control": "no-cache",
    "Connection": "keep-alive",
    "X-Accel-Buffering": "no",
}


def _sse_headers(request: Request) -> dict[str, str]:
    rid = getattr(request.state, "request_id", None) or str(uuid.uuid4())
    return {**_SSE_HEADERS, "X-Request-ID": str(rid)}


def _mws_upstream_stream_headers() -> dict[str, str]:
    return {
        "Authorization": f"Bearer {settings.mws_api_key}",
        "Content-Type": "application/json",
        "Accept-Encoding": "identity",
    }


def _sse_transport_error_chunk(exc: httpx.TransportError) -> str:
    """Finish SSE cleanly when MWS closes the body early (avoids client TransferEncodingError)."""
    return (
        "data: "
        + json.dumps(
            {"error": {"message": f"Upstream stream interrupted: {exc}"}},
            ensure_ascii=False,
        )
        + "\n\n"
    )


_static_root = settings.data_dir / "static"
_static_root.mkdir(parents=True, exist_ok=True)
(_static_root / "presentations").mkdir(parents=True, exist_ok=True)
(_static_root / "music").mkdir(parents=True, exist_ok=True)
(_static_root / "images").mkdir(parents=True, exist_ok=True)


@app.get("/preview/pptx", response_class=HTMLResponse)
async def preview_pptx(request: Request, path: str) -> HTMLResponse:
    rel = (path or "").strip().lstrip("/")
    if ".." in rel or not rel.startswith("static/presentations/") or not rel.lower().endswith(".pptx"):
        return HTMLResponse("<p>Invalid path</p>", status_code=400)
    abs_url = public_static_url(request, rel)
    enc = quote(abs_url, safe="")
    office = f"https://view.officeapps.live.com/op/embed.aspx?src={enc}"
    google = f"https://docs.google.com/viewer?embedded=true&url={enc}"
    html = f"""<!DOCTYPE html>
<html lang="ru"><head><meta charset="utf-8"/><meta name="viewport" content="width=device-width, initial-scale=1"/>
<title>Предпросмотр PPTX</title>
<style>
body {{ font-family: system-ui, sans-serif; margin: 0; background: #121212; color: #e5e5e5; }}
.bar {{ padding: 10px 14px; background: #1e1e1e; font-size: 14px; border-bottom: 1px solid #333; }}
.bar a {{ color: #93c5fd; margin-right: 14px; }}
.note {{ padding: 10px 14px; font-size: 12px; color: #a3a3a3; line-height: 1.4; }}
iframe {{ width: 100%; height: calc(100vh - 120px); border: 0; background: #000; }}
</style></head>
<body>
<div class="bar">
<a href="{office}" target="_blank" rel="noopener">Office Online (новая вкладка)</a>
<a href="{google}" target="_blank" rel="noopener">Google Viewer</a>
<a href="{abs_url}">Скачать PPTX</a>
</div>
<p class="note">Встроенный просмотр загружает файл с URL ниже. Нужен <strong>публичный HTTPS</strong> (задайте GPTHUB_PUBLIC_BASE_URL). На localhost предпросмотр может не сработать — скачайте файл и откройте в PowerPoint или Keynote.</p>
<iframe src="{office}" title="pptx preview"></iframe>
</body></html>"""
    return HTMLResponse(html)


@app.get("/presentation/pdf/{stem}")
async def presentation_pdf_download(stem: str) -> FileResponse:
    stem_ok = validate_stem(stem)
    pptx = pptx_path(stem_ok)
    pdf = pptx.parent / f"{stem_ok}.pdf"
    if not pptx.is_file():
        raise HTTPException(status_code=404, detail="PPTX not found")
    ok = await ensure_pptx_pdf(pptx, pdf)
    if not ok:
        raise HTTPException(
            status_code=503,
            detail="PDF conversion unavailable (LibreOffice / soffice not installed or failed)",
        )
    return FileResponse(
        path=str(pdf),
        media_type="application/pdf",
        filename=f"{stem_ok}.pdf",
    )


app.include_router(presentation_api_router)

_presentation_editor_dir = Path(__file__).resolve().parent / "presentation_editor"
app.mount(
    "/presentation/editor",
    StaticFiles(directory=str(_presentation_editor_dir), html=True),
    name="presentation_editor",
)

app.mount("/static", StaticFiles(directory=str(_static_root)), name="static")


async def get_available_model_ids() -> set[str]:
    global _models_cache
    now = time.time()
    if _models_cache["data"] is None or now - _models_cache["t"] > 300:
        try:
            j = await _client.get_models()
            _models_cache = {"t": now, "data": j}
        except Exception as e:
            logger.warning("models cache refresh failed: %s", e)
            return {settings.auto_model_id, settings.default_llm}
    data = _models_cache["data"] or {}
    ids = {m.get("id") for m in data.get("data", []) if m.get("id")}
    ids.add(settings.auto_model_id)
    return ids


def merge_models_payload(mws_json: dict[str, Any]) -> dict[str, Any]:
    data = list(mws_json.get("data") or [])
    has_auto = any(m.get("id") == settings.auto_model_id for m in data)
    if not has_auto:
        data.insert(
            0,
            {
                "id": settings.auto_model_id,
                "object": "model",
                "created": int(time.time()),
                "owned_by": "gpthub",
                "name": settings.auto_model_display_name,
            },
        )
    return {"object": "list", "data": data}


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/v1/models")
async def list_models() -> JSONResponse:
    try:
        j = await _client.get_models()
    except Exception as e:
        logger.exception("GET /v1/models")
        return JSONResponse(
            {"error": {"message": str(e), "type": "upstream_error"}},
            status_code=502,
        )
    return JSONResponse(merge_models_payload(j))


@app.post("/v1/embeddings")
async def embeddings(request: Request) -> Response:
    body = await request.json()
    try:
        out = await _client.post_json("/embeddings", body)
        return JSONResponse(out)
    except httpx.HTTPStatusError as e:
        return _upstream_json_error(e)


@app.post("/v1/completions")
async def completions(request: Request) -> Response:
    body = await request.json()
    try:
        out = await _client.post_json("/completions", body)
        return JSONResponse(out)
    except httpx.HTTPStatusError as e:
        return _upstream_json_error(e)


@app.post("/v1/images/generations")
async def images(request: Request) -> Response:
    body = await request.json()
    try:
        out = await _client.post_json("/images/generations", body)
        return JSONResponse(out)
    except httpx.HTTPStatusError as e:
        return _upstream_json_error(e)


@app.post("/v1/images/edits")
async def images_edits(request: Request) -> Response:
    body = await request.json()
    try:
        out = await _client.post_json("/images/edits", body)
        return JSONResponse(out)
    except httpx.HTTPStatusError as e:
        return _upstream_json_error(e)


@app.post("/v1/audio/speech")
async def audio_speech(request: Request) -> Response:
    body = await request.json()
    if not isinstance(body, dict):
        return JSONResponse(
            {"error": {"message": "JSON object required", "type": "invalid_request"}},
            status_code=400,
        )
    api_key = _mws_api_key_for_audio(request)
    if not api_key:
        return JSONResponse(
            {
                "error": {
                    "message": "Нет ключа MWS: задайте MWS_API_KEY в шлюзе или Authorization: Bearer при запросе (как Open WebUI).",
                    "type": "missing_api_key",
                }
            },
            status_code=401,
        )
    om = (settings.tts_override_model or "").strip()
    if om:
        body = {**body, "model": om}
    ov = (settings.tts_override_voice or "").strip()
    if ov:
        body = {**body, "voice": ov}
    try:
        async with httpx.AsyncClient(timeout=300.0) as client:
            url = f"{settings.mws_api_base.rstrip('/')}/audio/speech"
            hdrs = {
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            }
            r = await client.post(url, headers=hdrs, content=json.dumps(body))

            if r.status_code in _TTS_CATALOG_RETRY_STATUSES and settings.tts_auto_retry_catalog:
                try:
                    catalog = await _tts_catalog_model_ids(client)
                except Exception as exc:
                    logger.warning("TTS catalog fetch failed: %s", exc)
                    catalog = []
                tried: set[str] = {str(body.get("model") or "")}
                attempts = 0
                for mid in catalog:
                    if mid in tried:
                        continue
                    tried.add(mid)
                    attempts += 1
                    if attempts > 40:
                        break
                    try:
                        r_try = await client.post(
                            url,
                            headers=hdrs,
                            content=json.dumps({**body, "model": mid}),
                        )
                    except Exception as exc:
                        logger.warning("TTS retry POST model=%s: %s", mid, exc)
                        continue
                    ct_try = (r_try.headers.get("content-type") or "").lower()
                    blob = r_try.content or b""
                    looks_audio = (
                        r_try.status_code == 200
                        and "json" not in ct_try
                        and (not blob or blob[:1] != b"{")
                        and (
                            "audio" in ct_try
                            or blob[:2] == b"\xff\xfb"
                            or blob[:3] == b"ID3"
                        )
                    )
                    if looks_audio:
                        logger.info("TTS catalog auto-retry OK model=%s", mid)
                        r = r_try
                        break
                    r = r_try
                    logger.debug("TTS catalog retry model=%s -> HTTP %s", mid, r_try.status_code)

            if r.status_code >= 400:
                err_n = max(500, int(settings.log_upstream_error_chars))
                tail = (r.text or "")[:err_n]
                logger.warning(
                    "MWS TTS POST /audio/speech -> HTTP %s body[:%s]=%r",
                    r.status_code,
                    err_n,
                    tail,
                )
                if r.status_code in (401, 403) and settings.tts_fallback_on_denial:
                    fb = _tts_fallback_mp3_bytes()
                    if fb:
                        logger.warning(
                            "MWS TTS denied after retries; silent fallback MP3 (%s B)",
                            len(fb),
                        )
                        return Response(
                            content=fb,
                            status_code=200,
                            media_type="audio/mpeg",
                            headers={"X-GPTHUB-TTS-Fallback": "silent"},
                        )
                if r.status_code >= 500 and settings.tts_fallback_on_5xx:
                    fb = _tts_fallback_mp3_bytes()
                    if fb:
                        logger.warning(
                            "MWS TTS HTTP %s; silent fallback MP3 (%s B) (GPTHUB_TTS_FALLBACK_ON_5XX)",
                            r.status_code,
                            len(fb),
                        )
                        return Response(
                            content=fb,
                            status_code=200,
                            media_type="audio/mpeg",
                            headers={"X-GPTHUB-TTS-Fallback": "silent-5xx"},
                        )
                if r.status_code in (401, 403):
                    model = body.get("model", "")
                    voice = body.get("voice", "")
                    hint = (
                        f"MWS отклонил синтез речи (HTTP {r.status_code}). "
                        f"Проверьте MWS_API_KEY и доступ к TTS (model={model!r}, voice={voice!r}). "
                        f"Ответ MWS: {tail or '(пусто)'}"
                    )
                    return JSONResponse(
                        {"error": {"message": hint, "type": "mws_audio_denied"}},
                        status_code=r.status_code,
                    )
                if r.status_code >= 500:
                    model = body.get("model", "")
                    hint = (
                        f"MWS вернул ошибку синтеза (HTTP {r.status_code}). "
                        f"Перебор моделей из каталога уже выполнен (если включён GPTHUB_TTS_AUTO_RETRY_CATALOG). "
                        f"model={model!r}. Ответ MWS: {tail or '(пусто)'}"
                    )
                    return JSONResponse(
                        {"error": {"message": hint, "type": "mws_tts_server_error"}},
                        status_code=502,
                    )

            ct = r.headers.get("content-type", "application/octet-stream")
            return Response(content=r.content, status_code=r.status_code, media_type=ct)
    except Exception as e:
        logger.exception("TTS proxy failed: %s", e)
        return JSONResponse(
            {"error": {"message": str(e), "type": "gateway_error"}},
            status_code=502,
        )


@app.post("/v1/audio/transcriptions")
async def transcribe(request: Request) -> Response:
    form = await request.form()
    files = {}
    data = {}
    for k, v in form.multi_items():
        if hasattr(v, "read"):
            files[k] = (getattr(v, "filename", None) or "audio", await v.read())
        else:
            data[k] = v
    if "language" not in data:
        lang = (settings.asr_default_language or "").strip()
        if lang:
            data["language"] = lang
    api_key = _mws_api_key_for_audio(request)
    if not api_key:
        return JSONResponse(
            {
                "error": {
                    "message": "Нет ключа MWS: задайте MWS_API_KEY в шлюзе или Authorization: Bearer при запросе (как Open WebUI).",
                    "type": "missing_api_key",
                }
            },
            status_code=401,
        )
    try:
        async with httpx.AsyncClient(timeout=300.0) as client:
            r = await client.post(
                f"{settings.mws_api_base.rstrip('/')}/audio/transcriptions",
                headers={"Authorization": f"Bearer {api_key}"},
                files=files,
                data=data,
            )
            if r.headers.get("content-type", "").startswith("application/json"):
                return JSONResponse(r.json(), status_code=r.status_code)
            return Response(content=r.content, status_code=r.status_code)
    except Exception as e:
        return JSONResponse(
            {"error": {"message": str(e), "type": "gateway_error"}},
            status_code=502,
        )


def _inject_system(messages: list[dict[str, Any]], extra: str) -> list[dict[str, Any]]:
    if not extra.strip():
        return messages
    ms = [m.copy() for m in messages]
    ins = {"role": "system", "content": extra}
    if ms and ms[0].get("role") == "system":
        c = ms[0].get("content")
        if isinstance(c, str):
            ms[0]["content"] = extra + "\n\n" + c
        else:
            ms[0]["content"] = extra + "\n\n" + json.dumps(c)
    else:
        ms.insert(0, ins)
    return ms


async def maybe_music_demo_chat(
    request: Request,
    messages: list[dict[str, Any]],
    last_text: str,
    stream: bool,
    auto_mode: bool,
) -> Optional[dict[str, Any]]:
    if stream or not auto_mode or not (last_text or "").strip():
        return None
    if not user_wants_music_demo(last_text):
        return None
    if message_has_image(messages) or message_has_audio(messages):
        return None
    available = await get_available_model_ids()
    mid = gena_chat_target()
    if mid not in available:
        if settings.default_llm in available:
            mid = settings.default_llm
        else:
            for x in sorted(available):
                if x != settings.auto_model_id:
                    mid = x
                    break
    try:
        llm_notes = await melody_notes_from_llm(_client, last_text, mid)
        mp3 = build_mp3_from_prompt(last_text, llm_notes)
    except Exception as e:
        logger.warning("music demo failed: %s", e)
        return None
    if not mp3:
        return None
    fname = f"music_{uuid.uuid4().hex[:12]}.mp3"
    rel = f"static/music/{fname}"
    dest = settings.data_dir / rel
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(mp3)
    url = public_static_url(request, rel)
    content = (
        "**Демо-мелодия (MP3, синтез в шлюзе)**\n\n"
        f"[Скачать MP3]({url})\n"
    )
    return {
        "id": f"chatcmpl-gpthub-music-{uuid.uuid4().hex[:10]}",
        "object": "chat.completion",
        "created": int(time.time()),
        "model": mid,
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": content},
                "finish_reason": "stop",
            }
        ],
        "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
    }


async def maybe_image_generation_chat(
    messages: list[dict[str, Any]],
    route_note: str,
    requested_model: str = "",
) -> Optional[dict[str, Any]]:
    want = "image_gen" in route_note
    lu = last_user_message(messages)
    text = _content_to_text(lu.get("content") if lu else None)
    if not text:
        return None
    if not user_wants_image_generation(text, messages, want):
        return None
    if message_has_image(messages) or message_has_audio(messages):
        return None
    ids = await get_available_model_ids()
    try:
        model_id, final_prompt = await prepare_image_generation_prompt(
            _client, text, messages, ids, requested_model
        )
        img_resp = await post_images_with_optional_reference(
            _client, model_id, final_prompt, text, messages
        )
    except Exception as e:
        logger.warning("image gen failed: %s", e)
        return None
    url = await image_api_response_to_data_url(img_resp)
    if not url:
        return None
    content = f"![Изображение]({url})"
    return {
        "id": "chatcmpl-gpthub-img",
        "object": "chat.completion",
        "created": int(time.time()),
        "model": model_id,
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": content},
                "finish_reason": "stop",
            }
        ],
        "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
    }


@app.post("/v1/chat/completions")
async def chat_completions(request: Request) -> Response:
    body = await request.json()
    if not isinstance(body, dict):
        return JSONResponse(
            {
                "error": {
                    "message": "Expected a JSON object with messages, model, etc.",
                    "type": "invalid_request_error",
                }
            },
            status_code=400,
        )
    rid = str(getattr(request.state, "request_id", "") or "")[:24] or "?"
    try:
        logger.info(
            "chat begin rid=%s model=%r stream=%s n_messages=%s",
            rid,
            body.get("model"),
            body.get("stream"),
            len(body.get("messages") or []),
        )
        log_chat_json(logger, "request_in", rid, body, settings.log_json_max_chars)
    except Exception as log_ex:
        logger.warning("chat request log failed (non-fatal): %s", log_ex, exc_info=True)
    try:
        plen = len(json.dumps(body, ensure_ascii=False))
    except Exception:
        plen = 0
    if plen > settings.max_chat_payload_chars:
        return JSONResponse(
            {
                "error": {
                    "message": (
                        f"Слишком большой запрос (~{plen} символов). "
                        f"Лимит: {settings.max_chat_payload_chars} (GPTHUB_MAX_CHAT_PAYLOAD_CHARS)."
                    ),
                    "type": "payload_too_large",
                }
            },
            status_code=413,
        )
    messages: list[dict[str, Any]] = list(body.get("messages") or [])
    messages = await maybe_compress_messages_for_context(_client, messages)
    strip_gena_assistant_markers(messages)

    user_id = (body.get("user") or "default")[:128]
    requested_model = (body.get("model") or "").strip()
    stream = bool(body.get("stream"))

    available = await get_available_model_ids()
    req = normalize_requested_model(requested_model)
    auto_mode = not req or req == settings.auto_model_id

    lu = last_user_message(messages)
    last_text = _content_to_text(lu.get("content") if lu else None)

    want_image = False
    if last_text and stream:
        want_image = should_stream_image_gena(last_text, stream, message_has_image(messages), messages)

    if stream and (auto_mode or want_image):
        if auto_mode and should_stream_presentation(last_text, stream):
            logger.info(
                "gena intercept=presentation stream=1 rid=%s",
                getattr(request.state, "request_id", "")[:12],
            )
            if not has_explicit_presentation_style(last_text):
                return StreamingResponse(
                    stream_presentation_style_prompt(request),
                    media_type="text/event-stream",
                    headers=_sse_headers(request),
                )
            return StreamingResponse(
                stream_presentation_pptx(request, _client, last_text, available),
                media_type="text/event-stream",
                headers=_sse_headers(request),
            )
        if want_image:
            logger.info("gena intercept=image stream=1 requested_model=%r", requested_model)
            return StreamingResponse(
                stream_image_markdown(
                    request, _client, last_text, available, messages, req
                ),
                media_type="text/event-stream",
                headers=_sse_headers(request),
            )

    if not stream:
        music_early = await maybe_music_demo_chat(
            request, messages, last_text, stream, auto_mode
        )
        if music_early:
            return JSONResponse(music_early)
        img_early = await maybe_image_generation_chat(messages, "", req)
        if img_early:
            return JSONResponse(img_early)

    router_mode = (settings.router_mode or "gena").strip().lower()
    if req and req != settings.auto_model_id:
        resolved_model, route_note = apply_manual_route(req, available)
    elif router_mode == "legacy":
        resolved_model, route_note = pick_route_deterministic(messages, available)
    else:
        resolved_model, route_note = pick_route_gena(messages, available)
    logger.info(
        "chat route requested=%r -> model=%s note=%s",
        requested_model,
        resolved_model,
        route_note,
    )

    extra_parts: list[str] = []
    _gid = (settings.gena_system_identity or "").strip()
    if _gid:
        extra_parts.append(_gid)

    explicit_hint = extract_explicit_remember(last_text) if last_text else ""
    if explicit_hint:
        extra_parts.append(
            f"Пользователь просит сохранить в долгосрочной памяти: {explicit_hint}"
        )
    if _memory and last_text:
        mem = await _memory.retrieve(user_id, last_text[:2000])
        if mem:
            extra_parts.append(mem)

    cr = chroma_recall_block(user_id, last_text[:2000])
    if cr:
        extra_parts.append(cr)

    rag_scope = f"{user_id}:rag"
    if _rag and last_text:
        for blob in extract_embeddable_documents(last_text):
            await _rag.ingest_text_async(rag_scope, blob)
        rag_ctx = await _rag.retrieve(rag_scope, last_text)
        if rag_ctx:
            extra_parts.append(rag_ctx)

    for u in extract_urls(last_text):
        try:
            page = await fetch_url_text(u)
            extra_parts.append(f"Содержимое страницы {u}:\n{page[:8000]}")
        except Exception as e:
            extra_parts.append(f"URL {u}: ошибка загрузки {e}")

    messages_pre_inject = copy.deepcopy(messages)
    messages = _inject_system(messages, "\n\n".join(extra_parts))
    if settings.router_debug:
        messages = inject_router_debug(messages, route_note, resolved_model)

    new_body = dict(body)
    new_body["model"] = resolved_model
    new_body["messages"] = messages

    _to_mws = {**new_body, "stream": stream}
    try:
        log_chat_json(logger, "to_mws", rid, _to_mws, settings.log_json_max_chars)
    except Exception as log_ex:
        logger.warning("chat to_mws log failed (non-fatal): %s", log_ex, exc_info=True)

    if not stream:
        try:
            out = await _client.post_json(
                "/chat/completions", new_body, log_context=f"rid={rid}"
            )
        except httpx.HTTPStatusError as e:
            return _upstream_json_error(e)
        try:
            ch0 = (out.get("choices") or [{}])[0]
            msg = ch0.get("message")
            if isinstance(msg, dict):
                _normalize_assistant_message_content(msg)
                if msg.get("content") == "":
                    logger.warning(
                        "upstream returned empty assistant content (model=%s)",
                        resolved_model,
                    )
        except Exception as ex:
            logger.debug("normalize assistant: %s", ex)
        try:
            for _ in range(4):
                ch0 = (out.get("choices") or [{}])[0]
                msg = ch0.get("message")
                plain = (
                    openai_content_to_text(msg.get("content"), for_delta=False)
                    if isinstance(msg, dict)
                    else ""
                )
                if not isinstance(plain, str):
                    break
                leaked_q = try_parse_openwebui_queries_json(plain)
                if leaked_q is not None:
                    logger.warning(
                        "assistant returned only Open WebUI queries JSON; retrying rid=%s",
                        rid,
                    )
                    out = await _retry_after_queries_json_leak(
                        messages_pre_inject=messages_pre_inject,
                        extra_parts=extra_parts,
                        parsed_queries=leaked_q,
                        last_text=last_text or "",
                        new_body_base=new_body,
                        rid=rid,
                    )
                    ch0 = (out.get("choices") or [{}])[0]
                    msg = ch0.get("message")
                    if isinstance(msg, dict):
                        _normalize_assistant_message_content(msg)
                    continue
                leaked_f = try_parse_openwebui_follow_ups_json(plain)
                if leaked_f is not None:
                    logger.warning(
                        "assistant returned only Open WebUI follow_ups JSON; retrying rid=%s",
                        rid,
                    )
                    out = await _retry_after_follow_ups_json_leak(
                        messages_pre_inject=messages_pre_inject,
                        extra_parts=extra_parts,
                        new_body_base=new_body,
                        rid=rid,
                    )
                    ch0 = (out.get("choices") or [{}])[0]
                    msg = ch0.get("message")
                    if isinstance(msg, dict):
                        _normalize_assistant_message_content(msg)
                    continue
                break
        except Exception as ex:
            logger.warning("openwebui task-json retry failed: %s", ex, exc_info=True)
        if _memory and last_text:
            try:
                ch = (out.get("choices") or [{}])[0].get("message", {}).get("content")
                if isinstance(ch, str) and ch:
                    await _persist_turn_memory(user_id, last_text[:2000], ch[:4000])
            except Exception as ex:
                logger.debug("memory save: %s", ex)
        return JSONResponse(out)

    async def gen():
        acc: list[str] = []
        done_sent = False
        mode: str | None = None
        buf: list[str] = []

        async def pump_stream(resp: httpx.Response):
            nonlocal done_sent, mode, acc, buf
            async for line in resp.aiter_lines():
                if not line:
                    continue
                out_line = line
                payload_done = False
                if line.startswith("data:"):
                    payload = line[5:].lstrip()
                    if payload == "[DONE]":
                        payload_done = True
                        done_sent = True
                    else:
                        try:
                            j = json.loads(payload)
                            _patch_stream_chunk_for_ui(j)
                            delta = (j.get("choices") or [{}])[0].get("delta") or {}
                            c = delta_text(delta)
                            if c:
                                acc.append(c)
                            out_line = f"data: {json.dumps(j, ensure_ascii=False)}"
                        except json.JSONDecodeError:
                            pass
                piece = out_line + "\n\n"

                if mode is None:
                    buf.append(piece)
                    full = "".join(acc)
                    if payload_done:
                        if _openwebui_json_leak_requires_hold(full):
                            mode = "hold"
                        else:
                            mode = "streaming"
                            for b in buf:
                                yield b
                            buf = []
                    elif len(full) >= 160:
                        head = full.lstrip()[:800]
                        if head.startswith("{") and (
                            '"queries"' in head or '"follow_ups"' in head
                        ):
                            mode = "hold"
                        else:
                            mode = "streaming"
                            for b in buf:
                                yield b
                            buf = []
                    continue

                if mode == "streaming":
                    yield piece
                    continue

                if mode == "hold":
                    buf.append(piece)
                    continue

        try:
            async with httpx.AsyncClient(timeout=300.0) as client:
                async with client.stream(
                    "POST",
                    f"{settings.mws_api_base.rstrip('/')}/chat/completions",
                    headers=_mws_upstream_stream_headers(),
                    content=json.dumps({**new_body, "stream": True}),
                ) as resp:
                    if resp.status_code >= 400:
                        err = await resp.aread()
                        err_text = err.decode(errors="replace")
                        ec = max(500, int(settings.log_upstream_error_chars))
                        logger.error(
                            "MWS stream /chat/completions rid=%s HTTP %s\nbody:\n%s",
                            rid,
                            resp.status_code,
                            err_text[:ec] or "(empty)",
                        )
                        yield f"data: {json.dumps({'error': {'message': err_text}})}\n\n"
                        return
                    async for item in pump_stream(resp):
                        yield item
        except httpx.RequestError as e:
            logger.exception(
                "MWS stream read failed rid=%s model=%r",
                rid,
                resolved_model,
            )
            err_payload = {
                "error": {
                    "message": (
                        f"Поток от API прерван ({type(e).__name__}). "
                        "Повторите запрос; при повторении отключите streaming в настройках чата."
                    ),
                    "type": "upstream_stream_error",
                }
            }
            yield f"data: {json.dumps(err_payload, ensure_ascii=False)}\n\n"
            if not done_sent:
                yield "data: [DONE]\n\n"
            return
        except Exception as e:
            logger.exception("MWS stream unexpected error rid=%s", rid)
            err_payload = {
                "error": {
                    "message": str(e) or type(e).__name__,
                    "type": "gateway_stream_error",
                }
            }
            yield f"data: {json.dumps(err_payload, ensure_ascii=False)}\n\n"
            if not done_sent:
                yield "data: [DONE]\n\n"
            return

        if mode == "hold":
            full_text = "".join(acc)
            leaked_q = try_parse_openwebui_queries_json(full_text)
            if leaked_q is not None:
                logger.warning(
                    "stream: assistant returned Open WebUI queries JSON; retrying rid=%s",
                    rid,
                )
                try:
                    qs = _leak_queries_for_retry(leaked_q, last_text or "")
                    leak_blocks = [web_search_ddg(q) for q in qs]
                    leak_fix = "\n\n".join(leak_blocks) + "\n\n" + QUERY_JSON_LEAK_INSTRUCTION
                    merged_extra = "\n\n".join(extra_parts) + "\n\n" + leak_fix
                    retry_messages = _inject_system(
                        copy.deepcopy(messages_pre_inject), merged_extra
                    )
                    retry_body = {**new_body, "messages": retry_messages, "stream": True}
                    acc.clear()
                    done_sent = False
                    async with httpx.AsyncClient(timeout=300.0) as client:
                        async with client.stream(
                            "POST",
                            f"{settings.mws_api_base.rstrip('/')}/chat/completions",
                            headers=_mws_upstream_stream_headers(),
                            content=json.dumps(retry_body),
                        ) as resp2:
                            if resp2.status_code >= 400:
                                err = await resp2.aread()
                                err_text = err.decode(errors="replace")
                                logger.warning(
                                    "queries-json retry stream HTTP %s: %s",
                                    resp2.status_code,
                                    err_text[:500],
                                )
                                for b in buf:
                                    yield b
                            else:
                                try:
                                    async for line in resp2.aiter_lines():
                                        if not line:
                                            continue
                                        out_line = line
                                        if line.startswith("data:"):
                                            payload = line[5:].lstrip()
                                            if payload == "[DONE]":
                                                done_sent = True
                                            else:
                                                try:
                                                    j = json.loads(payload)
                                                    _patch_stream_chunk_for_ui(j)
                                                    delta = (j.get("choices") or [{}])[
                                                        0
                                                    ].get("delta") or {}
                                                    c = delta_text(delta)
                                                    if c:
                                                        acc.append(c)
                                                    out_line = f"data: {json.dumps(j, ensure_ascii=False)}"
                                                except json.JSONDecodeError:
                                                    pass
                                        yield out_line + "\n\n"
                                except httpx.TransportError as ex:
                                    logger.warning(
                                        "queries-json retry stream TransportError: %s",
                                        ex,
                                        exc_info=True,
                                    )
                                    yield _sse_transport_error_chunk(ex)
                                if not done_sent:
                                    yield "data: [DONE]\n\n"
                except Exception as ex:
                    logger.warning(
                        "stream queries-json retry failed: %s", ex, exc_info=True
                    )
                    for b in buf:
                        yield b
            elif try_parse_openwebui_follow_ups_json(full_text) is not None:
                logger.warning(
                    "stream: assistant returned Open WebUI follow_ups JSON; retrying rid=%s",
                    rid,
                )
                try:
                    merged_extra = (
                        "\n\n".join(extra_parts) + "\n\n" + FOLLOW_UPS_JSON_LEAK_INSTRUCTION
                    )
                    retry_messages = _inject_system(
                        copy.deepcopy(messages_pre_inject), merged_extra
                    )
                    retry_body = {**new_body, "messages": retry_messages, "stream": True}
                    acc.clear()
                    done_sent = False
                    async with httpx.AsyncClient(timeout=300.0) as client:
                        async with client.stream(
                            "POST",
                            f"{settings.mws_api_base.rstrip('/')}/chat/completions",
                            headers=_mws_upstream_stream_headers(),
                            content=json.dumps(retry_body),
                        ) as resp2:
                            if resp2.status_code >= 400:
                                err = await resp2.aread()
                                err_text = err.decode(errors="replace")
                                logger.warning(
                                    "follow-ups-json retry stream HTTP %s: %s",
                                    resp2.status_code,
                                    err_text[:500],
                                )
                                for b in buf:
                                    yield b
                            else:
                                try:
                                    async for line in resp2.aiter_lines():
                                        if not line:
                                            continue
                                        out_line = line
                                        if line.startswith("data:"):
                                            payload = line[5:].lstrip()
                                            if payload == "[DONE]":
                                                done_sent = True
                                            else:
                                                try:
                                                    j = json.loads(payload)
                                                    _patch_stream_chunk_for_ui(j)
                                                    delta = (j.get("choices") or [{}])[
                                                        0
                                                    ].get("delta") or {}
                                                    c = delta_text(delta)
                                                    if c:
                                                        acc.append(c)
                                                    out_line = f"data: {json.dumps(j, ensure_ascii=False)}"
                                                except json.JSONDecodeError:
                                                    pass
                                        yield out_line + "\n\n"
                                except httpx.TransportError as ex:
                                    logger.warning(
                                        "follow-ups-json retry stream TransportError: %s",
                                        ex,
                                        exc_info=True,
                                    )
                                    yield _sse_transport_error_chunk(ex)
                                if not done_sent:
                                    yield "data: [DONE]\n\n"
                except Exception as ex:
                    logger.warning(
                        "stream follow-ups-json retry failed: %s", ex, exc_info=True
                    )
                    for b in buf:
                        yield b
            else:
                for b in buf:
                    yield b
        elif mode is None:
            for b in buf:
                yield b
            if not done_sent:
                yield "data: [DONE]\n\n"
        elif mode == "streaming":
            if not done_sent:
                yield "data: [DONE]\n\n"

        if not acc:
            logger.warning(
                "stream ended with no text deltas (model=%s requested=%r); "
                "check upstream format or MWS key/models",
                resolved_model,
                requested_model,
            )
        if _memory and last_text and acc:
            await _persist_turn_memory(
                user_id, last_text[:2000], "".join(acc)[:4000]
            )

    return StreamingResponse(
        gen(),
        media_type="text/event-stream",
        headers=_sse_headers(request),
    )
