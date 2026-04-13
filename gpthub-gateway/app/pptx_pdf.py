"""Конвертация PPTX → PDF (LibreOffice soffice), опционально на сервере."""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path

logger = logging.getLogger("gpthub.pptx_pdf")


async def ensure_pptx_pdf(pptx: Path, pdf: Path, *, timeout: float = 120.0) -> bool:
    """
    Если pdf уже есть — True. Иначе вызывает soffice --headless.
    Возвращает True, если файл pdf создан и не пустой.
    """
    try:
        if pdf.is_file() and pdf.stat().st_size > 0:
            return True
    except OSError:
        pass
    if not pptx.is_file():
        return False
    outdir = pdf.parent
    try:
        proc = await asyncio.create_subprocess_exec(
            "soffice",
            "--headless",
            "--invisible",
            "--nologo",
            "--nofirststartwizard",
            "--convert-to",
            "pdf",
            "--outdir",
            str(outdir),
            str(pptx),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
        if proc.returncode != 0:
            logger.warning(
                "soffice pdf exit=%s stderr=%s",
                proc.returncode,
                (stderr or b"")[:800].decode("utf-8", errors="replace"),
            )
        ok = pdf.is_file() and pdf.stat().st_size > 0
        if not ok:
            logger.warning("pptx->pdf: output missing for %s", pdf)
        return ok
    except FileNotFoundError:
        logger.warning("soffice not found — install libreoffice-impress for PDF export")
        return False
    except asyncio.TimeoutError:
        logger.warning("pptx->pdf: timeout for %s", pptx)
        return False
    except Exception as e:
        logger.warning("pptx->pdf: %s", e)
        return False
