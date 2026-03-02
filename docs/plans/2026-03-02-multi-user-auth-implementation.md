# Multi-User Authentication Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add JWT-based multi-user auth with three roles (admin, user, guest), per-user data isolation in SQLite, and a login screen with guest mode.

**Architecture:** FastAPI dependency injection for auth on all endpoints. Per-user GhostfolioClient via decrypted tokens from SQLite. Paper portfolios and alert cooldowns migrated from JSON files to SQLite tables. Frontend auth gate with token login + guest mode.

**Tech Stack:** PyJWT, cryptography (Fernet), aiosqlite, FastAPI Depends

---

### Task 1: Add Dependencies

**Files:**
- Modify: `pyproject.toml`

**Step 1: Add PyJWT and cryptography to dependencies**

In `pyproject.toml`, add to the `dependencies` list:
```toml
    "PyJWT>=2.9",
    "cryptography>=44.0",
```

**Step 2: Install dependencies**

Run: `uv sync`
Expected: Dependencies install successfully

**Step 3: Commit**

```bash
git add pyproject.toml uv.lock
git commit -m "chore: add PyJWT and cryptography dependencies for auth"
```

---

### Task 2: Config — Add Auth Settings

**Files:**
- Modify: `src/ghostfolio_agent/config.py`
- Test: `tests/unit/test_config_auth.py`

**Step 1: Write test for new config fields**

Create `tests/unit/test_config_auth.py`:

```python
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
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_config_auth.py -v`
Expected: FAIL — `Settings` has no `jwt_secret` or `encryption_key` fields

**Step 3: Add fields to Settings**

In `src/ghostfolio_agent/config.py`, add after the `congressional_api_url` line:

```python
    # Auth
    jwt_secret: str = ""
    encryption_key: str = ""  # Fernet key for encrypting Ghostfolio tokens at rest
```

**Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/test_config_auth.py -v`
Expected: PASS

**Step 5: Run full test suite**

Run: `uv run pytest tests/unit/ -v`
Expected: All tests pass

**Step 6: Commit**

```bash
git add src/ghostfolio_agent/config.py tests/unit/test_config_auth.py
git commit -m "feat(auth): add jwt_secret and encryption_key to Settings"
```

---

### Task 3: Encryption Module

**Files:**
- Create: `src/ghostfolio_agent/auth/__init__.py`
- Create: `src/ghostfolio_agent/auth/encryption.py`
- Test: `tests/unit/test_encryption.py`

**Step 1: Create auth package**

Create empty `src/ghostfolio_agent/auth/__init__.py`.

**Step 2: Write encryption tests**

Create `tests/unit/test_encryption.py`:

```python
"""Tests for Ghostfolio token encryption/decryption."""
import pytest
from cryptography.fernet import Fernet


def _generate_key() -> str:
    return Fernet.generate_key().decode()


class TestEncryption:
    def test_round_trip(self):
        from ghostfolio_agent.auth.encryption import encrypt_token, decrypt_token
        key = _generate_key()
        plaintext = "my-ghostfolio-token-abc123"
        encrypted = encrypt_token(plaintext, key)
        assert encrypted != plaintext.encode()
        decrypted = decrypt_token(encrypted, key)
        assert decrypted == plaintext

    def test_different_keys_fail(self):
        from ghostfolio_agent.auth.encryption import encrypt_token, decrypt_token
        key1 = _generate_key()
        key2 = _generate_key()
        encrypted = encrypt_token("secret", key1)
        with pytest.raises(Exception):
            decrypt_token(encrypted, key2)

    def test_empty_token(self):
        from ghostfolio_agent.auth.encryption import encrypt_token, decrypt_token
        key = _generate_key()
        encrypted = encrypt_token("", key)
        assert decrypt_token(encrypted, key) == ""
```

**Step 3: Run tests to verify they fail**

Run: `uv run pytest tests/unit/test_encryption.py -v`
Expected: FAIL — module not found

**Step 4: Implement encryption module**

Create `src/ghostfolio_agent/auth/encryption.py`:

```python
"""AES encryption for Ghostfolio tokens at rest using Fernet."""
from cryptography.fernet import Fernet


def encrypt_token(plaintext: str, key: str) -> bytes:
    """Encrypt a Ghostfolio access token. Key must be a valid Fernet key."""
    f = Fernet(key.encode())
    return f.encrypt(plaintext.encode())


def decrypt_token(ciphertext: bytes, key: str) -> str:
    """Decrypt a Ghostfolio access token."""
    f = Fernet(key.encode())
    return f.decrypt(ciphertext).decode()
```

**Step 5: Run tests to verify they pass**

Run: `uv run pytest tests/unit/test_encryption.py -v`
Expected: PASS

**Step 6: Commit**

```bash
git add src/ghostfolio_agent/auth/ tests/unit/test_encryption.py
git commit -m "feat(auth): add Fernet encryption for Ghostfolio tokens"
```

---

### Task 4: JWT Module

**Files:**
- Create: `src/ghostfolio_agent/auth/jwt.py`
- Test: `tests/unit/test_jwt.py`

**Step 1: Write JWT tests**

Create `tests/unit/test_jwt.py`:

```python
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
```

**Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/unit/test_jwt.py -v`
Expected: FAIL — module not found

**Step 3: Implement JWT module**

Create `src/ghostfolio_agent/auth/jwt.py`:

```python
"""JWT token creation and verification."""
import time
import jwt


def create_token(
    user_id: str, role: str, secret: str, expires_in: int = 86400
) -> str:
    """Create a signed JWT. expires_in is seconds (default 24h)."""
    payload = {
        "user_id": user_id,
        "role": role,
        "exp": int(time.time()) + expires_in,
    }
    return jwt.encode(payload, secret, algorithm="HS256")


def verify_token(token: str, secret: str) -> dict:
    """Verify and decode a JWT. Raises ValueError on any failure."""
    try:
        return jwt.decode(token, secret, algorithms=["HS256"])
    except jwt.PyJWTError as e:
        raise ValueError(f"Invalid token: {e}") from e
```

**Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/unit/test_jwt.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add src/ghostfolio_agent/auth/jwt.py tests/unit/test_jwt.py
git commit -m "feat(auth): add JWT creation and verification"
```

---

### Task 5: Auth Database — Users Table

**Files:**
- Create: `src/ghostfolio_agent/auth/db.py`
- Test: `tests/unit/test_auth_db.py`

**Step 1: Write tests for user CRUD**

Create `tests/unit/test_auth_db.py`:

```python
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
        """Users can be looked up by their plaintext token to avoid duplicates."""
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
```

**Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/unit/test_auth_db.py -v`
Expected: FAIL — module not found

**Step 3: Implement AuthDB class**

Create `src/ghostfolio_agent/auth/db.py`:

```python
"""Auth database — users, paper portfolios, alert cooldowns in SQLite."""
import hashlib
import uuid
from datetime import datetime, timezone

import aiosqlite

from ghostfolio_agent.auth.encryption import encrypt_token, decrypt_token


class AuthDB:
    """Async SQLite database for auth and per-user data."""

    def __init__(self, db_path: str, encryption_key: str) -> None:
        self._db_path = db_path
        self._encryption_key = encryption_key
        self._conn: aiosqlite.Connection | None = None

    async def init(self) -> None:
        """Open connection and create tables."""
        self._conn = await aiosqlite.connect(self._db_path)
        self._conn.row_factory = aiosqlite.Row
        await self._conn.executescript(_SCHEMA)

    async def close(self) -> None:
        if self._conn:
            await self._conn.close()

    # ── Users ──────────────────────────────────────────────

    async def create_user(
        self, *, ghostfolio_token: str | None, role: str
    ) -> dict:
        now = datetime.now(timezone.utc).isoformat()
        user_id = str(uuid.uuid4())
        encrypted = None
        token_hash = None
        if ghostfolio_token:
            encrypted = encrypt_token(ghostfolio_token, self._encryption_key)
            token_hash = hashlib.sha256(ghostfolio_token.encode()).hexdigest()
        await self._conn.execute(
            "INSERT INTO users (id, ghostfolio_token, token_hash, role, created_at, last_login_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (user_id, encrypted, token_hash, role, now, now),
        )
        await self._conn.commit()
        return {"id": user_id, "role": role, "created_at": now, "last_login_at": now}

    async def get_user(self, user_id: str) -> dict | None:
        cursor = await self._conn.execute(
            "SELECT id, role, created_at, last_login_at FROM users WHERE id = ?",
            (user_id,),
        )
        row = await cursor.fetchone()
        return dict(row) if row else None

    async def get_decrypted_token(self, user_id: str) -> str | None:
        cursor = await self._conn.execute(
            "SELECT ghostfolio_token FROM users WHERE id = ?", (user_id,)
        )
        row = await cursor.fetchone()
        if not row or not row["ghostfolio_token"]:
            return None
        return decrypt_token(row["ghostfolio_token"], self._encryption_key)

    async def find_user_by_token(self, plaintext_token: str) -> dict | None:
        token_hash = hashlib.sha256(plaintext_token.encode()).hexdigest()
        cursor = await self._conn.execute(
            "SELECT id, role, created_at, last_login_at FROM users WHERE token_hash = ?",
            (token_hash,),
        )
        row = await cursor.fetchone()
        return dict(row) if row else None

    async def update_last_login(self, user_id: str) -> None:
        now = datetime.now(timezone.utc).isoformat()
        await self._conn.execute(
            "UPDATE users SET last_login_at = ? WHERE id = ?", (now, user_id)
        )
        await self._conn.commit()

    async def delete_user(self, user_id: str) -> None:
        await self._conn.execute("DELETE FROM users WHERE id = ?", (user_id,))
        await self._conn.commit()


_SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id              TEXT PRIMARY KEY,
    ghostfolio_token BLOB,
    token_hash      TEXT,
    role            TEXT NOT NULL,
    created_at      TEXT NOT NULL,
    last_login_at   TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS paper_portfolios (
    user_id    TEXT PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
    cash       REAL NOT NULL DEFAULT 100000.0,
    positions  TEXT NOT NULL DEFAULT '{}',
    trades     TEXT NOT NULL DEFAULT '[]',
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS alert_cooldowns (
    user_id   TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    alert_key TEXT NOT NULL,
    fired_at  REAL NOT NULL,
    PRIMARY KEY (user_id, alert_key)
);

CREATE INDEX IF NOT EXISTS idx_users_token_hash ON users(token_hash);
"""
```

**Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/unit/test_auth_db.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add src/ghostfolio_agent/auth/db.py tests/unit/test_auth_db.py
git commit -m "feat(auth): add AuthDB with users table and CRUD operations"
```

---

### Task 6: Auth Database — Paper Portfolio & Alert Cooldown Methods

**Files:**
- Modify: `src/ghostfolio_agent/auth/db.py`
- Modify: `tests/unit/test_auth_db.py`

**Step 1: Write tests for paper portfolio CRUD**

Append to `tests/unit/test_auth_db.py`:

```python
class TestPaperPortfolios:
    @pytest.mark.asyncio
    async def test_get_default_portfolio(self, db):
        """New user gets default $100K portfolio."""
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
        # Should get a fresh default since user no longer exists
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
        old_time = time.time() - 100_000  # well past 24h
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
```

**Step 2: Run tests to verify new ones fail**

Run: `uv run pytest tests/unit/test_auth_db.py -v -k "TestPaperPortfolios or TestAlertCooldowns"`
Expected: FAIL — methods not found

**Step 3: Add paper portfolio and cooldown methods to AuthDB**

Append to `AuthDB` class in `src/ghostfolio_agent/auth/db.py`:

```python
    # ── Paper Portfolios ───────────────────────────────────

    async def get_paper_portfolio(self, user_id: str) -> dict:
        cursor = await self._conn.execute(
            "SELECT cash, positions, trades FROM paper_portfolios WHERE user_id = ?",
            (user_id,),
        )
        row = await cursor.fetchone()
        if not row:
            return {"cash": 100_000.0, "positions": {}, "trades": []}
        import json
        return {
            "cash": row["cash"],
            "positions": json.loads(row["positions"]),
            "trades": json.loads(row["trades"]),
        }

    async def save_paper_portfolio(self, user_id: str, data: dict) -> None:
        import json
        now = datetime.now(timezone.utc).isoformat()
        await self._conn.execute(
            "INSERT INTO paper_portfolios (user_id, cash, positions, trades, created_at) "
            "VALUES (?, ?, ?, ?, ?) "
            "ON CONFLICT(user_id) DO UPDATE SET cash=?, positions=?, trades=?",
            (
                user_id, data["cash"], json.dumps(data["positions"]),
                json.dumps(data["trades"]), now,
                data["cash"], json.dumps(data["positions"]),
                json.dumps(data["trades"]),
            ),
        )
        await self._conn.commit()

    # ── Alert Cooldowns ────────────────────────────────────

    async def get_cooldowns(self, user_id: str) -> dict[str, float]:
        cursor = await self._conn.execute(
            "SELECT alert_key, fired_at FROM alert_cooldowns WHERE user_id = ?",
            (user_id,),
        )
        rows = await cursor.fetchall()
        return {row["alert_key"]: row["fired_at"] for row in rows}

    async def set_cooldown(self, user_id: str, alert_key: str, fired_at: float) -> None:
        await self._conn.execute(
            "INSERT INTO alert_cooldowns (user_id, alert_key, fired_at) "
            "VALUES (?, ?, ?) "
            "ON CONFLICT(user_id, alert_key) DO UPDATE SET fired_at=?",
            (user_id, alert_key, fired_at, fired_at),
        )
        await self._conn.commit()

    async def prune_cooldowns(self, user_id: str, ttl: int = 86400) -> None:
        import time
        cutoff = time.time() - ttl
        await self._conn.execute(
            "DELETE FROM alert_cooldowns WHERE user_id = ? AND fired_at < ?",
            (user_id, cutoff),
        )
        await self._conn.commit()
```

**Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/unit/test_auth_db.py -v`
Expected: All PASS

**Step 5: Run full test suite**

Run: `uv run pytest tests/unit/ -v`
Expected: All pass

**Step 6: Commit**

```bash
git add src/ghostfolio_agent/auth/db.py tests/unit/test_auth_db.py
git commit -m "feat(auth): add paper portfolio and alert cooldown methods to AuthDB"
```

---

### Task 7: Auth Middleware — FastAPI Dependency

**Files:**
- Create: `src/ghostfolio_agent/auth/middleware.py`
- Test: `tests/unit/test_auth_middleware.py`

**Step 1: Write middleware tests**

Create `tests/unit/test_auth_middleware.py`:

```python
"""Tests for auth middleware (FastAPI dependency)."""
import pytest
from unittest.mock import AsyncMock, patch

JWT_SECRET = "test-secret"


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
```

**Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/unit/test_auth_middleware.py -v`
Expected: FAIL — module not found

**Step 3: Implement middleware**

Create `src/ghostfolio_agent/auth/middleware.py`:

```python
"""FastAPI auth dependency — extracts and validates user from JWT."""
from fastapi import HTTPException

from ghostfolio_agent.auth.jwt import verify_token
from ghostfolio_agent.auth.db import AuthDB


async def get_current_user(
    authorization: str | None,
    jwt_secret: str,
    auth_db: AuthDB,
) -> dict:
    """Extract user from Authorization header. Raises 401 on failure.

    This is a building block — chat.py will wrap it in a FastAPI Depends()
    that injects jwt_secret and auth_db from app state.
    """
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing authorization header")
    token = authorization.removeprefix("Bearer ")
    try:
        payload = verify_token(token, jwt_secret)
    except ValueError:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    user = await auth_db.get_user(payload["user_id"])
    if not user:
        raise HTTPException(status_code=401, detail="User not found")
    return user
```

**Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/unit/test_auth_middleware.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add src/ghostfolio_agent/auth/middleware.py tests/unit/test_auth_middleware.py
git commit -m "feat(auth): add FastAPI auth middleware dependency"
```

---

### Task 8: Auth Endpoints — Login & Guest

**Files:**
- Create: `src/ghostfolio_agent/api/auth.py`
- Create: `tests/unit/test_auth_endpoints.py`

**Step 1: Write tests for auth endpoints**

Create `tests/unit/test_auth_endpoints.py`:

```python
"""Tests for /api/auth/* endpoints."""
import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from cryptography.fernet import Fernet

ENCRYPTION_KEY = Fernet.generate_key().decode()
JWT_SECRET = "test-jwt-secret"


@pytest.fixture
def mock_settings(monkeypatch):
    """Mock settings for auth endpoints."""
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
```

**Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/unit/test_auth_endpoints.py -v`
Expected: FAIL — module not found

**Step 3: Implement auth endpoints**

Create `src/ghostfolio_agent/api/auth.py`:

```python
"""Auth endpoints — login with Ghostfolio token or continue as guest."""
import httpx
import structlog
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from ghostfolio_agent.auth.db import AuthDB
from ghostfolio_agent.auth.jwt import create_token
from ghostfolio_agent.config import get_settings

logger = structlog.get_logger()

router = APIRouter()

_auth_db: AuthDB | None = None


async def _get_auth_db() -> AuthDB:
    global _auth_db
    if _auth_db is None:
        settings = get_settings()
        _auth_db = AuthDB("data/agent.db", settings.encryption_key)
        await _auth_db.init()
    return _auth_db


async def _validate_ghostfolio_token(token: str) -> bool:
    """Validate a Ghostfolio security token by calling the auth endpoint."""
    settings = get_settings()
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{settings.ghostfolio_base_url}/api/v1/auth/anonymous",
                json={"accessToken": token},
                timeout=10.0,
            )
            return resp.status_code == 201
    except Exception as e:
        logger.warning("ghostfolio_token_validation_failed", error=str(e))
        return False


class LoginRequest(BaseModel):
    ghostfolio_token: str


@router.post("/api/auth/login")
async def login(request: LoginRequest):
    """Validate Ghostfolio token, create/find user, return JWT."""
    is_valid = await _validate_ghostfolio_token(request.ghostfolio_token)
    if not is_valid:
        raise HTTPException(status_code=401, detail="Invalid Ghostfolio token")

    settings = get_settings()
    db = await _get_auth_db()

    # Determine role
    role = "admin" if request.ghostfolio_token == settings.ghostfolio_access_token else "user"

    # Find existing user or create new one
    existing = await db.find_user_by_token(request.ghostfolio_token)
    if existing:
        await db.update_last_login(existing["id"])
        user = existing
        # Update role in case admin token changed
        user["role"] = role
    else:
        user = await db.create_user(ghostfolio_token=request.ghostfolio_token, role=role)

    jwt = create_token(user["id"], user["role"], settings.jwt_secret)
    return {"token": jwt, "role": user["role"], "user_id": user["id"]}


@router.post("/api/auth/guest")
async def guest_login():
    """Create ephemeral guest user and return JWT."""
    settings = get_settings()
    db = await _get_auth_db()
    user = await db.create_user(ghostfolio_token=None, role="guest")
    jwt = create_token(user["id"], user["role"], settings.jwt_secret)
    return {"token": jwt, "role": user["role"], "user_id": user["id"]}
```

**Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/unit/test_auth_endpoints.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add src/ghostfolio_agent/api/auth.py tests/unit/test_auth_endpoints.py
git commit -m "feat(auth): add login and guest auth endpoints"
```

---

### Task 9: Wire Auth Into Main App & Chat Router

**Files:**
- Modify: `src/ghostfolio_agent/api/main.py`
- Modify: `src/ghostfolio_agent/api/chat.py`
- Modify: `src/ghostfolio_agent/models/api.py`

This task wires auth into the existing app. The key changes:

1. Register auth router in main.py
2. Add auth dependency to chat.py endpoints
3. Replace singleton `_get_client()` with per-user client creation
4. Scope thread_id with user_id
5. Pass user context to alert engine

**Step 1: Add auth router to main.py**

In `src/ghostfolio_agent/api/main.py`, add import and router registration:

After the line `from ghostfolio_agent.api.chat import router as chat_router`, add:
```python
from ghostfolio_agent.api.auth import router as auth_router
```

After `app.include_router(chat_router)`, add:
```python
app.include_router(auth_router)
```

In the `lifespan` function, add auth DB initialization before `yield`:
```python
    from ghostfolio_agent.api.auth import _get_auth_db
    await _get_auth_db()
```

**Step 2: Add `user_id` to ChatRequest model**

In `src/ghostfolio_agent/models/api.py`, the ChatRequest doesn't need user_id — the user is extracted from the JWT header. No model changes needed here.

**Step 3: Add auth dependency to chat.py**

In `src/ghostfolio_agent/api/chat.py`:

Add imports at top:
```python
from fastapi import APIRouter, HTTPException, Header
from ghostfolio_agent.auth.middleware import get_current_user
from ghostfolio_agent.api.auth import _get_auth_db
```

Add a helper to extract user from request:
```python
async def _require_user(authorization: str | None = Header(None)) -> dict:
    """FastAPI dependency — extracts authenticated user from JWT."""
    settings = get_settings()
    if not settings.jwt_secret:
        # Auth disabled (no JWT_SECRET configured) — return a default admin user
        return {"id": "default", "role": "admin"}
    db = await _get_auth_db()
    return await get_current_user(authorization, settings.jwt_secret, db)
```

**Step 4: Update chat endpoint to use per-user Ghostfolio client**

Replace the `_get_client()` singleton usage. Add a function to create per-user client:

```python
async def _get_user_client(user: dict) -> GhostfolioClient | None:
    """Get GhostfolioClient for the given user. Returns None for guests."""
    if user["role"] == "guest":
        return None
    if user["id"] == "default":
        # Auth disabled — use env token
        settings = get_settings()
        return GhostfolioClient(
            base_url=settings.ghostfolio_base_url,
            access_token=settings.ghostfolio_access_token,
        )
    db = await _get_auth_db()
    token = await db.get_decrypted_token(user["id"])
    if not token:
        return None
    settings = get_settings()
    return GhostfolioClient(base_url=settings.ghostfolio_base_url, access_token=token)
```

Update the `chat` endpoint signature to include user:
```python
@router.post("/api/chat", response_model=ChatResponse)
async def chat(request: ChatRequest, user: dict = Depends(_require_user)):
```

Inside the chat endpoint:
- Replace `_get_client()` with `await _get_user_client(user)`
- Replace `config = {"configurable": {"thread_id": request.session_id}, ...}` with:
  ```python
  config = {
      "configurable": {
          "thread_id": f"{user['id']}:{request.session_id}",
          "user_id": user["id"],
          "user_role": user["role"],
      },
      "recursion_limit": 25,
  }
  ```
- Update `_get_agent()` to accept optional client (None for guests)
- Pass user to alert engine check

Update portfolio endpoint:
```python
@router.get("/api/portfolio", response_model=PortfolioResponse)
async def get_portfolio(user: dict = Depends(_require_user)):
    if user["role"] == "guest":
        raise HTTPException(status_code=403, detail="Connect your Ghostfolio portfolio to access this feature.")
    client = await _get_user_client(user)
    if not client:
        raise HTTPException(status_code=403, detail="No portfolio connected.")
    # ... rest unchanged, but use `client` from above instead of `_get_client()`
```

Update paper portfolio endpoint:
```python
@router.get("/api/paper-portfolio", response_model=PaperPortfolioResponse)
async def get_paper_portfolio(user: dict = Depends(_require_user)):
    # Use user["id"] to load from DB instead of file
    db = await _get_auth_db()
    portfolio = await db.get_paper_portfolio(user["id"])
    # ... rest of the logic stays similar, but reads from db result
```

**Step 5: Update `_get_agent` to accept optional client**

The agent creation needs to handle `client=None` for guests. Modify `_get_agent`:

```python
async def _get_agent(model_name: str, client: GhostfolioClient | None):
    # Cache key includes whether client is present (guest vs non-guest)
    cache_key = f"{model_name}:{'guest' if client is None else 'auth'}"
    if cache_key not in _agents:
        settings = get_settings()
        checkpointer = await _get_checkpointer()
        _agents[cache_key] = create_agent(
            client,  # Can be None for guests
            openrouter_api_key=settings.openrouter_api_key,
            openai_api_key=settings.openai_api_key,
            model_name=model_name,
            checkpointer=checkpointer,
            max_context_messages=settings.max_context_messages,
            finnhub=_get_finnhub(),
            alpha_vantage=_get_alpha_vantage(),
            fmp=_get_fmp(),
            congressional=_get_congressional(),
        )
    return _agents[cache_key]
```

**Note:** The tools/__init__.py `create_tools` and graph.py `create_agent` will need to handle `client=None` — tools that require Ghostfolio client are excluded for guests. This is covered in Task 10.

**Step 6: Run full test suite**

Run: `uv run pytest tests/unit/ -v`
Expected: Some tests may need updating due to changed signatures. Fix as needed.

**Step 7: Commit**

```bash
git add src/ghostfolio_agent/api/main.py src/ghostfolio_agent/api/chat.py src/ghostfolio_agent/models/api.py
git commit -m "feat(auth): wire auth into main app, per-user clients, scoped sessions"
```

---

### Task 10: Update Tools & Graph for Guest Mode

**Files:**
- Modify: `src/ghostfolio_agent/tools/__init__.py`
- Modify: `src/ghostfolio_agent/agent/graph.py`
- Modify: `src/ghostfolio_agent/tools/paper_trade.py`

**Step 1: Update `create_tools` to handle `client=None`**

In `src/ghostfolio_agent/tools/__init__.py`, modify `create_tools`:

```python
def create_tools(
    client: GhostfolioClient | None,  # ← now optional
    finnhub=None, alpha_vantage=None, fmp=None, congressional=None,
) -> list:
    tools = []

    # Ghostfolio-dependent tools — only if client provided
    if client is not None:
        tools.extend([
            create_portfolio_summary_tool(client),
            create_portfolio_performance_tool(client),
            create_transaction_history_tool(client),
            create_holding_detail_tool(client, finnhub=finnhub, alpha_vantage=alpha_vantage, fmp=fmp, congressional=congressional),
            create_risk_analysis_tool(client),
            create_symbol_lookup_tool(client),
            create_activity_log_tool(client),
            create_benchmark_comparison_tool(client),
            create_paper_trade_tool(client),
            create_morning_briefing_tool(client, finnhub=finnhub, alpha_vantage=alpha_vantage, fmp=fmp, congressional=congressional),
        ])
    else:
        # Guest mode — paper trade without real portfolio lookup
        tools.append(create_paper_trade_tool(None))

    # Research tools — always available (no Ghostfolio needed)
    if finnhub:
        tools.append(create_stock_quote_tool(finnhub=finnhub))
    if finnhub or alpha_vantage or fmp:
        tools.append(create_conviction_score_tool(finnhub=finnhub, alpha_vantage=alpha_vantage, fmp=fmp, congressional=congressional))

    if congressional is not None:
        tools.extend([
            create_congressional_trades_tool(congressional),
            create_congressional_trades_summary_tool(congressional),
            create_congressional_members_tool(congressional),
        ])

    return tools
```

**Step 2: Update graph.py `create_agent` to accept optional client**

In `src/ghostfolio_agent/agent/graph.py`, change the signature:

```python
def create_agent(
    client: GhostfolioClient | None,  # ← now optional
    ...
)
```

**Step 3: Update paper_trade.py to work with AuthDB**

The paper trade tool needs to read/write from SQLite via user_id instead of the global JSON file. This requires passing user_id through the tool context.

In `src/ghostfolio_agent/tools/paper_trade.py`:

Add a way to get user_id from LangGraph config. The tool function receives `config` via LangChain's `RunnableConfig`:

```python
from langchain_core.runnables import RunnableConfig

def create_paper_trade_tool(client: GhostfolioClient | None):
    @tool
    async def paper_trade(action: str, config: RunnableConfig) -> str:
        """Execute paper trades or view paper portfolio."""
        user_id = config.get("configurable", {}).get("user_id", "default")
        # Use AuthDB instead of file I/O
        from ghostfolio_agent.api.auth import _get_auth_db
        db = await _get_auth_db()
        portfolio = await db.get_paper_portfolio(user_id)
        # ... rest of logic stays same but uses db.save_paper_portfolio(user_id, portfolio)
```

**Important:** Keep the old file-based functions (`load_portfolio`, `_save_portfolio`) temporarily for backwards compatibility during migration. Mark them as deprecated.

**Step 4: Run full test suite, fix broken tests**

Run: `uv run pytest tests/unit/ -v`

Paper trade tests will need updating to mock AuthDB instead of file paths. Update `tests/unit/test_paper_trade.py` fixtures to use the new DB path.

**Step 5: Commit**

```bash
git add src/ghostfolio_agent/tools/__init__.py src/ghostfolio_agent/agent/graph.py src/ghostfolio_agent/tools/paper_trade.py
git commit -m "feat(auth): update tools and graph for guest mode, per-user paper trade"
```

---

### Task 11: Update Alert Engine for Per-User Cooldowns

**Files:**
- Modify: `src/ghostfolio_agent/alerts/engine.py`
- Modify: `tests/unit/test_alert_engine.py`

**Step 1: Add user_id parameter to AlertEngine**

The AlertEngine needs to use AuthDB for cooldowns instead of the JSON file. Modify `check_alerts` to accept `user_id`:

```python
class AlertEngine:
    def __init__(self, auth_db: AuthDB | None = None) -> None:
        self._auth_db = auth_db
        # Keep in-memory fallback for backwards compat / testing
        self._fired: dict[str, float] = {}

    async def _is_cooled_down(self, user_id: str, key: str) -> bool:
        if self._auth_db:
            cooldowns = await self._auth_db.get_cooldowns(user_id)
            fired_at = cooldowns.get(key)
        else:
            fired_at = self._fired.get(key)
        if fired_at is None:
            return True
        return (time.time() - fired_at) > COOLDOWN_TTL

    async def _record(self, user_id: str, key: str) -> None:
        now = time.time()
        if self._auth_db:
            await self._auth_db.set_cooldown(user_id, key, now)
            await self._auth_db.prune_cooldowns(user_id, COOLDOWN_TTL)
        else:
            self._fired[key] = now

    async def check_alerts(
        self,
        client: GhostfolioClient,
        *,
        user_id: str = "default",
        finnhub=None, alpha_vantage=None, fmp=None, congressional=None,
    ) -> list[AlertResult]:
        # ... existing logic but pass user_id to _is_cooled_down and _record
```

**Step 2: Update tests**

Update `tests/unit/test_alert_engine.py` to use the async versions of `_is_cooled_down` and `_record`. Tests that call `self.engine._is_cooled_down("key")` become `await self.engine._is_cooled_down("default", "key")`.

**Step 3: Update chat.py to pass user_id to alert engine**

In chat.py, where alerts are checked:
```python
alerts = await alert_engine.check_alerts(
    client,
    user_id=user["id"],
    finnhub=_get_finnhub(),
    ...
)
```

**Step 4: Run full test suite**

Run: `uv run pytest tests/unit/ -v`
Expected: All pass

**Step 5: Commit**

```bash
git add src/ghostfolio_agent/alerts/engine.py tests/unit/test_alert_engine.py src/ghostfolio_agent/api/chat.py
git commit -m "feat(auth): per-user alert cooldowns via AuthDB"
```

---

### Task 12: Cache Isolation for User-Scoped Tools

**Files:**
- Modify: `src/ghostfolio_agent/utils/cache.py` (or `src/ghostfolio_agent/tools/cache.py`)

**Step 1: Update ttl_cache to support user_id in key**

The cache key is currently `(args, tuple(sorted(kwargs.items())))`. For tools that receive `config: RunnableConfig`, the user_id should be part of the key automatically since it's in the config.

However, the simpler approach: tools that use per-user data (portfolio_summary, holding_detail, etc.) are already re-created per agent instance. Since we cache agents by `{model}:guest` vs `{model}:auth`, and each tool closure captures a different `GhostfolioClient` per user token, the cache is already scoped by the client's token.

**Wait — the agent is cached per model+role-type, not per user.** So User A and User B both get the same `{model}:auth` agent with the same tools. The tools use closure-captured client, but the client is from the first user who triggered agent creation.

**Fix:** Don't cache agents per role-type. Instead, create agents per-request (or per user_id). Since `create_agent` is lightweight (just wiring), this is fine:

In chat.py, remove the `_agents` cache and create the agent per request:

```python
async def _create_agent_for_user(model_name: str, client: GhostfolioClient | None):
    settings = get_settings()
    checkpointer = await _get_checkpointer()
    return create_agent(
        client,
        openrouter_api_key=settings.openrouter_api_key,
        openai_api_key=settings.openai_api_key,
        model_name=model_name,
        checkpointer=checkpointer,
        max_context_messages=settings.max_context_messages,
        finnhub=_get_finnhub(),
        alpha_vantage=_get_alpha_vantage(),
        fmp=_get_fmp(),
        congressional=_get_congressional(),
    )
```

**Alternative (better performance):** Cache agents per `{user_id}:{model}` with an LRU eviction. But for now, per-request creation is simplest and correct.

Also clear tool-level `@ttl_cache` entries that contain user-specific data. The cleanest approach: add `user_id` as a parameter to user-scoped tools so the cache key naturally includes it.

**Step 2: Run full test suite**

Run: `uv run pytest tests/unit/ -v`
Expected: All pass

**Step 3: Commit**

```bash
git add src/ghostfolio_agent/api/chat.py
git commit -m "fix(auth): create agent per-request to isolate user data"
```

---

### Task 13: Frontend — useAuth Hook

**Files:**
- Create: `frontend/src/hooks/useAuth.ts`

**Step 1: Implement useAuth hook**

Create `frontend/src/hooks/useAuth.ts`:

```typescript
import { useState, useCallback, useEffect } from 'react'

const AUTH_KEY = 'ghostfolio-auth'

interface AuthState {
  jwt: string
  role: 'admin' | 'user' | 'guest'
  userId: string
}

export function useAuth() {
  const [auth, setAuth] = useState<AuthState | null>(() => {
    const stored = localStorage.getItem(AUTH_KEY)
    return stored ? JSON.parse(stored) : null
  })

  const login = useCallback(async (ghostfolioToken: string) => {
    const resp = await fetch('/api/auth/login', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ ghostfolio_token: ghostfolioToken }),
    })
    if (!resp.ok) {
      const err = await resp.json().catch(() => ({ detail: 'Login failed' }))
      throw new Error(err.detail || 'Login failed')
    }
    const data = await resp.json()
    const state: AuthState = { jwt: data.token, role: data.role, userId: data.user_id }
    localStorage.setItem(AUTH_KEY, JSON.stringify(state))
    setAuth(state)
    return state
  }, [])

  const loginAsGuest = useCallback(async () => {
    const resp = await fetch('/api/auth/guest', { method: 'POST' })
    if (!resp.ok) throw new Error('Guest login failed')
    const data = await resp.json()
    const state: AuthState = { jwt: data.token, role: data.role, userId: data.user_id }
    localStorage.setItem(AUTH_KEY, JSON.stringify(state))
    setAuth(state)
    return state
  }, [])

  const logout = useCallback(() => {
    localStorage.removeItem(AUTH_KEY)
    localStorage.removeItem('ghostfolio-session-id')
    setAuth(null)
  }, [])

  return {
    auth,
    isAuthenticated: auth !== null,
    isGuest: auth?.role === 'guest',
    isAdmin: auth?.role === 'admin',
    login,
    loginAsGuest,
    logout,
  }
}
```

**Step 2: Verify TypeScript compiles**

Run: `cd frontend && npx tsc -b --noEmit`
Expected: No errors

**Step 3: Commit**

```bash
git add frontend/src/hooks/useAuth.ts
git commit -m "feat(auth): add useAuth hook for frontend auth state"
```

---

### Task 14: Frontend — LoginScreen Component

**Files:**
- Create: `frontend/src/components/Auth/LoginScreen.tsx`

**Step 1: Implement LoginScreen**

Create `frontend/src/components/Auth/LoginScreen.tsx`:

```tsx
import { useState } from 'react'

interface LoginScreenProps {
  onLogin: (token: string) => Promise<void>
  onGuestLogin: () => Promise<void>
}

export function LoginScreen({ onLogin, onGuestLogin }: LoginScreenProps) {
  const [token, setToken] = useState('')
  const [error, setError] = useState('')
  const [isLoading, setIsLoading] = useState(false)

  const handleLogin = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!token.trim()) return
    setIsLoading(true)
    setError('')
    try {
      await onLogin(token.trim())
    } catch (err: any) {
      setError(err.message || 'Login failed')
    } finally {
      setIsLoading(false)
    }
  }

  const handleGuest = async () => {
    setIsLoading(true)
    setError('')
    try {
      await onGuestLogin()
    } catch (err: any) {
      setError(err.message || 'Guest login failed')
    } finally {
      setIsLoading(false)
    }
  }

  return (
    <div className="min-h-screen flex items-center justify-center bg-gradient-to-br from-slate-50 to-slate-100">
      <div className="w-full max-w-md px-6">
        <div className="text-center mb-8">
          <h1 className="text-3xl font-bold text-slate-900">AgentForge</h1>
          <p className="text-slate-500 mt-2">AI-powered portfolio assistant</p>
        </div>

        <div className="bg-white rounded-2xl shadow-sm border border-slate-200 p-8">
          <form onSubmit={handleLogin} className="space-y-4">
            <div>
              <label htmlFor="token" className="block text-sm font-medium text-slate-700 mb-1">
                Ghostfolio Security Token
              </label>
              <input
                id="token"
                type="password"
                value={token}
                onChange={(e) => setToken(e.target.value)}
                placeholder="Paste your token here"
                className="w-full px-4 py-3 rounded-xl border border-slate-200 focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:border-transparent text-sm"
                disabled={isLoading}
              />
              <p className="text-xs text-slate-400 mt-1">
                Find this in your Ghostfolio account under Settings → Security
              </p>
            </div>

            {error && (
              <p className="text-sm text-red-600 bg-red-50 rounded-lg px-3 py-2">{error}</p>
            )}

            <button
              type="submit"
              disabled={isLoading || !token.trim()}
              className="w-full py-3 rounded-xl bg-indigo-600 text-white font-medium hover:bg-indigo-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors text-sm"
            >
              {isLoading ? 'Connecting...' : 'Connect Portfolio'}
            </button>
          </form>

          <div className="relative my-6">
            <div className="absolute inset-0 flex items-center">
              <div className="w-full border-t border-slate-200" />
            </div>
            <div className="relative flex justify-center text-xs">
              <span className="bg-white px-3 text-slate-400">or</span>
            </div>
          </div>

          <button
            onClick={handleGuest}
            disabled={isLoading}
            className="w-full py-3 rounded-xl border border-slate-200 text-slate-600 font-medium hover:bg-slate-50 disabled:opacity-50 transition-colors text-sm"
          >
            Continue as Guest
          </button>
          <p className="text-xs text-slate-400 text-center mt-2">
            Paper trading & research tools — no portfolio needed
          </p>
        </div>
      </div>
    </div>
  )
}
```

**Step 2: Verify TypeScript compiles**

Run: `cd frontend && npx tsc -b --noEmit`
Expected: No errors

**Step 3: Commit**

```bash
git add frontend/src/components/Auth/LoginScreen.tsx
git commit -m "feat(auth): add LoginScreen component with token input and guest mode"
```

---

### Task 15: Frontend — Wire Auth Into App.tsx and API

**Files:**
- Modify: `frontend/src/App.tsx`
- Modify: `frontend/src/api/chat.ts`
- Modify: `frontend/src/hooks/useChat.ts`
- Modify: `frontend/src/hooks/useSidebar.ts`
- Modify: `frontend/src/components/Sidebar/Sidebar.tsx`

**Step 1: Update chat.ts to include auth headers**

In `frontend/src/api/chat.ts`, add JWT to all requests:

```typescript
function getAuthHeader(): Record<string, string> {
  const stored = localStorage.getItem('ghostfolio-auth')
  if (!stored) return {}
  const { jwt } = JSON.parse(stored)
  return jwt ? { Authorization: `Bearer ${jwt}` } : {}
}
```

Update `postChat`:
```typescript
const resp = await fetch('/api/chat', {
  method: 'POST',
  headers: { 'Content-Type': 'application/json', ...getAuthHeader() },
  body: JSON.stringify(request),
})
```

Update `fetchPortfolio` and `fetchPaperPortfolio` similarly — add `headers: getAuthHeader()` to each fetch call.

Handle 401 responses — if any API call returns 401, clear auth state:
```typescript
if (resp.status === 401) {
  localStorage.removeItem('ghostfolio-auth')
  window.location.reload()
  throw new ChatError('Session expired', 'server')
}
```

**Step 2: Update App.tsx with auth gate**

In `frontend/src/App.tsx`:

```tsx
import { useAuth } from './hooks/useAuth'
import { LoginScreen } from './components/Auth/LoginScreen'

function App() {
  const auth = useAuth()

  if (!auth.isAuthenticated) {
    return (
      <LoginScreen
        onLogin={async (token) => { await auth.login(token) }}
        onGuestLogin={async () => { await auth.loginAsGuest() }}
      />
    )
  }

  // ... existing app content, with minor additions:
  // - Pass auth.isGuest to sidebar for conditional rendering
  // - Add logout button somewhere in the UI
  // - If guest, force paper trading mode
}
```

For guests, auto-enable paper trading:
```typescript
const [isPaperTrading, setIsPaperTrading] = useState(auth.isGuest ? true : false)
```

**Step 3: Update Sidebar for guest mode**

In `frontend/src/components/Sidebar/Sidebar.tsx`, add `isGuest` prop:

When `isGuest` is true:
- Hide the real portfolio section
- Show a CTA card: "Connect your Ghostfolio portfolio for real-time tracking"
- Paper portfolio section shown as normal

**Step 4: Add logout button**

Add a small logout button/link in the sidebar footer or header area:
```tsx
<button onClick={auth.logout} className="text-xs text-slate-400 hover:text-slate-600">
  {auth.isGuest ? 'Exit Guest Mode' : 'Sign Out'}
</button>
```

**Step 5: Verify build**

Run: `cd frontend && npx tsc -b --noEmit && npx vite build`
Expected: No errors

**Step 6: Run backend tests**

Run: `uv run pytest tests/unit/ -v`
Expected: All pass

**Step 7: Commit**

```bash
git add frontend/src/
git commit -m "feat(auth): wire auth into frontend — login gate, auth headers, guest mode"
```

---

### Task 16: Generate Encryption & JWT Keys, Update .env

**Files:**
- Modify: `.env` (add new variables)
- Modify: `.env.example` (if exists)

**Step 1: Generate keys**

```bash
python3 -c "from cryptography.fernet import Fernet; print(f'ENCRYPTION_KEY={Fernet.generate_key().decode()}')"
python3 -c "import secrets; print(f'JWT_SECRET={secrets.token_urlsafe(32)}')"
```

**Step 2: Add to .env**

Add the generated values to `.env`:
```
ENCRYPTION_KEY=<generated-fernet-key>
JWT_SECRET=<generated-jwt-secret>
```

**Step 3: Do NOT commit .env** — it's in .gitignore

---

### Task 17: Migration Script for Existing Data

**Files:**
- Create: `scripts/migrate_to_auth.py`

**Step 1: Write migration script**

This script migrates existing file-based data into the new SQLite auth database for the admin user:

```python
"""One-time migration: import existing data into auth DB for admin user."""
import asyncio
import json
from pathlib import Path

from ghostfolio_agent.auth.db import AuthDB
from ghostfolio_agent.config import get_settings


async def migrate():
    settings = get_settings()
    db = AuthDB("data/agent.db", settings.encryption_key)
    await db.init()

    # Create admin user with env token
    admin = await db.find_user_by_token(settings.ghostfolio_access_token)
    if not admin:
        admin = await db.create_user(
            ghostfolio_token=settings.ghostfolio_access_token, role="admin"
        )
    admin_id = admin["id"]
    print(f"Admin user: {admin_id}")

    # Migrate paper portfolio
    paper_file = Path("data/paper_portfolio.json")
    if paper_file.exists():
        data = json.loads(paper_file.read_text())
        await db.save_paper_portfolio(admin_id, data)
        print(f"Migrated paper portfolio: ${data['cash']:.2f} cash, {len(data.get('positions', {}))} positions")

    # Migrate alert cooldowns
    cooldown_file = Path("data/alert_cooldowns.json")
    if cooldown_file.exists():
        cooldowns = json.loads(cooldown_file.read_text())
        for key, fired_at in cooldowns.items():
            await db.set_cooldown(admin_id, key, fired_at)
        print(f"Migrated {len(cooldowns)} alert cooldowns")

    await db.close()
    print("Migration complete.")


if __name__ == "__main__":
    asyncio.run(migrate())
```

**Step 2: Commit**

```bash
git add scripts/migrate_to_auth.py
git commit -m "feat(auth): add migration script for existing data to auth DB"
```

---

### Task 18: Integration Testing & Cleanup

**Step 1: Run full test suite**

Run: `uv run pytest tests/unit/ -v`
Expected: All pass

**Step 2: Build frontend**

Run: `cd frontend && npx vite build`
Expected: Build succeeds

**Step 3: Manual smoke test**

1. Start backend: `uv run uvicorn ghostfolio_agent.api.main:app --reload`
2. Open browser → should see LoginScreen
3. Click "Continue as Guest" → should enter app with paper trading mode
4. Paste Ghostfolio token → should enter app with full portfolio
5. Verify chat works, sidebar shows portfolio, paper trading works

**Step 4: Remove old file-based code (after migration confirmed working)**

- Remove `_DATA_FILE`, `_LOCK_FILE`, file-based `load_portfolio`, `_save_portfolio` from `paper_trade.py`
- Remove file-based cooldown persistence from `alerts/engine.py`
- Remove old `data/paper_portfolio.json`, `data/alert_cooldowns.json` (after migration)

**Step 5: Final commit**

```bash
git add -A
git commit -m "feat(auth): multi-user authentication with JWT, encrypted tokens, guest mode"
```

---

## Task Dependency Graph

```
Task 1 (deps) → Task 2 (config) → Task 3 (encryption) → Task 4 (JWT)
                                         ↓
                                    Task 5 (users DB) → Task 6 (portfolio/cooldown DB)
                                         ↓
                                    Task 7 (middleware) → Task 8 (auth endpoints)
                                         ↓
                                    Task 9 (wire into chat.py) → Task 10 (tools/graph)
                                         ↓                            ↓
                                    Task 11 (alert engine)      Task 12 (cache isolation)
                                         ↓
                              Task 13-15 (frontend) ← can be parallel with backend tasks 9-12
                                         ↓
                              Task 16 (env keys) → Task 17 (migration) → Task 18 (integration)
```

**Parallelizable:**
- Tasks 3 + 4 (encryption + JWT) — independent modules
- Tasks 13 + 14 (useAuth + LoginScreen) — independent frontend components
- Frontend tasks (13-15) can run in parallel with backend tasks (9-12) since they're different codebases
