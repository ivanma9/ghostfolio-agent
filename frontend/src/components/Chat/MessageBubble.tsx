import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import type { ChatMessage } from '../../types'
import RichCard from './RichCard'
import VerificationBanner from './VerificationBanner'

interface MessageBubbleProps {
  message: ChatMessage
}

function formatTime(date: Date): string {
  return new Intl.DateTimeFormat('en-US', { hour: 'numeric', minute: '2-digit', hour12: true }).format(date)
}

/**
 * When a RichCard will render structured data, strip out the raw table/data lines
 * from the markdown so we don't show the same info twice (ugly raw + nice card).
 */
function stripRawData(content: string, toolCalls: string[]): string {
  if (toolCalls.length === 0) return content

  const lines = content.split('\n')
  const filtered = lines.filter((line) => {
    const trimmed = line.trim()

    // Strip lines that look like raw pipe-delimited table data
    // e.g. "| Symbol | Name | Shares | Price | Value | Allocation |"
    // or "| AAPL | Apple Inc. | 13 | $272.14 | $3,537.82 | 12.9% |"
    // or separator rows like "|--------|------|..."
    if (toolCalls.includes('portfolio_summary') || toolCalls.includes('transaction_history') || toolCalls.includes('risk_analysis')) {
      // Lines with 3+ pipes are likely table rows
      if ((trimmed.match(/\|/g) || []).length >= 3) return false
      // Lines that are just dashes/pipes (separator rows)
      if (/^[\s|:-]+$/.test(trimmed) && trimmed.includes('|')) return false
    }

    // Strip "Portfolio Summary" header line if RichCard handles it
    if (toolCalls.includes('portfolio_summary') && /^📊?\s*Portfolio Summary\s*$/i.test(trimmed)) return false

    // Strip data point lines from performance tool (e.g., "2024-01-15: $10,000.00" or "2024-01-15: 10000.00")
    if (toolCalls.includes('portfolio_performance')) {
      if (/^\d{4}-\d{2}-\d{2}:\s*\$?[\d,]+/.test(trimmed)) return false
      if (/^Data Points:/.test(trimmed)) return false
    }

    // Strip raw holding detail data lines when RichCard renders them
    if (toolCalls.includes('holding_detail')) {
      if (/^\s*(Quantity|Market Price|Average Cost|Total Invested|Current Value|Unrealized P&L|Dividends|First Buy|Transactions):/i.test(trimmed)) return false
      if (/^\s*(Strong Buy:|Consensus:|Last Month:|Last Quarter:)/i.test(trimmed)) return false
      if (/^\s*\[(Bullish|Bearish|Neutral|Somewhat)/i.test(trimmed)) return false
      if (/^\s*\d{4}-\d{2}-\d{2}\s+EPS/i.test(trimmed)) return false
      if (/^\s*(Implied Upside|Implied Downside|Analyst Signal|Sentiment:|Earnings Alert):/i.test(trimmed)) return false
    }

    // Strip position/trade data lines from paper_trade
    if (toolCalls.includes('paper_trade')) {
      if ((trimmed.match(/\|/g) || []).length >= 3) return false
      if (/^[\s|:-]+$/.test(trimmed) && trimmed.includes('|')) return false
    }

    // Strip raw morning briefing data lines when RichCard renders them
    if (toolCalls.includes('morning_briefing')) {
      if (/^\s*(Total Value:|Daily Change:|Holdings:)\s/i.test(trimmed)) return false
      if (/^\s*[▲▼]\s+\w+/.test(trimmed)) return false
      if (/^\s*(Fed Funds Rate:|CPI:|10Y Treasury Yield:)\s/i.test(trimmed)) return false
      if (/^\s*•\s+/.test(trimmed)) return false
      if (/^\s*(Portfolio Overview|Top Movers|Earnings Watch|Market Signals|Macro Snapshot|Action Items):?\s*$/i.test(trimmed)) return false
      if (/^\s*Sentiment=/.test(trimmed)) return false
      if (/^\s*Flags:/.test(trimmed)) return false
      if (/^\s*\w+\s+\([^)]+\):\s*(Sentiment=|\d{4}-\d{2}-\d{2}\s*\(in)/.test(trimmed)) return false
    }

    return true
  })

  return filtered.join('\n').replace(/\n{3,}/g, '\n\n').trim()
}

export default function MessageBubble({ message }: MessageBubbleProps) {
  const isUser = message.role === 'user'
  const hasRichCard = !isUser && message.toolCalls.length > 0
  const displayContent = hasRichCard
    ? stripRawData(message.content, message.toolCalls)
    : message.content

  return (
    <div className={`flex gap-2.5 ${isUser ? 'flex-row-reverse' : 'flex-row'} items-end`}>
      {/* Avatar */}
      <div
        className={`flex-shrink-0 w-7 h-7 rounded-full flex items-center justify-center text-xs font-bold shadow-sm ${
          isUser
            ? 'bg-gradient-to-br from-indigo-500 to-violet-500 text-white'
            : 'bg-white border border-gray-200 text-gray-500'
        }`}
      >
        {isUser ? 'You' : 'AI'}
      </div>

      {/* Bubble + timestamp */}
      <div className={`flex flex-col gap-1 max-w-[75%] ${isUser ? 'items-end' : 'items-start'}`}>
        <div
          className={`px-4 py-3 shadow-sm ${
            isUser
              ? 'bg-gradient-to-br from-indigo-500 to-violet-500 text-white rounded-2xl rounded-br-sm'
              : message.isError
                ? 'bg-red-50 border border-red-200 text-red-700 rounded-2xl rounded-bl-sm'
                : 'bg-white border border-gray-100 text-gray-800 rounded-2xl rounded-bl-sm'
          }`}
        >
          {isUser ? (
            <p className="text-sm leading-relaxed whitespace-pre-wrap break-words">{message.content}</p>
          ) : (
            <div className="text-sm leading-relaxed prose prose-sm max-w-none prose-p:my-1 prose-headings:my-1.5 prose-ul:my-1 prose-ol:my-1 prose-li:my-0.5 prose-code:bg-gray-100 prose-code:text-indigo-600 prose-code:px-1 prose-code:py-0.5 prose-code:rounded prose-code:text-xs prose-pre:bg-gray-50 prose-pre:border prose-pre:border-gray-200 prose-pre:rounded-lg prose-table:text-xs prose-th:px-3 prose-th:py-1.5 prose-td:px-3 prose-td:py-1.5">
              <ReactMarkdown remarkPlugins={[remarkGfm]}>{displayContent}</ReactMarkdown>
            </div>
          )}

          {/* Rich card rendered below markdown for assistant messages */}
          {hasRichCard && (
            <RichCard toolCalls={message.toolCalls} content={message.content} />
          )}

          {/* Verification warnings */}
          {!isUser && message.verificationIssues && message.verificationIssues.length > 0 && (
            <VerificationBanner
              issues={message.verificationIssues}
              confidence={message.confidence}
            />
          )}
        </div>

        {/* Collapsible tool calls debug section */}
        {!isUser && message.toolCalls.length > 0 && (
          <details className="group px-1">
            <summary className="text-xs text-gray-400 cursor-pointer hover:text-indigo-500 transition-colors flex items-center gap-1 select-none">
              <svg className="w-3 h-3 transition-transform group-open:rotate-90" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M9 5l7 7-7 7" />
              </svg>
              {message.toolCalls.length} tool{message.toolCalls.length > 1 ? 's' : ''} called
            </summary>
            <div className="mt-1 flex flex-wrap gap-1">
              {message.toolCalls.map((tool) => (
                <span key={tool} className="inline-flex items-center gap-1 text-xs bg-gray-100 text-gray-600 px-2 py-0.5 rounded-full font-mono">
                  <span className="w-1.5 h-1.5 rounded-full bg-indigo-400" />
                  {tool}
                </span>
              ))}
            </div>
          </details>
        )}

        <span className="text-xs text-gray-400 px-1">{formatTime(message.timestamp)}</span>
      </div>
    </div>
  )
}
