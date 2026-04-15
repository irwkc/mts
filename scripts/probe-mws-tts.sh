#!/usr/bin/env bash
# Проверка TTS на реальном MWS: перебирает id из GET /v1/models (первые N) и ищет 200 на /v1/audio/speech.
# Нужен рабочий MWS_API_KEY в .env. Запуск: bash scripts/probe-mws-tts.sh
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
set -a
# shellcheck source=/dev/null
[[ -f .env ]] && source .env
set +a
BASE="${MWS_API_BASE:-https://api.gpt.mws.ru/v1}"
KEY="${MWS_API_KEY:?Задайте MWS_API_KEY в .env}"

IDS=$(curl -sS --max-time 60 "${BASE%/}/models" -H "Authorization: Bearer $KEY" | python3 -c "
import json,sys
j=json.load(sys.stdin)
for m in j.get('data',[])[:80]:
    print(m.get('id',''))
" 2>/dev/null || true)

if [[ -z "$IDS" ]]; then
  echo "Не удалось получить список моделей (проверьте ключ и MWS_API_BASE)."
  exit 1
fi

echo "Пробую POST .../audio/speech для id из каталога (до 80 шт.)…"
while IFS= read -r mid; do
  [[ -z "$mid" ]] && continue
  CODE=$(curl -sS -o /tmp/mws-tts-probe.bin -w "%{http_code}" --max-time 90 \
    -X POST "${BASE%/}/audio/speech" \
    -H "Authorization: Bearer $KEY" \
    -H "Content-Type: application/json" \
    -d "{\"model\":\"${mid}\",\"input\":\"тест\",\"voice\":\"alloy\"}" || echo "000")
  if [[ "$CODE" == "200" ]]; then
    echo "OK model=$mid bytes=$(wc -c </tmp/mws-tts-probe.bin) type=$(file -b /tmp/mws-tts-probe.bin | head -1)"
    echo "Добавьте в .env: AUDIO_TTS_MODEL=$mid  (и при необходимости GPTHUB_TTS_MODEL=$mid)"
    exit 0
  fi
done <<< "$IDS"

echo "Ни одна из проверенных моделей не дала HTTP 200 на /audio/speech."
echo "Нужен доступ к TTS в кабинете MWS или отдельный id из документации провайдера."
exit 1
