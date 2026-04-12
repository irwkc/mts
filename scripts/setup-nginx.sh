#!/usr/bin/env bash
# Устанавливает nginx и проксирует порт 80 → Open WebUI (Docker 127.0.0.1:3000).
# Запуск на сервере: sudo bash scripts/setup-nginx.sh
# Вызывается из корня репозитория ~/mts.

set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CONF_SRC="$ROOT/deploy/nginx-open-webui.conf"
CONF_DST="/etc/nginx/sites-available/mts"

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

install -m 644 "$CONF_SRC" "$CONF_DST"
rm -f /etc/nginx/sites-enabled/default
ln -sf "$CONF_DST" /etc/nginx/sites-enabled/mts

nginx -t
systemctl enable nginx
systemctl reload nginx

echo "nginx настроен: http://$(curl -sS ifconfig.me 2>/dev/null || hostname -I | awk '{print $1}')/"
