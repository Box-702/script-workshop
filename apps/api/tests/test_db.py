from pathlib import Path

from app.db import API_ROOT, resolve_database_url


def test_relative_sqlite_url_resolves_against_api_root():
    url = resolve_database_url("sqlite:///./data/script-workshop.db")

    expected = (API_ROOT / "data/script-workshop.db").resolve()
    assert url == f"sqlite:///{expected.as_posix()}"


def test_absolute_and_non_sqlite_database_urls_are_unchanged():
    absolute = Path("C:/tmp/script-workshop.db").as_posix()

    assert resolve_database_url(f"sqlite:///{absolute}") == f"sqlite:///{absolute}"
    assert resolve_database_url("sqlite:///:memory:") == "sqlite:///:memory:"
    assert resolve_database_url("postgresql://user:pass@host/db") == (
        "postgresql://user:pass@host/db"
    )
