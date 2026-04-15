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
if [[ -n "${GITLAB_TOKEN:-}" ]]; then
  GL_USER="${GITLAB_USER:-oauth2}"
  CLONE_URL="${TASK_REPO_URL/https:\/\//https://${GL_USER}:${GITLAB_TOKEN}@}"
fi

cd "$WORK"

if [[ ! -d task-repo/.git ]]; then
  echo ">>> Клонирую task-repo в $WORK/task-repo"
  if ! git clone "$CLONE_URL" task-repo; then
    echo ""
    echo "GitLab отклонил доступ. Сделай одно из двух:"
    echo ""
    echo "1) Personal Access Token (GitLab → Settings → Access Tokens): scope read_repository + write_repository"
    echo "   export GITLAB_TOKEN='glpat-...'"
    echo "   ./merge-to-gitlab/go.sh"
    echo ""
    echo "2) SSH: добавь ключ в GitLab, потом:"
    echo "   export TASK_REPO_URL='git@git.truetecharena.ru:tta/true-tech-hack2026-gpthub/baobab/task-repo.git'"
    echo "   ./merge-to-gitlab/go.sh"
    echo ""
    echo "Если папка task-repo создалась пустой/битая — удали: rm -rf \"$WORK/task-repo\""
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
echo "    git push origin $BRANCH"
