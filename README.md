# GPTHub (MWS + Open WebUI)

Стек в Docker: **Chroma** → **gpthub-gateway** (OpenAI-совместимый шлюз к MWS GPT) → **Open WebUI** (чат на порту 3000).

## Что нужно

- Docker с Compose (`docker compose` или `docker-compose`)
- Ключ **`MWS_API_KEY`** в файле **`.env`** (скопируйте из `.env.example`, подставьте ключ)

## Одна команда запуска

Из корня репозитория:

```bash
chmod +x up && ./up
```

или:

```bash
make up
```

или:

```bash
bash scripts/local-up.sh
```

Скрипт создаёт `.env` из `.env.example` при отсутствии, проверяет ключ и выполняет **`docker compose up -d`** / **`docker-compose up -d`** (без полной пересборки UI).

Первый запуск без готового `.env`:

```bash
MWS_API_KEY=sk-ваш_ключ ./up
```

## После старта

| Сервис | URL |
|--------|-----|
| Чат (Open WebUI) | http://localhost:3000 |
| Шлюз (модели) | http://127.0.0.1:8081/v1/models |

Проверка шлюза: `curl -s -H "Authorization: Bearer $MWS_API_KEY" http://127.0.0.1:8081/v1/models`

## Остановка

```bash
make down
```

или `docker compose down` / `docker-compose down`.

## Переменные (локально)

В `.env` обычно задают `MWS_API_BASE`, `GPTHUB_PUBLIC_BASE_URL=http://127.0.0.1:8081`, `WEBUI_URL=http://localhost:3000`. За reverse proxy задайте `GPTHUB_PUBLIC_BASE_URL` на публичный URL или оставьте пустым — см. код шлюза.

## Лицензии

Зависимости — по их лицензиям; код шлюза и обвязки — в рамках проекта.
