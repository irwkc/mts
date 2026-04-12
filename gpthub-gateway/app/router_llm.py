"""
Автовыбор модели через один вызов chat/completions (нейро-роутер):
MWS или локальный OpenAI-compatible (Ollama и т.д.), см. GPTHUB_ROUTER_LOCAL_BASE_URL.
При ошибке парсинга / API — по умолчанию fallback на pick_route_deterministic;
при GPTHUB_ROUTER_RULES_FALLBACK=false — исключение RouterLLMFailed (503).
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any

import httpx

from app.config import settings
from app.mws_client import MWSClient
from app.router_logic import (
    _content_to_text,
    last_user_message,
    message_has_audio,
    message_has_image,
    pick_route_deterministic,
    try_fast_path_default_llm_for_simple_turn,
)

logger = logging.getLogger("gpthub.router_llm")


class RouterLLMFailed(Exception):
    """Нейро-роутер не смог выбрать модель и откат на правила запрещён."""

    def __init__(self, message: str) -> None:
        self.message = message
        super().__init__(message)


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


async def _post_router_chat_completions(
    body: dict[str, Any], client: MWSClient
) -> dict[str, Any]:
    """Один вызов chat/completions: локальный OpenAI API или MWS."""
    base = (settings.router_local_base_url or "").strip()
    if base:
        url = base.rstrip("/") + "/chat/completions"
        headers: dict[str, str] = {"Content-Type": "application/json"}
        key = (settings.router_local_api_key or "").strip()
        if key:
            headers["Authorization"] = f"Bearer {key}"
        async with httpx.AsyncClient(timeout=90.0) as http:
            r = await http.post(url, headers=headers, content=json.dumps(body))
            if r.status_code in (400, 422) and body.get("response_format"):
                logger.warning(
                    "local router: retry without response_format (%s)",
                    r.text[:200],
                )
                b2 = {k: v for k, v in body.items() if k != "response_format"}
                r = await http.post(url, headers=headers, content=json.dumps(b2))
            r.raise_for_status()
            return r.json()
    return await client.chat_completions_router(body)


def _match_model_id(raw: str, available_ids: set[str]) -> str | None:
    """Сопоставить ответ LLM с id из каталога (регистр, кавычки, частичное совпадение)."""
    s = (raw or "").strip().strip("\"'")
    if not s:
        return None
    if s in available_ids:
        return s
    low = s.lower()
    for aid in available_ids:
        if aid.lower() == low:
            return aid
    # Однозначное вхождение подстроки (модель вернула укороченный id)
    subs = [a for a in available_ids if low in a.lower() or a.lower() in low]
    if len(subs) == 1:
        return subs[0]
    return None


async def resolve_auto_route_with_llm(
    messages: list[dict[str, Any]],
    available_ids: set[str],
    client: MWSClient,
) -> tuple[str, str]:
    """
    Один запрос к роутеру: JSON { "model_id", "route" }; backend — MWS или локальный LLM.
    """
    candidates = sorted(x for x in available_ids if x and x != settings.auto_model_id)
    if not candidates:
        return pick_route_deterministic(messages, available_ids)

    fast = try_fast_path_default_llm_for_simple_turn(messages, available_ids)
    if fast:
        logger.info("LLM router skipped (simple turn) -> %s %s", fast[0], fast[1])
        return fast

    use_local_router = bool((settings.router_local_base_url or "").strip())
    if use_local_router:
        router_model = (settings.router_local_model or "qwen2.5:0.5b").strip()
        logger.info("LLM router backend=local model=%s", router_model)
    else:
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
    primary = settings.default_llm if settings.default_llm in candidates else candidates[0]
    system = (
        "Ты маршрутизатор моделей MWS GPT. По последнему запросу пользователя выбери ровно один model_id "
        "СТРОГО из списка доступных id (копируй строку символ в символ).\n"
        f"Доступные model_id: {ids_list}\n"
        f"Обычный диалог, приветствия, вопросы, код без картинок — выбирай основную текстовую модель, "
        f"по возможности: {primary}.\n"
        "Есть изображение во входе — vision-модель из списка (gpt-4o, cotype-pro-vl-32b и т.п.). "
        "Явная просьба нарисовать/сгенерировать картинку — всё равно выбери текстовую модель для формулировки; "
        "генерация изображения выполняется отдельным шагом.\n"
        "Есть аудио — основная LLM (после транскрипции будет текст).\n"
        "Никогда не придумывай id вне списка. Ответь ТОЛЬКО JSON: "
        '{"model_id":"<id из списка>","route":"краткая_метка_латиницей"}'
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
        "response_format": {"type": "json_object"},
    }

    def _fallback_or_raise(exc: BaseException, msg: str) -> tuple[str, str]:
        if settings.router_rules_fallback:
            logger.warning("LLM router: %s — fallback to rules (%s)", msg, exc)
            return pick_route_deterministic(messages, available_ids)
        raise RouterLLMFailed(msg) from exc

    try:
        out = await _post_router_chat_completions(body, client)
        raw = (out.get("choices") or [{}])[0].get("message", {}).get("content") or ""
        parsed = _extract_json_object(raw)
        mid_raw = str(parsed.get("model_id") or "").strip()
        note = str(parsed.get("route") or "llm").strip()
        if not mid_raw or mid_raw == settings.auto_model_id:
            return _fallback_or_raise(
                ValueError("invalid model_id"),
                "нейро-роутер вернул пустой или запрещённый model_id",
            )
        mid = _match_model_id(mid_raw, available_ids)
        if not mid:
            return _fallback_or_raise(
                ValueError(mid_raw),
                f"нейро-роутер вернул неизвестный model_id: {mid_raw!r}",
            )
        logger.info("LLM router ok: model=%s note=%s", mid, note)
        return mid, f"llm:{note}"
    except RouterLLMFailed:
        raise
    except Exception as e:
        return _fallback_or_raise(e, f"ошибка нейро-роутера: {e!s}")
