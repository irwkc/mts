"""
Автовыбор модели через один вызов chat/completions к MWS (нейро-роутер).
При ошибке парсинга / API — fallback на pick_route_deterministic.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any

from app.config import settings
from app.mws_client import MWSClient
from app.router_logic import (
    _content_to_text,
    last_user_message,
    message_has_audio,
    message_has_image,
    pick_route_deterministic,
)

logger = logging.getLogger("gpthub.router_llm")

def _extract_json_object(text: str) -> dict[str, Any]:
    t = (text or "").strip()
    if "```" in t:
        m = re.search(r"```(?:json)?\s*(\{[\s\S]*?\})\s*```", t)
        if m:
            t = m.group(1)
    start = t.find("{")
    if start < 0:
        raise ValueError("no JSON object in router response")
    decoder = json.JSONDecoder()
    obj, _ = decoder.raw_decode(t[start:])
    if isinstance(obj, dict):
        return obj
    raise ValueError("router JSON is not an object")


async def resolve_auto_route_with_llm(
    messages: list[dict[str, Any]],
    available_ids: set[str],
    client: MWSClient,
) -> tuple[str, str]:
    """
    Один запрос к MWS: модель router_llm_model возвращает JSON { "model_id", "route" }.
    """
    candidates = sorted(x for x in available_ids if x and x != settings.auto_model_id)
    if not candidates:
        return pick_route_deterministic(messages, available_ids)

    router_model = settings.router_llm_model
    if router_model not in available_ids:
        router_model = settings.default_llm
        if router_model not in available_ids:
            router_model = candidates[0]

    lu = last_user_message(messages)
    text = _content_to_text(lu.get("content") if lu else None)[:6000]
    has_img = message_has_image(messages)
    has_aud = message_has_audio(messages)

    ids_list = ", ".join(candidates[:100])
    system = (
        "Ты маршрутизатор моделей MWS GPT. По запросу пользователя выбери ровно один model_id "
        "из списка доступных id (они уже проверены каталогом API).\n"
        f"Доступные model_id: {ids_list}\n"
        "Правила: есть изображение во входе — выбери vision-модель (gpt-4o, cotype-pro-vl-32b и т.п., что есть в списке). "
        "Есть только текст — основную LLM (mts-anya, mws-gpt-alpha и т.д.). "
        "Есть аудио — после транскрипции пойдёт текст; можно выбрать основную LLM.\n"
        "Ответь ТОЛЬКО JSON без пояснений: "
        '{"model_id":"<id из списка>","route":"краткая метка на англ."}'
    )
    user_msg = (
        f"has_image={has_img} has_audio={has_aud}\n"
        f"user_text:\n{text}"
    )

    body: dict[str, Any] = {
        "model": router_model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user_msg},
        ],
        "temperature": 0.05,
        "max_tokens": 256,
    }

    try:
        out = await client.post_json("/chat/completions", body)
        raw = (out.get("choices") or [{}])[0].get("message", {}).get("content") or ""
        parsed = _extract_json_object(raw)
        mid = str(parsed.get("model_id") or "").strip()
        note = str(parsed.get("route") or "llm").strip()
        if not mid or mid == settings.auto_model_id:
            raise ValueError("invalid model_id from LLM")
        if mid not in available_ids:
            logger.warning("LLM router picked unknown model %r, fallback rules", mid)
            return pick_route_deterministic(messages, available_ids)
        return mid, f"llm:{note}"
    except Exception as e:
        logger.warning("LLM router error: %s", e)
        return pick_route_deterministic(messages, available_ids)
