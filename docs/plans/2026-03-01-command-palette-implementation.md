# Command Palette Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add a persistent command palette to the chat input bar that surfaces all agent capabilities in categorized groups, accessible via "+" button and "/" shortcut.

**Architecture:** Self-contained within ChatInput — new CommandPalette component renders as a popover, ChatInput manages open/close state and "/" key interception. No backend changes. ChatPanel passes `isPaperTrading` to ChatInput.

**Tech Stack:** React, TypeScript, Tailwind CSS

---

### Task 1: Create CommandPalette component with categories and items

**Files:**
- Create: `frontend/src/components/Chat/CommandPalette.tsx`

**Step 1: Create the component**

Create `frontend/src/components/Chat/CommandPalette.tsx`:

```typescript
import { useState, useEffect, useRef, useCallback } from 'react'

// --- Data ---

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

const PORTFOLIO_ITEMS: CommandItem[] = [
  { label: 'Morning Briefing', description: 'Daily portfolio overview', message: 'Morning briefing', action: 'send' },
  { label: 'Portfolio Overview', description: 'Holdings and allocations', message: "What's in my portfolio?", action: 'send' },
  { label: 'Performance', description: 'Returns and charts', message: 'Show my portfolio performance', action: 'send' },
  { label: 'Transactions', description: 'Recent buy/sell history', message: 'Show my recent transactions', action: 'send' },
  { label: 'Risk Analysis', description: 'Concentration and sector risk', message: 'Analyze my portfolio risk', action: 'send' },
]

const RESEARCH_ITEMS: CommandItem[] = [
  { label: 'Deep Dive', description: 'Detailed holding analysis', message: 'Tell me about ', action: 'insert' },
  { label: 'Conviction Score', description: 'AI confidence rating', message: "What's the conviction score for ", action: 'insert' },
  { label: 'Stock Quote', description: 'Current price and stats', message: 'Get a quote for ', action: 'insert' },
  { label: 'Look Up Symbol', description: 'Find a ticker symbol', message: 'Look up ', action: 'insert' },
  { label: 'Congressional Activity', description: 'Congress member trades', message: 'Show congressional trades for ', action: 'insert' },
]

const TRADING_ITEMS: CommandItem[] = [
  { label: 'Buy', description: 'Purchase shares', message: 'Buy ', action: 'insert' },
  { label: 'Sell', description: 'Sell shares', message: 'Sell ', action: 'insert' },
  { label: 'Paper Portfolio', description: 'View paper positions', message: 'Show my paper portfolio', action: 'send' },
]

// --- Icons ---

function ChartIcon() {
  return (
    <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24" strokeWidth={1.5}>
      <path strokeLinecap="round" strokeLinejoin="round" d="M3 13.125C3 12.504 3.504 12 4.125 12h2.25c.621 0 1.125.504 1.125 1.125v6.75C7.5 20.496 6.996 21 6.375 21h-2.25A1.125 1.125 0 013 19.875v-6.75zM9.75 8.625c0-.621.504-1.125 1.125-1.125h2.25c.621 0 1.125.504 1.125 1.125v11.25c0 .621-.504 1.125-1.125 1.125h-2.25a1.125 1.125 0 01-1.125-1.125V8.625zM16.5 4.125c0-.621.504-1.125 1.125-1.125h2.25C20.496 3 21 3.504 21 4.125v15.75c0 .621-.504 1.125-1.125 1.125h-2.25a1.125 1.125 0 01-1.125-1.125V4.125z" />
    </svg>
  )
}

function SearchIcon() {
  return (
    <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24" strokeWidth={1.5}>
      <path strokeLinecap="round" strokeLinejoin="round" d="M21 21l-5.197-5.197m0 0A7.5 7.5 0 105.196 5.196a7.5 7.5 0 0010.607 10.607z" />
    </svg>
  )
}

function ArrowsIcon() {
  return (
    <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24" strokeWidth={1.5}>
      <path strokeLinecap="round" strokeLinejoin="round" d="M7.5 21L3 16.5m0 0L7.5 12M3 16.5h13.5m0-13.5L21 7.5m0 0L16.5 12M21 7.5H7.5" />
    </svg>
  )
}

// --- Component ---

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
  const paletteRef = useRef<HTMLDivElement>(null)
  const filterRef = useRef<HTMLInputElement>(null)

  // Build categories
  const categories: CommandCategory[] = [
    { name: 'Portfolio', icon: <ChartIcon />, items: PORTFOLIO_ITEMS },
    { name: 'Research', icon: <SearchIcon />, items: RESEARCH_ITEMS },
    ...(isPaperTrading ? [{ name: 'Trading', icon: <ArrowsIcon />, items: TRADING_ITEMS }] : []),
  ]

  // Filter items
  const filterLower = filter.toLowerCase()
  const filteredCategories = categories
    .map(cat => ({
      ...cat,
      items: cat.items.filter(item =>
        item.label.toLowerCase().includes(filterLower) ||
        item.description.toLowerCase().includes(filterLower)
      ),
    }))
    .filter(cat => cat.items.length > 0)

  // Flat list of visible items for arrow key navigation
  const flatItems = filteredCategories.flatMap(cat => cat.items)

  // Reset active index when filter changes
  useEffect(() => {
    setActiveIndex(0)
  }, [filter])

  // Focus filter input when opened with "/"
  useEffect(() => {
    if (isOpen && showFilter && filterRef.current) {
      filterRef.current.focus()
    }
  }, [isOpen, showFilter])

  // Click outside to close
  useEffect(() => {
    if (!isOpen) return
    const handleClick = (e: MouseEvent) => {
      if (paletteRef.current && !paletteRef.current.contains(e.target as Node)) {
        onClose()
      }
    }
    document.addEventListener('mousedown', handleClick)
    return () => document.removeEventListener('mousedown', handleClick)
  }, [isOpen, onClose])

  const handleSelect = useCallback((item: CommandItem) => {
    if (item.action === 'send') {
      onSend(item.message)
    } else {
      onInsert(item.message)
    }
    onClose()
  }, [onSend, onInsert, onClose])

  const handleKeyDown = useCallback((e: React.KeyboardEvent) => {
    if (e.key === 'Escape') {
      e.preventDefault()
      onClose()
    } else if (e.key === 'ArrowDown') {
      e.preventDefault()
      setActiveIndex(prev => (prev + 1) % Math.max(flatItems.length, 1))
    } else if (e.key === 'ArrowUp') {
      e.preventDefault()
      setActiveIndex(prev => (prev - 1 + flatItems.length) % Math.max(flatItems.length, 1))
    } else if (e.key === 'Enter' && flatItems.length > 0) {
      e.preventDefault()
      handleSelect(flatItems[activeIndex])
    } else if (e.key === 'Backspace' && filter === '') {
      e.preventDefault()
      onClose()
    }
  }, [flatItems, activeIndex, handleSelect, onClose, filter])

  if (!isOpen) return null

  // Track cumulative index for active highlighting
  let cumulativeIndex = 0

  return (
    <div
      ref={paletteRef}
      className="absolute bottom-full left-0 mb-2 w-72 bg-white border border-gray-200 rounded-xl shadow-lg max-h-96 overflow-y-auto z-50"
      onKeyDown={handleKeyDown}
    >
      {/* Filter input (only for "/" mode) */}
      {showFilter && (
        <input
          ref={filterRef}
          type="text"
          value={filter}
          onChange={(e) => onFilterChange(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder="Search commands..."
          className="w-full text-sm px-3 py-2 border-b border-gray-100 outline-none placeholder-gray-400"
          autoFocus
        />
      )}

      {filteredCategories.length === 0 ? (
        <div className="px-3 py-4 text-sm text-gray-400 text-center">No matching commands</div>
      ) : (
        filteredCategories.map(category => {
          const categoryItems = category.items.map((item, itemIndex) => {
            const globalIndex = cumulativeIndex + itemIndex
            const isActive = globalIndex === activeIndex
            return (
              <button
                key={item.label}
                onClick={() => handleSelect(item)}
                className={`w-full text-left px-3 py-2 rounded-lg transition-colors duration-150 cursor-pointer flex items-start gap-2.5 ${
                  isActive ? 'bg-slate-50/80' : 'hover:bg-slate-50/60'
                }`}
              >
                <span className="text-gray-400 mt-0.5 flex-shrink-0">{category.icon}</span>
                <div className="flex-1 min-w-0">
                  <p className="text-sm font-medium text-gray-700">{item.label}</p>
                  <p className="text-xs text-gray-400 truncate">{item.description}</p>
                </div>
              </button>
            )
          })
          cumulativeIndex += category.items.length
          return (
            <div key={category.name}>
              <p className="text-[10px] font-bold uppercase tracking-wider text-gray-400 px-3 pt-3 pb-1">
                {category.name}
              </p>
              <div className="px-1 pb-1">
                {categoryItems}
              </div>
            </div>
          )
        })
      )}
    </div>
  )
}
```

**Step 2: Verify it compiles**

Run: `cd frontend && npx tsc -b --noEmit`
Expected: No errors

**Step 3: Commit**

```bash
git add frontend/src/components/Chat/CommandPalette.tsx
git commit -m "feat: create CommandPalette component with categories and filter"
```

---

### Task 2: Integrate CommandPalette into ChatInput with "+" button and "/" shortcut

**Files:**
- Modify: `frontend/src/components/Chat/ChatInput.tsx`

**Step 1: Update ChatInput**

Rewrite `frontend/src/components/Chat/ChatInput.tsx`:

```typescript
import { useState, useRef, useCallback, type KeyboardEvent, type ReactNode } from 'react'
import CommandPalette from './CommandPalette'

interface ChatInputProps {
  onSend: (text: string) => void
  disabled?: boolean
  leftSlot?: ReactNode
  isPaperTrading?: boolean
}

function GridIcon() {
  return (
    <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24" strokeWidth={1.5}>
      <path strokeLinecap="round" strokeLinejoin="round" d="M3.75 6A2.25 2.25 0 016 3.75h2.25A2.25 2.25 0 0110.5 6v2.25a2.25 2.25 0 01-2.25 2.25H6a2.25 2.25 0 01-2.25-2.25V6zM3.75 15.75A2.25 2.25 0 016 13.5h2.25a2.25 2.25 0 012.25 2.25V18a2.25 2.25 0 01-2.25 2.25H6A2.25 2.25 0 013.75 18v-2.25zM13.5 6a2.25 2.25 0 012.25-2.25H18A2.25 2.25 0 0120.25 6v2.25A2.25 2.25 0 0118 10.5h-2.25a2.25 2.25 0 01-2.25-2.25V6zM13.5 15.75a2.25 2.25 0 012.25-2.25H18a2.25 2.25 0 012.25 2.25V18A2.25 2.25 0 0118 20.25h-2.25A2.25 2.25 0 0113.5 18v-2.25z" />
    </svg>
  )
}

export default function ChatInput({ onSend, disabled = false, leftSlot, isPaperTrading = false }: ChatInputProps) {
  const [value, setValue] = useState('')
  const [isPaletteOpen, setIsPaletteOpen] = useState(false)
  const [paletteFilter, setPaletteFilter] = useState('')
  const [openedViaSlash, setOpenedViaSlash] = useState(false)
  const inputRef = useRef<HTMLInputElement>(null)

  const handleSend = useCallback(() => {
    const trimmed = value.trim()
    if (!trimmed || disabled) return
    onSend(trimmed)
    setValue('')
  }, [value, disabled, onSend])

  const openPalette = useCallback((viaSlash: boolean) => {
    setIsPaletteOpen(true)
    setOpenedViaSlash(viaSlash)
    setPaletteFilter('')
  }, [])

  const closePalette = useCallback(() => {
    setIsPaletteOpen(false)
    setPaletteFilter('')
    setOpenedViaSlash(false)
    // Re-focus the main input
    inputRef.current?.focus()
  }, [])

  const handleInsert = useCallback((text: string) => {
    setValue(text)
    // Focus input after palette closes (via setTimeout to let palette close first)
    setTimeout(() => inputRef.current?.focus(), 0)
  }, [])

  const handlePaletteSend = useCallback((text: string) => {
    onSend(text)
  }, [onSend])

  const handleKeyDown = (e: KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      handleSend()
    } else if (e.key === '/' && value === '' && !isPaletteOpen) {
      e.preventDefault()
      openPalette(true)
    }
  }

  return (
    <div className="sticky bottom-0 bg-white border-t border-gray-100 px-4 py-3 shadow-[0_-4px_20px_rgba(0,0,0,0.06)]">
      <div className="max-w-3xl mx-auto flex items-center gap-3">
        {/* "+" button */}
        <div className="relative">
          <button
            onClick={() => isPaletteOpen ? closePalette() : openPalette(false)}
            className={`flex items-center justify-center w-9 h-9 rounded-lg transition-colors duration-150 ${
              isPaletteOpen
                ? 'bg-indigo-50 text-indigo-500'
                : 'text-gray-400 hover:bg-gray-100 hover:text-gray-600'
            }`}
            aria-label="Open command palette"
          >
            <GridIcon />
          </button>
          <CommandPalette
            onSend={handlePaletteSend}
            onInsert={handleInsert}
            isPaperTrading={isPaperTrading}
            isOpen={isPaletteOpen}
            onClose={closePalette}
            filter={paletteFilter}
            showFilter={openedViaSlash}
            onFilterChange={setPaletteFilter}
          />
        </div>

        {leftSlot}

        <input
          ref={inputRef}
          type="text"
          value={value}
          onChange={(e) => setValue(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder="Ask about your portfolio..."
          disabled={disabled}
          className="flex-1 rounded-full border border-gray-200 bg-gray-50 px-5 py-3 text-sm text-gray-800 placeholder-gray-400 outline-none focus:border-indigo-300 focus:bg-white focus:ring-2 focus:ring-indigo-100 transition-all duration-200 disabled:opacity-50 disabled:cursor-not-allowed shadow-sm"
        />
        <button
          onClick={handleSend}
          disabled={disabled || !value.trim()}
          className="flex-shrink-0 w-11 h-11 rounded-full flex items-center justify-center bg-gradient-to-br from-indigo-500 to-violet-500 text-white shadow-md hover:shadow-lg hover:from-indigo-600 hover:to-violet-600 active:scale-95 transition-all duration-200 disabled:opacity-40 disabled:cursor-not-allowed disabled:hover:shadow-md disabled:active:scale-100"
          aria-label="Send message"
        >
          <svg
            xmlns="http://www.w3.org/2000/svg"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="2.5"
            strokeLinecap="round"
            strokeLinejoin="round"
            className="w-5 h-5"
          >
            <line x1="5" y1="12" x2="19" y2="12" />
            <polyline points="12 5 19 12 12 19" />
          </svg>
        </button>
      </div>
    </div>
  )
}
```

**Step 2: Verify it compiles**

Run: `cd frontend && npx tsc -b --noEmit`
Expected: No errors (ChatPanel passes `leftSlot` but not `isPaperTrading` yet — that's ok, it defaults to `false`)

**Step 3: Commit**

```bash
git add frontend/src/components/Chat/ChatInput.tsx
git commit -m "feat: integrate CommandPalette into ChatInput with + button and / shortcut"
```

---

### Task 3: Pass isPaperTrading to ChatInput via ChatPanel

**Files:**
- Modify: `frontend/src/components/Chat/ChatPanel.tsx`

**Step 1: Pass isPaperTrading to ChatInput**

In `frontend/src/components/Chat/ChatPanel.tsx`, find the `<ChatInput>` usage (around line 128-137):

```tsx
      <ChatInput
        onSend={onSend}
        disabled={isLoading}
        leftSlot={
          <>
            <ModelSelector selectedModel={selectedModel} onModelChange={onModelChange} />
            <PaperTradeToggle isActive={isPaperTrading} onChange={onPaperTradingChange} />
          </>
        }
      />
```

Add `isPaperTrading` prop:

```tsx
      <ChatInput
        onSend={onSend}
        disabled={isLoading}
        isPaperTrading={isPaperTrading}
        leftSlot={
          <>
            <ModelSelector selectedModel={selectedModel} onModelChange={onModelChange} />
            <PaperTradeToggle isActive={isPaperTrading} onChange={onPaperTradingChange} />
          </>
        }
      />
```

**Step 2: Verify it compiles**

Run: `cd frontend && npx tsc -b --noEmit`
Expected: No errors

**Step 3: Verify full build**

Run: `cd frontend && npx vite build`
Expected: Build succeeds

**Step 4: Commit**

```bash
git add frontend/src/components/Chat/ChatPanel.tsx
git commit -m "feat: pass isPaperTrading to ChatInput for command palette Trading section"
```

---

### Task 4: Run full test suite, verify, and update docs

**Step 1: Run backend tests**

Run: `uv run pytest tests/unit/ -v`
Expected: All 305 pass (no backend changes)

**Step 2: Run frontend checks**

Run: `cd frontend && npx tsc -b --noEmit && npx vite build`
Expected: Both succeed

**Step 3: Update MEMORY.md**

Add a section about the command palette to the memory file.

**Step 4: Commit docs**

```bash
git add -A
git commit -m "docs: update memory with command palette implementation details"
```
