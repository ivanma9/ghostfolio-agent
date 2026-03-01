import type { ChatRequest, ChatResponse } from '../types'

export async function postChat(request: ChatRequest): Promise<ChatResponse> {
  const response = await fetch('/api/chat', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify(request),
  })

  if (!response.ok) {
    throw new Error(`Chat API error: ${response.status} ${response.statusText}`)
  }

  return response.json() as Promise<ChatResponse>
}

export async function fetchPortfolio(): Promise<{ totalValue: number; dailyChange: number; dailyChangePercent: number; positions: Array<{ symbol: string; name: string; quantity: number; price: number; value: number; allocation: number; currency: string }> }> {
  const response = await fetch('/api/portfolio')
  if (!response.ok) {
    throw new Error(`Portfolio API error: ${response.status} ${response.statusText}`)
  }
  const data = await response.json()
  return {
    totalValue: data.total_value,
    dailyChange: data.daily_change,
    dailyChangePercent: data.daily_change_percent,
    positions: (data.positions || []).map((p: Record<string, unknown>) => ({
      symbol: p.symbol,
      name: p.name,
      quantity: p.quantity,
      price: p.price,
      value: p.value,
      allocation: p.allocation,
      currency: p.currency,
    })),
  }
}

export async function fetchPaperPortfolio(): Promise<import('../types').PaperPortfolio> {
  const response = await fetch('/api/paper-portfolio')
  if (!response.ok) {
    throw new Error(`Paper portfolio API error: ${response.status} ${response.statusText}`)
  }
  const data = await response.json()
  // Map snake_case backend to camelCase frontend
  return {
    cash: data.cash,
    totalValue: data.total_value,
    totalPnl: data.total_pnl,
    totalPnlPercent: data.total_pnl_percent,
    positions: (data.positions || []).map((p: Record<string, unknown>) => ({
      symbol: p.symbol,
      quantity: p.quantity,
      avgCost: p.avg_cost,
      currentPrice: p.current_price,
      value: p.value,
      pnl: p.pnl,
      pnlPercent: p.pnl_percent,
      allocation: p.allocation,
    })),
  }
}
