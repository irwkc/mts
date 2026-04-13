"""
REST API для JSON-деки презентации + пересборка PPTX (основа редактора Kimi-style).
"""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Body, HTTPException
from app.config import settings
from app.mws_client import MWSClient
from app.presentation_pptx import build_colorful_pptx, resolve_slide_images

logger = logging.getLogger("gpthub.presentation_api")

router = APIRouter(prefix="/presentation/api", tags=["presentation"])

_STEM_RE = re.compile(r"^presentation_[a-f0-9]{10}$")

_mws = MWSClient()


def _presentations_dir() -> Path:
    d = settings.data_dir / "static" / "presentations"
    d.mkdir(parents=True, exist_ok=True)
    return d


def validate_stem(stem: str) -> str:
    s = (stem or "").strip()
    if not _STEM_RE.match(s):
        raise HTTPException(
            status_code=400,
            detail="Invalid stem: expected presentation_<10 hex chars>",
        )
    return s


def deck_path(stem: str) -> Path:
    return _presentations_dir() / f"{stem}.json"


def pptx_path(stem: str) -> Path:
    return _presentations_dir() / f"{stem}.pptx"


async def _model_ids() -> set[str]:
    try:
        j = await _mws.get_models()
        ids = {m.get("id") for m in (j.get("data") or []) if isinstance(m, dict) and m.get("id")}
        ids.add(settings.auto_model_id)
        return ids
    except Exception as e:
        logger.warning("get_models for presentation rebuild: %s", e)
        return {settings.auto_model_id, settings.default_llm}


def _normalize_slides(slides: list[dict[str, Any]]) -> list[dict[str, Any]]:
    mx = max(1, int(settings.gena_max_presentation_slides))
    out: list[dict[str, Any]] = []
    for i, s in enumerate(slides[:mx]):
        if isinstance(s, dict):
            out.append(s)
    return out


@router.get("/deck/{stem}")
async def get_deck(stem: str) -> dict[str, Any]:
    stem = validate_stem(stem)
    p = deck_path(stem)
    if not p.is_file():
        raise HTTPException(status_code=404, detail="Deck JSON not found")
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        raise HTTPException(status_code=500, detail=f"Invalid JSON: {e}") from e
    if not isinstance(data, dict):
        raise HTTPException(status_code=500, detail="Deck root must be object")
    data.setdefault("stem", stem)
    data.setdefault(
        "pptx_rel_url",
        f"static/presentations/{stem}.pptx",
    )
    return data


@router.put("/deck/{stem}")
async def put_deck(stem: str, body: dict[str, Any] = Body(...)) -> dict[str, Any]:
    stem = validate_stem(stem)
    slides = body.get("slides")
    if slides is None or not isinstance(slides, list):
        raise HTTPException(status_code=400, detail='"slides" must be a list')
    normalized = _normalize_slides([x for x in slides if isinstance(x, dict)])
    if not normalized:
        raise HTTPException(status_code=400, detail="At least one slide required")
    deck_title = str(body.get("deck_title") or "")
    research = str(body.get("research_excerpt") or "")[:8000]
    doc: dict[str, Any] = {
        "deck_title": deck_title,
        "slides": normalized,
        "research_excerpt": research,
        "stem": stem,
        "pptx_rel_url": f"static/presentations/{stem}.pptx",
        "editor_url": f"/presentation/editor/?stem={stem}",
        "edit_hint": (
            "Веб-редактор: /presentation/editor/?stem=" + stem
        ),
    }
    outp = deck_path(stem)
    outp.write_text(json.dumps(doc, ensure_ascii=False, indent=2), encoding="utf-8")
    logger.info("deck saved stem=%s slides=%s", stem, len(normalized))
    return {"ok": True, "stem": stem, "slides_count": len(normalized)}


@router.post("/deck/{stem}/rebuild")
async def rebuild_pptx(stem: str) -> dict[str, Any]:
    stem = validate_stem(stem)
    p = deck_path(stem)
    if not p.is_file():
        raise HTTPException(status_code=404, detail="Deck JSON not found — save the deck first")
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        raise HTTPException(status_code=500, detail=f"Invalid JSON: {e}") from e
    slides = data.get("slides")
    if not isinstance(slides, list) or not slides:
        raise HTTPException(status_code=400, detail="Invalid slides in deck file")
    slides = _normalize_slides([x for x in slides if isinstance(x, dict)])
    deck_title = str(data.get("deck_title") or "")
    out_pptx = pptx_path(stem)
    available = await _model_ids()
    image_paths = await resolve_slide_images(
        _mws, slides, available, deck_title=deck_title
    )
    build_colorful_pptx(slides, image_paths, out_pptx, deck_title=deck_title)
    logger.info("pptx rebuilt stem=%s path=%s", stem, out_pptx)
    return {
        "ok": True,
        "stem": stem,
        "pptx_rel_url": f"static/presentations/{stem}.pptx",
        "slides_count": len(slides),
    }
