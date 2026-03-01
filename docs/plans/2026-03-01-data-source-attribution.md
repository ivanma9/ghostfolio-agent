# Data Source Attribution — Footer Badges

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Show colored source badges (Finnhub, Alpha Vantage, FMP, Ghostfolio) below each chat message, indicating which 3rd-party data sources were used for that specific response.

**Architecture:** Tools append a `[DATA_SOURCES: ...]` metadata line to their output listing only sources that actually returned data. Backend extracts and deduplicates these into a `data_sources` field on `ChatResponse`. Frontend renders colored pills below assistant messages.

**Tech Stack:** Python (FastAPI/Pydantic), TypeScript (React), Tailwind CSS

---

### Task 1: Add `data_sources` field to ChatResponse model

**Files:**
- Modify: `src/ghostfolio_agent/models/api.py:29-43`
- Test: `tests/unit/test_data_sources.py`

**Step 1: Write the failing test**

```python
# tests/unit/test_data_sources.py
from ghostfolio_agent.models.api import ChatResponse


def test_chat_response_includes_data_sources_field():
    resp = ChatResponse(
        response="test",
        session_id="s1",
        data_sources=["Finnhub", "Alpha Vantage"],
    )
    assert resp.data_sources == ["Finnhub", "Alpha Vantage"]


def test_chat_response_data_sources_defaults_empty():
    resp = ChatResponse(response="test", session_id="s1")
    assert resp.data_sources == []
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_data_sources.py -v`
Expected: FAIL — `data_sources` field doesn't exist yet

**Step 3: Write minimal implementation**

Add to `ChatResponse` in `src/ghostfolio_agent/models/api.py` after line 43 (after `verification_details`):

```python
    data_sources: list[str] = Field(
        default_factory=list, description="3rd-party data sources used in this response"
    )
```

**Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/test_data_sources.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add src/ghostfolio_agent/models/api.py tests/unit/test_data_sources.py
git commit -m "feat: add data_sources field to ChatResponse model"
```

---

### Task 2: Add `[DATA_SOURCES: ...]` metadata to tool outputs

**Files:**
- Modify: `src/ghostfolio_agent/tools/stock_quote.py`
- Modify: `src/ghostfolio_agent/tools/holding_detail.py`
- Modify: `src/ghostfolio_agent/tools/conviction_score.py`
- Modify: `src/ghostfolio_agent/tools/morning_briefing.py`
- Test: `tests/unit/test_data_sources.py` (add tests)

Each tool that calls 3rd-party APIs should append `[DATA_SOURCES: Source1, Source2]` as the **last line** of its return string, listing only sources that actually returned data.

**Source mapping:**
- Ghostfolio client calls → `Ghostfolio`
- `finnhub.get_*()` calls → `Finnhub`
- `alpha_vantage.get_*()` calls → `Alpha Vantage`
- `fmp.get_*()` calls → `FMP`

**Step 1: Write failing tests**

Add to `tests/unit/test_data_sources.py`:

```python
import re

DATA_SOURCES_RE = re.compile(r"\[DATA_SOURCES:\s*(.+)\]")


def test_data_sources_regex_parses():
    line = "[DATA_SOURCES: Finnhub, Alpha Vantage, FMP]"
    m = DATA_SOURCES_RE.search(line)
    assert m is not None
    sources = [s.strip() for s in m.group(1).split(",")]
    assert sources == ["Finnhub", "Alpha Vantage", "FMP"]


def test_data_sources_regex_single():
    line = "[DATA_SOURCES: Finnhub]"
    m = DATA_SOURCES_RE.search(line)
    assert m is not None
    sources = [s.strip() for s in m.group(1).split(",")]
    assert sources == ["Finnhub"]
```

**Step 2: Run test to verify it passes** (regex tests are standalone)

Run: `uv run pytest tests/unit/test_data_sources.py -v`
Expected: PASS

**Step 3: Modify `stock_quote.py`**

In `create_stock_quote_tool` inner function, before the final `return "\n".join(lines)`:
- The tool always calls Ghostfolio for symbol lookup.
- If Finnhub quote succeeds, add "Finnhub" to sources.
- Append the metadata line.

```python
        sources = ["Ghostfolio"]
        # ... after finnhub quote fetch succeeds ...
        sources.append("Finnhub")
        # ... at the end, before return ...
        lines.append(f"[DATA_SOURCES: {', '.join(sources)}]")
        return "\n".join(lines)
```

**Step 4: Modify `holding_detail.py`**

After the enrichment `asyncio.gather` resolves, check which results are non-None/non-empty:

```python
        sources = ["Ghostfolio"]  # always used for base holding data
        if enrichment.get("finnhub_earnings") or enrichment.get("finnhub_analyst"):
            sources.append("Finnhub")
        if enrichment.get("av_news"):
            sources.append("Alpha Vantage")
        if enrichment.get("fmp_pt_consensus") or enrichment.get("fmp_pt_summary"):
            sources.append("FMP")
        lines.append(f"[DATA_SOURCES: {', '.join(sources)}]")
```

**Step 5: Modify `conviction_score.py`**

After the data fetch section resolves, check which results came back:

```python
        sources = []
        if data.get("analyst") or data.get("quote") or data.get("earnings"):
            sources.append("Finnhub")
        if data.get("news"):
            sources.append("Alpha Vantage")
        if data.get("pt_consensus"):
            sources.append("FMP")
        if sources:
            lines.append(f"[DATA_SOURCES: {', '.join(sources)}]")
```

**Step 6: Modify `morning_briefing.py`**

Track sources throughout the two-phase fetch:

```python
        sources = ["Ghostfolio"]  # always used for holdings
        # After Phase 1 (quotes/earnings from Finnhub):
        if finnhub and any quote data returned:
            sources.append("Finnhub")
        # After Phase 2 (deep enrich):
        if any news data returned:
            if "Alpha Vantage" not in sources:
                sources.append("Alpha Vantage")
        if any pt data returned:
            if "FMP" not in sources:
                sources.append("FMP")
        # Macro always from Alpha Vantage if available:
        if macro and macro.get("fed_funds") is not None:
            if "Alpha Vantage" not in sources:
                sources.append("Alpha Vantage")
        lines.append(f"[DATA_SOURCES: {', '.join(sources)}]")
```

**Step 7: Run full test suite**

Run: `uv run pytest tests/unit/ -v`
Expected: All PASS

**Step 8: Commit**

```bash
git add src/ghostfolio_agent/tools/stock_quote.py src/ghostfolio_agent/tools/holding_detail.py src/ghostfolio_agent/tools/conviction_score.py src/ghostfolio_agent/tools/morning_briefing.py tests/unit/test_data_sources.py
git commit -m "feat: append DATA_SOURCES metadata to tool outputs"
```

---

### Task 3: Extract data sources in `chat.py` and populate `ChatResponse`

**Files:**
- Modify: `src/ghostfolio_agent/api/chat.py:299-351`
- Test: `tests/unit/test_data_sources.py` (add tests)

**Step 1: Write the failing test**

Add to `tests/unit/test_data_sources.py`:

```python
def test_extract_data_sources_from_tool_outputs():
    from ghostfolio_agent.api.chat import _extract_data_sources

    outputs = [
        "AAPL — Apple Inc.\n  Price: $150.00\n[DATA_SOURCES: Ghostfolio, Finnhub]",
        "Conviction Score: 72/100 — Buy\n[DATA_SOURCES: Finnhub, Alpha Vantage, FMP]",
    ]
    sources = _extract_data_sources(outputs)
    assert sorted(sources) == ["Alpha Vantage", "FMP", "Finnhub", "Ghostfolio"]


def test_extract_data_sources_empty():
    from ghostfolio_agent.api.chat import _extract_data_sources

    assert _extract_data_sources([]) == []
    assert _extract_data_sources(["no metadata here"]) == []


def test_strip_data_sources_line_from_output():
    from ghostfolio_agent.api.chat import _strip_data_sources_line

    output = "AAPL — Apple\n  Price: $150\n[DATA_SOURCES: Finnhub]"
    assert _strip_data_sources_line(output) == "AAPL — Apple\n  Price: $150"
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_data_sources.py::test_extract_data_sources_from_tool_outputs -v`
Expected: FAIL — function doesn't exist

**Step 3: Implement extraction in `chat.py`**

Add two helper functions near the top of `chat.py` (after `_extract_citations`):

```python
import re

_DATA_SOURCES_RE = re.compile(r"\[DATA_SOURCES:\s*(.+)\]")


def _extract_data_sources(tool_outputs: list[str]) -> list[str]:
    """Extract and deduplicate data source names from tool output metadata lines."""
    seen: set[str] = set()
    for output in tool_outputs:
        for line in output.splitlines():
            m = _DATA_SOURCES_RE.search(line)
            if m:
                for src in m.group(1).split(","):
                    seen.add(src.strip())
    return sorted(seen)


def _strip_data_sources_line(output: str) -> str:
    """Remove the [DATA_SOURCES: ...] metadata line from a tool output string."""
    return "\n".join(
        line for line in output.splitlines()
        if not _DATA_SOURCES_RE.search(line)
    )
```

Then in the `chat()` endpoint, after building `tool_outputs` (around line 318):
1. Extract data sources from raw outputs.
2. Strip metadata lines from outputs before passing to verification/response.

```python
        # Extract data sources before stripping metadata
        data_sources = _extract_data_sources(tool_outputs)
        # Strip metadata lines so they don't appear in LLM context or verification
        tool_outputs = [_strip_data_sources_line(o) for o in tool_outputs]
```

And add `data_sources=data_sources` to the `ChatResponse(...)` return (around line 342).

**Step 4: Run tests**

Run: `uv run pytest tests/unit/test_data_sources.py -v`
Expected: All PASS

**Step 5: Run full test suite**

Run: `uv run pytest tests/unit/ -v`
Expected: All PASS

**Step 6: Commit**

```bash
git add src/ghostfolio_agent/api/chat.py tests/unit/test_data_sources.py
git commit -m "feat: extract data_sources from tool outputs in chat endpoint"
```

---

### Task 4: Frontend — Add `dataSources` to types, hook, and render pills

**Files:**
- Modify: `frontend/src/types/index.ts`
- Modify: `frontend/src/hooks/useChat.ts`
- Modify: `frontend/src/components/Chat/MessageBubble.tsx`

**Step 1: Add `dataSources` to types**

In `frontend/src/types/index.ts`:

Add to `ChatMessage` interface:
```typescript
  dataSources?: string[]
```

Add to `ChatResponse` interface:
```typescript
  data_sources: string[]
```

**Step 2: Map `data_sources` in `useChat.ts`**

In the `sendMessage` callback, when building `assistantMessage` (around line 55-63), add:

```typescript
          dataSources: data.data_sources ?? [],
```

**Step 3: Render source pills in `MessageBubble.tsx`**

Add a source color map at the top of the file:

```typescript
const SOURCE_COLORS: Record<string, { bg: string; text: string; dot: string }> = {
  Finnhub:          { bg: 'bg-blue-50',   text: 'text-blue-700',   dot: 'bg-blue-400' },
  'Alpha Vantage':  { bg: 'bg-green-50',  text: 'text-green-700',  dot: 'bg-green-400' },
  FMP:              { bg: 'bg-purple-50',  text: 'text-purple-700', dot: 'bg-purple-400' },
  Ghostfolio:       { bg: 'bg-indigo-50',  text: 'text-indigo-700', dot: 'bg-indigo-400' },
}

const DEFAULT_SOURCE_COLOR = { bg: 'bg-gray-50', text: 'text-gray-700', dot: 'bg-gray-400' }
```

Add a `DataSourceBadges` component:

```tsx
function DataSourceBadges({ sources }: { sources: string[] }) {
  if (sources.length === 0) return null
  return (
    <div className="flex flex-wrap items-center gap-1.5 mt-2 pt-2 border-t border-gray-100">
      <span className="text-xs text-gray-400">Sources</span>
      {sources.map((src) => {
        const colors = SOURCE_COLORS[src] ?? DEFAULT_SOURCE_COLOR
        return (
          <span
            key={src}
            className={`inline-flex items-center gap-1 text-xs ${colors.bg} ${colors.text} px-2 py-0.5 rounded-full font-medium`}
          >
            <span className={`w-1.5 h-1.5 rounded-full ${colors.dot}`} />
            {src}
          </span>
        )
      })}
    </div>
  )
}
```

Render it inside the assistant message bubble, after the VerificationBanner and before the closing `</div>` of the bubble (around line 129):

```tsx
          {/* Data source attribution */}
          {!isUser && message.dataSources && message.dataSources.length > 0 && (
            <DataSourceBadges sources={message.dataSources} />
          )}
```

**Step 4: Build to verify no TypeScript errors**

Run: `cd frontend && npx tsc -b && npx vite build`
Expected: Build succeeds

**Step 5: Commit**

```bash
git add frontend/src/types/index.ts frontend/src/hooks/useChat.ts frontend/src/components/Chat/MessageBubble.tsx
git commit -m "feat: render data source badges in chat messages"
```

---

### Task 5: Run full test suite and verify

**Step 1: Run backend tests**

Run: `uv run pytest tests/unit/ -v`
Expected: All PASS

**Step 2: Run frontend build**

Run: `cd frontend && npx tsc -b && npx vite build`
Expected: Build succeeds

**Step 3: Final commit (if any remaining changes)**

```bash
git status
# Should be clean
```
