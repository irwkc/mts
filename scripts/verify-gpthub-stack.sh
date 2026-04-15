#!/usr/bin/env bash
# Проверка стека GPTHub на сервере (docker compose + curl).
# Запуск: из корня репозитория: bash scripts/verify-gpthub-stack.sh
# Требуется: .env с MWS_API_KEY, поднятый compose.

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

GW="${GW:-http://127.0.0.1:8081}"
WEBUI="${WEBUI:-http://127.0.0.1:3000}"

if [[ ! -f .env ]]; then
  echo "FAIL: нет файла .env в $ROOT"
  exit 1
fi

# shellcheck disable=SC2046
KEY=$(grep '^MWS_API_KEY=' .env | head -1 | sed 's/^MWS_API_KEY=//' | tr -d '\r' | tr -d '"' | tr -d "'")
if [[ -z "${KEY:-}" ]]; then
  echo "FAIL: MWS_API_KEY пустой в .env"
  exit 1
fi

echo "=== Шаг 1: инфраструктура ==="
docker compose ps || true

echo -n "1.2 health: "
curl -sSf --max-time 15 "$GW/health" || { echo "FAIL"; exit 1; }
echo

echo -n "1.3 models (gpthub-auto): "
# Без --max-time curl может долго ждать большой каталог /v1/models (прокси к MWS).
if ! models_json=$(curl -sSf --max-time 90 -H "Authorization: Bearer $KEY" "$GW/v1/models"); then
  echo "FAIL (curl)"
else
  echo "$models_json" | python3 -c "import sys,json; d=json.load(sys.stdin); ids=[m['id'] for m in d.get('data',[])]; print('OK' if 'gpthub-auto' in ids else 'FAIL', ids[:8])"
fi

echo -n "1.4 open-webui HTTP: "
curl -sSf --max-time 15 -o /dev/null -w "%{http_code}\n" "$WEBUI/" || echo "FAIL"

if command -v nginx >/dev/null 2>&1; then
  echo -n "1.5 nginx -t: "
  sudo nginx -t 2>&1 | tail -1 || true
else
  echo "1.5 nginx: (не установлен на хосте — пропуск)"
fi

echo "1.6 GPTHUB / MWS (grep):"
grep -E '^MWS_API_BASE=|^GPTHUB_PUBLIC_BASE_URL=' .env || true

echo "1.8 df / docker system df:"
df -h / 2>/dev/null | head -2 || true
docker system df 2>/dev/null || true

echo ""
echo "=== Шаг 2: функциональные curl (stream=false) ==="

run_chat() {
  local name="$1"
  local body="$2"
  echo "--- $name ---"
  local resp
  resp=$(curl -sS --max-time "${3:-90}" -X POST "$GW/v1/chat/completions" \
    -H "Authorization: Bearer $KEY" \
    -H "Content-Type: application/json" \
    -d "$body") || true
  if echo "$resp" | python3 -c "import sys,json; json.load(sys.stdin)" 2>/dev/null; then
    echo "$resp" | python3 -c "
import sys, json
r = json.load(sys.stdin)
if r.get('error'):
    print('FAIL error:', r['error'])
else:
    c = (r.get('choices') or [{}])[0].get('message', {}).get('content', '')
    print('OK len(content)=', len(c))
    print(c[:400].replace('\n',' ') if c else '(empty)')
"
  else
    echo "FAIL: invalid JSON"
    echo "$resp" | head -c 500
    echo
  fi
}

run_chat "A текст (ТЗ1)" '{"model":"gpthub-auto","stream":false,"messages":[{"role":"user","content":"В двух предложениях объясни HTTP-код 404."}]}'

run_chat "B картинка (ТЗ3)" '{"model":"gpthub-auto","stream":false,"messages":[{"role":"user","content":"Нарисуй синий круг с буквой G, плоский стиль."}]}' 120

run_chat "C веб-поиск (ТЗ7)" '{"model":"gpthub-auto","stream":false,"messages":[{"role":"user","content":"Найди в интернете: какая последняя стабильная версия Python? Дай цифру и источник."}]}' 90

run_chat "D URL (ТЗ8)" '{"model":"gpthub-auto","stream":false,"messages":[{"role":"user","content":"Прочитай https://example.com и скажи что в заголовке страницы."}]}' 45

echo "--- E память (ТЗ9) два запроса ---"
curl -sS --max-time 60 -X POST "$GW/v1/chat/completions" \
  -H "Authorization: Bearer $KEY" -H "Content-Type: application/json" \
  -d '{"model":"gpthub-auto","stream":false,"messages":[{"role":"user","content":"Запомни: тестовый_ключ_проверки_памяти=ALPHA42"}]}' | python3 -c "import sys,json; r=json.load(sys.stdin); print('save:', (r.get('choices') or [{}])[0].get('message',{}).get('content','')[:120])"
sleep 2
curl -sS --max-time 60 -X POST "$GW/v1/chat/completions" \
  -H "Authorization: Bearer $KEY" -H "Content-Type: application/json" \
  -d '{"model":"gpthub-auto","stream":false,"messages":[{"role":"user","content":"Какое значение у тестового ключа тестовый_ключ_проверки_памяти?"}]}' | python3 -c "import sys,json; r=json.load(sys.stdin); t=(r.get('choices') or [{}])[0].get('message',{}).get('content',''); print('recall OK' if 'ALPHA42' in t else 'recall FAIL', t[:200])"

run_chat "F Deep Research (ТЗ13)" '{"model":"gpthub-auto","stream":false,"messages":[{"role":"user","content":"Сделай ресерч по теме: влияние температуры на LLM. Введение, 3 тезиса, вывод."}]}' 120

run_chat "G PPTX (ТЗ14)" '{"model":"gpthub-auto","stream":false,"messages":[{"role":"user","content":"Сделай презентацию на 3 слайда про Python."}]}' 120

echo "--- H TTS (ТЗ15) ---"
curl -sS --max-time 60 -X POST "$GW/v1/audio/speech" \
  -H "Authorization: Bearer $KEY" \
  -H "Content-Type: application/json" \
  -d '{"model":"tts-1","input":"Привет, это тест.","voice":"alloy"}' \
  -o /tmp/gpthub_tts_test.mp3 && ls -lh /tmp/gpthub_tts_test.mp3 || echo "TTS FAIL"

echo "--- I ASR: TTS→MP3→transcribe (ТЗ2/4) ---"
if [[ -f /tmp/gpthub_tts_test.mp3 ]]; then
  curl -sS --max-time 90 -X POST "$GW/v1/audio/transcriptions" \
    -H "Authorization: Bearer $KEY" \
    -F "file=@/tmp/gpthub_tts_test.mp3;type=audio/mpeg" \
    -F "model=${ASR_MODEL:-whisper-medium}" | python3 -c "import sys,json; r=json.load(sys.stdin); print(r.get('text', r)[:300])" || echo "ASR FAIL"
else
  echo "пропуск: нет /tmp/gpthub_tts_test.mp3"
fi

echo "--- J ручная модель (ТЗ11) ---"
MANUAL=$(curl -sSf --max-time 90 -H "Authorization: Bearer $KEY" "$GW/v1/models" | python3 -c "import sys,json; d=json.load(sys.stdin); ids=[m['id'] for m in d.get('data',[]) if m['id']!='gpthub-auto']; print(ids[0] if ids else '')")
if [[ -z "$MANUAL" ]]; then
  echo "FAIL: нет моделей кроме gpthub-auto"
else
  echo "model=$MANUAL"
  curl -sS --max-time 60 -X POST "$GW/v1/chat/completions" \
    -H "Authorization: Bearer $KEY" \
    -H "Content-Type: application/json" \
    -d "{\"model\":\"$MANUAL\",\"stream\":false,\"messages\":[{\"role\":\"user\",\"content\":\"Ответь одним словом: тест\"}]}" \
    | python3 -c "import sys,json; r=json.load(sys.stdin); e=r.get('error'); print('FAIL', e) if e else print('OK', (r.get('choices') or [{}])[0].get('message',{}).get('content','')[:80])"
fi

echo ""
echo "=== Логи шлюза (последние 80 строк, ошибки) ==="
docker compose logs gpthub-gateway --tail=80 2>/dev/null | grep -E "ERROR|CRITICAL|Traceback|401|502|503" || echo "(нет совпадений или сервис не найден)"

echo "Готово."
