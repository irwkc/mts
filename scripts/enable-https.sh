#!/usr/bin/env bash
# Включает HTTPS (Let's Encrypt) для Open WebUI за nginx.
# По умолчанию в репозитории только HTTP :80 — без этого шага https:// не заработает.
#
# На сервере (после setup-nginx.sh), из корня репозитория:
#   sudo CERTBOT_EMAIL=you@ваш-домен.tld bash scripts/enable-https.sh notifik.ru
# Затем в .env: WEBUI_URL=https://notifik.ru и: docker compose up -d

set -euo pipefail

DOMAIN="${1:-${NGINX_DOMAIN:-}}"
EMAIL="${CERTBOT_EMAIL:-}"

if [[ -z "${DOMAIN}" ]]; then
  echo "Usage: sudo CERTBOT_EMAIL=mail@example.com $0 your-domain.tld" >&2
  exit 1
fi
if [[ -z "${EMAIL}" ]]; then
  echo "Нужен CERTBOT_EMAIL=… для Let's Encrypt (уведомления о продлении сертификата)." >&2
  exit 1
fi
if [[ "${EUID:-0}" -ne 0 ]]; then
  echo "Нужен root: sudo $0 $*" >&2
  exit 1
fi

export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get install -y -qq certbot python3-certbot-nginx

CONF="/etc/nginx/sites-available/mts"
if [[ ! -f "${CONF}" ]]; then
  echo "Сначала: sudo bash scripts/setup-nginx.sh (нет ${CONF})" >&2
  exit 1
fi

cp -a "${CONF}" "${CONF}.bak.$(date +%s)"
# Явное имя хоста вместо _ — иначе certbot не привяжет сертификат
sed -i "s/server_name _;/server_name ${DOMAIN};/" "${CONF}"
nginx -t
systemctl reload nginx

certbot --nginx -d "${DOMAIN}" --non-interactive --agree-tos -m "${EMAIL}" --redirect

nginx -t
systemctl reload nginx
echo "Готово: https://${DOMAIN}/ — задайте WEBUI_URL=https://${DOMAIN} в .env и перезапустите: docker compose up -d"
