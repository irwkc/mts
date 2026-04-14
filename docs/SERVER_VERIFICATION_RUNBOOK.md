# Проверка полного стека GPTHub на сервере

Запускать **на хосте**, где лежит `docker-compose.yml` и `.env` с `MWS_API_KEY`.

Автоматизация: [../scripts/verify-gpthub-stack.sh](../scripts/verify-gpthub-stack.sh).

## Стек (факт из `docker-compose.yml`)

- **chroma** — векторная БД (том `chroma-data`).
- **gpthub-gateway** — внутри контейнера слушает **:8080**, на хосте проброшен **:8081**.
- **open-webui** — **127.0.0.1:3000** → в UI `OPENAI_API_BASE_URL=http://gpthub-gateway:8080/v1`.
- Nginx снаружи: статика шлюза `/static/`, `/presentation/` → бэкенд шлюза; остальное → WebUI.

## Шаг 0 — переменные

```bash
cd /path/to/mts   # каталог с docker-compose.yml
export KEY=$(grep '^MWS_API_KEY' .env | cut -d= -f2- | tr -d ' "'"'")
export GW="http://127.0.0.1:8081"
test -n "$KEY" && echo "KEY OK (${#KEY} chars)" || echo "FAIL: пустой MWS_API_KEY"
```

## Шаг 1 — инфраструктура

| # | Команда | Ожидание |
|---|---------|----------|
| 1.1 | `docker compose ps` | `chroma`, `gpthub-gateway`, `open-webui` — Up; gateway **healthy** |
| 1.2 | `curl -s $GW/health` | `{"status":"ok"}` |
| 1.3 | `curl -s -H "Authorization: Bearer $KEY" $GW/v1/models` | JSON, в `data` есть `gpthub-auto` |
| 1.4 | `curl -s -o /dev/null -w "%{http_code}" http://127.0.0.1:3000/` | `200` |
| 1.5 | `sudo nginx -t` | `syntax is ok` |
| 1.6 | `grep -E '^GPTHUB_PUBLIC_BASE_URL=' .env` | Для публичного доступа к картинкам/PPTX — **внешний** URL или относительные пути за тем же origin; не обязательно менять, если открываете только с сервера |
| 1.7 | `grep GPTHUB_ROUTER_MODE .env` | По умолчанию в compose: **gena** |
| 1.8 | `df -h` / `docker system df` | Достаточно места |

Проверка памяти на диске (код: `MemoryStore` → файл **`/data/memory.sqlite`**, таблица **`memory_items`**, не `memory_facts`):

```bash
docker compose exec gpthub-gateway ls -la /data/
docker compose exec gpthub-gateway sqlite3 /data/memory.sqlite "SELECT COUNT(*) FROM memory_items;" 2>/dev/null || echo "БД ещё пуста или нет sqlite3 в образе"
```

## Шаг 2 — триггеры по коду (кратко)

- **Deep Research (перехват SSE):** `should_stream_deep_gena` — только при **`stream: true`**. При **`stream: false`** контекст всё равно добавляется через `deep_research_ddg` в `main.py`, если сработал `DEEP_RESEARCH_RE` (`web_tools.py`).
- **Веб-поиск:** `_WEB_SEARCH_TRIGGERS` в `web_tools.py` — фразы вроде «найди в интернет», «что нового», «последние новости».
- **Deep Research regex:** `DEEP_RESEARCH_RE` — «глубокое исследование», «deep research», «сделай ресерч/рисерч», «исследуй тему», …

## Шаг 3 — функциональные тесты (curl)

Используйте скрипт `scripts/verify-gpthub-stack.sh` или вручную POST на `$GW/v1/chat/completions` с `"model":"gpthub-auto"`, `"stream":false` для сценариев из [TZ_ACCEPTANCE_TRACKER.md](TZ_ACCEPTANCE_TRACKER.md).

**Тест J (ручная модель):** в ответе OpenAI может не дублироваться поле `model` — проверяйте отсутствие ошибки и осмысленный `content`.

**Тест I (ASR):** без WAV — пометьте «ручная проверка»; можно сгенерировать вход через TTS → MP3 → transcriptions (см. скрипт).

## Шаг 4 — типовые починки (без удаления томов)

- **401 MWS:** обновить `MWS_API_KEY`, `docker compose up -d --force-recreate gpthub-gateway`.
- **502 nginx:** `nginx -t`, `proxy_pass` на 127.0.0.1:3000 и :8081 для нужных `location`.
- **Картинки 404 с клиента:** выставить `GPTHUB_PUBLIC_BASE_URL` на URL, с которого пользователь открывает чат, или HTTPS домен.
- **Gateway unhealthy:** `docker compose logs gpthub-gateway --tail=100`, затем при необходимости recreate только gateway.

## Ограничения

- Не удалять тома `gpthub-data`, `open-webui-data`, `chroma-data`.
- Не менять `docker-compose.yml` без необходимости.
