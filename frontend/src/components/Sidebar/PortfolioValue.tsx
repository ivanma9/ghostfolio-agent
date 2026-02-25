interface PortfolioValueProps {
  value: number;
  dailyChange: { value: number; percent: number };
  isLoading: boolean;
}

function formatCurrency(value: number): string {
  return new Intl.NumberFormat('en-US', {
    style: 'currency',
    currency: 'USD',
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  }).format(value);
}

export function PortfolioValue({ value, dailyChange, isLoading }: PortfolioValueProps) {
  const isPositive = dailyChange.value >= 0;

  if (isLoading) {
    return (
      <div className="rounded-2xl bg-gradient-to-br from-indigo-50 to-white p-5 animate-pulse">
        <div className="h-3 w-24 bg-gray-200 rounded mb-3" />
        <div className="h-8 w-40 bg-gray-200 rounded mb-3" />
        <div className="h-4 w-32 bg-gray-200 rounded" />
      </div>
    );
  }

  const changeSign = isPositive ? '+' : '';
  const changeColor = isPositive ? 'text-emerald-500' : 'text-red-500';
  const arrow = isPositive ? '▲' : '▼';

  return (
    <div className="rounded-2xl bg-gradient-to-br from-indigo-50 to-white p-5 shadow-sm">
      <p className="text-xs font-semibold uppercase tracking-wider text-gray-400 mb-1">
        Portfolio Value
      </p>
      <p className="text-3xl font-bold text-gray-900 tracking-tight">
        {formatCurrency(value)}
      </p>
      <p className={`mt-2 text-sm font-semibold flex items-center gap-1 ${changeColor}`}>
        <span>{arrow}</span>
        <span>
          {changeSign}{formatCurrency(dailyChange.value)} ({changeSign}{dailyChange.percent.toFixed(2)}%)
        </span>
      </p>
      <p className="text-xs text-gray-400 mt-0.5">Today</p>
    </div>
  );
}
