# AgentForge — Architecture

AgentForge is a Ghostfolio AI portfolio assistant composed of a React single-page application,
a FastAPI backend, a LangGraph ReAct agent, and a suite of financial data clients.

---

## 1. System Overview

```
+-----------------------+     HTTP/REST     +-----------------------------+
|  React SPA (Vite)     | <--------------> |  FastAPI backend            |
|  - ChatPanel           |                  |  - /api/chat (POST)         |
|  - Sidebar             |                  |  - /api/models (GET)        |
|  - RichCard parsers    |                  |  - /api/portfolio (GET)     |
|  - VerificationBanner  |                  |  - /api/paper-portfolio (GET)|
+-----------------------+                  +-----------------------------+
                                                         |
                                              LangGraph ReAct Agent
                                              (AsyncSqliteSaver checkpointer)
                                                         |
                                    +--------------------+--------------------+
                                    |                    |                    |
                              13 LangChain          Verification         AlertEngine
                              Tools                 Pipeline             (per-request,
                                                    (4 verifiers)        2-phase fetch)
                                    |
          +----------+----------+----------+----------+----------+
          |          |          |          |          |          |
    Ghostfolio   Finnhub   Alpha       FMP      Congressional  (paper
     Client      Client    Vantage     Client    Client        trade JSON)
      (REST)     (REST)    Client      (REST)    (Railway
                           (REST)                private net)
                                    |
                             Ghostfolio App
                             (self-hosted,
                              Docker + Redis)
```

External data sources:
- **Ghostfolio**: portfolio holdings, transactions, symbol lookup, performance, orders
- **Finnhub**: stock quotes, analyst recommendations, earnings calendar
- **Alpha Vantage**: news sentiment, Fed funds rate, CPI, treasury yield
- **Financial Modeling Prep (FMP)**: analyst estimates, price target consensus and summary
- **Congressional API**: congressional stock trades (separate Railway microservice)

---

## 2. Component Diagram (ASCII)

```
frontend/
  src/
    App.tsx                      Root: wires Sidebar + ChatPanel + state
    hooks/
      useChat.ts                 Session management, message state, API calls
      useSidebar.ts              Real vs paper portfolio fetch, refresh trigger
    components/
      Chat/
        ChatPanel.tsx            Message list, input bar, model selector, paper toggle
        MessageBubble.tsx        Per-message rendering + VerificationBanner + DataSourceBadges
        RichCard.tsx             Structured card parsers (MorningBriefingCard, HoldingDetailCard, etc.)
        VerificationBanner.tsx   Collapsible yellow/red confidence banner
        ModelSelector.tsx        Dropdown bound to /api/models
        PaperTradeToggle.tsx     Amber toggle that flips paper trading mode
        ChatInput.tsx            Textarea + send button
      Sidebar/
        Sidebar.tsx              Holdings list, portfolio value, mode-aware coloring
        PortfolioValue.tsx       Total value + daily change display
        TopHoldings.tsx          Holdings rows
        AllocationChart.tsx      Visual allocation bars
    api/
      chat.ts                    postChat / fetchPortfolio / fetchPaperPortfolio + ChatError

src/ghostfolio_agent/
  api/
    chat.py                      FastAPI router: all 4 endpoints, lazy client init
  agent/
    graph.py                     create_agent(), LangGraph ReAct, context trimmer
  tools/
    __init__.py                  create_tools() factory
    portfolio_summary.py
    portfolio_performance.py
    transaction_history.py
    risk_analysis.py
    symbol_lookup.py
    stock_quote.py
    holding_detail.py
    conviction_score.py          Scoring functions also imported by morning_briefing + alert engine
    morning_briefing.py
    paper_trade.py
    activity_log.py              Uses LangGraph interrupt() for human-in-the-loop
    congressional.py             3 tools: trades, summary, members
  clients/
    base.py                      BaseClient: httpx pool, retry, error classification
    exceptions.py                APIError / RateLimitError / AuthenticationError / TransientError
    ghostfolio.py
    finnhub.py
    alpha_vantage.py
    fmp.py
    congressional.py
  verification/
    pipeline.py                  Orchestrator: runs 4 verifiers, worst-case confidence
    numerical.py                 Async: checks $ amounts against live Ghostfolio API
    hallucination.py             Sync: symbol + $ grounding against tool outputs
    output_validation.py         Sync: empty/truncated/error surface detection
    domain_constraints.py        Sync: investment advice detection, disclaimer injection
  alerts/
    engine.py                    AlertEngine singleton, two-phase fetch, 5 conditions, JSON cooldowns
  config.py                      Pydantic Settings (env vars + .env)
  models/
    api.py                       Pydantic request/response models
```

---

## 3. Request Lifecycle

```
Browser
  |
  | POST /api/chat { message, session_id, model, paper_trading }
  v
FastAPI chat endpoint
  |
  |-- [paper trading?] prepend [PAPER TRADING MODE ACTIVE] instruction to content
  |
  |-- AlertEngine.check_alerts()
  |     Phase 1: parallel quote + earnings + congressional for all holdings
  |     Phase 2: analyst + sentiment + PT for flagged symbols only
  |     Fired alerts prepended: "ALERTS:\n- ...\n\nUser message: {content}"
  |
  |-- _get_agent(model)  [lazy init, cached per model name]
  |     AsyncSqliteSaver checkpointer (data/checkpoints.db)
  |     LangGraph ReAct agent with context trimmer pre_model_hook
  |
  |-- agent.ainvoke({ messages: [HumanMessage(content)] }, config={thread_id})
  |     |
  |     |-- pre_model_hook: trim/summarize messages beyond max_context_messages
  |     |
  |     |-- LLM decides tool calls (recursion_limit=25)
  |     |     Each tool call:
  |     |       Tool executes (may use asyncio.gather for parallel API fetches)
  |     |       Tool appends [DATA_SOURCES: ...] metadata line to output
  |     |       ToolMessage added to state
  |     |
  |     |-- LLM produces final AIMessage
  |
  |-- Extract response messages from this turn (after last HumanMessage)
  |-- _extract_data_sources(tool_outputs) -> deduplicated source list
  |-- _strip_data_sources_line(tool_outputs) -> clean outputs for verification
  |-- _extract_citations(messages) -> list[Citation]
  |
  |-- run_verification_pipeline(response_text, tool_outputs, client)
  |     1. verify_numerical_accuracy (async, hits Ghostfolio API)
  |     2. detect_hallucinations (sync)
  |     3. validate_output (sync)
  |     4. check_domain_constraints (sync)
  |     Worst-case confidence: min(high=3, medium=2, low=1) across all verifiers
  |     Response text may be modified: disclaimer prepended/appended, warning appended
  |
  |-- [GraphInterrupt?] activity_log tool interrupted for human confirmation
  |     Return confirmation prompt immediately, no verification
  |
  v
ChatResponse {
  response, session_id, tool_calls, tool_outputs,
  confidence, citations, verification_issues,
  verification_details, data_sources
}
  |
  v
Browser: useChat appends assistant message, calls onToolCall -> sidebar.refresh() if needed
```

---

## 4. Tool Architecture

### Tool count: 13

| Tool | Primary clients | Emits DATA_SOURCES |
|---|---|---|
| portfolio_summary | Ghostfolio | No |
| portfolio_performance | Ghostfolio | No |
| transaction_history | Ghostfolio | No |
| risk_analysis | Ghostfolio | No |
| symbol_lookup | Ghostfolio | No |
| stock_quote | Ghostfolio, Finnhub | Yes |
| holding_detail | Ghostfolio, Finnhub, AlphaVantage, FMP, Congressional | Yes |
| conviction_score | Finnhub, AlphaVantage, FMP, Congressional | Yes |
| morning_briefing | Ghostfolio, Finnhub, AlphaVantage, FMP, Congressional | Yes |
| paper_trade | Ghostfolio (price lookup) | No |
| activity_log | Ghostfolio | No |
| congressional_trades | Congressional | Yes |
| congressional_trades_summary | Congressional | Yes |
| congressional_members | Congressional | Yes |

### Factory pattern

All tools are constructed via the `create_tools()` factory in `tools/__init__.py`. Each tool
file exports a `create_<name>_tool(client, ...)` function that closes over its clients and
returns a LangChain `@tool`-decorated async function. Clients are passed in at agent creation
time; unavailable clients (empty API key) are passed as `None` and handled with graceful
degradation inside each tool.

```python
# tools/__init__.py
def create_tools(
    client: GhostfolioClient,
    finnhub: FinnhubClient | None = None,
    alpha_vantage: AlphaVantageClient | None = None,
    fmp: FMPClient | None = None,
    congressional: CongressionalClient | None = None,
) -> list:
    ...
```

Congressional tools are only added to the list when `congressional is not None`, so the agent
sees fewer tools if that service is unavailable.

### TTL cache

Expensive multi-API tools (conviction_score, congressional tools) use `@ttl_cache(ttl=300)` to
avoid redundant fetches within the same five-minute window. The cache is in-process and not
shared across multiple backend instances.

### DATA_SOURCES convention

Tools that aggregate data from multiple external APIs append a metadata line as the last line of
their output:

```
[DATA_SOURCES: Finnhub, Alpha Vantage, FMP]
```

`chat.py` extracts this line with a regex before passing the output to the LLM or verification
layer, then strips it so it does not appear in the response. The extracted list is surfaced to
the frontend as `data_sources: list[str]` on `ChatResponse`, where `DataSourceBadges` renders
colored pills per source.

### Parallel fetches inside tools

Tools that aggregate multiple APIs use `asyncio.gather` for all independent calls. Example:
`holding_detail` and `conviction_score` fire all API requests concurrently.

### Conviction score reuse

The scoring functions in `tools/conviction_score.py` are plain importable functions, not
LangChain tools:

```
compute_analyst_score, compute_price_target_score,
compute_sentiment_score, compute_earnings_score,
compute_congressional_score, compute_composite, score_to_label
```

These are imported directly by `morning_briefing.py` and `alerts/engine.py` so conviction
computation is not duplicated.

---

## 5. Client Architecture

### BaseClient (`clients/base.py`)

All five clients inherit from `BaseClient`, which provides:
- `httpx.AsyncClient` connection pool (15 s total timeout, 5 s connect timeout)
- Structured logging via `structlog` (`client_request`, `client_retry`, `client_timeout`, etc.)
- Exponential backoff retry for `TransientError` (subclasses set `retryable = True`, `max_retries = 2`)
- Error classification: HTTP status -> typed exception

### Exception hierarchy (`clients/exceptions.py`)

```
APIError (base)
  AuthenticationError   (401, 403)
  RateLimitError        (429, or soft rate-limit detected in 200 body)
  TransientError        (5xx, timeout, connection error) — retryable
```

### Clients

| Client | Base URL | Auth | Retryable | Notes |
|---|---|---|---|---|
| GhostfolioClient | configurable (default localhost:3333) | Bearer token | Yes (2 retries) | 9 endpoints, primary data source |
| FinnhubClient | https://finnhub.io/api/v1 | ?token= query param | No | Overrides `_check_soft_errors` for soft rate limits |
| AlphaVantageClient | https://www.alphavantage.co/query | &apikey= query param | No | 25 req/day free tier; macro data cached 24h |
| FMPClient | https://financialmodelingprep.com/stable | &apikey= query param | No | Free tier only; no legacy /api/v3 or /api/v4 |
| CongressionalClient | configurable Railway private net URL | None | No | Empty URL = disabled with graceful degradation |

### Graceful degradation

Every client is optional. If the API key or URL is not configured, the corresponding client
singleton in `chat.py` returns `None`. Tools and the alert engine check for `None` before
calling any client method. If all external clients are `None`, `AlertEngine.check_alerts()`
short-circuits immediately and returns an empty list.

---

## 6. Verification Pipeline

The pipeline runs after every agent turn that made at least one tool call.

```
run_verification_pipeline(response_text, tool_outputs, client)
  |
  |-- 1. verify_numerical_accuracy    (async)
  |       Extracts dollar amounts from response, cross-checks against
  |       live Ghostfolio portfolio data. Returns discrepancies as issues.
  |
  |-- 2. detect_hallucinations        (sync)
  |       Checks that stock symbols and large dollar amounts in the
  |       response are grounded in at least one tool output string.
  |
  |-- 3. validate_output              (sync)
  |       Detects empty response, truncation markers, or error strings
  |       surfaced as valid output.
  |
  |-- 4. check_domain_constraints     (sync)
  |       Detects investment advice ("you should buy", "I recommend"),
  |       large trade warnings, and enforces disclaimer injection.
  |
  v
Overall confidence = min(verifier confidences) where high=3, medium=2, low=1
  |
  Response text modifications:
    - Investment advice detected -> prepend disclaimer
    - Response mentions financial topics -> append disclaimer
    - Hallucinated symbols detected -> append grounding note
    - Overall confidence == "low" -> append warning
  |
  v
PipelineResult {
  overall_confidence, response_text (modified),
  all_issues, numerical, hallucination,
  output_validation, domain_constraints
}
```

The pipeline is skipped (returns `high` confidence, unmodified response) for turns where no
tool was called (e.g., greetings, clarifying questions).

---

## 7. Alert Engine

### Design

- `AlertEngine` is a singleton, lazily initialized on the first `POST /api/chat` request.
- Runs `check_alerts()` synchronously from the perspective of the chat handler (it is `await`ed
  before the agent is invoked).
- Fired alerts are prepended to the user's message content so the agent sees them as context.
  The system prompt instructs the agent to mention alerts briefly without calling extra tools.

### Two-phase fetch

```
Phase 1  (parallel, all holdings)
  Finnhub: get_quote(sym), get_earnings_calendar(sym)
  Congressional: get_trades_summary(ticker=sym, days=3)

  Conditions evaluated:
    earnings_proximity  -> earnings within 3 days
    big_mover           -> |daily %| >= 5.0
    congressional_trade -> any trades in last 3 days

  Flagged symbols: those that triggered at least one phase-1 condition

Phase 2  (parallel, flagged symbols only)
  Finnhub: get_analyst_recommendations(sym)
  Alpha Vantage: get_news_sentiment(sym)
  FMP: get_price_target_consensus(sym)

  Conditions evaluated:
    analyst_downgrade   -> bearish (sell+strongSell) >= 50% of total analysts
    low_conviction      -> composite conviction score < 40
```

### Cooldown persistence

- Cooldown state is a dict mapping alert key (`"{symbol}:{condition}"`) to the Unix timestamp
  when it last fired.
- State is persisted to `data/alert_cooldowns.json` after every `_record()` call.
- File writes use `FileLock` (`data/alert_cooldowns.lock`) + atomic `os.replace()` via a `.tmp`
  file to prevent corruption under concurrent requests.
- Expired entries (older than `COOLDOWN_TTL = 86400` seconds) are pruned on every write.
- On startup the engine loads the JSON file; if it is missing or malformed, it starts with an
  empty dict (no cooldowns suppressed).

### Alert key format

```
"{SYMBOL}:earnings"
"{SYMBOL}:big_mover"
"{SYMBOL}:congressional_trade"
"{SYMBOL}:analyst_downgrade"
"{SYMBOL}:low_conviction"
```

---

## 8. Frontend Architecture

### Layout

```
App.tsx
  |-- Sidebar (lg: visible, sm: hidden)
  |     useSidebar(isPaperTrading)
  |       real  -> GET /api/portfolio
  |       paper -> GET /api/paper-portfolio
  |
  |-- ChatPanel
        useChat({ onToolCall })
          -> POST /api/chat
          -> onToolCall triggers sidebar.refresh() when
             portfolio_summary | paper_trade | morning_briefing called
```

### Hooks

**`useChat`**
- Maintains `messages: ChatMessage[]` and `isLoading` state.
- Session ID is generated once per browser and stored in `localStorage` under
  `ghostfolio-session-id`. This maps to LangGraph's `thread_id`, which drives the SQLite
  checkpointer for conversation persistence.
- On success, appends the assistant message (with `confidence`, `verificationIssues`,
  `dataSources`). On `ChatError`, appends a red error bubble.

**`useSidebar`**
- `isPaperTrading` flag determines which endpoint to call.
- Re-fetches whenever the flag changes (via `useEffect` on `refresh` callback) and on
  explicit `refresh()` calls triggered by tool callbacks.
- Exposes `error: string | null` and `refresh` for the "Failed to load / Retry" sidebar state.

### Message rendering (`MessageBubble.tsx`)

Each assistant message is passed through a RichCard parser before being rendered as markdown.
If the content matches a known tool output structure (e.g., starts with `Morning Briefing` or
`Holding Detail:`), `RichCard.tsx` renders a structured card component instead of raw text.

RichCard parsers:
- `MorningBriefingCard` — 6 styled sub-cards: Portfolio Overview, Top Movers, Earnings Watch,
  Market Signals, Congressional Watch, Macro Snapshot, Action Items
- `HoldingDetailCard` — header with P&L, smart summary badges, position grid, price target
  range bar, expandable news / analyst / earnings sections

`VerificationBanner` is rendered below the message when `confidence` is `medium` or `low`, or
when `verificationIssues` is non-empty. The banner is collapsible.

`DataSourceBadges` renders colored pills for each entry in `dataSources`:
- blue = Finnhub
- green = Alpha Vantage
- purple = FMP
- indigo = Ghostfolio

### Paper trading mode

Toggled by `PaperTradeToggle` in the chat input bar. When active:
- Sidebar switches from `GET /api/portfolio` to `GET /api/paper-portfolio`.
- Sidebar uses amber/orange gradient and shows "PAPER MODE" badge.
- `PortfolioValue` shows "Paper Portfolio Value" / "Total P&L" labels.
- Chat sends `paper_trading: true` in the request body; `chat.py` prepends a paper trading
  instruction block to the message content before it reaches the agent.
- Suggested queries change to paper-trade-oriented examples.

### Model selector

`ModelSelector` fetches `GET /api/models` on mount. Selected model ID is passed as `model` in
each chat request. If the fetch fails, the component shows "Couldn't load models" in red.

---

## 9. Data Flow Diagrams

### Chat endpoint

```
POST /api/chat
  |
  v
[Optional] Prepend paper trading instruction
  |
  v
AlertEngine.check_alerts()
  Phase 1: asyncio.gather(quote+earnings+congressional for all holdings)
  Phase 2: asyncio.gather(analyst+sentiment+PT for flagged only)
  -> alerts: list[str]  (filtered by cooldown)
  |
  v
[alerts] Prepend "ALERTS:\n- ...\n\nUser message: ..." to content
  |
  v
agent.ainvoke(HumanMessage(content), thread_id=session_id)
  -> LangGraph ReAct loop (max 25 iterations)
     pre_model_hook: summarize old messages, compact tool results
     LLM selects tools
     Tools execute (asyncio.gather internally)
     Tools append [DATA_SOURCES: ...] metadata
  -> AIMessage(final response)
  |
  v
Extract this turn's messages (after last HumanMessage)
  _extract_data_sources(tool_outputs)  -> data_sources: list[str]
  _strip_data_sources_line(tool_outputs) -> clean tool_outputs
  _extract_citations(messages)         -> citations: list[Citation]
  |
  v
run_verification_pipeline(response_text, tool_outputs, client)
  -> PipelineResult(confidence, modified_response_text, issues)
  |
  v
ChatResponse { response, confidence, tool_calls, tool_outputs,
               citations, verification_issues, verification_details,
               data_sources, session_id }
```

### Sidebar (real mode)

```
GET /api/portfolio
  |
  asyncio.gather(
    client.get_portfolio_holdings(),
    client.get_portfolio_performance("1d")
  )
  |
  v
PortfolioResponse {
  total_value, daily_change, daily_change_percent,
  positions: [{ symbol, name, quantity, price, value, allocation, currency }]
}
```

### Sidebar (paper mode)

```
GET /api/paper-portfolio
  |
  load_portfolio()  (reads data/paper_portfolio.json with filelock)
  |
  asyncio.gather(
    client.lookup_symbol(sym) + client.get_symbol(ds, sym)
    ... for each held symbol
  )
  |
  v
PaperPortfolioResponse {
  cash, total_value, total_pnl, total_pnl_percent,
  positions: [{ symbol, quantity, avg_cost, current_price, value, pnl, pnl_percent, allocation }]
}
```

### Alert engine (per chat request)

```
check_alerts(client, finnhub, alpha_vantage, fmp, congressional)
  |
  [short-circuit if no external clients]
  |
  client.get_portfolio_holdings() -> symbols[]
  |
  Phase 1: asyncio.gather for all symbols
    finnhub.get_quote(sym)
    finnhub.get_earnings_calendar(sym)
    congressional.get_trades_summary(sym, days=3)
  |
  Evaluate:
    earnings_proximity -> 0-3 days  -> flagged
    big_mover          -> >=5%      -> flagged
    congressional_trade -> any      -> flagged
  |
  [no flagged symbols?] -> return alerts
  |
  Phase 2: asyncio.gather for flagged symbols only
    finnhub.get_analyst_recommendations(sym)
    alpha_vantage.get_news_sentiment(sym)
    fmp.get_price_target_consensus(sym)
  |
  Evaluate:
    analyst_downgrade  -> bearish >= 50%
    low_conviction     -> composite score < 40
  |
  Each fired alert: check cooldown, record + persist, prune expired
  |
  return alerts: list[str]
```

---

## 10. Deployment

### Platform: Railway

- **Backend service**: Python FastAPI app (`src/`), started with `uvicorn`.
- **Frontend service**: Vite build served as static files or via a separate Railway service.
- **Congressional API**: separate Railway microservice; connected via Railway private networking.
  The URL is passed as `CONGRESSIONAL_API_URL` env var and used as the `CongressionalClient`
  base URL. Empty = service disabled.

### Persistent storage

| File | Purpose | Locking |
|---|---|---|
| `data/checkpoints.db` | LangGraph SQLite checkpointer — conversation history survives restarts | `aiosqlite` / SQLite WAL |
| `data/paper_portfolio.json` | Paper trade positions and cash balance | `filelock` (`data/paper_portfolio.lock`) + `os.replace()` atomic write |
| `data/alert_cooldowns.json` | Alert cooldown timestamps | `filelock` (`data/alert_cooldowns.lock`) + `os.replace()` via `.tmp` |

### LLM routing

- Default model: `gpt-4o-mini` (called directly via OpenAI API, not through OpenRouter).
- All other models are routed through OpenRouter (`https://openrouter.ai/api/v1`).
- Agent instances are cached in-process per model name (`_agents: dict[str, object]`).

### In-memory caching

- `@ttl_cache(ttl=300)` on conviction_score and congressional tools: per-process, 5-minute TTL.
- Alpha Vantage macro data (Fed funds rate, CPI, 10Y treasury): 24-hour in-process dict
  (`_macro_cache`) in `morning_briefing.py`.
- Neither cache is shared across multiple Railway replicas.

### Environment variables

| Variable | Required | Description |
|---|---|---|
| `GHOSTFOLIO_ACCESS_TOKEN` | Yes | Ghostfolio API bearer token |
| `GHOSTFOLIO_BASE_URL` | No | Default: `http://localhost:3333` |
| `OPENAI_API_KEY` | Yes (default model) | Direct OpenAI access for gpt-4o-mini |
| `OPENROUTER_API_KEY` | No | Required for non-default models |
| `FINNHUB_API_KEY` | No | Enables Finnhub client |
| `ALPHA_VANTAGE_API_KEY` | No | Enables Alpha Vantage client |
| `FMP_API_KEY` | No | Enables FMP client |
| `CONGRESSIONAL_API_URL` | No | Enables Congressional client |
| `LANGSMITH_API_KEY` | No | LangSmith tracing |
| `MAX_CONTEXT_MESSAGES` | No | Default: 40 |
| `LOG_LEVEL` | No | Default: `debug` |

### LangSmith tracing

When `LANGSMITH_API_KEY` is set and `LANGCHAIN_TRACING_V2=true`, all agent runs are traced
to the `ghostfolio-agent` project on LangSmith.

---

## 11. API Reference

### POST /api/chat

Request:
```json
{
  "message": "What is in my portfolio?",
  "session_id": "uuid-v4",
  "model": "gpt-4o-mini-direct",
  "paper_trading": false
}
```

Response:
```json
{
  "response": "You hold 3 positions...",
  "session_id": "uuid-v4",
  "tool_calls": ["portfolio_summary"],
  "tool_outputs": ["Holdings: AAPL 10 shares..."],
  "confidence": "high",
  "citations": [
    {
      "claim": "Data from portfolio_summary",
      "tool_name": "portfolio_summary",
      "source_detail": "Holdings: AAPL..."
    }
  ],
  "verification_issues": [],
  "verification_details": {
    "numerical": "high",
    "hallucination": "high",
    "output_validation": "high",
    "domain_constraints": "high"
  },
  "data_sources": ["Finnhub", "Ghostfolio"]
}
```

Special cases:
- `GraphInterrupt` (activity_log confirmation): returns `response` = confirmation prompt,
  empty `tool_calls`/`tool_outputs`, `confidence = "high"`.
- Timeout after 90 s: returns low-confidence timeout message.

### GET /api/models

Response:
```json
{
  "models": [
    { "id": "gpt-4o-mini-direct", "name": "GPT-4o Mini (Direct)", "provider": "OpenAI Direct" },
    { "id": "anthropic/claude-sonnet-4", "name": "Claude Sonnet 4", "provider": "Anthropic" }
  ],
  "default": "gpt-4o-mini-direct"
}
```

### GET /api/portfolio

Response (`PortfolioResponse`):
```json
{
  "total_value": 52341.20,
  "daily_change": 134.50,
  "daily_change_percent": 0.26,
  "positions": [
    {
      "symbol": "AAPL",
      "name": "Apple Inc.",
      "quantity": 10,
      "price": 189.50,
      "value": 1895.00,
      "allocation": 3.6,
      "currency": "USD"
    }
  ]
}
```

### GET /api/paper-portfolio

Response (`PaperPortfolioResponse`):
```json
{
  "cash": 87234.10,
  "total_value": 100120.50,
  "total_pnl": 120.50,
  "total_pnl_percent": 0.12,
  "positions": [
    {
      "symbol": "NVDA",
      "quantity": 5,
      "avg_cost": 800.00,
      "current_price": 857.40,
      "value": 4287.00,
      "pnl": 287.00,
      "pnl_percent": 7.18,
      "allocation": 4.3
    }
  ]
}
```

---

## 12. Known Limitations and Future Work

### Fragile RichCard parsing

`RichCard.tsx` detects tool output type by pattern-matching the text content of assistant
messages (e.g., checking whether the string starts with "Morning Briefing" or contains
"Holding Detail:"). This approach is fragile because:
- Any wording change in a tool's output format silently breaks card rendering.
- The LLM can paraphrase tool output, causing the parser to miss the structured content.

The correct fix is to pass structured tool output JSON as a separate `tool_outputs` field on
`ChatMessage` and route rendering based on tool name, not text heuristics.

### No frontend test framework

There are no vitest or Jest tests in the frontend. Correctness is verified only via `tsc -b`
(type checking) and `vite build` (bundler validation). Component logic and hook behavior are
not regression-tested.

### In-memory TTL cache not shared across instances

`@ttl_cache(ttl=300)` and the macro data `_macro_cache` dict live in the process heap.
With multiple Railway replicas, each instance has its own independent cache, so the effective
cache hit rate is lower and the external API rate limits are hit N times faster (N = replicas).
Fix: replace with a shared Redis cache or Railway's shared volume.

### Unused Ghostfolio endpoints

The Ghostfolio client currently exposes 9 endpoints out of approximately 95 available. The
following are high-value candidates that should be added only when a feature task needs them
(do not add speculatively):
- `GET /api/v1/portfolio/dividends` — dividend history with groupBy support
- `GET /api/v1/portfolio/investments` — investment timeline
- `GET /api/v1/benchmarks/{dataSource}/{symbol}/{startDate}` — compare to S&P 500
- `GET /api/v1/market-data/markets` — market overview with optional historical data
- `GET /api/v1/market-data/{dataSource}/{symbol}` — historical prices (free tier may be limited)

### Single-turn alert injection

Alerts are injected as plain text into the user's message content on every chat request. This
means the agent always sees alerts regardless of what the user asked, which can cause the
agent to mention them even when irrelevant. A better approach would be a separate system-level
alert channel or a dedicated pre-turn agent state field.

### No background alert scheduler

Alerts are checked reactively on each chat request, not proactively on a schedule. A user who
does not send a message will not receive alerts. This is an intentional simplicity trade-off
documented in the alert engine design.
