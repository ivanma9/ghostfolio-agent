import type { Holding } from '../../types';
import { PortfolioValue } from './PortfolioValue';
import { AllocationChart } from './AllocationChart';
import { TopHoldings } from './TopHoldings';

interface SidebarProps {
  holdings: Holding[];
  portfolioValue: number;
  dailyChange: { value: number; percent: number };
  isLoading: boolean;
}

function ChartIcon() {
  return (
    <svg
      className="w-5 h-5 text-indigo-500"
      fill="none"
      stroke="currentColor"
      viewBox="0 0 24 24"
      strokeWidth={2}
    >
      <path
        strokeLinecap="round"
        strokeLinejoin="round"
        d="M7 12l3-3 3 3 4-4M8 21l4-4 4 4M3 4h18M4 4h16v12a1 1 0 01-1 1H5a1 1 0 01-1-1V4z"
      />
    </svg>
  );
}

export function Sidebar({ holdings, portfolioValue, dailyChange, isLoading }: SidebarProps) {
  return (
    <aside className="w-72 h-full border-r border-gray-100 bg-white overflow-y-auto flex-shrink-0">
      <div className="p-5 space-y-6">
        {/* Logo / Title */}
        <div className="flex items-center gap-2.5 py-1">
          <div className="w-8 h-8 rounded-xl bg-gradient-to-br from-indigo-500 to-violet-600 flex items-center justify-center shadow-sm">
            <ChartIcon />
          </div>
          <div>
            <h1 className="text-base font-bold text-gray-900 leading-none tracking-tight">
              AgentForge
            </h1>
            <p className="text-xs text-gray-400 mt-0.5">AI Portfolio Assistant</p>
          </div>
        </div>

        {/* Portfolio Value */}
        <section>
          <PortfolioValue
            value={portfolioValue}
            dailyChange={dailyChange}
            isLoading={isLoading}
          />
        </section>

        {/* Allocation Chart */}
        <section>
          <AllocationChart holdings={holdings} />
        </section>

        {/* Top Holdings */}
        <section>
          <TopHoldings holdings={holdings} />
        </section>
      </div>
    </aside>
  );
}
