"""
Демо-музыка для gena: вокальная линия по MIDI-нотам (синус) → WAV → MP3 (~1–1.5 мин).
Ноты задаёт LLM (JSON) или детерминированная мелодия от текста запроса.
"""

from __future__ import annotations

import io
import json
import logging
import re
import wave
from typing import Any, Optional

import numpy as np
from pydub import AudioSegment

logger = logging.getLogger("gpthub.music_demo")

MUSIC_INTENT_RE = re.compile(
    r"("
    r"(?:сгенерируй|сгенерь|создай|напиши|сделай)(?:\s+мне)?\s+(?:короткую\s+)?(?:мелоди|музык|трек|композици)|"
    r"(?:сгенерируй|создай)\s+mp3\b|"
    r"\b(?:melody|music|tune)\s+mp3\b|"
    r"generate\s+(?:a\s+)?(?:short\s+)?(?:melody|music|tune)|"
    r"make\s+(?:a\s+)?(?:short\s+)?melody"
    r")",
    re.I,
)


def user_wants_music_demo(text: str) -> bool:
    """Запрос на демо-мелодию MP3 (синтез в шлюзе), без стрима."""
    t = (text or "").strip()
    if len(t) < 8:
        return False
    return bool(MUSIC_INTENT_RE.search(t))


_SAMPLE_RATE = 44100
_MAX_NOTES = 240
_MAX_TOTAL_SEC = 95.0
_TARGET_MIN_SEC = 60.0
_TARGET_MAX_SEC = 90.0
_MIN_NOTE_DUR = 0.1
_MAX_NOTE_DUR = 2.5


def _midi_to_hz(midi_note: int) -> float:
    return 440.0 * (2.0 ** ((float(midi_note) - 69.0) / 12.0))


def _sine_tone(freq: float, duration: float, sr: int = _SAMPLE_RATE, vol: float = 0.18) -> np.ndarray:
    n = max(1, int(duration * sr))
    t = np.arange(n, dtype=np.float64) / sr
    x = vol * np.sin(2.0 * np.pi * freq * t)
    fade = min(int(0.005 * sr), n // 4)
    if fade > 0:
        x[:fade] *= np.linspace(0.0, 1.0, fade)
        x[-fade:] *= np.linspace(1.0, 0.0, fade)
    return x


def _notes_to_mono_pcm(notes: list[tuple[int, float]]) -> np.ndarray:
    """notes: (midi_note, duration_sec)."""
    parts: list[np.ndarray] = []
    total = 0.0
    for midi_n, dur in notes:
        if total >= _MAX_TOTAL_SEC:
            break
        dur = float(max(_MIN_NOTE_DUR, min(dur, _MAX_NOTE_DUR)))
        midi_n = int(max(36, min(midi_n, 96)))
        hz = _midi_to_hz(midi_n)
        parts.append(_sine_tone(hz, dur))
        total += dur
    if not parts:
        parts.append(_sine_tone(_midi_to_hz(60), 0.4))
    return np.concatenate(parts)


def _pcm_to_mp3_bytes(pcm: np.ndarray, sr: int = _SAMPLE_RATE) -> bytes:
    pcm = np.clip(pcm, -1.0, 1.0)
    int16 = (pcm * 32767.0).astype(np.int16)
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes(int16.tobytes())
    buf.seek(0)
    seg = AudioSegment.from_file(buf, format="wav")
    out = seg.export(format="mp3", bitrate="128k")
    return out.read()


def fallback_melody_from_prompt(prompt: str) -> list[tuple[int, float]]:
    """C-maj pentatonic, детерминированно от хэша; длина ~TARGET_MIN…TARGET_MAX секунд."""
    h = (hash((prompt or "").strip()) + (1 << 32)) % (1 << 32)
    scale = [60, 62, 64, 65, 67, 69, 72]
    notes: list[tuple[int, float]] = []
    total = 0.0
    while total < _TARGET_MIN_SEC and len(notes) < _MAX_NOTES:
        h = (h * 1103515245 + 12345) & 0x7FFFFFFF
        idx = h % len(scale)
        dur = 0.22 + (h % 800) / 1000.0
        if h % 19 == 0:
            dur += 0.35
        dur = min(dur, _MAX_NOTE_DUR)
        notes.append((scale[idx], dur))
        total += dur
        if total >= _TARGET_MAX_SEC:
            break
    return notes


def _extract_json_array_obj(raw: str) -> Optional[dict[str, Any]]:
    t = (raw or "").strip()
    if "```" in t:
        m = re.search(r"```(?:json)?\s*(\{[\s\S]*?\})\s*```", t)
        if m:
            t = m.group(1)
    start = t.find("{")
    if start < 0:
        return None
    try:
        return json.loads(t[start:])
    except json.JSONDecodeError:
        return None


def parse_llm_notes(data: dict[str, Any]) -> Optional[list[tuple[int, float]]]:
    arr = data.get("notes")
    if not isinstance(arr, list):
        return None
    out: list[tuple[int, float]] = []
    for item in arr[:_MAX_NOTES]:
        if isinstance(item, dict):
            m = item.get("m")
            d = item.get("d")
        else:
            continue
        try:
            mi = int(m)
            du = float(d)
        except (TypeError, ValueError):
            continue
        out.append((mi, du))
    return out if out else None


def _melody_total_sec(notes: list[tuple[int, float]]) -> float:
    return float(sum(d for _, d in notes))


def _extend_melody_to_target(notes: list[tuple[int, float]]) -> list[tuple[int, float]]:
    """Короткий ответ LLM: повторяем фразу; если упёрлись в лимит нот — слегка растягиваем длительности."""
    if not notes:
        return notes
    if _melody_total_sec(notes) >= _TARGET_MIN_SEC * 0.88:
        return notes[:_MAX_NOTES]
    out: list[tuple[int, float]] = []
    idx = 0
    while len(out) < _MAX_NOTES:
        if _melody_total_sec(out) >= _TARGET_MIN_SEC:
            break
        m, d = notes[idx % len(notes)]
        d = float(max(_MIN_NOTE_DUR, min(d, _MAX_NOTE_DUR)))
        out.append((m, d))
        idx += 1
    tot = _melody_total_sec(out)
    if tot < _TARGET_MIN_SEC * 0.85 and out:
        scale = (_TARGET_MIN_SEC * 0.92) / max(tot, 1e-6)
        scale = min(scale, 8.0)
        out = [
            (m, min(_MAX_NOTE_DUR, max(_MIN_NOTE_DUR, d * scale)))
            for m, d in out
        ]
    return out[:_MAX_NOTES]


async def melody_notes_from_llm(
    client: Any,
    user_prompt: str,
    model_id: str,
) -> Optional[list[tuple[int, float]]]:
    """Один вызов chat: JSON с нотами (вокальная линия ~1–1.5 мин). При ошибке — None."""
    system = (
        "Ты композитор вокальной мелодии (одна линия «под песню», монофония). "
        "Верни ТОЛЬКО JSON-объект без markdown и без комментариев. "
        'Формат: {"notes":[{"m":60,"d":0.35},...]} — m: MIDI 52–84, d: длительность ноты в секундах 0.15–1.2 '
        "(можно длиннее на сильной доле). "
        f"Сумма всех d должна быть примерно {_TARGET_MIN_SEC:.0f}–{_TARGET_MAX_SEC:.0f} секунд (полноценный фрагмент, не джингл). "
        f"Нужно много нот (ориентир 80–180, не больше {_MAX_NOTES}): можно повторять мотивы (куплет/припев). "
        "Лад: мажор, минор или пентатоника — уместно под запрос. Одна нота одновременно. "
        "Учти настроение и тему пользователя."
    )
    try:
        data = await client.post_json(
            "/chat/completions",
            {
                "model": model_id,
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": (user_prompt or "")[:4000]},
                ],
                "temperature": 0.85,
                "max_tokens": 8192,
            },
        )
        raw = (data.get("choices") or [{}])[0].get("message", {}).get("content") or ""
        obj = _extract_json_array_obj(raw)
        if not obj:
            return None
        return parse_llm_notes(obj)
    except Exception as e:
        logger.warning("music LLM melody failed: %s", e)
        return None


def build_mp3_from_prompt(
    prompt: str,
    llm_notes: Optional[list[tuple[int, float]]],
) -> bytes:
    notes = llm_notes if llm_notes else fallback_melody_from_prompt(prompt)
    notes = _extend_melody_to_target(notes)
    pcm = _notes_to_mono_pcm(notes)
    return _pcm_to_mp3_bytes(pcm)
