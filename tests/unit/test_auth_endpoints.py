"""Tests for /api/auth/* endpoints."""
import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from cryptography.fernet import Fernet

ENCRYPTION_KEY = Fernet.generate_key().decode()
JWT_SECRET = "test-jwt-secret"


@pytest.fixture
def mock_settings(monkeypatch):
    mock = MagicMock()
    mock.ghostfolio_base_url = "http://localhost:3333"
    mock.ghostfolio_access_token = "admin-env-token"
    mock.jwt_secret = JWT_SECRET
    mock.encryption_key = ENCRYPTION_KEY
    monkeypatch.setattr("ghostfolio_agent.api.auth.get_settings", lambda: mock)
    return mock


class TestLogin:
    @pytest.mark.asyncio
    async def test_login_creates_user_and_returns_jwt(self, mock_settings):
        from ghostfolio_agent.api.auth import login, LoginRequest

        mock_db = AsyncMock()
        mock_db.find_user_by_token.return_value = None
        mock_db.create_user.return_value = {"id": "new-user", "role": "user"}

        with patch("ghostfolio_agent.api.auth._validate_ghostfolio_token", return_value=True):
            with patch("ghostfolio_agent.api.auth._get_auth_db", return_value=mock_db):
                result = await login(LoginRequest(ghostfolio_token="valid-token"))

        assert "token" in result
        assert result["role"] == "user"
        mock_db.create_user.assert_called_once()

    @pytest.mark.asyncio
    async def test_login_existing_user_returns_jwt(self, mock_settings):
        from ghostfolio_agent.api.auth import login, LoginRequest

        mock_db = AsyncMock()
        mock_db.find_user_by_token.return_value = {"id": "existing", "role": "user"}

        with patch("ghostfolio_agent.api.auth._validate_ghostfolio_token", return_value=True):
            with patch("ghostfolio_agent.api.auth._get_auth_db", return_value=mock_db):
                result = await login(LoginRequest(ghostfolio_token="valid-token"))

        assert result["role"] == "user"
        mock_db.create_user.assert_not_called()
        mock_db.update_last_login.assert_called_once()

    @pytest.mark.asyncio
    async def test_login_admin_token_gets_admin_role(self, mock_settings):
        from ghostfolio_agent.api.auth import login, LoginRequest

        mock_db = AsyncMock()
        mock_db.find_user_by_token.return_value = None
        mock_db.create_user.return_value = {"id": "admin-1", "role": "admin"}

        with patch("ghostfolio_agent.api.auth._validate_ghostfolio_token", return_value=True):
            with patch("ghostfolio_agent.api.auth._get_auth_db", return_value=mock_db):
                result = await login(LoginRequest(ghostfolio_token="admin-env-token"))

        assert result["role"] == "admin"

    @pytest.mark.asyncio
    async def test_login_invalid_token_returns_401(self, mock_settings):
        from ghostfolio_agent.api.auth import login, LoginRequest
        from fastapi import HTTPException

        with patch("ghostfolio_agent.api.auth._validate_ghostfolio_token", return_value=False):
            with patch("ghostfolio_agent.api.auth._get_auth_db", return_value=AsyncMock()):
                with pytest.raises(HTTPException) as exc_info:
                    await login(LoginRequest(ghostfolio_token="bad-token"))
                assert exc_info.value.status_code == 401


class TestGuest:
    @pytest.mark.asyncio
    async def test_guest_creates_ephemeral_user(self, mock_settings):
        from ghostfolio_agent.api.auth import guest_login

        mock_db = AsyncMock()
        mock_db.create_user.return_value = {"id": "guest-99", "role": "guest"}

        with patch("ghostfolio_agent.api.auth._get_auth_db", return_value=mock_db):
            result = await guest_login()

        assert "token" in result
        assert result["role"] == "guest"
        mock_db.create_user.assert_called_once_with(ghostfolio_token=None, role="guest")
