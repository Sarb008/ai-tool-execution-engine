import pytest

import app.database as database
from app.database import initialize_database


@pytest.fixture(autouse=True)
def isolated_test_database(tmp_path, monkeypatch):
    """Give each test a fresh, isolated SQLite database."""
    test_database = tmp_path / "test_engine.db"
    monkeypatch.setattr(database, "DATABASE_PATH", test_database)
    initialize_database()
