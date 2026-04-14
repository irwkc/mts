# Модели для ключа с ограниченным каталогом MWS

У части ключей (например «команда») список `GET /v1/models` **не включает** модели вроде `mts-anya`. Если в `.env` или дефолтах шлюза указана недоступная модель, запросы к MWS возвращают **401/404**, а короткий чат через **`gpthub-auto`** может уходить в несовместимую или недоступную модель и давать **500**.

Репозиторий по умолчанию использует идентификаторы из **типичного разрешённого набора**: `llama-3.1-8b-instruct`, `cotype-pro-vl-32b`, `qwen3-coder-480b-a35b`, `qwen-image` и т.д. Подставьте **точные id из ответа вашего ключа**.

## Таблица переменных

| Переменная | Роль | Дефолт в compose / `config.py` |
|------------|------|----------------------------------|
| `DEFAULT_LLM` | Общий текстовый чат, база для роутера | `llama-3.1-8b-instruct` |
| `VISION_MODEL` | Сообщения с картинками, длинные тексты (gena) | `cotype-pro-vl-32b` |
| `GPTHUB_GENA_CHAT_MODEL` | Ветка «обычный чат» в gena | `llama-3.1-8b-instruct` |
| `GPTHUB_MEMORY_DIGEST_MODEL` | Извлечение фактов в память (LLM digest) | `llama-3.1-8b-instruct` |
| `GPTHUB_GENA_CODE_MODEL` | Код | `qwen3-coder-480b-a35b` |
| `GPTHUB_GENA_LONG_DOC_MODEL` | Длинные документы | `cotype-pro-vl-32b` |
| `IMAGE_GEN_MODEL` | Генерация картинок | `qwen-image` |

Полный список см. [.env.example](../.env.example) и [MODELS.md](MODELS.md).

## Проверки с хоста

Подставьте свой ключ и при необходимости URL шлюза (по умолчанию в compose проброс **8081**).

**Список моделей у провайдера (напрямую MWS):**

```bash
curl -sS -H "Authorization: Bearer $MWS_API_KEY" \
  "https://api.gpt.mws.ru/v1/models" | head -c 4000
```

**Список моделей через шлюз (должен отражать каталог ключа):**

```bash
curl -sS -H "Authorization: Bearer $MWS_API_KEY" \
  "http://127.0.0.1:8081/v1/models" | head -c 4000
```

**Минимальный чат (проверка, что `DEFAULT_LLM` существует для ключа):**

```bash
curl -sS "http://127.0.0.1:8081/v1/chat/completions" \
  -H "Authorization: Bearer $MWS_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"model":"llama-3.1-8b-instruct","messages":[{"role":"user","content":"ping"}],"max_tokens":16}'
```

Если в ответе ошибка про модель — замените `model` на id из вашего `GET /v1/models`.

## Чеклист для разработчика

1. Скопировать `.env.example` → `.env`, задать `MWS_API_KEY`.
2. Выполнить `GET /v1/models` для ключа и **записать** доступные id текстовой, vision и code-моделей.
3. В `.env` выставить `DEFAULT_LLM`, `VISION_MODEL`, `GPTHUB_GENA_CHAT_MODEL`, `GPTHUB_MEMORY_DIGEST_MODEL` **только из этого списка**.
4. Поднять стек: `docker compose up -d --build`, дождаться `healthy` у `gpthub-gateway`.
5. Проверить `curl` на `/v1/models` через шлюз и короткий `chat/completions`.
6. В Open WebUI выбрать **`gpthub-auto`** и отправить короткое сообщение — не должно быть 500 из-за недоступной модели по умолчанию.

Подробнее о сценариях: [ARCHITECTURE.md](ARCHITECTURE.md).
