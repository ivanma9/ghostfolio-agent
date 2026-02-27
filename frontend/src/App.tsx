import { useState, useCallback } from 'react'
import ChatPanel from './components/Chat/ChatPanel'
import { Sidebar } from './components/Sidebar/Sidebar'
import { useChat } from './hooks/useChat'
import { useSidebar } from './hooks/useSidebar'

function App() {
  const sidebar = useSidebar()
  const [selectedModel, setSelectedModel] = useState('anthropic/claude-sonnet-4')
  const [isPaperTrading, setIsPaperTrading] = useState(false)

  const handleToolCall = useCallback(
    (toolCalls: string[]) => {
      if (toolCalls.includes('portfolio_summary')) {
        sidebar.refresh()
      }
    },
    [sidebar.refresh],
  )

  const chat = useChat({ onToolCall: handleToolCall })

  const handleSend = useCallback(
    (text: string) => {
      chat.sendMessage(text, selectedModel, isPaperTrading)
    },
    [chat.sendMessage, selectedModel, isPaperTrading],
  )

  return (
    <div className="flex h-screen bg-gray-50">
      {/* Sidebar */}
      <div className="hidden lg:block">
        <Sidebar
          holdings={sidebar.holdings}
          portfolioValue={sidebar.portfolioValue}
          dailyChange={sidebar.dailyChange}
          isLoading={sidebar.isLoading}
        />
      </div>

      {/* Mobile top bar */}
      <div className="lg:hidden fixed top-0 left-0 right-0 z-10 bg-white border-b border-gray-200 px-4 py-3 flex items-center gap-3">
        <div className="flex items-center justify-center w-8 h-8 rounded-lg bg-gradient-to-br from-indigo-500 to-violet-500">
          <svg className="w-4 h-4 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 7h8m0 0v8m0-8l-8 8-4-4-6 6" />
          </svg>
        </div>
        <span className="font-bold text-gray-900">AgentForge</span>
        {sidebar.portfolioValue > 0 && (
          <span className="ml-auto text-sm font-semibold text-gray-700">
            ${sidebar.portfolioValue.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
          </span>
        )}
      </div>

      {/* Chat Panel */}
      <div className="flex-1 flex flex-col lg:pt-0 pt-14">
        <ChatPanel
          messages={chat.messages}
          isLoading={chat.isLoading}
          onSend={handleSend}
          selectedModel={selectedModel}
          onModelChange={setSelectedModel}
          isPaperTrading={isPaperTrading}
          onPaperTradingChange={setIsPaperTrading}
        />
      </div>
    </div>
  )
}

export default App
