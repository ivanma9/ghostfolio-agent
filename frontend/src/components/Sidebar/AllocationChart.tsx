import { PieChart, Pie, Cell, Tooltip, ResponsiveContainer } from 'recharts';
import type { Holding } from '../../types';

interface AllocationChartProps {
  holdings: Holding[];
}

const COLORS = [
  '#6366f1',
  '#8b5cf6',
  '#06b6d4',
  '#10b981',
  '#f59e0b',
  '#ef4444',
  '#ec4899',
  '#64748b',
];

interface TooltipPayloadEntry {
  name: string;
  value: number;
}

interface CustomTooltipProps {
  active?: boolean;
  payload?: TooltipPayloadEntry[];
}

function CustomTooltip({ active, payload }: CustomTooltipProps) {
  if (active && payload && payload.length) {
    return (
      <div className="bg-white border border-gray-100 rounded-lg shadow-lg px-3 py-2 text-xs">
        <p className="font-semibold text-gray-700">{payload[0].name}</p>
        <p className="text-indigo-600">{payload[0].value.toFixed(1)}%</p>
      </div>
    );
  }
  return null;
}

export function AllocationChart({ holdings }: AllocationChartProps) {
  if (!holdings || holdings.length === 0) {
    return (
      <div className="rounded-2xl bg-white border border-gray-100 p-5 shadow-sm">
        <p className="text-xs font-semibold uppercase tracking-wider text-gray-400 mb-4">
          Allocation
        </p>
        <div className="flex flex-col items-center justify-center py-8 text-gray-300">
          <svg className="w-12 h-12 mb-2" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M11 3.055A9.001 9.001 0 1020.945 13H11V3.055z" />
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M20.488 9H15V3.512A9.025 9.025 0 0120.488 9z" />
          </svg>
          <p className="text-sm">No holdings yet</p>
        </div>
      </div>
    );
  }

  const data = holdings.map((h) => ({
    name: h.symbol,
    value: h.allocation,
  }));

  const holdingCount = holdings.length;

  return (
    <div className="rounded-2xl bg-white border border-gray-100 p-5 shadow-sm">
      <p className="text-xs font-semibold uppercase tracking-wider text-gray-400 mb-4">
        Allocation
      </p>

      <div className="relative">
        <ResponsiveContainer width="100%" height={160}>
          <PieChart>
            <Pie
              data={data}
              dataKey="value"
              nameKey="name"
              cx="50%"
              cy="50%"
              innerRadius={50}
              outerRadius={75}
              paddingAngle={2}
              strokeWidth={0}
            >
              {data.map((_, index) => (
                <Cell key={`cell-${index}`} fill={COLORS[index % COLORS.length]} />
              ))}
            </Pie>
            <Tooltip content={<CustomTooltip />} />
          </PieChart>
        </ResponsiveContainer>

        <div className="absolute inset-0 flex flex-col items-center justify-center pointer-events-none">
          <span className="text-2xl font-bold text-gray-800">{holdingCount}</span>
          <span className="text-xs text-gray-400">{holdingCount === 1 ? 'holding' : 'holdings'}</span>
        </div>
      </div>

      <div className="mt-4 space-y-1.5">
        {holdings.slice(0, 6).map((holding, index) => (
          <div key={holding.symbol} className="flex items-center justify-between text-xs">
            <div className="flex items-center gap-2">
              <span
                className="w-2.5 h-2.5 rounded-full flex-shrink-0"
                style={{ backgroundColor: COLORS[index % COLORS.length] }}
              />
              <span className="font-semibold text-gray-700">{holding.symbol}</span>
            </div>
            <span className="text-gray-500">{holding.allocation.toFixed(1)}%</span>
          </div>
        ))}
        {holdings.length > 6 && (
          <p className="text-xs text-gray-400 pt-1">+{holdings.length - 6} more</p>
        )}
      </div>
    </div>
  );
}
