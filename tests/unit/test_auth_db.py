"""Tests for auth database operations."""
import pytest
from cryptography.fernet import Fernet

ENCRYPTION_KEY = Fernet.generate_key().decode()


@pytest.fixture
async def db(tmp_path):
    from ghostfolio_agent.auth.db import AuthDB
    auth_db = AuthDB(str(tmp_path / "test_auth.db"), ENCRYPTION_KEY)
    await auth_db.init()
    yield auth_db
    await auth_db.close()


class TestUsers:
    @pytest.mark.asyncio
    async def test_create_user_with_token(self, db):
        user = await db.create_user(ghostfolio_token="gf-token-123", role="user")
        assert user["id"]
        assert user["role"] == "user"

    @pytest.mark.asyncio
    async def test_create_guest(self, db):
        user = await db.create_user(ghostfolio_token=None, role="guest")
        assert user["role"] == "guest"

    @pytest.mark.asyncio
    async def test_get_user(self, db):
        created = await db.create_user(ghostfolio_token="tok", role="user")
        fetched = await db.get_user(created["id"])
        assert fetched is not None
        assert fetched["id"] == created["id"]
        assert fetched["role"] == "user"

    @pytest.mark.asyncio
    async def test_get_user_not_found(self, db):
        result = await db.get_user("nonexistent-id")
        assert result is None

    @pytest.mark.asyncio
    async def test_get_decrypted_token(self, db):
        user = await db.create_user(ghostfolio_token="my-secret-token", role="user")
        token = await db.get_decrypted_token(user["id"])
        assert token == "my-secret-token"

    @pytest.mark.asyncio
    async def test_get_decrypted_token_guest_returns_none(self, db):
        user = await db.create_user(ghostfolio_token=None, role="guest")
        token = await db.get_decrypted_token(user["id"])
        assert token is None

    @pytest.mark.asyncio
    async def test_find_user_by_token(self, db):
        created = await db.create_user(ghostfolio_token="unique-tok", role="user")
        found = await db.find_user_by_token("unique-tok")
        assert found is not None
        assert found["id"] == created["id"]

    @pytest.mark.asyncio
    async def test_find_user_by_token_not_found(self, db):
        result = await db.find_user_by_token("no-such-token")
        assert result is None

    @pytest.mark.asyncio
    async def test_update_last_login(self, db):
        user = await db.create_user(ghostfolio_token=None, role="guest")
        await db.update_last_login(user["id"])
        fetched = await db.get_user(user["id"])
        assert fetched["last_login_at"] >= user["last_login_at"]

    @pytest.mark.asyncio
    async def test_delete_user(self, db):
        user = await db.create_user(ghostfolio_token=None, role="guest")
        await db.delete_user(user["id"])
        assert await db.get_user(user["id"]) is None

    @pytest.mark.asyncio
    async def test_create_user_with_url(self, db):
        user = await db.create_user(
            ghostfolio_token="tok", role="user", ghostfolio_url="https://my.ghostfolio.com"
        )
        url = await db.get_decrypted_url(user["id"])
        assert url == "https://my.ghostfolio.com"

    @pytest.mark.asyncio
    async def test_create_user_without_url(self, db):
        user = await db.create_user(ghostfolio_token="tok", role="user")
        url = await db.get_decrypted_url(user["id"])
        assert url is None

    @pytest.mark.asyncio
    async def test_get_decrypted_url_nonexistent_user(self, db):
        url = await db.get_decrypted_url("no-such-id")
        assert url is None

    @pytest.mark.asyncio
    async def test_update_ghostfolio_url(self, db):
        user = await db.create_user(ghostfolio_token="tok", role="user")
        assert await db.get_decrypted_url(user["id"]) is None
        await db.update_ghostfolio_url(user["id"], "https://new.ghostfolio.io")
        assert await db.get_decrypted_url(user["id"]) == "https://new.ghostfolio.io"

    @pytest.mark.asyncio
    async def test_update_ghostfolio_url_clear(self, db):
        user = await db.create_user(
            ghostfolio_token="tok", role="user", ghostfolio_url="https://old.url"
        )
        await db.update_ghostfolio_url(user["id"], None)
        assert await db.get_decrypted_url(user["id"]) is None


class TestPaperPortfolios:
    @pytest.mark.asyncio
    async def test_get_default_portfolio(self, db):
        user = await db.create_user(ghostfolio_token=None, role="guest")
        portfolio = await db.get_paper_portfolio(user["id"])
        assert portfolio["cash"] == 100_000.0
        assert portfolio["positions"] == {}
        assert portfolio["trades"] == []

    @pytest.mark.asyncio
    async def test_save_and_load_portfolio(self, db):
        user = await db.create_user(ghostfolio_token=None, role="user")
        data = {"cash": 50000.0, "positions": {"AAPL": {"quantity": 10}}, "trades": [{"action": "buy"}]}
        await db.save_paper_portfolio(user["id"], data)
        loaded = await db.get_paper_portfolio(user["id"])
        assert loaded["cash"] == 50000.0
        assert loaded["positions"]["AAPL"]["quantity"] == 10
        assert len(loaded["trades"]) == 1

    @pytest.mark.asyncio
    async def test_upsert_replaces(self, db):
        user = await db.create_user(ghostfolio_token=None, role="user")
        await db.save_paper_portfolio(user["id"], {"cash": 90000.0, "positions": {}, "trades": []})
        await db.save_paper_portfolio(user["id"], {"cash": 80000.0, "positions": {}, "trades": []})
        loaded = await db.get_paper_portfolio(user["id"])
        assert loaded["cash"] == 80000.0

    @pytest.mark.asyncio
    async def test_delete_user_cascades_portfolio(self, db):
        user = await db.create_user(ghostfolio_token=None, role="guest")
        await db.save_paper_portfolio(user["id"], {"cash": 1.0, "positions": {}, "trades": []})
        await db.delete_user(user["id"])
        portfolio = await db.get_paper_portfolio(user["id"])
        assert portfolio["cash"] == 100_000.0


class TestAlertCooldowns:
    @pytest.mark.asyncio
    async def test_no_cooldowns_initially(self, db):
        user = await db.create_user(ghostfolio_token=None, role="user")
        cooldowns = await db.get_cooldowns(user["id"])
        assert cooldowns == {}

    @pytest.mark.asyncio
    async def test_set_and_get_cooldown(self, db):
        user = await db.create_user(ghostfolio_token=None, role="user")
        await db.set_cooldown(user["id"], "AAPL:earnings", 1000.0)
        cooldowns = await db.get_cooldowns(user["id"])
        assert cooldowns["AAPL:earnings"] == 1000.0

    @pytest.mark.asyncio
    async def test_prune_expired(self, db):
        import time
        user = await db.create_user(ghostfolio_token=None, role="user")
        old_time = time.time() - 100_000
        await db.set_cooldown(user["id"], "OLD:key", old_time)
        await db.set_cooldown(user["id"], "NEW:key", time.time())
        await db.prune_cooldowns(user["id"], ttl=86400)
        cooldowns = await db.get_cooldowns(user["id"])
        assert "OLD:key" not in cooldowns
        assert "NEW:key" in cooldowns

    @pytest.mark.asyncio
    async def test_cooldowns_isolated_per_user(self, db):
        u1 = await db.create_user(ghostfolio_token=None, role="user")
        u2 = await db.create_user(ghostfolio_token=None, role="user")
        await db.set_cooldown(u1["id"], "AAPL:earnings", 1000.0)
        assert await db.get_cooldowns(u2["id"]) == {}
