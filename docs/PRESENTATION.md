# Презентация GPTHub (структура слайдов)

Используйте как основу для PPTX/PDF или [Marp](https://marp.app/).

## 1. Проблема
- Разрозненные интерфейсы и модели; нужен единый чат с умным выбором модели и памятью под корпоративный контур MWS GPT.

## 2. Решение
- **Open WebUI** как UI, **GPTHub Gateway** (FastAPI) как единая точка входа к **MWS GPT** (`https://api.gpt.mws.ru/v1`).
- Все вызовы LLM только через совместимый OpenAI API и выданный ключ.

## 3. Архитектура (один абзац)
- Браузер → nginx (опционально) → Open WebUI → шлюз `/v1/*` → MWS; память и RAG в SQLite на volume; веб-поиск и URL — инструменты Python в шлюзе, синтез ответа делает LLM MWS.

## 4. Режимы модели
- **`gpthub-auto`** — детерминированный роутер (текст / картинка / поиск / ссылка / картинка по промпту).
- Любая другая модель из каталога — ручной режим без подмены.

## 5. Обязательные сценарии ТЗ
- Мультимодальность (текст, картинка, аудио, картинки по запросу).
- Ручной и автоматический выбор модели.
- Долговременная память (эмбеддинги bge-m3).

## 6. Запуск и сдача
- `docker compose up -d`, ключ в `.env`; репозиторий, архитектура в `docs/ARCHITECTURE.md`, сценарий демо в `docs/DEMO_SCRIPT.md`, чеклист фич в `docs/FEATURES_CHECKLIST.md`.

## 7. Продуктовая ценность
- Один привычный чат, прозрачный маршрут к моделям MWS, воспроизводимый деплой (Docker + optional GitHub Actions).

## 8. Редактор деки (Kimi-style, основа)
После генерации презентации шлюз сохраняет `static/presentations/<stem>.json` рядом с `.pptx`.
- **UI:** `/presentation/editor/?stem=presentation_xxxxxxxxxx` (статика шлюза; за nginx проксируйте `location /presentation/`).
- **API:** `GET/PUT /presentation/api/deck/{stem}`, `POST /presentation/api/deck/{stem}/rebuild` — пересборка PPTX с новыми картинками через `resolve_slide_images`.
- В чате есть ссылки «Скачать», «Редактор», «Предпросмотр».

## 9. Структурированный стрим (delta.gena) и Open WebUI
В SSE каждого чанка совместимого с OpenAI допускается поле **`choices[0].delta.gena`** — JSON-события презентации (`presentation_start`, `phase`, `deck_structure`, `slide_image`, `presentation_complete`, `error`). Текст для чата по-прежнему в **`delta.content`**.
Образ **open-webui-baobab** подключает **`gena-openwebui.js`**: перехват `fetch` на streaming `chat/completions`, парсинг `delta.gena` и док-панель справа (фазы, превью картинок по слайдам, ссылки после готовности).
