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

import httpx
from fastapi import Request

from app.config import settings
from app.image_utils import image_api_response_to_sse_href
from app.presentation_pptx import (
    build_colorful_pptx,
    normalize_slide_rows_for_images,
    parse_presentation_json,
    resolve_slide_images_progress,
    write_presentation_sidecar,
)
from app.mws_client import MWSClient
from app.pptx_pdf import ensure_pptx_pdf
from app.router_logic import (
    IMAGE_GEN_RE,
    PRESENTATION_RE,
    _DOC_WORD_AFTER_ADD,
    _DOC_WORD_AFTER_ADD_EN,
    _content_to_text,
    gena_chat_target,
)
from app.web_tools import (
    deep_research_ddg,
    extract_urls,
    fetch_url_text,
    should_run_deep_research,
    web_search_ddg,
)

logger = logging.getLogger("gpthub.gena")

_MD_IMG_URL = re.compile(r"!\[[^\]]*\]\((https?://[^)\s]+)\)")

# Правки сцены после картинки ассистента. Без слишком коротких токенов («картин», «исправ») —
# иначе ловится обычный текст в чате.
_IMAGE_EDIT_FOLLOWUP = re.compile(
    r"(?:"
    r"измени|изменить|перерисуй|перекрась|отредактируй|подправь|доработай|"
    r"убери\b|"
    r"добавь\s+(?:на\s+)?(?:картин|фото|фон|небо|объект|задний\s+план|передний\s+план)|"
    r"добавь\s+(?:ещё|еще\s+)?(?!(?:" + _DOC_WORD_AFTER_ADD + r")\b)[\wа-яё\-]{2,}|"
    r"ещ[ёе]\s*(?:вариант|картин|фото|раз|верси|один|одну|одного)|"
    r"ещ[ёе]\s+один\s+вариант|ещ[ёе]\s+одну\s+картинку|"
    r"другой\s+вариант|другая\s+верси|другую\s+картин|иначе\s+нарисуй|"
    r"замени\s+(?:фон|небо|картинку|объект)|поменяй\s+(?:фон|стиль|цвет|небо)|"
    r"сделай\s+(?:картин|фотк|фото|изображен|рисунок|по)?ярче|"
    r"сделай\s+(?:по)?темнее|сделай\s+контрастн|сделай\s+светлее|"
    r"сделай\s+(?:ещё|еще|похож|аналог|вариант|фон|небо|облак)|"
    r"без\s+(?:текста|надписей|логотипа|водяного|рамки)|"
    r"в\s+стиле\s+[\wа-яё\s\-«»]{2,48}|"
    r"как\s+(?:в|у)\s+[\wа-яё\s\-]{2,32}|"
    r"похож(?:е|ая)?\s+на\s+[\wа-яё\s\-]{2,40}|"
    r"(?:сделай|нарисуй|ещё|еще)\s+в\s+том\s+же\s+стиле|"
    r"перегенерируй|пересоздай\s+(?:картин|фото|изображен|вариант)|"
    r"отзеркаль|отрази\s+по\s+горизонтали|поверни\s+на\s+\d+|"
    r"обрежь|кадрируй|приблизь|отдали|зум\b|"
    r"regenerate\s+(?:the\s+)?(?:image|picture|photo)\b|"
    r"in\s+the\s+same\s+style\b|keep\s+the\s+same\s+style\b|"
    r"add\s+(?:a|an|the)\s+(?!(?:" + _DOC_WORD_AFTER_ADD_EN + r")\b)[\w\-]{2,}|"
    r"(?:re)?move\s+the\s+(?:background|foreground|object|text|watermark)|"
    r"change\s+the\s+(?:background|style|colors?)|edit\s+the\s+image|replace\s+the\s+background|"
    r"(?:make\s+it|image\s+)(?:brighter|darker|sharper|softer)\b|"
    r"(?:more|less)\s+(?:contrast|saturation|blur|brightness)\b|"
    r"upscale|inpaint|outpaint|crop\s+to|rotate\s+(?:by|to)|mirror\s+horizontally"
    r")",
    re.I,
)

# Сообщение явно просит факты/текст — не считать это запросом на новую картинку после предыдущей.
_TEXT_NOT_IMAGE_FOLLOWUP = re.compile(
    r"(?is)^\s*(?:"
    r"сколько\b|когда\b|почему\b|зачем\b|откуда\b|куда\b|"
    r"какой\b|какая\b|какое\b|какие\b|какого\b|какому\b|каких\b|"
    r"кто\s+так(ой|ая|ие)\b|что\s+такое\b|чем\s+отличается|чем\s+отличаются|в\s+чём\s+разница|"
    r"объясни\b|опиши\b|расскажи\b|сравни\b|переведи\b|"
    r"how\s+much\b|how\s+many\b|what\s+is\b|what\s+are\b|why\b|when\b|where\b|who\s+is\b|"
    r"define\b|explain\b"
    r")\b",
)


def _collect_assistant_image_urls(messages: list[dict[str, Any]], max_n: int = 4) -> list[str]:
    """URL из markdown ![...](url) в последних ответах ассистента — для правок картинки в диалоге."""
    out: list[str] = []
    seen: set[str] = set()
    for m in reversed(messages or []):
        if (m.get("role") or "") != "assistant":
            continue
        raw = _content_to_text(m.get("content"))
        for u in _MD_IMG_URL.findall(raw):
            if u not in seen:
                seen.add(u)
                out.append(u)
            if len(out) >= max_n:
                return out
    return out


def _last_assistant_has_markdown_image(messages: list[dict[str, Any]]) -> bool:
    """Есть ли в последнем ответе ассистента встроенная картинка (https или data:image)."""
    for m in reversed(messages or []):
        if (m.get("role") or "") != "assistant":
            continue
        raw = _content_to_text(m.get("content"))
        return bool(re.search(r"!\[[^\]]*\]\([^)]+\)", raw))
    return False


def _image_followup_after_assistant_picture(last_text: str, messages: list[dict[str, Any]]) -> bool:
    """Запрос без явного «нарисуй», но после сгенерированной картинки — доработка сцены."""
    if not last_text:
        return False
    t = last_text.strip()
    if len(t) > 1200:
        return False
    if re.match(r"^(спасибо|благодарю|thanks|thank you|ok\.?|ок\.?|понятно)\s*$", t, re.I):
        return False
    if _TEXT_NOT_IMAGE_FOLLOWUP.search(t):
        return False
    if not _collect_assistant_image_urls(messages, max_n=1) and not _last_assistant_has_markdown_image(
        messages
    ):
        return False
    if IMAGE_GEN_RE.search(last_text):
        return False
    if _IMAGE_EDIT_FOLLOWUP.search(last_text):
        return True
    # Раньше здесь было len(t)<=400 — из-за этого любой короткий вопрос после картинки
    # (напр. «сколько весит жираф») уходил в генерацию. Оставляем только явные правки выше
    # и прямые команды из IMAGE_GEN_RE в user_wants_image_generation.
    return False


def user_wants_image_generation(
    last_text: str,
    messages: list[dict[str, Any]],
    route_has_image_gen: bool,
) -> bool:
    if not last_text or len(last_text.strip()) < 3:
        return False
    if route_has_image_gen:
        return True
    if IMAGE_GEN_RE.search(last_text):
        return True
    return _image_followup_after_assistant_picture(last_text, messages)


async def prepare_image_generation_prompt(
    client: MWSClient,
    user_text: str,
    messages: list[dict[str, Any]] | None,
    available_ids: set[str],
    requested_model: str = "",
) -> tuple[str, str]:
    """Подобрать модель и финальный англ. промпт (с учётом URL предыдущей картинки при правках)."""
    image_refs = _collect_assistant_image_urls(messages or [], max_n=4)
    model_id = requested_model if (requested_model and requested_model != settings.auto_model_id) else settings.image_gen_model
    if model_id not in available_ids:
        for c in ("qwen-image", "qwen-image-lightning", "sd3.5-large-image", "z-image-turbo"):
            if c in available_ids:
                model_id = c
                break
    prompt = user_text
    try:
        if image_refs:
            enhance = await client.post_json(
                "/chat/completions",
                {
                    "model": _pick_model(gena_chat_target(), available_ids, settings.default_llm),
                    "messages": [
                        {
                            "role": "system",
                            "content": (
                                "You write ONE English prompt for a text-to-image diffusion model. "
                                "The user is iterating on a previous image; the URLs describe what was "
                                "already generated (style and subject). "
                                "Describe the full new scene after the user's change — objects, colors, "
                                "lighting, composition, art style. "
                                "Do not output URLs or markdown. Output ONLY the prompt."
                            ),
                        },
                        {
                            "role": "user",
                            "content": (
                                "Reference image URL(s) from the previous assistant message:\n"
                                + "\n".join(f"- {u}" for u in image_refs)
                                + f"\n\nUser instruction (any language):\n{user_text[:3000]}"
                            ),
                        },
                    ],
                    "max_tokens": 700,
                    "temperature": 0.35,
                },
            )
        elif _last_assistant_has_markdown_image(messages or []):
            enhance = await client.post_json(
                "/chat/completions",
                {
                    "model": _pick_model(gena_chat_target(), available_ids, settings.default_llm),
                    "messages": [
                        {
                            "role": "system",
                            "content": (
                                "You write ONE English prompt for a text-to-image diffusion model. "
                                "The previous assistant message in this chat already contained a generated "
                                "image (markdown image; may be a hosted URL or inline data). "
                                "The user now asks for a revision. Describe the complete new image — "
                                "scene, style, lighting, objects — matching their instruction. "
                                "Do not mention chat or URLs. Output ONLY the prompt."
                            ),
                        },
                        {"role": "user", "content": user_text[:3000]},
                    ],
                    "max_tokens": 700,
                    "temperature": 0.35,
                },
            )
        else:
            enhance = await client.post_json(
                "/chat/completions",
                {
                    "model": _pick_model(gena_chat_target(), available_ids, settings.default_llm),
                    "messages": [
                        {
                            "role": "system",
                            "content": "Output ONLY a concise English image generation prompt, no other text.",
                        },
                        {"role": "user", "content": user_text[:2000]},
                    ],
                    "max_tokens": 500,
                    "temperature": 0.35,
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
        logger.exception("image prompt enhance")
    return model_id, prompt[:4000]


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


def public_app_url(request: Request, path: str) -> str:
    """Публичный URL к маршруту шлюза (включая query), не только /static/.

    Нужен для /presentation/editor/, /preview/pptx — иначе в чат попадает
    http://gpthub-gateway:8080/... (Docker DNS), недоступный из браузера.
    """
    raw = (path or "").strip()
    if raw.startswith(("http://", "https://")):
        return raw
    p = raw.lstrip("/")
    base = (settings.public_base_url or "").strip().rstrip("/")
    if base:
        return f"{base}/{p}"

    fwd = (request.headers.get("x-forwarded-host") or "").strip()
    if fwd:
        host = fwd.split(",")[0].strip()
        proto = (request.headers.get("x-forwarded-proto") or "https").strip().split(",")[0].strip()
        if proto not in ("http", "https"):
            proto = "https"
        return f"{proto}://{host}/{p}"

    if (request.url.hostname or "").lower() == "gpthub-gateway":
        return f"/{p}"

    return str(request.base_url).rstrip("/") + "/" + p


# Стиль: слова в промпте (см. infer_presentation_style) или опционально префикс [gena_style:id].
_PRESENTATION_STYLE_HEAD = re.compile(r"^\s*\[gena_style:([a-z0-9_-]+)\]\s*", re.I)
_PRESENTATION_STYLE_IDS = frozenset(
    {"minimal", "corporate", "modern", "bold", "playful", "elegant"}
)

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
    "elegant": (
        "Визуальный стиль: изысканный — утончённая типографика, приглушённые акценты, "
        "визуально «премиальный» вид без визуального шума."
    ),
}


def has_explicit_presentation_style(user_text: str) -> bool:
    """Пользователь уже выбрал стиль префиксом [gena_style:id]."""
    raw = (user_text or "").strip()
    m = _PRESENTATION_STYLE_HEAD.match(raw)
    if not m:
        return False
    return m.group(1).lower() in _PRESENTATION_STYLE_IDS


# Порядок и подписи для UI (Open WebUI) — 6 кнопок выбора стиля
PRESENTATION_STYLE_UI_ROWS: list[dict[str, str]] = [
    {"id": "minimal", "label": "Минимализм", "hint": "воздух, 1–2 акцента"},
    {"id": "corporate", "label": "Деловой", "hint": "сетка, строгая типографика"},
    {"id": "modern", "label": "Современный", "hint": "крупный текст, плашки"},
    {"id": "bold", "label": "Яркий", "hint": "контраст, динамика"},
    {"id": "playful", "label": "Лёгкий", "hint": "дружелюбно, иллюстративно"},
    {"id": "elegant", "label": "Изысканный", "hint": "премиум, сдержанность"},
]


async def stream_presentation_style_prompt(request: Request) -> AsyncGenerator[str, None]:
    """Только ответ «выберите стиль» + delta.gena для кнопок в Open WebUI; без сборки PPTX."""
    _ = request
    styles = [dict(x) for x in PRESENTATION_STYLE_UI_ROWS]
    yield sse_delta(
        "**Отлично!** Выберите стиль вашей презентации — нажмите кнопку ниже, и я продолжу сборку слайдов.\n\n",
        gena={
            "type": "presentation_style_prompt",
            "schema": "gena.presentation.style_prompt.v1",
            "styles": styles,
        },
    )
    yield "data: [DONE]\n\n"


def infer_presentation_style(prompt: str) -> str:
    """Угадать стиль по словам в запросе (рус/англ). Иначе corporate."""
    t = (prompt or "").lower()
    # Порядок: более специфичные шаблоны раньше при необходимости
    checks: list[tuple[str, tuple[str, ...]]] = [
        ("minimal", (r"минимал", r"лаконич", r"\bminimal\b", r"clean\s+style", r"в\s+стиле\s+минимал")),
        ("corporate", (r"делов", r"корпоратив", r"\bcorporate\b", r"офисн", r"строг", r"business")),
        ("modern", (r"современ", r"\bmodern\b", r"модерн", r"tech", r"флет")),
        ("bold", (r"ярк", r"контраст", r"\bbold\b", r"смел", r"насыщен")),
        ("playful", (r"лёгк", r"легк", r"игрив", r"дружелюб", r"\bplayful\b", r"неформал")),
        ("elegant", (r"изыскан", r"премиум", r"элегант", r"\belegant\b", r"утончён")),
    ]
    for sid, pats in checks:
        for p in pats:
            if re.search(p, t, re.I):
                return sid
    return "corporate"


def resolve_presentation_style(prompt: str) -> tuple[str, str]:
    """(текст без опционального [gena_style:id], выбранный стиль)."""
    raw = (prompt or "").strip()
    m = _PRESENTATION_STYLE_HEAD.match(raw)
    if m:
        sid = m.group(1).lower()
        rest = raw[m.end() :].strip()
        if sid in _PRESENTATION_STYLE_IDS:
            return rest, sid
        return rest, infer_presentation_style(rest)
    return raw, infer_presentation_style(raw)


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
    clean_prompt, style_key = resolve_presentation_style(prompt)
    style_hint = _PRESENTATION_STYLE_HINTS.get(
        style_key, _PRESENTATION_STYLE_HINTS["corporate"]
    )

    slide_cap = _presentation_slide_cap(clean_prompt)
    # Только gena-события в UI (док); без текста «[gena · презентация]» в чате
    yield sse_delta(
        "",
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
        '"image_query":"ОБЯЗАТЕЛЬНО на английском: 3–8 ключевых слов для поиска фото/стока в интернете (не пусто); тема слайда одной строкой",'
        '"image_prompt":"Только для нейро-фолбэка: описание РЕАЛЬНОЙ сцены/фото на английском (животные, пейзаж, объект). '
        'НЕ слова presentation/slide/infographic/layout; БЕЗ текста на картинке; без «слайда» и «постера».",'
        '"sources":[{"title":"кратко","url":"https://..."}],'
        '"visual_style":"corporate|modern|bold|compact"}'
        "]}\n"
        "Опционально в объекте слайда (если уместно): "
        '"font_scale": число 0.85–1.2 (крупность текста относительно стиля); '
        '"title_font"|"body_font"|"notes_font": одно из arial, calibri, georgia, times, helvetica, verdana, tahoma. '
        f"Правила: не больше {slide_cap} слайдов (ровно столько, сколько нужно теме, но не выше этого числа); "
        "разные гармоничные accent; visual_style задаёт шрифты и плотность верстки; "
        "Иллюстрации: система ВСЕГДА сначала ищет картинки в интернете (по image_query), "
        "нейро-генерация — только если веб не дал подходящего файла. "
        "Поэтому на КАЖДОМ слайде заполняй image_query осмысленным английским запросом (фото, предмет, контекст). "
        "image_mode: auto — типичный режим; search — настаивать на реальных фото из сети; "
        "generate — допустить нейро-иллюстрацию как запасной вариант после веба (не отключай веб). "
        "Никогда не проси в image_prompt текст, буквы, подписи или заголовки на картинке — текст только в title/bullets слайда. "
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

        normalize_slide_rows_for_images(slides_data, deck_title or "")

        summary = _slides_gena_summary(slides_data)
        # План слайдов только в доке (deck_structure), не дублировать списком в чате
        yield sse_delta(
            "",
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
            client, slides_data, available_ids, deck_title=deck_title or ""
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

        pdf_path = static_dir / f"{stem}.pdf"
        pdf_ok = await ensure_pptx_pdf(fpath, pdf_path)
        pdf_href = (
            public_static_url(request, f"static/presentations/{stem}.pdf")
            if pdf_ok
            else public_app_url(request, f"presentation/pdf/{stem}")
        )

        # В чат — только две понятные ссылки на скачивание (без предпросмотра, редактора и raw URL).
        yield sse_delta(
            "\n\n"
            f"- [Скачать PDF]({pdf_href})\n"
            f"- [Скачать PPTX]({url})\n\n",
            gena={
                "type": "presentation_complete",
                "stem": stem,
                "download_url": url,
                "pdf_url": pdf_href,
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


async def stream_image_markdown(
    request: Request,
    client: MWSClient,
    prompt: str,
    available_ids: set[str],
    messages: list[dict[str, Any]] | None = None,
    requested_model: str = "",
) -> AsyncGenerator[str, None]:
    """Только картинка в markdown; статус — delta.gena (спиннер + подпись в UI)."""
    yield sse_delta("", gena={"type": "image_generation_start"})
    try:
        model_id, final_prompt = await prepare_image_generation_prompt(
            client, prompt, messages, available_ids, requested_model
        )
        
        payload = {
            "model": model_id,
            "prompt": final_prompt,
            "n": 1,
            "size": "1024x1024",
            "response_format": "b64_json",
        }
        try:
            img_resp = await client.post_json("/images/generations", payload)
        except httpx.HTTPStatusError as e:
            if e.response.status_code in (400, 404) and model_id != settings.image_gen_model:
                logger.warning("requested_model %s failed for images, retrying with default %s", model_id, settings.image_gen_model)
                payload["model"] = settings.image_gen_model
                img_resp = await client.post_json("/images/generations", payload)
            else:
                raise

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
    yield sse_delta("", gena={"type": "image_generation_done"})
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


def should_stream_image_gena(
    last_text: str,
    stream: bool,
    has_image: bool,
    messages: list[dict[str, Any]] | None,
) -> bool:
    if not (stream and last_text and not has_image):
        return False
    return user_wants_image_generation(last_text, messages or [], False)
