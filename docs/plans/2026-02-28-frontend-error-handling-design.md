# Frontend Error Handling — Design Doc

**Date:** 2026-02-28
**Status:** Approved

## Problem

The frontend has gaps in error handling:
1. `ChatResponse` type is missing 4 fields the backend sends (`verification_issues`, `verification_details`, `tool_outputs`, `citations`)
2. All network/fetch errors show a generic "Sorry, something went wrong" message
3. Sidebar and model selector fail silently — user sees empty state with no explanation
4. No display of verification warnings or confidence metadata

## Design

### 1. Type Sync & ChatMessage Updates

Sync frontend `ChatResponse` with backend model and extend `ChatMessage` to carry metadata.

**`types/index.ts`:**
- Add to `ChatResponse`: `tool_outputs: string[]`, `confidence: string`, `citations: Citation[]`, `verification_issues: string[]`, `verification_details: Record<string, string>`
- Add `Citation` interface: `{ claim: string, tool_name: string, source_detail: string }`
- Add to `ChatMessage`: `confidence?: string`, `verificationIssues?: string[]`, `isError?: boolean`

**`hooks/useChat.ts`:**
- Pass `confidence` and `verificationIssues` from response into assistant `ChatMessage`
- On catch, set `isError: true` with category-specific message (see section 2)

### 2. Network Error Categorization

New `ChatError` class in `api/chat.ts` with three categories:

```typescript
export type ChatErrorType = 'timeout' | 'network' | 'server'

export class ChatError extends Error {
  type: ChatErrorType
  constructor(type: ChatErrorType, message: string) {
    super(message)
    this.type = type
  }
}
```

Classification logic in `postChat` and `fetchPaperPortfolio`:
- `response.status >= 500` → `server`: "Our servers are having trouble. Please try again in a moment."
- `response.status === 408` or `AbortError`/`TimeoutError` → `timeout`: "That took too long. Try a simpler question or try again."
- `TypeError` from fetch (network failure) → `network`: "Couldn't reach the server. Check your connection and try again."
- Other non-ok responses → `server` with same message

In `useChat` catch block: check `instanceof ChatError`, use `error.message` as content with `isError: true`. Fallback to generic message for unknown errors.

### 3. Verification Warning Banner

New `VerificationBanner` component rendered below assistant message bubble.

**Behavior:**
- Only renders when `verificationIssues` has items
- Yellow bar for `confidence: "medium"`, red for `confidence: "low"`
- Collapsed by default — shows issue count
- Click to expand and see individual issues as a list
- `confidence: "high"` with no issues → nothing renders

**Layout:** Appended inside the message bubble component, below content. No layout changes.

### 4. Sidebar & Model Selector Error States

**`hooks/useSidebar.ts`:**
- Add `error: string | null` state
- On catch: set `error` to category message (reuse `ChatError` categories), keep holdings empty
- On success: clear `error`
- Return `error` from hook

**Sidebar UI:**
- When `error` is set and `holdings` is empty: show "Failed to load portfolio" + "Retry" link that calls `refresh()`
- Successful refresh clears error and renders holdings normally

**`components/Chat/ModelSelector.tsx`:**
- Add error state for `/api/models` fetch failure
- Show "Couldn't load models" inline instead of empty dropdown

## Files Changed

- `frontend/src/types/index.ts` — Add missing fields, `Citation` interface, `ChatMessage` extensions
- `frontend/src/api/chat.ts` — `ChatError` class, categorized error throwing
- `frontend/src/hooks/useChat.ts` — Pass metadata to messages, typed error handling
- `frontend/src/hooks/useSidebar.ts` — Add error state, return it
- `frontend/src/components/Chat/MessageBubble.tsx` (or equivalent) — Render `VerificationBanner`
- `frontend/src/components/VerificationBanner.tsx` — New component
- `frontend/src/components/Sidebar/` — Error state UI + retry
- `frontend/src/components/Chat/ModelSelector.tsx` — Error state for model fetch
- `frontend/tests/` — Unit tests for `ChatError`, `VerificationBanner`

## Non-Goals

- No toast/notification system — errors are contextual (inline in chat, sidebar)
- No React error boundary — out of scope for this change
- No retry logic for chat messages — user can resend manually
- No changes to backend error handling — it already handles errors gracefully
