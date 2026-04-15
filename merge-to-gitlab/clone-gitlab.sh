#!/usr/bin/env bash
# Клон + merge + подсказка push. Нужен только PAT в переменной окружения.
# Запуск (вставь СВОЙ токен из GitLab → Preferences → Access Tokens):
#   export GITLAB_TOKEN='glpat-xxxxxxxx'
#   ./merge-to-gitlab/clone-gitlab.sh
#
# Если раньше вводили неверный пароль — macOS мог сохранить его в связке ключей.
# Скрипт по умолчанию стирает запись для этого хоста (только для git https).
set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"

if [[ -z "${GITLAB_TOKEN:-}" ]]; then
  echo "Создай токен: GitLab → Preferences → Access Tokens"
  echo "Права: read_repository + write_repository (достаточно для clone/push)"
  echo ""
  echo "Потом в терминале:"
  echo "  export GITLAB_TOKEN='glpat-...'"
  echo "  $ROOT/clone-gitlab.sh"
  exit 1
fi

# Убрать залипший неверный пароль из Keychain (иначе Git снова шлёт его).
if [[ "${GITLAB_KEEP_KEYCHAIN:-}" != "1" ]]; then
  printf 'host=git.truetecharena.ru\nprotocol=https\n\n' | git credential-osxkeychain erase 2>/dev/null || true
  echo ">>> Старая запись git https для git.truetecharena.ru удалена из связки ключей (если была)."
fi

export TASK_REPO_URL="${TASK_REPO_URL:-https://git.truetecharena.ru/tta/true-tech-hack2026-gpthub/baobab/task-repo.git}"
# Если oauth2 не подходит у вашего GitLab — задайте логин: export GITLAB_USER='ivan'
export GITLAB_USER="${GITLAB_USER:-oauth2}"

rm -rf "$ROOT/work/task-repo"
exec "$ROOT/go.sh"
