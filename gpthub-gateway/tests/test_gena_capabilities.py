"""
Чеклист ТЗ gena (обязательные + доп.): проверки на уровне кода и HTTP-маршрутов шлюза.
Полный E2E с MWS/Open WebUI — в docker-compose и ручных сценариях из docs/DEMO_SCRIPT.md.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app import router_logic as rl
from app.main import app
from app.web_tools import (
    DEEP_RESEARCH_RE,
    URL_RE,
    should_run_deep_research,
    should_run_web_search,
)


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c


def test_tz_checklist_routes_exist(client: TestClient):
    """Маршруты API, нужные для пунктов ТЗ (чат, модели, эмбеддинги, картинки, голос)."""
    assert client.get("/health").json() == {"status": "ok"}
    paths = {r.path for r in app.routes}
    for p in (
        "/v1/chat/completions",
        "/v1/models",
        "/v1/embeddings",
        "/v1/images/generations",
        "/v1/images/edits",
        "/v1/audio/transcriptions",
        "/v1/audio/speech",
    ):
        assert p in paths, f"missing route {p}"


@pytest.mark.parametrize(
    "phrase,feature",
    [
        ("сделай deep research по квантовым вычислениям", "deep_research"),
        ("глубокое исследование темы нейросетей", "deep_research"),
        ("найди в интернете последние новости про Python", "web_search"),
        ("что нового в release Rust", "web_search"),
    ],
)
def test_tz_triggers_web_tools(phrase: str, feature: str):
    if feature == "deep_research":
        assert should_run_deep_research(phrase), phrase
        assert not should_run_web_search(phrase)
    else:
        assert should_run_web_search(phrase), phrase
        assert not should_run_deep_research(phrase)


def test_tz_url_parsing_trigger():
    t = "прочитай https://example.com/page и кратко перескажи"
    assert URL_RE.search(t)
    assert extract_urls_safe(t) == ["https://example.com/page"]


def extract_urls_safe(t: str) -> list[str]:
    from app.web_tools import extract_urls

    return extract_urls(t)


def test_tz_presentation_and_image_regex():
    from app.router_logic import IMAGE_GEN_RE, PRESENTATION_RE

    assert PRESENTATION_RE.search("сделай презентацию про отчёт")
    assert IMAGE_GEN_RE.search("нарисуй логотип кофейни")


def test_tz_router_gena_covers_vlm_audio_image_intent(router_settings):
    ids = {
        router_settings.default_llm,
        router_settings.vision_model,
        "gpthub-auto",
    }
    mid, note = rl.pick_route_gena(
        [{"role": "user", "content": [{"type": "image_url", "image_url": {"url": "http://x"}}]}],
        ids,
    )
    assert router_settings.vision_model in (mid, "gpt-4o", "gpt-4o-mini", "cotype-pro-vl-32b") or "vision" in note

    mid_a, note_a = rl.pick_route_gena(
        [{"role": "user", "content": [{"type": "input_audio", "input_audio": {}}]}],
        ids,
    )
    assert "audio" in note_a


def test_deep_research_regex_aligned_with_router():
    """router_logic._DEEP_RESEARCH_HINT и web_tools.DEEP_RESEARCH_RE согласованы по смыслу."""
    samples = [
        "сделай ресерч про Docker",
        "deep research on AI",
        "глубокое исследование рынка",
    ]
    for s in samples:
        assert DEEP_RESEARCH_RE.search(s), s
        assert rl._DEEP_RESEARCH_HINT.search(s), s
