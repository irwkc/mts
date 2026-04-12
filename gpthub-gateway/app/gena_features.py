"""
Фичи gena/router: стрим презентаций PPTX, стрим картинок, стрим deep research, SSE-хелперы.
"""

from __future__ import annotations

import json
import logging
import re
import uuid
from typing import AsyncGenerator

import httpx
from fastapi import Request

from app.config import settings
from app.image_utils import image_api_response_to_sse_href
from app.presentation_pptx import (
    build_colorful_pptx,
    parse_presentation_json,
    resolve_slide_images,
)
from app.mws_client import MWSClient
from app.router_logic import IMAGE_GEN_RE, MUSIC_GEN_RE, PRESENTATION_RE, gena_chat_target
from app.web_tools import (
    deep_research_ddg,
    extract_urls,
    fetch_url_text,
    should_run_deep_research,
    web_search_ddg,
)

logger = logging.getLogger("gpthub.gena")


def friendly_stream_error(exc: BaseException) -> str:
    """Короткое сообщение пользователю при сбое перехвата gena (стрим)."""
    if isinstance(exc, httpx.HTTPStatusError):
        code = exc.response.status_code
        if code == 429:
            return "Сервис моделей временно перегружен (лимит запросов). Попробуйте позже."
        if code >= 500:
            return "Временная ошибка сервера моделей (MWS). Повторите запрос."
        return f"Ошибка API моделей (код {code})."
    if isinstance(exc, httpx.TimeoutException):
        return "Превышено время ожидания ответа от моделей."
    if isinstance(exc, json.JSONDecodeError):
        return "Некорректный ответ модели (JSON). Упростите или сократите запрос."
    s = str(exc).strip()
    return (s[:500] if s else "Неизвестная ошибка.")


def sse_delta(content: str) -> str:
    esc = json.dumps(content, ensure_ascii=False)
    return f'data: {{"choices": [{{"delta": {{"content": {esc} }}}}]}}\n\n'


def _pick_model(preferred: str, available: set[str], fallback: str) -> str:
    if preferred in available:
        return preferred
    if fallback in available:
        return fallback
    for x in sorted(available):
        if x != settings.auto_model_id:
            return x
    return fallback


def public_static_url(request: Request, rel_path: str) -> str:
    """URL для скачивания файлов из /static/…

    Open WebUI дергает шлюз по Docker-DNS (Host: gpthub-gateway:8080) — такой absolute URL
    в чате не открывается из браузера. Явный GPTHUB_PUBLIC_BASE_URL, затем X-Forwarded-*,
    иначе для gpthub-gateway — корневой путь /static/… (тот же origin, что у UI за nginx).
    """
    rel_path = rel_path.lstrip("/")
    base = (settings.public_base_url or "").strip().rstrip("/")
    if base:
        return f"{base}/{rel_path}"

    fwd = (request.headers.get("x-forwarded-host") or "").strip()
    if fwd:
        host = fwd.split(",")[0].strip()
        proto = (request.headers.get("x-forwarded-proto") or "https").strip().split(",")[0].strip()
        if proto not in ("http", "https"):
            proto = "https"
        return f"{proto}://{host}/{rel_path}"

    if (request.url.hostname or "").lower() == "gpthub-gateway":
        return f"/{rel_path}"

    return str(request.base_url).rstrip("/") + "/" + rel_path


async def stream_presentation_pptx(
    request: Request,
    client: MWSClient,
    prompt: str,
    available_ids: set[str],
) -> AsyncGenerator[str, None]:
    yield sse_delta(
        "**[gena · презентация]** — веб-поиск, структура слайдов, картинки (веб/нейро), PPTX + JSON.\n\n"
    )
    yield sse_delta("*(Презентация: ищу материалы в интернете…)*\n\n")
    research = web_search_ddg((prompt or "")[:600], max_results=6)
    page_bits: list[str] = []
    for u in extract_urls(research, limit=2):
        try:
            pg = await fetch_url_text(u, max_chars=3200)
            page_bits.append(f"--- {u} ---\n{pg[:2800]}")
        except Exception:
            continue
    page_extra = "\n\n".join(page_bits)

    user_bundle = (
        f"Запрос пользователя:\n{prompt[:8000]}\n\n"
        f"Сниппеты веб-поиска (используй для фактов и ссылок sources):\n{research[:7000]}"
    )
    if page_extra:
        user_bundle += f"\n\nФрагменты страниц для анализа:\n{page_extra[:6000]}"

    yield sse_delta("*(Презентация: генерирую структуру слайдов и заметки докладчика…)*\n\n")
    model = _pick_model(settings.gena_code_model, available_ids, settings.default_llm)
    system_prompt = (
        "Ты — автор презентаций (как умный ассистент с веб-контекстом): факты, структура, заметки докладчика, иллюстрации.\n"
        "Верни СТРОГО один JSON-объект без markdown. Формат:\n"
        '{"deck_title":"Краткое название презентации",'
        '"slides":['
        '{"title":"Заголовок слайда","subtitle":"Подзаголовок или пустая строка",'
        '"bullets":["пункт 1","пункт 2"],'
        '"speaker_notes":"2–6 предложений: что говорить с экрана, акценты, переходы (редактируется в PowerPoint в заметках к слайду)",'
        '"accent":"#RRGGBB",'
        '"image_mode":"auto|search|generate",'
        '"image_query":"ключи на английском для поиска картинок в интернете (для search/auto)",'
        '"image_prompt":"описание на английском для нейро-картинки если generate или fallback",'
        '"sources":[{"title":"кратко","url":"https://..."}],'
        '"visual_style":"corporate|modern|bold|compact"}'
        "]}\n"
        "Правила: 5–10 слайдов; разные гармоничные accent; visual_style задаёт шрифты и плотность верстки; "
        "image_mode: search — только реальные фото/схемы из интернета; generate — только нейро-иллюстрация; "
        "auto — сначала подобрать изображение из веба, иначе нейро. "
        "sources — только реальные URL из контекста веб-поиска выше (0–2 на слайд). "
        "Не выдумывай URL."
    )
    try:
        data = await client.post_json(
            "/chat/completions",
            {
                "model": model,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_bundle[:24000]},
                ],
                "temperature": 0.35,
                "max_tokens": 8000,
            },
        )
        raw = (data.get("choices") or [{}])[0].get("message", {}).get("content") or ""
        deck_title, slides_data = parse_presentation_json(raw)
        max_slides = max(1, int(settings.gena_max_presentation_slides))
        slides_data = [s for s in slides_data if isinstance(s, dict)][:max_slides]
        if len(slides_data) < 1:
            raise ValueError("no slides in JSON")

        plan_lines = [f"**{deck_title}**" if deck_title else "**Презентация**"]
        for i, s in enumerate(slides_data, 1):
            plan_lines.append(f"{i}. {s.get('title', 'Слайд')}")
        yield sse_delta(
            "**План слайдов** (дальше — картинки и сборка; текст и заметки можно править в PowerPoint):\n\n"
            + "\n".join(plan_lines)
            + "\n\n"
        )

        yield sse_delta("*(Презентация: подбираю изображения — веб и нейросеть…)*\n\n")
        image_paths = await resolve_slide_images(client, slides_data, available_ids)

        yield sse_delta("*(Презентация: собираю PPTX с заметками докладчика…)*\n\n")

        static_dir = settings.data_dir / "static" / "presentations"
        static_dir.mkdir(parents=True, exist_ok=True)
        stem = f"presentation_{uuid.uuid4().hex[:10]}"
        fname = f"{stem}.pptx"
        fpath = static_dir / fname

        build_colorful_pptx(slides_data, image_paths, fpath, deck_title=deck_title)
        url = public_static_url(request, f"static/presentations/{fname}")
        yield sse_delta(
            "✅ **Презентация готова** — цветные слайды, **заметки докладчика** (в PowerPoint или Keynote: режим докладчика / заметки), "
            "картинки из **интернета** и/или **нейросети** по полю `image_mode`.\n\n"
            f"[Скачать PPTX]({url})\n\n"
        )
    except Exception as e:
        logger.exception("presentation")
        yield sse_delta(f"**Ошибка презентации.** {friendly_stream_error(e)}\n\n")
    yield "data: [DONE]\n\n"


async def stream_music_demo(
    request: Request,
    client: MWSClient,
    prompt: str,
    available_ids: set[str],
) -> AsyncGenerator[str, None]:
    """SSE: статусы + ссылка на демо MP3 (как у картинки, но для музыки)."""
    from app.music_demo import build_mp3_from_prompt, melody_notes_from_llm

    yield sse_delta("**[gena · музыка]** — демо-мелодия (~1–1.5 мин), синус по нотам.\n\n")
    yield sse_delta("*(Демо-мелодия: подбираю ноты…)*\n\n")
    mid = gena_chat_target()
    if mid not in available_ids:
        if settings.default_llm in available_ids:
            mid = settings.default_llm
        else:
            mid = next(iter(sorted(available_ids - {settings.auto_model_id})), settings.default_llm)
    try:
        llm_notes = await melody_notes_from_llm(client, prompt, mid)
        yield sse_delta("*(Демо-мелодия: синтез MP3…)*\n\n")
        mp3 = build_mp3_from_prompt(prompt, llm_notes)
    except Exception as e:
        logger.exception("music demo stream")
        yield sse_delta(f"**Не удалось сгенерировать MP3.** {friendly_stream_error(e)}\n\n")
        yield "data: [DONE]\n\n"
        return

    static_dir = settings.data_dir / "static" / "music"
    static_dir.mkdir(parents=True, exist_ok=True)
    fname = f"demo_{uuid.uuid4().hex[:12]}.mp3"
    (static_dir / fname).write_bytes(mp3)
    url = public_static_url(request, f"static/music/{fname}")
    yield sse_delta(
        "Демо-мелодия под песню (~1–1.5 мин, простой синус по нотам, не студийный трек):\n\n"
        f"[Скачать MP3]({url})\n\n"
    )
    yield "data: [DONE]\n\n"


async def stream_image_markdown(
    request: Request,
    client: MWSClient,
    prompt: str,
    available_ids: set[str],
) -> AsyncGenerator[str, None]:
    yield sse_delta("**[gena · изображение]** — нейро-генерация по запросу.\n\n")
    yield sse_delta("*(Генерация изображения…)*\n\n")
    model_id = settings.image_gen_model
    if model_id not in available_ids:
        for c in ("qwen-image", "qwen-image-lightning", "sd3.5-large-image", "z-image-turbo"):
            if c in available_ids:
                model_id = c
                break
    try:
        enhance = await client.post_json(
            "/chat/completions",
            {
                "model": _pick_model(gena_chat_target(), available_ids, settings.default_llm),
                "messages": [
                    {
                        "role": "system",
                        "content": "Output ONLY a concise English image generation prompt, no other text.",
                    },
                    {"role": "user", "content": prompt[:2000]},
                ],
                "max_tokens": 500,
            },
        )
        ep = (
            (enhance.get("choices") or [{}])[0]
            .get("message", {})
            .get("content", "")
            .strip()
        )
        if ep:
            prompt = ep
    except Exception:
        pass

    try:
        img_resp = await client.post_json(
            "/images/generations",
            {
                "model": model_id,
                "prompt": prompt[:4000],
                "n": 1,
                "size": "1024x1024",
                "response_format": "b64_json",  # сразу base64 → сохраняем в static, не в SSE
            },
        )
        href = await image_api_response_to_sse_href(img_resp, settings.data_dir)
        if href.startswith("http://") or href.startswith("https://"):
            display = href
        elif href.startswith("static/"):
            display = public_static_url(request, href)
        else:
            display = href
        if display:
            yield sse_delta(f"![Изображение]({display})\n\n")
        else:
            yield sse_delta("Не удалось получить ссылку на изображение.\n\n")
    except Exception as e:
        logger.exception("stream_image")
        yield sse_delta(f"**Ошибка генерации изображения.** {friendly_stream_error(e)}\n\n")
    yield "data: [DONE]\n\n"


async def stream_deep_research(
    client: MWSClient,
    user_prompt: str,
    available_ids: set[str],
) -> AsyncGenerator[str, None]:
    yield sse_delta("**[gena · Deep Research]** — веб-поиск + страницы + отчёт.\n\n")
    yield sse_delta("*(Deep Research: собираю источники…)*\n\n")
    block = deep_research_ddg(user_prompt)
    urls = extract_urls(block)[:3]
    fetched: list[str] = []
    for u in urls:
        t = await fetch_url_text(u, max_chars=6000)
        fetched.append(f"=== {u} ===\n{t}")
    ctx = block + "\n\n" + "\n\n".join(fetched)
    yield sse_delta("*(Deep Research: пишу отчёт…)*\n\n")

    model = _pick_model(settings.gena_long_doc_model, available_ids, settings.default_llm)
    sys_msg = (
        "Ты — исследователь. По теме пользователя и контексту из веба дай структурированный отчёт в Markdown.\n\n"
        f"КОНТЕКСТ:\n{ctx[:24000]}"
    )
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": sys_msg},
            {"role": "user", "content": user_prompt[:8000]},
        ],
        "stream": True,
        "temperature": 0.4,
    }
    headers = {
        "Authorization": f"Bearer {settings.mws_api_key}",
        "Content-Type": "application/json",
    }
    done = False
    async with httpx.AsyncClient(timeout=300.0) as http:
        async with http.stream(
            "POST",
            f"{settings.mws_api_base.rstrip('/')}/chat/completions",
            headers=headers,
            content=json.dumps(payload),
        ) as resp:
            if resp.status_code >= 400:
                err = await resp.aread()
                yield sse_delta(
                    f"**Ошибка MWS** (код {resp.status_code}): {err.decode()[:400]}\n\n"
                )
                yield "data: [DONE]\n\n"
                return
            async for line in resp.aiter_lines():
                if not line:
                    continue
                if line.startswith("data:"):
                    pl = line[5:].lstrip()
                    if pl == "[DONE]":
                        done = True
                        yield "data: [DONE]\n\n"
                        break
                    yield line + "\n\n"
            if not done:
                yield "data: [DONE]\n\n"


def should_stream_presentation(last_text: str, stream: bool) -> bool:
    return bool(stream and last_text and PRESENTATION_RE.search(last_text))


def should_stream_deep_gena(last_text: str, stream: bool) -> bool:
    return bool(stream and last_text and should_run_deep_research(last_text))


def should_stream_music_gena(
    last_text: str, stream: bool, has_image: bool, has_audio: bool
) -> bool:
    return bool(
        stream
        and last_text
        and not has_image
        and not has_audio
        and MUSIC_GEN_RE.search(last_text)
    )


def should_stream_image_gena(last_text: str, stream: bool, has_image: bool) -> bool:
    return bool(
        stream
        and last_text
        and not has_image
        and IMAGE_GEN_RE.search(last_text)
        and not MUSIC_GEN_RE.search(last_text)
    )
