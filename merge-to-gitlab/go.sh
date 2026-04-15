#!/usr/bin/env bash
# Запуск из любого места:  bash merge-to-gitlab/go.sh
# Или:  cd merge-to-gitlab && ./go.sh
set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
WORK="$ROOT/work"
mkdir -p "$WORK"

TASK_REPO_URL="${TASK_REPO_URL:-https://git.truetecharena.ru/tta/true-tech-hack2026-gpthub/baobab/task-repo.git}"
BRANCH="${BRANCH:-main1}"

CLONE_URL="$TASK_REPO_URL"
if [[ -n "${GITLAB_TOKEN:-}" ]] && [[ "$TASK_REPO_URL" == https://* ]]; then
  GL_USER="${GITLAB_USER:-oauth2}"
  CLONE_URL="${TASK_REPO_URL/https:\/\//https://${GL_USER}:${GITLAB_TOKEN}@}"
fi

cd "$WORK"

if [[ ! -d task-repo/.git ]]; then
  echo ">>> Клонирую task-repo в $WORK/task-repo"
  if ! git clone "$CLONE_URL" task-repo; then
    echo ""
    echo "GitLab отклонил доступ."
    echo ""
    echo "1) Новый токен: Preferences → Access Tokens → read_repository + write_repository"
    echo "2) Запуск с токеном в URL (обходит кэш пароля):"
    echo "   export GITLAB_TOKEN='glpat-...'"
    echo "   ./merge-to-gitlab/clone-gitlab.sh"
    echo "3) Если токен точно верный — попробуй логин GitLab вместо oauth2:"
    echo "   export GITLAB_USER='твой_логин_на_gitlab'"
    echo "4) Стереть залипший пароль в macOS:"
    echo "   printf 'host=git.truetecharena.ru\\nprotocol=https\\n\\n' | git credential-osxkeychain erase"
    echo ""
    echo "SSH: export TASK_REPO_URL='git@git.truetecharena.ru:tta/.../task-repo.git' && ./merge-to-gitlab/go.sh"
    echo ""
    echo "Если папка битая: rm -rf \"$WORK/task-repo\""
    exit 1
  fi
else
  echo ">>> Уже есть $WORK/task-repo — clone пропущен"
fi

cd task-repo

echo ">>> fetch origin, ветка $BRANCH"
git fetch origin
git checkout "$BRANCH"
git pull origin "$BRANCH" || true

if ! git remote get-url open-webui &>/dev/null; then
  git remote add open-webui https://github.com/open-webui/open-webui.git
fi
echo ">>> fetch open-webui/main"
git fetch open-webui

if [[ "${SKIP_MERGE:-}" == "1" ]]; then
  echo ""
  echo "SKIP_MERGE=1 — merge не выполнялся."
  echo "Дальше вручную:"
  echo "  cd \"$WORK/task-repo\""
  echo "  git merge open-webui/main"
  echo "  # при необходимости: git merge open-webui/main --allow-unrelated-histories"
  exit 0
fi

if [[ -d open-webui-src && ! -d backend ]] && [[ "${FORCE_MERGE:-}" != "1" ]]; then
  echo ""
  echo "Обнаружена монорепа (есть open-webui-src/, нет backend/ в корне)."
  echo "Корневой merge open-webui сломает структуру. Остановился после fetch."
  echo "Дальше синхронизируй open-webui только внутри open-webui-src (вручную или subtree)."
  echo "Если всё же нужен корневой merge: FORCE_MERGE=1 $0"
  exit 0
fi

echo ">>> merge open-webui/main"
set +e
git merge --no-edit open-webui/main
MERGE_STAT=$?
set -e

if [[ $MERGE_STAT -ne 0 ]]; then
  echo ">>> обычный merge не прошёл, пробую --allow-unrelated-histories"
  git merge --no-edit --allow-unrelated-histories open-webui/main
fi

echo ""
echo ">>> Готово. Если конфликты — разрули в $WORK/task-repo и сделай commit."
echo ">>> Отправка на GitLab:"
echo "    cd \"$WORK/task-repo\""
if [[ -n "${GITLAB_TOKEN:-}" ]] && git remote get-url origin 2>/dev/null | grep -q '^https://'; then
  ORIG="$(git remote get-url origin)"
  if [[ "$ORIG" != *"@"* ]]; then
    GU="${GITLAB_USER:-oauth2}"
    AUTH_ORIG="${ORIG/https:\/\//https://${GU}:${GITLAB_TOKEN}@}"
    echo "    (подставляю токен в origin для push)"
    git remote set-url origin "$AUTH_ORIG"
  fi
fi
echo ">>> Пробую git push origin $BRANCH"
if ! git push origin "$BRANCH"; then
  echo ""
  echo ">>> push не удался — смотри сообщение выше. Повтори:"
  echo "    cd \"$WORK/task-repo\" && git push origin $BRANCH"
fi
