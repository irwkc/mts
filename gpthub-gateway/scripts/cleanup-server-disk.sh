#!/usr/bin/env bash
# Безопасная очистка места на Linux-сервере (Docker, apt, журналы).
# Запускать на хосте с правами root или через sudo. Не храните секреты в скрипте.

set -euo pipefail

echo "== Disk before =="
df -h / || true

if command -v docker >/dev/null 2>&1; then
  echo "== docker system prune (образы/контейнеры неиспользуемые) =="
  docker system prune -af || true
fi

if command -v apt-get >/dev/null 2>&1; then
  echo "== apt clean =="
  apt-get clean || true
  apt-get autoremove -y || true
fi

if command -v journalctl >/dev/null 2>&1; then
  echo "== journal vacuum (оставить ~200M) =="
  journalctl --vacuum-size=200M || true
fi

echo "== Disk after =="
df -h / || true
