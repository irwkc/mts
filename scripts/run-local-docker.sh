#!/usr/bin/env bash
# Локальный стек: Docker Compose (gpthub-gateway + open-webui + chroma).
# Запуск из корня репозитория: bash scripts/run-local-docker.sh
# Перед запуском: включите Docker Desktop; в .env задайте реальный MWS_API_KEY.

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

if ! docker info >/dev/null 2>&1; then
  echo "Docker daemon недоступен. Запустите Docker Desktop и повторите:"
  echo "  bash scripts/run-local-docker.sh"
  exit 1
fi

if [[ ! -f .env ]]; then
  cp .env.example .env
  echo "Создан .env из .env.example — укажите в нём MWS_API_KEY (реальный ключ)."
fi

# Локальные URL для ссылок на /static/ и редиректов WebUI
if ! grep -q '^GPTHUB_PUBLIC_BASE_URL=' .env; then
  echo 'GPTHUB_PUBLIC_BASE_URL=http://127.0.0.1:8081' >> .env
fi
if ! grep -q '^WEBUI_URL=' .env; then
  echo 'WEBUI_URL=http://localhost:3000' >> .env
fi

KEY=$(grep '^MWS_API_KEY=' .env | head -1 | sed 's/^MWS_API_KEY=//' | tr -d '\r' | tr -d '"' | tr -d "'")
if [[ -z "${KEY:-}" || "$KEY" == sk-your-key-here ]]; then
  echo "ВНИМАНИЕ: в .env нужен рабочий MWS_API_KEY (не плейсхолдер)."
  echo "Отредактируйте .env и снова: bash scripts/run-local-docker.sh"
  exit 1
fi

echo "=== docker compose build + up ==="
docker compose up -d --build

echo "=== ждём шлюз (до 180 с) ==="
for i in $(seq 1 180); do
  if curl -sf --max-time 5 http://127.0.0.1:8081/health >/dev/null 2>&1; then
    echo "gpthub-gateway OK"
    break
  fi
  if [[ "$i" -eq 180 ]]; then
    echo "Таймаут health. Логи:"
    docker compose logs gpthub-gateway --tail=80
    exit 1
  fi
  sleep 1
done

echo "=== ждём Open WebUI (до 240 с) ==="
for i in $(seq 1 240); do
  if curl -sf --max-time 5 http://127.0.0.1:3000/ >/dev/null 2>&1; then
    echo "open-webui OK"
    break
  fi
  if [[ "$i" -eq 240 ]]; then
    echo "Таймаут WebUI. Логи:"
    docker compose logs open-webui --tail=80
    exit 1
  fi
  sleep 1
done

echo "=== быстрый стриминг (curl -N, первые строки SSE) ==="
curl -sS -N --max-time 90 \
  -X POST http://127.0.0.1:8081/v1/chat/completions \
  -H "Authorization: Bearer $KEY" \
  -H "Content-Type: application/json" \
  -d '{"model":"gpthub-auto","stream":true,"max_tokens":32,"messages":[{"role":"user","content":"Say hi in one word."}]}' \
  | head -15

echo ""
echo "=== полная проверка (опционально) ==="
echo "  bash scripts/verify-gpthub-stack.sh"
echo ""
if python3 -c "import aiohttp" 2>/dev/null; then
  echo "=== aiohttp SSE (как в Open WebUI backend) ==="
  python3 scripts/verify-aiohttp-sse.py || true
else
  echo "Для проверки aiohttp: pip install aiohttp && python3 scripts/verify-aiohttp-sse.py"
fi

echo ""
echo "Откройте в браузере: http://localhost:3000"
echo "Логин по умолчанию из .env (WEBUI_ADMIN_*) или зарегистрируйтесь при ENABLE_SIGNUP=true."
