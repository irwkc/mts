"""
Цветные презентации PPTX с иллюстрациями (python-pptx + images/generations).
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
import uuid
from pathlib import Path
from typing import Any, Optional

import httpx
from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.enum.shapes import MSO_SHAPE
from pptx.enum.text import MSO_ANCHOR, PP_ALIGN
from pptx.util import Inches, Pt

from app.config import settings
from app.image_utils import image_api_response_to_sse_href
from app.mws_client import MWSClient

logger = logging.getLogger("gpthub.presentation")

_DEFAULT_ACCENTS = [
    "#1e40af",
    "#6d28d9",
    "#0f766e",
    "#c2410c",
    "#be185d",
    "#15803d",
    "#b45309",
    "#0369a1",
]


def _hex_to_rgb(h: str | None, idx: int) -> tuple[RGBColor, RGBColor]:
    """Акцент + светлый фон под контент."""
    raw = (h or "").strip().lstrip("#") or _DEFAULT_ACCENTS[idx % len(_DEFAULT_ACCENTS)].lstrip("#")
    if len(raw) != 6 or not re.fullmatch(r"[0-9a-fA-F]{6}", raw):
        raw = _DEFAULT_ACCENTS[idx % len(_DEFAULT_ACCENTS)].lstrip("#")
    r, g, b = int(raw[0:2], 16), int(raw[2:4], 16), int(raw[4:6], 16)
    accent = RGBColor(r, g, b)
    br = min(255, r // 5 + 204)
    bg = min(255, g // 5 + 204)
    bb = min(255, b // 5 + 204)
    return accent, RGBColor(br, bg, bb)


def parse_slides_json(raw: str) -> list[dict[str, Any]]:
    m = re.search(r"\[.*\]", raw, re.DOTALL)
    if m:
        raw = m.group(0)
    data = json.loads(raw)
    if not isinstance(data, list):
        raise ValueError("slides not a list")
    return [x for x in data if isinstance(x, dict)]


async def _href_to_local_path(href: str) -> Optional[Path]:
    if not href:
        return None
    if href.startswith("static/"):
        p = settings.data_dir / href
        return p if p.is_file() else None
    if href.startswith("http://") or href.startswith("https://"):
        try:
            async with httpx.AsyncClient(timeout=90.0, follow_redirects=True) as client:
                r = await client.get(href)
                r.raise_for_status()
                body = r.content
                ct = (r.headers.get("content-type") or "").lower()
            if "jpeg" in ct or "jpg" in ct:
                ext = ".jpg"
            elif "webp" in ct:
                ext = ".webp"
            d = settings.data_dir / "static" / "images"
            d.mkdir(parents=True, exist_ok=True)
            fn = f"slide_{uuid.uuid4().hex[:12]}{ext}"
            p = d / fn
            p.write_bytes(body)
            return p
        except Exception as e:
            logger.warning("download slide image url failed: %s", e)
            return None
    return None


async def generate_slide_image(
    client: MWSClient,
    image_model: str,
    prompt_en: str,
) -> Optional[Path]:
    """Одна картинка для слайда; файл на диске для add_picture."""
    p = (
        "Professional presentation slide illustration, clean modern flat or soft 3D style, "
        "vivid colors, generous whitespace, no text, no letters, no watermark. "
        + (prompt_en or "")[:3500]
    )
    try:
        resp = await client.post_json(
            "/images/generations",
            {
                "model": image_model,
                "prompt": p,
                "n": 1,
                "size": "1024x1024",
                "response_format": "b64_json",
            },
        )
        href = await image_api_response_to_sse_href(resp, settings.data_dir)
        return await _href_to_local_path(href)
    except Exception as e:
        logger.warning("slide image generation failed: %s", e)
        return None


def _pick_image_model(available_ids: set[str]) -> str:
    mid = settings.image_gen_model
    if mid in available_ids:
        return mid
    for c in ("qwen-image", "qwen-image-lightning", "sd3.5-large-image", "z-image-turbo"):
        if c in available_ids:
            return c
    return mid


def build_colorful_pptx(
    slides_data: list[dict[str, Any]],
    image_paths: list[Optional[Path]],
    out_path: Path,
) -> None:
    """Собрать PPTX: цветной верхний бар, светлый фон, текст + картинка справа (если есть)."""
    prs = Presentation()
    try:
        blank = prs.slide_layouts[6]
    except IndexError:
        blank = prs.slide_layouts[-1]

    slide_w = prs.slide_width
    slide_h = prs.slide_height
    bar_h = Inches(1.2)

    for idx, slide_data in enumerate(slides_data):
        img_path = image_paths[idx] if idx < len(image_paths) else None
        title = str(slide_data.get("title") or "Слайд")
        bullets = slide_data.get("bullets") or []
        if not isinstance(bullets, list):
            bullets = []
        accent_s = slide_data.get("accent")
        if isinstance(accent_s, str):
            accent_s = accent_s.strip()
        else:
            accent_s = None

        accent, light_bg = _hex_to_rgb(accent_s, idx)

        slide = prs.slides.add_slide(blank)

        # Светлая подложка
        body_rect = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, 0, 0, slide_w, slide_h)
        body_rect.fill.solid()
        body_rect.fill.fore_color.rgb = light_bg
        body_rect.line.fill.background()

        # Верхняя цветная полоса
        top_bar = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, 0, 0, slide_w, bar_h)
        top_bar.fill.solid()
        top_bar.fill.fore_color.rgb = accent
        top_bar.line.fill.background()

        # Заголовок (белый на полосе)
        tx_title = slide.shapes.add_textbox(
            Inches(0.35),
            Inches(0.18),
            Inches(9.3),
            Inches(0.82),
        )
        tf_t = tx_title.text_frame
        tf_t.word_wrap = True
        p0 = tf_t.paragraphs[0]
        p0.text = title
        p0.font.size = Pt(28)
        p0.font.bold = True
        p0.font.color.rgb = RGBColor(255, 255, 255)
        p0.alignment = PP_ALIGN.LEFT

        # Текст: слева; если есть картинка — уже колонка
        left_margin = Inches(0.45)
        top_body = bar_h + Inches(0.25)
        body_h = Inches(5.85)
        if img_path and img_path.is_file():
            text_w = Inches(4.85)
            tx_body = slide.shapes.add_textbox(left_margin, top_body, text_w, body_h)
        else:
            tx_body = slide.shapes.add_textbox(left_margin, top_body, Inches(9.1), body_h)

        tf_b = tx_body.text_frame
        tf_b.word_wrap = True
        tf_b.vertical_anchor = MSO_ANCHOR.TOP
        for i, bullet in enumerate(bullets[:12]):
            text = str(bullet).strip()
            if not text:
                continue
            if i == 0:
                p = tf_b.paragraphs[0]
            else:
                p = tf_b.add_paragraph()
            p.text = text
            p.font.size = Pt(16)
            p.font.color.rgb = RGBColor(55, 65, 81)
            p.space_after = Pt(8)
            p.level = 0

        if not bullets:
            p = tf_b.paragraphs[0]
            p.text = "—"
            p.font.size = Pt(16)
            p.font.color.rgb = RGBColor(120, 120, 120)

        # Картинка справа
        if img_path and img_path.is_file():
            pic_left = Inches(5.45)
            pic_top = top_body
            pic_w = Inches(4.15)
            slide.shapes.add_picture(str(img_path), pic_left, pic_top, width=pic_w, height=body_h)

    prs.save(str(out_path))


async def generate_images_for_slides(
    client: MWSClient,
    slides_data: list[dict[str, Any]],
    available_ids: set[str],
) -> list[Optional[Path]]:
    """Параллельно (с лимитом) сгенерировать по картинке на слайд."""
    model_id = _pick_image_model(available_ids)
    sem = asyncio.Semaphore(2)

    async def one(i: int, row: dict[str, Any]) -> Optional[Path]:
        async with sem:
            ip = row.get("image_prompt")
            if isinstance(ip, str) and ip.strip():
                prompt = ip.strip()
            else:
                prompt = f"Illustration for presentation slide: {row.get('title', '')}. Topics: {row.get('bullets', [])}"
            try:
                return await generate_slide_image(client, model_id, prompt)
            except Exception as e:
                logger.warning("slide %s image: %s", i, e)
                return None

    tasks = [one(i, row) for i, row in enumerate(slides_data)]
    return list(await asyncio.gather(*tasks))
