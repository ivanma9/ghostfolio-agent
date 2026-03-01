"""Tests for SQLite-backed session persistence checkpointer."""

import sqlite3

import pytest
from langgraph.checkpoint.sqlite import SqliteSaver

import ghostfolio_agent.api.chat as chat_module


@pytest.fixture(autouse=True)
def reset_checkpointer():
    """Reset the module-level _checkpointer singleton before and after each test."""
    original = chat_module._checkpointer
    chat_module._checkpointer = None
    yield
    # Close any open connection to avoid ResourceWarning
    if chat_module._checkpointer is not None:
        try:
            chat_module._checkpointer.conn.close()
        except Exception:
            pass
    chat_module._checkpointer = original


def test_get_checkpointer_returns_sqlite_saver(tmp_path, monkeypatch):
    """_get_checkpointer() should return a SqliteSaver instance."""
    monkeypatch.setattr(chat_module, "_DB_PATH", str(tmp_path / "checkpoints.db"))
    monkeypatch.setattr(chat_module, "_checkpointer", None)

    checkpointer = chat_module._get_checkpointer()

    assert isinstance(checkpointer, SqliteSaver)


def test_get_checkpointer_creates_db_file(tmp_path, monkeypatch):
    """_get_checkpointer() should create the SQLite DB file on disk."""
    db_path = tmp_path / "data" / "checkpoints.db"
    monkeypatch.setattr(chat_module, "_DB_PATH", str(db_path))
    monkeypatch.setattr(chat_module, "_checkpointer", None)

    chat_module._get_checkpointer()

    assert db_path.exists(), f"Expected DB file at {db_path}"


def test_get_checkpointer_singleton(tmp_path, monkeypatch):
    """_get_checkpointer() should return the same instance on repeated calls."""
    monkeypatch.setattr(chat_module, "_DB_PATH", str(tmp_path / "checkpoints.db"))
    monkeypatch.setattr(chat_module, "_checkpointer", None)

    first = chat_module._get_checkpointer()
    second = chat_module._get_checkpointer()

    assert first is second
