# AgentForge — Project Rules

## Task Completion Protocol

Every task MUST follow this sequence before the session ends. No exceptions.

1. **Implement** — Write the code for the task
2. **Test** — Run the full test suite (`uv run pytest tests/unit/ -v`). All tests must pass.
3. **Commit** — Commit all changes with a descriptive message
4. **Update docs** — Update any affected documentation (plans, brainstorming docs, MEMORY.md) to reflect what changed
5. **Commit docs** — Commit documentation updates separately
6. **Session complete** — The task is done. Start a new session for the next task.

### Rules

- Do NOT start a new task/feature in the same session after completing one. End the session and start fresh.
- Do NOT mark a task as complete unless tests pass and changes are committed.
- If a task reveals issues in a previous task, fix and commit those first before continuing.
- Every session should end with a clean `git status` (no uncommitted changes).

## Branching Strategy

- **Single-session features**: Work on a feature branch directly (no worktree). Merge to main when done.
- **Multi-session or parallel features**: Use worktrees in `.worktrees/` for isolation.
- Don't copy `.env` into worktrees — use symlinks or env vars instead.

## Test Commands

- Unit tests: `uv run pytest tests/unit/ -v`
- Single file: `uv run pytest tests/unit/test_<name>.py -v`
- Evals: `uv run python tests/eval/run_evals.py`

## 3rd Party API Clients

- **Finnhub**: analyst recommendations, earnings calendar (free tier)
- **Alpha Vantage**: news sentiment, fed funds rate, CPI, treasury yield (free tier)
- **FMP**: analyst estimates (annual), price target consensus, price target summary (free tier, `/stable` base URL)
- Congressional trading data → separate standalone service (not in this repo)

## Ghostfolio Client — Unused Endpoints to Add Per Feature

Add new Ghostfolio client methods only when a feature task needs them. Do not add speculatively.

- `get_dividends()` → `/api/v1/portfolio/dividends` (groupBy, date range)
- `get_investments()` → `/api/v1/portfolio/investments` (investment timeline, groupBy)
- `get_benchmarks()` → `/api/v1/benchmarks/{dataSource}/{symbol}/{startDate}` (compare to S&P 500 etc)
- `get_market_data()` → `/api/v1/market-data/{dataSource}/{symbol}` (historical prices — test first, may be limited)
- `get_market_overview()` → `/api/v1/market-data/markets` (market context, supports includeHistoricalData flag)
