#!/usr/bin/env bash
# Локальный запуск стека одной командой из корня репозитория:
#   bash scripts/local-up.sh
# или (после chmod +x):
#   ./local-up.sh
#
# Требования: Docker + Docker Compose v2, в PATH — docker.
# Первый запрос: скопирует .env.example → .env и попросит задать MWS_API_KEY, если в .env ещё заглушка.
# Ключ можно передать в окружении без правки файла:
#   MWS_API_KEY=sk-... bash scripts/local-up.sh

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

if [[ ! -f .env ]]; then
  echo "==> Создаю .env из .env.example"
  cp .env.example .env
fi

# Картинки/PPTX в чате на localhost: абсолютный URL к шлюзу (если ещё не задано)
if ! grep -q '^GPTHUB_PUBLIC_BASE_URL=' .env 2>/dev/null; then
  echo "GPTHUB_PUBLIC_BASE_URL=http://127.0.0.1:8081" >> .env
  echo "==> Добавлен GPTHUB_PUBLIC_BASE_URL=http://127.0.0.1:8081 (ссылки на /static/ в чате)"
fi

_key_ok=0
if [[ -n "${MWS_API_KEY:-}" ]] && [[ "${MWS_API_KEY}" != "sk-your-key-here" ]]; then
  _key_ok=1
fi
if [[ "${_key_ok}" -eq 0 ]] && grep -qE '^MWS_API_KEY=.+$' .env 2>/dev/null; then
  _line="$(grep '^MWS_API_KEY=' .env | head -1)"
  _val="${_line#MWS_API_KEY=}"
  if [[ -n "${_val}" && "${_val}" != "sk-your-key-here" ]]; then
    _key_ok=1
  fi
fi

if [[ "${_key_ok}" -eq 0 ]]; then
  echo "" >&2
  echo "Задайте ключ MWS GPT в .env (строка MWS_API_KEY=...) или в окружении:" >&2
  echo "  MWS_API_KEY=sk-... bash scripts/local-up.sh" >&2
  echo "" >&2
  exit 1
fi

echo "==> docker compose up -d --build"
exec docker compose up -d --build
