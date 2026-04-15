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

# Ждём /health (после OOM/restart шлюз поднимается не сразу).
wait_gateway() {
  local max="${1:-90}"
  local i=0
  while [[ $i -lt "$max" ]]; do
    if curl -sf --max-time 5 "$GW/health" >/dev/null 2>&1; then
      return 0
    fi
    i=$((i + 1))
    sleep 1
  done
  echo "FAIL: за ${max}s не отвечает $GW/health (контейнер gpthub-gateway не поднялся?)"
  docker compose ps 2>/dev/null || true
  return 1
}

curl_chat_hint() {
  echo "    (curl 52 «Empty reply» / 7 «Connection refused»: часто OOM или падение uvicorn;"
  echo "     смотрите: docker compose logs gpthub-gateway --tail=120; dmesg | tail | grep -i oom)"
}

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
wait_gateway 120 || exit 1

run_chat() {
  local name="$1"
  local body="$2"
  local maxt="${3:-90}"
  echo "--- $name ---"
  wait_gateway 30 || { echo "FAIL: шлюз недоступен перед запросом"; curl_chat_hint; return 0; }
  local resp curl_ec=0
  resp=$(curl -sS --max-time "$maxt" -X POST "$GW/v1/chat/completions" \
    -H "Authorization: Bearer $KEY" \
    -H "Content-Type: application/json" \
    -d "$body") || curl_ec=$?
  if [[ "$curl_ec" != "0" ]]; then
    echo "FAIL: curl exit=$curl_ec"
    curl_chat_hint
    wait_gateway 60 || true
    return 0
  fi
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
    curl_chat_hint
    wait_gateway 60 || true
  fi
}

# Короткий ответ: меньше нагрузка на логи/память при DEBUG.
run_chat "A текст (ТЗ1)" '{"model":"gpthub-auto","stream":false,"max_tokens":512,"messages":[{"role":"user","content":"В двух предложениях объясни HTTP-код 404."}]}' 120

run_chat "B картинка (ТЗ3)" '{"model":"gpthub-auto","stream":false,"max_tokens":256,"messages":[{"role":"user","content":"Нарисуй синий круг с буквой G, плоский стиль."}]}' 120

run_chat "C веб-поиск (ТЗ7)" '{"model":"gpthub-auto","stream":false,"max_tokens":512,"messages":[{"role":"user","content":"Найди в интернете: какая последняя стабильная версия Python? Дай цифру и источник."}]}' 90

run_chat "D URL (ТЗ8)" '{"model":"gpthub-auto","stream":false,"max_tokens":256,"messages":[{"role":"user","content":"Прочитай https://example.com и скажи что в заголовке страницы."}]}' 45

echo "--- E память (ТЗ9) два запроса ---"
wait_gateway 30 || true
if ! resp_e1=$(curl -sS --max-time 60 -X POST "$GW/v1/chat/completions" \
  -H "Authorization: Bearer $KEY" -H "Content-Type: application/json" \
  -d '{"model":"gpthub-auto","stream":false,"max_tokens":256,"messages":[{"role":"user","content":"Запомни: тестовый_ключ_проверки_памяти=ALPHA42"}]}'); then
  echo "save: FAIL (curl)"
  curl_chat_hint
else
  echo "$resp_e1" | python3 -c "import sys,json; r=json.load(sys.stdin); print('save:', (r.get('choices') or [{}])[0].get('message',{}).get('content','')[:120])" || echo "save: invalid JSON"
fi
sleep 2
wait_gateway 30 || true
if ! resp_e2=$(curl -sS --max-time 60 -X POST "$GW/v1/chat/completions" \
  -H "Authorization: Bearer $KEY" -H "Content-Type: application/json" \
  -d '{"model":"gpthub-auto","stream":false,"max_tokens":256,"messages":[{"role":"user","content":"Какое значение у тестового ключа тестовый_ключ_проверки_памяти?"}]}'); then
  echo "recall: FAIL (curl)"
  curl_chat_hint
else
  echo "$resp_e2" | python3 -c "import sys,json; r=json.load(sys.stdin); t=(r.get('choices') or [{}])[0].get('message',{}).get('content',''); print('recall OK' if 'ALPHA42' in t else 'recall FAIL', t[:200])" || echo "recall: invalid JSON"
fi

run_chat "F Deep Research (ТЗ13)" '{"model":"gpthub-auto","stream":false,"max_tokens":2048,"messages":[{"role":"user","content":"Сделай ресерч по теме: влияние температуры на LLM. Введение, 3 тезиса, вывод."}]}' 120

run_chat "G PPTX (ТЗ14)" '{"model":"gpthub-auto","stream":false,"max_tokens":256,"messages":[{"role":"user","content":"Сделай презентацию на 3 слайда про Python."}]}' 120

echo "--- H TTS (ТЗ15) ---"
wait_gateway 30 || true
curl -sS --max-time 60 -X POST "$GW/v1/audio/speech" \
  -H "Authorization: Bearer $KEY" \
  -H "Content-Type: application/json" \
  -d '{"model":"tts-1","input":"Привет, это тест.","voice":"alloy"}' \
  -o /tmp/gpthub_tts_test.mp3 && ls -lh /tmp/gpthub_tts_test.mp3 || echo "TTS FAIL"

echo "--- I ASR: TTS→MP3→transcribe (ТЗ2/4) ---"
if [[ -f /tmp/gpthub_tts_test.mp3 ]]; then
  wait_gateway 30 || true
  if ! resp_asr=$(curl -sS --max-time 90 -X POST "$GW/v1/audio/transcriptions" \
    -H "Authorization: Bearer $KEY" \
    -F "file=@/tmp/gpthub_tts_test.mp3;type=audio/mpeg" \
    -F "model=${ASR_MODEL:-whisper-medium}"); then
    echo "ASR FAIL (curl)"
    curl_chat_hint
  else
    echo "$resp_asr" | python3 -c "import sys,json; r=json.load(sys.stdin); print(r.get('text', r)[:300])" || echo "ASR invalid JSON"
  fi
else
  echo "пропуск: нет /tmp/gpthub_tts_test.mp3"
fi

echo "--- J ручная модель (ТЗ11) ---"
wait_gateway 30 || true
if ! models_j=$(curl -sSf --max-time 90 -H "Authorization: Bearer $KEY" "$GW/v1/models"); then
  echo "FAIL: models curl"
else
MANUAL=$(echo "$models_j" | python3 -c "import sys,json; d=json.load(sys.stdin); ids=[m['id'] for m in d.get('data',[]) if m['id']!='gpthub-auto']; print(ids[0] if ids else '')")
if [[ -z "$MANUAL" ]]; then
  echo "FAIL: нет моделей кроме gpthub-auto"
else
  echo "model=$MANUAL"
  if ! resp_j=$(curl -sS --max-time 60 -X POST "$GW/v1/chat/completions" \
    -H "Authorization: Bearer $KEY" \
    -H "Content-Type: application/json" \
    -d "{\"model\":\"$MANUAL\",\"stream\":false,\"max_tokens\":64,\"messages\":[{\"role\":\"user\",\"content\":\"Ответь одним словом: тест\"}]}"); then
    echo "FAIL curl"
    curl_chat_hint
  else
    echo "$resp_j" | python3 -c "import sys,json; r=json.load(sys.stdin); e=r.get('error'); print('FAIL', e) if e else print('OK', (r.get('choices') or [{}])[0].get('message',{}).get('content','')[:80])" || echo "invalid JSON"
  fi
fi
fi

echo ""
echo "=== Логи шлюза (последние 120 строк) ==="
docker compose logs gpthub-gateway --tail=120 2>/dev/null || echo "(логи недоступны)"

echo ""
echo "Готово."
