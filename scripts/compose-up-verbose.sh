#!/usr/bin/env bash
# Подробный запуск стека: видно pull слоёв и сборку шлюза.
#
# Open WebUI не «ставится» на сервер: в docker-compose это image: ghcr.io/... —
# Docker только скачивает готовый образ при pull.
# Собирается с нуля только сервис gpthub-gateway (./gpthub-gateway/Dockerfile).
#
# Использование (из корня репозитория):
#   bash scripts/compose-up-verbose.sh
# Лог в файл:
#   bash scripts/compose-up-verbose.sh 2>&1 | tee /tmp/mts-compose.log

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

log() { printf '[%s] %s\n' "$(date -Iseconds 2>/dev/null || date '+%Y-%m-%dT%H:%M:%S%z')" "$*"; }

if docker info >/dev/null 2>&1; then
  DC=(docker compose)
elif sudo docker info >/dev/null 2>&1; then
  DC=(sudo docker compose)
else
  log "Ошибка: Docker недоступен (нужны права на docker или sudo)."
  exit 1
fi

export DOCKER_BUILDKIT=1
export BUILDKIT_PROGRESS=plain
export DOCKER_CLI_HINTS=false

log "Каталог проекта: $ROOT"
log "Open WebUI — готовый образ из ghcr.io (pull), на хост Python/Open WebUI не устанавливаются."
log "gpthub-gateway — docker build из ./gpthub-gateway"
echo ""

log "=== 1/3 docker compose pull (скачивание слоёв Open WebUI и базовых образов; может быть долго) ==="
"${DC[@]}" pull
echo ""

log "=== 2/3 docker compose build —progress=plain (сборка только шлюза gpthub-gateway) ==="
"${DC[@]}" build --progress=plain
echo ""

log "=== 3/3 docker compose up -d ==="
"${DC[@]}" up -d --remove-orphans
echo ""

log "Контейнеры:"
"${DC[@]}" ps
echo ""

log "Проверка HTTP (если контейнеры ещё прогреваются — повторите через минуту):"
sleep 2
if curl -sfS --connect-timeout 3 http://127.0.0.1:8081/health >/dev/null; then
  log "gpthub-gateway GET /health — OK"
else
  log "gpthub-gateway GET /health — пока нет ответа"
fi
curl -sfS --connect-timeout 3 -o /dev/null -w "open-webui http://127.0.0.1:3000/ → HTTP %{http_code}\n" http://127.0.0.1:3000/ || log "open-webui :3000 — пока нет ответа"
log "Готово."
