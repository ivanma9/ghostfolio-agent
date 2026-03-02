import { AreaChart, Area, XAxis, YAxis, Tooltip, ResponsiveContainer } from 'recharts'
import type { Holding, Transaction, SymbolInfo, PerformanceData, RiskData, PaperPortfolio, PaperTradeResult, HoldingDetailData, MorningBriefingData } from '../../types'

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
    allocation: number
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
      allocation: 0,
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

export function parseHoldingDetail(text: string): HoldingDetailData | null {
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

function parseMorningBriefing(text: string): MorningBriefingData | null {
  if (!text.includes('Morning Briefing')) return null

  const dateMatch = text.match(/\*{0,2}Morning Briefing:?\*{0,2}\s*(.+)/)
  const briefingDate = dateMatch?.[1]?.replace(/\*+/g, '').trim() || new Date().toLocaleDateString()

  const totalValueMatch = text.match(/\*{0,2}Total Value:?\*{0,2}\s*\$?([\d,]+\.?\d*)/)
  const dailyChangeMatch = text.match(/\*{0,2}Daily Change:?\*{0,2}\s*\+?([+-]?[\d.]+)%\s*\(\$?([+-]?[\d,.]+)\)/)
  const holdingsCountMatch = text.match(/\*{0,2}Holdings:?\*{0,2}\s*(\d+)/)

  const portfolioOverview = {
    totalValue: totalValueMatch ? parseFloat(totalValueMatch[1].replace(/,/g, '')) : 0,
    dailyChange: dailyChangeMatch ? parseFloat(dailyChangeMatch[1]) : 0,
    dailyChangeAmount: dailyChangeMatch ? parseFloat(dailyChangeMatch[2].replace(/,/g, '')) : 0,
    holdingsCount: holdingsCountMatch ? parseInt(holdingsCountMatch[1]) : 0,
  }

  const topMovers: MorningBriefingData['topMovers'] = []
  const moverRegex = /[▲▼]\s+(\w+)\s+\(([^)]+)\):\s*([+-]?[\d.]+)%\s*@\s*\$([\d,]+\.?\d*)/g
  let match
  while ((match = moverRegex.exec(text)) !== null) {
    topMovers.push({
      symbol: match[1],
      name: match[2],
      dailyChange: parseFloat(match[3]),
      currentPrice: parseFloat(match[4].replace(/,/g, '')),
      direction: match[3].startsWith('-') ? 'down' : 'up',
    })
  }

  const earningsWatch: MorningBriefingData['earningsWatch'] = []
  const earningsSection = text.match(/Earnings Watch:[\s\S]*?(?=\n\n|\nMarket Signals:)/)?.[0] || ''
  const earningsRegex = /(\w+)\s+\(([^)]+)\):\s*(\d{4}-\d{2}-\d{2})\s*\(in\s+(\d+)\s+days?\)/g
  while ((match = earningsRegex.exec(earningsSection)) !== null) {
    earningsWatch.push({
      symbol: match[1],
      name: match[2],
      earningsDate: match[3],
      daysUntil: parseInt(match[4]),
    })
  }

  const marketSignals: MorningBriefingData['marketSignals'] = []
  const signalRegex = /(\w+)\s+\(([^)]+)\):\s*Sentiment=(\w+),\s*Analyst=([^,]+),\s*Conviction=(?:(\d+)\/100\s*\(([^)]+)\)|N\/A)/g
  const signalsSection = text.match(/Market Signals:[\s\S]*?(?=\n\nMacro Snapshot:)/)?.[0] || text
  while ((match = signalRegex.exec(signalsSection)) !== null) {
    const afterMatch = signalsSection.slice(match.index + match[0].length, match.index + match[0].length + 200)
    const flagsMatch = afterMatch.match(/^\s*\n\s*Flags:\s*(.+)/)
    const flags = flagsMatch ? flagsMatch[1].split(',').map((f: string) => f.trim()) : []
    marketSignals.push({
      symbol: match[1],
      name: match[2],
      sentimentLabel: match[3],
      analystConsensus: match[4].trim(),
      convictionScore: match[5] ? parseInt(match[5]) : null,
      convictionLabel: match[6] || 'N/A',
      flags,
    })
  }

  const fedMatch = text.match(/Fed Funds Rate:\s*([\d.]+)%/)
  const cpiMatch = text.match(/CPI:\s*([\d.]+)%/)
  const treasuryMatch = text.match(/10Y Treasury Yield:\s*([\d.]+)%/)
  const cachedMatch = text.includes('(cached)')
  const macroSnapshot = {
    fedFundsRate: fedMatch?.[1] || 'N/A',
    cpi: cpiMatch?.[1] || 'N/A',
    treasury10y: treasuryMatch?.[1] || 'N/A',
    cached: cachedMatch,
  }

  const actionItems: string[] = []
  const actionRegex = /•\s+(.+)/g
  while ((match = actionRegex.exec(text)) !== null) {
    actionItems.push(match[1].trim())
  }

  return {
    briefingDate,
    portfolioOverview,
    topMovers,
    earningsWatch,
    marketSignals,
    macroSnapshot,
    actionItems,
  }
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
                : data.analystSignal.label === 'Sell' || data.analystSignal.label === 'Strong Sell'
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
                </>
              )
            })()}
          </div>
          <div className="flex justify-between mt-2 text-[10px] text-white/40">
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

function MorningBriefingCard({ data }: { data: MorningBriefingData }) {
  const isPositive = data.portfolioOverview.dailyChange >= 0
  const changeColor = isPositive ? 'text-emerald-600' : 'text-red-500'
  const changeBg = isPositive ? 'bg-emerald-50' : 'bg-red-50'

  return (
    <div className="mt-3 space-y-3">
      {/* Portfolio Overview */}
      <div className="bg-gradient-to-r from-indigo-50 to-violet-50 rounded-xl p-4 border border-indigo-100">
        <div className="flex items-center justify-between mb-2">
          <h3 className="text-sm font-semibold text-indigo-900">Portfolio Overview</h3>
          <span className="text-xs text-indigo-500">{data.briefingDate}</span>
        </div>
        <div className="text-2xl font-bold text-gray-900">
          ${data.portfolioOverview.totalValue.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
        </div>
        <div className="flex items-center gap-2 mt-1">
          <span className={`text-sm font-semibold ${changeColor}`}>
            {data.portfolioOverview.dailyChange >= 0 ? '+' : ''}{data.portfolioOverview.dailyChange.toFixed(1)}%
          </span>
          <span className={`text-xs px-2 py-0.5 rounded-full ${changeBg} ${changeColor}`}>
            ${data.portfolioOverview.dailyChangeAmount >= 0 ? '+' : ''}{data.portfolioOverview.dailyChangeAmount.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
          </span>
          <span className="text-xs text-gray-500">{data.portfolioOverview.holdingsCount} holdings</span>
        </div>
      </div>

      {/* Top Movers */}
      {data.topMovers.length > 0 && (
        <div className="bg-white rounded-xl p-4 border border-gray-200">
          <h3 className="text-sm font-semibold text-gray-700 mb-2">Top Movers</h3>
          <div className="space-y-2">
            {data.topMovers.map((m) => (
              <div key={m.symbol} className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <span className={`text-lg ${m.direction === 'up' ? 'text-emerald-500' : 'text-red-500'}`}>
                    {m.direction === 'up' ? '▲' : '▼'}
                  </span>
                  <div>
                    <span className="font-semibold text-sm text-gray-900">{m.symbol}</span>
                    <span className="text-xs text-gray-500 ml-1">{m.name}</span>
                  </div>
                </div>
                <div className="text-right">
                  <span className={`text-sm font-semibold ${m.direction === 'up' ? 'text-emerald-600' : 'text-red-500'}`}>
                    {m.dailyChange >= 0 ? '+' : ''}{m.dailyChange.toFixed(1)}%
                  </span>
                  <span className="text-xs text-gray-500 ml-2">${m.currentPrice.toLocaleString('en-US', { minimumFractionDigits: 2 })}</span>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Earnings Watch */}
      {data.earningsWatch.length > 0 && (
        <div className="bg-amber-50 rounded-xl p-4 border border-amber-200">
          <h3 className="text-sm font-semibold text-amber-800 mb-2">Earnings Watch</h3>
          <div className="space-y-2">
            {data.earningsWatch.map((e) => (
              <div key={e.symbol} className="flex items-center justify-between">
                <div>
                  <span className="font-semibold text-sm text-gray-900">{e.symbol}</span>
                  <span className="text-xs text-gray-600 ml-1">{e.name}</span>
                </div>
                <div className="flex items-center gap-2">
                  <span className="text-xs text-gray-600">{e.earningsDate}</span>
                  <span className="text-xs font-semibold px-2 py-0.5 rounded-full bg-amber-200 text-amber-800">
                    in {e.daysUntil} days
                  </span>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Market Signals */}
      {data.marketSignals.length > 0 && (
        <div className="bg-white rounded-xl p-4 border border-gray-200">
          <h3 className="text-sm font-semibold text-gray-700 mb-2">Market Signals</h3>
          <div className="space-y-3">
            {data.marketSignals.map((s) => (
              <div key={s.symbol} className="space-y-1">
                <div className="flex items-center gap-2">
                  <span className="font-semibold text-sm text-gray-900">{s.symbol}</span>
                  <span className="text-xs text-gray-500">{s.name}</span>
                </div>
                <div className="flex flex-wrap gap-1.5">
                  <span className={`text-xs px-2 py-0.5 rounded-full font-medium ${
                    s.sentimentLabel === 'Bullish' ? 'bg-emerald-100 text-emerald-700' :
                    s.sentimentLabel === 'Bearish' ? 'bg-red-100 text-red-700' :
                    'bg-gray-100 text-gray-600'
                  }`}>
                    {s.sentimentLabel}
                  </span>
                  <span className="text-xs px-2 py-0.5 rounded-full bg-blue-100 text-blue-700 font-medium">
                    {s.analystConsensus}
                  </span>
                  {s.convictionScore !== null && (
                    <span className={`text-xs px-2 py-0.5 rounded-full font-medium ${
                      s.convictionScore >= 61 ? 'bg-emerald-100 text-emerald-700' :
                      s.convictionScore >= 41 ? 'bg-yellow-100 text-yellow-700' :
                      'bg-red-100 text-red-700'
                    }`}>
                      {s.convictionScore}/100 {s.convictionLabel}
                    </span>
                  )}
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Macro Snapshot */}
      {(data.macroSnapshot.fedFundsRate !== 'N/A' || data.macroSnapshot.cpi !== 'N/A') && (
        <div className="bg-gray-50 rounded-xl p-4 border border-gray-200">
          <div className="flex items-center justify-between mb-2">
            <h3 className="text-sm font-semibold text-gray-600">Macro Snapshot</h3>
            {data.macroSnapshot.cached && (
              <span className="text-[10px] text-gray-400 uppercase tracking-wider">cached</span>
            )}
          </div>
          <div className="grid grid-cols-3 gap-3">
            <div>
              <div className="text-xs text-gray-500">Fed Funds</div>
              <div className="text-sm font-semibold text-gray-800">{data.macroSnapshot.fedFundsRate}%</div>
            </div>
            <div>
              <div className="text-xs text-gray-500">CPI</div>
              <div className="text-sm font-semibold text-gray-800">{data.macroSnapshot.cpi}%</div>
            </div>
            <div>
              <div className="text-xs text-gray-500">10Y Treasury</div>
              <div className="text-sm font-semibold text-gray-800">{data.macroSnapshot.treasury10y}%</div>
            </div>
          </div>
        </div>
      )}

      {/* Action Items */}
      {data.actionItems.length > 0 && (
        <div className="bg-amber-50 rounded-xl p-4 border border-amber-300">
          <h3 className="text-sm font-semibold text-amber-800 mb-2">Action Items</h3>
          <ul className="space-y-1.5">
            {data.actionItems.map((item, i) => (
              <li key={i} className="flex items-start gap-2 text-sm text-amber-900">
                <span className="mt-0.5 w-1.5 h-1.5 rounded-full bg-amber-500 flex-shrink-0" />
                {item}
              </li>
            ))}
          </ul>
        </div>
      )}
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

  if (toolCalls.includes('holding_detail')) {
    const data = parseHoldingDetail(content)
    if (data) return <HoldingDetailCard data={data} />
  }

  if (toolCalls.includes('morning_briefing')) {
    const data = parseMorningBriefing(content)
    if (data) return <MorningBriefingCard data={data} />
  }

  return null
}
