# Техническое задание GPTHub (консолидация по репозиторию)

Исходного единого PDF/файла ТЗ в каталоге нет; этот документ **собирает требования** из `docs/ARCHITECTURE.md`, `docker-compose.yml`, шлюза `gpthub-gateway` и форка `open-webui-src`. Используйте его как чеклист приёмки.

## 1. Архитектура

| Требование | Реализация |
|------------|------------|
| Единый веб-чат | Open WebUI (образ BAOBAB) |
| Все вызовы LLM через один API | GPTHub Gateway → MWS `OPENAI`-совместимый API |
| Ключ только в окружении | `MWS_API_KEY` в `.env`, не в git |

## 2. Функции шлюза (MWS)

| ID | Сценарий | Endpoint / логика |
|----|----------|-------------------|
| Т1 | Текстовый диалог, ручная модель | `POST /v1/chat/completions` |
| Т2 | Авто-модель **gena 2.0** (`gpthub-auto`) | Роутер `pick_route_gena`, перехваты gena |
| Т3 | Картинка в сообщении (VLM) | Выбор `VISION_MODEL` |
| Т4 | «Нарисуй» / генерация изображения | `POST /v1/images/generations`, markdown в ответе |
| Т5 | Аудио → текст (диктовка, файлы) | `POST /v1/audio/transcriptions` → MWS Whisper |
| Т6 | Текст → речь (TTS) | `POST /v1/audio/speech` → MWS |
| Т7 | RAG по длинному тексту в чате | Чанки + эмбеддинги `EMBEDDING_MODEL` |
| Т8 | «Найди в интернете» | DuckDuckGo + контекст в system |
| Т9 | URL в сообщении | Загрузка текста страницы в контекст |
| Т10 | Долговременная память | SQLite + семантический отбор на эмбеддингах |
| Т11 | Список моделей | `GET /v1/models` + виртуальная `gpthub-auto` |
| Т12 | Эмбеддинги | `POST /v1/embeddings` |
| Т13 | Deep research (gena) | Перехват в шлюзе, веб-контекст |
| Т14 | Презентации PPTX (gena) | Перехват, статика `/static/` |
| Т15 | Музыкальное демо (опционально) | Локальный синтез в шлюзе |

## 3. Голосовой чат (Voice mode / «звонок»)

Open WebUI: кнопка **Voice mode** у поля ввода (иконка звонка). Цепочка:

1. Браузер: микрофон → запись фрагмента → `POST /api/audio/transcriptions` (Open WebUI).
2. Backend Open WebUI: `STT_ENGINE=openai` → `STT_OPENAI_API_BASE_URL` + `/audio/transcriptions` → **шлюз** → MWS.
3. Ответ чата стримится; для озвучки: события → `POST /api/audio/speech` → **шлюз** → MWS TTS.

**Условия:**

- В настройках аудио должен быть движок **OpenAI** (не **Web**), иначе Voice mode отключён.
- В `docker-compose` задано `ENABLE_PERSISTENT_CONFIG=false`, чтобы не перезаписать STT/TTS из SQLite.
- Микрофон: **HTTPS** или **`http://localhost:...`** (и обычно `http://127.0.0.1:...`) — безопасный контекст для `getUserMedia`. С произвольным HTTP-доменом без TLS браузер может запретить микрофон.
- Одна модель в чате при звонке (несколько моделей — кнопка блокируется).
- Роли пользователей: права `chat.stt`, `chat.tts`, `chat.call` должны быть включены (в compose задаются явно).

## 4. Переменные окружения (минимум)

См. `.env.example`. Критично: `MWS_API_KEY`, `MWS_API_BASE`, имена моделей из `GET /v1/models`.

Аудио (уже в compose, при необходимости переопределить в `.env`):

- `AUDIO_STT_ENGINE=openai`, `AUDIO_STT_OPENAI_API_BASE_URL`, `AUDIO_STT_MODEL`
- `AUDIO_TTS_ENGINE=openai`, `AUDIO_TTS_OPENAI_API_BASE_URL`, `AUDIO_TTS_MODEL`, `AUDIO_TTS_VOICE`

## 5. Проверка стека

```bash
bash scripts/verify-tz-stack.sh
```

Полный прогон с реальным MWS и тяжёлыми сценариями — вручную по таблице п.2 и голосу по п.3.

## 6. Известные ограничения

- Качество TTS/STT зависит от каталога моделей MWS по вашему ключу.
- Утечки JSON `queries` / `follow_ups` в текст режутся на шлюзе (см. код `web_tools.py`, `_patch_stream_chunk_for_ui`).
