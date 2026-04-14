# Матрица: пункты ТЗ ↔ автотесты шлюза

Автотесты живут в `gpthub-gateway/tests/` (pytest). Они проверяют **логику gpthub-gateway** (роутинг, триггеры, SSE-патчи, наличие маршрутов), а не полный E2E с реальным MWS и браузером.

## Как запускать

```bash
cd gpthub-gateway
python -m pip install -r requirements.txt -r requirements-dev.txt
python -m pytest tests/ -q
```

CI: инструкция и готовый YAML — [CI.md](CI.md) (файл в репозитории: `.github/workflows/gpthub-pytest.yml`; при отказе push см. раздел в CI.md).

## Соответствие ТЗ 1–15

| ТЗ | Функционал | Тест(ы) | Что проверяется |
|----|------------|---------|-----------------|
| 1 | Текстовой чат | `test_tz01_simple_chat_fast_path` | Быстрый путь на `DEFAULT_LLM` для короткого текста |
| 2 | Голосовой чат | `test_tz02_audio_message_routes_to_llm_branch` | Сообщение с `input_audio` → ветка `audio` |
| 3 | Генерация изображений в чате | `test_tz03_image_generation_intent` | Триггер `image_gen` по тексту |
| 4 | Аудиофайлы + ASR | `test_tz04_transcriptions_route_registered` | Есть `POST /v1/audio/transcriptions` |
| 5 | VLM | `test_tz05_vision_route` | Картинка в сообщении → vision-модель |
| 6 | Файлы / RAG | `test_tz06_embeddable_blob_from_long_user_text` | Длинный текст ≥800 символов → кандидат в RAG |
| 7 | Поиск в интернете | `test_tz07_web_search_trigger` + `test_tz_triggers_web_tools` | Триггер веб-поиска |
| 8 | Веб по ссылке | `test_tz08_extract_url_from_message` + `test_tz_url_parsing_trigger` | Извлечение URL |
| 9 | Долгосрочная память | `test_tz09_explicit_remember_extracted` | Парсинг «Запомни: …» |
| 10 | Автовыбор модели | `test_tz10_*`, `test_try_fast_path_never_picks_embedding_catalog`, `test_pick_route_gena_*` | gena-роутер, не bge-m3 для чата |
| 11 | Ручной выбор модели | `test_tz11_manual_route_*`, `test_pick_route_manual` | `apply_manual_route`, fallback |
| 12 | Markdown / код | `test_tz12_stream_patch_*`, `test_sse_patch_*` | SSE `delta.content` и fallback reasoning/message |
| 13 | Deep Research | `test_tz13_deep_research_trigger` + `test_tz_triggers_web_tools` | Триггеры deep research |
| 14 | Презентации | `test_tz14_presentation_keyword` + `test_tz_presentation_and_image_regex` | Regex презентации |
| 15 | Доп. (TTS, MP3) | `test_tz15_tts_route_exists`, `test_tz15_music_demo_intent`, `test_music_intent_*` | Маршрут TTS, интент музыки |

Дополнительно: `test_tz_checklist_routes_exist` (все нужные `/v1/*`), `test_models_merge_inserts_gpthub_auto`, инфраструктура в `test_log_sanitize.py`.

## Что автотесты **не** заменяют

- Реальный ответ LLM от MWS (`MWS_API_KEY`, доступные id моделей).
- Open WebUI (рендер Markdown, микрофон, кнопки TTS).
- Nginx / HTTPS / `GPTHUB_PUBLIC_BASE_URL` для картинок.

Их покрывают [TZ_ACCEPTANCE_TRACKER.md](TZ_ACCEPTANCE_TRACKER.md) и ручные сценарии [QA_CHECKLIST.md](QA_CHECKLIST.md).

## Журнал прогонов (обновлять при релизе)

| Дата | Ветка / коммит | `pytest tests/` | Замечания |
|------|----------------|-----------------|-----------|
| 2026-04-15 | main | 49 passed | Добавлены `test_tz_matrix.py`, CI gpthub-pytest; до этого без `requirements.txt` в окружении падала сборка на `trafilatura` |
