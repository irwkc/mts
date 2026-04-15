#!/usr/bin/env python3
"""
Смоук-проверка промптов из docs/TZ_ACCEPTANCE_TRACKER.md через OpenAI-совместимый API.
Использование:  GW=http://host:8081 python3 scripts/prompt_acceptance_smoke.py

Пропускает: голос (ТЗ2), аудиофайл без файла (ТЗ4), TTS кнопка в UI (15.1).
"""

from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request

GW = os.environ.get("GW", "http://127.0.0.1:8081").rstrip("/")
TIMEOUT = int(os.environ.get("SMOKE_TIMEOUT", "120"))


def req(method: str, path: str, body: dict | None = None) -> tuple[int, dict | list | str]:
    url = f"{GW}{path}"
    data = None
    headers = {"Content-Type": "application/json"}
    if body is not None:
        data = json.dumps(body, ensure_ascii=False).encode("utf-8")
    r = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(r, timeout=TIMEOUT) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
            ct = resp.headers.get("Content-Type", "")
            if "json" in ct or raw.strip().startswith("{"):
                return resp.status, json.loads(raw)
            return resp.status, raw
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8", errors="replace")
        try:
            return e.code, json.loads(raw)
        except json.JSONDecodeError:
            return e.code, {"_raw": raw[:800]}


def chat(model: str, messages: list[dict], max_tokens: int = 512, user: str | None = None, stream: bool = False):
    body: dict = {"model": model, "messages": messages, "stream": stream, "max_tokens": max_tokens}
    if user:
        body["user"] = user
    return req("POST", "/v1/chat/completions", body)


def ok_content(d: dict) -> str:
    if d.get("error"):
        return ""
    ch = (d.get("choices") or [{}])[0].get("message") or {}
    c = ch.get("content")
    if isinstance(c, str):
        return c
    return ""


def main() -> int:
    print(f"GW={GW}\n")
    results: list[tuple[str, str, str]] = []

    # 0
    st, h = req("GET", "/health")
    results.append(("0.1 health", "OK" if st == 200 and isinstance(h, dict) and h.get("status") == "ok" else f"FAIL http={st}", ""))

    st, m = req("GET", "/v1/models")
    ids = [x.get("id") for x in (m.get("data") if isinstance(m, dict) else []) or []]
    results.append(("0.2 models gpthub-auto", "OK" if "gpthub-auto" in ids else "FAIL", f"n={len(ids)}"))

    def run_tz(id_: str, prompt: str, extra: str = "", **kwargs):
        st, d = chat("gpthub-auto", [{"role": "user", "content": prompt}], **kwargs)
        if st != 200:
            results.append((id_, f"FAIL http={st}", str(d)[:200]))
            return
        if isinstance(d, dict) and d.get("error"):
            results.append((id_, "FAIL error", str(d.get("error"))[:200]))
            return
        text = ok_content(d) if isinstance(d, dict) else ""
        results.append((id_, "OK" if len(text) > 5 else "EMPTY?", extra + text[:120].replace("\n", " ")))

    run_tz("1.1 HTTP 404 RU", "В двух предложениях объясни, что такое HTTP-код 404.")
    run_tz("1.2 prime EN", "Say in one sentence what a prime number is.")

    results.append(("2.1–2.2 голос", "SKIP", "только UI/микрофон"))

    run_tz("3.1 иконка", "Нарисуй простую иконку: синий круг с белой буквой G внутри, плоский стиль.", max_tokens=256)
    run_tz("3.2 apple EN", "Draw a simple red apple on white background, flat icon.", max_tokens=256)

    results.append(("4.1 ASR файл", "SKIP", "нужен multipart + .wav в UI"))

    # 5 VLM — публичная картинка кота
    st, d = chat(
        "gpthub-auto",
        [
            {
                "role": "user",
                "content": [
                    {
                        "type": "image_url",
                        # Не hotlink с Wikimedia — у провайдера часто 403; httpbin отдаёт стабильный PNG
                        "image_url": {"url": "https://httpbin.org/image/png"},
                    },
                    {"type": "text", "text": "Что изображено на картинке? Ответь кратко по пунктам."},
                ],
            }
        ],
        max_tokens=300,
    )
    if st == 200 and isinstance(d, dict) and not d.get("error") and len(ok_content(d)) > 10:
        results.append(("5.1 VLM", "OK", ok_content(d)[:100]))
    else:
        results.append(("5.1 VLM", f"FAIL st={st}", str(d)[:200]))

    long_blob = ("Случайный факт номер %d. " * 80) % tuple(range(80))
    run_tz(
        "6.1 RAG текст",
        f"{long_blob}\n\nПо тексту выше: какие три факта названы явно? Только из текста.",
        max_tokens=400,
    )

    run_tz(
        "7.1 веб-поиск",
        "Найди в интернете последние новости про запуск космического телескопа за последний год. Дай 2–3 ссылки или факта с указанием источника.",
        max_tokens=600,
    )

    run_tz("8.1 example.com", "Прочитай https://example.com и скажи, что написано в заголовке страницы.", max_tokens=128)

    uid = "acceptance_tz9"
    st, d1 = chat(
        "gpthub-auto",
        [{"role": "user", "content": "Запомни: мой любимый язык программирования — Python."}],
        user=uid,
        max_tokens=256,
    )
    st2, d2 = chat(
        "gpthub-auto",
        [{"role": "user", "content": "Какой язык программирования я назвал любимым?"}],
        user=uid,
        max_tokens=128,
    )
    t2 = ok_content(d2) if isinstance(d2, dict) else ""
    py_ok = "python" in t2.lower()
    results.append(
        (
            "9.1–9.2 память",
            "OK" if st == 200 and st2 == 200 and py_ok else f"FAIL st={st}/{st2} py={py_ok}",
            t2[:120],
        )
    )

    run_tz("10.2 код is_prime", "Напиши на Python функцию is_prime(n), которая возвращает True для простых чисел.", max_tokens=512)
    results.append(("10.1 router debug", "SKIP", "нужны логи контейнера при GPTHUB_ROUTER_DEBUG=true"))

    st, d = chat(
        "llama-3.1-8b-instruct",
        [{"role": "user", "content": "Ответь одним словом: тест"}],
        user="tz11_manual_only",
        max_tokens=32,
    )
    c = ok_content(d) if isinstance(d, dict) else ""
    results.append(("11.1 ручная модель", "OK" if st == 200 and c.strip() else f"FAIL {st}", c[:80]))

    run_tz("12.1 таблица", "Дай таблицу из двух колонок: язык | приветствие, для русского и английского.", max_tokens=400)
    run_tz("12.2 JS for", "Покажи пример цикла for на JavaScript в блоке кода.", max_tokens=400)

    run_tz(
        "13.1 Deep Research",
        "Сделай глубокое исследование темы: влияние длины контекста LLM на качество RAG. Структурируй: введение, 3 тезиса, вывод.",
        max_tokens=2500,
    )

    run_tz(
        "14.1 презентация",
        "Сделай короткую презентацию на 5 слайдов про плюсы удалённой работы, без лишней воды.",
        max_tokens=512,
    )

    st, dm = chat(
        "gpthub-auto",
        [{"role": "user", "content": "Сгенерируй короткую мелодию в духе детской песенки, запиши в mp3."}],
        stream=False,
        max_tokens=256,
    )
    cm = ok_content(dm) if isinstance(dm, dict) else ""
    mp3_ok = "/static/music/" in cm or "static/music" in cm
    results.append(("15.2 MP3 демо", "OK" if mp3_ok else "WEAK(no /static/music link)", cm[:160]))

    results.append(("15.1 TTS озвучка", "SKIP", "только кнопка в Open WebUI"))

    print(f"{'ID':<22} {'Статус':<12} Детали")
    print("-" * 70)
    for rid, status, detail in results:
        print(f"{rid:<22} {status:<12} {detail}")
    failed = [r for r in results if r[1].startswith("FAIL") or r[1] == "EMPTY?"]
    weak = [r for r in results if r[1] == "WEAK(no /static/music link)"]
    print("-" * 70)
    if failed:
        print(f"Проблемы: {len(failed)}")
        return 1
    if weak:
        print("Есть замечания (WEAK), остальное OK.")
        return 0
    print("Все выполненные проверки OK.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
