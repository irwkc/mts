"""
Опциональная память ChromaDB (gena/router/memory.py): семантический recall + сохранение реплик.
Retry при подключении — Chroma может стартовать позже шлюза.
"""

from __future__ import annotations

import hashlib
import logging
import time
from typing import Optional

from app.config import settings

logger = logging.getLogger("gpthub.chroma")

_client: Optional[object] = None
_client_failed_until: float = 0.0  # временная блокировка после ошибок подключения
_RETRY_COOLDOWN = 30.0  # секунд ждать между попытками переподключения


def _get_client():
    global _client, _client_failed_until
    host = (settings.chroma_host or "").strip()
    if not host:
        return None
    now = time.monotonic()
    if _client is not None:
        return _client
    if now < _client_failed_until:
        return None  # ещё в cooldown после последней ошибки
    try:
        import chromadb
        from chromadb.config import Settings as ChromaSettings

        cl = chromadb.HttpClient(
            host=host,
            port=int(settings.chroma_port),
            settings=ChromaSettings(anonymized_telemetry=False),
        )
        # Проверяем соединение
        cl.heartbeat()
        _client = cl
        logger.info("ChromaDB connected: %s:%d", host, settings.chroma_port)
        return _client
    except Exception as e:
        _client_failed_until = now + _RETRY_COOLDOWN
        logger.warning(
            "ChromaDB not available (%s:%d): %s — retry in %.0fs",
            host, settings.chroma_port, e, _RETRY_COOLDOWN,
        )
        return None


def _collection_name(user_id: str) -> str:
    return "u_" + hashlib.md5(user_id.encode()).hexdigest()[:12]


def recall_block(user_id: str, query: str, n_results: int = 5) -> str:
    """Текст для system: релевантные фрагменты из Chroma."""
    cl = _get_client()
    if not cl or not query.strip():
        return ""
    try:
        col = cl.get_or_create_collection(
            name=_collection_name(user_id),
            metadata={"hnsw:space": "cosine"},
        )
        if col.count() == 0:
            return ""
        n = min(n_results, max(1, col.count()))
        r = col.query(query_texts=[query[:2000]], n_results=n)
        docs = r.get("documents", [[]])[0]
        metas = r.get("metadatas", [[]])[0]
        lines = [
            f"{m.get('role', '?')}: {d}"
            for d, m in zip(docs, metas)
            if isinstance(d, str)
        ]
        if not lines:
            return ""
        return "Chroma (долгая память, gena-стиль):\n" + "\n".join(f"- {x}" for x in lines)
    except Exception as e:
        logger.warning("chroma recall: %s", e)
        # Сбрасываем клиент чтобы переподключиться в следующий раз
        global _client
        _client = None
        return ""


def save_message(user_id: str, role: str, content: str) -> None:
    cl = _get_client()
    if not cl or len((content or "").strip()) < 2:
        return
    try:
        col = cl.get_or_create_collection(
            name=_collection_name(user_id),
            metadata={"hnsw:space": "cosine"},
        )
        doc_id = hashlib.md5(f"{time.time()}{content}".encode()).hexdigest()
        col.add(
            documents=[content[:8000]],
            metadatas=[{"role": role, "ts": time.time()}],
            ids=[doc_id],
        )
    except Exception as e:
        logger.warning("chroma save: %s", e)
        global _client
        _client = None
