import os
import tempfile

# До импорта app (main создаёт data_dir/static). Иначе на хосте без /data падает сборка тестов.
if not os.environ.get("_GPTHUB_PYTEST_DATA"):
    _td = tempfile.mkdtemp(prefix="gpthub-pytest-")
    os.environ["_GPTHUB_PYTEST_DATA"] = _td
    os.environ["DATA_DIR"] = _td

import pytest


@pytest.fixture
def router_settings(monkeypatch: pytest.MonkeyPatch):
    """Стабильный каталог моделей и поля роутера для юнит-тестов."""
    from app import router_logic

    s = router_logic.settings
    monkeypatch.setattr(s, "default_llm", "mts-anya", raising=False)
    monkeypatch.setattr(s, "vision_model", "gpt-4o", raising=False)
    monkeypatch.setattr(s, "auto_model_id", "gpthub-auto", raising=False)
    monkeypatch.setattr(s, "gena_chat_model", "", raising=False)
    monkeypatch.setattr(s, "gena_code_model", "code-model", raising=False)
    monkeypatch.setattr(s, "gena_long_doc_model", "long-doc-model", raising=False)
    monkeypatch.setattr(s, "gena_long_doc_word_threshold", 600, raising=False)
    return s
