#!/usr/bin/env python3
"""Смоук-тест gpthub-gateway по HTTP (реальный MWS). Запуск: из корня репо с поднятым Docker."""

from __future__ import annotations

import base64
import json
import os
import struct
import sys
import wave
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
BASE = os.environ.get("GPTHUB_BASE", "http://127.0.0.1:8081").rstrip("/")


def load_key() -> str:
    env = ROOT / ".env"
    if env.is_file():
        for line in env.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line.startswith("MWS_API_KEY=") and not line.endswith("your-key-here"):
                return line.split("=", 1)[1].strip().strip('"').strip("'")
    k = os.environ.get("MWS_API_KEY", "")
    if not k:
        print("FAIL: нет MWS_API_KEY в .env или окружении", file=sys.stderr)
        sys.exit(1)
    return k


def ok(name: str, cond: bool, detail: str = "") -> None:
    status = "OK" if cond else "FAIL"
    extra = f" — {detail}" if detail else ""
    print(f"[{status}] {name}{extra}")
    if not cond:
        raise SystemExit(1)


def main() -> None:
    key = load_key()
    h = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}

    with httpx.Client(timeout=120.0) as client:
        r = client.get(f"{BASE}/health")
        ok("GET /health", r.status_code == 200, r.text[:120])

        r = client.get(f"{BASE}/v1/models", headers={"Authorization": f"Bearer {key}"})
        ok("GET /v1/models", r.status_code == 200)
        models = r.json().get("data") or []
        ids = {m.get("id") for m in models if isinstance(m, dict)}
        ok("models содержит gpthub-auto", "gpthub-auto" in ids)
        any_chat = bool(ids - {"gpthub-auto"})
        ok("есть хотя бы одна реальная модель MWS", any_chat, str(ids)[:200])

        body = {
            "model": "gpthub-auto",
            "messages": [{"role": "user", "content": "Ответь одним словом: тест"}],
            "stream": False,
            "max_tokens": 32,
        }
        r = client.post(f"{BASE}/v1/chat/completions", headers=h, json=body)
        ok("POST chat (gpthub-auto) 200", r.status_code == 200, f"status={r.status_code}")
        j = r.json()
        msg = (j.get("choices") or [{}])[0].get("message", {}).get("content") or ""
        ok("есть текст ответа", len(str(msg).strip()) > 0)

        body_manual = {
            "model": "mws-gpt-alpha",
            "messages": [{"role": "user", "content": "1+1=?"}],
            "stream": False,
            "max_tokens": 20,
        }
        r = client.post(f"{BASE}/v1/chat/completions", headers=h, json=body_manual)
        ok("POST chat (ручная модель mws-gpt-alpha) 200", r.status_code == 200)

        body_md = {
            "model": "gpthub-auto",
            "messages": [
                {
                    "role": "user",
                    "content": 'Выведи блок кода на Python: print("hi")',
                }
            ],
            "stream": False,
            "max_tokens": 200,
        }
        r = client.post(f"{BASE}/v1/chat/completions", headers=h, json=body_md)
        ok("POST chat markdown/код 200", r.status_code == 200)
        msg = (r.json().get("choices") or [{}])[0].get("message", {}).get("content") or ""
        ok("ответ содержит print или код", "print" in msg.lower() or "```" in msg or "hi" in msg)

        emb = {
            "model": next((x for x in ("bge-m3", "BAAI/bge-multilingual-gemma2") if x in ids), "bge-m3"),
            "input": "тест эмбеддинга",
        }
        r = client.post(f"{BASE}/v1/embeddings", headers=h, json=emb)
        ok("POST /v1/embeddings 200", r.status_code == 200)
        data = r.json().get("data") or []
        ok("embedding не пустой", len(data) > 0 and len(data[0].get("embedding") or []) > 8)

        if "qwen-image" in ids or "qwen-image-lightning" in ids:
            img_model = "qwen-image-lightning" if "qwen-image-lightning" in ids else "qwen-image"
            r = client.post(
                f"{BASE}/v1/images/generations",
                headers=h,
                json={
                    "model": img_model,
                    "prompt": "a single red apple on white table, photorealistic, no text no watermark",
                    "n": 1,
                    "size": "1024x1024",
                },
                timeout=180.0,
            )
            ok(f"POST /v1/images/generations ({img_model}) 200", r.status_code == 200)
            d0 = (r.json().get("data") or [{}])[0]
            ok(
                "картинка b64 или url",
                bool(d0.get("b64_json") or d0.get("url")),
            )
        else:
            print("[SKIP] нет qwen-image в /v1/models — генерация картинок не проверена")

        png_1x1 = base64.b64decode(
            "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
        )
        b64img = base64.b64encode(png_1x1).decode("ascii")
        vm = "gpt-4o" if "gpt-4o" in ids else next(iter(x for x in ids if "vl" in x.lower() or "vision" in x.lower()), None)
        if vm:
            body_vlm = {
                "model": "gpthub-auto",
                "messages": [
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": "Что на изображении? Ответь одним словом."},
                            {
                                "type": "image_url",
                                "image_url": {"url": f"data:image/png;base64,{b64img}"},
                            },
                        ],
                    }
                ],
                "stream": False,
                "max_tokens": 40,
            }
            r = client.post(f"{BASE}/v1/chat/completions", headers=h, json=body_vlm, timeout=120.0)
            ok(f"VLM (1x1 png, роутер→{vm or 'auto'}) 200", r.status_code == 200)
        else:
            print("[SKIP] нет подходящей vision-модели в списке для явной проверки VLM")

        wav_path = Path("/tmp/gpthub_smoke.wav")
        with wave.open(str(wav_path), "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(16000)
            w.writeframes(struct.pack("<h", 0) * 8000)
        with open(wav_path, "rb") as f:
            files = {"file": ("smoke.wav", f.read(), "audio/wav")}
            data = {"model": next((x for x in ("whisper-medium", "whisper-turbo-local", "whisper-large-v3") if x in ids), "whisper-medium")}
            r = client.post(
                f"{BASE}/v1/audio/transcriptions",
                headers={"Authorization": f"Bearer {key}"},
                files=files,
                data=data,
                timeout=120.0,
            )
        ok("POST /v1/audio/transcriptions", r.status_code in (200, 400))
        if r.status_code == 200:
            t = r.json().get("text") if r.headers.get("content-type", "").startswith("application/json") else r.text
            ok("ASR вернул текст (в т.ч. пустой для тишины)", t is not None)
        else:
            print(f"[WARN] ASR status {r.status_code}: {r.text[:300]}")

        body_url = {
            "model": "gpthub-auto",
            "messages": [
                {
                    "role": "user",
                    "content": "Кратко по ссылке что за страница: https://example.com",
                }
            ],
            "stream": False,
            "max_tokens": 120,
        }
        r = client.post(f"{BASE}/v1/chat/completions", headers=h, json=body_url, timeout=120.0)
        ok("чат с URL (веб-парсинг) 200", r.status_code == 200)
        msg = (r.json().get("choices") or [{}])[0].get("message", {}).get("content") or ""
        low = msg.lower()
        ok(
            "ответ про example/domain",
            "example" in low or "домен" in low or "illustrative" in low or "iana" in low,
            msg[:200],
        )

        body_ns = {
            "model": "gpthub-auto",
            "messages": [
                {
                    "role": "user",
                    "content": "Найди в интернете последние новости про Mars colony yesterday exact headlines list",
                }
            ],
            "stream": False,
            "max_tokens": 80,
        }
        r = client.post(f"{BASE}/v1/chat/completions", headers=h, json=body_ns, timeout=120.0)
        ok("чат без обязательного DDG-инжекта 200", r.status_code == 200)
        msg = (r.json().get("choices") or [{}])[0].get("message", {}).get("content") or ""
        ok(
            "нет маркера «Результаты веб-поиска» (поиск отключён в шлюзе)",
            "Результаты веб-поиска" not in msg,
        )

        r = client.get("http://127.0.0.1:3000/", timeout=15.0)
        ok("Open WebUI GET / 200", r.status_code == 200)

    print("\nВсе проверки пройдены.")


if __name__ == "__main__":
    main()
