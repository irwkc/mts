"""
Долгосрочная память: SQLite + эмбеддинги bge-m3 (через MWS) для поиска релевантных фрагментов.
"""

import json
import sqlite3
import time
import uuid

import numpy as np

from app.config import settings
from app.mws_client import MWSClient


def _cosine(a: list[float], b: list[float]) -> float:
    va = np.array(a, dtype=np.float64)
    vb = np.array(b, dtype=np.float64)
    na = np.linalg.norm(va)
    nb = np.linalg.norm(vb)
    if na == 0 or nb == 0:
        return 0.0
    return float(np.dot(va, vb) / (na * nb))


class MemoryStore:
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
                CREATE TABLE IF NOT EXISTS memory_items (
                    id TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    text TEXT NOT NULL,
                    embedding_json TEXT NOT NULL,
                    created REAL NOT NULL
                )
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_mem_user ON memory_items(user_id)"
            )
            conn.commit()
        finally:
            conn.close()

    async def retrieve(self, user_id: str, query: str) -> str:
        if not query.strip():
            return ""
        conn = sqlite3.connect(self.path)
        try:
            rows = conn.execute(
                "SELECT text, embedding_json FROM memory_items WHERE user_id = ? "
                "ORDER BY created DESC LIMIT 100",
                (user_id,),
            ).fetchall()
        finally:
            conn.close()
        if not rows:
            return ""
        try:
            q_emb = (await self._client.embeddings([query]))[0]
        except Exception:
            return ""
        scored: list[tuple[float, str]] = []
        for text, ej in rows:
            try:
                emb = json.loads(ej)
                scored.append((_cosine(q_emb, emb), text))
            except Exception:
                continue
        scored.sort(key=lambda x: -x[0])
        top = [t for s, t in scored[: settings.memory_top_k] if s > 0.25]
        if not top:
            top = [t for s, t in scored[:3]]
        if not top:
            return ""
        return "Факты из долгосрочной памяти (может быть полезно):\n" + "\n".join(
            f"- {x}" for x in top
        )

    async def add_exchange(
        self, user_id: str, user_text: str, assistant_text: str
    ) -> None:
        line = f"Пользователь: {user_text[:800]}\nОтвет ассистента: {assistant_text[:1200]}"
        try:
            emb = (await self._client.embeddings([line[:2000]]))[0]
        except Exception:
            return
        conn = sqlite3.connect(self.path)
        try:
            conn.execute(
                "INSERT INTO memory_items (id, user_id, text, embedding_json, created) VALUES (?,?,?,?,?)",
                (
                    str(uuid.uuid4()),
                    user_id,
                    line,
                    json.dumps(emb),
                    time.time(),
                ),
            )
            conn.commit()
        finally:
            conn.close()
