"""
Локальный RAG по загруженным фрагментам текста (сессия = user + chat key).
Поддерживает PDF через pypdf — Open WebUI может прислать paste из PDF.
"""

import io
import json
import logging
import sqlite3
import uuid
from typing import Optional

import numpy as np

from app.config import settings
from app.mws_client import MWSClient

logger = logging.getLogger("gpthub.rag")


def _cosine(a: list[float], b: list[float]) -> float:
    va = np.array(a, dtype=np.float64)
    vb = np.array(b, dtype=np.float64)
    na = np.linalg.norm(va)
    nb = np.linalg.norm(vb)
    if na == 0 or nb == 0:
        return 0.0
    return float(np.dot(va, vb) / (na * nb))


def chunk_text(text: str) -> list[str]:
    text = text.strip()
    if not text:
        return []
    chunks: list[str] = []
    i = 0
    size = settings.chunk_size
    ov = settings.chunk_overlap
    while i < len(text):
        chunks.append(text[i : i + size])
        i += max(size - ov, 1)
    return chunks


def extract_text_from_pdf_bytes(data: bytes) -> str:
    """Извлечь текст из PDF-байт через pypdf."""
    try:
        from pypdf import PdfReader

        reader = PdfReader(io.BytesIO(data))
        pages: list[str] = []
        for page in reader.pages:
            t = page.extract_text() or ""
            if t.strip():
                pages.append(t.strip())
        return "\n\n".join(pages)
    except Exception as e:
        logger.warning("PDF extraction failed: %s", e)
        return ""


class RAGStore:
    def __init__(self, path: str) -> None:
        self.path = path
        self._client = MWSClient()
        self._ensure()

    def _ensure(self) -> None:
        settings.data_dir.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(self.path)
        try:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS rag_chunks (
                    id TEXT PRIMARY KEY,
                    scope TEXT NOT NULL,
                    text TEXT NOT NULL,
                    embedding_json TEXT NOT NULL
                )
                """
            )
            conn.execute("CREATE INDEX IF NOT EXISTS idx_rag_scope ON rag_chunks(scope)")
            conn.commit()
        finally:
            conn.close()

    def ingest_text(self, scope: str, text: str) -> int:
        chunks = chunk_text(text)
        if not chunks:
            return 0
        # синхронные эмбеддинги в ingest — вызываем через asyncio в main
        return len(chunks)

    async def ingest_text_async(self, scope: str, text: str) -> int:
        chunks = chunk_text(text)
        if not chunks:
            return 0
        embs = await self._client.embeddings(chunks)
        conn = sqlite3.connect(self.path)
        try:
            for ch, emb in zip(chunks, embs):
                conn.execute(
                    "INSERT INTO rag_chunks (id, scope, text, embedding_json) VALUES (?,?,?,?)",
                    (str(uuid.uuid4()), scope, ch, json.dumps(emb)),
                )
            conn.commit()
        finally:
            conn.close()
        return len(chunks)

    async def retrieve(self, scope: str, query: str) -> str:
        if not query.strip():
            return ""
        conn = sqlite3.connect(self.path)
        try:
            rows = conn.execute(
                "SELECT text, embedding_json FROM rag_chunks WHERE scope = ?",
                (scope,),
            ).fetchall()
        finally:
            conn.close()
        if not rows:
            return ""
        try:
            q_emb = (await self._client.embeddings([query[:2000]]))[0]
        except Exception:
            return ""
        scored = []
        for text, ej in rows:
            try:
                emb = json.loads(ej)
                scored.append((_cosine(q_emb, emb), text))
            except Exception:
                continue
        scored.sort(key=lambda x: -x[0])
        top = [t for s, t in scored[: settings.rag_top_k] if s > 0.2]
        if not top:
            top = [t for s, t in scored[:3]]
        if not top:
            return ""
        return "Фрагменты из загруженных документов:\n" + "\n---\n".join(top)


def extract_embeddable_documents(last_user_text: str) -> list[str]:
    """
    Выделяет длинные вставки текста как кандидата на индексацию.
    Поддерживает PDF-контент (base64 или binary paste с маркером %PDF).
    """
    if not last_user_text:
        return []

    # Попытка распознать PDF paste
    if last_user_text.lstrip().startswith("%PDF"):
        try:
            pdf_text = extract_text_from_pdf_bytes(last_user_text.encode("latin-1", errors="replace"))
            if pdf_text.strip():
                logger.info("RAG: extracted PDF paste, %d chars", len(pdf_text))
                return [pdf_text]
        except Exception:
            pass

    # Обычный длинный текст
    if len(last_user_text) >= 800:
        return [last_user_text]

    return []


def looks_like_pdf_paste(text: str) -> bool:
    return "%PDF" in text[:2000] or text.count("\n") > 80
