import { useRef, useState, type KeyboardEvent, type ReactNode } from 'react'
import CommandPalette from './CommandPalette'

interface ChatInputProps {
  onSend: (text: string) => void
  disabled?: boolean
  leftSlot?: ReactNode
  isPaperTrading?: boolean
}

function GridIcon() {
  return (
    <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="w-4 h-4">
      <rect x="3" y="3" width="7" height="7" />
      <rect x="14" y="3" width="7" height="7" />
      <rect x="3" y="14" width="7" height="7" />
      <rect x="14" y="14" width="7" height="7" />
    </svg>
  )
}

export default function ChatInput({
  onSend,
  disabled = false,
  leftSlot,
  isPaperTrading = false,
}: ChatInputProps) {
  const [value, setValue] = useState('')
  const [isPaletteOpen, setIsPaletteOpen] = useState(false)
  const [paletteFilter, setPaletteFilter] = useState('')
  const [openedViaSlash, setOpenedViaSlash] = useState(false)
  const inputRef = useRef<HTMLInputElement>(null)

  const handleSend = () => {
    const trimmed = value.trim()
    if (!trimmed || disabled) return
    onSend(trimmed)
    setValue('')
  }

  const handleKeyDown = (e: KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      if (isPaletteOpen) return // let palette handle it
      e.preventDefault()
      handleSend()
      return
    }

    // Open palette with "/" when input is empty
    if (e.key === '/' && value === '' && !isPaletteOpen) {
      e.preventDefault()
      setOpenedViaSlash(true)
      setPaletteFilter('')
      setIsPaletteOpen(true)
      return
    }
  }

  const handleClosePalette = () => {
    setIsPaletteOpen(false)
    setPaletteFilter('')
    setOpenedViaSlash(false)
    // Re-focus the input
    setTimeout(() => inputRef.current?.focus(), 0)
  }

  const handleInsert = (text: string) => {
    setValue(text)
    setTimeout(() => {
      if (inputRef.current) {
        inputRef.current.focus()
        // Place cursor at end
        const len = text.length
        inputRef.current.setSelectionRange(len, len)
      }
    }, 0)
  }

  const handlePaletteSend = (text: string) => {
    onSend(text)
  }

  const togglePalette = () => {
    if (isPaletteOpen) {
      handleClosePalette()
    } else {
      setOpenedViaSlash(false)
      setPaletteFilter('')
      setIsPaletteOpen(true)
    }
  }

  return (
    <div className="sticky bottom-0 bg-white border-t border-gray-100 px-4 py-3 shadow-[0_-4px_20px_rgba(0,0,0,0.06)]">
      <div className="max-w-3xl mx-auto flex items-center gap-3">
        {/* Command palette button */}
        <div className="relative flex-shrink-0">
          <button
            type="button"
            onClick={togglePalette}
            aria-label="Open command palette"
            className={`w-9 h-9 rounded-lg flex items-center justify-center transition-colors ${
              isPaletteOpen
                ? 'bg-indigo-50 text-indigo-500'
                : 'text-gray-400 hover:bg-gray-100'
            }`}
          >
            <GridIcon />
          </button>
          <CommandPalette
            onSend={handlePaletteSend}
            onInsert={handleInsert}
            isPaperTrading={isPaperTrading}
            isOpen={isPaletteOpen}
            onClose={handleClosePalette}
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
