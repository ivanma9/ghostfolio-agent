import { AreaChart, Area, XAxis, YAxis, Tooltip, ResponsiveContainer } from 'recharts'
import type { Holding, Transaction, SymbolInfo, PerformanceData, RiskData, PaperPortfolio, PaperTradeResult } from '../../types'

// ── Parsers ──────────────────────────────────────────────────────────────────

export function parseHoldings(text: string): Holding[] {
  const holdings: Holding[] = []

  // Match lines like: AAPL Apple Inc 10 150.00 1500.00 25.5% USD
  // or table rows with symbol, qty, price, value, allocation
  const lineRe =
    /\b([A-Z]{1,5})\b[^\n]*?(\d+(?:\.\d+)?)\s+(?:shares?|units?)?\s*[@at]?\s*\$?([\d,]+(?:\.\d{2})?)[^\n]*?\$?([\d,]+(?:\.\d{2}))[^\n]*?([\d.]+)\s*%/gi
  let m: RegExpExecArray | null
  while ((m = lineRe.exec(text)) !== null) {
    const symbol = m[1].toUpperCase()
    const quantity = parseFloat(m[2])
    const price = parseFloat(m[3].replace(/,/g, ''))
    const value = parseFloat(m[4].replace(/,/g, ''))
    const allocation = parseFloat(m[5])
    holdings.push({ symbol, name: symbol, quantity, price, value, allocation, currency: 'USD' })
  }

  // Fallback: look for markdown table rows  | AAPL | ... | ... | ... | ... |
  if (holdings.length === 0) {
    const tableRe = /\|\s*([A-Z]{1,5})\s*\|[^|]*\|\s*([\d.]+)\s*\|\s*\$?([\d,]+(?:\.\d{2})?)\s*\|\s*\$?([\d,]+(?:\.\d{2})?)\s*\|\s*([\d.]+)\s*%/gi
    while ((m = tableRe.exec(text)) !== null) {
      holdings.push({
        symbol: m[1],
        name: m[1],
        quantity: parseFloat(m[2]),
        price: parseFloat(m[3].replace(/,/g, '')),
        value: parseFloat(m[4].replace(/,/g, '')),
        allocation: parseFloat(m[5]),
        currency: 'USD',
      })
    }
  }

  return holdings
}

export function parseTransactions(text: string): Transaction[] {
  const transactions: Transaction[] = []

  // Match: 2024-01-15 BUY AAPL 10 150.00
  const lineRe =
    /(\d{4}-\d{2}-\d{2}|\d{1,2}\/\d{1,2}\/\d{2,4})\s+(BUY|SELL|DIVIDEND)\s+([A-Z]{1,5})\s+([\d.]+)\s+@?\s*\$?([\d,]+(?:\.\d{2})?)/gi
  let m: RegExpExecArray | null
  while ((m = lineRe.exec(text)) !== null) {
    const qty = parseFloat(m[4])
    const price = parseFloat(m[5].replace(/,/g, ''))
    transactions.push({
      date: m[1],
      type: m[2].toUpperCase() as 'BUY' | 'SELL' | 'DIVIDEND',
      symbol: m[3].toUpperCase(),
      quantity: qty,
      price,
      fee: 0,
      total: qty * price,
    })
  }

  // Fallback: markdown table rows
  if (transactions.length === 0) {
    const tableRe =
      /\|\s*(\d{4}-\d{2}-\d{2}|\d{1,2}\/\d{1,2}\/\d{2,4})\s*\|\s*(BUY|SELL|DIVIDEND)\s*\|\s*([A-Z]{1,5})\s*\|\s*([\d.]+)\s*\|\s*\$?([\d,]+(?:\.\d{2})?)\s*\|/gi
    while ((m = tableRe.exec(text)) !== null) {
      const qty = parseFloat(m[4])
      const price = parseFloat(m[5].replace(/,/g, ''))
      transactions.push({
        date: m[1],
        type: m[2].toUpperCase() as 'BUY' | 'SELL' | 'DIVIDEND',
        symbol: m[3].toUpperCase(),
        quantity: qty,
        price,
        fee: 0,
        total: qty * price,
      })
    }
  }

  return transactions
}

export function parseSymbolInfo(text: string): SymbolInfo[] {
  const symbols: SymbolInfo[] = []

  // Look for patterns like: Symbol: AAPL, Name: Apple Inc, Asset Class: Equity
  const symbolRe = /(?:symbol|ticker)[:\s]+([A-Z]{1,5})/gi
  const nameRe = /(?:name|company)[:\s]+([^\n,]+)/i
  const assetRe = /(?:asset\s*class|type)[:\s]+([^\n,]+)/i
  const currencyRe = /(?:currency)[:\s]+([A-Z]{3})/i
  const sourceRe = /(?:data\s*source|source|exchange)[:\s]+([^\n,]+)/i

  let m: RegExpExecArray | null
  while ((m = symbolRe.exec(text)) !== null) {
    const symbol = m[1].toUpperCase()
    const nameMatch = nameRe.exec(text)
    const assetMatch = assetRe.exec(text)
    const currencyMatch = currencyRe.exec(text)
    const sourceMatch = sourceRe.exec(text)

    symbols.push({
      symbol,
      name: nameMatch ? nameMatch[1].trim() : symbol,
      assetClass: assetMatch ? assetMatch[1].trim() : 'Equity',
      currency: currencyMatch ? currencyMatch[1].trim() : 'USD',
      dataSource: sourceMatch ? sourceMatch[1].trim() : 'Unknown',
    })
  }

  return symbols
}

export function parsePerformance(text: string): PerformanceData | null {
  // Match period
  const periodMatch = text.match(/Period:\s*([^\n]+)/i)
  const period = periodMatch ? periodMatch[1].trim() : 'Unknown'

  // Match total return: "+$1,234.56 (+12.3%)" or "Net Performance: ..."
  let totalReturn = 0
  let totalReturnPercent = 0
  const returnMatch = text.match(/Total Return[:\s]+([+-]?\$?[\d,]+(?:\.\d{2})?)\s*\(([+-]?[\d.]+)%\)/i)
    ?? text.match(/Net Performance[:\s]+([+-]?\$?[\d,]+(?:\.\d{2})?)\s*\(([+-]?[\d.]+)%\)/i)
  if (returnMatch) {
    totalReturn = parseFloat(returnMatch[1].replace(/[$,]/g, ''))
    totalReturnPercent = parseFloat(returnMatch[2])
  }

  // Match current value
  let currentValue = 0
  const valueMatch = text.match(/Current Value[:\s]+\$?([\d,]+(?:\.\d{2})?)/i)
  if (valueMatch) {
    currentValue = parseFloat(valueMatch[1].replace(/,/g, ''))
  }

  // Match data points: lines like "2024-01-15: 10000.00" or "2024-01-15: $10,000.00"
  const dataPoints: Array<{ date: string; value: number }> = []
  const dpRe = /(\d{4}-\d{2}-\d{2}):\s*\$?([\d,]+(?:\.\d{2})?)/g
  let m: RegExpExecArray | null
  while ((m = dpRe.exec(text)) !== null) {
    dataPoints.push({ date: m[1], value: parseFloat(m[2].replace(/,/g, '')) })
  }

  if (dataPoints.length === 0) return null

  return { period, totalReturn, totalReturnPercent, currentValue, dataPoints }
}

export function parseRiskAnalysis(text: string): RiskData | null {
  // Concentration risk
  const topMatch = text.match(/Top holding[:\s]+([A-Z]{1,5})\s+at\s+([\d.]+)%/i)
  if (!topMatch) return null

  const topHolding = topMatch[1].toUpperCase()
  const topPercent = parseFloat(topMatch[2])
  const isHighRisk = /WARNING|High concentration/i.test(text)

  // Sector breakdown: lines like "- SectorName: XX.X%"
  const sectorBreakdown: Array<{ name: string; percent: number }> = []
  const sectorRe = /[-•]\s+([A-Za-z &]+):\s*([\d.]+)%/g
  // Find the sector section first
  const sectorSection = text.match(/sector[^\n]*\n([\s\S]*?)(?:\n\n|\ncurrency|\nCurrency|$)/i)
  if (sectorSection) {
    let sm: RegExpExecArray | null
    while ((sm = sectorRe.exec(sectorSection[1])) !== null) {
      sectorBreakdown.push({ name: sm[1].trim(), percent: parseFloat(sm[2]) })
    }
  }

  // Currency breakdown: lines like "- USD: XX.X%"
  const currencyBreakdown: Array<{ name: string; percent: number }> = []
  const currencySection = text.match(/currency[^\n]*\n([\s\S]*?)(?:\n\n|$)/i)
  if (currencySection) {
    const currRe = /[-•]\s+([A-Z]{3}):\s*([\d.]+)%/g
    let cm: RegExpExecArray | null
    while ((cm = currRe.exec(currencySection[1])) !== null) {
      currencyBreakdown.push({ name: cm[1].trim(), percent: parseFloat(cm[2]) })
    }
  }

  // Summary line
  const summaryMatch = text.match(/Summary[:\s]+([^\n]+)/i)
  const summary = summaryMatch ? summaryMatch[1].trim() : ''

  return {
    concentrationRisk: { topHolding, topPercent, isHighRisk },
    sectorBreakdown,
    currencyBreakdown,
    summary,
  }
}

export function parsePaperPortfolio(text: string): PaperPortfolio | null {
  // Match cash
  const cashMatch = text.match(/Cash[:\s]+\$?([\d,]+(?:\.\d{2})?)/i)
  if (!cashMatch) return null
  const cash = parseFloat(cashMatch[1].replace(/,/g, ''))

  // Match position lines: "- SYMBOL: X shares, avg cost $XX.XX, current $XX.XX, value $XX.XX, P&L: +$XX.XX (+X.X%)"
  const positions: Array<{
    symbol: string
    quantity: number
    avgCost: number
    currentPrice: number
    value: number
    pnl: number
    pnlPercent: number
  }> = []
  const posRe = /[-•]\s+([A-Z]{1,5}):\s*([\d.]+)\s+shares?,\s+avg\s+cost\s+\$?([\d,]+(?:\.\d{2})?),\s+current\s+\$?([\d,]+(?:\.\d{2})?),\s+value\s+\$?([\d,]+(?:\.\d{2})?),\s+P&L:\s+([+-]?\$?[\d,]+(?:\.\d{2})?)\s+\(([+-]?[\d.]+)%\)/gi
  let m: RegExpExecArray | null
  while ((m = posRe.exec(text)) !== null) {
    positions.push({
      symbol: m[1].toUpperCase(),
      quantity: parseFloat(m[2]),
      avgCost: parseFloat(m[3].replace(/,/g, '')),
      currentPrice: parseFloat(m[4].replace(/,/g, '')),
      value: parseFloat(m[5].replace(/,/g, '')),
      pnl: parseFloat(m[6].replace(/[$,]/g, '')),
      pnlPercent: parseFloat(m[7]),
    })
  }

  if (positions.length === 0 && cash === 0) return null

  // Total value
  const totalValueMatch = text.match(/Total Value[:\s]+\$?([\d,]+(?:\.\d{2})?)/i)
  const totalValue = totalValueMatch ? parseFloat(totalValueMatch[1].replace(/,/g, '')) : cash

  // Total P&L
  const totalPnlMatch = text.match(/Total P&L[:\s]+([+-]?\$?[\d,]+(?:\.\d{2})?)\s*\(([+-]?[\d.]+)%\)/i)
  const totalPnl = totalPnlMatch ? parseFloat(totalPnlMatch[1].replace(/[$,]/g, '')) : 0
  const totalPnlPercent = totalPnlMatch ? parseFloat(totalPnlMatch[2]) : 0

  return { cash, totalValue, totalPnl, totalPnlPercent, positions }
}

export function parsePaperTrade(text: string): PaperTradeResult | null {
  // Match "BUY X SYMBOL @ $XX.XX = $XX.XX" or "SELL X SYMBOL @ $XX.XX = $XX.XX"
  const tradeMatch = text.match(/(BUY|SELL)\s+([\d.]+)\s+([A-Z]{1,5})\s+@\s+\$?([\d,]+(?:\.\d{2})?)\s*=\s*\$?([\d,]+(?:\.\d{2})?)/i)
  if (!tradeMatch) return null

  const action = tradeMatch[1].toUpperCase() as 'BUY' | 'SELL'
  const quantity = parseFloat(tradeMatch[2])
  const symbol = tradeMatch[3].toUpperCase()
  const price = parseFloat(tradeMatch[4].replace(/,/g, ''))
  const total = parseFloat(tradeMatch[5].replace(/,/g, ''))

  // Match cash remaining
  const cashMatch = text.match(/Cash remaining[:\s]+\$?([\d,]+(?:\.\d{2})?)/i)
  const cashRemaining = cashMatch ? parseFloat(cashMatch[1].replace(/,/g, '')) : 0

  return { action, symbol, quantity, price, total, cashRemaining }
}

// ── Sub-components ────────────────────────────────────────────────────────────

function fmt(n: number, currency = 'USD') {
  return new Intl.NumberFormat('en-US', { style: 'currency', currency, minimumFractionDigits: 2 }).format(n)
}

function HoldingsCard({ holdings }: { holdings: Holding[] }) {
  if (holdings.length === 0) return null
  return (
    <div className="mt-3 rounded-xl border border-gray-200 shadow-sm overflow-hidden bg-white">
      <div className="px-4 py-2.5 bg-gray-50 border-b border-gray-200">
        <span className="text-xs font-semibold text-gray-500 uppercase tracking-wide">Portfolio Holdings</span>
      </div>
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="bg-gray-50/50">
              <th className="px-4 py-2 text-left text-xs font-semibold text-gray-400 uppercase tracking-wide">Symbol</th>
              <th className="px-4 py-2 text-right text-xs font-semibold text-gray-400 uppercase tracking-wide">Qty</th>
              <th className="px-4 py-2 text-right text-xs font-semibold text-gray-400 uppercase tracking-wide">Price</th>
              <th className="px-4 py-2 text-right text-xs font-semibold text-gray-400 uppercase tracking-wide">Value</th>
              <th className="px-4 py-2 text-right text-xs font-semibold text-gray-400 uppercase tracking-wide">Alloc%</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-100">
            {holdings.map((h) => (
              <tr key={h.symbol} className="hover:bg-gray-50/50 transition-colors">
                <td className="px-4 py-2.5">
                  <span className="font-bold text-gray-800">{h.symbol}</span>
                  {h.name !== h.symbol && (
                    <span className="ml-1.5 text-xs text-gray-400">{h.name}</span>
                  )}
                </td>
                <td className="px-4 py-2.5 text-right text-gray-600 tabular-nums">{h.quantity.toLocaleString()}</td>
                <td className="px-4 py-2.5 text-right text-gray-600 tabular-nums">{fmt(h.price, h.currency)}</td>
                <td className="px-4 py-2.5 text-right font-medium text-gray-800 tabular-nums">{fmt(h.value, h.currency)}</td>
                <td className="px-4 py-2.5 text-right tabular-nums">
                  <span className="inline-block bg-indigo-50 text-indigo-600 text-xs font-medium px-2 py-0.5 rounded-full">
                    {h.allocation.toFixed(1)}%
                  </span>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}

const typeBadge: Record<string, string> = {
  BUY: 'bg-emerald-100 text-emerald-700',
  SELL: 'bg-red-100 text-red-600',
  DIVIDEND: 'bg-blue-100 text-blue-600',
}

function TransactionsCard({ transactions }: { transactions: Transaction[] }) {
  if (transactions.length === 0) return null
  return (
    <div className="mt-3 rounded-xl border border-gray-200 shadow-sm overflow-hidden bg-white">
      <div className="px-4 py-2.5 bg-gray-50 border-b border-gray-200">
        <span className="text-xs font-semibold text-gray-500 uppercase tracking-wide">Transaction History</span>
      </div>
      <ul className="divide-y divide-gray-100">
        {transactions.map((tx, i) => (
          <li key={i} className="flex items-center justify-between px-4 py-3 hover:bg-gray-50/50 transition-colors">
            <div className="flex items-center gap-3">
              <span
                className={`text-xs font-semibold px-2 py-0.5 rounded-full ${typeBadge[tx.type] ?? 'bg-gray-100 text-gray-500'}`}
              >
                {tx.type}
              </span>
              <div>
                <span className="font-bold text-gray-800 text-sm">{tx.symbol}</span>
                <span className="ml-2 text-xs text-gray-400">{tx.date}</span>
              </div>
            </div>
            <div className="text-right">
              <p className="text-sm font-medium text-gray-800 tabular-nums">{fmt(tx.total)}</p>
              <p className="text-xs text-gray-400 tabular-nums">
                {tx.quantity} × {fmt(tx.price)}
              </p>
            </div>
          </li>
        ))}
      </ul>
    </div>
  )
}

function SymbolCard({ symbols }: { symbols: SymbolInfo[] }) {
  if (symbols.length === 0) return null
  return (
    <div className="mt-3 space-y-2">
      {symbols.map((s) => (
        <div key={s.symbol} className="rounded-xl border border-gray-200 shadow-sm bg-white px-4 py-3">
          <div className="flex items-start gap-3">
            <div className="w-10 h-10 rounded-lg bg-gradient-to-br from-indigo-500 to-violet-500 flex items-center justify-center flex-shrink-0">
              <span className="text-white text-xs font-bold">{s.symbol.slice(0, 2)}</span>
            </div>
            <div className="flex-1 min-w-0">
              <p className="font-bold text-gray-800 text-sm">{s.symbol}</p>
              <p className="text-xs text-gray-500 truncate">{s.name}</p>
              <div className="mt-1.5 flex flex-wrap gap-1.5">
                <span className="text-xs bg-gray-100 text-gray-500 px-2 py-0.5 rounded-full">{s.assetClass}</span>
                <span className="text-xs bg-gray-100 text-gray-500 px-2 py-0.5 rounded-full">{s.currency}</span>
                <span className="text-xs bg-indigo-50 text-indigo-500 px-2 py-0.5 rounded-full">{s.dataSource}</span>
              </div>
            </div>
          </div>
        </div>
      ))}
    </div>
  )
}

function PerformanceCard({ data }: { data: PerformanceData }) {
  const isPositive = data.totalReturn >= 0
  const color = isPositive ? '#10b981' : '#ef4444'
  const gradientId = isPositive ? 'perfGreenGradient' : 'perfRedGradient'

  return (
    <div className="mt-3 rounded-xl border border-gray-200 shadow-sm overflow-hidden bg-white">
      <div className="px-4 py-2.5 bg-gray-50 border-b border-gray-200 flex items-center justify-between">
        <span className="text-xs font-semibold text-gray-500 uppercase tracking-wide">Portfolio Performance</span>
        <span className="text-xs bg-indigo-50 text-indigo-600 font-medium px-2 py-0.5 rounded-full">{data.period}</span>
      </div>
      <div className="p-2">
        <ResponsiveContainer width="100%" height={200}>
          <AreaChart data={data.dataPoints} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
            <defs>
              <linearGradient id={gradientId} x1="0" y1="0" x2="0" y2="1">
                <stop offset="5%" stopColor={color} stopOpacity={0.25} />
                <stop offset="95%" stopColor={color} stopOpacity={0.02} />
              </linearGradient>
            </defs>
            <XAxis
              dataKey="date"
              tick={{ fontSize: 10, fill: '#9ca3af' }}
              tickLine={false}
              axisLine={false}
              tickFormatter={(v: string) => v.slice(5)}
            />
            <YAxis
              tick={{ fontSize: 10, fill: '#9ca3af' }}
              tickLine={false}
              axisLine={false}
              tickFormatter={(v: number) => `$${(v / 1000).toFixed(0)}k`}
              width={42}
            />
            <Tooltip
              contentStyle={{ fontSize: 11, borderRadius: 8, border: '1px solid #e5e7eb', boxShadow: '0 2px 8px rgba(0,0,0,0.08)' }}
              formatter={(value: unknown) => [fmt(Number(value)), 'Value']}
              labelFormatter={(label: unknown) => String(label)}
            />
            <Area
              type="monotone"
              dataKey="value"
              stroke={color}
              strokeWidth={2}
              fill={`url(#${gradientId})`}
              dot={false}
              activeDot={{ r: 4, fill: color }}
            />
          </AreaChart>
        </ResponsiveContainer>
      </div>
      <div className="px-4 py-3 border-t border-gray-100 flex items-center justify-between gap-4">
        <div className="text-center">
          <p className="text-xs text-gray-400 mb-0.5">Period</p>
          <p className="text-sm font-semibold text-gray-700">{data.period}</p>
        </div>
        <div className="text-center">
          <p className="text-xs text-gray-400 mb-0.5">Total Return</p>
          <p className={`text-sm font-bold tabular-nums ${isPositive ? 'text-emerald-600' : 'text-red-500'}`}>
            {isPositive ? '+' : ''}{fmt(data.totalReturn)} ({isPositive ? '+' : ''}{data.totalReturnPercent.toFixed(2)}%)
          </p>
        </div>
        <div className="text-center">
          <p className="text-xs text-gray-400 mb-0.5">Current Value</p>
          <p className="text-sm font-semibold text-gray-700 tabular-nums">{fmt(data.currentValue)}</p>
        </div>
      </div>
    </div>
  )
}

const SECTOR_COLORS = ['#6366f1', '#8b5cf6', '#06b6d4', '#10b981', '#f59e0b', '#ef4444', '#ec4899', '#64748b']

function RiskCard({ data }: { data: RiskData }) {
  const { concentrationRisk, sectorBreakdown, currencyBreakdown, summary } = data

  return (
    <div className="mt-3 rounded-xl border border-gray-200 shadow-sm overflow-hidden bg-white">
      <div className="px-4 py-2.5 bg-gray-50 border-b border-gray-200">
        <span className="text-xs font-semibold text-gray-500 uppercase tracking-wide">Risk Analysis</span>
      </div>

      <div className="p-4 space-y-4">
        {/* Concentration Risk */}
        <div>
          {concentrationRisk.isHighRisk && (
            <div className="mb-2 flex items-center gap-2 bg-amber-50 border border-amber-200 rounded-lg px-3 py-2">
              <span className="text-amber-500 text-base">⚠</span>
              <span className="text-xs font-medium text-amber-700">
                High concentration risk: {concentrationRisk.topHolding} at {concentrationRisk.topPercent.toFixed(1)}%
              </span>
            </div>
          )}
          {!concentrationRisk.isHighRisk && (
            <p className="text-xs text-gray-600 mb-2">
              Top holding: <span className="font-semibold text-gray-800">{concentrationRisk.topHolding}</span>{' '}
              at <span className="font-semibold">{concentrationRisk.topPercent.toFixed(1)}%</span>
            </p>
          )}
        </div>

        {/* Sector Breakdown */}
        {sectorBreakdown.length > 0 && (
          <div>
            <p className="text-xs font-semibold text-gray-500 uppercase tracking-wide mb-2">Sector Breakdown</p>
            <div className="space-y-1.5">
              {sectorBreakdown.map((s, i) => (
                <div key={s.name} className="flex items-center gap-2">
                  <span className="w-24 text-xs text-gray-600 truncate flex-shrink-0">{s.name}</span>
                  <div className="flex-1 h-2 bg-gray-100 rounded-full overflow-hidden">
                    <div
                      className="h-full rounded-full"
                      style={{ width: `${Math.min(s.percent, 100)}%`, backgroundColor: SECTOR_COLORS[i % SECTOR_COLORS.length] }}
                    />
                  </div>
                  <span className="w-10 text-xs text-gray-500 text-right tabular-nums flex-shrink-0">{s.percent.toFixed(1)}%</span>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Currency Breakdown */}
        {currencyBreakdown.length > 0 && (
          <div>
            <p className="text-xs font-semibold text-gray-500 uppercase tracking-wide mb-2">Currency Breakdown</p>
            <div className="flex flex-wrap gap-3">
              {currencyBreakdown.map((c, i) => (
                <div key={c.name} className="flex items-center gap-1.5">
                  <span
                    className="w-2.5 h-2.5 rounded-full flex-shrink-0"
                    style={{ backgroundColor: SECTOR_COLORS[i % SECTOR_COLORS.length] }}
                  />
                  <span className="text-xs text-gray-600">{c.name}</span>
                  <span className="text-xs font-medium text-gray-800 tabular-nums">{c.percent.toFixed(1)}%</span>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Summary */}
        {summary && (
          <p className="text-xs text-gray-500 italic border-t border-gray-100 pt-3">{summary}</p>
        )}
      </div>
    </div>
  )
}

function PaperPortfolioCard({ data }: { data: PaperPortfolio }) {
  const isPositive = data.totalPnl >= 0

  return (
    <div className="mt-3 rounded-xl border border-gray-200 shadow-sm overflow-hidden bg-white">
      <div className="px-4 py-2.5 bg-gray-50 border-b border-gray-200">
        <span className="text-xs font-semibold text-gray-500 uppercase tracking-wide">Paper Portfolio</span>
      </div>

      {data.positions.length > 0 && (
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="bg-gray-50/50">
                <th className="px-4 py-2 text-left text-xs font-semibold text-gray-400 uppercase tracking-wide">Symbol</th>
                <th className="px-4 py-2 text-right text-xs font-semibold text-gray-400 uppercase tracking-wide">Qty</th>
                <th className="px-4 py-2 text-right text-xs font-semibold text-gray-400 uppercase tracking-wide">Avg Cost</th>
                <th className="px-4 py-2 text-right text-xs font-semibold text-gray-400 uppercase tracking-wide">Current</th>
                <th className="px-4 py-2 text-right text-xs font-semibold text-gray-400 uppercase tracking-wide">Value</th>
                <th className="px-4 py-2 text-right text-xs font-semibold text-gray-400 uppercase tracking-wide">P&amp;L</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-100">
              {data.positions.map((pos) => {
                const posPositive = pos.pnl >= 0
                return (
                  <tr key={pos.symbol} className="hover:bg-gray-50/50 transition-colors">
                    <td className="px-4 py-2.5 font-bold text-gray-800">{pos.symbol}</td>
                    <td className="px-4 py-2.5 text-right text-gray-600 tabular-nums">{pos.quantity.toLocaleString()}</td>
                    <td className="px-4 py-2.5 text-right text-gray-600 tabular-nums">{fmt(pos.avgCost)}</td>
                    <td className="px-4 py-2.5 text-right text-gray-600 tabular-nums">{fmt(pos.currentPrice)}</td>
                    <td className="px-4 py-2.5 text-right font-medium text-gray-800 tabular-nums">{fmt(pos.value)}</td>
                    <td className={`px-4 py-2.5 text-right font-medium tabular-nums ${posPositive ? 'text-emerald-600' : 'text-red-500'}`}>
                      {posPositive ? '+' : ''}{fmt(pos.pnl)}
                      <span className="block text-xs font-normal">
                        ({posPositive ? '+' : ''}{pos.pnlPercent.toFixed(1)}%)
                      </span>
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      )}

      <div className="px-4 py-3 border-t border-gray-100 flex items-center justify-between">
        <span className="text-xs text-gray-500">
          Cash: <span className="font-semibold text-gray-700 tabular-nums">{fmt(data.cash)}</span>
        </span>
        <span className="text-xs text-gray-500">
          Total Value: <span className="font-semibold text-gray-700 tabular-nums">{fmt(data.totalValue)}</span>
        </span>
      </div>

      <div className={`px-4 py-2.5 border-t ${isPositive ? 'bg-emerald-50 border-emerald-100' : 'bg-red-50 border-red-100'} flex items-center justify-between`}>
        <span className="text-xs font-semibold text-gray-600">Total P&amp;L</span>
        <span className={`text-base font-bold tabular-nums ${isPositive ? 'text-emerald-600' : 'text-red-500'}`}>
          {isPositive ? '+' : ''}{fmt(data.totalPnl)}{' '}
          <span className="text-sm font-medium">({isPositive ? '+' : ''}{data.totalPnlPercent.toFixed(2)}%)</span>
        </span>
      </div>
    </div>
  )
}

function PaperTradeCard({ data }: { data: PaperTradeResult }) {
  const isBuy = data.action === 'BUY'

  return (
    <div className={`mt-3 rounded-xl border shadow-sm overflow-hidden bg-white flex ${isBuy ? 'border-emerald-200' : 'border-red-200'}`}>
      <div className={`w-1 flex-shrink-0 ${isBuy ? 'bg-emerald-400' : 'bg-red-400'}`} />
      <div className="flex-1 px-4 py-3">
        <div className="flex items-center gap-2 mb-2">
          <span className={`text-lg ${isBuy ? 'text-emerald-500' : 'text-red-500'}`}>
            {isBuy ? '✓' : '↓'}
          </span>
          <span className="text-sm font-bold text-gray-800">
            {isBuy ? 'Bought' : 'Sold'} {data.quantity} {data.symbol} at {fmt(data.price)}
          </span>
        </div>
        <div className="flex items-center gap-4 text-xs text-gray-500">
          <span>
            Total: <span className="font-semibold text-gray-700 tabular-nums">{fmt(data.total)}</span>
          </span>
          <span>
            Cash remaining: <span className="font-semibold text-gray-700 tabular-nums">{fmt(data.cashRemaining)}</span>
          </span>
        </div>
      </div>
    </div>
  )
}

// ── Main export ───────────────────────────────────────────────────────────────

interface RichCardProps {
  toolCalls: string[]
  content: string
}

export default function RichCard({ toolCalls, content }: RichCardProps) {
  if (toolCalls.includes('portfolio_summary')) {
    const holdings = parseHoldings(content)
    if (holdings.length === 0) return null
    return <HoldingsCard holdings={holdings} />
  }

  if (toolCalls.includes('transaction_history')) {
    const transactions = parseTransactions(content)
    if (transactions.length === 0) return null
    return <TransactionsCard transactions={transactions} />
  }

  if (toolCalls.includes('symbol_lookup')) {
    const symbols = parseSymbolInfo(content)
    if (symbols.length === 0) return null
    return <SymbolCard symbols={symbols} />
  }

  if (toolCalls.includes('portfolio_performance')) {
    const data = parsePerformance(content)
    if (data) return <PerformanceCard data={data} />
  }

  if (toolCalls.includes('risk_analysis')) {
    const data = parseRiskAnalysis(content)
    if (data) return <RiskCard data={data} />
  }

  if (toolCalls.includes('paper_trade')) {
    // Try trade confirmation first, then portfolio view
    const trade = parsePaperTrade(content)
    if (trade) return <PaperTradeCard data={trade} />
    const portfolio = parsePaperPortfolio(content)
    if (portfolio) return <PaperPortfolioCard data={portfolio} />
  }

  return null
}
