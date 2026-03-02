"""Tests for JWT token creation and verification."""
import time
import pytest


JWT_SECRET = "test-secret-key-for-jwt-signing"


class TestJWT:
    def test_create_and_verify(self):
        from ghostfolio_agent.auth.jwt import create_token, verify_token
        token = create_token("user-123", "user", JWT_SECRET)
        payload = verify_token(token, JWT_SECRET)
        assert payload["user_id"] == "user-123"
        assert payload["role"] == "user"

    def test_admin_role(self):
        from ghostfolio_agent.auth.jwt import create_token, verify_token
        token = create_token("admin-1", "admin", JWT_SECRET)
        payload = verify_token(token, JWT_SECRET)
        assert payload["role"] == "admin"

    def test_guest_role(self):
        from ghostfolio_agent.auth.jwt import create_token, verify_token
        token = create_token("guest-99", "guest", JWT_SECRET)
        payload = verify_token(token, JWT_SECRET)
        assert payload["role"] == "guest"

    def test_invalid_token_raises(self):
        from ghostfolio_agent.auth.jwt import verify_token
        with pytest.raises(ValueError, match="Invalid token"):
            verify_token("garbage.token.here", JWT_SECRET)

    def test_wrong_secret_raises(self):
        from ghostfolio_agent.auth.jwt import create_token, verify_token
        token = create_token("user-1", "user", JWT_SECRET)
        with pytest.raises(ValueError, match="Invalid token"):
            verify_token(token, "wrong-secret")

    def test_expired_token_raises(self):
        from ghostfolio_agent.auth.jwt import create_token, verify_token
        token = create_token("user-1", "user", JWT_SECRET, expires_in=0)
        time.sleep(1)
        with pytest.raises(ValueError, match="Invalid token"):
            verify_token(token, JWT_SECRET)
