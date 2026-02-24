# MVP Design — Ghostfolio Agent

**Date:** 2026-02-24
**Scope:** 24-hour MVP sprint

## What We're Building

A Python/FastAPI sidecar service that connects to a running Ghostfolio instance and provides a natural language chat interface for querying portfolio data via LangGraph-powered tools.

## Data Flow

```
User message → POST /api/chat
  → LangGraph agent (Claude Sonnet selects tools)
    → Tools call Ghostfolio REST API (httpx)
      → Verification checks numerical accuracy
        → Agent synthesizes natural language response
          → Returns to user
```

## MVP Scope

### In Scope
- FastAPI server with `POST /api/chat` and `GET /api/health`
- 3 tools: `portfolio_summary`, `transaction_history`, `symbol_lookup`
- LangGraph StateGraph with nodes: route → execute_tools → synthesize
- In-memory conversation history (dict keyed by session_id)
- Numerical accuracy verification (cross-check vs Ghostfolio API)
- LangSmith tracing (2-line env var setup)
- 5 eval test cases as JSON
- Dockerfile + Railway deployment
- Ghostfolio running via Docker Compose with seed data

### Out of Scope (post-MVP)
- tax_estimator, risk_analyzer, portfolio_performance tools
- Haiku routing tier (MVP uses Sonnet for everything)
- PostgreSQL/SQLAlchemy conversation persistence
- Redis caching
- CI/CD eval gate
- Feedback endpoint
- Frontend chat UI

## Build Order
1. Ghostfolio Docker + seed data
2. Project scaffold (pyproject.toml, FastAPI skeleton)
3. Ghostfolio async httpx client
4. 3 tools
5. LangGraph agent graph
6. POST /api/chat endpoint with conversation history
7. Numerical verification
8. 5 eval test cases
9. Deploy to Railway
