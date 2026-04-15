# GPTHub — описание проекта

Единый чат-интерфейс на базе Open WebUI и шлюза **GPTHub Gateway**: вызовы LLM идут в **MWS GPT** (OpenAI-совместимый API), автоматический выбор модели (`gpthub-auto`), память (эмбеддинги), RAG, веб-поиск и загрузка страниц по ссылке.

## Сборка образов

Open WebUI собирается из `open-webui-src/` и слоя BAOBAB (`open-webui-baobab/Dockerfile`, контекст — корень репозитория). В CI по умолчанию образы: `ghcr.io/.../mts-open-webui-baobab:latest`, `ghcr.io/.../mts-gpthub-gateway:latest`.

Подробный вывод сборки: `bash scripts/compose-up-verbose.sh`.

## Режимы модели

- **`gpthub-auto`** — автоматический выбор по правилам gena (презентации, картинки, deep research; иначе роутер по тексту/коду/VLM). При `GPTHUB_ROUTER_DEBUG=true` в system добавляется `[GPTHub route: …]`.
- Любая другая модель из **GET /v1/models** — ручной выбор.

Материалы: [FEATURES_CHECKLIST.md](FEATURES_CHECKLIST.md), [PRESENTATION.md](PRESENTATION.md), [DEMO_SCRIPT.md](DEMO_SCRIPT.md).

Голос: `AUDIO_STT_*` / `AUDIO_TTS_*` на шлюз → MWS; Whisper — `ASR_MODEL` в `.env`.

## Проверка на сервере

[SERVER_VERIFICATION_RUNBOOK.md](SERVER_VERIFICATION_RUNBOOK.md), `bash scripts/verify-gpthub-stack.sh`.

## Переменные окружения

См. [.env.example](../.env.example). Критично: `MWS_API_KEY`. Имена моделей должны совпадать с `GET /v1/models`: [MWS_TEAM_MODELS.md](MWS_TEAM_MODELS.md).

## Деплой (GitHub Actions)

При push в `main` workflow собирает изменённые образы, пушит в GHCR, по SSH на сервере: `git reset`, `docker compose pull`, `up`, nginx. См. [.github/workflows/deploy.yml](../.github/workflows/deploy.yml). Образы в GHCR должны быть доступны серверу (`docker login` или Public package).

Секреты: `SSH_HOST`, `SSH_USER`, `SSH_PASSWORD` (или ключ вместо пароля — см. workflow).

Автозапуск после reboot: `scripts/install-boot-autostart.sh`, unit `mts-docker.service`.

## Структура репозитория

| Путь | Назначение |
|------|------------|
| `docker-compose.yml` | Open WebUI + gateway + Chroma |
| `gpthub-gateway/` | FastAPI-шлюз |
| `docs/ARCHITECTURE.md` | Схема |
| `docs/MODELS.md` | Модели и задачи |
| `docs/QA_CHECKLIST.md` | Проверки |
