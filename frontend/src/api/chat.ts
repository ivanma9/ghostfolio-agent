import type { ChatRequest, ChatResponse } from '../types'

export type ChatErrorType = 'timeout' | 'network' | 'server'

const ERROR_MESSAGES: Record<ChatErrorType, string> = {
  timeout: 'That took too long. Try a simpler question or try again.',
  network: "Couldn't reach the server. Check your connection and try again.",
  server: 'Our servers are having trouble. Please try again in a moment.',
}

export class ChatError extends Error {
  type: ChatErrorType
  constructor(type: ChatErrorType) {
    super(ERROR_MESSAGES[type])
    this.type = type
  }
}

export async function postChat(request: ChatRequest): Promise<ChatResponse> {
  let response: Response
  try {
    response = await fetch('/api/chat', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(request),
    })
  } catch (err) {
    if (err instanceof TypeError) {
      throw new ChatError('network')
    }
    if (err instanceof DOMException && err.name === 'AbortError') {
      throw new ChatError('timeout')
    }
    throw new ChatError('network')
  }

  if (!response.ok) {
    if (response.status === 408) {
      throw new ChatError('timeout')
    }
    throw new ChatError('server')
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
  let response: Response
  try {
    response = await fetch('/api/paper-portfolio')
  } catch (err) {
    if (err instanceof TypeError) {
      throw new ChatError('network')
    }
    throw new ChatError('network')
  }

  if (!response.ok) {
    throw new ChatError('server')
  }

  const data = await response.json()
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
