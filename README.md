# GPTHub

Единый чат-интерфейс на базе [Open WebUI](https://github.com/open-webui/open-webui) и шлюза **GPTHub Gateway**: все вызовы LLM идут в **MWS GPT** (OpenAI-совместимый API `https://api.gpt.mws.ru/v1`), с автоматическим выбором модели (`gpthub-auto`), долговременной памятью (эмбеддинги `bge-m3`), RAG по длинным вставкам текста, веб-поиском и загрузкой страниц по ссылке.

## Запуск одной командой

Создайте файл `.env` рядом с `docker-compose.yml` (например `cp .env.example .env`) и задайте в нём `MWS_API_KEY`, затем:

```bash
docker compose up -d --build
```

**Open WebUI** собирается из **`open-webui-src/`** (форк с интеграцией gena) и слоя BAOBAB: `docker compose` использует **`open-webui-baobab/Dockerfile`** с контекстом **корня репозитория**. На проде по умолчанию тянется готовый образ **`ghcr.io/irwkc/mts-open-webui-baobab:latest`** из GitHub Actions. Отдельно из исходников собирается **gpthub-gateway** (`./gpthub-gateway`).

Чтобы в терминале было видно загрузку слоёв и шаги сборки (удобно на сервере по SSH):

```bash
bash scripts/compose-up-verbose.sh
```

Одна команда после подготовки `.env`: `docker compose up -d --build`.

Локально: **http://localhost:3000** (в `docker-compose` проброс на `127.0.0.1:3000`). На сервере снаружи nginx по умолчанию слушает только **порт 80 (HTTP)** — **`https://` сам по себе не появится**, пока не выпустите сертификат. После `sudo bash scripts/setup-nginx.sh`: `sudo CERTBOT_EMAIL=ваш@email bash scripts/enable-https.sh ваш-домен.tld`, затем в `.env` укажите **`WEBUI_URL=https://ваш-домен.tld`** и `docker compose up -d`.

- API шлюза (отладка): **http://localhost:8081/v1/models**
- Первый вход в Open WebUI: создайте локальную учётную запись (если включён `ENABLE_SIGNUP`).

## Режимы модели

- **`gpthub-auto`** — автоматический выбор по правилам **gena** (перехваты: презентации, картинки, deep research; иначе `pick_route_gena`: длинные тексты, код, обычный чат). VLM для сообщений с изображениями; «найди в интернете» / ссылки; «нарисуй» — `POST /v1/images/generations`. При `GPTHUB_ROUTER_DEBUG=true` в system добавляется `[GPTHub route: …]`. Open WebUI может слать id как `openai/gpthub-auto` — шлюз нормализует до `gpthub-auto`.
- Любая другая модель из списка **GET /v1/models** — ручной выбор (шлюз не переопределяет `model`).

Материалы сдачи: [docs/FEATURES_CHECKLIST.md](docs/FEATURES_CHECKLIST.md), [docs/PRESENTATION.md](docs/PRESENTATION.md), сценарий записи видео — [docs/DEMO_SCRIPT.md](docs/DEMO_SCRIPT.md).

Голос и диктофон: в compose заданы `AUDIO_STT_*` и `AUDIO_TTS_*` на шлюз (`/v1/audio/transcriptions`, `/v1/audio/speech` → MWS). Модель Whisper — `ASR_MODEL` в `.env`. Режим роутера по умолчанию: `GPTHUB_ROUTER_MODE=gena` (без отдельного LLM-классификатора).

## Переменные окружения

См. [.env.example](.env.example). Критично: `MWS_API_KEY`. Имена моделей (`DEFAULT_LLM`, `VISION_MODEL`, `GPTHUB_GENA_CHAT_MODEL`, `GPTHUB_MEMORY_DIGEST_MODEL`, …) должны совпадать с ответом `GET /v1/models` для вашего ключа. Ограниченный каталог (ключ «команда» и т.п.): [docs/MWS_TEAM_MODELS.md](docs/MWS_TEAM_MODELS.md).

## Деплой через GitHub Actions

При push в `main` workflow **собирает** образы при изменении путей (`gpthub-gateway/**`, `open-webui-*`), пушит в **GHCR**, затем по SSH на сервере: `git fetch` / `reset --hard origin/main`, `docker compose pull`, `docker compose up -d --force-recreate`, nginx. См. [.github/workflows/deploy.yml](.github/workflows/deploy.yml).

Пакет в GitHub Packages для образов должен быть **Public**, либо на сервере настроен `docker login ghcr.io`.

### Секреты репозитория (Actions)

| Секрет | Назначение |
|--------|------------|
| `SSH_HOST` | IP или hostname сервера |
| `SSH_USER` | Логин SSH — **должен совпадать** с учётной записью на сервере (после переименования пользователя обновите секрет) |
| `SSH_PASSWORD` | Пароль для входа по SSH; вставляйте без кавычек и без лишнего пробела/переноса в конце |
Если на сервере **отключён** вход по паролю (`PasswordAuthentication no`), в workflow вместо `password:` задайте `key: ${{ secrets.SSH_PRIVATE_KEY }}` (содержимое приватного ключа PEM) и **уберите** строку с `password:` — в `appleboy/ssh-action` нельзя указывать оба способа сразу.

Если job **deploy** падает с `ssh: unable to authenticate, attempted methods [none password]`: проверьте `SSH_USER` (должен совпадать с логином на сервере) и `SSH_PASSWORD`; зайдите с машины командой `ssh "$SSH_USER@$SSH_HOST"` с теми же данными. Убедитесь, что в секрете нет лишнего пробела или переноса строки в конце пароля.

Если в Open WebUI по-прежнему пустой список моделей после смены настроек, один раз пересоздайте контейнер (`docker compose up -d --force-recreate`) или удалите том `open-webui-data` (удалит локальные чаты).

### Автозапуск после перезагрузки сервера

Юнит **systemd** `mts-docker.service` выполняет `docker compose up -d` при загрузке (после `docker.service`). Установка вручную из каталога с `docker-compose.yml`: `sudo env MTS_HOME="$(pwd)" bash scripts/install-boot-autostart.sh` (скрипт сам ищет `/home/irwkc/mts` или `/home/ubuntuuser/mts`, если `MTS_HOME` не задан). Деплой через Actions передаёт `MTS_HOME="$(pwd)"` автоматически. Включены также `docker` и при наличии **nginx**.

## Структура

- `docker-compose.yml` — Open WebUI + GPTHub Gateway.
- `gpthub-gateway/` — FastAPI-шлюз (прокси, роутер, память, RAG, веб-инструменты).
- [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) — схема и сценарии.
- [docs/MODELS.md](docs/MODELS.md) — соответствие моделей задачам.
- [docs/MWS_TEAM_MODELS.md](docs/MWS_TEAM_MODELS.md) — дефолты под ограниченный каталог MWS, curl, чеклист.
- [docs/QA_CHECKLIST.md](docs/QA_CHECKLIST.md) — проверка ТЗ по шагам, готовые промпты, критерии ОК/не ОК.
- [docs/DEMO_SCRIPT.md](docs/DEMO_SCRIPT.md) — сценарий демо-видео.

## Лицензии

Open WebUI и зависимости — по их лицензиям; код шлюза — для проекта GPTHub.
