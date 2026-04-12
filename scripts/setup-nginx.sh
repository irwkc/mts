#!/usr/bin/env bash
# Устанавливает nginx и проксирует порт 80 → Open WebUI (Docker 127.0.0.1:3000).
# Запуск на сервере: sudo bash scripts/setup-nginx.sh
# Вызывается из корня репозитория ~/mts.

set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CONF_SRC="$ROOT/deploy/nginx-open-webui.conf"
CONF_DST="/etc/nginx/sites-available/mts"
MAP_SRC="$ROOT/deploy/nginx-websocket-map.conf"
MAP_DST="/etc/nginx/conf.d/mts-websocket-map.conf"

if [[ "${EUID:-0}" -ne 0 ]]; then
  echo "Нужен root: sudo bash $0" >&2
  exit 1
fi

if [[ ! -f "$CONF_SRC" ]]; then
  echo "Не найден $CONF_SRC" >&2
  exit 1
fi

export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get install -y -qq nginx

install -m 644 "$MAP_SRC" "$MAP_DST"

# Не затирать vhost, если уже настроен HTTPS (Certbot) — иначе пропадёт :443 и https://домен
if [[ -f "$CONF_DST" ]] && grep -qE 'listen[[:space:]]+.*443|managed by Certbot' "$CONF_DST" 2>/dev/null; then
  echo "Сохраняю $CONF_DST: найден HTTPS/Certbot. Обновлён только websocket map."
else
  install -m 644 "$CONF_SRC" "$CONF_DST"
  rm -f /etc/nginx/sites-enabled/default
  ln -sf "$CONF_DST" /etc/nginx/sites-enabled/mts
fi

# Патчим /static/ location в активный конфиг (работает и при HTTP, и при HTTPS/Certbot).
# GPTHub Gateway отдаёт PPTX-презентации через /static/ — этот location нужен всегда.
if ! grep -q 'location /static/' "$CONF_DST" 2>/dev/null; then
  python3 - "$CONF_DST" << 'PYEOF'
import re, sys

path = sys.argv[1]
content = open(path).read()

static_block = """\
    # GPTHub Gateway: статика (презентации PPTX, картинки)
    location /static/ {
        proxy_pass http://127.0.0.1:8081/static/;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_buffering off;
    }

"""

# Вставляем перед первым "location /" (но не "location = /login")
# Паттерн: начало location / блока (с пробелами)
patched = re.sub(
    r'([ \t]+location\s*/\s*\{)',
    static_block + r'\1',
    content,
    count=1,
)

if patched == content:
    print("WARN: не удалось найти 'location /' для вставки /static/", file=sys.stderr)
else:
    open(path, 'w').write(patched)
    print("✅ Добавлен location /static/ → gateway:8081")
PYEOF
  echo "Перезагружаем nginx с обновлённым /static/..."
else
  echo "/static/ уже есть в $CONF_DST"
fi

nginx -t
systemctl enable nginx
systemctl reload nginx

echo "Ожидание Open WebUI на 127.0.0.1:3000 (до ~3 мин после деплоя)..."
for i in $(seq 1 90); do
  if curl -sfS --connect-timeout 2 "http://127.0.0.1:3000/" -o /dev/null; then
    echo "Open WebUI отвечает (попытка $i)"
    systemctl reload nginx
    break
  fi
  sleep 2
done

echo "nginx настроен: http://$(curl -sS ifconfig.me 2>/dev/null || hostname -I | awk '{print $1}')/"
