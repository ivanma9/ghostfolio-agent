# AgentForge

AI-powered portfolio assistant for [Ghostfolio](https://ghostfol.io). Chat with your portfolio using natural language.

## Features

- **6 AI Tools**: Portfolio summary, transaction history, symbol lookup, performance analysis, risk analysis, paper trading
- **Chat-first UI**: React frontend with rich inline data cards (tables, charts, trade confirmations)
- **Portfolio sidebar**: Live portfolio value, allocation donut chart, top holdings
- **Paper trading simulator**: $100K virtual cash, persistent across restarts

## Quick Start

### 1. Start Ghostfolio

```bash
docker compose -f docker-compose.dev.yml up -d
# Wait ~2 min, then open http://localhost:3333 to get an API token
```

### 2. Configure environment

```bash
cp .env.example .env
# Fill in: ANTHROPIC_API_KEY, GHOSTFOLIO_ACCESS_TOKEN
```

### 3. Start the agent

```bash
uv sync
uv run uvicorn ghostfolio_agent.main:app --reload --port 8000
```

### 4. Start the frontend

```bash
cd frontend
npm install
npm run dev
# Open http://localhost:5173
```

## Tools

| Tool | Description | Example |
|------|-------------|---------|
| `portfolio_summary` | Holdings, values, allocations | "What's in my portfolio?" |
| `transaction_history` | Buy/sell/dividend activity | "Show my AAPL transactions" |
| `symbol_lookup` | Search stocks, ETFs, crypto | "Look up NVDA" |
| `portfolio_performance` | Returns over time (1D-ALL) | "Show my 3 month performance" |
| `risk_analysis` | Concentration, sector, currency risk | "Analyze my portfolio risk" |
| `paper_trade` | Virtual trading with $100K | "Paper buy 10 AAPL" |

## Evals

Golden-set evaluation tests verify all 6 tools work correctly. Tests are located at [`tests/eval/datasets/mvp_test_cases.json`](tests/eval/datasets/mvp_test_cases.json).

### Running evals

```bash
# Make sure the agent is running on port 8000 first
uv run python tests/eval/run_evals.py
```

### Test cases (8 total)

| ID | Category | Tool Tested | Description |
|----|----------|-------------|-------------|
| tc_001 | happy_path | `portfolio_summary` | Lists all holdings |
| tc_002 | happy_path | `transaction_history` | Filters transactions by symbol |
| tc_003 | happy_path | `symbol_lookup` | Looks up ticker symbols |
| tc_004 | edge_case | `portfolio_summary` | Infers sector allocation from raw data |
| tc_005 | safety | (none) | Refuses investment advice |
| tc_006 | happy_path | `portfolio_performance` | Returns performance metrics |
| tc_007 | happy_path | `risk_analysis` | Analyzes portfolio risk |
| tc_008 | happy_path | `paper_trade` | Executes virtual trade |

### Pre-commit hook

Evals run automatically on every `git commit` via a pre-commit hook. Commits are blocked if any eval fails.

### LangSmith evals (optional)

```bash
uv run python tests/eval/langsmith_upload_dataset.py
uv run pytest tests/eval/test_langsmith_evals.py -v
```

## Architecture

```
frontend/          React (Vite) + Tailwind chat UI
src/ghostfolio_agent/
  api/chat.py      POST /api/chat endpoint
  agent/graph.py   LangGraph agent with Claude
  tools/           6 tool implementations
  clients/         Ghostfolio API client
  verification/    Numerical accuracy checks
tests/eval/        Golden-set evaluation suite
```

## Tech Stack

- **Backend**: FastAPI, LangGraph, LangChain, Claude Sonnet 4.6
- **Frontend**: React, Vite, Tailwind CSS, Recharts
- **Data**: Ghostfolio REST API, PostgreSQL, Redis
- **Observability**: LangSmith (optional)
