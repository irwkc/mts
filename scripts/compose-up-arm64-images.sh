#!/usr/bin/env bash
# Поднять стек на ARM Mac: тянем amd64-образы с GHCR и запускаем без локальной сборки (она часто падает по RAM на vite build).
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

DC=(docker-compose -f docker-compose.yml -f docker-compose.platform-amd64.yml)
export DOCKER_DEFAULT_PLATFORM="${DOCKER_DEFAULT_PLATFORM:-linux/amd64}"

echo "=== pull (linux/amd64) ==="
"${DC[@]}" pull gpthub-gateway open-webui chroma

echo "=== up -d --no-build ==="
"${DC[@]}" up -d --no-build --remove-orphans

echo "=== ps ==="
"${DC[@]}" ps

echo ""
echo "Проверка: curl -sS http://127.0.0.1:8081/health"
curl -sS --connect-timeout 5 http://127.0.0.1:8081/health || echo "(шлюз ещё не поднялся — подождите healthcheck)"
