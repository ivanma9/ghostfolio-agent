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
