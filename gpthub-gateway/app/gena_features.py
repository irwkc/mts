"""
Фичи gena/router: стрим презентаций PPTX, стрим картинок, стрим deep research, SSE-хелперы.
"""

from __future__ import annotations

import json
import logging
import re
import uuid
from pathlib import Path
from typing import Any, AsyncGenerator, Optional
from urllib.parse import quote

import httpx
from fastapi import Request

from app.config import settings
from app.image_utils import image_api_response_to_sse_href
from app.presentation_pptx import (
    build_colorful_pptx,
    parse_presentation_json,
    resolve_slide_images_progress,
    write_presentation_sidecar,
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


def sse_delta(content: str = "", gena: Optional[dict[str, Any]] = None) -> str:
    """
    OpenAI-совместимый SSE. Поле delta.gena — структурированные события для Open WebUI (виджет).
    Пустой контент + только gena: подставляем zero-width space, чтобы UI не ругался на пустой delta.
    """
    c = content if content is not None else ""
    if gena is not None and not (c and c.strip()):
        c = "\u200b"
    delta: dict[str, Any] = {"content": c}
    if gena is not None:
        delta["gena"] = gena
    return "data: " + json.dumps({"choices": [{"delta": delta}]}, ensure_ascii=False) + "\n\n"


def _path_to_static_url(request: Request, p: Optional[Path]) -> Optional[str]:
    if p is None or not p.is_file():
        return None
    try:
        rel = p.resolve().relative_to(settings.data_dir.resolve())
        return public_static_url(request, str(rel).replace("\\", "/"))
    except ValueError:
        return None


def _slides_gena_summary(slides_data: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for i, s in enumerate(slides_data):
        if not isinstance(s, dict):
            continue
        bullets = s.get("bullets")
        nbul = len(bullets) if isinstance(bullets, list) else 0
        out.append(
            {
                "index": i,
                "title": (str(s.get("title") or "")[:240]),
                "subtitle": (str(s.get("subtitle") or "")[:160]),
                "bullet_count": nbul,
                "image_mode": str(s.get("image_mode") or "auto"),
            }
        )
    return out


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


def presentation_preview_markdown(request: Request, fname: str) -> str:
    """Одна ссылка: страница шлюза с iframe (рядом с тем же origin, что и PPTX)."""
    rel = f"static/presentations/{fname}"
    base = str(request.base_url).rstrip("/")
    page = f"{base}/preview/pptx?path={quote(rel, safe='')}"
    return f"[Предпросмотр]({page})\n\n"


# Выбор стиля в Open WebUI: пользователь жмёт кнопку → в чат уходит «[gena_style:id] …».
_PRESENTATION_STYLE_HEAD = re.compile(r"^\s*\[gena_style:([a-z0-9_-]+)\]\s*", re.I)

# Список для кнопок в виджете (id стабильны для API).
PRESENTATION_STYLE_CHOICES: list[dict[str, str]] = [
    {"id": "minimal", "label": "Минимализм", "emoji": "◻"},
    {"id": "corporate", "label": "Деловой", "emoji": "◼"},
    {"id": "modern", "label": "Современный", "emoji": "◆"},
    {"id": "bold", "label": "Яркий", "emoji": "●"},
    {"id": "playful", "label": "Лёгкий", "emoji": "◎"},
]

_PRESENTATION_STYLE_IDS = {x["id"] for x in PRESENTATION_STYLE_CHOICES}

_PRESENTATION_STYLE_HINTS: dict[str, str] = {
    "minimal": (
        "Визуальный стиль презентации: минимализм — много воздуха, 1–2 спокойных акцента, "
        "короткие заголовки, без визуального шума."
    ),
    "corporate": (
        "Визуальный стиль: деловой — сдержанная палитра, чёткая сетка, строгая типографика, "
        "как в корпоративных шаблонах."
    ),
    "modern": (
        "Визуальный стиль: современный — крупная типографика, мягкие контрасты, "
        "аккуратные градиенты или плоские плашки."
    ),
    "bold": (
        "Визуальный стиль: яркий — высокий контраст, насыщенные акценты, смелые заголовки, "
        "динамичная компоновка."
    ),
    "playful": (
        "Визуальный стиль: лёгкий — дружелюбные акценты, больше иллюстративности, "
        "мягкие формы; без перегруза."
    ),
}


def split_presentation_style(prompt: str) -> tuple[str, Optional[str]]:
    """Убрать префикс [gena_style:id] из текста; вернуть (текст, id или None)."""
    t = (prompt or "").strip()
    m = _PRESENTATION_STYLE_HEAD.match(t)
    if not m:
        return t, None
    sid = m.group(1).lower()
    rest = t[m.end() :].strip()
    if sid not in _PRESENTATION_STYLE_IDS:
        return rest, None
    return rest, sid


def _normalize_presentation_style(sid: Optional[str]) -> str:
    if sid and sid in _PRESENTATION_STYLE_IDS:
        return sid
    return "corporate"


def _presentation_slide_cap(prompt: str) -> int:
    """Число слайдов из запроса («на 20 слайдов») с ограничением GPTHUB_MAX_PRESENTATION_SLIDES."""
    mx = max(1, int(settings.gena_max_presentation_slides))
    t = (prompt or "")[:2500]
    m = re.search(r"(?:на|до)\s*(\d{1,2})\s*слайд", t, re.I)
    if not m:
        m = re.search(r"(\d{1,2})\s*слайд", t, re.I)
    if m:
        try:
            return max(1, min(mx, int(m.group(1))))
        except ValueError:
            pass
    return mx


async def stream_presentation_pptx(
    request: Request,
    client: MWSClient,
    prompt: str,
    available_ids: set[str],
) -> AsyncGenerator[str, None]:
    clean_prompt, style_id = split_presentation_style(prompt)
    if not style_id:
        yield sse_delta(
            "",
            gena={
                "type": "presentation_style_prompt",
                "prompt_plain": clean_prompt,
                "styles": PRESENTATION_STYLE_CHOICES,
            },
        )
        yield "data: [DONE]\n\n"
        return

    style_key = _normalize_presentation_style(style_id)
    style_hint = _PRESENTATION_STYLE_HINTS.get(
        style_key, _PRESENTATION_STYLE_HINTS["corporate"]
    )

    slide_cap = _presentation_slide_cap(clean_prompt)
    yield sse_delta(
        "**[gena · презентация]**\n\n",
        gena={
            "type": "presentation_start",
            "slide_cap": slide_cap,
            "schema": "gena.presentation.v1",
            "style": style_key,
        },
    )
    yield sse_delta("", gena={"type": "phase", "phase": "research"})
    research = web_search_ddg((clean_prompt or "")[:600], max_results=6)
    page_bits: list[str] = []
    for u in extract_urls(research, limit=2):
        try:
            pg = await fetch_url_text(u, max_chars=3200)
            page_bits.append(f"--- {u} ---\n{pg[:2800]}")
        except Exception:
            continue
    page_extra = "\n\n".join(page_bits)

    user_bundle = (
        f"Запрос пользователя:\n{clean_prompt[:8000]}\n\n"
        f"Сниппеты веб-поиска (используй для фактов и ссылок sources):\n{research[:7000]}"
    )
    if page_extra:
        user_bundle += f"\n\nФрагменты страниц для анализа:\n{page_extra[:6000]}"

    yield sse_delta("", gena={"type": "phase", "phase": "research_done"})
    yield sse_delta("", gena={"type": "phase", "phase": "llm"})
    model = _pick_model(settings.gena_code_model, available_ids, settings.default_llm)
    system_prompt = (
        "Ты — автор презентаций (как умный ассистент с веб-контекстом): факты, структура, заметки докладчика, иллюстрации.\n"
        + style_hint
        + "\n\n"
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
        "Опционально в объекте слайда (если уместно): "
        '"font_scale": число 0.85–1.2 (крупность текста относительно стиля); '
        '"title_font"|"body_font"|"notes_font": одно из arial, calibri, georgia, times, helvetica, verdana, tahoma. '
        f"Правила: не больше {slide_cap} слайдов (ровно столько, сколько нужно теме, но не выше этого числа); "
        "разные гармоничные accent; visual_style задаёт шрифты и плотность верстки; "
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
                "max_tokens": 14000 if slide_cap > 14 else 8000,
            },
        )
        raw = (data.get("choices") or [{}])[0].get("message", {}).get("content") or ""
        deck_title, slides_data = parse_presentation_json(raw)
        slides_data = [s for s in slides_data if isinstance(s, dict)][:slide_cap]
        if len(slides_data) < 1:
            raise ValueError("no slides in JSON")

        plan_lines: list[str] = []
        if deck_title:
            plan_lines.append(f"**{deck_title}**")
        for i, s in enumerate(slides_data, 1):
            plan_lines.append(f"{i}. {s.get('title', 'Слайд')}")
        summary = _slides_gena_summary(slides_data)
        yield sse_delta(
            "\n".join(plan_lines) + "\n\n",
            gena={
                "type": "deck_structure",
                "deck_title": (deck_title or "")[:500],
                "slides": summary,
                "slide_count": len(slides_data),
            },
        )

        yield sse_delta(
            "",
            gena={
                "type": "phase",
                "phase": "images",
                "total": len(slides_data),
                "done": 0,
            },
        )
        image_paths: list[Optional[Path]] = [None] * len(slides_data)
        done = 0
        async for idx, img_path in resolve_slide_images_progress(
            client, slides_data, available_ids
        ):
            image_paths[idx] = img_path
            done += 1
            preview = _path_to_static_url(request, img_path)
            yield sse_delta(
                "",
                gena={
                    "type": "slide_image",
                    "slide_index": idx,
                    "status": "ready" if preview else "empty",
                    "preview_url": preview,
                    "progress": {"done": done, "total": len(slides_data)},
                },
            )

        static_dir = settings.data_dir / "static" / "presentations"
        static_dir.mkdir(parents=True, exist_ok=True)
        stem = f"presentation_{uuid.uuid4().hex[:10]}"
        fname = f"{stem}.pptx"
        fpath = static_dir / fname

        yield sse_delta("", gena={"type": "phase", "phase": "build"})
        build_colorful_pptx(slides_data, image_paths, fpath, deck_title=deck_title)
        write_presentation_sidecar(
            static_dir / f"{stem}.json",
            deck_title,
            slides_data,
            research + ("\n" + page_extra if page_extra else ""),
            stem=stem,
        )
        url = public_static_url(request, f"static/presentations/{fname}")
        base = str(request.base_url).rstrip("/")
        preview_page = f"{base}/preview/pptx?path={quote(f'static/presentations/{fname}', safe='')}"
        editor = f"{base}/presentation/editor/?stem={stem}"
        yield sse_delta(
            f"✅ [Скачать PPTX]({url}) · [Редактор]({editor})\n\n"
            + presentation_preview_markdown(request, fname),
            gena={
                "type": "presentation_complete",
                "stem": stem,
                "download_url": url,
                "editor_url": editor,
                "preview_page_url": preview_page,
                "pptx_rel": f"static/presentations/{fname}",
                "slide_count": len(slides_data),
            },
        )
        yield sse_delta("", gena={"type": "phase", "phase": "done"})
    except Exception as e:
        logger.exception("presentation")
        yield sse_delta(
            f"**Ошибка презентации.** {friendly_stream_error(e)}\n\n",
            gena={"type": "error", "message": friendly_stream_error(e)},
        )
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
