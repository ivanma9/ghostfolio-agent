# Congressional Trading Datastore — Technical Specification

## Overview / Context

The Congressional Trading Datastore is a standalone service that scrapes, parses, and serves U.S. House of Representatives financial disclosure data (Periodic Transaction Reports / PTRs). It exposes a REST API that AgentForge (a Ghostfolio AI portfolio agent) will consume to answer questions like "are any congress members trading my holdings?"

This is a separate repository and deployment from AgentForge. It is tracked as AgentForge Task #10 for eventual integration.

### Why a Separate Service?

- Congressional trading data requires scraping + PDF parsing — fundamentally different from AI agent work
- Different deployment lifecycle: scraper runs daily on a schedule; agent runs on demand
- Different dependencies: PDF parsing, scraping libs vs. LangGraph, LLM SDKs
- Keeps AgentForge clean — it just calls the API

## Goals and Non-Goals

### Goals

- Scrape House PTR filings from the official source (disclosures-clerk.house.gov)
- Parse transaction-level data from PTR PDFs using regex-based extraction
- Store parsed transactions in SQLite
- Expose a REST API for querying trades by ticker, member, or date range
- Run a daily scraper job to ingest new filings
- Deploy on Railway as a standalone service

### Non-Goals

- Senate disclosures (future scope)
- Real-time streaming of new filings (daily batch is sufficient)
- LLM-assisted PDF parsing (regex-first for MVP)
- User authentication on the API (internal service on Railway private network)
- Historical backfill beyond the current + previous year

## System Architecture

```
┌──────────────────────────────────────────────────┐
│                 CongressionalTrading              │
│                                                   │
│  ┌─────────────┐    ┌────────────┐    ┌────────┐ │
│  │   Scraper    │───▶│   Parser   │───▶│ SQLite │ │
│  │  (Daily Job) │    │  (Regex)   │    │   DB   │ │
│  └─────────────┘    └────────────┘    └───┬────┘ │
│                                           │      │
│  ┌─────────────────────────────────────────┘      │
│  │                                                │
│  ▼                                                │
│  ┌─────────────┐                                  │
│  │  FastAPI     │◀── GET /trades?ticker=AAPL      │
│  │  REST API    │◀── GET /trades?member=Pelosi    │
│  └─────────────┘                                  │
│                                                   │
└──────────────────────────────────────────────────┘
         ▲
         │ HTTP (Railway private network)
         │
┌────────┴─────────┐
│   AgentForge     │
│   (Task #10)     │
└──────────────────┘
```

### Components

1. **Scraper** — Downloads the annual XML index ZIP from House Clerk, diffs against DB, downloads new PTR PDFs
2. **Parser** — Extracts transaction-level data from PDF text using `pdftotext` + regex patterns
3. **Database** — SQLite with `trades`, `filings`, and `scraper_runs` tables
4. **API** — FastAPI REST endpoints for querying trades

### Why SQLite?

Congressional trading data is small (~10MB/year, tens of thousands of rows). SQLite in WAL mode handles concurrent reads (API) alongside sequential writes (scraper) without issue. No external database service means zero infra cost, simpler deployment, and trivial backups (copy one file). If data volume ever exceeds what SQLite handles well, migration to Postgres is straightforward.

## Component Design

### Scraper (`scraper/`)

**Data Source:** `https://disclosures-clerk.house.gov/public_disc/financial-pdfs/{YEAR}FD.zip`

Each ZIP contains:
- `{YEAR}FD.xml` — structured index of all filings
- `{YEAR}FD.txt` — TSV version of the same index

**XML Index Fields:**
- `Prefix` — Hon., Mr., Dr., etc.
- `Last` — Last name
- `First` — First name
- `Suffix` — Jr., III, etc.
- `FilingType` — P (PTR), O (Annual), C (Candidate), A (Amendment), etc.
- `StateDst` — State + district code (e.g., CA11, GA12)
- `Year` — Filing year
- `FilingDate` — Date filed (MM/DD/YYYY)
- `DocID` — Unique document identifier

**PTR PDF URL Pattern:** `https://disclosures-clerk.house.gov/public_disc/ptr-pdfs/{YEAR}/{DocID}.pdf`

**Daily Scrape Cycle:**

1. Create `scraper_runs` record with `status=running`
2. Download ZIP for current year (and previous year if January)
3. Parse XML, filter for `FilingType=P`
4. Compare DocIDs against `filings` table — identify new filings
5. For each new filing:
   a. Download PTR PDF
   b. Extract text via `pdftotext`
   c. Parse transactions with regex
   d. Insert filing + transactions into DB (single transaction per filing)
6. Update `scraper_runs` record with counts and `status=success`
7. Retry any filings with `status=error` and `retry_count < 3`

**Batch Processing Semantics:**
- Each filing is processed in its own database transaction
- Failures are isolated — one filing's error doesn't affect others
- Progress is persisted after each successful filing
- On restart, processing resumes from where it left off (new filings + retries)

**Error Handling:**
- If ZIP download fails: log error, mark run as failed, retry next cycle
- If individual PDF download fails: log error, mark filing as `status=error`, increment `retry_count`, continue with other filings
- If PDF parsing fails (no transactions extracted): log warning, mark filing as `status=parse_error`, continue
- If PDF > 10MB: skip with `status=error`, log security warning
- If PDF download takes > 30s: timeout, mark as `status=error`

**PDF Security:**
- Validate DocID format before constructing URL: `^[0-9]+$`
- Maximum PDF size: 10MB
- Download timeout: 30 seconds per PDF
- Validate PDF magic bytes (`%PDF-`) before processing
- Download to temp file, clean up immediately after parsing

**Rate Limiting:**
- 1-second delay between PDF downloads to be respectful to House servers
- All downloads use User-Agent: `CongressionalTradingBot/1.0 (https://github.com/ivanma/congressional-trading)`

**Retry Strategy:**
- Network failures: Exponential backoff with jitter, max 3 retries per PDF (delays: 1s, 2s, 4s)
- Circuit breaker: After 5 consecutive download failures, pause scraper for 1 hour before resuming
- `retry_count` is never reset — once a filing succeeds, its status changes to `parsed` and it's never retried again. Filings that exhaust all 3 retries remain at `status=error` for manual review.

### Parser (`parser/`)

**Input:** Raw text output from `pdftotext`

**Extraction Strategy:**

The PTR PDF format is standardized by the House Ethics Committee. Key patterns:

1. **Member identification:** Already known from the XML index (name, state, district)

2. **Ticker extraction:** `\(([A-Z]{1,5})\)` — stock tickers in parentheses after asset description

3. **Asset description:** Text preceding the ticker, trimmed of whitespace, e.g., "NVIDIA Corporation - Common Stock"

4. **Asset type code:** `\[(ST|OP|EF|DC|UT|AH|OT)\]` where:
   - ST = Stock
   - OP = Option
   - EF = ETF
   - DC = Debt/Corporate Bond
   - UT = Unit Trust
   - AH = Asset Held
   - OT = Other

5. **Transaction type:** `\b(P|S|S \(partial\)|E)\b` where:
   - P = Purchase
   - S = Sale (full)
   - S (partial) = Sale (partial)
   - E = Exchange

6. **Owner:** `\b(SP|JT|DC)\b` or Self if none matched
   - SP = Spouse
   - JT = Joint
   - DC = Dependent Child
   - (blank) = Self

7. **Transaction date:** `(\d{2})/(\d{2})/(\d{4})` — first date on the line

8. **Notification date:** Second `(\d{2})/(\d{2})/(\d{4})` on the same line

9. **Amount range:** `\$([0-9,]+)\s*-?\s*\$([0-9,]+)` or `Over \$([0-9,]+)` — validated against known brackets

10. **Description:** Line matching `D\s*:\s*(.+)` — free text like "Purchased 50 call options..."

11. **Capital gains > $200:** Match `Yes` or `No` after cap gains header

**Known Amount Range Brackets:**
```python
AMOUNT_RANGES = [
    (1_001, 15_000),
    (15_001, 50_000),
    (50_001, 100_000),
    (100_001, 250_000),
    (250_001, 500_000),
    (500_001, 1_000_000),
    (1_000_001, 5_000_000),
    (5_000_001, 25_000_000),
    (25_000_001, 50_000_000),
    (50_000_001, None),  # Over $50M — amount_range_high is NULL
]
```

**Data Validation:**
- Transaction date must be <= notification date
- Notification date must be <= filing date
- Amount range must match a known bracket (log warning if unknown bracket encountered)
- Ticker must be 1-5 uppercase letters (if present)
- Duplicate transactions within a filing (same ticker + date + type + owner) are logged and skipped

**PDF Text Extraction:**
- Use `pdftotext -layout` to preserve column alignment (critical for parsing)
- Timeout: 10 seconds per PDF
- Handle corrupted PDFs gracefully (log error, mark filing as `parse_error`)

**Parser Output:** List of transaction dicts ready for DB insertion.

### Scheduler

- **APScheduler** with a cron trigger: runs daily at 6:00 AM UTC
- On startup, runs an initial scrape if the DB is empty or last successful scrape > 24 hours ago
- Scheduler runs in-process with FastAPI (BackgroundScheduler)
- Prevents concurrent runs via a file-based lock (`/tmp/congressional_scraper.lock`)

## API Design

### Base URL

`/api/v1`

### Endpoints

#### `GET /api/v1/trades`

Query congressional stock trades.

**Query Parameters:**
| Parameter | Type | Required | Description | Validation |
|-----------|------|----------|-------------|------------|
| `ticker` | string | No* | Filter by stock ticker symbol (case-insensitive) | 1-5 letters |
| `member` | string | No* | Filter by member last name (case-insensitive, partial match) | 2-50 chars |
| `days` | int | No | Only return trades from the last N days | 1-730, default: 90 |
| `transaction_type` | string | No | Filter by type | Enum: `purchase`, `sale`, `sale_partial`, `exchange` |
| `limit` | int | No | Max results to return | 1-500, default: 100 |
| `offset` | int | No | Pagination offset | >= 0, default: 0 |

*At least one of `ticker` or `member` must be provided.

**Response (200 OK):**
```json
{
  "trades": [
    {
      "id": 1,
      "member_name": "Nancy Pelosi",
      "member_state": "CA",
      "member_district": "11",
      "ticker": "NVDA",
      "asset_description": "NVIDIA Corporation - Common Stock",
      "asset_type": "ST",
      "transaction_type": "sale_partial",
      "transaction_date": "2024-12-31",
      "disclosure_date": "2025-01-17",
      "amount_range_low": 5000001,
      "amount_range_high": 25000000,
      "owner": "spouse",
      "description": "Sold 10,000 shares.",
      "cap_gains_over_200": true,
      "filing_id": "20026590",
      "filing_url": "https://disclosures-clerk.house.gov/public_disc/ptr-pdfs/2025/20026590.pdf"
    }
  ],
  "total": 1,
  "limit": 100,
  "offset": 0
}
```

#### `GET /api/v1/trades/summary`

Get aggregate trading activity for a ticker.

**Query Parameters:**
| Parameter | Type | Required | Description | Validation |
|-----------|------|----------|-------------|------------|
| `ticker` | string | Yes | Stock ticker symbol | 1-5 letters |
| `days` | int | No | Lookback period | 1-730, default: 90 |

**Response (200 OK):**
```json
{
  "ticker": "NVDA",
  "period_days": 90,
  "total_trades": 5,
  "purchases": 3,
  "sales": 2,
  "unique_members": 4,
  "members": ["Pelosi", "Tuberville", "Crenshaw", "Allen"],
  "net_sentiment": "bullish",
  "latest_trade_date": "2025-01-14"
}
```

#### `GET /api/v1/members`

List members with recent trading activity.

**Query Parameters:**
| Parameter | Type | Required | Description | Validation |
|-----------|------|----------|-------------|------------|
| `days` | int | No | Lookback period | 1-730, default: 90 |
| `limit` | int | No | Max results | 1-500, default: 100 |
| `offset` | int | No | Pagination offset | >= 0, default: 0 |

**Response (200 OK):**
```json
{
  "members": [
    {
      "name": "Nancy Pelosi",
      "state": "CA",
      "district": "11",
      "trade_count": 8,
      "latest_trade_date": "2025-01-14"
    }
  ],
  "total": 45,
  "limit": 100,
  "offset": 0
}
```

#### `GET /api/v1/health`

Health check endpoint. Returns 503 if last successful scrape is older than 48 hours.

**Response (200 OK):**
```json
{
  "status": "ok",
  "last_scrape": "2025-02-28T06:00:00Z",
  "total_filings": 451,
  "total_trades": 2340,
  "database_size_mb": 8.4
}
```

**Response (503 Service Unavailable):**
```json
{
  "status": "unhealthy",
  "last_scrape": "2025-02-26T06:00:00Z",
  "error": "Last successful scrape older than 48 hours"
}
```

### Error Responses

**400 Bad Request:**
```json
{
  "error": "At least one of 'ticker' or 'member' must be provided",
  "status": 400
}
```

**422 Unprocessable Entity:**
```json
{
  "error": "Validation error",
  "status": 422,
  "details": [
    {
      "field": "days",
      "message": "Must be between 1 and 730"
    }
  ]
}
```

**429 Too Many Requests:**
```json
{
  "error": "Rate limit exceeded",
  "status": 429,
  "retry_after": 60
}
```

**500 Internal Server Error:**
```json
{
  "error": "Internal server error",
  "status": 500
}
```

**503 Service Unavailable:**
```json
{
  "error": "Database unavailable",
  "status": 503,
  "retry_after": 30
}
```

### Rate Limiting

- **Per-IP limit:** 10 requests/second
- **Implementation:** In-memory token bucket via `slowapi`
- **Response headers:** `X-RateLimit-Limit`, `X-RateLimit-Remaining`, `X-RateLimit-Reset`

## Data Models / Database Schema

### `filings` Table

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| `doc_id` | TEXT | PRIMARY KEY | Unique document ID from House Clerk |
| `member_first` | TEXT | NOT NULL | First name |
| `member_last` | TEXT | NOT NULL | Last name |
| `member_prefix` | TEXT | | Hon., Mr., etc. |
| `member_suffix` | TEXT | | Jr., III, etc. |
| `state_district` | TEXT | NOT NULL | e.g., CA11 |
| `filing_date` | TEXT | NOT NULL | ISO date string |
| `filing_year` | INTEGER | NOT NULL | Year |
| `status` | TEXT | NOT NULL DEFAULT 'pending' | pending, parsed, error, parse_error |
| `error_message` | TEXT | | Error details if status is error/parse_error |
| `retry_count` | INTEGER | NOT NULL DEFAULT 0 | Number of download/parse attempts |
| `created_at` | TEXT | NOT NULL | ISO timestamp |
| `updated_at` | TEXT | NOT NULL | ISO timestamp |

### `trades` Table

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| `id` | INTEGER | PRIMARY KEY AUTOINCREMENT | |
| `filing_doc_id` | TEXT | FOREIGN KEY → filings.doc_id | |
| `ticker` | TEXT | | May be NULL if asset is not a stock |
| `asset_description` | TEXT | NOT NULL | Full asset name |
| `asset_type` | TEXT | | ST, OP, EF, DC, UT, AH, OT |
| `transaction_type` | TEXT | NOT NULL | purchase, sale, sale_partial, exchange |
| `transaction_date` | TEXT | | ISO date string |
| `notification_date` | TEXT | | ISO date string |
| `amount_range_low` | INTEGER | | Lower bound in dollars |
| `amount_range_high` | INTEGER | | Upper bound in dollars (NULL for "Over $50M") |
| `owner` | TEXT | NOT NULL DEFAULT 'self' | self, spouse, joint, dependent |
| `description` | TEXT | | Free text description |
| `cap_gains_over_200` | BOOLEAN | | |
| `created_at` | TEXT | NOT NULL | ISO timestamp |

**Unique constraint:** `UNIQUE(filing_doc_id, ticker, transaction_date, transaction_type, owner)` — prevents duplicate trades within a filing. Insert uses `INSERT OR IGNORE`.

### `scraper_runs` Table

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| `id` | INTEGER | PRIMARY KEY AUTOINCREMENT | |
| `started_at` | TEXT | NOT NULL | ISO timestamp |
| `completed_at` | TEXT | | ISO timestamp |
| `status` | TEXT | NOT NULL | running, success, error |
| `new_filings` | INTEGER | | Count of new filings found |
| `new_trades` | INTEGER | | Count of new trades parsed |
| `retried_filings` | INTEGER | | Count of previously-failed filings retried |
| `error_message` | TEXT | | Error details if failed |

### Indexes

- `idx_trades_ticker` on `trades(ticker)`
- `idx_trades_transaction_date` on `trades(transaction_date)`
- `idx_trades_filing_doc_id` on `trades(filing_doc_id)`
- `idx_filings_member_last` on `filings(member_last)`
- `idx_filings_filing_date` on `filings(filing_date)`
- `idx_filings_status` on `filings(status)` — for retry queries

### Database Configuration

```sql
PRAGMA journal_mode = WAL;        -- concurrent reads during writes
PRAGMA busy_timeout = 5000;       -- wait up to 5s for locks
PRAGMA synchronous = NORMAL;      -- safe with WAL mode
PRAGMA cache_size = -64000;       -- 64MB cache
PRAGMA temp_store = MEMORY;       -- temp tables in memory
```

## Infrastructure Requirements

- **Runtime:** Python 3.12+, FastAPI, uvicorn
- **Package manager:** uv
- **System dependency:** `poppler-utils` (for `pdftotext`)
- **Key Python dependencies:** `fastapi`, `uvicorn[standard]`, `httpx`, `apscheduler`, `pydantic`, `slowapi`, `lxml`
- **Database:** SQLite 3.35+ (single file, `/data/congressional_trades.db`)
- **Deployment:** Railway (single service)
- **Resources:** 512MB memory, 0.5 vCPU, 1GB volume

## Security Considerations

- Service only accessible within Railway private network (no public URL)
- Read-only API — no write endpoints exposed
- Scraper only downloads from official government sources (`disclosures-clerk.house.gov`)
- No user data stored (member names are public record)
- Per-IP rate limiting (10 req/s) via `slowapi`
- SQLite parameterized queries to prevent SQL injection
- All query parameters validated with Pydantic models
- PDF downloads: size limit (10MB), magic bytes validation, download timeout (30s)
- DocID format validation before constructing download URLs

## Error Handling Strategy

| Scenario | Handling | Recovery |
|----------|----------|----------|
| House Clerk site down | Log error, mark run as failed | Retry next daily cycle |
| ZIP file corrupted | Log error, skip cycle | Retry next daily cycle |
| Individual PDF download fails | Mark filing as `error`, increment `retry_count` | Auto-retry in subsequent runs (up to 3 attempts) |
| PDF parsing extracts 0 transactions | Mark filing as `parse_error` | Log for manual review |
| Regex misses a field | Store NULL for that field, log warning | Continue processing |
| API query with no results | Return empty `trades: []` array, 200 status | N/A |
| Invalid query parameters | Return 422 with field-level errors | N/A |
| Database unavailable | Return 503 to API clients | Auto-recovery when DB accessible |
| SQLite write lock contention | `busy_timeout=5000` handles via WAL mode | Automatic |
| 5 consecutive download failures | Circuit breaker pauses scraper for 1 hour | Auto-resume after pause |
| PDF > 10MB | Skip with `status=error`, log security warning | Manual review |
| Duplicate trade in filing | Log warning, skip via `INSERT OR IGNORE` | Continue processing |

## Performance Requirements

- **API p95 latency:** < 200ms for indexed queries
- **API throughput:** 100 requests/second sustained
- **Daily scrape:** < 30 minutes for up to 50 new filings
- **PDF parsing:** < 2 seconds per document
- **Database size:** ~10MB/year (linear growth, 5-year capacity = 50MB)
- **All indexed queries:** < 10ms at database level

## Observability

### Logging

Structured JSON logs via Python `logging`:

```json
{
  "timestamp": "2025-02-28T06:05:12.123Z",
  "level": "INFO",
  "logger": "congressional_trading.scraper",
  "message": "Scrape cycle completed",
  "new_filings": 3,
  "new_trades": 15,
  "retried": 1,
  "duration_seconds": 45.2
}
```

- **Scraper:** Log cycle start/end, new filings found, parse successes/failures, retry attempts
- **API:** Log each request with endpoint, parameters, response time, status code
- **Log levels:** ERROR (service failures), WARNING (parse errors), INFO (requests, scrape summaries), DEBUG (detailed parsing, disabled in production)

### Health Checks

- `GET /api/v1/health` — returns 200 if healthy, 503 if last scrape > 48 hours
- Railway configured to use this endpoint for automatic restarts

## Testing Strategy

- **Unit tests:** Regex parser against known PTR text extracts with expected output
  - Valid ticker: "NVIDIA Corporation (NVDA)" → "NVDA"
  - Amount parsing: "$15,001 - $50,000" → (15001, 50000)
  - "Over $50,000,000" → (50000001, None)
  - Date validation: Invalid dates rejected, date ordering enforced
  - Edge cases: missing ticker, multi-page PTRs, options descriptions
- **Integration tests:** Full scrape cycle against fixture XML + sample PDFs, verify DB state
- **API tests:** FastAPI TestClient against pre-seeded test database
  - All parameter combinations and edge cases
  - Pagination correctness
  - Error responses for invalid input
- **Validation tests:** Compare parsed output against House Stock Watcher's known dataset for overlapping filings (golden test set)
- **Test command:** `uv run pytest tests/ -v`

## Deployment Strategy

- Single Railway service with `Dockerfile`:
  ```dockerfile
  FROM python:3.12-slim
  RUN apt-get update && apt-get install -y poppler-utils && rm -rf /var/lib/apt/lists/*
  ```
- SQLite DB persists via Railway volume mount at `/data`
- Railway health check configured at `/api/v1/health`
- Automatic restart on failure (Railway default behavior)
- Rollback: `railway rollback` to previous deployment
- Database backup: scraper copies DB to `/data/backups/` before each run, keeps last 7

### Environment Variables

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `DATABASE_PATH` | No | `/data/congressional_trades.db` | SQLite database path |
| `LOG_LEVEL` | No | `INFO` | Logging level |
| `SCRAPE_HOUR_UTC` | No | `6` | Hour to run daily scrape (UTC) |

## Project Structure

```
CongressionalTrading/
├── src/
│   └── congressional_trading/
│       ├── __init__.py
│       ├── main.py              # FastAPI app + scheduler setup
│       ├── config.py            # Settings (env vars, constants)
│       ├── scraper/
│       │   ├── __init__.py
│       │   ├── downloader.py    # ZIP + PDF download logic
│       │   └── scheduler.py     # APScheduler cron job + circuit breaker
│       ├── parser/
│       │   ├── __init__.py
│       │   ├── xml_index.py     # Parse FD XML index
│       │   ├── ptr_parser.py    # Regex-based PTR PDF parser
│       │   └── patterns.py      # Compiled regex patterns + amount brackets
│       ├── db/
│       │   ├── __init__.py
│       │   ├── models.py        # Pydantic response models
│       │   ├── database.py      # SQLite connection + pragmas
│       │   └── queries.py       # Data access layer (raw SQL)
│       └── api/
│           ├── __init__.py
│           └── routes.py        # FastAPI route handlers
├── tests/
│   ├── fixtures/                # Sample XML, PDFs, expected outputs
│   ├── test_parser.py
│   ├── test_scraper.py
│   └── test_api.py
├── data/                        # SQLite DB + backups (gitignored)
├── Dockerfile
├── pyproject.toml
└── README.md
```

## Open Questions / Future Considerations

1. **Senate disclosures** — efdsearch.senate.gov has a different format. Could add as a second scraper module later.
2. **Party affiliation** — The House XML doesn't include party. Could enrich from a static mapping or external source.
3. **Amendment handling** — PTR amendments (`FilingType=A`) may modify previously filed transactions. How to handle updates/corrections.
4. **Historical backfill** — ZIP files exist for 2008–present. Could backfill on demand.
5. **Options detail parsing** — Options trades include strike price, expiration, # contracts in the description field. Could parse these into structured fields.
