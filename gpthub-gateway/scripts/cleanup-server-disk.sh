#!/usr/bin/env bash
set -euo pipefail

echo "== Disk before =="
df -h / || true

if command -v docker >/dev/null 2>&1; then
  if [[ "${DEPLOY_QUICK_CLEAN:-}" == "1" ]]; then
    echo "== docker quick clean =="
    timeout 120 docker builder prune -f || true
    timeout 180 docker system prune -f || true
    docker system df || true
  else
    echo "== docker build cache =="
    timeout 300 docker builder prune -af || true
    echo "== docker system prune =="
    timeout 600 docker system prune -af || true
    echo "== docker system df =="
    docker system df || true
  fi
fi

if command -v apt-get >/dev/null 2>&1; then
  echo "== apt clean =="
  apt-get clean || true
  apt-get autoremove -y || true
fi

if command -v journalctl >/dev/null 2>&1; then
  echo "== journal vacuum =="
  journalctl --vacuum-size=200M || true
fi

echo "== Disk after =="
df -h / || true
