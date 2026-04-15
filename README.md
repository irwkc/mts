# GPTHub (локальный запуск в Docker)

Да: взят смысл коммита **7edcaa1** (для **сервера** за nginx — пустой `GPTHUB_PUBLIC_BASE_URL`, относительные `/static/...` и HTTPS). Здесь **дефолты переведены на локалку**: `GPTHUB_PUBLIC_BASE_URL=http://127.0.0.1:8081`, `WEBUI_URL=http://localhost:3000`, UI слушает `3000` на всех интерфейсах. Для VPS отдельно задаёшь в `.env` пустой или `https://…` URL — как в том коммите.

Нужны **Docker** и **Compose** (`docker compose` или `docker-compose`).

## Одна команда на локалке

После того как в **`.env`** уже есть рабочий **`MWS_API_KEY`** (не заглушка):

```bash
bash scripts/local-up.sh
```

То же из корня репозитория (если `chmod +x local-up.sh`):

```bash
./local-up.sh
```

Скрипт только поднимает контейнеры: **`docker compose up -d`** (без тяжёлой сборки UI на машине).

Первый раз, если `.env` ещё нет — одна строка с ключом:

```bash
MWS_API_KEY=sk-ваш_ключ bash scripts/local-up.sh
```

(скрипт сам скопирует `.env` из `.env.example`, при необходимости допишет `GPTHUB_PUBLIC_BASE_URL` и запустит Docker.)

Эквивалент без скрипта, когда `.env` уже настроен:

```bash
docker compose up -d
```

Откройте **http://localhost:3000** · шлюз: **http://127.0.0.1:8081/v1/models**  
Остановка: **`docker compose down`**

### Дефолты под локалку

| Переменная | По умолчанию |
|------------|----------------|
| `WEBUI_URL` | `http://localhost:3000` |
| `GPTHUB_PUBLIC_BASE_URL` | `http://127.0.0.1:8081` |

### Продакшен (как 7edcaa1)

На сервере за nginx в **`.env`**:

```env
GPTHUB_PUBLIC_BASE_URL=
```

или `https://ваш-домен`.

## Лицензии

Зависимости — по их лицензиям; код шлюза — для проекта GPTHub.
