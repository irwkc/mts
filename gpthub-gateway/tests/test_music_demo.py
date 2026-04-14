"""Триггеры демо MP3."""

from app.music_demo import user_wants_music_demo


def test_music_intent_russian():
    assert user_wants_music_demo("сгенерируй мелодию про осень")
    assert user_wants_music_demo("Создай короткую музыку в стиле джаз")
    assert not user_wants_music_demo("нарисуй кота")
    assert not user_wants_music_demo("")


def test_music_intent_english():
    assert user_wants_music_demo("generate a melody for a happy scene")
    assert not user_wants_music_demo("explain recursion")
