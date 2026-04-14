"""
Матрица автотестов ↔ пункты ТЗ (1–15) из шаблона фич / docs/TZ_ACCEPTANCE_TRACKER.md.

Покрывает логику шлюза (gpthub-gateway). E2E с реальным MWS и UI — вручную или в docker-compose.
"""

from __future__ import annotations

import json

import pytest

from app import router_logic as rl
from app.config import settings
from app.main import _patch_stream_chunk_for_ui, app
from app.memory_context import extract_explicit_remember
from app.music_demo import user_wants_music_demo
from app.rag_store import extract_embeddable_documents
from app.web_tools import extract_urls, should_run_deep_research, should_run_web_search

# --- TZ №1 Текстовой чат ---


def test_tz01_simple_chat_fast_path(router_settings):
    ids = {router_settings.default_llm, "gpthub-auto"}
    r = rl.try_fast_path_default_llm_for_simple_turn(
        [{"role": "user", "content": "привет"}], ids
    )
    assert r == (router_settings.default_llm, "auto:simple_chat")


# --- TZ №2 Голосовой чат (микрофон → STT → тот же чат) ---


def test_tz02_audio_message_routes_to_llm_branch(router_settings):
    ids = {router_settings.default_llm, "gpthub-auto"}
    mid, note = rl.pick_route_gena(
        [{"role": "user", "content": [{"type": "input_audio", "input_audio": {}}]}],
        ids,
    )
    assert "audio" in note


# --- TZ №3 Генерация изображений в чате ---


def test_tz03_image_generation_intent(router_settings):
    ids = {router_settings.default_llm, "gpthub-auto"}
    mid, note = rl.pick_route_gena(
        [{"role": "user", "content": "нарисуй иконку кота"}], ids
    )
    assert "image_gen" in note


# --- TZ №4 Аудиофайлы + ASR (эндпоинт прокси) ---


def test_tz04_transcriptions_route_registered():
    paths = {r.path for r in app.routes}
    assert "/v1/audio/transcriptions" in paths


# --- TZ №5 VLM ---


def test_tz05_vision_route(router_settings):
    ids = {router_settings.vision_model, router_settings.default_llm, "gpthub-auto"}
    mid, note = rl.pick_route_gena(
        [
            {
                "role": "user",
                "content": [{"type": "image_url", "image_url": {"url": "http://x"}}],
            }
        ],
        ids,
    )
    assert mid == router_settings.vision_model
    assert "vision" in note


# --- TZ №6 Файлы / RAG (извлечение вставок из текста) ---


def test_tz06_embeddable_blob_from_long_user_text():
    blob = "параграф " * 200
    text = f"Вот текст:\n\n{blob}\n\nвопрос?"
    docs = extract_embeddable_documents(text)
    assert len(docs) >= 1


# --- TZ №7 Поиск в интернете ---


def test_tz07_web_search_trigger():
    assert should_run_web_search("найди в интернете новости про Python")


# --- TZ №8 Веб по ссылке ---


def test_tz08_extract_url_from_message():
    t = "прочитай https://example.com и скажи заголовок"
    assert extract_urls(t) == ["https://example.com"]


# --- TZ №9 Долгосрочная память (явное «запомни») ---


def test_tz09_explicit_remember_extracted():
    hint = extract_explicit_remember("Запомни: мой город — Казань.")
    assert "казань" in hint.lower() or "Казань" in hint


# --- TZ №10 Автовыбор модели ---


def test_tz10_auto_skips_embedding_fallback():
    ids = {"gpthub-auto", "bge-m3", "cotype-pro-vl-32b"}
    r = rl.try_fast_path_default_llm_for_simple_turn(
        [{"role": "user", "content": "hi"}], ids
    )
    assert r is not None and r[0] != "bge-m3"


def test_tz10_code_route(router_settings):
    ids = {
        router_settings.default_llm,
        router_settings.gena_code_model,
        "gpthub-auto",
    }
    mid, note = rl.pick_route_gena(
        [{"role": "user", "content": "напиши на python функцию sort"}], ids
    )
    assert mid == router_settings.gena_code_model
    assert "code" in note


# --- TZ №11 Ручной выбор модели ---


def test_tz11_manual_route_known_model(router_settings):
    ids = {"gpthub-auto", "llama-3.1-8b-instruct", "other-chat"}
    mid, note = rl.apply_manual_route("other-chat", ids)
    assert mid == "other-chat"
    assert note == "manual"


def test_tz11_manual_unknown_falls_back_to_default(router_settings):
    ids = {"gpthub-auto", router_settings.default_llm}
    mid, _ = rl.apply_manual_route("nonexistent-model-xyz", ids)
    assert mid == router_settings.default_llm


# --- TZ №12 Markdown / код — рендер в Open WebUI; шлюз проксирует SSE ---


def test_tz12_stream_patch_preserves_text_delta():
    j = {"choices": [{"delta": {"content": "Hello"}}]}
    _patch_stream_chunk_for_ui(j)
    assert json.loads(json.dumps(j))["choices"][0]["delta"]["content"] == "Hello"


# --- TZ №13 Deep Research ---


def test_tz13_deep_research_trigger():
    assert should_run_deep_research("сделай deep research по теме RAG")


# --- TZ №14 Презентации ---


def test_tz14_presentation_keyword():
    from app.router_logic import PRESENTATION_RE

    assert PRESENTATION_RE.search("сделай презентацию про отчёт за квартал")


# --- TZ №15 Доп. (TTS + демо MP3) ---


def test_tz15_tts_route_exists():
    paths = {r.path for r in app.routes}
    assert "/v1/audio/speech" in paths


def test_tz15_music_demo_intent():
    assert user_wants_music_demo("сгенерируй короткую мелодию в mp3")


# --- SSE: провайдеры с reasoning / message вместо delta.content ---


def test_sse_patch_reasoning_into_content():
    j = {"choices": [{"delta": {"reasoning": "ответ"}}]}
    _patch_stream_chunk_for_ui(j)
    assert j["choices"][0]["delta"].get("content") == "ответ"


def test_sse_patch_message_fallback():
    j = {
        "choices": [
            {
                "delta": {},
                "message": {"role": "assistant", "content": "полный ответ"},
            }
        ]
    }
    _patch_stream_chunk_for_ui(j)
    assert j["choices"][0]["delta"].get("content") == "полный ответ"


# --- Инфра: список моделей содержит авто-модель ---


def test_models_merge_inserts_gpthub_auto(monkeypatch: pytest.MonkeyPatch):
    from app import main as main_mod

    fake = {
        "object": "list",
        "data": [{"id": "llama-3.1-8b-instruct", "object": "model"}],
    }

    async def fake_get_models():
        return fake

    monkeypatch.setattr(main_mod._client, "get_models", fake_get_models)
    merged = main_mod.merge_models_payload(fake)
    ids = [m["id"] for m in merged.get("data", [])]
    assert settings.auto_model_id in ids


# --- Настройки: нечатовые модели в skip ---


def test_non_chat_ids_include_embedding_and_env():
    skip = settings.router_skip_model_ids()
    assert "bge-m3" in skip or settings.embedding_model in skip
