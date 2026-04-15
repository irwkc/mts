"""
Минимальный OpenAI-совместимый mock для локального стека без реального MWS_API_KEY.
"""
from __future__ import annotations

import asyncio
import json
import time
from pathlib import Path
from typing import Any, AsyncGenerator

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, Response, StreamingResponse

app = FastAPI(title="mock-mws")

MODELS = [
    {"id": "llama-3.1-8b-instruct", "object": "model", "created": 0, "owned_by": "mock"},
    {"id": "cotype-pro-vl-32b", "object": "model", "created": 0, "owned_by": "mock"},
    {"id": "qwen-image", "object": "model", "created": 0, "owned_by": "mock"},
    {"id": "whisper-medium", "object": "model", "created": 0, "owned_by": "mock"},
    {"id": "tts-1", "object": "model", "created": 0, "owned_by": "mock"},
    {"id": "bge-m3", "object": "model", "created": 0, "owned_by": "mock"},
]

_SILENT_MP3 = Path(__file__).resolve().parent / "silent.mp3"


@app.get("/v1/models")
async def models() -> dict[str, Any]:
    return {"object": "list", "data": MODELS}


def _sse_line(obj: dict) -> bytes:
    return f"data: {json.dumps(obj, ensure_ascii=False)}\n\n".encode()


async def _chat_stream(model: str) -> AsyncGenerator[bytes, None]:
    text = f"[mock-mws] Ответ для модели {model}. Стриминг OK."
    words = text.split()
    for i, word in enumerate(words):
        piece = word if i == len(words) - 1 else word + " "
        chunk = {
            "id": "chatcmpl-mock",
            "object": "chat.completion.chunk",
            "created": int(time.time()),
            "model": model,
            "choices": [
                {
                    "index": 0,
                    "delta": {"content": piece},
                    "finish_reason": None,
                }
            ],
        }
        yield _sse_line(chunk)
        await asyncio.sleep(0.02)
    yield _sse_line(
        {
            "id": "chatcmpl-mock",
            "object": "chat.completion.chunk",
            "created": int(time.time()),
            "model": model,
            "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}],
        }
    )
    yield b"data: [DONE]\n\n"


@app.post("/v1/chat/completions")
async def chat_completions(request: Request):
    body = await request.json()
    model = (body.get("model") or "mock")[:128]
    stream = bool(body.get("stream"))

    if stream:
        return StreamingResponse(
            _chat_stream(model),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
        )

    return JSONResponse(
        {
            "id": "chatcmpl-mock",
            "object": "chat.completion",
            "created": int(time.time()),
            "model": model,
            "choices": [
                {
                    "index": 0,
                    "message": {
                        "role": "assistant",
                        "content": f"[mock-mws] JSON-ответ для {model}.",
                    },
                    "finish_reason": "stop",
                }
            ],
            "usage": {"prompt_tokens": 1, "completion_tokens": 8, "total_tokens": 9},
        }
    )


@app.post("/v1/embeddings")
async def embeddings(request: Request):
    body = await request.json()
    inp = body.get("input") or ""
    if isinstance(inp, str):
        inp = [inp]
    data = []
    for i, _ in enumerate(inp):
        data.append(
            {
                "object": "embedding",
                "embedding": [0.01] * 8,
                "index": i,
            }
        )
    return {"object": "list", "data": data, "model": body.get("model", "bge-m3")}


@app.post("/v1/completions")
async def completions(request: Request):
    return await chat_completions(request)


@app.post("/v1/images/generations")
async def images(request: Request):
    return JSONResponse(
        {
            "created": int(time.time()),
            "data": [
                {
                    "url": "https://example.com/mock-image.png",
                    "revised_prompt": "mock",
                }
            ],
        }
    )


@app.post("/v1/audio/speech")
async def speech(request: Request):
    """Валидный короткий MP3, чтобы локальный стек проверял цепочку TTS без реального MWS."""
    _ = await request.json()
    data = _SILENT_MP3.read_bytes()
    return Response(content=data, media_type="audio/mpeg")


@app.post("/v1/audio/transcriptions")
async def transcribe():
    return {"text": "mock transcription"}
