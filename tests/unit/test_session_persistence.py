"""Tests for SQLite-backed session persistence checkpointer."""

import pytest
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver

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
            import asyncio
            asyncio.get_event_loop().run_until_complete(chat_module._checkpointer.conn.close())
        except Exception:
            pass
    chat_module._checkpointer = original


@pytest.mark.asyncio
async def test_get_checkpointer_returns_async_sqlite_saver(tmp_path, monkeypatch):
    """_get_checkpointer() should return an AsyncSqliteSaver instance."""
    monkeypatch.setattr(chat_module, "_DB_PATH", str(tmp_path / "checkpoints.db"))
    monkeypatch.setattr(chat_module, "_checkpointer", None)

    checkpointer = await chat_module._get_checkpointer()

    assert isinstance(checkpointer, AsyncSqliteSaver)


@pytest.mark.asyncio
async def test_get_checkpointer_creates_db_file(tmp_path, monkeypatch):
    """_get_checkpointer() should create the SQLite DB file on disk."""
    db_path = tmp_path / "data" / "checkpoints.db"
    monkeypatch.setattr(chat_module, "_DB_PATH", str(db_path))
    monkeypatch.setattr(chat_module, "_checkpointer", None)

    await chat_module._get_checkpointer()

    assert db_path.exists(), f"Expected DB file at {db_path}"


@pytest.mark.asyncio
async def test_get_checkpointer_singleton(tmp_path, monkeypatch):
    """_get_checkpointer() should return the same instance on repeated calls."""
    monkeypatch.setattr(chat_module, "_DB_PATH", str(tmp_path / "checkpoints.db"))
    monkeypatch.setattr(chat_module, "_checkpointer", None)

    first = await chat_module._get_checkpointer()
    second = await chat_module._get_checkpointer()

    assert first is second
