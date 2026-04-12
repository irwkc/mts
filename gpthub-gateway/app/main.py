"""
OpenAI-совместимый шлюз: MWS GPT + автроутер, память, RAG, веб-инструменты.
"""

from __future__ import annotations

import json
import logging
import time
from typing import Any, Optional

import httpx
from fastapi import FastAPI, Request, Response
from fastapi.responses import JSONResponse, StreamingResponse

from app.config import settings
from app.memory_store import MemoryStore
from app.mws_client import MWSClient
from app.rag_store import RAGStore, extract_embeddable_documents
from app.router_logic import (
    IMAGE_GEN_RE,
    inject_router_debug,
    last_user_message,
    pick_route,
    _content_to_text,
    message_has_image,
    message_has_audio,
)
from app.web_tools import (
    deep_research_ddg,
    extract_urls,
    fetch_url_text,
    search_query_from_text,
    should_run_deep_research,
    should_run_web_search,
    web_search_ddg,
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("gpthub")

app = FastAPI(title="GPTHub Gateway", version="1.0.0")

_models_cache: dict[str, Any] = {"t": 0.0, "data": None}
_memory: Optional[MemoryStore] = None
_rag: Optional[RAGStore] = None
_client = MWSClient()


@app.on_event("startup")
async def startup() -> None:
    global _memory, _rag
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    _memory = MemoryStore(str(settings.data_dir / "memory.sqlite"))
    _rag = RAGStore(str(settings.data_dir / "rag.sqlite"))


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
                "name": "GPTHub Auto (router)",
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
        return JSONResponse(
            {"error": {"message": e.response.text, "type": "upstream_error"}},
            status_code=e.response.status_code,
        )


@app.post("/v1/completions")
async def completions(request: Request) -> Response:
    body = await request.json()
    try:
        out = await _client.post_json("/completions", body)
        return JSONResponse(out)
    except httpx.HTTPStatusError as e:
        return JSONResponse(
            {"error": {"message": e.response.text, "type": "upstream_error"}},
            status_code=e.response.status_code,
        )


@app.post("/v1/images/generations")
async def images(request: Request) -> Response:
    body = await request.json()
    try:
        out = await _client.post_json("/images/generations", body)
        return JSONResponse(out)
    except httpx.HTTPStatusError as e:
        return JSONResponse(
            {"error": {"message": e.response.text, "type": "upstream_error"}},
            status_code=e.response.status_code,
        )


@app.post("/v1/audio/transcriptions")
async def transcribe(request: Request) -> Response:
    # multipart → MWS
    form = await request.form()
    files = {}
    data = {}
    for k, v in form.multi_items():
        if hasattr(v, "read"):
            files[k] = (getattr(v, "filename", None) or "audio", await v.read())
        else:
            data[k] = v
    try:
        async with httpx.AsyncClient(timeout=300.0) as client:
            r = await client.post(
                f"{settings.mws_api_base.rstrip('/')}/audio/transcriptions",
                headers={"Authorization": f"Bearer {settings.mws_api_key}"},
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


async def maybe_image_generation_chat(
    messages: list[dict[str, Any]],
    route_note: str,
) -> Optional[dict[str, Any]]:
    """Вызов /v1/images/generations при явном запросе на картинку (текстовый промпт)."""
    want = "image_gen" in route_note
    lu = last_user_message(messages)
    text = _content_to_text(lu.get("content") if lu else None)
    if not want and not IMAGE_GEN_RE.search(text):
        return None
    prompt = text
    if message_has_image(messages) or message_has_audio(messages):
        return None
    if len(prompt) < 3:
        return None
    model_id = settings.image_gen_model
    ids = await get_available_model_ids()
    if model_id not in ids:
        for c in ("qwen-image", "sd3.5-large-image", "z-image-turbo"):
            if c in ids:
                model_id = c
                break
    try:
        img_body = {"model": model_id, "prompt": prompt[:4000], "n": 1, "size": "1024x1024"}
        img_resp = await _client.post_json("/images/generations", img_body)
    except Exception as e:
        logger.warning("image gen failed: %s", e)
        return None
    # OpenAI images format
    url = ""
    if img_resp.get("data") and len(img_resp["data"]) > 0:
        url = img_resp["data"][0].get("url") or ""
        b64 = img_resp["data"][0].get("b64_json")
        if b64:
            url = f"data:image/png;base64,{b64}"
    if not url:
        return None
    content = f"Сгенерировано изображение:\n\n![image]({url})"
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
    messages: list[dict[str, Any]] = list(body.get("messages") or [])
    user_id = (body.get("user") or "default")[:128]
    requested_model = (body.get("model") or "").strip()
    stream = bool(body.get("stream"))

    available = await get_available_model_ids()
    resolved_model, route_note = pick_route(messages, requested_model, available)
    logger.info(
        "chat route requested=%r -> model=%s note=%s",
        requested_model,
        resolved_model,
        route_note,
    )

    # Долгосрочная память + RAG scope
    lu = last_user_message(messages)
    last_text = _content_to_text(lu.get("content") if lu else None)

    extra_parts: list[str] = []
    if _memory and last_text:
        mem = await _memory.retrieve(user_id, last_text[:2000])
        if mem:
            extra_parts.append(mem)

    rag_scope = f"{user_id}:rag"
    if _rag and last_text:
        for blob in extract_embeddable_documents(last_text):
            await _rag.ingest_text_async(rag_scope, blob)
        rag_ctx = await _rag.retrieve(rag_scope, last_text)
        if rag_ctx:
            extra_parts.append(rag_ctx)

    if last_text:
        if should_run_deep_research(last_text):
            extra_parts.append(deep_research_ddg(last_text))
        elif should_run_web_search(last_text):
            q = search_query_from_text(last_text)
            extra_parts.append(web_search_ddg(q))

    for u in extract_urls(last_text):
        try:
            page = await fetch_url_text(u)
            extra_parts.append(f"Содержимое страницы {u}:\n{page[:8000]}")
        except Exception as e:
            extra_parts.append(f"URL {u}: ошибка загрузки {e}")

    messages = _inject_system(messages, "\n\n".join(extra_parts))
    if settings.router_debug:
        messages = inject_router_debug(messages, route_note, resolved_model)

    img_chat = await maybe_image_generation_chat(messages, route_note)
    if img_chat:
        return JSONResponse(img_chat)

    new_body = dict(body)
    new_body["model"] = resolved_model
    new_body["messages"] = messages

    # логика памяти после ответа — только если не stream (ниже для stream буферизуем)
    if not stream:
        try:
            out = await _client.post_json("/chat/completions", new_body)
        except httpx.HTTPStatusError as e:
            return JSONResponse(
                {"error": {"message": e.response.text, "type": "upstream_error"}},
                status_code=e.response.status_code,
            )
        # сохранить обмен
        if _memory and last_text:
            try:
                ch = out["choices"][0]["message"]["content"]
                if isinstance(ch, str):
                    await _memory.add_exchange(user_id, last_text[:2000], ch[:4000])
            except Exception as ex:
                logger.debug("memory save: %s", ex)
        return JSONResponse(out)

    async def gen():
        acc: list[str] = []
        async with httpx.AsyncClient(timeout=300.0) as client:
            async with client.stream(
                "POST",
                f"{settings.mws_api_base.rstrip('/')}/chat/completions",
                headers={
                    "Authorization": f"Bearer {settings.mws_api_key}",
                    "Content-Type": "application/json",
                },
                content=json.dumps({**new_body, "stream": True}),
            ) as resp:
                if resp.status_code >= 400:
                    err = await resp.aread()
                    yield f"data: {json.dumps({'error': {'message': err.decode()}})}\n\n"
                    return
                async for line in resp.aiter_lines():
                    if not line:
                        continue
                    if line.startswith("data: "):
                        payload = line[6:].strip()
                        if payload == "[DONE]":
                            yield "data: [DONE]\n\n"
                            break
                        try:
                            j = json.loads(payload)
                            delta = (j.get("choices") or [{}])[0].get("delta") or {}
                            c = delta.get("content")
                            if isinstance(c, str):
                                acc.append(c)
                        except json.JSONDecodeError:
                            pass
                    yield line + "\n\n"
        if _memory and last_text and acc:
            await _memory.add_exchange(user_id, last_text[:2000], "".join(acc)[:4000])

    return StreamingResponse(gen(), media_type="text/event-stream")
