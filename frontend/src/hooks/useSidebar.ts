import { useState, useCallback, useEffect } from 'react'
import { postChat } from '../api/chat'
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
  refresh: () => Promise<void>
}

const SIDEBAR_SESSION_ID = 'sidebar-refresh'

// Parses lines like:
// "AAPL - Apple Inc. | Quantity: 150 | Price: $189.50 | Value: $28,425.00 | Allocation: 34.2%"
function parseHoldingsFromText(text: string): Holding[] {
  const holdings: Holding[] = []

  const lines = text.split('\n')

  for (const line of lines) {
    try {
      // Match symbol and name: "AAPL - Apple Inc."
      const symbolNameMatch = line.match(/^([A-Z0-9.]+)\s*-\s*([^|]+)/)
      if (!symbolNameMatch) continue

      const symbol = symbolNameMatch[1].trim()
      const name = symbolNameMatch[2].trim()

      // Quantity: 150
      const quantityMatch = line.match(/Quantity:\s*([\d,]+(?:\.\d+)?)/)
      // Price: $189.50
      const priceMatch = line.match(/Price:\s*\$?([\d,]+(?:\.\d+)?)/)
      // Value: $28,425.00
      const valueMatch = line.match(/Value:\s*\$?([\d,]+(?:\.\d+)?)/)
      // Allocation: 34.2%
      const allocationMatch = line.match(/Allocation:\s*([\d.]+)%/)
      // Currency (optional): Currency: USD
      const currencyMatch = line.match(/Currency:\s*([A-Z]{3})/)

      if (!quantityMatch || !priceMatch || !valueMatch || !allocationMatch) continue

      const quantity = parseFloat(quantityMatch[1].replace(/,/g, ''))
      const price = parseFloat(priceMatch[1].replace(/,/g, ''))
      const value = parseFloat(valueMatch[1].replace(/,/g, ''))
      const allocation = parseFloat(allocationMatch[1])
      const currency = currencyMatch ? currencyMatch[1] : 'USD'

      holdings.push({ symbol, name, quantity, price, value, allocation, currency })
    } catch {
      // Skip lines that fail to parse
      continue
    }
  }

  return holdings
}

function parsePortfolioValue(text: string): number {
  // Look for total portfolio value patterns like "Total: $83,125.00" or "Portfolio Value: $83,125.00"
  const match = text.match(/(?:Total(?:\s+Portfolio)?(?:\s+Value)?|Portfolio\s+Value):\s*\$?([\d,]+(?:\.\d+)?)/i)
  if (match) {
    return parseFloat(match[1].replace(/,/g, ''))
  }
  return 0
}

function parseDailyChange(text: string): DailyChange {
  // Look for daily change patterns like "Daily Change: +$150.00 (+0.18%)"
  const match = text.match(/Daily\s+Change:\s*([+-]?\$?[\d,]+(?:\.\d+)?)\s*\(([+-]?[\d.]+)%\)/i)
  if (match) {
    const value = parseFloat(match[1].replace(/[$,]/g, ''))
    const percent = parseFloat(match[2])
    return { value, percent }
  }
  return { value: 0, percent: 0 }
}

export function useSidebar(): UseSidebarReturn {
  const [holdings, setHoldings] = useState<Holding[]>([])
  const [portfolioValue, setPortfolioValue] = useState(0)
  const [dailyChange, setDailyChange] = useState<DailyChange>({ value: 0, percent: 0 })
  const [isLoading, setIsLoading] = useState(false)

  const refresh = useCallback(async () => {
    setIsLoading(true)
    try {
      const data = await postChat({
        message: 'Give me my portfolio summary',
        session_id: SIDEBAR_SESSION_ID,
      })

      const text = data.response

      const parsedHoldings = parseHoldingsFromText(text)
      const parsedValue = parsePortfolioValue(text)
      const parsedDailyChange = parseDailyChange(text)

      setHoldings(parsedHoldings)
      setPortfolioValue(parsedValue)
      setDailyChange(parsedDailyChange)
    } catch (error) {
      console.error('Sidebar refresh error:', error)
      setHoldings([])
      setPortfolioValue(0)
      setDailyChange({ value: 0, percent: 0 })
    } finally {
      setIsLoading(false)
    }
  }, [])

  useEffect(() => {
    refresh()
  }, [refresh])

  return { holdings, portfolioValue, dailyChange, isLoading, refresh }
}
