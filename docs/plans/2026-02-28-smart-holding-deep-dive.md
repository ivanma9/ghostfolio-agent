# Smart Holding Deep Dive — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Enhance `holding_detail` with computed intelligence signals (implied upside, sentiment score, analyst signal, earnings proximity) and build a frontend `HoldingDetailCard` that visualizes the deep dive.

**Architecture:** Add a `_format_smart_summary()` function to `holding_detail.py` that computes signals from enrichment data. The frontend gets a new `parseHoldingDetail()` parser and `HoldingDetailCard` component in `RichCard.tsx`. No new tools, no new API calls — just smarter presentation of existing data.

**Tech Stack:** Python (backend computed signals), React + Tailwind (frontend card), recharts (price target range vis)

---

### Task 1: Backend — Smart Summary computed signals

**Files:**
- Modify: `src/ghostfolio_agent/tools/holding_detail.py`
- Test: `tests/unit/test_holding_detail.py`

**Step 1: Write failing tests for smart summary signals**

Add a new test class `TestSmartSummary` to `tests/unit/test_holding_detail.py`:

```python
class TestSmartSummary:
    @pytest.mark.asyncio
    async def test_implied_upside_displayed(
        self, ghostfolio_client, finnhub_client, alpha_vantage_client, fmp_client
    ):
        """Implied upside is computed from consensus target vs market price."""
        tool = create_holding_detail_tool(
            ghostfolio_client,
            finnhub=finnhub_client,
            alpha_vantage=alpha_vantage_client,
            fmp=fmp_client,
        )
        result = await tool.ainvoke({"symbol": "AAPL"})
        # Market price = 195.50, consensus = 220.50 → upside = +12.8%
        assert "Smart Summary" in result
        assert "Implied Upside" in result
        assert "+12.8%" in result

    @pytest.mark.asyncio
    async def test_analyst_signal_strong_buy(
        self, ghostfolio_client, finnhub_client, alpha_vantage_client, fmp_client
    ):
        """Analyst signal summarizes the buy/hold/sell distribution."""
        tool = create_holding_detail_tool(
            ghostfolio_client,
            finnhub=finnhub_client,
            alpha_vantage=alpha_vantage_client,
            fmp=fmp_client,
        )
        result = await tool.ainvoke({"symbol": "AAPL"})
        # 12 strong buy + 18 buy = 30 bullish out of 37 total
        assert "Analyst Signal" in result
        assert "Strong Buy" in result
        assert "30 of 37" in result

    @pytest.mark.asyncio
    async def test_sentiment_score_bullish(
        self, ghostfolio_client, finnhub_client, alpha_vantage_client, fmp_client
    ):
        """Sentiment aggregation from news articles."""
        tool = create_holding_detail_tool(
            ghostfolio_client,
            finnhub=finnhub_client,
            alpha_vantage=alpha_vantage_client,
            fmp=fmp_client,
        )
        result = await tool.ainvoke({"symbol": "AAPL"})
        # Single article is Bullish → overall Bullish
        assert "Sentiment" in result
        assert "Bullish" in result
        assert "1 of 1" in result

    @pytest.mark.asyncio
    async def test_earnings_proximity_flag(
        self, ghostfolio_client, finnhub_client, alpha_vantage_client, fmp_client
    ):
        """Earnings within 14 days triggers proximity alert."""
        # Override earnings to be within 14 days from a fixed reference
        from datetime import date, timedelta
        near_date = (date.today() + timedelta(days=8)).isoformat()
        finnhub_client.get_earnings_calendar = AsyncMock(
            return_value=[{"date": near_date, "epsEstimate": 2.35, "epsActual": None, "symbol": "AAPL"}]
        )
        tool = create_holding_detail_tool(
            ghostfolio_client,
            finnhub=finnhub_client,
            alpha_vantage=alpha_vantage_client,
            fmp=fmp_client,
        )
        result = await tool.ainvoke({"symbol": "AAPL"})
        assert "Earnings Alert" in result
        assert "8 days" in result

    @pytest.mark.asyncio
    async def test_no_earnings_proximity_when_far(
        self, ghostfolio_client, finnhub_client, alpha_vantage_client, fmp_client
    ):
        """Earnings more than 14 days away — no proximity alert."""
        from datetime import date, timedelta
        far_date = (date.today() + timedelta(days=45)).isoformat()
        finnhub_client.get_earnings_calendar = AsyncMock(
            return_value=[{"date": far_date, "epsEstimate": 2.35, "epsActual": None, "symbol": "AAPL"}]
        )
        tool = create_holding_detail_tool(
            ghostfolio_client,
            finnhub=finnhub_client,
            alpha_vantage=alpha_vantage_client,
            fmp=fmp_client,
        )
        result = await tool.ainvoke({"symbol": "AAPL"})
        assert "Earnings Alert" not in result

    @pytest.mark.asyncio
    async def test_implied_downside_when_target_below_price(self, ghostfolio_client, fmp_client):
        """Consensus target below market price shows downside."""
        fmp_client.get_price_target_consensus = AsyncMock(
            return_value=[{"targetConsensus": 170.0, "targetMedian": 175.0, "targetHigh": 200.0, "targetLow": 150.0}]
        )
        tool = create_holding_detail_tool(ghostfolio_client, fmp=fmp_client)
        result = await tool.ainvoke({"symbol": "AAPL"})
        # Market price 195.50, consensus 170.0 → downside -13.0%
        assert "Implied Downside" in result
        assert "-13.0%" in result

    @pytest.mark.asyncio
    async def test_smart_summary_absent_without_enrichment(self, ghostfolio_client):
        """No 3rd party clients → no smart summary section."""
        tool = create_holding_detail_tool(ghostfolio_client)
        result = await tool.ainvoke({"symbol": "AAPL"})
        assert "Smart Summary" not in result

    @pytest.mark.asyncio
    async def test_smart_summary_partial_data(self, ghostfolio_client, fmp_client):
        """Only FMP available — shows implied upside but not analyst signal or sentiment."""
        tool = create_holding_detail_tool(ghostfolio_client, fmp=fmp_client)
        result = await tool.ainvoke({"symbol": "AAPL"})
        assert "Implied Upside" in result or "Implied Downside" in result
        assert "Analyst Signal" not in result
        assert "Earnings Alert" not in result
```

**Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/unit/test_holding_detail.py::TestSmartSummary -v`
Expected: All 8 tests FAIL (no "Smart Summary" in current output)

**Step 3: Implement `_format_smart_summary()` in holding_detail.py**

Add this function and wire it into the tool. Insert after the existing `_format_price_targets` function (around line 90):

```python
from datetime import date, timedelta


def _format_smart_summary(
    market_price: float,
    enrichment: dict,
) -> list[str]:
    """Compute intelligence signals from enrichment data."""
    signals: list[str] = []

    # 1. Implied upside/downside from price target consensus
    pt_consensus = enrichment.get("pt_consensus")
    if pt_consensus:
        consensus_price = pt_consensus[0].get("targetConsensus", 0)
        if consensus_price and market_price:
            pct = ((consensus_price - market_price) / market_price) * 100
            if pct >= 0:
                signals.append(f"  Implied Upside: +{pct:.1f}% (target ${consensus_price:,.2f})")
            else:
                signals.append(f"  Implied Downside: {pct:.1f}% (target ${consensus_price:,.2f})")

    # 2. Analyst signal from recommendation counts
    analyst = enrichment.get("analyst")
    if analyst:
        entry = analyst[0]
        strong_buy = entry.get("strongBuy", 0)
        buy = entry.get("buy", 0)
        hold = entry.get("hold", 0)
        sell = entry.get("sell", 0)
        strong_sell = entry.get("strongSell", 0)
        total = strong_buy + buy + hold + sell + strong_sell
        bullish = strong_buy + buy
        bearish = sell + strong_sell
        if total > 0:
            if bullish / total >= 0.7:
                label = "Strong Buy"
            elif bullish / total >= 0.5:
                label = "Buy"
            elif bearish / total >= 0.5:
                label = "Sell"
            else:
                label = "Hold"
            signals.append(f"  Analyst Signal: {label} ({bullish} of {total} analysts bullish)")

    # 3. Sentiment aggregation from news
    news = enrichment.get("news")
    if news:
        bullish_labels = {"Bullish", "Somewhat_Bullish", "Somewhat-Bullish"}
        bearish_labels = {"Bearish", "Somewhat_Bearish", "Somewhat-Bearish"}
        bullish_count = sum(1 for a in news if a.get("overall_sentiment_label") in bullish_labels)
        bearish_count = sum(1 for a in news if a.get("overall_sentiment_label") in bearish_labels)
        total_articles = len(news)
        if bullish_count > bearish_count:
            signals.append(f"  Sentiment: Bullish ({bullish_count} of {total_articles} articles positive)")
        elif bearish_count > bullish_count:
            signals.append(f"  Sentiment: Bearish ({bearish_count} of {total_articles} articles negative)")
        else:
            signals.append(f"  Sentiment: Neutral ({total_articles} articles)")

    # 4. Earnings proximity flag (within 14 days)
    earnings = enrichment.get("earnings")
    if earnings:
        today = date.today()
        for entry in earnings:
            earn_date_str = entry.get("date")
            if not earn_date_str:
                continue
            try:
                earn_date = date.fromisoformat(earn_date_str)
                days_until = (earn_date - today).days
                if 0 <= days_until <= 14:
                    signals.append(f"  Earnings Alert: Reporting in {days_until} days ({earn_date_str})")
                    break
            except ValueError:
                continue

    if not signals:
        return []

    return ["", "Smart Summary:"] + signals
```

Then in the main tool function, after the `enrichment` dict is built (around line 178), add:

```python
        # --- Smart Summary (computed signals) ---
        lines.extend(_format_smart_summary(market_price, enrichment))
```

This line goes after the existing `lines.extend(_format_price_targets(...))` call and before the `return "\n".join(lines)`.

**Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/unit/test_holding_detail.py -v`
Expected: All tests pass (existing + new)

**Step 5: Commit**

```bash
git add src/ghostfolio_agent/tools/holding_detail.py tests/unit/test_holding_detail.py
git commit -m "feat: add Smart Summary computed signals to holding_detail"
```

---

### Task 2: Frontend — HoldingDetailData type

**Files:**
- Modify: `frontend/src/types/index.ts`

**Step 1: Add HoldingDetailData interface**

Append to the end of `frontend/src/types/index.ts`:

```typescript
// Holding Detail (Smart Deep Dive)
export interface HoldingDetailData {
  name: string
  symbol: string
  quantity: number
  marketPrice: number
  currency: string
  avgCost: number
  totalInvested: number
  currentValue: number
  unrealizedPnl: number
  unrealizedPnlPercent: number
  dividends: number | null
  firstBuy: string
  transactionCount: number
  // Enrichment
  earnings: Array<{ date: string; epsEstimate: string; epsActual: string }> | null
  analystCounts: { strongBuy: number; buy: number; hold: number; sell: number; strongSell: number; period: string } | null
  news: Array<{ sentiment: string; title: string; source: string }> | null
  priceTargets: { consensus: number; median: number; high: number; low: number } | null
  // Smart Summary signals
  impliedMove: { direction: 'upside' | 'downside'; percent: number; target: number } | null
  analystSignal: { label: string; bullish: number; total: number } | null
  sentiment: { label: 'Bullish' | 'Bearish' | 'Neutral'; count: number; total: number } | null
  earningsAlert: { daysUntil: number; date: string } | null
}
```

**Step 2: Commit**

```bash
git add frontend/src/types/index.ts
git commit -m "feat: add HoldingDetailData type for smart deep dive card"
```

---

### Task 3: Frontend — parseHoldingDetail parser

**Files:**
- Modify: `frontend/src/components/Chat/RichCard.tsx`

**Step 1: Add parser function**

Add `HoldingDetailData` to the import on line 2, then add the parser after the existing `parsePaperTrade` function (around line 254):

```typescript
export function parseHoldingDetail(text: string): HoldingDetailData | null {
  // Must have the "Holding Detail:" header
  const headerMatch = text.match(/Holding Detail:\s*(.+?)\s*\((\w+)\)/)
  if (!headerMatch) return null

  const name = headerMatch[1]
  const symbol = headerMatch[2]

  const num = (pattern: RegExp): number => {
    const m = text.match(pattern)
    return m ? parseFloat(m[1].replace(/,/g, '')) : 0
  }

  const quantity = num(/Quantity:\s*([\d,.]+)/)
  const marketPrice = num(/Market Price:\s*\$([\d,.]+)/)
  const currency = text.match(/Market Price:\s*\$[\d,.]+\s+(\w+)/)?.[1] ?? 'USD'
  const avgCost = num(/Average Cost:\s*\$([\d,.]+)/)
  const totalInvested = num(/Total Invested:\s*\$([\d,.]+)/)
  const currentValue = num(/Current Value:\s*\$([\d,.]+)/)
  const unrealizedPnl = num(/Unrealized P&L:\s*\$([-\d,.]+)/)
  const pnlPctMatch = text.match(/Unrealized P&L:.*?\(([-+\d.]+)%\)/)
  const unrealizedPnlPercent = pnlPctMatch ? parseFloat(pnlPctMatch[1]) : 0
  const dividendsMatch = text.match(/Dividends:\s*\$([\d,.]+)/)
  const dividends = dividendsMatch ? parseFloat(dividendsMatch[1].replace(/,/g, '')) : null
  const firstBuy = text.match(/First Buy:\s*(\S+)/)?.[1] ?? ''
  const transactionCount = num(/Transactions:\s*(\d+)/)

  // Earnings
  let earnings: HoldingDetailData['earnings'] = null
  const earningsSection = text.match(/Upcoming Earnings:\n([\s\S]*?)(?=\n\n|\nAnalyst|\nNews|\nPrice Targets|\nSmart Summary|$)/)
  if (earningsSection) {
    const lines = earningsSection[1].trim().split('\n')
    earnings = lines.map(line => {
      const parts = line.trim().match(/(\S+)\s+EPS Est:\s*(\S+)\s+EPS Actual:\s*(\S+)/)
      return parts ? { date: parts[1], epsEstimate: parts[2], epsActual: parts[3] } : null
    }).filter((e): e is NonNullable<typeof e> => e !== null)
  }

  // Analyst
  let analystCounts: HoldingDetailData['analystCounts'] = null
  const analystMatch = text.match(/Analyst Consensus \(([^)]+)\):\n\s*Strong Buy:\s*(\d+)\s+Buy:\s*(\d+)\s+Hold:\s*(\d+)\s+Sell:\s*(\d+)\s+Strong Sell:\s*(\d+)/)
  if (analystMatch) {
    analystCounts = {
      period: analystMatch[1],
      strongBuy: parseInt(analystMatch[2]),
      buy: parseInt(analystMatch[3]),
      hold: parseInt(analystMatch[4]),
      sell: parseInt(analystMatch[5]),
      strongSell: parseInt(analystMatch[6]),
    }
  }

  // News
  let news: HoldingDetailData['news'] = null
  const newsSection = text.match(/News Sentiment:\n([\s\S]*?)(?=\n\n|\nPrice Targets|\nSmart Summary|$)/)
  if (newsSection) {
    const lines = newsSection[1].trim().split('\n')
    news = lines.map(line => {
      const parts = line.trim().match(/\[([^\]]+)\]\s*(.+?)\s+\(([^)]+)\)/)
      return parts ? { sentiment: parts[1], title: parts[2], source: parts[3] } : null
    }).filter((e): e is NonNullable<typeof e> => e !== null)
  }

  // Price targets
  let priceTargets: HoldingDetailData['priceTargets'] = null
  const ptMatch = text.match(/Consensus:\s*\$([\d,.]+)\s+Median:\s*\$([\d,.]+)\s+High:\s*\$([\d,.]+)\s+Low:\s*\$([\d,.]+)/)
  if (ptMatch) {
    priceTargets = {
      consensus: parseFloat(ptMatch[1].replace(/,/g, '')),
      median: parseFloat(ptMatch[2].replace(/,/g, '')),
      high: parseFloat(ptMatch[3].replace(/,/g, '')),
      low: parseFloat(ptMatch[4].replace(/,/g, '')),
    }
  }

  // Smart Summary signals
  let impliedMove: HoldingDetailData['impliedMove'] = null
  const upsideMatch = text.match(/Implied Upside:\s*\+([\d.]+)%\s*\(target \$([\d,.]+)\)/)
  const downsideMatch = text.match(/Implied Downside:\s*([-\d.]+)%\s*\(target \$([\d,.]+)\)/)
  if (upsideMatch) {
    impliedMove = { direction: 'upside', percent: parseFloat(upsideMatch[1]), target: parseFloat(upsideMatch[2].replace(/,/g, '')) }
  } else if (downsideMatch) {
    impliedMove = { direction: 'downside', percent: parseFloat(downsideMatch[1]), target: parseFloat(downsideMatch[2].replace(/,/g, '')) }
  }

  let analystSignal: HoldingDetailData['analystSignal'] = null
  const sigMatch = text.match(/Analyst Signal:\s*(\w[\w ]*?)\s*\((\d+) of (\d+) analysts bullish\)/)
  if (sigMatch) {
    analystSignal = { label: sigMatch[1], bullish: parseInt(sigMatch[2]), total: parseInt(sigMatch[3]) }
  }

  let sentiment: HoldingDetailData['sentiment'] = null
  const sentMatch = text.match(/Sentiment:\s*(Bullish|Bearish|Neutral)\s*\((\d+) of (\d+) articles/)
  if (sentMatch) {
    sentiment = { label: sentMatch[1] as 'Bullish' | 'Bearish' | 'Neutral', count: parseInt(sentMatch[2]), total: parseInt(sentMatch[3]) }
  } else {
    const neutralMatch = text.match(/Sentiment:\s*Neutral\s*\((\d+) articles\)/)
    if (neutralMatch) {
      sentiment = { label: 'Neutral', count: 0, total: parseInt(neutralMatch[1]) }
    }
  }

  let earningsAlert: HoldingDetailData['earningsAlert'] = null
  const alertMatch = text.match(/Earnings Alert:\s*Reporting in (\d+) days\s*\((\S+)\)/)
  if (alertMatch) {
    earningsAlert = { daysUntil: parseInt(alertMatch[1]), date: alertMatch[2] }
  }

  return {
    name, symbol, quantity, marketPrice, currency, avgCost, totalInvested, currentValue,
    unrealizedPnl, unrealizedPnlPercent, dividends, firstBuy, transactionCount,
    earnings, analystCounts, news, priceTargets,
    impliedMove, analystSignal, sentiment, earningsAlert,
  }
}
```

**Step 2: Commit**

```bash
git add frontend/src/components/Chat/RichCard.tsx
git commit -m "feat: add parseHoldingDetail parser for smart deep dive card"
```

---

### Task 4: Frontend — HoldingDetailCard component

**Files:**
- Modify: `frontend/src/components/Chat/RichCard.tsx`

**Step 1: Add the HoldingDetailCard component**

Insert before the main `RichCard` export (around line 618). This goes after `PaperTradeCard`:

```tsx
function HoldingDetailCard({ data }: { data: HoldingDetailData }) {
  const pnlColor = data.unrealizedPnl >= 0 ? 'text-emerald-400' : 'text-red-400'
  const pnlSign = data.unrealizedPnl >= 0 ? '+' : ''

  return (
    <div className="mt-3 rounded-xl border border-white/10 bg-white/5 overflow-hidden">
      {/* Header */}
      <div className="px-5 py-4 border-b border-white/10 bg-gradient-to-r from-indigo-500/10 to-violet-500/10">
        <div className="flex items-center justify-between">
          <div>
            <h3 className="text-lg font-semibold text-white">{data.name}</h3>
            <span className="text-sm text-white/50">{data.symbol} · {data.currency}</span>
          </div>
          <div className="text-right">
            <div className="text-lg font-semibold text-white">${data.currentValue.toLocaleString(undefined, { minimumFractionDigits: 2 })}</div>
            <div className={`text-sm font-medium ${pnlColor}`}>
              {pnlSign}${Math.abs(data.unrealizedPnl).toLocaleString(undefined, { minimumFractionDigits: 2 })} ({pnlSign}{data.unrealizedPnlPercent.toFixed(1)}%)
            </div>
          </div>
        </div>
      </div>

      {/* Smart Summary Badges */}
      {(data.impliedMove || data.analystSignal || data.sentiment || data.earningsAlert) && (
        <div className="px-5 py-3 border-b border-white/10 flex flex-wrap gap-2">
          {data.impliedMove && (
            <span className={`inline-flex items-center px-2.5 py-1 rounded-full text-xs font-medium ${
              data.impliedMove.direction === 'upside'
                ? 'bg-emerald-500/20 text-emerald-400'
                : 'bg-red-500/20 text-red-400'
            }`}>
              {data.impliedMove.direction === 'upside' ? '↑' : '↓'}{' '}
              {data.impliedMove.direction === 'upside' ? '+' : ''}{data.impliedMove.percent.toFixed(1)}% implied
            </span>
          )}
          {data.analystSignal && (
            <span className={`inline-flex items-center px-2.5 py-1 rounded-full text-xs font-medium ${
              data.analystSignal.label === 'Strong Buy' || data.analystSignal.label === 'Buy'
                ? 'bg-emerald-500/20 text-emerald-400'
                : data.analystSignal.label === 'Sell'
                  ? 'bg-red-500/20 text-red-400'
                  : 'bg-yellow-500/20 text-yellow-400'
            }`}>
              {data.analystSignal.label} ({data.analystSignal.bullish}/{data.analystSignal.total})
            </span>
          )}
          {data.sentiment && (
            <span className={`inline-flex items-center px-2.5 py-1 rounded-full text-xs font-medium ${
              data.sentiment.label === 'Bullish'
                ? 'bg-emerald-500/20 text-emerald-400'
                : data.sentiment.label === 'Bearish'
                  ? 'bg-red-500/20 text-red-400'
                  : 'bg-gray-500/20 text-gray-400'
            }`}>
              {data.sentiment.label}
            </span>
          )}
          {data.earningsAlert && (
            <span className="inline-flex items-center px-2.5 py-1 rounded-full text-xs font-medium bg-orange-500/20 text-orange-400">
              Earnings in {data.earningsAlert.daysUntil}d
            </span>
          )}
        </div>
      )}

      {/* Position Details Grid */}
      <div className="px-5 py-3 grid grid-cols-2 gap-x-6 gap-y-2 text-sm border-b border-white/10">
        <div className="flex justify-between">
          <span className="text-white/50">Shares</span>
          <span className="text-white">{data.quantity}</span>
        </div>
        <div className="flex justify-between">
          <span className="text-white/50">Avg Cost</span>
          <span className="text-white">${data.avgCost.toLocaleString(undefined, { minimumFractionDigits: 2 })}</span>
        </div>
        <div className="flex justify-between">
          <span className="text-white/50">Market Price</span>
          <span className="text-white">${data.marketPrice.toLocaleString(undefined, { minimumFractionDigits: 2 })}</span>
        </div>
        <div className="flex justify-between">
          <span className="text-white/50">Invested</span>
          <span className="text-white">${data.totalInvested.toLocaleString(undefined, { minimumFractionDigits: 2 })}</span>
        </div>
        {data.dividends !== null && (
          <div className="flex justify-between">
            <span className="text-white/50">Dividends</span>
            <span className="text-emerald-400">${data.dividends.toLocaleString(undefined, { minimumFractionDigits: 2 })}</span>
          </div>
        )}
        <div className="flex justify-between">
          <span className="text-white/50">First Buy</span>
          <span className="text-white">{data.firstBuy}</span>
        </div>
      </div>

      {/* Price Target Range */}
      {data.priceTargets && (
        <div className="px-5 py-3 border-b border-white/10">
          <div className="text-xs text-white/50 mb-2">Price Target Range</div>
          <div className="relative h-6 bg-white/5 rounded-full overflow-hidden">
            {(() => {
              const low = data.priceTargets!.low
              const high = data.priceTargets!.high
              const range = high - low
              if (range <= 0) return null
              const consensusPos = ((data.priceTargets!.consensus - low) / range) * 100
              const pricePos = ((data.marketPrice - low) / range) * 100
              const clamp = (v: number) => Math.max(2, Math.min(98, v))
              return (
                <>
                  <div className="absolute top-0 bottom-0 bg-indigo-500/20 rounded-full" style={{ left: '0%', right: '0%' }} />
                  <div className="absolute top-1 bottom-1 w-0.5 bg-indigo-400" style={{ left: `${clamp(consensusPos)}%` }} title={`Target: $${data.priceTargets!.consensus}`} />
                  <div className="absolute top-0 bottom-0 w-1 bg-white rounded-full" style={{ left: `${clamp(pricePos)}%` }} title={`Current: $${data.marketPrice}`} />
                  <div className="absolute -bottom-4 left-0 text-[10px] text-white/40">${low}</div>
                  <div className="absolute -bottom-4 right-0 text-[10px] text-white/40">${high}</div>
                </>
              )
            })()}
          </div>
          <div className="flex justify-between mt-5 text-[10px] text-white/40">
            <span>Low ${data.priceTargets.low}</span>
            <span>Consensus ${data.priceTargets.consensus}</span>
            <span>High ${data.priceTargets.high}</span>
          </div>
        </div>
      )}

      {/* Expandable: News */}
      {data.news && data.news.length > 0 && (
        <details className="border-b border-white/10">
          <summary className="px-5 py-2 text-sm text-white/60 cursor-pointer hover:text-white/80">
            News ({data.news.length})
          </summary>
          <div className="px-5 pb-3 space-y-1">
            {data.news.map((item, i) => (
              <div key={i} className="flex items-start gap-2 text-xs">
                <span className={`shrink-0 px-1.5 py-0.5 rounded text-[10px] font-medium ${
                  item.sentiment.includes('Bullish') ? 'bg-emerald-500/20 text-emerald-400'
                    : item.sentiment.includes('Bearish') ? 'bg-red-500/20 text-red-400'
                    : 'bg-gray-500/20 text-gray-400'
                }`}>{item.sentiment.replace('Somewhat_', '').replace('Somewhat-', '')}</span>
                <span className="text-white/70">{item.title}</span>
                <span className="text-white/30 shrink-0">{item.source}</span>
              </div>
            ))}
          </div>
        </details>
      )}

      {/* Expandable: Analyst Breakdown */}
      {data.analystCounts && (
        <details className="border-b border-white/10">
          <summary className="px-5 py-2 text-sm text-white/60 cursor-pointer hover:text-white/80">
            Analyst Breakdown ({data.analystCounts.period})
          </summary>
          <div className="px-5 pb-3 space-y-1.5">
            {[
              { label: 'Strong Buy', count: data.analystCounts.strongBuy, color: 'bg-emerald-500' },
              { label: 'Buy', count: data.analystCounts.buy, color: 'bg-emerald-400' },
              { label: 'Hold', count: data.analystCounts.hold, color: 'bg-yellow-400' },
              { label: 'Sell', count: data.analystCounts.sell, color: 'bg-red-400' },
              { label: 'Strong Sell', count: data.analystCounts.strongSell, color: 'bg-red-500' },
            ].map(({ label, count, color }) => {
              const total = data.analystCounts!.strongBuy + data.analystCounts!.buy + data.analystCounts!.hold + data.analystCounts!.sell + data.analystCounts!.strongSell
              const pct = total > 0 ? (count / total) * 100 : 0
              return (
                <div key={label} className="flex items-center gap-2 text-xs">
                  <span className="w-20 text-white/50">{label}</span>
                  <div className="flex-1 h-2 bg-white/5 rounded-full overflow-hidden">
                    <div className={`h-full ${color} rounded-full`} style={{ width: `${pct}%` }} />
                  </div>
                  <span className="w-6 text-right text-white/60">{count}</span>
                </div>
              )
            })}
          </div>
        </details>
      )}

      {/* Expandable: Earnings */}
      {data.earnings && data.earnings.length > 0 && (
        <details>
          <summary className="px-5 py-2 text-sm text-white/60 cursor-pointer hover:text-white/80">
            Earnings ({data.earnings.length})
          </summary>
          <div className="px-5 pb-3 space-y-1">
            {data.earnings.map((e, i) => (
              <div key={i} className="flex gap-4 text-xs text-white/70">
                <span>{e.date}</span>
                <span>Est: {e.epsEstimate}</span>
                <span>Actual: {e.epsActual}</span>
              </div>
            ))}
          </div>
        </details>
      )}
    </div>
  )
}
```

**Step 2: Commit**

```bash
git add frontend/src/components/Chat/RichCard.tsx
git commit -m "feat: add HoldingDetailCard component for smart deep dive"
```

---

### Task 5: Frontend — Wire card + strip raw data

**Files:**
- Modify: `frontend/src/components/Chat/RichCard.tsx` (main export, around line 623)
- Modify: `frontend/src/components/Chat/MessageBubble.tsx` (stripRawData function)

**Step 1: Wire HoldingDetailCard in RichCard main export**

In the `RichCard` default export function, add a holding_detail check BEFORE the `paper_trade` check (around line 652). Insert after the `risk_analysis` block:

```tsx
  if (toolCalls.includes('holding_detail')) {
    const data = parseHoldingDetail(content)
    if (data) return <HoldingDetailCard data={data} />
  }
```

**Step 2: Add raw data stripping for holding_detail in MessageBubble.tsx**

In the `stripRawData` function in `MessageBubble.tsx`, add a new block after the `paper_trade` block (around line 49):

```typescript
    // Strip raw holding detail data lines when RichCard renders them
    if (toolCalls.includes('holding_detail')) {
      // Strip the structured data lines (key: value format)
      if (/^\s*(Quantity|Market Price|Average Cost|Total Invested|Current Value|Unrealized P&L|Dividends|First Buy|Transactions):/i.test(trimmed)) return false
      // Strip enrichment section data lines
      if (/^\s*(Strong Buy:|Consensus:|Last Month:|Last Quarter:)/i.test(trimmed)) return false
      if (/^\s*\[(Bullish|Bearish|Neutral|Somewhat)/i.test(trimmed)) return false
      if (/^\s*\d{4}-\d{2}-\d{2}\s+EPS/i.test(trimmed)) return false
      // Strip Smart Summary signal lines
      if (/^\s*(Implied Upside|Implied Downside|Analyst Signal|Sentiment:|Earnings Alert):/i.test(trimmed)) return false
    }
```

**Step 3: Commit**

```bash
git add frontend/src/components/Chat/RichCard.tsx frontend/src/components/Chat/MessageBubble.tsx
git commit -m "feat: wire HoldingDetailCard to tool detection and strip raw data"
```

---

### Task 6: Run full test suite + manual verification

**Step 1: Run backend tests**

Run: `uv run pytest tests/unit/ -v`
Expected: All tests pass

**Step 2: Run frontend build check**

Run: `cd frontend && npm run build`
Expected: Build succeeds with no TypeScript errors

**Step 3: Commit any fixes if needed**

---

### Task 7: Final commit + docs update

**Step 1: Update MEMORY.md**

Add a section about the Smart Holding Deep Dive feature noting what was built.

**Step 2: Commit docs**

```bash
git add docs/plans/2026-02-28-smart-holding-deep-dive.md
git commit -m "docs: add Smart Holding Deep Dive implementation plan"
```
