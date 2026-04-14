import asyncio
import json
import logging
from typing import Any, Optional

import httpx

from app.config import settings

logger = logging.getLogger("gpthub.mws")

_RETRYABLE_STATUS = frozenset({429, 502, 503, 504})


class MWSClient:
    def __init__(self) -> None:
        self.base = settings.mws_api_base.rstrip("/")
        self.key = settings.mws_api_key
        self._retries = max(0, int(settings.mws_http_retries))
        self._backoff = float(settings.mws_retry_backoff_sec)

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.key}",
            "Content-Type": "application/json",
        }

    def _should_retry(self, exc: BaseException) -> bool:
        if isinstance(exc, httpx.TimeoutException):
            return True
        if isinstance(exc, httpx.HTTPStatusError):
            return exc.response.status_code in _RETRYABLE_STATUS
        return False

    async def get_models(self) -> dict[str, Any]:
        last: Optional[BaseException] = None
        for attempt in range(self._retries + 1):
            try:
                async with httpx.AsyncClient(timeout=60.0) as client:
                    r = await client.get(f"{self.base}/models", headers=self._headers())
                    r.raise_for_status()
                    return r.json()
            except Exception as e:
                last = e
                if not self._should_retry(e) or attempt >= self._retries:
                    raise
                logger.warning(
                    "get_models retry %s/%s: %s",
                    attempt + 1,
                    self._retries + 1,
                    e,
                )
                await asyncio.sleep(self._backoff * (attempt + 1))
        assert last is not None
        raise last

    async def post_json(
        self,
        path: str,
        body: dict[str, Any],
        *,
        log_context: str = "",
    ) -> dict[str, Any]:
        last: Optional[BaseException] = None
        err_chars = max(500, int(settings.log_upstream_error_chars))
        ctx = f"{log_context} " if log_context else ""
        for attempt in range(self._retries + 1):
            try:
                async with httpx.AsyncClient(timeout=300.0) as client:
                    r = await client.post(
                        f"{self.base}{path}",
                        headers=self._headers(),
                        content=json.dumps(body),
                    )
                    r.raise_for_status()
                    return r.json()
            except httpx.HTTPStatusError as e:
                last = e
                txt = (e.response.text or "")[:err_chars]
                logger.error(
                    "MWS POST %s%s-> HTTP %s (attempt %s/%s)\nresponse body:\n%s",
                    ctx,
                    path,
                    e.response.status_code,
                    attempt + 1,
                    self._retries + 1,
                    txt or "(empty body)",
                )
                if not self._should_retry(e) or attempt >= self._retries:
                    raise
                logger.warning(
                    "post_json %s retry %s/%s after HTTP error",
                    path,
                    attempt + 1,
                    self._retries + 1,
                )
                await asyncio.sleep(self._backoff * (attempt + 1))
            except Exception as e:
                last = e
                if not self._should_retry(e) or attempt >= self._retries:
                    logger.error(
                        "MWS POST %s%s failed (final, attempt %s/%s): %s",
                        ctx,
                        path,
                        attempt + 1,
                        self._retries + 1,
                        e,
                        exc_info=not isinstance(e, httpx.HTTPStatusError),
                    )
                    raise
                logger.warning(
                    "post_json %s%s retry %s/%s: %s",
                    ctx,
                    path,
                    attempt + 1,
                    self._retries + 1,
                    e,
                )
                await asyncio.sleep(self._backoff * (attempt + 1))
        assert last is not None
        raise last

    async def embeddings(self, texts: list[str]) -> list[list[float]]:
        data = await self.post_json(
            "/embeddings",
            {"model": settings.embedding_model, "input": texts},
        )
        out = []
        for item in sorted(data["data"], key=lambda x: x["index"]):
            out.append(item["embedding"])
        return out
