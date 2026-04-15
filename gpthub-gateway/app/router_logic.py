from __future__ import annotations

import json
import re
from typing import Any, Optional

from app.config import settings

_ROUTER_SIMPLE_TURN_MAX = 360

_CODE_VERBS = (
    r"(?:код\b|функц|sql\b|python\b|скрипт\b|класс\b|метод\b|api\b|текст\b|ответ\b|резюме\b|отчёт\b|"
    r"письмо\b|стих\b|эссе\b|json\b|html\b|regex\b|таблиц\w*|список\b|документ\b)"
)
IMAGE_GEN_RE = re.compile(
    r"("
    r"нарисуй\b|"
    r"нарисуй\s+мне\b|"
    r"отрисуй\b|"
    r"изобрази\b|"
    r"сделай\s+(?:мне\s+)?(?:картинку|картинк\w+|фото|фотографию|фотку|фоточку|изображение|рисунок|арт\b|постер|баннер|"
    r"коллаж|обложку|аватарк\w*|иконку|визуал|иллюстрац\w*|рендер|мем\b)|"
    r"создай\s+(?:мне\s+)?(?:картинк\w*|изображен\w*|фото|фотографию|рисунок|арт\b|постер|логотип|баннер|иконк\w*|"
    r"коллаж|обложку|аватарк\w*|визуал|иллюстрац\w*)|"
    r"(?:сотвори|визуализируй)\s+(?!" + _CODE_VERBS + r")[\wа-яё\s\-«»]{2,80}|"
    r"покажи\s+(?:мне\s+)?(?:картинку|фото|изображение|рисунок|визуал|рендер)|"
    r"хочу\s+(?:картинку|фото|изображение|рисунок|визуал|иллюстрац\w*)|"
    r"(?:дай|вышли|скинь|кинь|покажи)\s+(?:мне\s+)?(?:картинк|фото|рендер|визуал|иллюстрац|обложк|аватар)\w*|"
    r"(?:нужна|нужен|нужны)\s+(?:мне\s+)?(?:картинк|иллюстрац|визуал|обложк|рендер|коллаж|аватар|иконк)\w*|"
    r"(?:сгенери|сгенерь|сгенерируй)\s+(?!" + _CODE_VERBS + r")"
    r"(?:изображение|картинк\w*|фото\w*|логотип|иконк\w*|иллюстрац\w*|арт\b|постер|[\wа-яё\-]{2,48})|"
    r"(?:сделай|создай|нарисуй|придумай|генерируй)\s+(?:мне\s+)?фото\w*|"
    r"\b(?:text-to-image|t2i|img2img|dall-?e|midjourney|миджорни|stable\s*diffusion|sdxl|flux)\b|"
    r"text-to-image|generate\s+an?\s+image|create\s+an?\s+(?:image|picture|illustration)|"
    r"make\s+(?:me\s+)?(?:an?\s+)?(?:image|picture|photo|illustration|visual)\b|"
    r"render\s+(?:an?\s+)?(?:image|picture|scene)\b|"
    r"draw\s+(?:me\s+)?|image\s+generation|i\s+need\s+(?:an?\s+)?(?:image|picture|photo)\b|"
    r"give\s+me\s+(?:an?\s+)?(?:image|picture|photo)\b|"
    r"paint\s+(?:me\s+)?(?:a|an)\s+(?:picture|image|portrait|landscape|scene)\b|"
    r"придумай\s+(?:мне\s+)?(?:картинк|логотип|обложк|постер|баннер|мем|иконк)\w*|"
    r"смоделируй\s+(?:сцену|картинк\w*|изображен\w*)"
    r")",
    re.I,
)

_DOC_WORD_AFTER_ADD = (
    r"пункт|ссылку|ссылк|текст|заголовок|абзац|строку|файл|запись|комментарий|"
    r"примечание|сноску|оглавление|нумерацию|таблицу|формулу|тег|метку|раздел|"
    r"столбец|ячейку|страницу|слайд|подпись|цитату|список"
)
_DOC_WORD_AFTER_ADD_EN = (
    r"section|link|paragraph|footnote|comment|row|column|cell|page|slide|"
    r"heading|title|line|file|tag|label|chapter|index|bullet|note"
)
PRESENTATION_RE = re.compile(r"(презентаци|слайд)", re.I)
SEARCH_RE = re.compile(
    r"(найди\s+в\s+интернет|поиск\s+в\s+сети|web\s+search|google\s+this|"
    r"search\s+the\s+web)",
    re.I,
)
URL_RE = re.compile(r"https?://[^\s)]+", re.I)

_DOC_WORD_AFTER_ADD = (
    r"пункт|ссылку|ссылк|текст|заголовок|абзац|строку|файл|запись|комментарий|"
    r"примечание|сноску|оглавление|нумерацию|таблицу|формулу|тег|метку|раздел|"
    r"столбец|ячейку|страницу|слайд|подпись|цитату|список"
)
_DOC_WORD_AFTER_ADD_EN = (
    r"section|link|paragraph|footnote|comment|row|column|cell|page|slide|"
    r"heading|title|line|file|tag|label|chapter|index|bullet|note"
)

_DEEP_RESEARCH_HINT = re.compile(
    r"(deep\s+research|глубок(ое|ий)\s+исследован|глубокий\s+поиск|"
    r"многошагов(ый|ого)\s+поиск|iterative\s+search|исследуй\s+тему|"
    r"проанализируй\s+вс[её]\s+в\s+интернет|сделай\s+ресерч|сделай\s+рисерч)",
    re.I,
)

_GENA_CODE_KEYWORDS = re.compile(
    r"(напиш(и\b|ь\b)|реализу(й\b|ет\b|ация)|покаж(и\b|ет\b)|сдела(й\b|ть\b)|исправ(ь\b|и\b|ляй)|почин(и\b|ь\b)|отлад(ь\b|и\b)|задеплой|"
    r"код|функц|алгоритм|скрипт|програм|python|py\b|js\b|javascript|typescript|ts\b|sql|ошибк|баг|bug\b|debug\b|"
    r"class\b|def \b|import \b|html|css|json|питон|java\b|c\+\+|c#|golang|go\b|rust\b|kotlin|swift\b|"
    r"dockerfile|docker\b|kubernetes|k8s|yaml\b|bash\b|shell\b|curl\b|api\b|fastapi|django|flask|"
    r"объясни\s+(код|функцию|скрипт|ошибку)|разбери\s+(код|файл)|что\s+делает\s+(код|функция))",
    re.I,
)
_GENA_LONG_DOC_KEYWORDS = re.compile(
    r"(документ|файл|текст|перевод|реферат|статья|резюме|изложи|summarize|translate|сократи|выдели главное|"
    r"проанализируй|проанализировать|объясни\s+(документ|статью|текст)|опиши|расскажи\s+о|расскажи\s+про|"
    r"сравни|сделай\s+обзор|дай\s+обзор|напиши\s+обзор|напиши\s+резюме|сделай\s+саммари)",
    re.I,
)


def gena_chat_target() -> str:
    g = (settings.gena_chat_model or "").strip()
    return g if g else settings.default_llm


def simple_turn_chat_target() -> str:
    s = (settings.simple_chat_model or "").strip()
    return s if s else gena_chat_target()


def strip_gena_assistant_markers(messages: list[dict[str, Any]]) -> None:
    pat = re.compile(
        r"^\*\((?:Авто-выбор модели|Рисую изображение|Deep Research|Презентация)[^*]*\)\*\s*\n*",
        re.MULTILINE,
    )
    for m in messages or []:
        if m.get("role") != "assistant":
            continue
        c = m.get("content")
        if isinstance(c, str):
            m["content"] = pat.sub("", c, count=1)


def _coerce_available_model(preferred: str, available_ids: set[str]) -> str:
    if preferred in available_ids:
        return preferred
    for alt in (
        gena_chat_target(),
        settings.default_llm,
        settings.gena_code_model,
        settings.gena_long_doc_model,
        settings.vision_model,
    ):
        if alt and alt in available_ids:
            return alt
    skip = settings.router_skip_model_ids() | {settings.auto_model_id}
    for x in sorted(available_ids):
        if x not in skip:
            return x
    for x in sorted(available_ids):
        if x != settings.auto_model_id:
            return x
    return settings.default_llm


def pick_route_gena(
    messages: list[dict[str, Any]],
    available_ids: set[str],
) -> tuple[str, str]:
    if message_has_image(messages):
        vm = settings.vision_model
        if vm in available_ids:
            return vm, "gena:vision"
        for candidate in ("gpt-4o", "gpt-4o-mini", "cotype-pro-vl-32b"):
            if candidate in available_ids:
                return candidate, "gena:vision"

    if message_has_audio(messages):
        return _coerce_available_model(gena_chat_target(), available_ids), "gena:audio_then_llm"

    lu = last_user_message(messages)
    text = _content_to_text(lu.get("content") if lu else None)
    if IMAGE_GEN_RE.search(text):
        return _coerce_available_model(gena_chat_target(), available_ids), "gena:image_gen_intent"

    user_texts = " ".join(
        _content_to_text(m.get("content")) for m in messages or [] if m.get("role") == "user"
    )
    total_words = len(user_texts.split())

    if total_words > settings.gena_long_doc_word_threshold or _GENA_LONG_DOC_KEYWORDS.search(
        user_texts
    ):
        mid = _coerce_available_model(settings.gena_long_doc_model, available_ids)
        return mid, "gena:long_doc"

    if _GENA_CODE_KEYWORDS.search(user_texts):
        mid = _coerce_available_model(settings.gena_code_model, available_ids)
        return mid, "gena:code"

    fp = try_fast_path_default_llm_for_simple_turn(messages, available_ids)
    if fp is not None:
        return fp

    mid = _coerce_available_model(gena_chat_target(), available_ids)
    return mid, "gena:chat"


def normalize_requested_model(model_id: str) -> str:
    s = (model_id or "").strip()
    if not s:
        return ""
    if "/" in s:
        s = s.rsplit("/", 1)[-1]
    return s.strip()


def _content_to_text(content: Any) -> str:
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for block in content:
            if isinstance(block, dict):
                t = block.get("type")
                if t == "text":
                    parts.append(block.get("text") or "")
                elif t == "image_url":
                    parts.append("<image>")
                elif t == "input_audio":
                    parts.append("<audio>")
            elif isinstance(block, str):
                parts.append(block)
        return "\n".join(parts)
    return str(content)


def last_user_message(messages: list[dict[str, Any]]) -> Optional[dict[str, Any]]:
    for m in reversed(messages or []):
        if m.get("role") == "user":
            return m
    return None


def message_has_image(messages: list[dict[str, Any]]) -> bool:
    for m in messages or []:
        c = m.get("content")
        if isinstance(c, list):
            for block in c:
                if isinstance(block, dict) and block.get("type") == "image_url":
                    return True
        if isinstance(c, str) and "data:image" in c:
            return True
    return False


def message_has_audio(messages: list[dict[str, Any]]) -> bool:
    for m in messages or []:
        c = m.get("content")
        if isinstance(c, list):
            for block in c:
                if isinstance(block, dict) and block.get("type") == "input_audio":
                    return True
    return False


def apply_manual_route(req: str, available_ids: set[str]) -> tuple[str, str]:
    mid = req if req in available_ids else settings.default_llm
    return mid, "manual"


def try_fast_path_default_llm_for_simple_turn(
    messages: list[dict[str, Any]],
    available_ids: set[str],
) -> tuple[str, str] | None:
    if message_has_image(messages) or message_has_audio(messages):
        return None
    lu = last_user_message(messages)
    text = _content_to_text(lu.get("content") if lu else None).strip()
    if not text or len(text) > _ROUTER_SIMPLE_TURN_MAX:
        return None
    if IMAGE_GEN_RE.search(text) or SEARCH_RE.search(text):
        return None
    if URL_RE.search(text) or _DEEP_RESEARCH_HINT.search(text):
        return None
    target = simple_turn_chat_target()
    if target in available_ids:
        return (target, "auto:simple_chat")
    coerced = _coerce_available_model(target, available_ids)
    return (coerced, "auto:simple_chat")


def pick_route_deterministic(
    messages: list[dict[str, Any]],
    available_ids: set[str],
) -> tuple[str, str]:
    lu = last_user_message(messages)
    text = _content_to_text(lu.get("content") if lu else None)

    if message_has_image(messages):
        vm = settings.vision_model
        if vm in available_ids:
            return vm, "auto:vision"
        for candidate in ("gpt-4o", "gpt-4o-mini", "cotype-pro-vl-32b"):
            if candidate in available_ids:
                return candidate, "auto:vision"

    if message_has_audio(messages):
        dm = settings.default_llm
        if dm in available_ids:
            return dm, "auto:audio_then_llm"
        return next(iter(available_ids - {settings.auto_model_id}), settings.default_llm), "auto:audio"

    if IMAGE_GEN_RE.search(text):
        dm = settings.default_llm
        if dm in available_ids:
            return dm, "auto:image_gen_intent"
        return next(iter(available_ids - {settings.auto_model_id}), settings.default_llm), "auto:image_gen_intent"

    if SEARCH_RE.search(text):
        dm = settings.default_llm
        if dm in available_ids:
            return dm, "auto:web_search_context"
        return next(iter(available_ids - {settings.auto_model_id}), settings.default_llm), "auto:web_search"

    if URL_RE.search(text):
        dm = settings.default_llm
        if dm in available_ids:
            return dm, "auto:url_fetch_context"
        return next(iter(available_ids - {settings.auto_model_id}), settings.default_llm), "auto:url"

    dm = settings.default_llm
    if dm in available_ids:
        return dm, "auto:default_llm"
    for x in sorted(available_ids):
        if x != settings.auto_model_id:
            return x, "auto:fallback"
    return settings.default_llm, "auto:fallback"


def pick_route(
    messages: list[dict[str, Any]],
    requested_model: str,
    available_ids: set[str],
) -> tuple[str, str]:
    req = normalize_requested_model(requested_model)
    if req and req != settings.auto_model_id:
        return apply_manual_route(req, available_ids)
    return pick_route_deterministic(messages, available_ids)


def inject_router_debug(
    messages: list[dict[str, Any]], note: str, model: str
) -> list[dict[str, Any]]:
    prefix = f"[GPTHub route: {note} → {model}]\n"
    out = [m.copy() for m in messages]
    for i in range(len(out) - 1, -1, -1):
        if out[i].get("role") == "system":
            c = out[i].get("content")
            if isinstance(c, str):
                out[i]["content"] = prefix + c
            else:
                out[i]["content"] = prefix + json.dumps(c)
            return out
    out.insert(0, {"role": "system", "content": prefix.strip()})
    return out
