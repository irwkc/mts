"""
Автовыбор модели под задачу. Ручной режим: пользователь выбирает конкретный id из /v1/models
(любой кроме gpthub-auto). В авто режиме model == gpthub-auto.
"""

import json
import re
from typing import Any, Optional

from app.config import settings

IMAGE_GEN_RE = re.compile(
    r"(нарисуй|сгенерируй\s+изображение|создай\s+картинк|text-to-image|"
    r"generate\s+an?\s+image|draw\s+a|image\s+generation|flux|sdxl)",
    re.I,
)
SEARCH_RE = re.compile(
    r"(найди\s+в\s+интернет|поиск\s+в\s+сети|web\s+search|google\s+this|"
    r"search\s+the\s+web)",
    re.I,
)
URL_RE = re.compile(r"https?://[^\s)]+", re.I)


def normalize_requested_model(model_id: str) -> str:
    """
    Open WebUI шлёт model как «gpthub-auto» или с префиксом провайдера, напр. openai/gpthub-auto.
    Без нормализации роутер не узнаёт авто-режим и MWS может получить несуществующий id.
    """
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


def pick_route_deterministic(
    messages: list[dict[str, Any]],
    available_ids: set[str],
) -> tuple[str, str]:
    """Автовыбор без LLM (правила)."""
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
        # Аудио: транскрипция обрабатывается отдельным эндпоинтом; для chat оставляем LLM
        # после того как клиент вставит текст — здесь выбираем LLM по умолчанию.
        dm = settings.default_llm
        if dm in available_ids:
            return dm, "auto:audio_then_llm"
        return next(iter(available_ids - {settings.auto_model_id}), settings.default_llm), "auto:audio"

    if IMAGE_GEN_RE.search(text):
        # Сама генерация — через /v1/images/generations; в chat идёт обычная LLM как запасной путь
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
    # любая первая подходящая chat-модель
    for x in sorted(available_ids):
        if x != settings.auto_model_id:
            return x, "auto:fallback"
    return settings.default_llm, "auto:fallback"


def pick_route(
    messages: list[dict[str, Any]],
    requested_model: str,
    available_ids: set[str],
) -> tuple[str, str]:
    """
    Ручной режим или детерминированный авто-режим (для тестов / fallback).
    """
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
