#!/usr/bin/env bash
# Однократное добавление базового контекста «Гены» в Chroma (user_id=default).
# Повторные запуски добавляют новые фрагменты (id по времени). Запускать с корня репозитория на сервере.

set -euo pipefail
cd "$(dirname "$0")/.."

sudo docker compose exec -T gpthub-gateway python3 -c "
from app.chroma_store import save_message
save_message(
    'default',
    'system',
    'Гена: ассистент BAOBAB. Шлюз gpthub-auto, маршрутизация gena: код, длинные документы, презентации, '
    'картинки, deep research; память Chroma и SQLite.',
)
print('gena chroma seed ok')
"
