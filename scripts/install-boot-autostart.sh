#!/usr/bin/env bash
# Включает автозапуск Docker и стека MTS после перезагрузки ВМ.
# Запуск: sudo bash scripts/install-boot-autostart.sh
# Каталог проекта на сервере по умолчанию: /home/ubuntuuser/mts

set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
# Каталог с docker-compose.yml и .env на сервере (при другом пользователе: MTS_HOME=/home/ubuntu/mts)
MTS_HOME="${MTS_HOME:-/home/ubuntuuser/mts}"
UNIT_SRC="$ROOT/deploy/mts-docker.service"
UNIT_DST="/etc/systemd/system/mts-docker.service"

if [[ "${EUID:-0}" -ne 0 ]]; then
  echo "Нужен root: sudo bash $0" >&2
  exit 1
fi

if [[ ! -f "$UNIT_SRC" ]]; then
  echo "Не найден $UNIT_SRC" >&2
  exit 1
fi

systemctl enable docker 2>/dev/null || true

TMP="$(mktemp)"
sed "s|^WorkingDirectory=.*|WorkingDirectory=$MTS_HOME|" "$UNIT_SRC" >"$TMP"
install -m 644 "$TMP" "$UNIT_DST"
rm -f "$TMP"
systemctl daemon-reload
systemctl enable mts-docker.service
systemctl restart mts-docker.service || systemctl start mts-docker.service

if systemctl is-enabled nginx &>/dev/null; then
  systemctl enable nginx
fi

echo "Готово: mts-docker.service включён. Проверка: systemctl status mts-docker.service"
