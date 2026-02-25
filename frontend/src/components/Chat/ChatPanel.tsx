import { useEffect, useRef } from 'react'
import type { ChatMessage } from '../../types'
import MessageBubble from './MessageBubble'
import ChatInput from './ChatInput'

interface ChatPanelProps {
  messages: ChatMessage[]
  isLoading: boolean
  onSend: (text: string) => void
}

const SUGGESTED_QUERIES = [
  "What's in my portfolio?",
  'Show my recent transactions',
  'Look up NVDA',
]

function TypingIndicator() {
  return (
    <div className="flex gap-2.5 items-end">
      <div className="flex-shrink-0 w-7 h-7 rounded-full flex items-center justify-center text-xs font-bold shadow-sm bg-white border border-gray-200 text-gray-500">
        AI
      </div>
      <div className="px-4 py-3 bg-white border border-gray-100 rounded-2xl rounded-bl-sm shadow-sm">
        <div className="flex items-center gap-1.5 h-4">
          <span
            className="w-2 h-2 rounded-full bg-gray-300 animate-bounce"
            style={{ animationDelay: '0ms', animationDuration: '1.2s' }}
          />
          <span
            className="w-2 h-2 rounded-full bg-gray-300 animate-bounce"
            style={{ animationDelay: '200ms', animationDuration: '1.2s' }}
          />
          <span
            className="w-2 h-2 rounded-full bg-gray-300 animate-bounce"
            style={{ animationDelay: '400ms', animationDuration: '1.2s' }}
          />
        </div>
      </div>
    </div>
  )
}

function WelcomeState({ onSend }: { onSend: (text: string) => void }) {
  return (
    <div className="flex flex-col items-center justify-center flex-1 px-6 pb-8 select-none">
      {/* Logo / icon */}
      <div className="w-16 h-16 rounded-2xl bg-gradient-to-br from-indigo-500 to-violet-500 flex items-center justify-center shadow-lg mb-5">
        <svg
          xmlns="http://www.w3.org/2000/svg"
          viewBox="0 0 24 24"
          fill="none"
          stroke="white"
          strokeWidth="1.8"
          strokeLinecap="round"
          strokeLinejoin="round"
          className="w-8 h-8"
        >
          <polyline points="22 7 13.5 15.5 8.5 10.5 2 17" />
          <polyline points="16 7 22 7 22 13" />
        </svg>
      </div>

      <h1 className="text-2xl font-bold text-gray-800 mb-1">Welcome to AgentForge</h1>
      <p className="text-sm text-gray-500 mb-8 text-center max-w-xs">
        Your AI-powered portfolio assistant. Ask anything about your investments.
      </p>

      <div className="flex flex-wrap justify-center gap-2">
        {SUGGESTED_QUERIES.map((query) => (
          <button
            key={query}
            onClick={() => onSend(query)}
            className="px-4 py-2 rounded-full border border-indigo-200 bg-indigo-50 text-indigo-600 text-sm font-medium hover:bg-indigo-100 hover:border-indigo-300 hover:shadow-sm active:scale-95 transition-all duration-150"
          >
            {query}
          </button>
        ))}
      </div>
    </div>
  )
}

export default function ChatPanel({ messages, isLoading, onSend }: ChatPanelProps) {
  const scrollRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight
    }
  }, [messages, isLoading])

  const hasMessages = messages.length > 0

  return (
    <div className="flex flex-col h-full bg-gray-50">
      {/* Scrollable message area */}
      <div
        ref={scrollRef}
        className="flex-1 overflow-y-auto"
        style={{ scrollBehavior: 'smooth' }}
      >
        {!hasMessages ? (
          <WelcomeState onSend={onSend} />
        ) : (
          <div className="max-w-3xl mx-auto px-4 py-6 space-y-5">
            {messages.map((msg) => (
              <MessageBubble key={msg.id} message={msg} />
            ))}
            {isLoading && <TypingIndicator />}
          </div>
        )}
      </div>

      {/* Input bar */}
      <ChatInput onSend={onSend} disabled={isLoading} />
    </div>
  )
}
