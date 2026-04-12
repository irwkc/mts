"""
Демо-музыка для gena: простой синтез по MIDI-нотам (синус) → WAV → MP3.
Опционально ноты задаёт LLM (JSON); иначе — детерминированная пентатоника от текста запроса.
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

_SAMPLE_RATE = 44100
_MAX_NOTES = 48
_MAX_TOTAL_SEC = 45.0


def _midi_to_hz(midi_note: int) -> float:
    return 440.0 * (2.0 ** ((float(midi_note) - 69.0) / 12.0))


def _sine_tone(freq: float, duration: float, sr: int = _SAMPLE_RATE, vol: float = 0.18) -> np.ndarray:
    n = max(1, int(duration * sr))
    t = np.arange(n, dtype=np.float64) / sr
    x = vol * np.sin(2.0 * np.pi * freq * t)
    # простой fade 5 ms
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
        dur = float(max(0.08, min(dur, 2.0)))
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
    """C-maj pentatonic, детерминированно от хэша запроса."""
    h = (hash((prompt or "").strip()) + (1 << 32)) % (1 << 32)
    scale = [60, 62, 64, 67, 69, 72]
    notes: list[tuple[int, float]] = []
    for _ in range(16):
        h = (h * 1103515245 + 12345) & 0x7FFFFFFF
        idx = h % len(scale)
        dur = 0.18 + (h % 180) / 1000.0
        notes.append((scale[idx], dur))
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


async def melody_notes_from_llm(
    client: Any,
    user_prompt: str,
    model_id: str,
) -> Optional[list[tuple[int, float]]]:
    """Один вызов chat: JSON с нотами. При ошибке — None."""
    system = (
        "Ты генератор короткой мелодии. Верни ТОЛЬКО JSON-объект без markdown. "
        'Формат: {"notes":[{"m":60,"d":0.25},...]} — m: MIDI 48-84, d: длительность ноты в секундах 0.12-0.6. '
        "8–20 нот, лучше пентатоника или мажор, без аккордов (одна нота за раз). "
        "Учти настроение из запроса пользователя кратко."
    )
    try:
        data = await client.post_json(
            "/chat/completions",
            {
                "model": model_id,
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": (user_prompt or "")[:1500]},
                ],
                "temperature": 0.9,
                "max_tokens": 800,
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
    pcm = _notes_to_mono_pcm(notes)
    return _pcm_to_mp3_bytes(pcm)
