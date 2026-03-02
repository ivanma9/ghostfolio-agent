"""Auth database — users, paper portfolios, alert cooldowns in SQLite."""
import hashlib
import json
import time
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
        self._conn = await aiosqlite.connect(self._db_path)
        self._conn.row_factory = aiosqlite.Row
        await self._conn.execute("PRAGMA foreign_keys = ON")
        await self._conn.executescript(_SCHEMA)

    async def close(self) -> None:
        if self._conn:
            await self._conn.close()

    # ── Users ──────────────────────────────────────────────

    async def create_user(self, *, ghostfolio_token: str | None, role: str) -> dict:
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

    # ── Paper Portfolios ───────────────────────────────────

    async def get_paper_portfolio(self, user_id: str) -> dict:
        cursor = await self._conn.execute(
            "SELECT cash, positions, trades FROM paper_portfolios WHERE user_id = ?",
            (user_id,),
        )
        row = await cursor.fetchone()
        if not row:
            return {"cash": 100_000.0, "positions": {}, "trades": []}
        return {
            "cash": row["cash"],
            "positions": json.loads(row["positions"]),
            "trades": json.loads(row["trades"]),
        }

    async def save_paper_portfolio(self, user_id: str, data: dict) -> None:
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
        cutoff = time.time() - ttl
        await self._conn.execute(
            "DELETE FROM alert_cooldowns WHERE user_id = ? AND fired_at < ?",
            (user_id, cutoff),
        )
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
