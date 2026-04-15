import json
import logging
import re
import time
from threading import Lock
from typing import Optional
from urllib.parse import urlparse

import httpx
import trafilatura
from duckduckgo_search import DDGS

from app.config import settings

logger = logging.getLogger("gpthub.web_tools")

_web_search_cache: dict[str, tuple[float, str]] = {}
_web_search_lock = Lock()


URL_RE = re.compile(r"https?://[^\s)>\]}]+", re.I)

# Как gena RESEARCH_KEYWORDS + прежние триггеры
DEEP_RESEARCH_RE = re.compile(
    r"(глубокий\s+поиск|deep\s+research|глубок(ое|ий)\s+исследован|"
    r"многошагов(ый|ого)\s+поиск|iterative\s+search|исследуй\s+тему|"
    r"проанализируй\s+вс[её]\s+в\s+интернет|сделай\s+ресерч|сделай\s+рисерч)",
    re.I,
)

# Расширенный список триггеров веб-поиска
_WEB_SEARCH_TRIGGERS = re.compile(
    r"("
    # Явные команды поиска
    r"найди\s+в\s+интернет|поиск\s+в\s+сети|web\s+search|google\s+this|search\s+the\s+web|"
    r"погугли|загугли|поищи\s+в\s+(сети|интернет)|"
    # Запросы про актуальность и новости
    r"что\s+нов(ого|ое|ые)|актуальн(ый|ые|ая|ое|о)\s+|последн(ие|ий|яя|ее)\s+(новости|данные|события|инфо)|"
    r"свежи(е|й)\s+(новости|данные|события)|"
    # Запросы на поиск информации
    r"найди\s+(информаци|данные|новости|факты|статистику)|"
    r"найди\s+(информацию|данные|новости|факты)\s+(о|про|по)|"
    # Фактические запросы
    r"кто\s+такой\s+\w|что\s+такое\s+\w{4}|сколько\s+стоит|"
    r"когда\s+(вышел|был|произошло|случилось)|"
    # Английские варианты
    r"look\s+up|find\s+(info|information|news)\s+(about|on)|latest\s+(news|info|data)|"
    r"current\s+(news|events|situation)|what'?s\s+(new|happening)"
    r")",
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
    key = f"{(query or '').strip()[:800]}|{max_results}"
    ttl = float(settings.web_search_cache_ttl_sec)
    now = time.time()
    with _web_search_lock:
        hit = _web_search_cache.get(key)
        if hit is not None and now - hit[0] < ttl:
            return hit[1]

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
        out = "(пустой результат поиска)"
    else:
        out = "Результаты веб-поиска:\n" + "\n\n".join(lines)

    with _web_search_lock:
        _web_search_cache[key] = (now, out)
        max_e = int(settings.web_search_cache_max_entries)
        while len(_web_search_cache) > max_e and _web_search_cache:
            oldest = min(_web_search_cache.keys(), key=lambda k: _web_search_cache[k][0])
            del _web_search_cache[oldest]
    return out


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
    t = (last_user_text or "")
    if should_run_deep_research(last_user_text):
        return False
    return bool(_WEB_SEARCH_TRIGGERS.search(t))


_IMG_URL_IN_TEXT = re.compile(
    r"https?://[^\s<>\]\"']+\.(?:jpg|jpeg|png|webp)(?:\?[^\s<>\]\"']*)?",
    re.I,
)


def _image_urls_from_ddg_text_fallback(query: str, max_urls: int = 12) -> list[str]:
    """Если ddgs.images пустой или заблокирован — вытащить прямые ссылки на jpg/png из текстовой выдачи."""
    q = (query or "").strip()[:400]
    if len(q) < 2:
        return []
    out: list[str] = []
    seen: set[str] = set()
    try:
        with DDGS() as ddgs:
            for r in ddgs.text(f"{q} photo picture image", max_results=8):
                blob = f"{r.get('body') or ''} {r.get('href') or ''}"
                for m in _IMG_URL_IN_TEXT.finditer(blob):
                    u = m.group(0).rstrip(").,;]")
                    if u.startswith("http") and u not in seen:
                        seen.add(u)
                        out.append(u)
                    if len(out) >= max_urls:
                        return out
    except Exception as e:
        logger.warning("image_urls_from_ddg_text_fallback: %s", e)
    return out


def image_search_ddg_urls(query: str, max_results: int = 24) -> list[str]:
    """Поиск картинок в интернете (DuckDuckGo images). Сначала type_image=photo (реальные фото)."""
    q = (query or "").strip()[:500]
    if len(q) < 2:
        return []
    urls: list[str] = []
    seen: set[str] = set()

    def consume(gen) -> None:
        for r in gen:
            u = (r.get("image") or r.get("thumbnail") or "").strip()
            if u.startswith("http") and u not in seen:
                seen.add(u)
                urls.append(u)
            if len(urls) >= max_results:
                break

    try:
        with DDGS() as ddgs:
            photo_used = False
            try:
                consume(ddgs.images(q, max_results=max_results, type_image="photo"))
                photo_used = True
            except TypeError:
                consume(ddgs.images(q, max_results=max_results))
            if photo_used and len(urls) < max(6, max_results // 3):
                consume(ddgs.images(q, max_results=max_results))
    except Exception as e:
        logger.warning("image_search_ddg_urls: %s", e)

    if len(urls) < 3:
        for u in _image_urls_from_ddg_text_fallback(q, max_urls=14):
            if u not in seen:
                seen.add(u)
                urls.append(u)
            if len(urls) >= max_results:
                break
    return urls[:max_results]


def try_parse_openwebui_queries_json(text: str) -> list[str] | None:
    """Только ответы вида Open WebUI query-generation: {\"queries\": [...] } без других ключей.

    Возвращает None, если это не такой объект; пустой список — для {\"queries\": []}.
    """
    t = (text or "").strip()
    if not t:
        return None
    if t.startswith("```"):
        lines = t.splitlines()
        if lines and lines[0].strip().startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        t = "\n".join(lines).strip()
    bracket_start = t.rfind("{")
    bracket_end = t.rfind("}") + 1
    if bracket_start == -1 or bracket_end <= bracket_start:
        return None
    try:
        blob = t[bracket_start:bracket_end]
        obj = json.loads(blob)
    except json.JSONDecodeError:
        return None
    if not isinstance(obj, dict):
        return None
    if set(obj.keys()) != {"queries"}:
        return None
    qs = obj.get("queries")
    if not isinstance(qs, list):
        return None
    return [str(x).strip() for x in qs]


def try_parse_openwebui_follow_ups_json(text: str) -> list[str] | None:
    """Open WebUI follow-up generation: {\"follow_ups\": [...] } без других ключей."""
    t = (text or "").strip()
    if not t:
        return None
    if t.startswith("```"):
        lines = t.splitlines()
        if lines and lines[0].strip().startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        t = "\n".join(lines).strip()
    bracket_start = t.rfind("{")
    bracket_end = t.rfind("}") + 1
    if bracket_start == -1 or bracket_end <= bracket_start:
        return None
    try:
        blob = t[bracket_start:bracket_end]
        obj = json.loads(blob)
    except json.JSONDecodeError:
        return None
    if not isinstance(obj, dict):
        return None
    if set(obj.keys()) != {"follow_ups"}:
        return None
    fu = obj.get("follow_ups")
    if not isinstance(fu, list):
        return None
    return [str(x).strip() for x in fu]


def search_query_from_text(last_user_text: str) -> str:
    t = (last_user_text or "").strip()
    # Убираем префикс-команду поиска, оставляем суть запроса
    for prefix in (
        "найди в интернете",
        "найди в интернет",
        "поищи в интернете",
        "поищи в интернет",
        "поищи в сети",
        "погугли",
        "загугли",
        "web search:",
        "search the web:",
        "google this:",
        "найди информацию о",
        "найди информацию про",
        "найди данные о",
        "найди данные про",
        "найди новости о",
        "найди новости про",
    ):
        if t.lower().startswith(prefix):
            return t[len(prefix):].strip()
    return t[:500]
