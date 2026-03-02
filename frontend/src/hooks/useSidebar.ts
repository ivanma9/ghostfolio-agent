import { useState, useCallback, useEffect } from 'react'
import { fetchPortfolio, fetchPaperPortfolio, ChatError } from '../api/chat'
import type { Holding } from '../types'

interface DailyChange {
  value: number
  percent: number
}

interface UseSidebarReturn {
  holdings: Holding[]
  portfolioValue: number
  dailyChange: DailyChange
  isLoading: boolean
  error: string | null
  refresh: () => Promise<void>
}

export function useSidebar(isPaperTrading: boolean = false, isGuest: boolean = false, isAuthenticated: boolean = true): UseSidebarReturn {
  const [holdings, setHoldings] = useState<Holding[]>([])
  const [portfolioValue, setPortfolioValue] = useState(0)
  const [dailyChange, setDailyChange] = useState<DailyChange>({ value: 0, percent: 0 })
  const [isLoading, setIsLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const refresh = useCallback(async () => {
    // Not authenticated or guest without paper trading — nothing to fetch
    if (!isAuthenticated || (isGuest && !isPaperTrading)) {
      setHoldings([])
      setPortfolioValue(0)
      setDailyChange({ value: 0, percent: 0 })
      return
    }
    setIsLoading(true)
    try {
      setError(null)
      if (isPaperTrading) {
        const paper = await fetchPaperPortfolio()
        const mappedHoldings: Holding[] = paper.positions.map(p => ({
          symbol: p.symbol,
          name: p.symbol,
          quantity: p.quantity,
          price: p.currentPrice,
          value: p.value,
          allocation: p.allocation,
          currency: 'USD',
        }))
        setHoldings(mappedHoldings)
        setPortfolioValue(paper.totalValue)
        setDailyChange({ value: paper.totalPnl, percent: paper.totalPnlPercent })
      } else {
        const data = await fetchPortfolio()
        const mappedHoldings: Holding[] = data.positions.map(p => ({
          symbol: p.symbol,
          name: p.name,
          quantity: p.quantity,
          price: p.price,
          value: p.value,
          allocation: p.allocation,
          currency: p.currency,
        }))
        setHoldings(mappedHoldings)
        setPortfolioValue(data.totalValue)
        setDailyChange({ value: data.dailyChange, percent: data.dailyChangePercent })
      }
    } catch (error) {
      const message = error instanceof ChatError
        ? error.message
        : 'Failed to load portfolio'
      console.error('Sidebar refresh error:', error)
      setError(message)
      setHoldings([])
      setPortfolioValue(0)
      setDailyChange({ value: 0, percent: 0 })
    } finally {
      setIsLoading(false)
    }
  }, [isPaperTrading, isGuest, isAuthenticated])

  useEffect(() => {
    refresh()
  }, [refresh])

  return { holdings, portfolioValue, dailyChange, isLoading, error, refresh }
}
