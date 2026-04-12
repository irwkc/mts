# GPTHub

Единый чат-интерфейс на базе [Open WebUI](https://github.com/open-webui/open-webui) и шлюза **GPTHub Gateway**: все вызовы LLM идут в **MWS GPT** (OpenAI-совместимый API `https://api.gpt.mws.ru/v1`), с автоматическим выбором модели (`gpthub-auto`), долговременной памятью (эмбеддинги `bge-m3`), RAG по длинным вставкам текста, веб-поиском и загрузкой страниц по ссылке.

## Запуск одной командой

Создайте файл `.env` рядом с `docker-compose.yml` (например `cp .env.example .env`) и задайте в нём `MWS_API_KEY`, затем:

```bash
docker compose up -d --build
```

Одна команда после подготовки `.env`: `docker compose up -d --build`.

Откройте в браузере: **http://localhost:3000**

- API шлюза (отладка): **http://localhost:8081/v1/models**
- Первый вход в Open WebUI: создайте локальную учётную запись (если включён `ENABLE_SIGNUP`).

## Режимы модели

- **`gpthub-auto`** — автоматический выбор: VLM для сообщений с изображениями, сценарии «найди в интернете» / ссылки, обычный чат для текста; запросы вида «нарисуй / сгенерируй изображение» обрабатываются через `POST /v1/images/generations`.
- Любая другая модель из списка **GET /v1/models** — ручной выбор (шлюз не переопределяет `model`).

## Переменные окружения

См. [.env.example](.env.example). Критично: `MWS_API_KEY`. Имена моделей (`DEFAULT_LLM`, `VISION_MODEL`, …) должны совпадать с ответом `GET /v1/models` для вашего ключа.

## Структура

- `docker-compose.yml` — Open WebUI + GPTHub Gateway.
- `gpthub-gateway/` — FastAPI-шлюз (прокси, роутер, память, RAG, веб-инструменты).
- [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) — схема и сценарии.
- [docs/MODELS.md](docs/MODELS.md) — соответствие моделей задачам.
- [docs/DEMO_SCRIPT.md](docs/DEMO_SCRIPT.md) — сценарий демо-видео.

## Лицензии

Open WebUI и зависимости — по их лицензиям; код шлюза — для проекта GPTHub.
