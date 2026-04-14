"""
Pytest: задаёт БД и секрет до импорта open_webui (DATABASE_URL читается при импорте env).
"""

import os
import tempfile


def pytest_configure(config):
    if os.environ.get('_OPEN_WEBUI_TEST_DB_ROOT'):
        return
    root = tempfile.mkdtemp(prefix='owui-pytest-')
    os.environ['_OPEN_WEBUI_TEST_DB_ROOT'] = root
    db_path = os.path.join(root, 'webui.db')
    os.environ['DATABASE_URL'] = f'sqlite:///{db_path}'
    os.environ.setdefault('WEBUI_SECRET_KEY', 'test-secret-key-pytest-open-webui')
    os.environ.setdefault('ENABLE_SIGNUP', 'false')
    os.environ.setdefault('OFFLINE_MODE', 'true')
