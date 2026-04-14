# CI: gpthub-gateway (pytest)

Тесты: `cd gpthub-gateway && pip install -r requirements.txt -r requirements-dev.txt && pytest tests/ -q`.

## GitHub Actions

Чтобы workflow попал в репозиторий:

1. Создайте в GitHub файл **`.github/workflows/gpthub-pytest.yml`** (кнопка **Add file** → содержимое ниже), либо выполните `git push` с токеном, у которого есть scope **workflow**, либо используйте **SSH** (`git@github.com:…`).

2. После merge workflow будет в списке **Actions** → **gpthub-gateway tests** (также доступен ручной запуск **Run workflow**).

### Содержимое `.github/workflows/gpthub-pytest.yml`

```yaml
name: gpthub-gateway tests

on:
  push:
    branches: [main]
    paths:
      - "gpthub-gateway/**"
      - ".github/workflows/gpthub-pytest.yml"
  pull_request:
    paths:
      - "gpthub-gateway/**"
      - ".github/workflows/gpthub-pytest.yml"
  workflow_dispatch:

permissions:
  contents: read

jobs:
  pytest:
    runs-on: ubuntu-latest
    defaults:
      run:
        working-directory: gpthub-gateway
    steps:
      - uses: actions/checkout@v4

      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: "3.12"
          cache: "pip"
          cache-dependency-path: gpthub-gateway/requirements*.txt

      - name: Install dependencies
        run: |
          python -m pip install --upgrade pip
          pip install -r requirements.txt -r requirements-dev.txt

      - name: Run pytest
        run: python -m pytest tests/ -q --tb=short
```

### Поведение

- **Когда:** push / PR в `main`, если менялись `gpthub-gateway/**` или сам workflow.
- **Ручной запуск:** `workflow_dispatch` в UI Actions.

### Если HTTPS push отклоняет workflow

Текст вида *Personal Access Token … without `workflow` scope* — включите scope **workflow** у PAT или добавьте YAML через веб-интерфейс репозитория.
