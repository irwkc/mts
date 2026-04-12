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
