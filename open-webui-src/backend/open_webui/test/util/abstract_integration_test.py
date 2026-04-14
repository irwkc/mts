"""Базовый класс HTTP-тестов Open WebUI (SQLite, TestClient)."""

from __future__ import annotations

from urllib.parse import urlencode

from starlette.testclient import TestClient


class AbstractPostgresTest:
    """Имя историческое; используется SQLite из conftest (DATABASE_URL)."""

    BASE_PATH = ''
    fast_api_client: TestClient
    app = None

    @classmethod
    def setup_class(cls):
        from open_webui.main import app

        cls.app = app
        cls.fast_api_client = TestClient(app)

    @classmethod
    def teardown_class(cls):
        if getattr(cls, 'fast_api_client', None) is not None:
            cls.fast_api_client.close()

    def setup_method(self):
        self._clear_db()

    def _clear_db(self):
        from open_webui.internal.db import Base, engine

        with engine.begin() as conn:
            for table in reversed(Base.metadata.sorted_tables):
                conn.execute(table.delete())

    def create_url(self, path: str = '', query_params: dict | None = None) -> str:
        base = self.BASE_PATH.rstrip('/')
        if path == '':
            url = base
        else:
            if not path.startswith('/'):
                path = '/' + path
            url = base + path
        if query_params:
            url += '?' + urlencode(query_params)
        return url
