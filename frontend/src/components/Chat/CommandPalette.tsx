import { useEffect, useRef, useState } from 'react'

interface CommandItem {
  label: string
  description: string
  message: string
  action: 'send' | 'insert'
}

interface CommandCategory {
  name: string
  icon: React.ReactNode
  items: CommandItem[]
}

interface CommandPaletteProps {
  onSend: (text: string) => void
  onInsert: (text: string) => void
  isPaperTrading: boolean
  isOpen: boolean
  onClose: () => void
  filter: string
  showFilter: boolean
  onFilterChange: (value: string) => void
}

// Icons
function BarChartIcon() {
  return (
    <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="w-3.5 h-3.5">
      <line x1="18" y1="20" x2="18" y2="10" />
      <line x1="12" y1="20" x2="12" y2="4" />
      <line x1="6" y1="20" x2="6" y2="14" />
    </svg>
  )
}

function MagnifierIcon() {
  return (
    <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="w-3.5 h-3.5">
      <circle cx="11" cy="11" r="8" />
      <line x1="21" y1="21" x2="16.65" y2="16.65" />
    </svg>
  )
}

function SwapArrowsIcon() {
  return (
    <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="w-3.5 h-3.5">
      <polyline points="17 1 21 5 17 9" />
      <path d="M3 11V9a4 4 0 0 1 4-4h14" />
      <polyline points="7 23 3 19 7 15" />
      <path d="M21 13v2a4 4 0 0 1-4 4H3" />
    </svg>
  )
}

const PORTFOLIO_ITEMS: CommandItem[] = [
  { label: 'Morning Briefing', description: 'Daily portfolio summary & alerts', message: 'Morning briefing', action: 'send' },
  { label: 'Portfolio Overview', description: "See all your holdings", message: "What's in my portfolio?", action: 'send' },
  { label: 'Performance', description: 'Check portfolio performance', message: 'Show my portfolio performance', action: 'send' },
  { label: 'Transactions', description: 'View recent transactions', message: 'Show my recent transactions', action: 'send' },
  { label: 'Risk Analysis', description: 'Analyze portfolio risk', message: 'Analyze my portfolio risk', action: 'send' },
]

const RESEARCH_ITEMS: CommandItem[] = [
  { label: 'Deep Dive', description: 'Detailed analysis of a stock', message: 'Tell me about ', action: 'insert' },
  { label: 'Conviction Score', description: 'AI conviction rating for a stock', message: "What's the conviction score for ", action: 'insert' },
  { label: 'Stock Quote', description: 'Get current price & data', message: 'Get a quote for ', action: 'insert' },
  { label: 'Look Up Symbol', description: 'Find a stock ticker', message: 'Look up ', action: 'insert' },
  { label: 'Congressional Activity', description: 'See congressional trades', message: 'Show congressional trades for ', action: 'insert' },
]

const TRADING_ITEMS: CommandItem[] = [
  { label: 'Buy', description: 'Buy shares in paper portfolio', message: 'Buy ', action: 'insert' },
  { label: 'Sell', description: 'Sell shares in paper portfolio', message: 'Sell ', action: 'insert' },
  { label: 'Paper Portfolio', description: 'View paper portfolio holdings', message: 'Show my paper portfolio', action: 'send' },
]

function fuzzyMatch(text: string, filter: string): boolean {
  if (!filter) return true
  const lower = text.toLowerCase()
  const f = filter.toLowerCase()
  return lower.includes(f)
}

export default function CommandPalette({
  onSend,
  onInsert,
  isPaperTrading,
  isOpen,
  onClose,
  filter,
  showFilter,
  onFilterChange,
}: CommandPaletteProps) {
  const [activeIndex, setActiveIndex] = useState(0)
  const containerRef = useRef<HTMLDivElement>(null)
  const filterInputRef = useRef<HTMLInputElement>(null)

  const categories: CommandCategory[] = [
    { name: 'Portfolio', icon: <BarChartIcon />, items: PORTFOLIO_ITEMS },
    { name: 'Research', icon: <MagnifierIcon />, items: RESEARCH_ITEMS },
    ...(isPaperTrading ? [{ name: 'Trading', icon: <SwapArrowsIcon />, items: TRADING_ITEMS }] : []),
  ]

  // Filter items
  const filteredCategories = categories
    .map((cat) => ({
      ...cat,
      items: cat.items.filter(
        (item) => fuzzyMatch(item.label, filter) || fuzzyMatch(item.description, filter)
      ),
    }))
    .filter((cat) => cat.items.length > 0)

  // Flat list for keyboard navigation
  const flatItems = filteredCategories.flatMap((cat) => cat.items)

  // Reset active index when filter changes
  useEffect(() => {
    setActiveIndex(0)
  }, [filter])

  // Focus filter input when opened via slash
  useEffect(() => {
    if (isOpen && showFilter && filterInputRef.current) {
      filterInputRef.current.focus()
    }
  }, [isOpen, showFilter])

  // Click outside to close
  useEffect(() => {
    if (!isOpen) return
    const handleMouseDown = (e: MouseEvent) => {
      if (containerRef.current && !containerRef.current.contains(e.target as Node)) {
        onClose()
      }
    }
    document.addEventListener('mousedown', handleMouseDown)
    return () => document.removeEventListener('mousedown', handleMouseDown)
  }, [isOpen, onClose])

  const selectItem = (item: CommandItem) => {
    if (item.action === 'send') {
      onSend(item.message)
    } else {
      onInsert(item.message)
    }
    onClose()
  }

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'ArrowDown') {
      e.preventDefault()
      setActiveIndex((prev) => (prev + 1) % Math.max(flatItems.length, 1))
    } else if (e.key === 'ArrowUp') {
      e.preventDefault()
      setActiveIndex((prev) => (prev - 1 + Math.max(flatItems.length, 1)) % Math.max(flatItems.length, 1))
    } else if (e.key === 'Enter') {
      e.preventDefault()
      if (flatItems[activeIndex]) {
        selectItem(flatItems[activeIndex])
      }
    } else if (e.key === 'Escape') {
      e.preventDefault()
      onClose()
    } else if (e.key === 'Backspace' && filter === '') {
      e.preventDefault()
      onClose()
    }
  }

  if (!isOpen) return null

  // Track absolute index across categories for active state
  let itemCounter = 0

  return (
    <div
      ref={containerRef}
      className="absolute bottom-full left-0 mb-2 w-72 bg-white border border-gray-200 rounded-xl shadow-lg max-h-96 overflow-y-auto z-50"
      onKeyDown={handleKeyDown}
    >
      {showFilter && (
        <div className="px-3 pt-3 pb-2 border-b border-gray-100">
          <input
            ref={filterInputRef}
            type="text"
            value={filter}
            onChange={(e) => onFilterChange(e.target.value)}
            placeholder="Search commands..."
            className="w-full text-sm text-gray-700 placeholder-gray-400 outline-none bg-transparent"
            onKeyDown={handleKeyDown}
          />
        </div>
      )}

      <div className="py-1.5">
        {filteredCategories.length === 0 ? (
          <div className="px-4 py-6 text-center text-xs text-gray-400">No matching commands</div>
        ) : (
          filteredCategories.map((cat) => (
            <div key={cat.name}>
              <div className="flex items-center gap-1.5 px-3 py-1.5 text-[10px] font-bold uppercase tracking-wider text-gray-400">
                <span className="text-gray-300">{cat.icon}</span>
                {cat.name}
              </div>
              {cat.items.map((item) => {
                const currentIndex = itemCounter++
                const isActive = currentIndex === activeIndex
                return (
                  <button
                    key={item.label}
                    className={`w-full flex items-start gap-2.5 px-3 py-2 text-left transition-colors ${
                      isActive ? 'bg-slate-50/80' : 'hover:bg-slate-50/60'
                    }`}
                    onMouseEnter={() => setActiveIndex(currentIndex)}
                    onClick={() => selectItem(item)}
                  >
                    <div className="flex-shrink-0 w-6 h-6 rounded-md bg-gray-100 flex items-center justify-center text-gray-400 mt-0.5">
                      {cat.icon}
                    </div>
                    <div className="min-w-0">
                      <div className="text-sm font-medium text-gray-700 truncate">{item.label}</div>
                      <div className="text-xs text-gray-400 truncate">{item.description}</div>
                    </div>
                  </button>
                )
              })}
            </div>
          ))
        )}
      </div>
    </div>
  )
}
