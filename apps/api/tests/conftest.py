import pytest

from app.config import get_settings


@pytest.fixture(autouse=True)
def isolate_test_settings(monkeypatch):
    monkeypatch.setenv("AUTH_MODE", "local")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()
