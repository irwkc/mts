import json
from typing import Any

import httpx

from app.config import settings


class MWSClient:
    def __init__(self) -> None:
        self.base = settings.mws_api_base.rstrip("/")
        self.key = settings.mws_api_key

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.key}",
            "Content-Type": "application/json",
        }

    async def get_models(self) -> dict[str, Any]:
        async with httpx.AsyncClient(timeout=60.0) as client:
            r = await client.get(f"{self.base}/models", headers=self._headers())
            r.raise_for_status()
            return r.json()

    async def post_json(self, path: str, body: dict[str, Any]) -> dict[str, Any]:
        async with httpx.AsyncClient(timeout=300.0) as client:
            r = await client.post(
                f"{self.base}{path}",
                headers=self._headers(),
                content=json.dumps(body),
            )
            r.raise_for_status()
            return r.json()

    async def embeddings(self, texts: list[str]) -> list[list[float]]:
        data = await self.post_json(
            "/embeddings",
            {"model": settings.embedding_model, "input": texts},
        )
        out = []
        for item in sorted(data["data"], key=lambda x: x["index"]):
            out.append(item["embedding"])
        return out
