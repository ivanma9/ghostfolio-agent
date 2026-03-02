import type { Holding } from '../../types';

interface TopHoldingsProps {
  holdings: Holding[];
  onHoldingClick?: (symbol: string) => void;
}

function formatCurrency(value: number): string {
  return new Intl.NumberFormat('en-US', {
    style: 'currency',
    currency: 'USD',
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  }).format(value);
}

export function TopHoldings({ holdings, onHoldingClick }: TopHoldingsProps) {
  const top5 = [...(holdings || [])]
    .sort((a, b) => b.value - a.value)
    .slice(0, 5);

  return (
    <div className="rounded-2xl bg-white border border-gray-100 p-5 shadow-sm">
      <p className="text-xs font-semibold uppercase tracking-wider text-gray-400 mb-4">
        Top Holdings
      </p>

      {top5.length === 0 ? (
        <p className="text-sm text-gray-400 py-4 text-center">No holdings yet</p>
      ) : (
        <div className="space-y-0">
          {top5.map((holding, index) => (
            <div key={holding.symbol}>
              <button
                onClick={() => onHoldingClick?.(holding.symbol)}
                className="group w-full text-left py-3 pl-2 pr-1 rounded-lg border-l-2 border-transparent hover:bg-slate-50/60 hover:border-indigo-400 transition-all duration-150 ease-out cursor-pointer"
              >
                <div className="flex items-start justify-between mb-1.5">
                  <div className="flex-1 min-w-0 pr-3">
                    <span className="font-bold text-sm text-gray-900 group-hover:text-indigo-600 transition-colors duration-150">{holding.symbol}</span>
                    <p className="text-xs text-gray-400 truncate mt-0.5">{holding.name}</p>
                  </div>
                  <div className="flex items-center gap-1">
                    <div className="text-right flex-shrink-0">
                      <p className="text-sm font-semibold text-gray-900">
                        {formatCurrency(holding.value)}
                      </p>
                      <p className="text-xs text-indigo-500 font-medium">
                        {holding.allocation.toFixed(1)}%
                      </p>
                    </div>
                    <svg
                      className="w-3.5 h-3.5 text-gray-300 opacity-0 group-hover:opacity-100 transition-opacity duration-150 flex-shrink-0"
                      fill="none"
                      stroke="currentColor"
                      viewBox="0 0 24 24"
                    >
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
                    </svg>
                  </div>
                </div>

                <div className="w-full bg-gray-100 rounded-full h-1.5 overflow-hidden">
                  <div
                    className="h-full rounded-full"
                    style={{
                      width: `${Math.min(holding.allocation, 100)}%`,
                      background: 'linear-gradient(to right, #6366f1, #8b5cf6)',
                    }}
                  />
                </div>
              </button>

              {index < top5.length - 1 && (
                <div className="h-px bg-gray-50" />
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
