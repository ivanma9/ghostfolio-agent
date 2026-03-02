"""Tests for auth-related config fields."""
import os
import pytest


def test_settings_has_auth_fields(monkeypatch):
    """Settings should include jwt_secret and encryption_key with defaults."""
    monkeypatch.setenv("GHOSTFOLIO_ACCESS_TOKEN", "test-token")
    monkeypatch.setenv("JWT_SECRET", "test-jwt-secret")
    monkeypatch.setenv("ENCRYPTION_KEY", "dGVzdC1lbmNyeXB0aW9uLWtleS0zMi1ieXRlcyE=")

    from ghostfolio_agent.config import Settings
    s = Settings()
    assert s.jwt_secret == "test-jwt-secret"
    assert s.encryption_key == "dGVzdC1lbmNyeXB0aW9uLWtleS0zMi1ieXRlcyE="


def test_settings_jwt_secret_defaults_empty(monkeypatch):
    """JWT secret should default to empty string for backwards compat."""
    monkeypatch.setenv("GHOSTFOLIO_ACCESS_TOKEN", "test-token")
    # Don't set JWT_SECRET or ENCRYPTION_KEY
    from ghostfolio_agent.config import Settings
    s = Settings()
    assert s.jwt_secret == ""
    assert s.encryption_key == ""
