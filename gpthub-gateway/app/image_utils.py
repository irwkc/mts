"""
Разбор ответа POST /images/generations: встраивание картинки как data URL.
Добавлена авторизация при скачивании изображений с MWS API.
"""

from __future__ import annotations

import base64
import logging
from typing import Any

import httpx

from app.config import settings

logger = logging.getLogger("gpthub.image")


async def image_api_response_to_data_url(img_resp: dict[str, Any]) -> str:
    """Вернуть data:image/...;base64,... пригодный для ![](...) в markdown."""
    data = (img_resp.get("data") or [{}])[0] if isinstance(img_resp, dict) else {}
    if not isinstance(data, dict):
        return ""

    # MWS может вернуть base64 напрямую
    b64 = data.get("b64_json")
    if isinstance(b64, str) and b64.strip():
        return f"data:image/png;base64,{b64.strip()}"

    url = (data.get("url") or "").strip()
    if not url:
        return ""
    if url.startswith("data:"):
        return url
    if not (url.startswith("http://") or url.startswith("https://")):
        return url

    # Скачиваем изображение. Для MWS-доменов добавляем авторизацию.
    headers: dict[str, str] = {"User-Agent": "gpthub-gateway/1.0"}
    mws_domains = ("api.gpt.mws.ru", "mws.ru", "gpt.mws.ru")
    if any(d in url for d in mws_domains):
        headers["Authorization"] = f"Bearer {settings.mws_api_key}"

    try:
        async with httpx.AsyncClient(timeout=90.0, follow_redirects=True) as client:
            r = await client.get(url, headers=headers)
            r.raise_for_status()
            raw = r.content
            ct = (r.headers.get("content-type") or "image/png").split(";")[0].strip()
            if not ct.startswith("image/"):
                ct = "image/png"
            b64e = base64.b64encode(raw).decode("ascii")
            return f"data:{ct};base64,{b64e}"
    except Exception as e:
        logger.warning("could not inline image URL (%s): %s", url[:80], e)
        # Возвращаем оригинальный URL — Open WebUI попробует сам
        return url
