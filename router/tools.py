"""
Устаревший модуль tools (router/) — оставлен для совместимости.
Основной инструментарий — в gpthub-gateway/app/web_tools.py.
"""
import re
import httpx
import trafilatura
from duckduckgo_search import DDGS

URL_RE = re.compile(r"https?://[^\s)>\]}]+", re.I)

# Расширенные триггеры веб-поиска (синхронизированы с gpthub-gateway)
WEB_SEARCH_TRIGGERS = re.compile(
    r"(найди\s+в\s+интернет|поиск\s+в\s+сети|web\s+search|погугли|загугли|"
    r"что\s+нов(ого|ое|ые)|актуальн|последние\s+(новости|данные)|свежие\s+(новости|данные)|"
    r"найди\s+(информацию|данные|новости|факты)|look\s+up|latest\s+news)",
    re.I,
)


def extract_urls(text: str, limit: int = 3) -> list[str]:
    found = URL_RE.findall(text or "")
    out = []
    for u in found:
        u = u.rstrip(".,;:")
        if u not in out:
            out.append(u)
        if len(out) >= limit:
            break
    return out


def fetch_url(url: str, max_chars: int = 12000) -> str:
    try:
        with httpx.Client(
            timeout=30.0,
            follow_redirects=True,
            headers={"User-Agent": "GPTHub/1.0 (compatible; research)"},
        ) as client:
            r = client.get(url)
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


def web_search(query: str, max_results: int = 5) -> str:
    lines = []
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
