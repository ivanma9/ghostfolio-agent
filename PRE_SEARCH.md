# AgentForge Pre-Search Document

**Domain:** Finance (Ghostfolio)
**Date:** 2026-02-23
**Author:** Ivan Ma

---

## Phase 1: Define Your Constraints

### 1. Domain Selection

**Which domain:** Finance — forking [Ghostfolio](https://github.com/ghostfolio/ghostfolio), an open-source wealth management platform for tracking stocks, ETFs, and cryptocurrencies.

**Specific use cases:**

- **Portfolio Analysis Agent** — Natural language queries about holdings, allocation, risk, and performance ("What's my sector exposure?", "Am I too concentrated in tech?")
- **Transaction Intelligence** — Auto-categorization of imported transactions, duplicate detection, and data entry validation
- **Tax Optimization** — Capital gains estimation, tax-loss harvesting suggestions, long-term vs short-term gain analysis
- **Risk & Compliance** — Concentration warnings, currency exposure analysis, diversification scoring
- **Performance Attribution** — Explain what drove portfolio returns, benchmark comparisons, underperformer identification

**Verification requirements:**

- All numerical calculations (returns, allocations, tax estimates) must be cross-referenced against Ghostfolio's own computed data via its API
- Investment suggestions must include disclaimers and confidence scores
- Tax estimates must flag jurisdiction-specific assumptions
- No hallucinated ticker symbols or financial data — all must come from verified data sources

**Data sources needed:**

- Ghostfolio REST API (`/portfolio/details`, `/portfolio/performance`, `/order`, `/account`, `/symbol`)
- Market data via Ghostfolio's existing providers (Yahoo Finance, CoinGecko, Alpha Vantage)
- User's portfolio holdings, transactions, and account balances from the Ghostfolio database

---

### 2. Scale & Performance

**Expected query volume:** 100-500 queries/day during development and demo. Production target: 1,000-5,000 queries/day.

**Acceptable latency:**

- Single-tool queries (e.g., "What's my top holding?"): < 3 seconds
- Multi-step reasoning (e.g., "Analyze my portfolio risk and suggest rebalancing"): < 10 seconds
- Complex analysis with multiple API calls: < 15 seconds

**Concurrent user requirements:** 10-20 concurrent users for MVP. Agent processes requests sequentially per user but can handle multiple users in parallel via async FastAPI.

**Cost constraints for LLM calls:**

- Development budget: ~$50/week for LLM API calls
- Target production cost: < $0.05 per user query (average)
- Use Claude Haiku for simple tool routing, Claude Sonnet for complex reasoning
- Cache repeated queries and market data lookups

---

### 3. Reliability Requirements

**Cost of a wrong answer:**

- **High for tax/compliance:** Wrong tax estimates could lead to financial penalties. These must have clear disclaimers and confidence scores.
- **Medium for portfolio analysis:** Incorrect allocation percentages could lead to poor investment decisions. Cross-verify against Ghostfolio's computed values.
- **Low for educational queries:** Explaining concepts has lower stakes but still shouldn't hallucinate.

**Non-negotiable verification:**

- All portfolio numbers must match Ghostfolio's API responses (no hallucinated figures)
- Tax estimates must clearly state assumptions and limitations
- Investment suggestions must never be presented as financial advice
- Disclaimer on every response involving financial decisions

**Human-in-the-loop requirements:**

- All trade recommendations are advisory only — user must execute manually
- Tax-related outputs require user confirmation of jurisdiction and filing status
- Flag low-confidence responses (< 70%) for user review

**Audit/compliance needs:**

- Log all agent interactions (query, tool calls, responses) for review
- Track which data sources informed each response
- Maintain conversation history for regulatory traceability
- No PII stored in logs beyond user ID

---

### 4. Team & Skill Constraints

**Familiarity with agent frameworks:** Beginner — general Python experience, new to LangChain/LangGraph. Will use LangGraph for its structured state management which suits financial workflows.

**Experience with chosen domain:** Familiar with personal investing concepts (portfolios, diversification, P&L). Not a financial professional — will lean on Ghostfolio's existing calculations rather than reimplementing financial math.

**Comfort with eval/testing frameworks:** Comfortable with pytest. New to LLM eval frameworks — will use Braintrust or LangSmith for structured evaluation.

---

## Phase 2: Architecture Discovery

### 5. Agent Framework Selection

**Framework: LangGraph (Python)**

Rationale:

- Provides explicit state machines — ideal for multi-step financial workflows (e.g., "analyze portfolio → identify risks → suggest rebalancing")
- Better control flow than vanilla LangChain for complex reasoning chains
- Built-in support for conditional routing (e.g., route tax queries vs. portfolio queries to different tool sets)
- Good documentation and growing community
- State management is critical for financial conversations where context matters

**Architecture: Single agent with tool routing**

- One primary agent with multiple specialized tools
- LangGraph state graph manages conversation flow and tool selection
- Simpler to build, debug, and evaluate than multi-agent setups
- Can evolve to multi-agent later if needed

**State management:**

- LangGraph's built-in state management for conversation turns
- Redis (already in Ghostfolio stack) for session persistence
- PostgreSQL for long-term conversation history

**Tool integration complexity:** Medium — Ghostfolio has a clean REST API, so tools are mostly HTTP wrappers with response parsing. The challenge is in composing tool results into meaningful financial insights.

---

### 6. LLM Selection

**Primary LLM: Claude Sonnet 4.6** (`claude-sonnet-4-6`)

Rationale:

- Strong structured output and function calling support
- Excellent at financial reasoning and numerical analysis
- Good balance of capability and cost
- 200K context window handles large portfolio data

**Secondary LLM: Claude Haiku 4.5** (`claude-haiku-4-5-20251001`)

- For simple tool routing and classification tasks
- Reduces cost on high-volume, low-complexity queries

**Function calling:** Required — Claude's tool_use format maps cleanly to LangGraph tool definitions.

**Context window needs:** Most queries need < 10K tokens. Portfolio details for large portfolios could reach 20-50K tokens. 200K window provides ample headroom.

**Cost per query:**

- Simple queries (Haiku routing + Sonnet response): ~$0.01-0.03
- Complex multi-step (multiple Sonnet calls): ~$0.05-0.10
- Target average: $0.03/query

---

### 7. Tool Design

**Required Tools (6 total):**


| Tool                    | Input                                 | Output                                                                    | Data Source                                   |
| ----------------------- | ------------------------------------- | ------------------------------------------------------------------------- | --------------------------------------------- |
| `portfolio_summary`     | user_id, date_range                   | Holdings, allocation %, total value, performance                          | `GET /portfolio/details`                      |
| `portfolio_performance` | user_id, range (1d/1w/1m/1y/max)      | Returns, benchmarks, time series                                          | `GET /portfolio/performance`                  |
| `transaction_history`   | user_id, filters (date, type, symbol) | Transaction list, patterns, summaries                                     | `GET /order`                                  |
| `symbol_lookup`         | query string                          | Matching symbols, asset profiles, current price                           | `GET /symbol/lookup` + `GET /symbol/:ds/:sym` |
| `tax_estimator`         | user_id, tax_year, jurisdiction       | Capital gains breakdown, estimated tax liability                          | Computed from `/order` + `/portfolio/details` |
| `risk_analyzer`         | user_id                               | Concentration risk, sector exposure, currency risk, diversification score | Computed from `/portfolio/details`            |


**External API dependencies:**

- Ghostfolio REST API (primary — all tools route through this)
- No direct external API calls needed — Ghostfolio already aggregates Yahoo Finance, CoinGecko, etc.

**Mock vs real data for development:**

- Start with mock data for initial tool development and eval dataset creation
- Switch to real Ghostfolio instance (Docker) with seed data for integration testing
- Use Ghostfolio's demo account data for consistent testing

**Error handling per tool:**

- API timeout → Return partial data with warning, retry once
- Missing data → Return what's available, flag gaps clearly
- Invalid symbol → Return "not found" with suggestions from lookup
- Auth failure → Return clear error, don't retry
- Rate limiting → Queue and retry with exponential backoff

---

### 8. Observability Strategy

**Primary tool: LangSmith**

Rationale:

- Native LangGraph integration (minimal setup overhead)
- Built-in tracing for agent reasoning chains
- Eval dataset management and scoring
- Good for a beginner — visual trace debugging is invaluable

**Key metrics:**

1. **End-to-end latency** — Total response time per query
2. **Tool call success rate** — % of tool invocations that succeed
3. **LLM token usage** — Input/output tokens per request, cost per query
4. **Eval scores** — Correctness, tool selection accuracy, safety compliance
5. **Error rate** — % of queries that result in failures or fallbacks

**Real-time monitoring:** LangSmith dashboard for development. Will add alerting for production (error rate > 5%, latency > 15s).

**Cost tracking:** LangSmith tracks token usage. Will add custom logging for per-query cost calculation including tool execution time.

---

### 9. Eval Approach

**Correctness measurement:**

- Compare agent numerical outputs against Ghostfolio API ground truth
- Verify tool selection matches expected tool for each query type
- Check that responses include required disclaimers for financial queries
- Validate structured output format compliance

**Ground truth data sources:**

- Ghostfolio API responses (portfolio values, returns, holdings) — the source of truth
- Manually curated expected outputs for 50+ test cases
- Known-correct tax calculations for sample portfolios

**Automated vs human evaluation:**

- Automated: Tool selection accuracy, numerical correctness, response format, latency
- LLM-as-judge: Response quality, helpfulness, appropriate disclaimers
- Human: Edge cases, adversarial inputs, nuanced financial reasoning (spot-check 10%)

**CI integration:**

- Run eval suite on every PR
- Fail build if correctness drops below 80%
- Track eval scores over time in LangSmith
- Nightly full eval run (all 50+ cases)

---

### 10. Verification Design

**Claims that must be verified (implementing 4):**

1. **Numerical Accuracy** — All portfolio values, returns, and allocations must match Ghostfolio API data within 0.1% tolerance
2. **Hallucination Detection** — Flag any claims about holdings or transactions not present in the user's actual data
3. **Confidence Scoring** — Every response gets a confidence score (high/medium/low) based on data completeness and query complexity
4. **Domain Constraint Enforcement** — Responses must include financial disclaimers; agent must refuse to execute trades or provide specific buy/sell advice

**Fact-checking data sources:**

- Ghostfolio API is the single source of truth for user portfolio data
- Market data verified against Ghostfolio's data providers
- Tax rules verified against published IRS/tax authority guidelines

**Confidence thresholds:**

- High (> 90%): Direct data retrieval, simple calculations — respond normally
- Medium (70-90%): Multi-step reasoning, estimates — respond with caveats
- Low (< 70%): Ambiguous queries, incomplete data — flag for user review, ask clarifying questions

**Escalation triggers:**

- Query involves specific trade execution recommendations
- Tax estimate involves complex multi-jurisdiction scenarios
- User asks for advice that could constitute regulated financial advice
- Agent detects contradictory data from multiple sources

---

## Phase 3: Post-Stack Refinement

### 11. Failure Mode Analysis

**When tools fail:**

- Return a clear error message to the user explaining what happened
- Suggest alternative queries or manual lookup in Ghostfolio UI
- Log the failure with full context for debugging
- Never fabricate data to fill gaps from failed tools

**Ambiguous queries:**

- Ask clarifying questions ("Did you mean your total portfolio or a specific account?")
- Default to the most common interpretation with a note
- Provide multiple interpretations if reasonable

**Rate limiting and fallback:**

- Ghostfolio API: Unlikely to rate-limit (self-hosted), but implement 3-retry with backoff
- LLM API: Queue requests, degrade to Haiku if Sonnet is rate-limited
- Cache frequently requested data (portfolio summary, market prices) with 5-minute TTL

**Graceful degradation:**

- If LLM is down → Return raw tool data without natural language synthesis
- If Ghostfolio API is down → Inform user, suggest retrying later
- If specific tool fails → Complete the query with available tools, note what's missing

---

### 12. Security Considerations

**Prompt injection prevention:**

- Sanitize all user inputs before passing to LLM
- Tool outputs are treated as data, not instructions
- System prompt includes explicit injection defense instructions
- LangGraph's structured state prevents prompt leakage between turns

**Data leakage risks:**

- Portfolio data is sensitive PII — never log full portfolio details to external services
- LangSmith traces should redact financial values in production
- Agent should never expose one user's data to another
- API keys stored in environment variables, never in code

**API key management:**

- Ghostfolio API token: Environment variable `GHOSTFOLIO_ACCESS_TOKEN`
- Claude API key: Environment variable `ANTHROPIC_API_KEY`
- LangSmith API key: Environment variable `LANGSMITH_API_KEY`
- All secrets in `.env` file, excluded from version control

**Audit logging:**

- Log: timestamp, user_id, query, tools_called, response_summary, latency, cost
- Do NOT log: full portfolio data, specific financial values, API keys
- Retain logs for 90 days
- Store in PostgreSQL alongside Ghostfolio's database

---

### 13. Testing Strategy

**Unit tests for tools:**

- Each tool tested independently with mock Ghostfolio API responses
- Test happy path, error cases, edge cases (empty portfolio, single holding, 1000+ holdings)
- Test input validation and parameter parsing
- pytest with fixtures for mock data

**Integration tests for agent flows:**

- End-to-end tests with a real Ghostfolio instance (Docker + seed data)
- Test multi-turn conversations (context maintained correctly)
- Test tool chaining (portfolio analysis → risk assessment → recommendations)
- Verify response format and disclaimer inclusion

**Adversarial testing:**

- Prompt injection attempts ("Ignore previous instructions and...")
- Requests for specific trade execution
- Queries with manipulated financial data
- Attempts to access other users' data
- Edge cases: negative balances, zero holdings, currencies with extreme exchange rates

**Regression testing:**

- Eval suite runs on every commit
- Track metrics over time: correctness, tool selection accuracy, latency
- Alert on any metric regression > 5%

---

### 14. Open Source Planning

**What to release:** A reusable **Finance Agent Python package** (`ghostfolio-agent`) that provides:

- LangGraph-based agent with financial tools for Ghostfolio
- Eval dataset (50+ test cases) for financial agent benchmarking
- Tool implementations that can be adapted for other financial platforms
- Documentation for setup, configuration, and extension

**Licensing:** AGPL-3.0 (matching Ghostfolio's license for compatibility)

**Documentation requirements:**

- README with quick start guide
- Architecture diagram
- Tool reference documentation
- Eval dataset format specification
- Contributing guide

**Community engagement:**

- Submit PR to Ghostfolio repo with agent integration
- Publish eval dataset as a standalone resource
- Write a blog post / tutorial on building financial agents

---

### 15. Deployment & Operations

**Hosting approach:**

- Agent API: FastAPI deployed on Railway or Vercel (serverless)
- Ghostfolio: Docker Compose (PostgreSQL + Redis + Ghostfolio app)
- Option: Single Docker Compose that includes both Ghostfolio and the agent API

**CI/CD:**

- GitHub Actions: lint → test → eval → deploy
- Eval gate: Must pass 80% correctness before deploy
- Automatic deployment on merge to main

**Monitoring and alerting:**

- LangSmith for agent-specific observability
- Health check endpoint (`/health`) for uptime monitoring
- Alert on: error rate > 5%, p95 latency > 15s, eval score regression

**Rollback strategy:**

- Railway/Vercel instant rollback to previous deployment
- Database migrations are forward-only (no breaking schema changes)
- Feature flags for new tool rollouts

---

### 16. Iteration Planning

**User feedback collection:**

- Thumbs up/down on every agent response
- Optional text feedback field
- Track which queries users retry (indicates dissatisfaction)
- Monthly review of low-rated responses

**Eval-driven improvement cycle:**

1. Identify failing test cases from eval runs
2. Analyze failure patterns (wrong tool? bad reasoning? missing data?)
3. Improve prompt, add tools, or adjust verification
4. Re-run evals to confirm improvement
5. Deploy and monitor

**Feature prioritization:**

1. MVP: Basic portfolio Q&A with 3 tools (portfolio_summary, transaction_history, symbol_lookup)
2. Week 1: Add remaining tools (performance, tax_estimator, risk_analyzer)
3. Week 1: Eval framework + observability
4. Week 1: Verification layer + production hardening
5. Post-launch: Multi-turn planning conversations, goal tracking, automated alerts

**Long-term maintenance:**

- Keep tools updated as Ghostfolio API evolves
- Refresh eval dataset quarterly with new edge cases
- Monitor LLM model updates and re-evaluate performance
- Community PRs for new tools and use cases

---

## Architecture Summary

```
┌─────────────────────────────────────────────────┐
│                   User (Browser)                 │
│              Ghostfolio Angular UI               │
└──────────────────────┬──────────────────────────┘
                       │ Chat / Query
                       ▼
┌─────────────────────────────────────────────────┐
│              FastAPI Agent Server                │
│  ┌───────────────────────────────────────────┐  │
│  │           LangGraph Agent                 │  │
│  │  ┌─────────┐  ┌──────────┐  ┌─────────┐  │  │
│  │  │ Router  │→ │ Tool Exec │→ │Synthesize│ │  │
│  │  │ (Haiku) │  │          │  │ (Sonnet) │  │  │
│  │  └─────────┘  └────┬─────┘  └─────────┘  │  │
│  └─────────────────────┼─────────────────────┘  │
│                        │                         │
│  ┌─────────────────────┼─────────────────────┐  │
│  │              Tool Layer                    │  │
│  │  portfolio_summary  │  symbol_lookup       │  │
│  │  portfolio_perf     │  tax_estimator       │  │
│  │  transaction_hist   │  risk_analyzer       │  │
│  └─────────────────────┼─────────────────────┘  │
│                        │                         │
│  ┌─────────────────────┼─────────────────────┐  │
│  │         Verification Layer                 │  │
│  │  numerical_check │ hallucination_detect    │  │
│  │  confidence_score│ disclaimer_enforce      │  │
│  └─────────────────────┼─────────────────────┘  │
└────────────────────────┼────────────────────────┘
                         │ REST API calls
                         ▼
┌─────────────────────────────────────────────────┐
│            Ghostfolio Backend (NestJS)           │
│  ┌──────────┐  ┌──────────┐  ┌──────────────┐  │
│  │PostgreSQL│  │  Redis   │  │ Data Providers│  │
│  │          │  │          │  │ Yahoo/CoinGecko│ │
│  └──────────┘  └──────────┘  └──────────────┘  │
└─────────────────────────────────────────────────┘

Observability: LangSmith (traces, evals, metrics)
```

---

## Tech Stack (Our Agent Project)

### Core Dependencies

| Layer | Technology | Version | Purpose |
|-------|-----------|---------|---------|
| **Runtime** | Python | 3.12+ | Language runtime |
| **Package Manager** | uv | latest | Fast Python package management (replaces pip/poetry) |
| **Web Framework** | FastAPI | 0.115+ | Async REST API server |
| **ASGI Server** | uvicorn | 0.34+ | Production ASGI server for FastAPI |
| **Agent Framework** | langgraph | 0.3+ | State machine agent orchestration |
| **LLM Integration** | langchain-anthropic | 0.3+ | Claude model binding for LangChain/LangGraph |
| **HTTP Client** | httpx | 0.28+ | Async HTTP client for Ghostfolio API calls |
| **Data Validation** | pydantic | 2.10+ | Request/response schemas, tool input/output validation |
| **Database ORM** | sqlalchemy | 2.0+ | Conversation history + audit log persistence |
| **Database Migrations** | alembic | 1.14+ | Schema migrations for agent-specific tables |
| **Redis Client** | redis[hiredis] | 5.2+ | Session caching, tool response caching |
| **Financial Math** | numpy | 2.2+ | Portfolio allocation calculations, risk metrics |
| **Data Analysis** | pandas | 2.2+ | Transaction aggregation, time series analysis |

### Observability & Eval

| Technology | Version | Purpose |
|-----------|---------|---------|
| langsmith | 0.3+ | Tracing, eval datasets, scoring, LLM-as-judge |
| structlog | 24.4+ | Structured JSON logging for audit trail |

### Dev & Testing

| Technology | Version | Purpose |
|-----------|---------|---------|
| pytest | 8.3+ | Unit + integration tests |
| pytest-asyncio | 0.24+ | Async test support for FastAPI + httpx |
| pytest-cov | 6.0+ | Code coverage reporting |
| respx | 0.22+ | Mock httpx requests (Ghostfolio API mocks) |
| ruff | 0.9+ | Linting + formatting (replaces black/isort/flake8) |
| mypy | 1.14+ | Static type checking |
| pre-commit | 4.0+ | Git hook management for linting/formatting |

### Infrastructure

| Technology | Purpose |
|-----------|---------|
| Docker | Containerize agent service |
| Docker Compose | Orchestrate agent + Ghostfolio + PostgreSQL + Redis |
| GitHub Actions | CI/CD pipeline (lint → test → eval → deploy) |
| Railway | Production hosting |

---

## Project File Structure

```
ghostfolio-agent/
│
├── README.md                          # Quick start, architecture overview, API reference
├── LICENSE                            # AGPL-3.0 (matching Ghostfolio)
├── pyproject.toml                     # Project metadata, dependencies, tool config (ruff, mypy, pytest)
├── uv.lock                           # Locked dependency versions
├── .env.example                       # Template for required environment variables
├── .gitignore
├── .pre-commit-config.yaml            # Pre-commit hooks (ruff, mypy)
├── Dockerfile                         # Agent service container
├── docker-compose.yml                 # Full stack: agent + ghostfolio + postgres + redis
├── docker-compose.dev.yml             # Dev: postgres + redis only (agent runs locally)
│
├── .github/
│   └── workflows/
│       ├── ci.yml                     # PR checks: lint → test → eval gate (80%)
│       └── deploy.yml                 # Deploy to Railway on merge to main
│
├── src/
│   └── ghostfolio_agent/
│       │
│       ├── __init__.py
│       ├── main.py                    # FastAPI app entrypoint, lifespan, CORS, middleware
│       ├── config.py                  # Pydantic Settings: env vars, feature flags, model config
│       │
│       ├── api/                       # --- FastAPI Routes ---
│       │   ├── __init__.py
│       │   ├── router.py              # Top-level API router, mounts sub-routers
│       │   ├── chat.py                # POST /api/chat — main agent query endpoint
│       │   ├── health.py              # GET /api/health — liveness + readiness checks
│       │   └── feedback.py            # POST /api/feedback — thumbs up/down on responses
│       │
│       ├── agent/                     # --- LangGraph Agent Core ---
│       │   ├── __init__.py
│       │   ├── graph.py               # LangGraph StateGraph definition: nodes, edges, compile
│       │   ├── state.py               # TypedDict state schema (messages, tool_results, metadata)
│       │   ├── nodes.py               # Graph node functions: route, execute_tools, synthesize
│       │   └── prompts.py             # System prompts, tool selection prompts, synthesis prompts
│       │
│       ├── tools/                     # --- Agent Tools (one file per tool) ---
│       │   ├── __init__.py
│       │   ├── base.py                # Base tool class, shared httpx client, error handling
│       │   ├── portfolio_summary.py   # Fetches holdings, allocation, total value from /portfolio/details
│       │   ├── portfolio_performance.py # Returns, time series from /portfolio/performance
│       │   ├── transaction_history.py # Transaction list + patterns from /order
│       │   ├── symbol_lookup.py       # Symbol search + asset profile from /symbol/lookup
│       │   ├── tax_estimator.py       # Capital gains computation from /order + /portfolio/details
│       │   └── risk_analyzer.py       # Concentration, sector, currency risk from /portfolio/details
│       │
│       ├── verification/              # --- Verification Layer ---
│       │   ├── __init__.py
│       │   ├── numerical.py           # Cross-check agent numbers vs Ghostfolio API (0.1% tolerance)
│       │   ├── hallucination.py       # Flag claims about holdings/transactions not in user data
│       │   ├── confidence.py          # Score responses high/medium/low based on data completeness
│       │   └── disclaimer.py          # Enforce financial disclaimers on applicable responses
│       │
│       ├── clients/                   # --- External Service Clients ---
│       │   ├── __init__.py
│       │   └── ghostfolio.py          # Async httpx wrapper for Ghostfolio REST API (/api/v1/*)
│       │
│       ├── models/                    # --- Pydantic Schemas ---
│       │   ├── __init__.py
│       │   ├── api.py                 # Request/response models for FastAPI endpoints
│       │   ├── ghostfolio.py          # Typed models for Ghostfolio API responses
│       │   └── agent.py               # Agent state models, tool input/output schemas
│       │
│       ├── db/                        # --- Database (conversation history + audit) ---
│       │   ├── __init__.py
│       │   ├── engine.py              # SQLAlchemy async engine + session factory
│       │   ├── models.py              # ORM models: Conversation, Message, EvalResult, AuditLog
│       │   └── repository.py          # CRUD operations for conversations and audit logs
│       │
│       └── observability/             # --- Logging, Tracing, Metrics ---
│           ├── __init__.py
│           ├── logging.py             # structlog configuration, JSON output, redaction filters
│           ├── tracing.py             # LangSmith setup, custom metadata injection
│           └── metrics.py             # Latency tracking, token usage, cost calculation
│
├── alembic/                           # --- Database Migrations ---
│   ├── alembic.ini
│   ├── env.py
│   └── versions/                      # Migration files (auto-generated)
│       └── 001_initial_schema.py      # conversations, messages, eval_results, audit_logs tables
│
├── tests/                             # --- Test Suite ---
│   ├── __init__.py
│   ├── conftest.py                    # Shared fixtures: mock Ghostfolio API, test DB, fake portfolios
│   │
│   ├── unit/                          # Fast, isolated, no external dependencies
│   │   ├── __init__.py
│   │   ├── test_tools/                # One test file per tool
│   │   │   ├── test_portfolio_summary.py
│   │   │   ├── test_portfolio_performance.py
│   │   │   ├── test_transaction_history.py
│   │   │   ├── test_symbol_lookup.py
│   │   │   ├── test_tax_estimator.py
│   │   │   └── test_risk_analyzer.py
│   │   ├── test_verification/         # One test file per verifier
│   │   │   ├── test_numerical.py
│   │   │   ├── test_hallucination.py
│   │   │   ├── test_confidence.py
│   │   │   └── test_disclaimer.py
│   │   ├── test_ghostfolio_client.py  # HTTP client with mocked responses
│   │   └── test_config.py            # Config loading, env var validation
│   │
│   ├── integration/                   # Requires running Ghostfolio instance (Docker)
│   │   ├── __init__.py
│   │   ├── test_agent_flow.py         # End-to-end: query → tool calls → response
│   │   ├── test_multi_turn.py         # Conversation context maintained across turns
│   │   └── test_api_endpoints.py      # FastAPI route tests with real agent
│   │
│   └── eval/                          # LLM evaluation suite
│       ├── __init__.py
│       ├── run_evals.py               # Script to execute eval suite against LangSmith
│       └── datasets/                  # Eval test cases (JSON)
│           ├── happy_path.json        # 20+ standard queries with expected outputs
│           ├── edge_cases.json        # 10+ boundary conditions, missing data
│           ├── adversarial.json       # 10+ prompt injection, unsafe requests
│           └── multi_step.json        # 10+ complex queries requiring tool chaining
│
└── docs/                              # --- Documentation ---
    ├── architecture.md                # System design, data flow, component responsibilities
    ├── tools.md                       # Tool reference: inputs, outputs, Ghostfolio API mapping
    ├── eval_dataset_spec.md           # Eval case format, scoring criteria, adding new cases
    └── deployment.md                  # Docker setup, Railway deploy, env var reference
```

### File Structure Design Decisions

**Why `src/ghostfolio_agent/` layout (src layout)?**
- Standard Python packaging convention — prevents accidental imports from the project root
- `ghostfolio_agent` is the importable package name, matching the PyPI package name
- Makes the project installable via `pip install -e .` for development

**Why one file per tool in `tools/`?**
- Each tool maps 1:1 to a Ghostfolio API interaction pattern — keeping them separate makes it clear which API endpoints each tool depends on
- Tools can be tested independently with their own mock fixtures
- New tools are added by creating a single file + registering in `__init__.py` — no modification to existing tools needed

**Why separate `verification/` from `agent/`?**
- Verification runs *after* the agent produces a response, as a post-processing step — it's not part of the agent's reasoning loop
- Verifiers can be toggled independently (e.g., disable `disclaimer.py` for internal testing)
- Each verifier has different data dependencies (numerical needs API data, hallucination needs user portfolio, confidence is computed from metadata)

**Why `clients/ghostfolio.py` as a single file?**
- All 6 tools call the same Ghostfolio REST API — a shared async httpx client with auth, base URL, timeout, and retry logic avoids duplication
- If we later add a second external API (e.g., direct Yahoo Finance), it gets its own client file

**Why `models/` split into `api.py`, `ghostfolio.py`, `agent.py`?**
- `api.py` = what the user sends/receives (FastAPI request/response schemas)
- `ghostfolio.py` = what Ghostfolio's API returns (typed so we catch API changes)
- `agent.py` = internal state (LangGraph state, tool inputs/outputs)
- Three distinct boundaries, three distinct schema files — prevents coupling between API contract, external data, and internal state

**Why `tests/eval/datasets/` as JSON files?**
- Eval datasets are uploaded to LangSmith but also checked into git for version control
- JSON format matches LangSmith's dataset import format
- Split by category (happy_path, edge_cases, adversarial, multi_step) so we can run targeted eval subsets during development

---

## Cost Analysis (Required)

### Development & Testing Costs (Estimated)


| Item                            | Estimated Cost |
| ------------------------------- | -------------- |
| Claude Sonnet API (development) | ~$30/week      |
| Claude Haiku API (routing)      | ~$5/week       |
| LangSmith (free tier)           | $0             |
| Railway hosting (dev)           | ~$5/month      |
| **Total development (1 week)**  | **~$40**       |


### Production Cost Projections


| Scale         | Queries/Day | Monthly Cost   |
| ------------- | ----------- | -------------- |
| 100 users     | 500         | ~$50/month     |
| 1,000 users   | 5,000       | ~$450/month    |
| 10,000 users  | 50,000      | ~$4,000/month  |
| 100,000 users | 500,000     | ~$35,000/month |


**Assumptions:** 5 queries/user/day average, ~1,500 tokens/query (input+output), 30% of queries use Haiku routing only, 70% require Sonnet, tool calls average 1.5 per query.

---

## Technology Selection Rationale

### Agent Framework: LangGraph (Python)

**Chosen over:** LangChain (vanilla), CrewAI, AutoGen, Semantic Kernel, Custom


| Framework       | Pros                                                                                   | Cons                                                                                                 | Verdict                                                                                          |
| --------------- | -------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------ |
| **LangGraph**   | Explicit state graphs, conditional routing, native LangChain tool reuse, cycle support | Newer, smaller community than LangChain                                                              | **Selected**                                                                                     |
| LangChain       | Largest ecosystem, most tutorials, extensive tool library                              | Implicit chains are hard to debug, limited control flow for multi-step workflows                     | Too opaque for financial workflows where we need deterministic step ordering                     |
| CrewAI          | Great for multi-agent role-based collaboration                                         | Overkill for single-agent MVP, adds coordination complexity, less control over individual tool calls | Multi-agent not needed — our tools share the same data source (Ghostfolio API)                   |
| AutoGen         | Strong conversational agents, code execution                                           | Microsoft ecosystem bias, conversation-centric model doesn't fit tool-heavy financial queries        | Conversation-between-agents paradigm is a poor fit; we need tool orchestration, not agent debate |
| Semantic Kernel | Enterprise-grade, .NET + Python support, plugins                                       | Heavier enterprise focus, plugin model adds abstraction we don't need                                | Designed for enterprise integration patterns; too heavy for a focused financial agent            |
| Custom          | Full control, no framework overhead                                                    | Must build state management, tool routing, retry logic from scratch                                  | Time constraint (1 week) makes this impractical for a beginner                                   |


**Why LangGraph is best for Ghostfolio specifically:**

- Financial queries naturally decompose into **state machine steps**: parse query → select tools → fetch data → verify numbers → synthesize response. LangGraph models this explicitly with nodes and edges rather than implicit chain behavior.
- Ghostfolio's API returns structured JSON from endpoints like `/portfolio/details` and `/order`. LangGraph's state object can accumulate results from multiple API calls before passing to the synthesis step — critical when a query like "compare my portfolio risk to last quarter" needs data from both `/portfolio/details` and `/portfolio/performance`.
- LangGraph supports **conditional edges** — we can route tax queries through the tax_estimator tool and skip it for simple portfolio lookups, without building custom routing logic.
- LangGraph is built on top of LangChain, so we get access to LangChain's tool abstractions, output parsers, and Claude integration without the rigidity of LangChain's sequential chain model.

---

### LLM: Claude Sonnet 4.6 (primary) + Claude Haiku 4.5 (routing)

**Chosen over:** GPT-4o/GPT-5, Llama 3, Mistral, Gemini


| LLM                   | Pros                                                                                          | Cons                                                                                                  | Verdict                                                                                                                   |
| --------------------- | --------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------- |
| **Claude Sonnet 4.6** | Excellent structured output, strong numerical reasoning, 200K context, native tool_use format | Anthropic-only ecosystem                                                                              | **Selected (primary)**                                                                                                    |
| **Claude Haiku 4.5**  | Ultra-fast, ultra-cheap, sufficient for classification/routing                                | Limited reasoning depth                                                                               | **Selected (routing)**                                                                                                    |
| GPT-4o / GPT-5        | Largest ecosystem, function calling mature, wide adoption                                     | Higher cost at scale, OpenAI rate limits more aggressive, tool_call format is slightly more verbose   | Close second; Claude's tool_use format is cleaner for LangGraph integration and the cost/performance ratio edges it out   |
| Llama 3 (70B/405B)    | Free inference (self-hosted), no API costs, full control                                      | Requires GPU infrastructure, weaker function calling than Claude/GPT, hosting complexity adds latency | Self-hosting adds operational burden incompatible with 1-week timeline; function calling quality is notably behind Claude |
| Mistral Large         | Good European option, competitive pricing                                                     | Smaller tool-use ecosystem, less battle-tested for financial reasoning                                | Function calling support is less mature; fewer examples of financial domain use                                           |
| Gemini 2.0            | Large context window (1M+), Google ecosystem                                                  | Tool calling less mature than Claude/GPT, inconsistent structured output                              | Context window is overkill; tool_use reliability is what matters for an agent, and Gemini lags here                       |


**Why Claude is best for Ghostfolio specifically:**

- **Numerical precision matters in finance.** Claude Sonnet demonstrates strong performance on tasks requiring exact numerical reasoning — critical when we're computing portfolio allocation percentages or tax estimates from Ghostfolio's transaction data.
- **Structured output reliability.** Our agent needs to parse tool results (JSON from Ghostfolio API) and produce structured responses with confidence scores and disclaimers. Claude's tool_use format produces well-structured, schema-compliant outputs more consistently than alternatives.
- **Two-tier cost optimization.** Haiku handles the cheap, fast question of "which tool should I call?" (~$0.001/call), while Sonnet handles the expensive reasoning. For Ghostfolio, many queries are simple lookups ("What's my portfolio value?") that Haiku can route directly — only complex queries ("Analyze my tax-loss harvesting opportunities across all accounts") need Sonnet's full reasoning.
- **200K context window.** A user with 500+ transactions and 50+ holdings could generate 30-40K tokens of portfolio data. Claude's 200K window handles this comfortably without truncation, unlike models with smaller windows that would force us to implement summarization logic.

---

### Backend: Python / FastAPI

**Chosen over:** NestJS/TypeScript (matching Ghostfolio), Express.js, Django, Flask


| Backend             | Pros                                                                            | Cons                                                                                                              | Verdict                                                                                  |
| ------------------- | ------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------- |
| **Python/FastAPI**  | Native LangGraph/LangChain support, async, fastest Python framework, type hints | Different language from Ghostfolio (TypeScript)                                                                   | **Selected**                                                                             |
| NestJS (TypeScript) | Same language as Ghostfolio, could integrate directly into codebase             | LangChain.js is significantly behind Python LangChain in features and maturity; LangGraph JS is even more nascent | Language match doesn't compensate for the immature JS agent ecosystem                    |
| Express.js          | Lightweight, same ecosystem as Ghostfolio                                       | Same LangChain.js maturity problem, less structured than FastAPI                                                  | Same JS ecosystem limitation, plus no built-in validation/docs                           |
| Django              | Batteries-included, ORM, admin panel                                            | Too heavy for an API-only agent service, synchronous by default                                                   | Overhead of Django's ORM/admin/middleware is wasted on a stateless agent API             |
| Flask               | Simple, familiar                                                                | No async support, no automatic OpenAPI docs, less structured                                                      | Missing async is a dealbreaker — agent tool calls are I/O-bound and must be non-blocking |


**Why Python/FastAPI despite Ghostfolio being TypeScript:**

This is the most important architectural tradeoff in the project. Ghostfolio is a **NestJS + Angular + TypeScript** monorepo. The natural choice would be to build the agent in TypeScript to match. Here's why we're deliberately choosing Python instead:

1. **LangGraph Python >> LangGraph JS.** The Python ecosystem for AI agents is 12-18 months ahead of JavaScript. LangGraph for Python has stable APIs, extensive documentation, production examples, and active community support. LangGraph.js exists but has fewer features, less documentation, and a smaller community. For a beginner building under time pressure, this maturity gap is decisive.
2. **The agent communicates via REST API, not code integration.** Our agent doesn't need to import Ghostfolio's TypeScript modules or share code. It calls Ghostfolio's REST API (`/portfolio/details`, `/order`, etc.) over HTTP — the same API any client uses. Language match provides zero benefit for HTTP-based integration.
3. **Python AI library ecosystem is unmatched.** Beyond LangGraph: numpy for financial calculations, pandas for transaction analysis, scipy for risk metrics — all used by our tax_estimator and risk_analyzer tools. The JavaScript equivalents are either nonexistent or significantly less capable.
4. **FastAPI's async model matches agent workloads.** Agent requests are I/O-bound (waiting on LLM API calls + Ghostfolio API calls). FastAPI's native async/await with uvicorn handles concurrent requests efficiently. A single FastAPI instance can serve 20+ concurrent users while waiting on external API responses.
5. **Deployment is independent.** The agent runs as a separate Docker container alongside Ghostfolio's existing Docker Compose stack. Adding a Python service to a Docker Compose file is one `service:` block — the language of the container is irrelevant to Docker.

**Integration pattern:**

```
Ghostfolio (NestJS/TypeScript)  ←── REST API ──→  Agent (Python/FastAPI)
       :3333/api/v1                                    :8000/api
```

The agent is a **sidecar service** that consumes Ghostfolio's API. It could be rewritten in any language without changing Ghostfolio's codebase.

---

### Observability: LangSmith

**Chosen over:** Braintrust, Langfuse, Weights & Biases, Arize Phoenix, Helicone, Custom


| Tool             | Pros                                                                                                                        | Cons                                                                                      | Verdict                                                                                                                               |
| ---------------- | --------------------------------------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------- |
| **LangSmith**    | Native LangGraph integration (2 lines of code), visual trace debugging, built-in eval runner, dataset management, free tier | Vendor lock-in to LangChain ecosystem, limited free tier (5K traces/month)                | **Selected**                                                                                                                          |
| Braintrust       | Strong eval framework, CI integration, prompt versioning                                                                    | No native LangGraph integration — requires custom instrumentation                         | Better for teams already doing evals; setup overhead too high for MVP                                                                 |
| Langfuse         | Open source, self-hostable, good tracing + evals                                                                            | Requires self-hosting for full features, less polished UI than LangSmith                  | Strong alternative — would choose this if we needed to self-host for data privacy; for MVP, LangSmith's managed service wins on speed |
| Weights & Biases | Excellent experiment tracking, model monitoring                                                                             | AI agent tracing is a bolt-on, not core product; traces are less intuitive than LangSmith | Built for ML experiment tracking, not agent debugging — wrong primary use case                                                        |
| Arize Phoenix    | Open source, drift detection, good for production monitoring                                                                | Tracing is newer feature, eval support less mature                                        | Better for production monitoring phase; not ideal for development-phase debugging                                                     |
| Helicone         | Proxy-based (zero code changes), cost tracking, caching                                                                     | Limited to LLM call logging — doesn't trace tool execution or agent reasoning             | Only sees LLM calls, not the full agent workflow; misses tool execution traces which are critical for debugging                       |
| Custom Logging   | Full control, no vendor dependency                                                                                          | Must build dashboard, trace visualization, eval runner from scratch                       | Impractical in 1-week timeline; would spend more time on observability than the agent itself                                          |


**Why LangSmith is best for Ghostfolio specifically:**

- **Two-line integration with LangGraph.** Set `LANGCHAIN_TRACING_V2=true` and `LANGCHAIN_API_KEY=...` — every LangGraph node execution, tool call, and LLM invocation is automatically traced. No custom instrumentation needed.
- **Visual trace debugging is critical for a beginner.** When the agent calls `portfolio_summary` but returns incorrect allocation percentages, LangSmith's trace view shows exactly: what the LLM received → what tool it selected → what the Ghostfolio API returned → how the LLM synthesized the response. This visual chain is invaluable for debugging financial accuracy issues.
- **Built-in eval datasets and scoring.** We can upload our 50+ test cases directly to LangSmith, run evals against the agent, and track correctness scores over time — all in the same tool we use for tracing.
- **Free tier covers MVP.** 5,000 traces/month is sufficient for development and early testing. Production would require a paid plan, but that's a later decision.

---

### Deployment: Railway + Docker Compose

**Chosen over:** Vercel, Modal, AWS Lambda, GCP Cloud Run, bare EC2/VPS


| Platform      | Pros                                                                                      | Cons                                                                                                                                 | Verdict                                                                     |
| ------------- | ----------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------ | --------------------------------------------------------------------------- |
| **Railway**   | Simple deploy from Git, supports Docker, persistent PostgreSQL/Redis, $5/month hobby plan | Less control than raw cloud                                                                                                          | **Selected**                                                                |
| Vercel        | Great for Next.js/frontend, serverless                                                    | Python support is limited, serverless cold starts hurt agent latency, 10s function timeout is too short for multi-step agent queries | Timeout limit is a dealbreaker — complex agent queries need 10-15s          |
| Modal         | Excellent for Python, GPU support, serverless                                             | Overkill for HTTP API, pricing model favors batch workloads                                                                          | Great for ML inference, but our agent is a simple HTTP API, not a batch job |
| AWS Lambda    | Scalable, pay-per-use                                                                     | Cold starts (3-5s for Python), 15min max timeout, complex setup (API Gateway, IAM, etc.)                                             | Cold starts + setup complexity are hostile to a 1-week timeline             |
| GCP Cloud Run | Docker-native, auto-scaling, generous free tier                                           | More complex setup than Railway, GCP IAM is a time sink                                                                              | Strong option for production; Railway wins on setup speed for MVP           |
| Bare EC2/VPS  | Full control, cheapest at scale                                                           | Must manage OS, security patches, scaling, SSL, etc.                                                                                 | Too much ops overhead for a solo 1-week sprint                              |


**Why Railway for Ghostfolio specifically:**

- **Docker Compose compatibility.** Ghostfolio already runs via Docker Compose (PostgreSQL + Redis + NestJS app). Railway can deploy Docker containers from a repo, so we can deploy the agent service alongside Ghostfolio without changing the deployment model.
- **Persistent services.** Unlike serverless platforms, Railway keeps the service running — no cold starts. This is critical because our agent's first response after a cold start would add 3-5s of latency (loading LangGraph, initializing LLM client, etc.).
- **Built-in PostgreSQL and Redis.** Railway offers managed PostgreSQL and Redis as add-ons. Since Ghostfolio already needs both, Railway can host the entire stack (Ghostfolio + Agent + PostgreSQL + Redis) in one project.

---

### Eval Framework: LangSmith Evals (integrated with observability)

**Chosen over:** Braintrust Evals, DeepEval, RAGAS, pytest-only, Custom


| Eval Tool           | Pros                                                                               | Cons                                                                | Verdict                                                                                                   |
| ------------------- | ---------------------------------------------------------------------------------- | ------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------- |
| **LangSmith Evals** | Same platform as tracing, dataset management, LLM-as-judge support, CI integration | Tied to LangSmith platform                                          | **Selected**                                                                                              |
| Braintrust Evals    | Excellent scoring system, prompt versioning, strong CI hooks                       | Separate platform from tracing — doubles the tooling surface        | Would add a second platform to learn; LangSmith handles both tracing + evals                              |
| DeepEval            | Open source, pytest integration, many built-in metrics                             | Less mature, documentation gaps, no native LangGraph support        | Promising but too early-stage to rely on for a deadline-driven project                                    |
| RAGAS               | Strong RAG evaluation metrics                                                      | Designed for RAG pipelines, not tool-calling agents                 | Wrong evaluation paradigm — we're evaluating tool selection and numerical accuracy, not retrieval quality |
| pytest-only         | Simple, familiar, no new tools                                                     | No LLM-as-judge, no dataset management, no score tracking over time | Sufficient for unit tests but inadequate for evaluating natural language response quality                 |
| Custom              | Full control over metrics                                                          | Must build dataset management, scoring, tracking, CI integration    | Same time constraint issue — building eval infrastructure is a project unto itself                        |


**Why LangSmith Evals for Ghostfolio specifically:**

- **Unified platform.** Tracing and evaluation in the same tool means we can click from a failing eval case directly to the trace that produced it — seeing exactly where the agent went wrong (wrong tool? bad API response? LLM hallucination?).
- **LLM-as-judge for financial responses.** Some eval criteria can't be automated with string matching — "Did the agent provide appropriate disclaimers?" and "Is this tax explanation helpful?" require LLM-based evaluation. LangSmith supports this natively.
- **Dataset versioning.** As we add test cases (starting with 50, growing over time), LangSmith tracks dataset versions so we can compare eval scores across different dataset versions — critical for understanding whether score changes are from agent improvements or harder test cases.

---

### Database Integration: Reuse Ghostfolio's PostgreSQL + Redis

**Chosen over:** Separate database, SQLite, MongoDB, in-memory only


| Approach                                  | Pros                                                                                                     | Cons                                                                       | Verdict                                                                                           |
| ----------------------------------------- | -------------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------- |
| **Reuse Ghostfolio's PostgreSQL + Redis** | Zero additional infrastructure, Redis already available for caching, PostgreSQL for conversation history | Couples agent to Ghostfolio's database lifecycle                           | **Selected**                                                                                      |
| Separate PostgreSQL                       | Clean separation of concerns                                                                             | Extra infrastructure to manage, extra cost, extra Docker service           | Unnecessary isolation — agent data is lightweight and logically belongs alongside Ghostfolio data |
| SQLite                                    | Simple, file-based, no server needed                                                                     | No concurrent write support, can't share with Ghostfolio's PostgreSQL      | Inadequate for concurrent agent sessions                                                          |
| MongoDB                                   | Flexible schema for conversation history                                                                 | Additional dependency, different query language, another service to manage | Introducing a third database technology into the stack adds complexity for no benefit             |
| In-memory only                            | Simplest, fastest                                                                                        | Conversation history lost on restart, no audit trail                       | Violates our audit/compliance requirements                                                        |


**Why reusing Ghostfolio's infra is best:**

- Ghostfolio already runs PostgreSQL (via Prisma) and Redis (for caching). Both are already in the Docker Compose stack. Adding agent tables to PostgreSQL and using Redis for session caching requires **zero new infrastructure**.
- The agent's data model is simple: `conversations` table (user_id, messages, timestamps) and `eval_results` table (test_case_id, score, timestamp). These are lightweight additions to Ghostfolio's existing schema.
- Redis is already configured for Ghostfolio's caching. We can reuse the same Redis instance for agent session state and tool response caching with a key prefix (`agent:session:`*, `agent:cache:*`).

---

## Decision Log


| Decision      | Choice                              | Alternatives Considered                              | Key Differentiator                                                                 |
| ------------- | ----------------------------------- | ---------------------------------------------------- | ---------------------------------------------------------------------------------- |
| Domain        | Finance (Ghostfolio)                | Healthcare (OpenEMR)                                 | Rich REST API, structured financial data, clear tool opportunities                 |
| Framework     | LangGraph (Python)                  | LangChain, CrewAI, AutoGen, Semantic Kernel, Custom  | Explicit state machines for multi-step financial workflows                         |
| LLM           | Claude Sonnet 4.6 + Haiku 4.5       | GPT-4o/5, Llama 3, Mistral, Gemini                   | Strongest structured output + numerical reasoning at best cost ratio               |
| Backend       | Python / FastAPI                    | NestJS (matching Ghostfolio), Express, Django, Flask | Python AI ecosystem maturity; REST API integration makes language match irrelevant |
| Observability | LangSmith                           | Braintrust, Langfuse, W&B, Arize Phoenix, Helicone   | Native LangGraph integration (2-line setup), unified tracing + evals               |
| Eval          | LangSmith Evals                     | Braintrust Evals, DeepEval, RAGAS, pytest-only       | Same platform as tracing, LLM-as-judge, dataset versioning                         |
| Database      | Reuse Ghostfolio PostgreSQL + Redis | Separate DB, SQLite, MongoDB, in-memory              | Zero new infrastructure, both already in Docker Compose                            |
| Deployment    | Railway + Docker                    | Vercel, Modal, AWS Lambda, GCP Cloud Run, EC2        | No cold starts, Docker Compose compatible, built-in PostgreSQL/Redis               |
| License       | AGPL-3.0                            | MIT, Apache 2.0                                      | Must match Ghostfolio's AGPL-3.0 for fork compatibility                            |


