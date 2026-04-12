# GPTHub

Единый чат-интерфейс на базе [Open WebUI](https://github.com/open-webui/open-webui) и шлюза **GPTHub Gateway**: все вызовы LLM идут в **MWS GPT** (OpenAI-совместимый API `https://api.gpt.mws.ru/v1`), с автоматическим выбором модели (`gpthub-auto`), долговременной памятью (эмбеддинги `bge-m3`), RAG по длинным вставкам текста, веб-поиском и загрузкой страниц по ссылке.

## Запуск одной командой

Создайте файл `.env` рядом с `docker-compose.yml` (например `cp .env.example .env`) и задайте в нём `MWS_API_KEY`, затем:

```bash
docker compose up -d --build
```

**Open WebUI на машину не устанавливается:** в `docker-compose.yml` для него указан готовый образ `ghcr.io/open-webui/open-webui:main` — Docker только **скачивает** его при первом запуске. **Собирается** из исходников только контейнер **gpthub-gateway** (`./gpthub-gateway`).

Чтобы в терминале было видно загрузку слоёв и шаги сборки (удобно на сервере по SSH):

```bash
bash scripts/compose-up-verbose.sh
```

Одна команда после подготовки `.env`: `docker compose up -d --build`.

Локально: **http://localhost:3000** (в `docker-compose` проброс на `127.0.0.1:3000`). На сервере снаружи — **http://** и публичный IP без порта (nginx на `:80` проксирует в Open WebUI). Только **http://**, не **https://**, пока нет TLS. Установка конфига nginx: `sudo bash scripts/setup-nginx.sh` из корня репозитория.

- API шлюза (отладка): **http://localhost:8081/v1/models**
- Первый вход в Open WebUI: создайте локальную учётную запись (если включён `ENABLE_SIGNUP`).

## Режимы модели

- **`gpthub-auto`** — автоматический выбор: VLM для сообщений с изображениями, сценарии «найди в интернете» / ссылки, обычный чат для текста; запросы вида «нарисуй / сгенерируй изображение» обрабатываются через `POST /v1/images/generations`.
- Любая другая модель из списка **GET /v1/models** — ручной выбор (шлюз не переопределяет `model`).

## Переменные окружения

См. [.env.example](.env.example). Критично: `MWS_API_KEY`. Имена моделей (`DEFAULT_LLM`, `VISION_MODEL`, …) должны совпадать с ответом `GET /v1/models` для вашего ключа.

## Деплой через GitHub Actions

При push в `main` workflow **собирает** образ `gpthub-gateway` на раннере GitHub (с [кэшем Docker BuildKit `gha`](https://docs.docker.com/build/ci/github-actions/cache/)), пушит в **GHCR** `ghcr.io/irwkc/mts-gpthub-gateway:latest`, затем по SSH на сервере: `git pull`, `docker compose pull`, `docker compose up -d --no-build`, nginx. Сборка на сервере не выполняется.

Пакет в GitHub Packages для этого образа должен быть **Public**, либо на сервере настроен `docker login ghcr.io`.

Если в Open WebUI по-прежнему пустой список моделей после смены настроек, один раз пересоздайте контейнер (`docker compose up -d --force-recreate`) или удалите том `open-webui-data` (удалит локальные чаты).

## Структура

- `docker-compose.yml` — Open WebUI + GPTHub Gateway.
- `gpthub-gateway/` — FastAPI-шлюз (прокси, роутер, память, RAG, веб-инструменты).
- [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) — схема и сценарии.
- [docs/MODELS.md](docs/MODELS.md) — соответствие моделей задачам.
- [docs/DEMO_SCRIPT.md](docs/DEMO_SCRIPT.md) — сценарий демо-видео.

## Лицензии

Open WebUI и зависимости — по их лицензиям; код шлюза — для проекта GPTHub.
