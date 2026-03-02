# P0 Sidebar UX Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Make sidebar holdings clickable (triggering chat deep dives) and surface alert engine output in a "Needs Attention" sidebar section.

**Architecture:** Extend `ChatResponse` with structured `alerts` field. Frontend `useChat` accumulates alerts in state, passes to Sidebar. TopHoldings and AllocationChart become interactive, sending "Tell me about {SYMBOL}" on click. New `AlertsSection` component renders between PortfolioValue and AllocationChart.

**Tech Stack:** Python/Pydantic (backend model), React/TypeScript/Tailwind (frontend), Recharts (chart interaction)

---

### Task 1: Backend — Add AlertItem model and extend ChatResponse

**Files:**
- Modify: `src/ghostfolio_agent/models/api.py`
- Modify: `src/ghostfolio_agent/api/chat.py`
- Test: `tests/unit/test_chat_alerts_response.py`

**Step 1: Write the failing test**

Create `tests/unit/test_chat_alerts_response.py`:

```python
"""Tests for structured alert items in ChatResponse."""

import pytest
from ghostfolio_agent.models.api import AlertItem, ChatResponse


class TestAlertItem:
    def test_alert_item_warning(self):
        item = AlertItem(
            symbol="AAPL",
            condition="earnings_proximity",
            message="AAPL earnings in 2 days",
            severity="warning",
        )
        assert item.symbol == "AAPL"
        assert item.severity == "warning"

    def test_alert_item_critical(self):
        item = AlertItem(
            symbol="TSLA",
            condition="low_conviction",
            message="TSLA conviction score dropped to 25/100",
            severity="critical",
        )
        assert item.severity == "critical"

    def test_alert_item_invalid_severity(self):
        with pytest.raises(Exception):
            AlertItem(
                symbol="X",
                condition="test",
                message="test",
                severity="invalid",
            )


class TestChatResponseAlerts:
    def test_chat_response_includes_alerts_field(self):
        resp = ChatResponse(
            response="Hello",
            session_id="s1",
            alerts=[
                AlertItem(symbol="AAPL", condition="big_mover", message="AAPL up 6%", severity="warning"),
            ],
        )
        assert len(resp.alerts) == 1
        assert resp.alerts[0].symbol == "AAPL"

    def test_chat_response_alerts_defaults_empty(self):
        resp = ChatResponse(response="Hi", session_id="s1")
        assert resp.alerts == []
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_chat_alerts_response.py -v`
Expected: FAIL — `AlertItem` not importable

**Step 3: Write AlertItem model and extend ChatResponse**

In `src/ghostfolio_agent/models/api.py`, add after the `Citation` class:

```python
class AlertItem(BaseModel):
    symbol: str = Field(..., description="Ticker symbol")
    condition: str = Field(..., description="Alert condition key e.g. earnings_proximity")
    message: str = Field(..., description="Human-readable alert message")
    severity: Literal["warning", "critical"] = Field(..., description="Alert severity level")
```

Add `from typing import Literal` at top of file.

Add to `ChatResponse`:

```python
    alerts: list[AlertItem] = Field(
        default_factory=list, description="Structured alerts fired during this request"
    )
```

**Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/test_chat_alerts_response.py -v`
Expected: PASS (all 5 tests)

**Step 5: Commit**

```bash
git add tests/unit/test_chat_alerts_response.py src/ghostfolio_agent/models/api.py
git commit -m "feat: add AlertItem model and alerts field to ChatResponse"
```

---

### Task 2: Backend — Parse alert strings into structured AlertItems in chat endpoint

**Files:**
- Modify: `src/ghostfolio_agent/api/chat.py`
- Test: `tests/unit/test_chat_alert_parsing.py`

**Step 1: Write the failing test**

Create `tests/unit/test_chat_alert_parsing.py`:

```python
"""Tests for parsing alert strings into structured AlertItems."""

import pytest
from ghostfolio_agent.api.chat import _parse_alert_strings


class TestParseAlertStrings:
    def test_earnings_alert(self):
        items = _parse_alert_strings([
            "AAPL earnings in 2 days (2026-03-03) — consider position sizing"
        ])
        assert len(items) == 1
        assert items[0].symbol == "AAPL"
        assert items[0].condition == "earnings_proximity"
        assert items[0].severity == "warning"

    def test_big_mover_alert(self):
        items = _parse_alert_strings([
            "TSLA up 6.2% today ($185.50) — significant daily move"
        ])
        assert len(items) == 1
        assert items[0].symbol == "TSLA"
        assert items[0].condition == "big_mover"
        assert items[0].severity == "warning"

    def test_low_conviction_alert(self):
        items = _parse_alert_strings([
            "NVDA conviction score dropped to 25/100 (Sell) — review position"
        ])
        assert len(items) == 1
        assert items[0].symbol == "NVDA"
        assert items[0].condition == "low_conviction"
        assert items[0].severity == "critical"

    def test_analyst_downgrade_alert(self):
        items = _parse_alert_strings([
            "MSFT analyst consensus shifted to Sell (3 of 20 analysts bullish) — monitor closely"
        ])
        assert len(items) == 1
        assert items[0].symbol == "MSFT"
        assert items[0].condition == "analyst_downgrade"
        assert items[0].severity == "critical"

    def test_congressional_trade_alert(self):
        items = _parse_alert_strings([
            "AAPL has 5 congressional trades in the last 3 days (3 buys, 2 sells) — Bullish"
        ])
        assert len(items) == 1
        assert items[0].symbol == "AAPL"
        assert items[0].condition == "congressional_trade"
        assert items[0].severity == "warning"

    def test_multiple_alerts(self):
        items = _parse_alert_strings([
            "AAPL earnings in 1 days (2026-03-02) — consider position sizing",
            "TSLA conviction score dropped to 30/100 (Sell) — review position",
        ])
        assert len(items) == 2
        assert items[0].severity == "warning"
        assert items[1].severity == "critical"

    def test_empty_list(self):
        items = _parse_alert_strings([])
        assert items == []

    def test_unrecognized_alert_uses_fallback(self):
        items = _parse_alert_strings(["UNKNOWN some weird alert text"])
        assert len(items) == 1
        assert items[0].symbol == "UNKNOWN"
        assert items[0].condition == "unknown"
        assert items[0].severity == "warning"
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_chat_alert_parsing.py -v`
Expected: FAIL — `_parse_alert_strings` not importable

**Step 3: Implement `_parse_alert_strings` in chat.py**

Add to `src/ghostfolio_agent/api/chat.py` (after the imports, before the router):

```python
from ghostfolio_agent.models.api import AlertItem  # add to existing import line

# Alert condition → severity mapping
_ALERT_SEVERITY: dict[str, str] = {
    "earnings_proximity": "warning",
    "big_mover": "warning",
    "low_conviction": "critical",
    "analyst_downgrade": "critical",
    "congressional_trade": "warning",
}

# Alert string patterns → condition keys
_ALERT_PATTERNS: list[tuple[str, str]] = [
    ("earnings in", "earnings_proximity"),
    ("significant daily move", "big_mover"),
    ("conviction score dropped", "low_conviction"),
    ("analyst consensus shifted", "analyst_downgrade"),
    ("congressional trades", "congressional_trade"),
]


def _parse_alert_strings(alert_strings: list[str]) -> list[AlertItem]:
    """Parse alert engine string outputs into structured AlertItem objects."""
    items: list[AlertItem] = []
    for alert_str in alert_strings:
        # Extract symbol (first word)
        parts = alert_str.split(maxsplit=1)
        symbol = parts[0] if parts else "?"

        # Match condition by substring
        condition = "unknown"
        for pattern, cond in _ALERT_PATTERNS:
            if pattern in alert_str:
                condition = cond
                break

        severity = _ALERT_SEVERITY.get(condition, "warning")
        items.append(AlertItem(
            symbol=symbol,
            condition=condition,
            message=alert_str,
            severity=severity,
        ))
    return items
```

**Step 4: Wire into chat endpoint**

In the `chat()` function in `chat.py`, after the alert check block (around line 323), change:

```python
        if alerts:
            alert_block = "ALERTS:\n" + "\n".join(f"- {a}" for a in alerts)
            content = f"{alert_block}\n\nUser message: {content}"
```

to:

```python
        structured_alerts: list[AlertItem] = []
        if alerts:
            alert_block = "ALERTS:\n" + "\n".join(f"- {a}" for a in alerts)
            content = f"{alert_block}\n\nUser message: {content}"
            structured_alerts = _parse_alert_strings(alerts)
```

Then in the `ChatResponse` return (around line 414), add `alerts=structured_alerts`:

```python
        return ChatResponse(
            response=pipeline_result.response_text,
            session_id=request.session_id,
            tool_calls=list(set(tool_calls_made)),
            tool_outputs=tool_outputs,
            confidence=pipeline_result.overall_confidence,
            citations=citations,
            verification_issues=pipeline_result.all_issues,
            verification_details=verification_details,
            data_sources=data_sources,
            alerts=structured_alerts,
        )
```

Also add `alerts=[]` to the timeout and GraphInterrupt early returns.

**Step 5: Run test to verify it passes**

Run: `uv run pytest tests/unit/test_chat_alert_parsing.py -v`
Expected: PASS (all 8 tests)

**Step 6: Run full test suite**

Run: `uv run pytest tests/unit/ -v`
Expected: All pass

**Step 7: Commit**

```bash
git add tests/unit/test_chat_alert_parsing.py src/ghostfolio_agent/api/chat.py
git commit -m "feat: parse alert strings into structured AlertItems in chat endpoint"
```

---

### Task 3: Frontend — Add AlertItem type and extend ChatResponse/useChat

**Files:**
- Modify: `frontend/src/types/index.ts`
- Modify: `frontend/src/hooks/useChat.ts`

**Step 1: Add AlertItem type to `frontend/src/types/index.ts`**

Add after the `HoldingDetailData` interface:

```typescript
export interface AlertItem {
  symbol: string
  condition: string
  message: string
  severity: 'warning' | 'critical'
}
```

Add `alerts` field to `ChatResponse`:

```typescript
export interface ChatResponse {
  // ... existing fields ...
  alerts: AlertItem[]
}
```

**Step 2: Update `useChat` hook to track alerts**

In `frontend/src/hooks/useChat.ts`:

- Import `AlertItem` from types
- Add `activeAlerts` state: `const [activeAlerts, setActiveAlerts] = useState<AlertItem[]>([])`
- After processing chat response, merge alerts:

```typescript
        // Merge alerts (key by symbol:condition, newer replaces older)
        if (data.alerts && data.alerts.length > 0) {
          setActiveAlerts(prev => {
            const merged = new Map(prev.map(a => [`${a.symbol}:${a.condition}`, a]))
            for (const alert of data.alerts) {
              merged.set(`${alert.symbol}:${alert.condition}`, alert)
            }
            return Array.from(merged.values())
          })
        }
```

- Update `UseChatReturn` to include `activeAlerts: AlertItem[]`
- Return `activeAlerts` from the hook

**Step 3: Verify TypeScript compiles**

Run: `cd frontend && npx tsc -b --noEmit`
Expected: No errors

**Step 4: Commit**

```bash
git add frontend/src/types/index.ts frontend/src/hooks/useChat.ts
git commit -m "feat: add AlertItem type and alert accumulation in useChat hook"
```

---

### Task 4: Frontend — Make TopHoldings clickable with hover states

**Files:**
- Modify: `frontend/src/components/Sidebar/TopHoldings.tsx`
- Modify: `frontend/src/components/Sidebar/Sidebar.tsx`

**Step 1: Update TopHoldings to accept `onHoldingClick` prop**

Replace the current `TopHoldingsProps` and component to make rows interactive:

```typescript
interface TopHoldingsProps {
  holdings: Holding[];
  onHoldingClick?: (symbol: string) => void;
}
```

Each holding row becomes a `<button>` with hover states:
- `cursor-pointer` always
- Hover: `bg-slate-50/60`, symbol shifts to `text-indigo-600`, 2px left border `border-l-2 border-indigo-400` fades in, right chevron fades in
- Transitions: `transition-all duration-150 ease-out`

**Step 2: Update Sidebar to pass `onHoldingClick`**

Add `onHoldingClick?: (symbol: string) => void` to `SidebarProps`.

Pass it to `<TopHoldings onHoldingClick={onHoldingClick} />`.

**Step 3: Verify it compiles**

Run: `cd frontend && npx tsc -b --noEmit`

**Step 4: Commit**

```bash
git add frontend/src/components/Sidebar/TopHoldings.tsx frontend/src/components/Sidebar/Sidebar.tsx
git commit -m "feat: make TopHoldings rows clickable with hover states"
```

---

### Task 5: Frontend — Make AllocationChart segments clickable

**Files:**
- Modify: `frontend/src/components/Sidebar/AllocationChart.tsx`

**Step 1: Add `onHoldingClick` prop to AllocationChart**

```typescript
interface AllocationChartProps {
  holdings: Holding[];
  onHoldingClick?: (symbol: string) => void;
}
```

**Step 2: Make pie segments clickable**

Add `onClick` handler to each `<Cell>`:

```typescript
<Cell
  key={`cell-${index}`}
  fill={COLORS[index % COLORS.length]}
  cursor="pointer"
  onClick={() => onHoldingClick?.(data[index].name)}
/>
```

Add `activeShape` prop to `<Pie>` for hover scale effect — use Recharts' `activeShape` render prop to increase `outerRadius` by 4px on hover. Add `activeIndex` state to track which segment is hovered.

Also make the legend items clickable:

```typescript
<button
  key={holding.symbol}
  onClick={() => onHoldingClick?.(holding.symbol)}
  className="flex items-center justify-between text-xs w-full hover:bg-slate-50/60 rounded px-1 py-0.5 transition-colors duration-150 cursor-pointer"
>
```

**Step 3: Wire in Sidebar**

Pass `onHoldingClick` to `<AllocationChart />` in Sidebar.tsx.

**Step 4: Verify it compiles**

Run: `cd frontend && npx tsc -b --noEmit`

**Step 5: Commit**

```bash
git add frontend/src/components/Sidebar/AllocationChart.tsx frontend/src/components/Sidebar/Sidebar.tsx
git commit -m "feat: make AllocationChart segments and legend clickable"
```

---

### Task 6: Frontend — Create AlertsSection component

**Files:**
- Create: `frontend/src/components/Sidebar/AlertsSection.tsx`

**Step 1: Create the AlertsSection component**

Create `frontend/src/components/Sidebar/AlertsSection.tsx`:

```typescript
import { useState } from 'react'
import type { AlertItem } from '../../types'

interface AlertsSectionProps {
  alerts: AlertItem[]
  onAlertClick?: (symbol: string) => void
}

export function AlertsSection({ alerts, onAlertClick }: AlertsSectionProps) {
  const [expanded, setExpanded] = useState(false)

  if (alerts.length === 0) return null

  // Sort: critical first, then warning
  const sorted = [...alerts].sort((a, b) => {
    if (a.severity === 'critical' && b.severity !== 'critical') return -1
    if (b.severity === 'critical' && a.severity !== 'critical') return 1
    return 0
  })

  const hasCritical = sorted.some(a => a.severity === 'critical')
  const visible = expanded ? sorted : sorted.slice(0, 3)
  const overflow = sorted.length - 3

  return (
    <div className="rounded-2xl bg-amber-50/40 border border-amber-100 p-5 shadow-sm">
      {/* Header */}
      <div className="flex items-center gap-2 mb-3">
        <span className={`w-1.5 h-1.5 rounded-full animate-pulse ${hasCritical ? 'bg-red-400' : 'bg-amber-400'}`} />
        <p className="text-xs font-bold uppercase tracking-wider text-gray-500">
          Needs Attention
        </p>
        <span className="ml-auto text-[10px] font-medium text-gray-400">
          {alerts.length}
        </span>
      </div>

      {/* Alert rows */}
      <div className="space-y-0">
        {visible.map((alert, index) => (
          <div key={`${alert.symbol}:${alert.condition}`}>
            <button
              onClick={() => onAlertClick?.(alert.symbol)}
              className="group w-full text-left py-2.5 pl-3 pr-2 rounded-lg hover:bg-white/60 transition-all duration-150 cursor-pointer relative"
            >
              {/* Left severity border */}
              <div className={`absolute left-0 top-1/2 -translate-y-1/2 w-[3px] h-3/5 rounded-full ${
                alert.severity === 'critical' ? 'bg-red-400' : 'bg-amber-400'
              }`} />

              <div className="flex items-center justify-between">
                <div className="flex-1 min-w-0 pr-2">
                  <span className="font-bold text-[13px] text-gray-900">{alert.symbol}</span>
                  <p className="text-xs text-gray-500 truncate mt-0.5">
                    {alert.message.replace(`${alert.symbol} `, '')}
                  </p>
                </div>
                {/* Chevron on hover */}
                <svg
                  className="w-3.5 h-3.5 text-gray-300 opacity-0 group-hover:opacity-100 transition-opacity duration-150 flex-shrink-0"
                  fill="none"
                  stroke="currentColor"
                  viewBox="0 0 24 24"
                >
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
                </svg>
              </div>
            </button>
            {index < visible.length - 1 && <div className="h-px bg-amber-100/60 mx-3" />}
          </div>
        ))}
      </div>

      {/* Overflow toggle */}
      {overflow > 0 && !expanded && (
        <button
          onClick={() => setExpanded(true)}
          className="mt-2 text-xs text-amber-600 hover:text-amber-700 font-medium transition-colors cursor-pointer"
        >
          +{overflow} more
        </button>
      )}
      {expanded && overflow > 0 && (
        <button
          onClick={() => setExpanded(false)}
          className="mt-2 text-xs text-amber-600 hover:text-amber-700 font-medium transition-colors cursor-pointer"
        >
          Show less
        </button>
      )}
    </div>
  )
}
```

**Step 2: Verify it compiles**

Run: `cd frontend && npx tsc -b --noEmit`

**Step 3: Commit**

```bash
git add frontend/src/components/Sidebar/AlertsSection.tsx
git commit -m "feat: create AlertsSection sidebar component"
```

---

### Task 7: Frontend — Wire everything together in App.tsx and Sidebar

**Files:**
- Modify: `frontend/src/App.tsx`
- Modify: `frontend/src/components/Sidebar/Sidebar.tsx`

**Step 1: Update App.tsx**

- Pass `chat.activeAlerts` to Sidebar as `alerts` prop
- Pass `handleSend` to Sidebar as `onHoldingClick` — wrap it so it sends `"Tell me about {SYMBOL}"`:

```typescript
const handleHoldingClick = useCallback(
  (symbol: string) => {
    handleSend(`Tell me about ${symbol}`)
  },
  [handleSend],
)
```

- Pass to Sidebar:

```typescript
<Sidebar
  holdings={sidebar.holdings}
  portfolioValue={sidebar.portfolioValue}
  dailyChange={sidebar.dailyChange}
  isLoading={sidebar.isLoading}
  isPaperTrading={isPaperTrading}
  error={sidebar.error}
  onRetry={sidebar.refresh}
  alerts={chat.activeAlerts}
  onHoldingClick={handleHoldingClick}
/>
```

**Step 2: Update Sidebar.tsx**

- Import `AlertsSection` and `AlertItem`
- Add to `SidebarProps`: `alerts?: AlertItem[]`, `onHoldingClick?: (symbol: string) => void`
- Insert `<AlertsSection>` between PortfolioValue and AllocationChart (with `mt-1` spacing class for 12px gap):

```tsx
{/* Alerts (between value and allocation) */}
{alerts && alerts.length > 0 && (
  <section>
    <AlertsSection alerts={alerts} onAlertClick={onHoldingClick} />
  </section>
)}
```

- Pass `onHoldingClick` to both `<TopHoldings>` and `<AllocationChart>`

**Step 3: Verify it compiles**

Run: `cd frontend && npx tsc -b --noEmit`

**Step 4: Verify full frontend builds**

Run: `cd frontend && npx vite build`
Expected: Build succeeds

**Step 5: Commit**

```bash
git add frontend/src/App.tsx frontend/src/components/Sidebar/Sidebar.tsx
git commit -m "feat: wire alerts and clickable holdings through App to Sidebar"
```

---

### Task 8: Run full test suite and verify

**Step 1: Run backend tests**

Run: `uv run pytest tests/unit/ -v`
Expected: All pass (existing + new tests)

**Step 2: Run frontend type check and build**

Run: `cd frontend && npx tsc -b --noEmit && npx vite build`
Expected: Both succeed

**Step 3: Commit if any fixes needed**

---

### Task 9: Update documentation

**Files:**
- Modify: Memory file at `/Users/ivanma/.claude/projects/-Users-ivanma-Desktop-gauntlet-AgentForge/memory/MEMORY.md`

**Step 1: Update MEMORY.md**

Add a section documenting:
- AlertItem model in `models/api.py`
- `alerts` field on ChatResponse
- `_parse_alert_strings()` in `chat.py`
- `useChat` now exposes `activeAlerts`
- Sidebar accepts `alerts` and `onHoldingClick` props
- New `AlertsSection` component
- TopHoldings and AllocationChart are now interactive

**Step 2: Commit**

```bash
git add -A
git commit -m "docs: update memory with P0 sidebar UX implementation details"
```
