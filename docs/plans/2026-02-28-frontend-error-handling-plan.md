# Frontend Error Handling Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Surface backend verification metadata in the chat UI, categorize network errors with specific messages, and add error states to sidebar and model selector.

**Architecture:** Sync frontend `ChatResponse` type with backend, add `ChatError` class for categorized fetch failures, extend `ChatMessage` with metadata fields, create `VerificationBanner` component, and add error+retry states to sidebar/model selector.

**Tech Stack:** React 19, TypeScript, Tailwind CSS 4, Vite 7. No frontend test framework — verify via `tsc -b` (type checking) and `vite build`.

---

### Task 1: Sync ChatResponse type and extend ChatMessage

**Files:**
- Modify: `frontend/src/types/index.ts`

**Step 1: Add Citation interface and update ChatResponse**

Add `Citation` interface and the 4 missing fields to `ChatResponse`:

```typescript
export interface Citation {
  claim: string
  tool_name: string
  source_detail: string
}

export interface ChatResponse {
  response: string
  session_id: string
  tool_calls: string[]
  tool_outputs: string[]
  confidence: string
  citations: Citation[]
  verification_issues: string[]
  verification_details: Record<string, string>
}
```

**Step 2: Extend ChatMessage with metadata fields**

Add optional fields to `ChatMessage`:

```typescript
export interface ChatMessage {
  id: string
  role: 'user' | 'assistant'
  content: string
  toolCalls: string[]
  timestamp: Date
  confidence?: string
  verificationIssues?: string[]
  isError?: boolean
}
```

**Step 3: Verify types compile**

Run: `cd frontend && npx tsc -b --noEmit`
Expected: No errors

**Step 4: Commit**

```bash
git add frontend/src/types/index.ts
git commit -m "feat(frontend): sync ChatResponse type with backend, extend ChatMessage"
```

---

### Task 2: Add ChatError class with categorized errors

**Files:**
- Modify: `frontend/src/api/chat.ts`

**Step 1: Add ChatError class and update postChat**

Add error class at the top and update both functions:

```typescript
export type ChatErrorType = 'timeout' | 'network' | 'server'

const ERROR_MESSAGES: Record<ChatErrorType, string> = {
  timeout: 'That took too long. Try a simpler question or try again.',
  network: "Couldn't reach the server. Check your connection and try again.",
  server: 'Our servers are having trouble. Please try again in a moment.',
}

export class ChatError extends Error {
  type: ChatErrorType
  constructor(type: ChatErrorType) {
    super(ERROR_MESSAGES[type])
    this.type = type
  }
}
```

**Step 2: Update postChat to throw ChatError**

Replace the existing `postChat` function:

```typescript
export async function postChat(request: ChatRequest): Promise<ChatResponse> {
  let response: Response
  try {
    response = await fetch('/api/chat', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(request),
    })
  } catch (err) {
    if (err instanceof TypeError) {
      throw new ChatError('network')
    }
    if (err instanceof DOMException && err.name === 'AbortError') {
      throw new ChatError('timeout')
    }
    throw new ChatError('network')
  }

  if (!response.ok) {
    if (response.status === 408) {
      throw new ChatError('timeout')
    }
    throw new ChatError('server')
  }

  return response.json() as Promise<ChatResponse>
}
```

**Step 3: Update fetchPaperPortfolio to throw ChatError**

Replace the existing `fetchPaperPortfolio` error handling:

```typescript
export async function fetchPaperPortfolio(): Promise<import('../types').PaperPortfolio> {
  let response: Response
  try {
    response = await fetch('/api/paper-portfolio')
  } catch (err) {
    if (err instanceof TypeError) {
      throw new ChatError('network')
    }
    throw new ChatError('network')
  }

  if (!response.ok) {
    throw new ChatError('server')
  }

  const data = await response.json()
  return {
    cash: data.cash,
    totalValue: data.total_value,
    totalPnl: data.total_pnl,
    totalPnlPercent: data.total_pnl_percent,
    positions: (data.positions || []).map((p: Record<string, unknown>) => ({
      symbol: p.symbol,
      quantity: p.quantity,
      avgCost: p.avg_cost,
      currentPrice: p.current_price,
      value: p.value,
      pnl: p.pnl,
      pnlPercent: p.pnl_percent,
      allocation: p.allocation,
    })),
  }
}
```

**Step 4: Verify types compile**

Run: `cd frontend && npx tsc -b --noEmit`
Expected: No errors

**Step 5: Commit**

```bash
git add frontend/src/api/chat.ts
git commit -m "feat(frontend): add ChatError class with categorized error messages"
```

---

### Task 3: Update useChat to pass metadata and handle ChatError

**Files:**
- Modify: `frontend/src/hooks/useChat.ts`

**Step 1: Update useChat to pass verification metadata and use ChatError**

Import `ChatError` and update the sendMessage function:

```typescript
import { postChat, ChatError } from '../api/chat'
```

In the try block, update the assistant message creation to include metadata:

```typescript
const assistantMessage: ChatMessage = {
  id: uuidv4(),
  role: 'assistant',
  content: data.response,
  toolCalls: data.tool_calls ?? [],
  timestamp: new Date(),
  confidence: data.confidence,
  verificationIssues: data.verification_issues,
}
```

Update the catch block to use ChatError:

```typescript
catch (error) {
  const content = error instanceof ChatError
    ? error.message
    : 'Sorry, something went wrong. Please try again.'
  const errorMessage: ChatMessage = {
    id: uuidv4(),
    role: 'assistant',
    content,
    toolCalls: [],
    timestamp: new Date(),
    isError: true,
  }
  setMessages((prev) => [...prev, errorMessage])
  console.error('Chat error:', error)
}
```

**Step 2: Verify types compile**

Run: `cd frontend && npx tsc -b --noEmit`
Expected: No errors

**Step 3: Commit**

```bash
git add frontend/src/hooks/useChat.ts
git commit -m "feat(frontend): pass verification metadata to messages, use ChatError"
```

---

### Task 4: Create VerificationBanner component

**Files:**
- Create: `frontend/src/components/Chat/VerificationBanner.tsx`

**Step 1: Create the component**

```tsx
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
```

**Step 2: Verify types compile**

Run: `cd frontend && npx tsc -b --noEmit`
Expected: No errors

**Step 3: Commit**

```bash
git add frontend/src/components/Chat/VerificationBanner.tsx
git commit -m "feat(frontend): add VerificationBanner component"
```

---

### Task 5: Integrate VerificationBanner and error styling into MessageBubble

**Files:**
- Modify: `frontend/src/components/Chat/MessageBubble.tsx`

**Step 1: Import VerificationBanner and add error styling**

Add import at the top:

```typescript
import VerificationBanner from './VerificationBanner'
```

In the assistant message bubble `<div>`, after the `{hasRichCard && ...}` block and before the closing `</div>` of the bubble, add:

```tsx
{/* Verification warnings */}
{!isUser && message.verificationIssues && message.verificationIssues.length > 0 && (
  <VerificationBanner
    issues={message.verificationIssues}
    confidence={message.confidence}
  />
)}
```

**Step 2: Add error message styling**

Update the assistant bubble's outer `<div>` className to conditionally style error messages. Replace the existing className logic:

```tsx
<div
  className={`px-4 py-3 shadow-sm ${
    isUser
      ? 'bg-gradient-to-br from-indigo-500 to-violet-500 text-white rounded-2xl rounded-br-sm'
      : message.isError
        ? 'bg-red-50 border border-red-200 text-red-700 rounded-2xl rounded-bl-sm'
        : 'bg-white border border-gray-100 text-gray-800 rounded-2xl rounded-bl-sm'
  }`}
>
```

**Step 3: Verify types compile**

Run: `cd frontend && npx tsc -b --noEmit`
Expected: No errors

**Step 4: Commit**

```bash
git add frontend/src/components/Chat/MessageBubble.tsx
git commit -m "feat(frontend): render VerificationBanner and error styling in MessageBubble"
```

---

### Task 6: Add error state to useSidebar

**Files:**
- Modify: `frontend/src/hooks/useSidebar.ts`

**Step 1: Add error state and update return type**

Import `ChatError`:

```typescript
import { postChat, fetchPaperPortfolio, ChatError } from '../api/chat'
```

Update the interface:

```typescript
interface UseSidebarReturn {
  holdings: Holding[]
  portfolioValue: number
  dailyChange: DailyChange
  isLoading: boolean
  error: string | null
  refresh: () => Promise<void>
}
```

Add error state:

```typescript
const [error, setError] = useState<string | null>(null)
```

In the `refresh` callback, add `setError(null)` at the top of the try block, and update the catch:

```typescript
} catch (error) {
  const message = error instanceof ChatError
    ? error.message
    : 'Failed to load portfolio'
  console.error('Sidebar refresh error:', error)
  setError(message)
  setHoldings([])
  setPortfolioValue(0)
  setDailyChange({ value: 0, percent: 0 })
}
```

Update the return:

```typescript
return { holdings, portfolioValue, dailyChange, isLoading, error, refresh }
```

**Step 2: Verify types compile**

Run: `cd frontend && npx tsc -b --noEmit`
Expected: No errors

**Step 3: Commit**

```bash
git add frontend/src/hooks/useSidebar.ts
git commit -m "feat(frontend): add error state to useSidebar"
```

---

### Task 7: Render sidebar error state in Sidebar component

**Files:**
- Modify: `frontend/src/components/Sidebar/Sidebar.tsx`
- Modify: `frontend/src/App.tsx`

**Step 1: Add error and onRetry props to Sidebar**

Update `SidebarProps`:

```typescript
interface SidebarProps {
  holdings: Holding[];
  portfolioValue: number;
  dailyChange: { value: number; percent: number };
  isLoading: boolean;
  isPaperTrading?: boolean;
  error?: string | null;
  onRetry?: () => void;
}
```

Update the function signature to destructure the new props:

```typescript
export function Sidebar({ holdings, portfolioValue, dailyChange, isLoading, isPaperTrading = false, error, onRetry }: SidebarProps) {
```

After the `<PortfolioValue>` section and before the `<AllocationChart>` section, add error display:

```tsx
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
```

**Step 2: Pass error and onRetry from App.tsx**

In `App.tsx`, update the `<Sidebar>` usage to pass the new props:

```tsx
<Sidebar
  holdings={sidebar.holdings}
  portfolioValue={sidebar.portfolioValue}
  dailyChange={sidebar.dailyChange}
  isLoading={sidebar.isLoading}
  isPaperTrading={isPaperTrading}
  error={sidebar.error}
  onRetry={sidebar.refresh}
/>
```

**Step 3: Verify types compile**

Run: `cd frontend && npx tsc -b --noEmit`
Expected: No errors

**Step 4: Commit**

```bash
git add frontend/src/components/Sidebar/Sidebar.tsx frontend/src/App.tsx
git commit -m "feat(frontend): render sidebar error state with retry button"
```

---

### Task 8: Add error state to ModelSelector

**Files:**
- Modify: `frontend/src/components/Chat/ModelSelector.tsx`

**Step 1: Add error state and update fetch logic**

Add error state:

```typescript
const [error, setError] = useState<string | null>(null)
```

Replace the `useEffect` fetch with error handling:

```typescript
useEffect(() => {
  fetch('/api/models')
    .then((res) => {
      if (!res.ok) throw new Error('Failed to load')
      return res.json()
    })
    .then((data) => {
      setModels(data.models)
      setError(null)
      if (!selectedModel && data.default) {
        onModelChange(data.default)
      }
    })
    .catch((err) => {
      console.error('Model fetch error:', err)
      setError("Couldn't load models")
    })
}, [])
```

**Step 2: Show error in the button when models fail to load**

Update the button label to show error state. Replace `{selected?.name ?? 'Select model'}` with:

```tsx
<span className={error ? 'text-red-500' : ''}>
  {error ?? selected?.name ?? 'Select model'}
</span>
```

**Step 3: Verify types compile**

Run: `cd frontend && npx tsc -b --noEmit`
Expected: No errors

**Step 4: Commit**

```bash
git add frontend/src/components/Chat/ModelSelector.tsx
git commit -m "feat(frontend): add error state to ModelSelector"
```

---

### Task 9: Full build verification

**Files:** None (verification only)

**Step 1: Run full TypeScript + Vite build**

Run: `cd frontend && npm run build`
Expected: Build completes with no errors

**Step 2: Verify no lint errors**

Run: `cd frontend && npm run lint`
Expected: No errors (or only pre-existing warnings)

**Step 3: Run backend tests to ensure no regressions**

Run: `cd /Users/ivanma/Desktop/gauntlet/AgentForge && uv run pytest tests/unit/ -v`
Expected: All tests pass (frontend changes don't affect backend tests, but verify nothing broke)
