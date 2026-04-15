# GPTHub (MWS + Open WebUI / gena)

Репозиторий: **https://github.com/irwkc/mts**

Стек в Docker: **Chroma** → **gpthub-gateway** (OpenAI-совместимый шлюз к MWS GPT, режим маршрутизации **gena**) → **Open WebUI** (форк в `./open-webui-src`, сборка из этого каталога — отдельный образ без старого overlay `open-webui-baobab`).

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

Скрипт создаёт `.env` из `.env.example` при отсутствии, проверяет ключ и выполняет **`docker compose up -d`** (без обязательной пересборки фронтенда на каждом запуске).

Первый запуск без готового `.env`:

```bash
MWS_API_KEY=sk-ваш_ключ ./up
```

### Тяжёлая сборка UI в Docker

Если сборка Open WebUI в контейнере упирается в память, соберите фронт на хосте и подставьте артефакт:

```bash
cd open-webui-src && npm ci && npm run build
cd .. && USE_PREBUILT_FRONTEND=true docker compose build open-webui && docker compose up -d
```

(см. `docker-compose.yml`, аргумент `USE_PREBUILT_FRONTEND`.)

## После старта

| Сервис | URL |
|--------|-----|
| Чат (Open WebUI) | http://localhost:3000 |
| Шлюз (модели) | http://127.0.0.1:8081/v1/models |

Проверка шлюза:

```bash
curl -s -H "Authorization: Bearer $MWS_API_KEY" http://127.0.0.1:8081/v1/models
```

### Смоук-тест шлюза

С поднятым стеком и заполненным `.env`:

```bash
python3 scripts/smoke_test_api.py
```

База URL при необходимости: `GPTHUB_BASE=http://127.0.0.1:8081`.

### Демо-мелодия (MP3 в чате)

В **нестримовом** запросе к шлюзу распознаются формулировки вроде «сгенерируй короткую мелодию» / «make a short melody» — ответ приходит с готовым MP3 (синтез в `gpthub-gateway`, модуль `music_demo`).

## Остановка

```bash
make down
```

или `docker compose down` / `docker-compose down`.

## Переменные (локально)

В `.env` обычно задают `MWS_API_BASE`, `GPTHUB_PUBLIC_BASE_URL=http://127.0.0.1:8081`, `WEBUI_URL=http://localhost:3000`. За reverse proxy укажите `GPTHUB_PUBLIC_BASE_URL` как публичный URL или оставьте пустым — см. логику шлюза.

| Переменная | Смысл (локально) |
|------------|------------------|
| `WEBUI_URL` | `http://localhost:3000` |
| `GPTHUB_PUBLIC_BASE_URL` | `http://127.0.0.1:8081` |

## Деплой и CI

В репозитории **нет** GitHub Actions (и иных workflow’ов) для **автодеплоя** на сервер: push в `main` только обновляет код на GitHub. Развёртывание — вручную (свой хост, `docker compose`, при необходимости — сборка и публикация образов в GHCR отдельно).

## Лицензии

Зависимости — по их лицензиям; код шлюза и обвязки — в рамках проекта.
