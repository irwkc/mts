"""Парсинг утечки JSON task-generation Open WebUI (queries, follow_ups)."""

from app.web_tools import (
    try_parse_openwebui_follow_ups_json,
    try_parse_openwebui_queries_json,
)


def test_parses_strict_queries_only_object() -> None:
    assert try_parse_openwebui_queries_json('{"queries": ["a", "b"]}') == ["a", "b"]


def test_parses_with_markdown_fence() -> None:
    raw = '```json\n{"queries": ["x"]}\n```'
    assert try_parse_openwebui_queries_json(raw) == ["x"]


def test_empty_queries_list_is_match() -> None:
    assert try_parse_openwebui_queries_json('{"queries": []}') == []


def test_rejects_extra_keys() -> None:
    assert try_parse_openwebui_queries_json('{"queries": ["a"], "note": "x"}') is None


def test_rejects_plain_text() -> None:
    assert try_parse_openwebui_queries_json("Ответ пользователю") is None


def test_follow_ups_parses() -> None:
    raw = '{"follow_ups": ["Какой стиль?", "Что любишь?"]}'
    assert try_parse_openwebui_follow_ups_json(raw) == ["Какой стиль?", "Что любишь?"]


def test_follow_ups_rejects_with_queries_shape() -> None:
    assert try_parse_openwebui_follow_ups_json('{"queries": ["a"]}') is None


def test_queries_rejects_follow_ups_shape() -> None:
    assert try_parse_openwebui_queries_json('{"follow_ups": ["a"]}') is None
