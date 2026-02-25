# AgentForge Frontend UI Design

**Date:** 2026-02-24
**Status:** Approved
**Type:** Feature — Web UI Dashboard

## Summary

A chat-first web UI for AgentForge built with React (Vite) + Tailwind. The primary interface is a conversational chat panel with rich inline data cards, accompanied by a sidebar showing portfolio summary, allocation donut chart, and top holdings.

## Design Decisions

- **Chat-focused layout** — chat is the main interface, sidebar is secondary
- **React (Vite) + Tailwind** — fast dev, SPA, no SSR complexity
- **Friendly/modern style** — rounded corners, gradients, card-based (Robinhood/Coinbase vibes)
- **Rich cards in chat** — tool calls trigger inline data cards (tables, lists) alongside markdown text
- **No backend changes** — existing `/api/chat` endpoint and CORS config work as-is

## Architecture

```
AgentForge/
├── frontend/                     # New React SPA
│   ├── src/
│   │   ├── App.tsx
│   │   ├── main.tsx
│   │   ├── api/
│   │   │   └── chat.ts          # API client for POST /api/chat
│   │   ├── components/
│   │   │   ├── Chat/
│   │   │   │   ├── ChatPanel.tsx
│   │   │   │   ├── MessageBubble.tsx
│   │   │   │   ├── ChatInput.tsx
│   │   │   │   └── RichCard.tsx  # Holdings table, transactions, symbol info
│   │   │   └── Sidebar/
│   │   │       ├── Sidebar.tsx
│   │   │       ├── PortfolioValue.tsx
│   │   │       ├── AllocationChart.tsx
│   │   │       └── TopHoldings.tsx
│   │   ├── hooks/
│   │   │   ├── useChat.ts       # Chat state management
│   │   │   └── useSidebar.ts    # Sidebar data management
│   │   └── types/
│   │       └── index.ts
│   ├── index.html
│   ├── package.json
│   ├── vite.config.ts
│   └── tailwind.config.js
├── src/ghostfolio_agent/         # Existing backend (unchanged)
```

## Layout

```
┌──────────────────────────────────────────────────────┐
│  AgentForge                              [dark/light] │
├────────────────┬─────────────────────────────────────┤
│                │                                     │
│   SIDEBAR      │          CHAT PANEL                 │
│   (280px)      │                                     │
│                │  ┌─────────────────────────────┐    │
│  ┌──────────┐  │  │  Welcome! Ask me about      │    │
│  │ $124,532 │  │  │    your portfolio.           │    │
│  │ +2.4%    │  │  └─────────────────────────────┘    │
│  └──────────┘  │                                     │
│                │  ┌─────────────────────────────┐    │
│  ┌──────────┐  │  │  What's in my portfolio?     │    │
│  │  Donut   │  │  └─────────────────────────────┘    │
│  │  Chart   │  │                                     │
│  └──────────┘  │  ┌─────────────────────────────┐    │
│                │  │  Here's your portfolio:       │    │
│  Top Holdings  │  │ ┌─────────────────────────┐  │    │
│  AAPL  34.2%   │  │ │ AAPL   150 × $189  32%  │  │    │
│  VTI   28.1%   │  │ │ VTI    200 × $245  28%  │  │    │
│  NVDA  18.5%   │  │ │ NVDA    50 × $890  18%  │  │    │
│  BTC   12.0%   │  │ └─────────────────────────┘  │    │
│                │  │ Your portfolio is $124K...     │    │
│                │  └─────────────────────────────┘    │
│                │                                     │
│                │  ┌─────────────────────────────┐    │
│                │  │ Type a message...        >   │    │
│                │  └─────────────────────────────┘    │
└────────────────┴─────────────────────────────────────┘
```

Mobile: sidebar collapses to a top summary bar.

## Visual Style

- **Theme:** White background, blue/purple accents, green/red for gains/losses
- **Cards:** Rounded corners, subtle shadows, soft gradients
- **Typography:** Clean sans-serif, clear hierarchy
- **Interaction:** Smooth transitions, typing indicator during loading

## Rich Cards

The API returns `tool_calls` (list of tool names used). We use this to determine which rich card to render inline in the chat, alongside the markdown text response.

| tool_calls contains     | Card Rendered                                            |
|-------------------------|----------------------------------------------------------|
| `portfolio_summary`     | Holdings table (symbol, qty, price, value, allocation %) |
| `transaction_history`   | Transaction list (date, type badge, symbol, qty, price)  |
| `symbol_lookup`         | Symbol info card (ticker, name, asset class, currency)   |

**Parsing strategy (hybrid):**
- Always render agent text as markdown
- When `tool_calls` contains a known tool, render the matching rich card below the text
- Parse structured data from the agent's text using patterns (tables, lists)
- Sidebar refreshes automatically when `portfolio_summary` is called

## State Management

No external state library. Two custom hooks:

### `useChat`
```typescript
{
  messages: Array<{ role: 'user' | 'assistant', content: string, toolCalls: string[], timestamp: Date }>
  isLoading: boolean
  sessionId: string         // uuid, generated on mount
  sendMessage(text: string): Promise<void>
}
```

### `useSidebar`
```typescript
{
  portfolioValue: number
  dailyChange: { value: number, percent: number }
  holdings: Array<{ symbol: string, name: string, value: number, allocation: number }>
  isLoading: boolean
  refresh(): Promise<void>  // sends silent "Give me my portfolio summary" request
}
```

### Message flow
1. User types message -> appended as user bubble
2. `isLoading = true` -> typing indicator shown
3. `POST /api/chat` with message + sessionId
4. Response arrives -> render markdown text + check `tool_calls`
5. If `portfolio_summary` in tool_calls -> render holdings card + refresh sidebar
6. If `transaction_history` in tool_calls -> render transaction list card
7. If `symbol_lookup` in tool_calls -> render symbol info card

### Sidebar initialization
On mount, `useSidebar.refresh()` fires to populate dashboard. If it fails (no holdings), show empty state: "Add holdings in Ghostfolio to get started."

## Dependencies

| Library        | Purpose                      |
|----------------|------------------------------|
| react          | UI framework                 |
| react-dom      | DOM rendering                |
| tailwindcss    | Styling                      |
| recharts       | Donut chart in sidebar       |
| react-markdown | Render agent text responses  |
| uuid           | Generate session IDs         |

No router (single page), no state library, no component library.

## Dev Setup

```bash
cd frontend
npm install
npm run dev        # Vite dev server on localhost:5173
```

Vite proxy forwards `/api/*` to `localhost:8000`.

```bash
npm run build      # outputs to frontend/dist/
```

## Implementation Steps

1. Scaffold Vite + React + Tailwind project in `frontend/`
2. Set up Vite proxy config for API forwarding
3. Create types and API client (`api/chat.ts`)
4. Build `useChat` hook with message state and API integration
5. Build `ChatPanel`, `MessageBubble`, `ChatInput` components
6. Add markdown rendering for agent responses
7. Build `RichCard` component with holdings table, transaction list, symbol card variants
8. Wire rich cards to tool_calls detection
9. Build `useSidebar` hook with auto-refresh
10. Build `Sidebar`, `PortfolioValue`, `AllocationChart`, `TopHoldings` components
11. Compose full layout in `App.tsx` with responsive design
12. Add loading states, empty states, error handling
13. Polish: transitions, dark/light toggle, mobile responsive
