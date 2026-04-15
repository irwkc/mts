#!/usr/bin/env bash
# Полный локальный стек с mock MWS: чат + STT + TTS (короткий MP3) без доступа к TTS в реальном MWS.
# Запуск из корня репозитория: bash scripts/up-mock-stack.sh
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

if ! docker info >/dev/null 2>&1; then
  echo "Запустите Docker Desktop и повторите."
  exit 1
fi

if [[ ! -f .env ]]; then
  cp .env.example .env
  echo "Создан .env из .env.example"
fi

# Для mock достаточно произвольного ключа; не затираем непустой реальный ключ без явного флага
if [[ "${MOCK_FORCE_KEY:-}" == "1" ]] || ! grep -q '^MWS_API_KEY=' .env || grep -q '^MWS_API_KEY=$' .env || grep -q '^MWS_API_KEY=sk-your-key-here' .env; then
  if grep -q '^MWS_API_KEY=' .env; then
    sed -i.bak 's/^MWS_API_KEY=.*/MWS_API_KEY=mock-local-key/' .env && rm -f .env.bak
  else
    echo 'MWS_API_KEY=mock-local-key' >> .env
  fi
  echo "MWS_API_KEY=mock-local-key (режим mock)"
fi

DC=(docker compose -f docker-compose.yml -f docker-compose.local-mock.yml)
echo "=== build + up (mock MWS) ==="
"${DC[@]}" up -d --build

echo "=== ждём шлюз ==="
for i in $(seq 1 120); do
  if curl -sf --max-time 5 http://127.0.0.1:8081/health >/dev/null 2>&1; then
    echo "gpthub-gateway OK"
    break
  fi
  if [[ "$i" -eq 120 ]]; then
    "${DC[@]}" logs gpthub-gateway --tail=60
    exit 1
  fi
  sleep 1
done

KEY=$(grep '^MWS_API_KEY=' .env | head -1 | cut -d= -f2- | tr -d '\r' | tr -d '"' | tr -d "'")
echo "=== TTS через шлюз ==="
TTS_OUT="$(mktemp -t gpthub-tts.XXXXXX.bin)"
HTTP_CODE=$(curl -sS -o "$TTS_OUT" -w "%{http_code}" --max-time 45 \
  -X POST http://127.0.0.1:8081/v1/audio/speech \
  -H "Authorization: Bearer $KEY" \
  -H "Content-Type: application/json" \
  -d '{"model":"tts-1","input":"Проверка озвучки.","voice":"alloy"}') || true
if [[ "$HTTP_CODE" == "200" ]] && [[ -s "$TTS_OUT" ]]; then
  echo "TTS OK: HTTP $HTTP_CODE, $(wc -c <"$TTS_OUT") байт, $(file -b "$TTS_OUT" | head -1)"
else
  echo "TTS FAIL: HTTP ${HTTP_CODE:-?}"
  head -c 500 "$TTS_OUT" 2>/dev/null || true
  echo
  rm -f "$TTS_OUT"
  exit 1
fi
rm -f "$TTS_OUT"

echo "=== Open WebUI: http://localhost:3000 (логин из WEBUI_ADMIN_* в .env) ==="
