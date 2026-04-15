"""
Разбор ответа POST /images/generations: встраивание картинки как data URL.
Добавлена авторизация при скачивании изображений с MWS API.
"""

from __future__ import annotations

import base64
import logging
import uuid
from pathlib import Path
from typing import Any

import httpx

from app.config import settings

logger = logging.getLogger("gpthub.image")

_MWS_DOMAINS = ("api.gpt.mws.ru", "mws.ru", "gpt.mws.ru")


async def fetch_image_bytes_from_url(url: str) -> bytes:
    """Скачать изображение по https URL. Для доменов MWS передаётся Bearer."""
    u = (url or "").strip()
    if not u.startswith("http://") and not u.startswith("https://"):
        return b""
    headers: dict[str, str] = {"User-Agent": "gpthub-gateway/1.0"}
    if any(d in u for d in _MWS_DOMAINS):
        headers["Authorization"] = f"Bearer {settings.mws_api_key}"
    try:
        async with httpx.AsyncClient(timeout=90.0, follow_redirects=True) as client:
            r = await client.get(u, headers=headers)
            r.raise_for_status()
            raw = r.content
        if not raw or not looks_like_image_bytes(raw[:64]):
            logger.warning("fetch_image_bytes_from_url: not a valid image (%s)", u[:80])
            return b""
        return raw
    except Exception as e:
        logger.warning("fetch_image_bytes_from_url failed (%s): %s", u[:80], e)
        return b""


def looks_like_image_bytes(head: bytes) -> bool:
    """Минимальная проверка, что байты — не пустой ответ и похожи на PNG/JPEG/GIF/WebP."""
    if len(head) < 8:
        return False
    if head.startswith(b"\x89PNG\r\n\x1a\n"):
        return True
    if len(head) >= 3 and head.startswith(b"\xff\xd8\xff"):
        return True
    if head.startswith(b"GIF87a") or head.startswith(b"GIF89a"):
        return True
    if len(head) >= 12 and head.startswith(b"RIFF") and head[8:12] == b"WEBP":
        return True
    return False


def _write_generated_image(data_dir: Path, raw: bytes, ext: str) -> str:
    """Сохранить байты под data_dir/static/images/, вернуть путь вида static/images/...."""
    if not raw or len(raw) < 24 or not looks_like_image_bytes(raw[:64]):
        logger.warning("rejecting image payload: invalid or empty (%s bytes)", len(raw))
        return ""
    d = data_dir / "static" / "images"
    d.mkdir(parents=True, exist_ok=True)
    fname = f"gen_{uuid.uuid4().hex[:12]}{ext}"
    (d / fname).write_bytes(raw)
    return f"static/images/{fname}"


def stored_image_file_is_valid(data_dir: Path, rel_static: str) -> bool:
    """Проверка, что под data_dir лежит непустой валидный файл изображения (для ссылок в чат)."""
    rel = rel_static.lstrip("/").replace("\\", "/")
    if not rel.startswith("static/"):
        return False
    p = (data_dir / rel).resolve()
    try:
        p.relative_to(data_dir.resolve())
    except ValueError:
        return False
    if not p.is_file():
        return False
    if p.stat().st_size < 24:
        return False
    try:
        head = p.read_bytes()[:128]
    except OSError:
        return False
    return looks_like_image_bytes(head)


async def image_api_response_to_sse_href(img_resp: dict[str, Any], data_dir: Path) -> str:
    """
    Короткая ссылка для стрима: внешний https URL или файл под static/images/.
    Не встраивает data:... — иначе Open WebUI падает с «Chunk too big» на одном SSE-событии.
    """
    data = (img_resp.get("data") or [{}])[0] if isinstance(img_resp, dict) else {}
    if not isinstance(data, dict):
        return ""

    b64 = data.get("b64_json")
    if isinstance(b64, str) and b64.strip():
        try:
            raw = base64.b64decode(b64.strip())
        except Exception as e:
            logger.warning("b64 decode failed: %s", e)
            return ""
        out = _write_generated_image(data_dir, raw, ".png")
        return out

    url = (data.get("url") or "").strip()
    if not url:
        return ""
    if url.startswith("data:"):
        try:
            head, b64part = url.split(",", 1)
            if ";base64" in head:
                raw = base64.b64decode(b64part)
                ext = ".png"
                if "jpeg" in head or "jpg" in head:
                    ext = ".jpg"
                elif "webp" in head:
                    ext = ".webp"
                out = _write_generated_image(data_dir, raw, ext)
                return out
        except Exception as e:
            logger.warning("data url to file failed: %s", e)
        return ""

    if not (url.startswith("http://") or url.startswith("https://")):
        return url if url.strip() else ""

    needs_auth = any(d in url for d in _MWS_DOMAINS)
    if not needs_auth:
        try:
            async with httpx.AsyncClient(timeout=90.0, follow_redirects=True) as client:
                r = await client.get(url, headers={"User-Agent": "gpthub-gateway/1.0"})
                r.raise_for_status()
                raw = r.content
            ct = (r.headers.get("content-type") or "image/png").lower()
            ext = ".png"
            if "jpeg" in ct or "jpg" in ct:
                ext = ".jpg"
            elif "webp" in ct:
                ext = ".webp"
            elif "gif" in ct:
                ext = ".gif"
            return _write_generated_image(data_dir, raw, ext)
        except Exception as e:
            logger.warning("could not fetch external image for sse (%s): %s", url[:80], e)
            return ""

    headers: dict[str, str] = {"User-Agent": "gpthub-gateway/1.0"}
    headers["Authorization"] = f"Bearer {settings.mws_api_key}"
    try:
        async with httpx.AsyncClient(timeout=90.0, follow_redirects=True) as client:
            r = await client.get(url, headers=headers)
            r.raise_for_status()
            raw = r.content
        ct = (r.headers.get("content-type") or "image/png").lower()
        ext = ".png"
        if "jpeg" in ct or "jpg" in ct:
            ext = ".jpg"
        elif "webp" in ct:
            ext = ".webp"
        return _write_generated_image(data_dir, raw, ext)
    except Exception as e:
        logger.warning("could not fetch image for sse (%s): %s", url[:80], e)
        return ""


async def image_api_response_to_data_url(img_resp: dict[str, Any]) -> str:
    """Вернуть data:image/...;base64,... пригодный для ![](...) в markdown."""
    data = (img_resp.get("data") or [{}])[0] if isinstance(img_resp, dict) else {}
    if not isinstance(data, dict):
        return ""

    b64 = data.get("b64_json")
    if isinstance(b64, str) and b64.strip():
        try:
            raw = base64.b64decode(b64.strip())
        except Exception:
            return ""
        if not raw or not looks_like_image_bytes(raw[:64]):
            logger.warning("rejecting invalid b64 for data url")
            return ""
        return f"data:image/png;base64,{b64.strip()}"

    url = (data.get("url") or "").strip()
    if not url:
        return ""
    if url.startswith("data:"):
        return url
    if not (url.startswith("http://") or url.startswith("https://")):
        return url

    headers: dict[str, str] = {"User-Agent": "gpthub-gateway/1.0"}
    mws_domains = ("api.gpt.mws.ru", "mws.ru", "gpt.mws.ru")
    if any(d in url for d in mws_domains):
        headers["Authorization"] = f"Bearer {settings.mws_api_key}"

    try:
        async with httpx.AsyncClient(timeout=90.0, follow_redirects=True) as client:
            r = await client.get(url, headers=headers)
            r.raise_for_status()
            raw = r.content
        if not raw or not looks_like_image_bytes(raw[:64]):
            logger.warning("rejecting non-image or empty body for data url (%s)", url[:80])
            return ""
        ct = (r.headers.get("content-type") or "image/png").split(";")[0].strip()
        if not ct.startswith("image/"):
            ct = "image/png"
        b64e = base64.b64encode(raw).decode("ascii")
        return f"data:{ct};base64,{b64e}"
    except Exception as e:
        logger.warning("could not inline image URL (%s): %s", url[:80], e)
        return ""
