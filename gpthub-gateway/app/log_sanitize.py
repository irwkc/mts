from __future__ import annotations

import copy
import json
import logging
import re
from typing import Any

logger = logging.getLogger("gpthub.log")

_REDACT_KEY_PARTS = (
    "password",
    "secret",
    "api_key",
    "authorization",
    "apikey",
    "access_token",
    "refresh_token",
    "client_secret",
)

_SK_PATTERN = re.compile(r"\bsk-[A-Za-z0-9_-]{12,}\b")


def _redact_string(s: str) -> str:
    return _SK_PATTERN.sub("sk-***REDACTED***", s)


def redact_for_log(obj: Any, _depth: int = 0) -> Any:
    """Копия объекта с замазанными секретами (рекурсивно)."""
    if _depth > 48:
        return "<max depth>"
    if isinstance(obj, dict):
        out: dict[str, Any] = {}
        for k, v in obj.items():
            ks = str(k).lower()
            if any(p in ks for p in _REDACT_KEY_PARTS) or ks in ("token", "bearer"):
                out[str(k)] = "***REDACTED***"
            else:
                out[str(k)] = redact_for_log(v, _depth + 1)
        return out
    if isinstance(obj, list):
        return [redact_for_log(x, _depth + 1) for x in obj]
    if isinstance(obj, str):
        return _redact_string(obj)
    return obj


def format_json_for_log(obj: Any, max_chars: int) -> str:
    """JSON с отступами; max_chars <= 0 — только пометка."""
    if max_chars <= 0:
        return "(logging disabled: GPTHUB_LOG_JSON_MAX_CHARS=0)"
    try:
        try:
            safe = redact_for_log(copy.deepcopy(obj))
        except Exception as e:
            safe = f"<deepcopy/redact failed: {e}>"
        text = json.dumps(safe, ensure_ascii=False, indent=2)
    except Exception as e:
        return f"<json serialize failed: {e}>"
    if len(text) > max_chars:
        return text[:max_chars] + f"\n... [truncated, total {len(text)} chars, max {max_chars}]"
    return text


def log_chat_json(
    log: logging.Logger,
    phase: str,
    request_id: str,
    payload: Any,
    max_chars: int,
) -> None:
    """Один блок лога: фаза + rid + JSON (санитизированный)."""
    if max_chars <= 0:
        log.info("chat %s rid=%s (payload log off)", phase, request_id)
        return
    body = format_json_for_log(payload, max_chars)
    log.info("chat %s rid=%s\n%s", phase, request_id, body)
