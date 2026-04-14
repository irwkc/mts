"""Юнит-тесты роутера моделей (gpthub-auto / gena / deterministic)."""

from __future__ import annotations

import pytest

from app import router_logic as rl


def test_normalize_requested_model():
    assert rl.normalize_requested_model("") == ""
    assert rl.normalize_requested_model("gpthub-auto") == "gpthub-auto"
    assert rl.normalize_requested_model("openai/gpthub-auto") == "gpthub-auto"
    assert rl.normalize_requested_model("  llama-3.1-8b-instruct  ") == "llama-3.1-8b-instruct"


def test_content_to_text():
    assert rl._content_to_text(None) == ""
    assert rl._content_to_text("hello") == "hello"
    assert rl._content_to_text([{"type": "text", "text": "a"}, {"type": "text", "text": "b"}]) == "a\nb"
    assert "<image>" in rl._content_to_text([{"type": "image_url", "image_url": {}}])
    assert "<audio>" in rl._content_to_text([{"type": "input_audio", "input_audio": {}}])


def test_last_user_message():
    assert rl.last_user_message([]) is None
    assert rl.last_user_message([{"role": "assistant", "content": "x"}]) is None
    msgs = [{"role": "assistant", "content": "a"}, {"role": "user", "content": "hi"}]
    assert rl.last_user_message(msgs)["content"] == "hi"


def test_message_has_image_audio():
    assert rl.message_has_image([{"role": "user", "content": [{"type": "image_url"}]}]) is True
    assert rl.message_has_image([{"role": "user", "content": "data:image/png;base64,xx"}]) is True
    assert rl.message_has_image([{"role": "user", "content": "no image"}]) is False
    assert rl.message_has_audio([{"role": "user", "content": [{"type": "input_audio"}]}]) is True


def test_pick_route_manual(router_settings):
    ids = {"gpthub-auto", "llama-3.1-8b-instruct", "other"}
    mid, note = rl.pick_route([{"role": "user", "content": "hi"}], "llama-3.1-8b-instruct", ids)
    assert mid == "llama-3.1-8b-instruct"
    assert note == "manual"

    mid2, _ = rl.pick_route([], "unknown-model", ids)
    assert mid2 == router_settings.default_llm


def test_pick_route_deterministic_vision(router_settings):
    ids = {router_settings.vision_model, "gpthub-auto"}
    mid, note = rl.pick_route_deterministic(
        [{"role": "user", "content": [{"type": "image_url", "image_url": {"url": "http://x"}}]}],
        ids,
    )
    assert mid == router_settings.vision_model
    assert "vision" in note


def test_pick_route_deterministic_image_gen_intent(router_settings):
    ids = {router_settings.default_llm, "gpthub-auto"}
    mid, note = rl.pick_route_deterministic(
        [{"role": "user", "content": "нарисуй кота в шляпе"}],
        ids,
    )
    assert mid == router_settings.default_llm
    assert "image_gen" in note


def test_pick_route_gena_code_vs_chat(router_settings):
    ids = {
        router_settings.default_llm,
        router_settings.gena_code_model,
        router_settings.gena_long_doc_model,
        "gpthub-auto",
    }
    mid, note = rl.pick_route_gena(
        [{"role": "user", "content": "напиши функцию на python для сортировки"}],
        ids,
    )
    assert mid == router_settings.gena_code_model
    assert note == "gena:code"

    mid2, note2 = rl.pick_route_gena(
        [{"role": "user", "content": "как дела?"}],
        ids,
    )
    assert mid2 == router_settings.default_llm
    assert note2 == "auto:simple_chat"


def test_pick_route_gena_long_doc(router_settings):
    ids = {router_settings.default_llm, router_settings.gena_long_doc_model, "gpthub-auto"}
    long_text = "слово " * 700
    mid, note = rl.pick_route_gena([{"role": "user", "content": long_text}], ids)
    assert mid == router_settings.gena_long_doc_model
    assert note == "gena:long_doc"


def test_try_fast_path_simple_chat(router_settings):
    ids = {router_settings.default_llm, "gpthub-auto"}
    r = rl.try_fast_path_default_llm_for_simple_turn(
        [{"role": "user", "content": "привет"}],
        ids,
    )
    assert r is not None
    assert r[0] == router_settings.default_llm
    assert r[1] == "auto:simple_chat"

    assert (
        rl.try_fast_path_default_llm_for_simple_turn(
            [{"role": "user", "content": "найди в интернете новости"}],
            ids,
        )
        is None
    )
    assert (
        rl.try_fast_path_default_llm_for_simple_turn(
            [{"role": "user", "content": "сделай ресерч про Python"}],
            ids,
        )
        is None
    )


def test_inject_router_debug():
    out = rl.inject_router_debug(
        [{"role": "system", "content": "sys"}],
        "test-note",
        "my-model",
    )
    assert out[0]["role"] == "system"
    assert "[GPTHub route: test-note → my-model]" in out[0]["content"]


def test_strip_gena_assistant_markers():
    msgs = [
        {
            "role": "assistant",
            "content": "*(Авто-выбор модели: foo)*\n\nHello",
        }
    ]
    rl.strip_gena_assistant_markers(msgs)
    assert "*(Авто-выбор" not in msgs[0]["content"]
    assert "Hello" in msgs[0]["content"]
