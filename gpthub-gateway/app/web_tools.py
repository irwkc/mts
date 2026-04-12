import re
from typing import Optional
from urllib.parse import urlparse

import httpx
import trafilatura
from duckduckgo_search import DDGS


URL_RE = re.compile(r"https?://[^\s)>\]}]+", re.I)

# Как gena RESEARCH_KEYWORDS + прежние триггеры
DEEP_RESEARCH_RE = re.compile(
    r"(глубокий\s+поиск|deep\s+research|глубок(ое|ий)\s+исследован|"
    r"многошагов(ый|ого)\s+поиск|iterative\s+search|исследуй\s+тему|"
    r"проанализируй\s+вс[её]\s+в\s+интернет|сделай\s+ресерч|сделай\s+рисерч)",
    re.I,
)


def extract_urls(text: str, limit: int = 3) -> list[str]:
    found = URL_RE.findall(text or "")
    out: list[str] = []
    for u in found:
        u = u.rstrip(".,;:")
        if u not in out:
            out.append(u)
        if len(out) >= limit:
            break
    return out


async def fetch_url_text(url: str, max_chars: int = 12000) -> str:
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        return ""
    try:
        async with httpx.AsyncClient(
            timeout=30.0,
            follow_redirects=True,
            headers={"User-Agent": "GPTHub/1.0 (compatible; research)"},
        ) as client:
            r = await client.get(url)
            r.raise_for_status()
            html = r.text
    except Exception as e:
        return f"(не удалось загрузить страницу: {e})"
    try:
        text = trafilatura.extract(html) or ""
    except Exception:
        text = ""
    if not text:
        text = html[:max_chars]
    return text[:max_chars]


def web_search_ddg(query: str, max_results: int = 5) -> str:
    lines: list[str] = []
    try:
        with DDGS() as ddgs:
            for i, r in enumerate(ddgs.text(query, max_results=max_results)):
                title = r.get("title") or ""
                body = r.get("body") or ""
                href = r.get("href") or ""
                lines.append(f"{i+1}. {title}\n{body}\n{href}")
    except Exception as e:
        return f"(ошибка поиска: {e})"
    if not lines:
        return "(пустой результат поиска)"
    return "Результаты веб-поиска:\n" + "\n\n".join(lines)


def should_run_deep_research(last_user_text: str) -> bool:
    t = last_user_text or ""
    return bool(DEEP_RESEARCH_RE.search(t))


def deep_research_ddg(topic: str, subqueries: int = 3) -> str:
    """Несколько запросов DuckDuckGo + сырой контекст для синтеза LLM (бонус «Deep Research»)."""
    topic = (topic or "").strip()[:500]
    if len(topic) < 4:
        return "(укажите тему исследования)"
    queries = [
        topic,
        f"{topic[:200]} обзор ключевых фактов",
        f"{topic[:200]} последние новости и тенденции",
    ][:subqueries]
    blocks: list[str] = []
    for i, q in enumerate(queries):
        blocks.append(f"=== Запрос {i + 1}: {q} ===\n{web_search_ddg(q, max_results=4)}")
    return "Многошаговый веб-поиск (контекст для ответа):\n\n" + "\n\n".join(blocks)


def should_run_web_search(last_user_text: str) -> bool:
    t = (last_user_text or "").lower()
    if should_run_deep_research(last_user_text):
        return False
    if any(
        k in t
        for k in (
            "найди в интернет",
            "поиск в сети",
            "web search",
            "search the web",
            "погугли",
        )
    ):
        return True
    return False


def search_query_from_text(last_user_text: str) -> str:
    t = (last_user_text or "").strip()
    for prefix in ("найди в интернете", "найди в интернет", "web search:", "search the web:"):
        if t.lower().startswith(prefix):
            return t[len(prefix) :].strip()
    return t[:500]
