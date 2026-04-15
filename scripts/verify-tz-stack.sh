#!/usr/bin/env bash
# Быстрая проверка стека по docs/TZ_GPTHUB.md (без UI).
# Запуск из корня репозитория. Нужен .env с MWS_API_KEY.

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

GW="${GW:-http://127.0.0.1:8081}"

if [[ ! -f .env ]]; then
  echo "FAIL: нет .env"
  exit 1
fi

# shellcheck disable=SC2046
KEY=$(grep '^MWS_API_KEY=' .env | head -1 | sed 's/^MWS_API_KEY=//' | tr -d '\r' | tr -d '"' | tr -d "'")
if [[ -z "${KEY:-}" ]]; then
  echo "FAIL: MWS_API_KEY пустой"
  exit 1
fi

echo "=== 1. health ==="
curl -sf --max-time 15 "$GW/health" | python3 -m json.tool

echo "=== 2. models (gpthub-auto) ==="
curl -sf --max-time 90 -H "Authorization: Bearer $KEY" "$GW/v1/models" \
  | python3 -c "import sys,json; d=json.load(sys.stdin); ids=[m['id'] for m in d.get('data',[])]; assert 'gpthub-auto' in ids, ids; print('OK', len(ids), 'models')"

echo "=== 3. chat non-stream ==="
curl -sf --max-time 120 -X POST "$GW/v1/chat/completions" \
  -H "Authorization: Bearer $KEY" \
  -H "Content-Type: application/json" \
  -d '{"model":"gpthub-auto","stream":false,"max_tokens":64,"messages":[{"role":"user","content":"Ответь одним словом: тест"}]}' \
  | python3 -c "import sys,json; r=json.load(sys.stdin); assert not r.get('error'); c=(r.get('choices')or[{}])[0].get('message',{}).get('content',''); print('OK', len(c), c[:80])"

echo "=== 4. chat stream (первые байты SSE) ==="
curl -sS --max-time 90 -X POST "$GW/v1/chat/completions" \
  -H "Authorization: Bearer $KEY" \
  -H "Content-Type: application/json" \
  -d '{"model":"gpthub-auto","stream":true,"max_tokens":32,"messages":[{"role":"user","content":"Hi"}]}' \
  | head -c 400
echo
echo "=== Готово ==="
echo "Голосовой режим: в UI откройте http://localhost:3000 → Voice mode (иконка звонка)."
echo "Нужны микрофон, одна модель, STT/TTS OpenAI в настройках (задаётся compose)."
