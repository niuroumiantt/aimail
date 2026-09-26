from pathlib import Path

from aimail.config import default_database_path


def test_database_path_defaults_to_aimail(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("DB_PATH", raising=False)

    assert default_database_path() == Path("data/aimail.sqlite3")


def test_database_path_preserves_existing_legacy_file(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("DB_PATH", raising=False)
    legacy = tmp_path / "data/mail2leads.sqlite3"
    legacy.parent.mkdir()
    legacy.touch()

    assert default_database_path() == Path("data/mail2leads.sqlite3")


def test_explicit_database_path_wins(tmp_path, monkeypatch):
    configured = tmp_path / "existing.sqlite3"
    monkeypatch.setenv("DB_PATH", str(configured))

    assert default_database_path() == configured
