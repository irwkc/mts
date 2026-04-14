#!/usr/bin/env bash
# Проверка поднятого docker-compose: шлюз, при желании MWS /v1/models, Open WebUI.
# Использование (из корня репозитория):
#   set -a && source .env && set +a
#   bash scripts/verify-integration.sh
#
# На ARM Mac с образами только amd64 сначала:
#   bash scripts/compose-up-arm64-images.sh

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

GATEWAY="${GATEWAY_URL:-http://127.0.0.1:8081}"
WEBUI="${WEBUI_URL:-http://127.0.0.1:3000}"

fail=0

echo "=== 1. Шлюз GET $GATEWAY/health ==="
if out=$(curl -sS --connect-timeout 5 "$GATEWAY/health"); then
  echo "$out"
  echo "$out" | grep -q '"status".*"ok"' || fail=1
else
  echo "FAIL: нет ответа от шлюза"
  fail=1
fi

echo ""
echo "=== 2. GET $GATEWAY/v1/models (нужен MWS_API_KEY в окружении) ==="
if [ -z "${MWS_API_KEY:-}" ]; then
  echo "SKIP: MWS_API_KEY не задан (export или source .env)"
else
  code=$(curl -sS -o /tmp/gpthub-models.json -w '%{http_code}' \
    -H "Authorization: Bearer $MWS_API_KEY" \
    -H "Content-Type: application/json" \
    "$GATEWAY/v1/models" || true)
  echo "HTTP $code"
  if [ "$code" = "200" ]; then
    python3 - <<'PY' 2>/dev/null || head -c 400 /tmp/gpthub-models.json
import json,sys
d=json.load(open("/tmp/gpthub-models.json"))
data=d.get("data") or []
print("models:", len(data), "| sample ids:", [x.get("id") for x in data[:5]])
PY
  elif [ "$code" = "502" ]; then
    echo "Ожидаемо при неверном/просроченном ключе: шлюз проксирует ошибку MWS."
    head -c 300 /tmp/gpthub-models.json 2>/dev/null || true
    echo ""
  else
    echo "Неожиданный код"
    fail=1
  fi
fi

echo ""
echo "=== 3. Open WebUI GET $WEBUI/ ==="
code=$(curl -sS -o /dev/null -w '%{http_code}' --connect-timeout 5 --max-time 15 "$WEBUI/" || echo "000")
echo "HTTP $code"
if [ "$code" != "200" ] && [ "$code" != "302" ] && [ "$code" != "301" ]; then
  echo "Примечание: при первом старте контейнер долго качает зависимости (HF и т.д.); под QEMU/amd64 на Apple Silicon это может занять много минут."
  echo "Смотрите: docker logs -f <имя-контейнера-open-webui>"
  [ "$code" = "000" ] && fail=1
fi

echo ""
if [ "$fail" -eq 0 ]; then
  echo "verify-integration: базовые проверки пройдены (WebUI см. выше)."
  exit 0
else
  echo "verify-integration: есть ошибки (шлюз или сеть)."
  exit 1
fi
