export interface ChatMessage {
  id: string
  role: 'user' | 'assistant'
  content: string
  toolCalls: string[]
  timestamp: Date
}

export interface ChatRequest {
  message: string
  session_id: string
  model?: string
  paper_trading?: boolean
}

export interface ModelOption {
  id: string
  name: string
  provider: string
}

export interface ChatResponse {
  response: string
  session_id: string
  tool_calls: string[]
  confidence: string
}

export interface Holding {
  symbol: string
  name: string
  quantity: number
  price: number
  value: number
  allocation: number
  currency: string
}

export interface Transaction {
  date: string
  type: 'BUY' | 'SELL' | 'DIVIDEND'
  symbol: string
  quantity: number
  price: number
  fee: number
  total: number
}

export interface SymbolInfo {
  symbol: string
  name: string
  assetClass: string
  currency: string
  dataSource: string
}

export interface SidebarData {
  portfolioValue: number
  dailyChange: { value: number; percent: number }
  holdings: Holding[]
  isLoading: boolean
}

// Performance
export interface PerformanceDataPoint {
  date: string
  value: number
}

export interface PerformanceData {
  period: string
  totalReturn: number
  totalReturnPercent: number
  currentValue: number
  dataPoints: PerformanceDataPoint[]
}

// Risk
export interface RiskData {
  concentrationRisk: {
    topHolding: string
    topPercent: number
    isHighRisk: boolean
  }
  sectorBreakdown: Array<{ name: string; percent: number }>
  currencyBreakdown: Array<{ name: string; percent: number }>
  summary: string
}

// Paper Trading
export interface PaperPosition {
  symbol: string
  quantity: number
  avgCost: number
  currentPrice: number
  value: number
  pnl: number
  pnlPercent: number
  allocation: number
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
