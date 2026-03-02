import { useState } from 'react'
import type { AlertItem } from '../../types'

interface AlertsSectionProps {
  alerts: AlertItem[]
  onAlertClick?: (symbol: string) => void
}

export function AlertsSection({ alerts, onAlertClick }: AlertsSectionProps) {
  const [expanded, setExpanded] = useState(false)

  if (alerts.length === 0) return null

  // Sort: critical first, then warning
  const sorted = [...alerts].sort((a, b) => {
    if (a.severity === 'critical' && b.severity !== 'critical') return -1
    if (b.severity === 'critical' && a.severity !== 'critical') return 1
    return 0
  })

  const hasCritical = sorted.some(a => a.severity === 'critical')
  const visible = expanded ? sorted : sorted.slice(0, 3)
  const hiddenCount = sorted.length - 3

  return (
    <div className="rounded-2xl bg-amber-50/40 border border-amber-100 p-5 shadow-sm">
      {/* Header */}
      <div className="flex items-center gap-2 mb-3">
        <span className={`w-1.5 h-1.5 rounded-full animate-pulse ${hasCritical ? 'bg-red-400' : 'bg-amber-400'}`} />
        <p className="text-xs font-bold uppercase tracking-wider text-gray-500">
          Needs Attention
        </p>
        <span className="ml-auto text-[10px] font-medium text-gray-400">
          {alerts.length}
        </span>
      </div>

      {/* Alert rows */}
      <div>
        {visible.map((alert, index) => (
          <div key={`${alert.symbol}:${alert.condition}`}>
            <button
              onClick={() => onAlertClick?.(alert.symbol)}
              className="group w-full text-left py-2.5 pl-3 pr-2 rounded-lg hover:bg-white/60 transition-all duration-150 cursor-pointer relative"
            >
              {/* Left severity border */}
              <div className={`absolute left-0 top-1/2 -translate-y-1/2 w-[3px] h-3/5 rounded-full ${
                alert.severity === 'critical' ? 'bg-red-400' : 'bg-amber-400'
              }`} />

              <div className="flex items-center justify-between">
                <div className="flex-1 min-w-0 pr-2">
                  <span className="font-bold text-[13px] text-gray-900">{alert.symbol}</span>
                  <p className="text-xs text-gray-500 truncate mt-0.5">
                    {alert.message.replace(`${alert.symbol} `, '')}
                  </p>
                </div>
                {/* Chevron on hover */}
                <svg
                  className="w-3.5 h-3.5 text-gray-300 opacity-0 group-hover:opacity-100 transition-opacity duration-150 flex-shrink-0"
                  fill="none"
                  stroke="currentColor"
                  viewBox="0 0 24 24"
                >
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
                </svg>
              </div>
            </button>
            {index < visible.length - 1 && <div className="h-px bg-amber-100/60 mx-3" />}
          </div>
        ))}
      </div>

      {/* Overflow toggle */}
      {hiddenCount > 0 && !expanded && (
        <button
          onClick={() => setExpanded(true)}
          className="mt-2 text-xs text-amber-600 hover:text-amber-700 font-medium transition-colors cursor-pointer"
        >
          +{hiddenCount} more
        </button>
      )}
      {expanded && hiddenCount > 0 && (
        <button
          onClick={() => setExpanded(false)}
          className="mt-2 text-xs text-amber-600 hover:text-amber-700 font-medium transition-colors cursor-pointer"
        >
          Show less
        </button>
      )}
    </div>
  )
}
