import type { Holding } from '../../types';

interface TopHoldingsProps {
  holdings: Holding[];
}

function formatCurrency(value: number): string {
  return new Intl.NumberFormat('en-US', {
    style: 'currency',
    currency: 'USD',
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  }).format(value);
}

export function TopHoldings({ holdings }: TopHoldingsProps) {
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
              <div className="py-3">
                <div className="flex items-start justify-between mb-1.5">
                  <div className="flex-1 min-w-0 pr-3">
                    <span className="font-bold text-sm text-gray-900">{holding.symbol}</span>
                    <p className="text-xs text-gray-400 truncate mt-0.5">{holding.name}</p>
                  </div>
                  <div className="text-right flex-shrink-0">
                    <p className="text-sm font-semibold text-gray-900">
                      {formatCurrency(holding.value)}
                    </p>
                    <p className="text-xs text-indigo-500 font-medium">
                      {holding.allocation.toFixed(1)}%
                    </p>
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
              </div>

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
