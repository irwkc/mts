# 🚀 MWS AI Workspace

Единый AI-чат на базе Open WebUI с умным роутингом между моделями, 
долгосрочной памятью и веб-инструментами.

## Что умеет

- Автоматически выбирает нужную модель под задачу
- Помнит пользователя между сессиями (RAG)
- Читает содержимое ссылок
- Ищет информацию в интернете

## Быстрый старт

### 1. Клонируй репозиторий
git clone https://github.com/your-team/mws-ai-workspace
cd mws-ai-workspace

### 2. Создай .env файл
cp .env.example .env

Открой .env и вставь ключ:
MWS_API_KEY=sk-ewgiaPC3A6pPDYHwR8siVA

### 3. Запусти
docker-compose up --build

### 4. Открой браузер
http://localhost:3000

Всё готово.

## Архитектура

Браузер → Open WebUI (3000) → Роутер (8001) → MWS GPT API
                                     ↕
                               ChromaDB (8000)

## Модели

| Модель              | Когда используется                  |
|---------------------|-------------------------------------|
| mws-gpt-alpha       | Обычные вопросы и диалог            |
| kodify-2.0          | Код, функции, технические вопросы   |
| cotype-preview-32k  | Длинные документы и файлы           |
| bge-m3              | Память пользователя (embeddings)    |

## Структура проекта

mws-ai-workspace/
├── router/
│   ├── router.py       # FastAPI роутер
│   ├── memory.py       # RAG память (ChromaDB)
│   ├── tools.py        # Веб-поиск и парсинг ссылок
│   └── requirements.txt
├── docker-compose.yml
├── .env.example
└── README.md

## Требования

- Docker
- docker-compose

Больше ничего устанавливать не нужно.