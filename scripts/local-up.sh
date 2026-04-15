#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

[[ -f .env ]] || cp .env.example .env
if ! grep -q '^GPTHUB_PUBLIC_BASE_URL=' .env 2>/dev/null; then
  echo 'GPTHUB_PUBLIC_BASE_URL=http://127.0.0.1:8081' >> .env
fi

has_key=0
if [[ -n "${MWS_API_KEY:-}" && "${MWS_API_KEY}" != "sk-your-key-here" ]]; then
  has_key=1
else
  v="$(grep '^MWS_API_KEY=' .env 2>/dev/null | head -1 | cut -d= -f2- || true)"
  if [[ -n "${v}" && "${v}" != "sk-your-key-here" ]]; then
    has_key=1
  fi
fi

if [[ "${has_key}" -eq 0 ]]; then
  echo "Set MWS_API_KEY in .env or: MWS_API_KEY=sk-... bash scripts/local-up.sh" >&2
  exit 1
fi

if docker compose version >/dev/null 2>&1; then
  exec docker compose up -d
fi
if command -v docker-compose >/dev/null 2>&1; then
  exec docker-compose up -d
fi
echo "Need Docker Compose: install Docker Desktop / plugin, or docker-compose" >&2
exit 1
