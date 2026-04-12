# Шаблон фич — соответствие ТЗ (текстовая копия для сдачи)

Заполните одноимённый файл **GPTHub шаблон фич.xlsx** теми же формулировками или скопируйте колонки отсюда.

| № | Функционал | Сделано | Как и через что |
|---|------------|---------|-------------------|
| 1 | Текстовый чат | **Да** | `POST /v1/chat/completions` через шлюз → MWS GPT; модель из роутера (`gpthub-auto`) или вручную. |
| 2 | Голосовой чат | **Да** | Аудио в сообщении → `POST /v1/audio/transcriptions` (Whisper в MWS) → текст в тот же тред → LLM. STT настроен в compose (`AUDIO_STT_ENGINE=openai`). |
| 3 | Генерация изображений в чате | **Да** | Ключевые фразы «нарисуй», «сгенерируй» → `stream_image_markdown` → `POST /v1/images/generations` (`qwen-image`). Промпт улучшается через LLM перед генерацией. |
| 4 | Аудиофайлы + авто ASR | **Да** | Вложение аудио → транскрипция Whisper (`whisper-medium`) → дальше обычный чат. Прокси через `/v1/audio/transcriptions`. |
| 5 | Изображения (VLM) | **Да** | `image_url` / картинка в сообщении → `pick_route_gena` выбирает `VISION_MODEL` (`gpt-4o`) из каталога `/v1/models`. |
| 6 | Файлы и ответы по содержимому | **Да** | RAG: чанки, `POST /v1/embeddings` с `bge-m3`, SQLite в volume `/data/rag.sqlite` → контекст в chat completions. Поддержка PDF через `pypdf`. |
| 7 | Поиск в интернете | **Да** | DuckDuckGo (`duckduckgo-search`) → результаты в system → ответ LLM через MWS. Триггеры: «найди», «что нового», «актуальные», «погугли» и др. |
| 8 | Веб-парсинг по ссылке | **Да** | `trafilatura` по URL из текста → фрагмент до 12 000 символов в контекст → LLM. Авто-извлечение URL regex. |
| 9 | Долгосрочная память | **Да** | SQLite + эмбеддинги `bge-m3` (`memory_store.py`), LLM-digest фактов после ответа, ChromaDB для semantic recall (`chroma_store.py`). «Запомни: …» обрабатывается явно. |
| 10 | Автовыбор модели | **Да** | `gpthub-auto` → `pick_route_gena`: перехваты (презентация, картинка, deep research) + эвристики (длинный текст → `cotype-pro-vl-32b`, код → `qwen3-coder-480b-a35b`, чат → `DEFAULT_LLM`). Префикс `provider/model` нормализуется. |
| 11 | Ручной выбор модели | **Да** | Любой id из `/v1/models` кроме авто — шлюз не подменяет `model` (`apply_manual_route`). |
| 12 | Markdown и код | **Да** | Рендер Open WebUI (подсветка синтаксиса, таблицы, изображения inline). |
| 13 | Deep Research (доп.) | **Да** | `stream_deep_research`: 3 запроса DDG + парсинг страниц + синтез LLM (`gena_long_doc_model`) в стриминге. Триггеры: «глубокое исследование», «deep research», «сделай ресерч» и др. |
| 14 | Презентации PPTX (доп.) | **Да** | `stream_presentation_pptx`: структура слайдов через LLM (JSON) → `python-pptx` → скачиваемый файл по `/static/presentations/*.pptx`. Триггеры: «презентация», «слайды». |
| 15 | TTS (голос ответа) | **Да** | `POST /v1/audio/speech` → прокси на MWS TTS; настроен в compose (`AUDIO_TTS_ENGINE=openai`). |
