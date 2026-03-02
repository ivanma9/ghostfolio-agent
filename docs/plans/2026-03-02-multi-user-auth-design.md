# Multi-User Authentication Design

**Date:** 2026-03-02
**Status:** Approved

## Problem

AgentForge currently runs as a single-user app. One Ghostfolio token in `.env`, one shared paper portfolio, one alert cooldown file, no authentication. Multiple users see the same portfolio and interfere with each other's paper trades.

## Solution

Add lightweight authentication with three user types, per-user data isolation, and a guest mode for frictionless access.

## User Types

| Type | How they get in | What they access |
|------|----------------|------------------|
| **Admin** | Ghostfolio token in `.env` matches their login | Full real portfolio + paper trading + all tools |
| **User** | Pastes their Ghostfolio security token once | Their own real portfolio + paper trading + all tools |
| **Guest** | Clicks "Continue as Guest" | Paper trading + research tools only. Ephemeral — no persistence across visits. |

## Auth Flow

1. User opens app → frontend checks localStorage for JWT
2. No JWT → login screen with token field + "Continue as Guest" button
3. **Token login:**
   - User pastes Ghostfolio security token
   - Backend calls `POST /api/v1/auth/anonymous` on Ghostfolio to validate
   - If valid → create/find user in SQLite, encrypt & store token, issue JWT
   - Admin auto-detected: if token matches `GHOSTFOLIO_ACCESS_TOKEN` from `.env`, role = admin
4. **Guest login:**
   - Backend creates ephemeral user (role=guest, no Ghostfolio token)
   - Issues JWT with guest role
5. JWT stored in localStorage, sent via `Authorization: Bearer {jwt}` on every request
6. Backend middleware extracts user from JWT on every request (except `/api/auth/*` and `/api/health`)

**JWT payload:** `{ user_id, role: "admin" | "user" | "guest", exp }`

## Database Schema

Single SQLite database: `data/agent.db`

```sql
CREATE TABLE users (
    id              TEXT PRIMARY KEY,   -- UUID
    ghostfolio_token BLOB,              -- AES-256 encrypted, NULL for guests
    role            TEXT NOT NULL,       -- 'admin' | 'user' | 'guest'
    created_at      TEXT NOT NULL,
    last_login_at   TEXT NOT NULL
);

CREATE TABLE paper_portfolios (
    user_id    TEXT PRIMARY KEY REFERENCES users(id),
    cash       REAL NOT NULL DEFAULT 100000.0,
    positions  TEXT NOT NULL DEFAULT '{}',
    trades     TEXT NOT NULL DEFAULT '[]',
    created_at TEXT NOT NULL
);

CREATE TABLE alert_cooldowns (
    user_id   TEXT NOT NULL REFERENCES users(id),
    alert_key TEXT NOT NULL,
    fired_at  REAL NOT NULL,
    PRIMARY KEY (user_id, alert_key)
);
```

**Token encryption:** AES-256 with key from `ENCRYPTION_KEY` in `.env`. Tokens must be decryptable (not hashed) since we need them for Ghostfolio API calls.

**Chat history:** Existing `checkpoints.db` unchanged. Thread ID becomes `{user_id}:{session_id}` to scope conversations per user.

## Per-User Data Isolation

### Fully isolated per user
- **Real portfolio** — different Ghostfolio tokens = different API responses at the source
- **Paper portfolio** — separate SQLite rows per user_id
- **Alert cooldowns** — scoped by user_id in SQLite
- **Chat history** — thread_id prefixed with user_id

### Shared across all users (by design)
- 3rd party API keys (Finnhub, Alpha Vantage, FMP, Congressional)
- LLM API key
- Tool TTL caches (with exception below)

### Cache isolation

In-memory `@ttl_cache` is keyed by function args. Tools that return Ghostfolio user-specific data must include `user_id` in cache keys to prevent cross-user leaks.

**Needs user-scoped cache keys:**
- `portfolio_summary`, `portfolio_performance`, `transaction_history`
- `holding_detail`, `benchmark_comparison`, `morning_briefing`

**Safe to share cache (external data only):**
- `stock_quote`, `conviction_score`, `symbol_lookup`
- `congressional_trades`, `congressional_trades_summary`, `congressional_members`

## Backend Changes

### New files

#### `src/ghostfolio_agent/auth/` module
- **`db.py`** — SQLite connection pool, table creation, CRUD:
  - `init_db()` — create tables if not exist
  - `create_user(ghostfolio_token, role)` → User
  - `get_user(user_id)` → User | None
  - `get_user_by_token_hash(token_hash)` → User | None (for dedup on login)
  - `update_last_login(user_id)`
  - `delete_user(user_id)` (for guest cleanup)
  - Paper portfolio CRUD: `get_paper_portfolio(user_id)`, `upsert_paper_portfolio(user_id, data)`
  - Alert cooldown CRUD: `get_cooldowns(user_id)`, `set_cooldown(user_id, key, timestamp)`, `prune_cooldowns(user_id, ttl)`
- **`jwt.py`** — JWT creation & verification using PyJWT:
  - `create_token(user_id, role)` → JWT string (24h expiry)
  - `verify_token(token)` → `{ user_id, role }` or raise
  - Secret from `JWT_SECRET` in `.env`
- **`middleware.py`** — FastAPI dependency:
  - `get_current_user(authorization: str = Header(None))` → User
  - Decodes JWT, looks up user in DB, returns User object
  - Guest JWT returns User with role=guest, ghostfolio_token=None
- **`encryption.py`** — AES-256 encrypt/decrypt for Ghostfolio tokens:
  - `encrypt_token(plaintext, key)` → bytes
  - `decrypt_token(ciphertext, key)` → str
  - Key from `ENCRYPTION_KEY` in `.env`

### Modified files

#### `config.py`
- Add `encryption_key: str` and `jwt_secret: str` settings

#### `api/chat.py`
- **Remove** singleton `_get_client()` pattern
- **Add** per-request Ghostfolio client creation:
  - Admin/User: decrypt token from DB, create `GhostfolioClient` per request
  - Guest: no Ghostfolio client (skip real portfolio tools)
- **Add** auth endpoints:
  - `POST /api/auth/login` — validate Ghostfolio token, create/find user, return JWT
  - `POST /api/auth/guest` — create ephemeral guest user, return JWT
- **Add** auth dependency to all existing endpoints (except auth + health)
- **Pass** user_id to tools that need it via tool kwargs or config

#### `tools/paper_trade.py`
- Replace file I/O with SQLite queries via `auth.db` functions
- Accept `user_id` parameter
- Remove filelock (SQLite handles concurrency)

#### `alerts/engine.py`
- Replace file I/O with SQLite queries via `auth.db` functions
- `check_alerts(user_id, ...)` — scope cooldowns by user
- Remove filelock

#### `main.py`
- Init auth DB on startup (`init_db()`)
- No other middleware changes (auth is a FastAPI dependency, not middleware)

### Tool user_id propagation

Tools receive user context via LangGraph config. In `chat.py`, the agent config becomes:

```python
config = {
    "configurable": {
        "thread_id": f"{user.id}:{request.session_id}",
        "user_id": user.id,
        "user_role": user.role,
    },
    "recursion_limit": 25,
}
```

Tools that need user_id extract it from `config["configurable"]["user_id"]`.

Guest-restricted tools (real portfolio) check `user_role` and return a helpful message like "Connect your Ghostfolio portfolio to access this feature."

## Frontend Changes

### New files

#### `frontend/src/components/Auth/LoginScreen.tsx`
- Token input field with "Connect Portfolio" button
- "Continue as Guest" button
- Error display for invalid tokens
- Clean, minimal design

#### `frontend/src/hooks/useAuth.ts`
- Manages `{ jwt, role, userId }` in localStorage
- `login(token)` → calls `/api/auth/login`, stores JWT
- `loginAsGuest()` → calls `/api/auth/guest`, stores JWT
- `logout()` → clears JWT, returns to login screen
- `isAuthenticated` / `isGuest` / `isAdmin` computed properties

### Modified files

#### `frontend/src/App.tsx`
- Auth gate: no JWT → `LoginScreen`, has JWT → existing app
- Pass user role down for conditional rendering
- Add logout button to header/settings

#### `frontend/src/api/chat.ts`
- Add `Authorization: Bearer {jwt}` header to all fetch calls
- Handle 401 responses → clear JWT, redirect to login

#### `frontend/src/components/Sidebar/`
- Guest: hide real portfolio section, show "Connect your portfolio" CTA card
- User/Admin: show real portfolio as today

## What Stays the Same

- **3rd party API clients** — singletons with shared API keys (not user-specific)
- **Agent graph** (`graph.py`) — no changes
- **Research tool signatures** — `stock_quote`, `conviction_score`, etc. don't need user_id
- **Verification pipeline** — unchanged
- **System prompt & routing rules** — unchanged
- **Frontend components** (RichCard, MessageBubble, CommandPalette, etc.) — unchanged

## New Dependencies

- `PyJWT` — JWT creation/verification
- `cryptography` — AES-256 encryption for token storage (fernet)

## New Environment Variables

```
ENCRYPTION_KEY=   # AES-256 key for encrypting Ghostfolio tokens at rest
JWT_SECRET=       # Secret for signing JWTs
```

## Guest Behavior

- Ephemeral: fresh $100K paper portfolio each visit, no chat history carryover
- Access: paper trading, stock quotes, conviction scores, congressional data, morning briefings (market data sections only, no holdings)
- Restricted: no real portfolio tools (`portfolio_summary`, `portfolio_performance`, `transaction_history`, `holding_detail`, `benchmark_comparison`)
- No persistence: guest user row can be cleaned up after session expires

## Migration

- Existing `data/paper_portfolio.json` → import into admin's paper_portfolios row (one-time)
- Existing `data/alert_cooldowns.json` → import into admin's alert_cooldowns rows (one-time)
- Existing `data/checkpoints.db` → prefix existing thread_ids with admin user_id (migration script)
- Old files can be deleted after migration
