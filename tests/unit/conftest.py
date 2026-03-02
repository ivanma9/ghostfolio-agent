"""Shared fixtures for unit tests."""

import pytest
from pathlib import Path


@pytest.fixture(autouse=True)
def _isolate_alert_cooldowns(tmp_path, monkeypatch):
    """Ensure each test gets its own cooldown file to prevent cross-test interference."""
    monkeypatch.setattr(
        "ghostfolio_agent.alerts.engine._COOLDOWN_PATH",
        tmp_path / "alert_cooldowns.json",
    )
