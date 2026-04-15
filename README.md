# GPTHub

Веб-чат на [Open WebUI](https://github.com/open-webui/open-webui) и шлюзе **GPTHub Gateway** к API MWS GPT (`https://api.gpt.mws.ru/v1`).

## Запуск одной командой (GitLab / локально)

Нужны **Docker** и **Compose**: подкоманда `docker compose` или отдельная утилита `docker-compose` (скрипт поддерживает оба варианта).

```bash
git clone <URL_репозитория.git>
cd <папка-проекта>
MWS_API_KEY=ваш_ключ bash scripts/local-up.sh
```

Откройте **http://localhost:3000** · API шлюза: **http://localhost:8081/v1/models**

Скрипт при первом запуске создаёт `.env` из `.env.example`, при необходимости добавляет `GPTHUB_PUBLIC_BASE_URL=http://127.0.0.1:8081` и выполняет `docker compose up -d --build`. Ключ можно держать только в `.env` (`MWS_API_KEY=...`) и вызывать `bash scripts/local-up.sh` или `./local-up.sh`.

## Документация

Архитектура, модели, деплой, чеклисты: каталог [**docs/**](docs/). Развёрнутое описание проекта: [docs/README_PROJECT.md](docs/README_PROJECT.md).

## Лицензии

Зависимости — по их лицензиям; код шлюза — для проекта GPTHub.
