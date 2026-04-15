"""
Долгий диалог и «важная» память в духе OpenClaw: сводка контекста, явное «запомни», LLM-digest фактов.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any, Optional

from app.config import settings
from app.mws_client import MWSClient

logger = logging.getLogger("gpthub.memory")

_EXPLICIT_REMEMBER_RE = re.compile(
    r"(?i)(?:запомни(?:\s+что)?|remember(?:\s+that)?|save\s+that|важно)\s*[:,]?\s*(.+)",
)


def extract_explicit_remember(user_text: str) -> str:
    m = _EXPLICIT_REMEMBER_RE.search((user_text or "").strip())
    if not m:
        return ""
    return m.group(1).strip()[:4000]


def _message_content_to_plain(content: Any) -> str:
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for block in content:
            if isinstance(block, dict):
                if block.get("type") == "text" and isinstance(block.get("text"), str):
                    parts.append(block["text"])
            elif isinstance(block, str):
                parts.append(block)
        return "\n".join(parts)
    return str(content)


def messages_to_transcript(messages: list[dict[str, Any]], max_chars: int = 100_000) -> str:
    lines: list[str] = []
    n = 0
    for m in messages:
        role = m.get("role") or "unknown"
        text = _message_content_to_plain(m.get("content"))
        if not text.strip():
            continue
        lines.append(f"{role.upper()}: {text.strip()}")
        n += len(lines[-1]) + 1
        if n >= max_chars:
            lines.append("… [обрезано]")
            break
    return "\n\n".join(lines)


def _parse_json_fact_array(raw: str) -> list[str]:
    s = raw.strip()
    if not s:
        return []
    fence = re.match(r"^```(?:json)?\s*([\s\S]*?)```\s*$", s)
    if fence:
        s = fence.group(1).strip()
    try:
        data = json.loads(s)
    except json.JSONDecodeError:
        return []
    if not isinstance(data, list):
        return []
    out: list[str] = []
    for item in data:
        if isinstance(item, str) and item.strip():
            out.append(item.strip()[:1500])
    return out


async def digest_turn_to_facts(
    client: MWSClient, user_text: str, assistant_text: str
) -> list[str]:
    """Извлечь устойчивые факты из одного обмена (отдельный вызов LLM)."""
    ut = (user_text or "")[:3000]
    at = (assistant_text or "")[:6000]
    if len(ut) < 2 and len(at) < 2:
        return []
    body = {
        "model": settings.memory_digest_model,
        "temperature": 0.1,
        "max_tokens": 800,
        "messages": [
            {
                "role": "system",
                "content": (
                    "Ты извлекаешь факты для долгосрочной памяти ассистента между сессиями. "
                    "Верни ТОЛЬКО JSON-массив строк (без пояснений): факты, которые стоит помнить "
                    "(имена, предпочтения, договорённости, проектные решения, даты, ограничения). "
                    "Пропускай приветствия, шутки и разовые формулировки без последствий. "
                    "Если ничего важного — верни []. Язык фактов — как в диалоге."
                ),
            },
            {
                "role": "user",
                "content": f"Пользователь:\n{ut}\n\nАссистент:\n{at}\n\nJSON-массив:",
            },
        ],
    }
    try:
        out = await client.post_json("/chat/completions", body)
        ch0 = (out.get("choices") or [{}])[0]
        msg = ch0.get("message") or {}
        raw = msg.get("content")
        if isinstance(raw, list):
            raw = _message_content_to_plain(raw)
        if not isinstance(raw, str):
            return []
        return _parse_json_fact_array(raw)
    except Exception as e:
        logger.warning("memory digest LLM failed: %s", e)
        return []


async def summarize_messages_tail(
    client: MWSClient, messages: list[dict[str, Any]]
) -> str:
    """Сжать середину диалога в текстовую сводку."""
    transcript = messages_to_transcript(messages, max_chars=120_000)
    if not transcript.strip():
        return ""
    body = {
        "model": settings.memory_digest_model,
        "temperature": 0.2,
        "max_tokens": 2000,
        "messages": [
            {
                "role": "system",
                "content": (
                    "Сожми фрагмент переписки в связную сводку для ассистента: факты, решения, "
                    "открытые вопросы, договорённости. Без приветствий и воды. "
                    "5–20 предложений. Язык — как у пользователя в переписке."
                ),
            },
            {"role": "user", "content": transcript},
        ],
    }
    try:
        out = await client.post_json("/chat/completions", body)
        ch0 = (out.get("choices") or [{}])[0]
        msg = ch0.get("message") or {}
        raw = msg.get("content")
        if isinstance(raw, list):
            raw = _message_content_to_plain(raw)
        if isinstance(raw, str) and raw.strip():
            return raw.strip()[:8000]
    except Exception as e:
        logger.warning("memory compress summarize failed: %s", e)
    return ""


async def maybe_compress_messages_for_context(
    client: MWSClient, messages: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """
    Если сообщений много — оставить начальный system (если есть), свернуть середину в сводку,
    сохранить последние N реплик для модели.
    """
    if not settings.memory_compress_enabled:
        return messages
    after = max(8, settings.memory_compress_after_messages)
    keep = max(4, settings.memory_compress_keep_last)
    if len(messages) <= after:
        return messages

    first: Optional[dict[str, Any]] = None
    start = 0
    if messages and messages[0].get("role") == "system":
        first = messages[0]
        start = 1

    tail = messages[-keep:]
    head = messages[start : len(messages) - keep]
    if not head:
        return messages

    summary = await summarize_messages_tail(client, head)
    if not summary:
        return messages

    summary_msg = {
        "role": "system",
        "content": (
            "Сводка более ранней части диалога (для преемственности; опирайся при ответах):\n"
            + summary
        ),
    }
    out: list[dict[str, Any]] = []
    if first:
        out.append(dict(first))
    out.append(summary_msg)
    out.extend(tail)
    return out
