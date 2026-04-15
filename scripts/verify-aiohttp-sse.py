#!/usr/bin/env python3
"""Проверка SSE через aiohttp (тот же клиент, что в Open WebUI при прокси на шлюз).

Запуск из корня репозитория после поднятого compose:
  python3 scripts/verify-aiohttp-sse.py

Ключ берётся из .env (MWS_API_KEY). URL по умолчанию: http://127.0.0.1:8081/v1/chat/completions
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ENV = ROOT / ".env"


def _load_key() -> str:
    if k := os.environ.get("MWS_API_KEY"):
        return k.strip()
    if not ENV.is_file():
        print("Нет .env и переменной MWS_API_KEY", file=sys.stderr)
        sys.exit(1)
    for line in ENV.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if line.startswith("MWS_API_KEY=") and not line.startswith("#"):
            return line.split("=", 1)[1].strip().strip('"').strip("'")
    print("MWS_API_KEY не найден в .env", file=sys.stderr)
    sys.exit(1)


async def main() -> None:
    import aiohttp

    key = _load_key()
    if not key or key == "sk-your-key-here":
        print("Задайте реальный MWS_API_KEY в .env", file=sys.stderr)
        sys.exit(1)

    url = os.environ.get("GPTHUB_SSE_TEST_URL", "http://127.0.0.1:8081/v1/chat/completions")
    body = {
        "model": "gpthub-auto",
        "stream": True,
        "max_tokens": 48,
        "messages": [{"role": "user", "content": "Reply with one short sentence."}],
    }

    timeout = aiohttp.ClientTimeout(total=120)
    async with aiohttp.ClientSession(timeout=timeout) as session:
        async with session.post(
            url,
            headers={
                "Authorization": f"Bearer {key}",
                "Content-Type": "application/json",
            },
            json=body,
        ) as resp:
            print("status", resp.status, "content-type", resp.headers.get("Content-Type"))
            cl = resp.headers.get("Content-Length")
            te = resp.headers.get("Transfer-Encoding")
            if cl:
                print("warning: upstream sent Content-Length=", cl, "(для SSE обычно нет)")
            if te:
                print("Transfer-Encoding:", te)

            n = 0
            buf = b""
            try:
                async for chunk in resp.content.iter_any():
                    if not chunk:
                        continue
                    buf += chunk
                    n += len(chunk)
                    while b"\n\n" in buf:
                        line, buf = buf.split(b"\n\n", 1)
                        s = line.decode("utf-8", errors="replace").strip()
                        if s.startswith("data:"):
                            print(s[:200])
                    if n > 20000:
                        print("… прочитано", n, "байт, останавливаемся")
                        break
            except aiohttp.ClientPayloadError as e:
                print("FAIL ClientPayloadError (как у Open WebUI):", e, file=sys.stderr)
                sys.exit(2)

    print("OK: aiohttp дочитал поток без ClientPayloadError, байт ~", n)


if __name__ == "__main__":
    asyncio.run(main())
