interface PaperTradeToggleProps {
  isActive: boolean
  onChange: (active: boolean) => void
}

export default function PaperTradeToggle({ isActive, onChange }: PaperTradeToggleProps) {
  return (
    <button
      onClick={() => onChange(!isActive)}
      className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium transition-all shadow-sm ${
        isActive
          ? 'bg-amber-50 border border-amber-300 text-amber-700 hover:bg-amber-100'
          : 'bg-white border border-gray-200 text-gray-700 hover:bg-gray-50 hover:border-gray-300'
      }`}
    >
      <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
        <path strokeLinecap="round" strokeLinejoin="round" d="M9.75 3.104v5.714a2.25 2.25 0 0 1-.659 1.591L5 14.5m14.8.8 1.402 1.402c1.232 1.232.65 3.318-1.067 3.611A48.309 48.309 0 0 1 12 21a48.309 48.309 0 0 1-8.135-.687c-1.718-.293-2.3-2.379-1.067-3.61L5 14.5m0 0 4.091-4.091a2.25 2.25 0 0 0 .659-1.591V3.104m0 0A2.25 2.25 0 0 1 12 1.5a2.25 2.25 0 0 1 2.25 1.604M14.25 3.104v5.714a2.25 2.25 0 0 0 .659 1.591L19.8 15.3" />
      </svg>
      <span>Paper</span>
    </button>
  )
}
