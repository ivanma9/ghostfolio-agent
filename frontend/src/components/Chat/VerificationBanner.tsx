import { useState } from 'react'

interface VerificationBannerProps {
  issues: string[]
  confidence?: string
}

export default function VerificationBanner({ issues, confidence }: VerificationBannerProps) {
  const [isExpanded, setIsExpanded] = useState(false)

  if (issues.length === 0) return null

  const isLow = confidence === 'low'
  const barColor = isLow
    ? 'bg-red-50 border-red-200 text-red-700'
    : 'bg-amber-50 border-amber-200 text-amber-700'
  const dotColor = isLow ? 'bg-red-400' : 'bg-amber-400'

  return (
    <div className={`mt-2 rounded-lg border text-xs ${barColor}`}>
      <button
        onClick={() => setIsExpanded(!isExpanded)}
        className="w-full flex items-center justify-between px-3 py-2 cursor-pointer hover:opacity-80 transition-opacity"
      >
        <span className="flex items-center gap-1.5">
          <span className={`w-1.5 h-1.5 rounded-full ${dotColor}`} />
          {issues.length} verification issue{issues.length > 1 ? 's' : ''}
        </span>
        <svg
          className={`w-3 h-3 transition-transform ${isExpanded ? 'rotate-180' : ''}`}
          fill="none"
          viewBox="0 0 24 24"
          stroke="currentColor"
          strokeWidth={2}
        >
          <path strokeLinecap="round" strokeLinejoin="round" d="m19.5 8.25-7.5 7.5-7.5-7.5" />
        </svg>
      </button>
      {isExpanded && (
        <ul className="px-3 pb-2 space-y-1">
          {issues.map((issue, i) => (
            <li key={i} className="flex items-start gap-1.5">
              <span className="mt-1.5 w-1 h-1 rounded-full bg-current flex-shrink-0" />
              {issue}
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}
