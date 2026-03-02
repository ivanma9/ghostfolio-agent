"""Tests for auth middleware (FastAPI dependency)."""
import pytest
from unittest.mock import AsyncMock

JWT_SECRET = "test-secret-for-middleware-tests"


class TestGetCurrentUser:
    @pytest.mark.asyncio
    async def test_valid_token_returns_user(self):
        from ghostfolio_agent.auth.jwt import create_token
        from ghostfolio_agent.auth.middleware import get_current_user

        token = create_token("user-123", "user", JWT_SECRET)
        mock_db = AsyncMock()
        mock_db.get_user.return_value = {"id": "user-123", "role": "user"}

        user = await get_current_user(
            authorization=f"Bearer {token}", jwt_secret=JWT_SECRET, auth_db=mock_db
        )
        assert user["id"] == "user-123"
        assert user["role"] == "user"

    @pytest.mark.asyncio
    async def test_missing_header_raises_401(self):
        from ghostfolio_agent.auth.middleware import get_current_user
        from fastapi import HTTPException

        with pytest.raises(HTTPException) as exc_info:
            await get_current_user(authorization=None, jwt_secret=JWT_SECRET, auth_db=AsyncMock())
        assert exc_info.value.status_code == 401

    @pytest.mark.asyncio
    async def test_invalid_token_raises_401(self):
        from ghostfolio_agent.auth.middleware import get_current_user
        from fastapi import HTTPException

        with pytest.raises(HTTPException) as exc_info:
            await get_current_user(
                authorization="Bearer garbage", jwt_secret=JWT_SECRET, auth_db=AsyncMock()
            )
        assert exc_info.value.status_code == 401

    @pytest.mark.asyncio
    async def test_user_not_in_db_raises_401(self):
        from ghostfolio_agent.auth.jwt import create_token
        from ghostfolio_agent.auth.middleware import get_current_user
        from fastapi import HTTPException

        token = create_token("deleted-user", "user", JWT_SECRET)
        mock_db = AsyncMock()
        mock_db.get_user.return_value = None

        with pytest.raises(HTTPException) as exc_info:
            await get_current_user(
                authorization=f"Bearer {token}", jwt_secret=JWT_SECRET, auth_db=mock_db
            )
        assert exc_info.value.status_code == 401

    @pytest.mark.asyncio
    async def test_no_bearer_prefix_raises_401(self):
        from ghostfolio_agent.auth.middleware import get_current_user
        from fastapi import HTTPException

        with pytest.raises(HTTPException) as exc_info:
            await get_current_user(
                authorization="just-a-token", jwt_secret=JWT_SECRET, auth_db=AsyncMock()
            )
        assert exc_info.value.status_code == 401
