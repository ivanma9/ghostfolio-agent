# Command Palette Design

**Date:** 2026-03-01
**Status:** Design approved

## Problem

Users don't know what the system can do. 12+ capabilities are hidden behind a blank chat input with only 3 suggested queries on the welcome screen. New users don't know they can ask for conviction scores, risk analysis, congressional activity, etc.

## Solution

A persistent command palette accessible via a "+" button in the chat input bar and "/" keyboard shortcut. Categorized menu of all capabilities, always one click away.

## Design

### Trigger

- **"+" button** in the `leftSlot` of ChatInput, before ModelSelector and PaperTradeToggle
- **"/" shortcut** when input is empty: prevents default, opens palette with filter mode
- If input already has text, "/" types normally

### Popover

- Opens upward from the "+" button
- `bg-white border border-gray-200 rounded-xl shadow-lg`
- Width: `w-72` (matches sidebar width)
- Max height: `max-h-96 overflow-y-auto`
- Closes on: item click, click outside, Escape

### Categories and Items

**Portfolio** (5 items — send immediately)
| Label | Description | Message |
|-------|-------------|---------|
| Morning Briefing | Daily portfolio overview | "Morning briefing" |
| Portfolio Overview | Holdings and allocations | "What's in my portfolio?" |
| Performance | Returns and charts | "Show my portfolio performance" |
| Transactions | Recent buy/sell history | "Show my recent transactions" |
| Risk Analysis | Concentration and sector risk | "Analyze my portfolio risk" |

**Research** (5 items — paste into input, cursor at end)
| Label | Description | Message |
|-------|-------------|---------|
| Deep Dive | Detailed holding analysis | "Tell me about " |
| Conviction Score | AI confidence rating | "What's the conviction score for " |
| Stock Quote | Current price and stats | "Get a quote for " |
| Look Up Symbol | Find a ticker symbol | "Look up " |
| Congressional Activity | Congress member trades | "Show congressional trades for " |

**Trading** (3 items — only visible when paper trading is active, paste into input)
| Label | Description | Message |
|-------|-------------|---------|
| Buy | Purchase shares | "Buy " |
| Sell | Sell shares | "Sell " |
| Paper Portfolio | View paper positions | "Show my paper portfolio" (sends immediately) |

### Item Click Behavior

- **Portfolio items:** Send message immediately, palette closes
- **Research items:** Paste prompt into input field (don't send), place cursor at end for user to type symbol, palette closes
- **Trading items:** Same as Research (paste, don't send). Exception: "Paper Portfolio" sends immediately.

### "/" Shortcut Behavior

- Opens palette with a filter input at top ("Search commands..." placeholder)
- Keystrokes filter items in real time (fuzzy match on label)
- Arrow keys navigate, Enter selects
- Backspace on empty filter closes palette
- Category headers stay visible unless all items in category are filtered out

### Visual Details

**"+" button:**
- Same size as ModelSelector/PaperTradeToggle
- 2x2 grid icon (four squares), gray-400
- `rounded-lg hover:bg-gray-100`
- First item in leftSlot

**Category headers:**
- `text-[10px] font-bold uppercase tracking-wider text-gray-400 px-3 pt-3 pb-1`
- Matches sidebar section header style

**Items:**
- Full-width buttons: `px-3 py-2 rounded-lg hover:bg-slate-50/60 transition-colors duration-150`
- Left: 16px icon (gray-400) — chart for Portfolio, magnifier for Research, arrows for Trading
- Label: `text-sm font-medium text-gray-700`
- Description: `text-xs text-gray-400` (second line)
- Active/selected (arrow keys): same as hover style

**Filter input (only when opened via "/"):**
- `text-sm px-3 py-2 border-b border-gray-100`
- Auto-focused on open
- Hidden when opened via "+" button click

### Component Architecture

**New file:** `frontend/src/components/Chat/CommandPalette.tsx`

**Props:**
- `onSend: (text: string) => void` — Portfolio items that fire immediately
- `onInsert: (text: string) => void` — Research/Trading items that paste into input
- `isPaperTrading: boolean` — controls Trading section visibility
- `isOpen: boolean`
- `onClose: () => void`
- `filter: string` — current filter text

**State lives in `ChatInput.tsx`:**
- `isPaletteOpen: boolean` — toggled by "+" click or "/" key
- When opened via "/", keystrokes route to filter
- `onInsert` sets input value programmatically and focuses input

**File changes:**
- Create: `frontend/src/components/Chat/CommandPalette.tsx`
- Modify: `frontend/src/components/Chat/ChatInput.tsx` — add "+" button, palette state, "/" handler, onInsert
- Modify: `frontend/src/components/Chat/ChatPanel.tsx` — pass `isPaperTrading` to ChatInput

No changes to App.tsx, Sidebar, or backend.

## Out of Scope

- Keyboard-only navigation beyond arrow keys + Enter
- Recently used / favorites
- Custom user-defined commands
- Welcome screen changes
