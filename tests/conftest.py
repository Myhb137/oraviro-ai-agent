import pytest
from app import database

@pytest.fixture(autouse=True)
def isolated_database(tmp_path, monkeypatch):
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    monkeypatch.setattr(database, "DB_PATH", str(tmp_path / "test.db"))
    database.initialize_database()
    database.seed_products()
