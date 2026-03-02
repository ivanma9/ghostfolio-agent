# Error Handling & Observability Design

## Goals
- Production reliability: prevent silent failures, resilient to flaky 3rd-party APIs
- Debugging & visibility: trace requests end-to-end, understand partial results, diagnose issues in logs
- User clarity: tell users what data is missing, not just "something went wrong"

## Decisions
- **Retry strategy**: Retry Ghostfolio (critical path) only. Fail fast on enrichment clients (Finnhub, FMP, Alpha Vantage).
- **Observability level**: Structured logging + request tracing middleware. No OpenTelemetry (overkill for single-service app).
- **User error messages**: Include context about what's missing (e.g., "Earnings data unavailable"). No technical details — those live in logs.
- **Client architecture**: BaseClient inheritance for shared HTTP logic.

---

## Section 1: Structlog Configuration & Request Middleware

### Structlog Setup
- New file: `src/ghostfolio_agent/logging.py`
- `configure_logging(log_level)` called from `main.py` lifespan
- JSON output in production, colored console in dev (controlled by `LOG_FORMAT` env var, default `"json"`)
- Processors: timestamps, log level, module name
- Wires up the existing dead `settings.log_level` config

### Correlation IDs
- FastAPI middleware generates a `request_id` (UUID) per incoming request
- Stored in `contextvars.ContextVar` — available throughout the async call chain
- structlog processor auto-injects `request_id` into every log event

### Request Logging Middleware
- New file: `src/ghostfolio_agent/api/middleware.py`
- Logs at request start: `method`, `path`, `session_id`, `request_id`
- Logs at request end: `status_code`, `duration_ms`, `request_id`

---

## Section 2: Base HTTP Client & Retry Logic

### BaseClient (`src/ghostfolio_agent/clients/base.py`)
- All 4 clients inherit from `BaseClient`
- Shared `httpx.AsyncClient` instance with connection pooling (created once in `__init__`, not per-request)
- Configurable `httpx.Timeout(connect=5.0, read=15.0)` replacing flat `timeout=30.0`
- Structured logging on every request: `client_name`, `method`, `url`, `status_code`, `duration_ms`, `request_id`
- Shared `_get()` and `_post()` methods with error classification

### Custom Exceptions (`src/ghostfolio_agent/clients/exceptions.py`)
- `APIError(client, status_code, url, body)` — base
- `RateLimitError(APIError)` — HTTP 429 + soft rate limits (Alpha Vantage `{"Note": "..."}`, FMP `{"Error Message": "..."}`)
- `AuthenticationError(APIError)` — 401/403, never retried
- `TransientError(APIError)` — 5xx and timeouts, retryable

### Retry Logic
- Opt-in via `retryable = True` on class (only Ghostfolio)
- 2 retries, exponential backoff (1s, 2s)
- Only retries `TransientError` — `RateLimitError` and `AuthenticationError` fail immediately

### Soft Error Detection
- Each client overrides `_check_soft_errors(response_json)` hook
- Alpha Vantage: check for `"Note"` or `"Information"` keys → `RateLimitError`
- FMP: check for `"Error Message"` key → `APIError`
- Finnhub/Ghostfolio: no soft errors to detect (default no-op)

---

## Section 3: Shared Utilities & Tool-Layer Cleanup

### Shared `safe_fetch` (`src/ghostfolio_agent/utils.py`)
- Single implementation replacing 3 copies in `holding_detail.py`, `conviction_score.py`, `morning_briefing.py`
- Logs with `logger.warning` including `label`, `error`, `request_id`
- Returns `None` on failure

### Tool-Layer Bug Fixes
| File | Fix |
|---|---|
| `stock_quote.py` | Add structlog logger, replace silent `except: pass` with logged warnings |
| `paper_trade.py` | Add structlog logger, bare `except:` → `except Exception:`, log price fetch failures |
| `risk_analysis.py` | `asyncio.gather(..., return_exceptions=True)`, handle `get_portfolio_details` failure independently |
| `morning_briefing.py` | Don't cache empty macro results, log warning when all macro calls fail |

### User-Facing Error Messages
- Enrichment failures include context: "Earnings data unavailable — results shown without earnings info"
- Core tool still returns useful output, notes the gap
- Consistent pattern across all tools

---

## Section 4: Verification Pipeline & FastAPI Error Handling

### Verification Pipeline
- Wrap each verifier call in try/except in `pipeline.py` — skip crashed verifier, don't kill pipeline
- Add structlog logger to all 5 verification files
- Log results: `confidence_level`, `issues_found`, `request_id`

### FastAPI Error Handling
- `/api/chat`: Return HTTP 500 for unexpected errors (not HTTP 200 with error body)
- Global `@app.exception_handler(Exception)` in `main.py` — logs and returns structured JSON error
- `/api/paper-portfolio`: Add outer try/except for JSON corruption

### Health Check
- `GET /api/health` — verifies Ghostfolio is reachable
- Useful for Railway health check config

---

## Files Changed / Created

### New Files
- `src/ghostfolio_agent/logging.py` — structlog configuration
- `src/ghostfolio_agent/api/middleware.py` — request logging + correlation ID middleware
- `src/ghostfolio_agent/clients/base.py` — BaseClient with shared HTTP logic
- `src/ghostfolio_agent/clients/exceptions.py` — custom exception hierarchy
- `src/ghostfolio_agent/utils.py` — shared `safe_fetch`

### Modified Files
- `src/ghostfolio_agent/main.py` — call `configure_logging()`, add middleware, exception handler, health check
- `src/ghostfolio_agent/clients/ghostfolio.py` — inherit BaseClient, `retryable = True`
- `src/ghostfolio_agent/clients/finnhub.py` — inherit BaseClient
- `src/ghostfolio_agent/clients/alpha_vantage.py` — inherit BaseClient, override `_check_soft_errors`
- `src/ghostfolio_agent/clients/fmp.py` — inherit BaseClient, override `_check_soft_errors`
- `src/ghostfolio_agent/tools/stock_quote.py` — add logging, fix silent catches
- `src/ghostfolio_agent/tools/paper_trade.py` — add logging, fix bare except
- `src/ghostfolio_agent/tools/risk_analysis.py` — fix gather, independent failure handling
- `src/ghostfolio_agent/tools/morning_briefing.py` — fix macro cache, use shared `safe_fetch`
- `src/ghostfolio_agent/tools/holding_detail.py` — use shared `safe_fetch`
- `src/ghostfolio_agent/tools/conviction_score.py` — use shared `safe_fetch`
- `src/ghostfolio_agent/api/chat.py` — HTTP 500 on errors, log request start
- `src/ghostfolio_agent/verification/pipeline.py` — wrap verifiers, add logging
- `src/ghostfolio_agent/verification/numerical.py` — add logging
- `src/ghostfolio_agent/verification/hallucination.py` — add logging
- `src/ghostfolio_agent/verification/output_validation.py` — add logging
- `src/ghostfolio_agent/verification/domain_constraints.py` — add logging
