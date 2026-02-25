import { useState, type KeyboardEvent } from 'react'

interface ChatInputProps {
  onSend: (text: string) => void
  disabled?: boolean
}

export default function ChatInput({ onSend, disabled = false }: ChatInputProps) {
  const [value, setValue] = useState('')

  const handleSend = () => {
    const trimmed = value.trim()
    if (!trimmed || disabled) return
    onSend(trimmed)
    setValue('')
  }

  const handleKeyDown = (e: KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      handleSend()
    }
  }

  return (
    <div className="sticky bottom-0 bg-white border-t border-gray-100 px-4 py-3 shadow-[0_-4px_20px_rgba(0,0,0,0.06)]">
      <div className="max-w-3xl mx-auto flex items-center gap-3">
        <input
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
