"""
Устаревший роутер (router/) — оставлен для совместимости.
Основной рабочий код — в gpthub-gateway/.

Этот роутер используется как fallback / reference implementation.
Модели приведены к актуальным именам MWS GPT API.
"""
import os
import re
import json
import httpx
from typing import Optional, AsyncGenerator
from fastapi import FastAPI, Request
from fastapi.responses import StreamingResponse, JSONResponse
from pydantic import BaseModel

import memory
import tools

MWS_API_KEY = os.getenv("MWS_API_KEY", "")
MWS_BASE_URL = os.getenv("MWS_API_BASE", "https://api.gpt.mws.ru/v1")
# Нормализация URL
if not MWS_BASE_URL.startswith("https://api.gpt.mws.ru"):
    MWS_BASE_URL = "https://api.gpt.mws.ru/v1"

app = FastAPI(title="MWS AI Workspace Router (legacy)")


# --- Модели данных ---
class Message(BaseModel):
    role: str
    content: str | list | None = ""


class ChatRequest(BaseModel):
    model: Optional[str] = None
    messages: list[Message]
    stream: Optional[bool] = False
    temperature: Optional[float] = 0.7
    max_tokens: Optional[int] = None
    user: Optional[str] = "anonymous"


# --- Актуальные модели MWS GPT (по ТЗ) ---
MODEL_CHAT = os.getenv("DEFAULT_LLM", "mts-anya")          # обычный диалог
MODEL_CODE = os.getenv("GPTHUB_GENA_CODE_MODEL", "qwen3-coder-480b-a35b")  # код
MODEL_LONG = os.getenv("GPTHUB_GENA_LONG_DOC_MODEL", "cotype-pro-vl-32b")  # длинные документы
MODEL_VISION = os.getenv("VISION_MODEL", "gpt-4o")         # картинки
MODEL_IMAGE_GEN = os.getenv("IMAGE_GEN_MODEL", "qwen-image")  # генерация

# --- Эвристики выбора моделей (синхронизированы с gpthub-gateway/router_logic.py) ---
CODE_KEYWORDS = re.compile(
    r"(напиш(и|ь)|реализу(й|ет|ация)|покаж(и|ет)|исправ(ь|и)|почин(и|ь)|отлад(ь|и)|"
    r"код|функц|алгоритм|скрипт|програм|python|js|javascript|sql|ошибк|баг|debug|"
    r"class|def |import |html|json|питон|java|c\+\+|c#|golang|rust|kotlin|bash)",
    re.IGNORECASE,
)

LONG_DOC_KEYWORDS = re.compile(
    r"(документ|файл|текст|перевод|реферат|статья|резюме|изложи|summarize|translate|"
    r"сократи|выдели главное|проанализируй|опиши|сравни|сделай обзор)",
    re.IGNORECASE,
)

IMAGE_KEYWORDS = re.compile(
    r"(нарисуй|сгенерируй\s+(?:изображение|картинк|фото|логотип|иконк|арт)|"
    r"создай\s*(?:картинк|изображен)|draw\s+|generate\s+an?\s+image|картинк\b|сделай\s+картинку)",
    re.IGNORECASE,
)

RESEARCH_KEYWORDS = re.compile(
    r"(глубокий\s+поиск|deep\s+research|глубок(ое|ий)\s+исследован|"
    r"исследуй\s+тему|сделай\s+ресерч|сделай\s+рисерч)",
    re.IGNORECASE,
)


def select_model(messages: list[Message]) -> str:
    user_texts = []
    for m in messages:
        if m.role == "user":
            if isinstance(m.content, str):
                user_texts.append(m.content)
            elif isinstance(m.content, list):
                for p in m.content:
                    if isinstance(p, dict) and p.get("type") == "text":
                        user_texts.append(p.get("text", ""))

    text = " ".join(user_texts)
    words = len(text.split())

    # Длинные документы
    if words > 600 or LONG_DOC_KEYWORDS.search(text):
        return MODEL_LONG

    # Код и функции
    if CODE_KEYWORDS.search(text):
        return MODEL_CODE

    # Обычные вопросы
    return MODEL_CHAT


def extract_last_user_text(messages: list[Message]) -> str:
    for m in reversed(messages):
        if m.role == "user":
            if isinstance(m.content, str):
                return m.content
            if isinstance(m.content, list):
                parts = [p.get("text", "") for p in m.content if isinstance(p, dict) and p.get("type") == "text"]
                return " ".join(parts)
    return ""


def build_system_context(user_id: str, text: str) -> str:
    parts = []

    # RAG Память (ChromaDB)
    recalled = memory.recall(user_id, text, n_results=5)
    if recalled:
        parts.append("=== Память о пользователе ===\n" + "\n".join(recalled))

    # Парсинг ссылок
    urls = tools.extract_urls(text)
    for u in urls[:2]:
        parts.append(f"=== Содержимое {u} ===\n" + tools.fetch_url(u))

    # Веб-поиск: расширенные триггеры
    if not urls and re.search(
        r"\b(найди|поищи|погугли|загугли|что\s+нов|актуальн|последние\s+новости|"
        r"web\s+search|look\s+up|поиск\s+в\s+интернет)\b",
        text, re.IGNORECASE
    ):
        parts.append(tools.web_search(text))

    return "\n\n".join(parts)


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.get("/v1/models")
async def list_models():
    """Актуальный список моделей MWS GPT по ТЗ."""
    models = [
        {"id": "gpthub-auto", "object": "model", "owned_by": "gpthub", "name": "gena 2.0 (авто)"},
        {"id": MODEL_CHAT, "object": "model", "owned_by": "mws"},
        {"id": MODEL_CODE, "object": "model", "owned_by": "mws"},
        {"id": MODEL_LONG, "object": "model", "owned_by": "mws"},
        {"id": MODEL_VISION, "object": "model", "owned_by": "mws"},
        {"id": "bge-m3", "object": "model", "owned_by": "mws"},
    ]
    return {"object": "list", "data": models}


@app.post("/v1/chat/completions")
async def chat_completions(req: ChatRequest):
    user_id = req.user or "anonymous"
    last_text = extract_last_user_text(req.messages)

    # Выбор модели
    is_auto = not req.model or req.model in ["gpthub-auto", "auto-router"]
    model_id = select_model(req.messages) if is_auto else req.model

    system_ctx = build_system_context(user_id, last_text)

    # Сохраняем в память
    if last_text:
        memory.save_message(user_id, "user", last_text)

    # Формируем тело для MWS
    messages_dicts = []
    for m in req.messages:
        messages_dicts.append({"role": m.role, "content": m.content})

    if system_ctx:
        if messages_dicts and messages_dicts[0]["role"] == "system":
            messages_dicts[0]["content"] = system_ctx + "\n\n" + str(messages_dicts[0]["content"])
        else:
            messages_dicts.insert(0, {"role": "system", "content": system_ctx})

    payload = {
        "model": model_id,
        "messages": messages_dicts,
        "stream": req.stream,
        "temperature": req.temperature,
    }
    if req.max_tokens:
        payload["max_tokens"] = req.max_tokens

    headers = {
        "Authorization": f"Bearer {MWS_API_KEY}",
        "Content-Type": "application/json",
    }

    if req.stream:
        return StreamingResponse(
            _stream_from_mws(payload, headers, user_id),
            media_type="text/event-stream"
        )

    async with httpx.AsyncClient(timeout=120) as client:
        resp = await client.post(f"{MWS_BASE_URL}/chat/completions", json=payload, headers=headers)
        if resp.status_code != 200:
            return JSONResponse(resp.json(), status_code=resp.status_code)

        data = resp.json()
        try:
            assistant_answer = data["choices"][0]["message"]["content"]
            if assistant_answer:
                memory.save_message(user_id, "assistant", str(assistant_answer))
        except Exception:
            pass
        return JSONResponse(data)


async def _stream_from_mws(payload: dict, headers: dict, user_id: str) -> AsyncGenerator[str, None]:
    async with httpx.AsyncClient(timeout=300) as client:
        async with client.stream("POST", f"{MWS_BASE_URL}/chat/completions", json=payload, headers=headers) as resp:
            if resp.status_code != 200:
                err = await resp.aread()
                yield f"data: {json.dumps({'error': err.decode()})}\n\n"
                return

            full_text = ""
            async for line in resp.aiter_lines():
                if not line:
                    continue
                if line.startswith("data:") and "[DONE]" not in line:
                    try:
                        obj = json.loads(line[5:].strip())
                        c = obj.get("choices", [{}])[0].get("delta", {}).get("content", "")
                        full_text += str(c or "")
                    except Exception:
                        pass
                yield line + "\n\n"

            if full_text:
                memory.save_message(user_id, "assistant", full_text)
