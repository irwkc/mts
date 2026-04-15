#!/usr/bin/env bash
# Стек на реальный MWS (без mock-mws).
# В .env: MWS_API_KEY (боевой ключ), при необходимости MWS_API_BASE.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

if ! docker info >/dev/null 2>&1; then
  echo "Запустите Docker Desktop."
  exit 1
fi

MOCK=(docker compose -f docker-compose.yml -f docker-compose.local-mock.yml)
REAL=(docker compose -f docker-compose.yml)

echo "=== down (mock + real профили) ==="
"${MOCK[@]}" down --remove-orphans 2>/dev/null || true
"${REAL[@]}" down --remove-orphans 2>/dev/null || true

echo "=== up только docker-compose.yml ==="
"${REAL[@]}" up -d

echo "=== ждём шлюз ==="
for i in $(seq 1 90); do
  if curl -sf --max-time 5 http://127.0.0.1:8081/health >/dev/null 2>&1; then
    echo "gpthub-gateway OK"
    break
  fi
  if [[ "$i" -eq 90 ]]; then
    "${REAL[@]}" logs gpthub-gateway --tail=50
    exit 1
  fi
  sleep 1
done

echo "Open WebUI: http://localhost:3000"
