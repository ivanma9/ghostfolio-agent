# New Tools Design: Performance, Risk Analysis, Paper Trading

**Date:** 2026-02-24
**Status:** Approved
**Type:** Feature — 3 New Backend Tools + Frontend RichCards

## Summary

Add 3 new tools to the AgentForge chat agent:
1. **Portfolio Performance** — time-series returns with chart
2. **Risk Analysis** — concentration, sector, currency exposure
3. **Paper Trading** — virtual portfolio sim with real prices, persistent JSON

## Tool 1: Portfolio Performance

### Backend

**New file:** `src/ghostfolio_agent/tools/portfolio_performance.py`

- LangChain `@tool` decorator, factory pattern matching existing tools
- Accepts a time period preset: 1D, 1W, 1M, 3M, 6M, 1Y, YTD, ALL
- Calls `client.get_portfolio_performance(date_range)`
- Returns formatted text with:
  - Total return ($ and %)
  - Start value, end value
  - Best day, worst day
  - Data points list (date, value) for frontend charting

**Client change:** `src/ghostfolio_agent/clients/ghostfolio.py`

- Add `get_portfolio_performance(date_range: str)` method
- Calls `GET /api/v1/portfolio/performance` with appropriate query params (`range` param)
- Returns JSON response with chart data and summary stats

**Agent wiring:** `src/ghostfolio_agent/agent/graph.py`

- Import and register `create_portfolio_performance_tool(client)` in the tools list

### Frontend

**Types** (`types/index.ts`):
```typescript
export interface PerformanceDataPoint {
  date: string
  value: number
}

export interface PerformanceData {
  period: string
  totalReturn: number
  totalReturnPercent: number
  startValue: number
  endValue: number
  bestDay: { date: string; percent: number }
  worstDay: { date: string; percent: number }
  dataPoints: PerformanceDataPoint[]
}
```

**RichCard addition** (`RichCard.tsx`):
- New `parsePerformance(text: string): PerformanceData | null` parser
- New `PerformanceCard` component:
  - recharts `LineChart` with `Area` fill showing portfolio value over time
  - Green gradient if positive return, red gradient if negative
  - Summary stats row below chart: total return, best/worst day
  - Period label in card header
- Wire to `tool_calls` containing `"portfolio_performance"`

---

## Tool 2: Risk Analysis

### Backend

**New file:** `src/ghostfolio_agent/tools/risk_analysis.py`

- LangChain `@tool` decorator, factory pattern
- No user input needed — analyzes current portfolio
- Calls `client.get_portfolio_holdings()` and `client.get_portfolio_details()`
- Computes:
  - **Concentration risk**: % of each holding, flag if any > 25%
  - **Sector breakdown**: group by sector from details data, show % per sector
  - **Currency breakdown**: group by currency, show % per currency
- Returns formatted text with all three breakdowns plus a risk summary sentence

**Client change:** None — `get_portfolio_details()` already exists in `ghostfolio.py` but is unused. Risk tool will call it.

**Agent wiring:** `src/ghostfolio_agent/agent/graph.py`

- Import and register `create_risk_analysis_tool(client)` in the tools list

### Frontend

**Types** (`types/index.ts`):
```typescript
export interface RiskData {
  concentrationRisk: {
    topHolding: { symbol: string; percent: number }
    isHighRisk: boolean
    warning: string | null
  }
  sectorBreakdown: Array<{ sector: string; percent: number }>
  currencyBreakdown: Array<{ currency: string; percent: number }>
  summary: string
}
```

**RichCard addition** (`RichCard.tsx`):
- New `parseRiskAnalysis(text: string): RiskData | null` parser
- New `RiskCard` component:
  - Horizontal bar chart for sector breakdown (colored bars with labels)
  - Small donut chart for currency split
  - Concentration warning banner (yellow/orange) if any holding > 25%
  - Matching existing RichCard styling
- Wire to `tool_calls` containing `"risk_analysis"`

---

## Tool 3: Paper Trading

### Backend

**New file:** `src/ghostfolio_agent/tools/paper_trade.py`

- LangChain `@tool` decorator, factory pattern
- Accepts natural language actions:
  - `"buy 10 AAPL"` — look up current price, deduct from cash, add position
  - `"sell 5 AAPL"` — validate ownership, add proceeds to cash, reduce position
  - `"show portfolio"` / `"status"` — display all positions with current P&L
- Starting balance: $100,000 virtual cash
- Validates:
  - Sufficient cash for buys
  - Sufficient shares for sells
  - Valid symbol (via existing symbol lookup)
- Gets current prices via `client.symbol_lookup()` for trade execution and P&L calc

**Persistence:**
- JSON file at `data/paper_portfolio.json`
- Schema:
  ```json
  {
    "cash": 100000.00,
    "positions": {
      "AAPL": { "quantity": 10, "avg_cost": 272.14, "total_cost": 2721.40 }
    },
    "trades": [
      { "timestamp": "2026-02-24T15:00:00Z", "action": "BUY", "symbol": "AAPL", "quantity": 10, "price": 272.14, "total": 2721.40 }
    ],
    "created_at": "2026-02-24T15:00:00Z"
  }
  ```
- Loaded on each tool call, saved after each trade
- Created with defaults if file doesn't exist

**Client change:** None — uses existing `symbol_lookup` endpoint for price data.

**Agent wiring:** `src/ghostfolio_agent/agent/graph.py`

- Import and register `create_paper_trade_tool(client)` in the tools list

### Frontend

**Types** (`types/index.ts`):
```typescript
export interface PaperPosition {
  symbol: string
  quantity: number
  avgCost: number
  currentPrice: number
  value: number
  pnl: number
  pnlPercent: number
}

export interface PaperPortfolio {
  cash: number
  totalValue: number
  totalPnl: number
  totalPnlPercent: number
  positions: PaperPosition[]
}

export interface PaperTradeResult {
  action: 'BUY' | 'SELL'
  symbol: string
  quantity: number
  price: number
  total: number
  cashRemaining: number
}
```

**RichCard addition** (`RichCard.tsx`):
- New `parsePaperPortfolio(text: string): PaperPortfolio | null` parser
- New `parsePaperTrade(text: string): PaperTradeResult | null` parser
- New `PaperPortfolioCard` component:
  - Table: symbol, qty, avg cost, current price, value, P&L, P&L %
  - Green/red coloring on P&L values
  - Footer row: cash remaining + total account value
- New `PaperTradeCard` component:
  - Confirmation card: "Bought 10 AAPL at $272.14"
  - Shows total deducted/received and cash remaining
- Wire to `tool_calls` containing `"paper_trade"`

---

## Files Changed Summary

### New files (3):
- `src/ghostfolio_agent/tools/portfolio_performance.py`
- `src/ghostfolio_agent/tools/risk_analysis.py`
- `src/ghostfolio_agent/tools/paper_trade.py`

### Modified files (6):
- `src/ghostfolio_agent/clients/ghostfolio.py` — add `get_portfolio_performance()` method
- `src/ghostfolio_agent/agent/graph.py` — register 3 new tools
- `frontend/src/types/index.ts` — add new type interfaces
- `frontend/src/components/Chat/RichCard.tsx` — add 4 new card components + parsers
- `frontend/src/components/Chat/MessageBubble.tsx` — add new tool names to stripRawData
- `frontend/src/hooks/useSidebar.ts` — no changes needed

### New directories:
- `data/` — for paper_portfolio.json (created at runtime, gitignored)

---

## Implementation Steps

1. Add `get_portfolio_performance()` to ghostfolio client
2. Create `portfolio_performance` tool
3. Create `risk_analysis` tool
4. Create `paper_trade` tool with JSON persistence
5. Register all 3 tools in agent graph
6. Add new TypeScript types
7. Build `PerformanceCard` with line chart
8. Build `RiskCard` with bar chart + donut + warning banner
9. Build `PaperPortfolioCard` and `PaperTradeCard`
10. Wire new cards to tool_calls detection in RichCard
11. Update MessageBubble stripRawData for new tool names
12. Add `data/` to .gitignore
