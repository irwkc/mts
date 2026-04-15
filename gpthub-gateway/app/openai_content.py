"""Единый разбор строкового и multimodal content/delta в стиле OpenAI."""

from __future__ import annotations

from typing import Any


def openai_content_to_text(content: Any, *, for_delta: bool = False) -> str:
    if isinstance(content, str):
        return content
    if not isinstance(content, list):
        return ""
    parts: list[str] = []
    for p in content:
        if isinstance(p, dict):
            t = p.get("text")
            if for_delta:
                typ = (p.get("type") or "").lower()
                if typ in ("text", "output_text") and isinstance(t, str):
                    parts.append(t)
                elif isinstance(t, str):
                    parts.append(t)
            else:
                if p.get("type") == "text" and isinstance(t, str):
                    parts.append(t)
                elif isinstance(t, str):
                    parts.append(t)
        elif isinstance(p, str):
            parts.append(p)
    return "".join(parts)


def delta_text(delta: dict[str, Any]) -> str:
    return openai_content_to_text(delta.get("content"), for_delta=True)
