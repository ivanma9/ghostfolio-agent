import type { Holding, AlertItem } from '../../types';
import { PortfolioValue } from './PortfolioValue';
import { AllocationChart } from './AllocationChart';
import { TopHoldings } from './TopHoldings';
import { AlertsSection } from './AlertsSection';

interface SidebarProps {
  holdings: Holding[];
  portfolioValue: number;
  dailyChange: { value: number; percent: number };
  isLoading: boolean;
  isPaperTrading?: boolean;
  isGuest?: boolean;
  error?: string | null;
  onRetry?: () => void;
  alerts?: AlertItem[];
  onHoldingClick?: (symbol: string) => void;
  onLogout?: () => void;
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

export function Sidebar({ holdings, portfolioValue, dailyChange, isLoading, isPaperTrading = false, isGuest = false, error, onRetry, alerts = [], onHoldingClick, onLogout }: SidebarProps) {
  return (
    <aside className="w-72 h-full border-r border-gray-100 bg-white overflow-y-auto flex-shrink-0">
      <div className="p-5 space-y-6">
        {/* Logo / Title */}
        <div className="flex items-center gap-2.5 py-1">
          <div className={`w-8 h-8 rounded-xl flex items-center justify-center shadow-sm bg-gradient-to-br ${isPaperTrading ? 'from-amber-400 to-orange-500' : 'from-indigo-500 to-violet-600'}`}>
            <ChartIcon />
          </div>
          <div>
            <h1 className="text-base font-bold text-gray-900 leading-none tracking-tight">
              AgentForge
            </h1>
            <p className="text-xs text-gray-400 mt-0.5">
              {isPaperTrading ? 'Paper Portfolio' : 'AI Portfolio Assistant'}
            </p>
          </div>
          {isPaperTrading && (
            <span className="ml-auto px-2 py-0.5 text-[10px] font-bold uppercase tracking-wider rounded-full bg-amber-100 text-amber-700 border border-amber-200">
              Paper Mode
            </span>
          )}
        </div>

        {/* Portfolio Value */}
        <section>
          <PortfolioValue
            value={portfolioValue}
            dailyChange={dailyChange}
            isLoading={isLoading}
            isPaperTrading={isPaperTrading}
          />
        </section>

        {/* Error state */}
        {error && holdings.length === 0 && !isLoading && (
          <section className="text-center py-4">
            <p className="text-sm text-red-600">{error}</p>
            {onRetry && (
              <button
                onClick={onRetry}
                className="mt-2 text-xs text-indigo-500 hover:text-indigo-700 font-medium transition-colors"
              >
                Retry
              </button>
            )}
          </section>
        )}

        {/* Alerts Section */}
        <section>
          <AlertsSection alerts={alerts} onAlertClick={onHoldingClick} />
        </section>

        {/* Allocation Chart */}
        <section>
          <AllocationChart holdings={holdings} onHoldingClick={onHoldingClick} />
        </section>

        {/* Top Holdings */}
        <section>
          <TopHoldings holdings={holdings} onHoldingClick={onHoldingClick} />
        </section>

        {/* Guest CTA to connect portfolio */}
        {isGuest && (
          <section className="bg-indigo-50/60 rounded-xl p-4 border border-indigo-100">
            <p className="text-sm text-indigo-900 font-medium">Connect your portfolio</p>
            <p className="text-xs text-indigo-600/70 mt-1">
              Sign in with your Ghostfolio token to view your real portfolio and get personalized insights.
            </p>
            <button
              onClick={onLogout}
              className="mt-3 w-full text-xs font-medium text-indigo-600 hover:text-indigo-800 bg-white hover:bg-indigo-50 border border-indigo-200 rounded-lg py-1.5 transition-colors"
            >
              Sign in with token
            </button>
          </section>
        )}

        {/* Footer */}
        <section className="pt-4 border-t border-slate-100">
          <button
            onClick={onLogout}
            className="w-full text-xs text-slate-400 hover:text-slate-600 transition-colors py-1"
          >
            {isGuest ? 'Exit Guest Mode' : 'Sign Out'}
          </button>
        </section>
      </div>
    </aside>
  );
}
