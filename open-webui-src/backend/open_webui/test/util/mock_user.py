"""Подмена get_current_user для интеграционных тестов роутеров."""

from __future__ import annotations

from contextlib import contextmanager
from typing import Optional


@contextmanager
def mock_webui_user(id: Optional[str] = '1'):
    from open_webui.main import app
    from open_webui.models.users import Users
    from open_webui.utils import auth as auth_utils

    uid = id

    async def _override():
        u = Users.get_user_by_id(uid) if uid else None
        if u is None:
            raise RuntimeError(f'mock_webui_user: user not found id={uid!r}')
        return u

    app.dependency_overrides[auth_utils.get_current_user] = _override
    try:
        yield
    finally:
        app.dependency_overrides.pop(auth_utils.get_current_user, None)
