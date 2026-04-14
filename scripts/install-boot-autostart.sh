#!/usr/bin/env bash
# Включает автозапуск Docker и стека MTS после перезагрузки ВМ.
# Запуск: sudo bash scripts/install-boot-autostart.sh
# Каталог проекта: задайте MTS_HOME или положите репозиторий в одном из типичных путей ниже.

set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
# Деплой из Actions передаёт MTS_HOME=$(pwd). Иначе ищем docker-compose.yml у типичных пользователей.
if [[ -z "${MTS_HOME:-}" ]]; then
  for d in /home/irwkc/mts /home/ubuntuuser/mts /root/mts; do
    if [[ -f "$d/docker-compose.yml" ]]; then
      MTS_HOME="$d"
      break
    fi
  done
fi
MTS_HOME="${MTS_HOME:-/home/ubuntuuser/mts}"
if [[ ! -f "$MTS_HOME/docker-compose.yml" ]]; then
  echo "Не найден docker-compose.yml в MTS_HOME=$MTS_HOME — задайте MTS_HOME вручную." >&2
  exit 1
fi
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

# nginx не должен стартовать раньше контейнеров (иначе 502 сразу после reboot)
mkdir -p /etc/systemd/system/nginx.service.d
cat > /etc/systemd/system/nginx.service.d/10-after-mts.conf <<'EOF'
[Unit]
After=mts-docker.service
Wants=mts-docker.service
EOF
systemctl daemon-reload

echo "Готово: mts-docker.service включён. Проверка: systemctl status mts-docker.service"
