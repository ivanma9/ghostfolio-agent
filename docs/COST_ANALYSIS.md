# AgentForge — AI Cost Analysis

**Date:** 2026-02-28
**Author:** Ivan Ma
**Project:** Ghostfolio AI Agent (AgentForge)

---

## Data Confidence Legend

Every number in this document is tagged with its confidence level:

| Tag | Meaning | Example |
|---|---|---|
| **[MEASURED]** | Read directly from source code, API docs, or published pricing pages | API call counts per tool, model pricing, rate limits |
| **[ESTIMATED]** | Derived from measured data with reasonable calculation | Per-query cost (measured pricing × estimated token counts) |
| **[ASSUMED]** | No measured basis; educated guess or industry convention | Queries per user per day, model mix percentages |

---

## 1. Development & Testing Costs

### LLM API Costs

The agent defaults to **GPT-4o-mini via OpenAI direct API** (bypassing OpenRouter markup). Nine additional models are available via OpenRouter for eval comparisons and user selection.

#### Model Pricing Reference [MEASURED]

Prices sourced from OpenAI and OpenRouter published pricing pages as of Feb 2026.

| Model | Route | Input (per 1M tokens) | Output (per 1M tokens) |
|---|---|---|---|
| **gpt-4o-mini** (default) | OpenAI Direct | $0.15 | $0.60 |
| anthropic/claude-sonnet-4 | OpenRouter | $3.00 | $15.00 |
| anthropic/claude-haiku-4 | OpenRouter | $1.00 | $5.00 |
| openai/gpt-4o | OpenRouter | $2.50 | $10.00 |
| openai/o3-mini | OpenRouter | $1.10 | $4.40 |
| google/gemini-2.5-pro-preview | OpenRouter | $1.25 | $10.00 |
| google/gemini-2.0-flash-001 | OpenRouter | $0.10 | $0.40 |
| deepseek/deepseek-chat-v3-0324 | OpenRouter | $0.14 | $0.28 |
| meta-llama/llama-4-maverick | OpenRouter | $0.20 | $0.60 |

> OpenRouter applies a 5.5% platform fee on top of base model pricing. [MEASURED]

#### Development Spend [ESTIMATED]

**No formal token tracking was instrumented.** LangSmith auto-tracing was configured but actual usage data lives in the LangSmith dashboard, not exported. The numbers below are reconstructed estimates based on development activity logs and git history.

| Activity | Est. Queries | Avg Input Tokens | Avg Output Tokens | Est. Cost |
|---|---|---|---|---|
| Manual testing & iteration | ~500 [ASSUMED] | ~2,000 [ASSUMED] | ~800 [ASSUMED] | $0.39 |
| Unit test development (mock-based, no LLM) | 0 [MEASURED] | 0 | 0 | $0.00 |
| Eval suite runs (~80 cases × ~5 iterations) | ~400 [ESTIMATED] | ~2,500 [ASSUMED] | ~1,000 [ASSUMED] | $0.39 |
| Multi-model eval comparisons | ~160 [ESTIMATED] | ~2,500 [ASSUMED] | ~1,000 [ASSUMED] | $3.20 |
| Demo & debugging sessions | ~200 [ASSUMED] | ~3,000 [ASSUMED] | ~1,200 [ASSUMED] | $0.24 |
| **Total estimated development spend** | **~1,260** | | | **~$4.22** |

> Multi-model eval comparisons use more expensive models (Claude Sonnet at $3/$15, GPT-4o at $2.50/$10), averaging ~$0.02/query across the mix. [ESTIMATED]

> Unit tests use `respx` mocks and never call LLM APIs — confirmed by reading test source code. [MEASURED]

#### Token Composition Per Query [MEASURED + ESTIMATED]

| Component | Tokens | Source |
|---|---|---|
| System prompt | ~350 | [MEASURED] — counted from `agent/prompts.py` |
| Tool schemas (10 tools) | ~1,200 | [MEASURED] — counted from tool definitions |
| Conversation context (first message) | ~100 | [MEASURED] — single user message |
| Conversation context (at 40-message trim limit) | ~5,000–10,000 | [ESTIMATED] — depends on message lengths |
| Tool results (simple tool like portfolio_summary) | ~500–1,500 | [ESTIMATED] — depends on portfolio size |
| Tool results (enriched tool like holding_detail) | ~2,000–4,000 | [ESTIMATED] — 5 API sources aggregated |
| **Typical first-message query total (input)** | **~2,000–2,500** | [ESTIMATED] |
| **Typical output tokens** | **~600–1,200** | [ESTIMATED] |

### Observability Tool Costs [MEASURED]

| Tool | Tier | Cost |
|---|---|---|
| LangSmith | Free (5,000 traces/month) | $0 |
| Structlog | Open source | $0 |

### Infrastructure Costs [MEASURED]

| Service | Cost | Source |
|---|---|---|
| Railway (agent + PostgreSQL + Redis) | ~$5/month | Railway Hobby plan pricing |
| Ghostfolio self-hosted (Docker) | $0 (local) | Self-hosted |
| GitHub Actions (CI/CD) | $0 (free tier) | GitHub free tier |
| 3rd-party data APIs (Finnhub, Alpha Vantage, FMP) | $0 | Free tiers |
| **Total infrastructure** | **~$5/month** | |

### Total Development Cost Summary

| Category | Cost | Confidence |
|---|---|---|
| LLM API calls | ~$4.22 | ESTIMATED |
| Observability | $0 | MEASURED |
| Infrastructure (1 month) | ~$5 | MEASURED |
| 3rd-party data APIs | $0 | MEASURED |
| **Total development cost** | **~$9.22** | |

---

## 2. Production Cost Projections

### Assumptions [ASSUMED unless noted]

| Parameter | Value | Confidence | Rationale |
|---|---|---|---|
| Queries per user per day | 5 | ASSUMED | Mix of quick lookups and deep analysis |
| Avg input tokens per query | 2,300 | ESTIMATED | System prompt (350 [M]) + tool schemas (1,200 [M]) + context (750 [A]) |
| Avg output tokens per query | 900 | ASSUMED | Typical agent response with formatted data |
| LLM calls per query | 2.0 | ESTIMATED | ReAct loop: 1 tool selection + 1 synthesis. [M] from `create_react_agent` pattern |
| Tool calls per query | 1.5 | ASSUMED | Some queries need 0, complex ones need 2–3 |
| Verification overhead | +1 Ghostfolio call/query | MEASURED | `numerical.py` calls `get_portfolio_holdings` on every response |
| Days per month | 30 | — | Calendar math |

### Per-Query Cost Breakdown by Model [ESTIMATED]

Based on 2 LLM calls per query × (2,300 input + 900 output tokens per call).

| Model | Input Cost (4,600 tokens) | Output Cost (1,800 tokens) | Cost/Query | vs. Default |
|---|---|---|---|---|
| **gpt-4o-mini** (default) | $0.00069 | $0.00108 | **$0.0018** | 1.0x |
| gemini-2.0-flash | $0.00048 | $0.00076 | **$0.0012** | 0.7x |
| deepseek-chat-v3 | $0.00068 | $0.00053 | **$0.0012** | 0.7x |
| llama-4-maverick | $0.00097 | $0.00114 | **$0.0021** | 1.2x |
| claude-haiku-4 | $0.00485 | $0.00950 | **$0.0144** | 8.0x |
| o3-mini | $0.00534 | $0.00836 | **$0.0137** | 7.6x |
| gpt-4o | $0.01213 | $0.01900 | **$0.0311** | 17.3x |
| gemini-2.5-pro | $0.00606 | $0.01900 | **$0.0251** | 13.9x |
| claude-sonnet-4 | $0.01455 | $0.02850 | **$0.0431** | 23.9x |

> OpenRouter prices include 5.5% platform fee. Ghostfolio API calls are $0 (self-hosted). 3rd-party API calls are $0 at free tier. [MEASURED]

### Monthly LLM Cost Projections — By Model [ESTIMATED]

**If all users use the same model.** 5 queries/user/day × 30 days = 150 queries/user/month.

| Model | Cost/Query | 100 Users | 1,000 Users | 10,000 Users | 100,000 Users |
|---|---|---|---|---|---|
| **gpt-4o-mini** (default) | $0.0018 | **$27** | **$270** | **$2,700** | **$27,000** |
| gemini-2.0-flash | $0.0012 | $18 | $180 | $1,800 | $18,000 |
| deepseek-chat-v3 | $0.0012 | $18 | $180 | $1,800 | $18,000 |
| llama-4-maverick | $0.0021 | $32 | $315 | $3,150 | $31,500 |
| claude-haiku-4 | $0.0144 | $216 | $2,160 | $21,600 | $216,000 |
| o3-mini | $0.0137 | $206 | $2,055 | $20,550 | $205,500 |
| gpt-4o | $0.0311 | $467 | $4,665 | $46,650 | $466,500 |
| gemini-2.5-pro | $0.0251 | $377 | $3,765 | $37,650 | $376,500 |
| claude-sonnet-4 | $0.0431 | $647 | $6,465 | $64,650 | $646,500 |

> These are LLM-only costs. Infrastructure and 3rd-party API costs are added in the Total Cost of Ownership section below.

### Mixed Model Usage Scenario [ASSUMED]

The model mix below is assumed — no usage analytics exist to measure actual user preferences.

| Model | Assumed Usage Share | Rationale |
|---|---|---|
| gpt-4o-mini (default) | 70% | Default model, most users don't change |
| claude-sonnet-4 | 15% | Power users wanting best quality |
| gpt-4o | 10% | Users wanting OpenAI's best |
| Other (haiku, gemini, deepseek, etc.) | 5% | Experimenters |

**Weighted average cost per query: $0.0085** [ESTIMATED from ASSUMED mix]

| Scale | Users | Queries/Month | LLM Cost/Month |
|---|---|---|---|
| 100 users | 100 | 15,000 | **$128** |
| 1,000 users | 1,000 | 150,000 | **$1,275** |
| 10,000 users | 10,000 | 1,500,000 | **$12,750** |
| 100,000 users | 100,000 | 15,000,000 | **$127,500** |

---

## 3. API Call Budget & Rate Limit Analysis

### 3rd-Party API Rate Limits [MEASURED]

Sourced from each provider's free tier documentation.

| API | Free Tier Limit | Cost to Upgrade | Tools That Consume It |
|---|---|---|---|
| **Alpha Vantage** | 25 requests/day | $49.99/month (120 req/min) | holding_detail, conviction_score |
| **Finnhub** | 60 requests/minute | $0 (generous free tier) | holding_detail, conviction_score, stock_quote |
| **FMP** | ~250 requests/day (undocumented) | $14/month (300 req/min) | holding_detail, conviction_score |
| **Ghostfolio** | Unlimited (self-hosted) | $0 | All tools + verification pipeline |

### API Calls Per Tool Invocation [MEASURED]

Counted directly from source code in `src/ghostfolio_agent/tools/` and `src/ghostfolio_agent/verification/`.

| Tool | Ghostfolio | Finnhub | Alpha Vantage | FMP | Total |
|---|---|---|---|---|---|
| portfolio_summary | 1 | 0 | 0 | 0 | 1 |
| portfolio_performance | 1 | 0 | 0 | 0 | 1 |
| transaction_history | 1 | 0 | 0 | 0 | 1 |
| symbol_lookup | 1 | 0 | 0 | 0 | 1 |
| risk_analysis | 2 | 0 | 0 | 0 | 2 |
| stock_quote | 2 | 1 | 0 | 0 | 3 |
| holding_detail | 2 | 2 | **1** | 2 | 7 |
| conviction_score | 0 | 3 | **1** | 1 | 5 |
| paper_trade (show, N positions) | 2N | 0 | 0 | 0 | 2N |
| paper_trade (buy/sell) | 2 | 0 | 0 | 0 | 2 |
| activity_log | 2–3 | 0 | 0 | 0 | 2–3 |
| **Verification pipeline** (every query) | 1 | 0 | 0 | 0 | 1 |

### Alpha Vantage: The Bottleneck [MEASURED limits, ESTIMATED usage]

Alpha Vantage's **25 requests/day** free tier is the dominant constraint. Only two tools consume it:
- `holding_detail` — 1 call per invocation (`get_news_sentiment`)
- `conviction_score` — 1 call per invocation (`get_news_sentiment`)

**Assumption:** ~30% of queries trigger an AV-consuming tool, with 1 AV call each. [ASSUMED]

| Scale | Users | Est. AV Calls/Day | Free Tier (25/day) | Paid Tier Needed? |
|---|---|---|---|---|
| 1 user | 1 | ~2 | Sufficient | No |
| 5 users | 5 | ~8 | Sufficient | No |
| 10 users | 10 | ~15 | Sufficient | No |
| 17+ users | 17+ | ~25+ | Exceeded | **Yes ($49.99/month)** |

> At the free tier limit, `get_news_sentiment` calls fail silently. Tools handle missing data gracefully — conviction_score redistributes weights across remaining sub-scores. [MEASURED from source code]

### Finnhub: Comfortable Headroom [MEASURED limits, ESTIMATED usage]

60 requests/minute = 86,400/day. ~30% of queries hit Finnhub tools averaging 2 calls each. [ASSUMED]

| Scale | Finnhub Calls/Day | % of Limit |
|---|---|---|
| 100 users | ~300 | 0.3% |
| 1,000 users | ~3,000 | 3.5% |
| 10,000 users | ~30,000 | 35% |
| 100,000 users | ~300,000 | **347% — exceeded** |

> Finnhub free tier breaks at ~29,000 daily users. [ESTIMATED]

### FMP: Moderate Headroom [ESTIMATED]

~250 requests/day free tier (undocumented, estimated from testing). ~20% of queries hit FMP tools averaging 2 calls each. [ASSUMED]

| Scale | FMP Calls/Day | Status |
|---|---|---|
| 100 users | ~200 | Borderline |
| 1,000 users | ~2,000 | **Exceeded** |

> FMP free tier breaks at ~125 daily users. Paid tier ($14/month) required beyond that. [ESTIMATED]

---

## 4. Query Type Cost Profiles [ESTIMATED]

Costs below use the default model (gpt-4o-mini). API call counts are [MEASURED] from source code. LLM costs are [ESTIMATED] using assumed token counts.

### Simple Queries (No Tools)

*"What is dollar-cost averaging?" / "Explain P/E ratio"*

| Component | Count [MEASURED] | Cost [ESTIMATED] |
|---|---|---|
| LLM calls | 1 | $0.0009 |
| Ghostfolio calls | 1 (verifier) | $0.00 |
| 3rd-party calls | 0 | $0.00 |
| **Total** | | **$0.0009** |

### Portfolio Queries

*"What's my portfolio summary?" / "Show my performance this year"*

| Component | Count [MEASURED] | Cost [ESTIMATED] |
|---|---|---|
| LLM calls | 2 | $0.0018 |
| Ghostfolio calls | 2 (1 tool + 1 verifier) | $0.00 |
| 3rd-party calls | 0 | $0.00 |
| **Total** | | **$0.0018** |

### Enriched Queries (holding_detail)

*"Tell me about my AAPL position" — the most expensive single-tool query*

| Component | Count [MEASURED] | Cost [ESTIMATED] |
|---|---|---|
| LLM calls | 3 (route + tool result + synthesis) | $0.0035 |
| Ghostfolio calls | 3 (lookup + holding + verifier) | $0.00 |
| Finnhub calls | 2 | $0.00 |
| Alpha Vantage calls | 1 | $0.00 |
| FMP calls | 2 | $0.00 |
| **Total** | | **$0.0035** |

> LLM cost is higher because tool results from 5 API sources inject ~3,000 additional input tokens into the synthesis call. [ESTIMATED]

### Multi-Tool Queries

*"Analyze my portfolio risk and give me conviction scores for my top 3 holdings"*

| Component | Count [MEASURED] | Cost [ESTIMATED] |
|---|---|---|
| LLM calls | 5–6 (iterative ReAct loop) | $0.0045–$0.0054 |
| Ghostfolio calls | 4 (risk_analysis: 2 + verifier: 1 + holding lookups) | $0.00 |
| Finnhub calls | 9 (3 per conviction_score × 3 symbols) | $0.00 |
| Alpha Vantage calls | 3 (1 per conviction_score × 3 symbols) | $0.00 |
| FMP calls | 3 (1 per conviction_score × 3 symbols) | $0.00 |
| **Total** | | **$0.005–$0.006** |

### Paper Trade Show (N Positions) [MEASURED call pattern]

*"Show my paper portfolio" — API calls scale linearly with position count*

| Positions | Ghostfolio Calls | LLM Calls | LLM Cost |
|---|---|---|---|
| 5 | 11 (2×5 + verifier) | 2 | $0.0018 |
| 10 | 21 (2×10 + verifier) | 2 | $0.0018 |
| 20 | 41 (2×20 + verifier) | 2 | $0.0018 |

> Ghostfolio is self-hosted so API call scaling affects latency, not cost. LLM cost is constant. [MEASURED architecture]

### Query Type Cost Comparison Across Models [ESTIMATED]

How the same query costs on different models:

| Query Type | gpt-4o-mini | deepseek-v3 | claude-haiku-4 | gpt-4o | claude-sonnet-4 |
|---|---|---|---|---|---|
| Simple (no tools) | $0.0009 | $0.0006 | $0.0072 | $0.016 | $0.022 |
| Portfolio summary | $0.0018 | $0.0012 | $0.0144 | $0.031 | $0.043 |
| Holding detail | $0.0035 | $0.0024 | $0.028 | $0.060 | $0.084 |
| Multi-tool (3 symbols) | $0.0054 | $0.0036 | $0.043 | $0.093 | $0.130 |

> A holding_detail query on claude-sonnet-4 costs **24x more** than on gpt-4o-mini. This is the core cost trade-off users make when selecting a model.

---

## 5. Edge Cases & Cost Spikes

### Long Conversations (Context Growth) [ESTIMATED]

The context trimmer caps at 40 messages [MEASURED from `graph.py`]. Token growth is estimated.

| Conversation Length | Input Tokens/Call | Cost/Query (gpt-4o-mini) | Cost/Query (claude-sonnet-4) |
|---|---|---|---|
| Fresh (1–5 messages) | ~2,300 [ESTIMATED] | $0.0018 | $0.043 |
| Medium (10–20 messages) | ~5,000 [ESTIMATED] | $0.0024 | $0.058 |
| Long (30–40 messages) | ~10,000 [ESTIMATED] | $0.0042 | $0.101 |

> Worst case is ~2.3x the baseline cost. The 40-message trim prevents unbounded growth. [MEASURED cap, ESTIMATED multiplier]

### ReAct Loop Runaway [MEASURED architecture, ESTIMATED costs]

The ReAct agent (`create_react_agent`) has **no explicit max iterations** [MEASURED from `graph.py`]. If the LLM enters a loop, costs multiply:

| ReAct Iterations | LLM Calls | gpt-4o-mini | claude-sonnet-4 |
|---|---|---|---|
| 2 (typical) | 2 | $0.0018 | $0.043 |
| 5 (unusual) | 5 | $0.0045 | $0.108 |
| 10 (pathological) | 10 | $0.0090 | $0.215 |

### Large Portfolio Data [ESTIMATED]

Users with many holdings generate large tool results. Token counts per holding are estimated from sample Ghostfolio API responses.

| Holdings | Tool Result Size | Additional Input Tokens | gpt-4o-mini Impact | claude-sonnet-4 Impact |
|---|---|---|---|---|
| 10 holdings | ~1,500 tokens | +1,500 | +$0.0002 | +$0.027 |
| 50 holdings | ~7,500 tokens | +7,500 | +$0.0011 | +$0.135 |
| 200 holdings | ~30,000 tokens | +30,000 | +$0.0045 | +$0.540 |
| 500+ holdings | ~75,000 tokens | +75,000 | +$0.0113 | +$1.350 |

> A user with 500 holdings on claude-sonnet-4 pays ~$1.35 extra per query just for portfolio data in context. On gpt-4o-mini, the same data costs 1.1 cents extra.

### No Caching [MEASURED]

The codebase has **zero caching** at any layer — confirmed by searching for cache/TTL/memoize patterns across all source files:
- No LLM response cache (identical questions re-invoke full stack)
- No tool result cache (repeated portfolio_summary calls hit Ghostfolio API every time)
- No 3rd-party API response cache (each holding_detail call makes 5 fresh API calls)
- Ghostfolio client creates a new `httpx.AsyncClient` per request (no connection pooling) [MEASURED from `clients/ghostfolio.py`]

**Cost impact [ESTIMATED]:** A user asking "what's my portfolio?" three times in a row costs 3x instead of 1x. Implementing a 5-minute TTL cache on tool results would reduce costs by an estimated 20–30% for typical usage patterns.

---

## 6. LangSmith Observability Costs [MEASURED pricing, ESTIMATED usage]

| Tier | Traces/Month | Cost | Source |
|---|---|---|---|
| Free | 5,000 | $0 | LangSmith pricing page |
| Plus | 50,000 | $39/month | LangSmith pricing page |
| Enterprise | Unlimited | Custom | LangSmith pricing page |

Each user query generates 1 trace with 3–8 spans [ESTIMATED from ReAct pattern]. At 5 queries/user/day [ASSUMED]:

| Scale | Traces/Month | Tier Needed | Cost |
|---|---|---|---|
| 100 users | 15,000 | Plus ($39/mo) | $39 |
| 1,000 users | 150,000 | Enterprise | Custom |
| 10,000+ users | 1,500,000+ | Enterprise | Custom |

---

## 7. Total Cost of Ownership by Scale

### 100 Users/month

| Category | Monthly Cost | Confidence |
|---|---|---|
| LLM API — if all gpt-4o-mini | $27 | ESTIMATED |
| LLM API — if mixed models | $128 | ESTIMATED (ASSUMED mix) |
| LLM API — if all claude-sonnet-4 | $647 | ESTIMATED |
| Railway hosting | $10 | MEASURED |
| Alpha Vantage | $0 (free tier) | MEASURED |
| FMP | $0 (free tier) | MEASURED |
| Finnhub | $0 (free tier) | MEASURED |
| LangSmith | $39 (Plus tier) | MEASURED |
| **Total (default model)** | **$76** | |
| **Total (mixed models)** | **$177** | |
| **Total (all Sonnet)** | **$696** | |

### 1,000 Users/month

| Category | Monthly Cost | Confidence |
|---|---|---|
| LLM API — if all gpt-4o-mini | $270 | ESTIMATED |
| LLM API — if mixed models | $1,275 | ESTIMATED (ASSUMED mix) |
| LLM API — if all claude-sonnet-4 | $6,465 | ESTIMATED |
| Railway hosting | $25 | MEASURED |
| Alpha Vantage | $49.99 (paid tier required) | MEASURED |
| FMP | $14 (paid tier required) | MEASURED |
| Finnhub | $0 (free tier) | MEASURED |
| LangSmith | Custom (Enterprise) | MEASURED |
| **Total (default model)** | **$359** + LangSmith | |
| **Total (mixed models)** | **$1,364** + LangSmith | |
| **Total (all Sonnet)** | **$6,554** + LangSmith | |

### 10,000 Users/month

| Category | Monthly Cost | Confidence |
|---|---|---|
| LLM API — if all gpt-4o-mini | $2,700 | ESTIMATED |
| LLM API — if mixed models | $12,750 | ESTIMATED (ASSUMED mix) |
| LLM API — if all claude-sonnet-4 | $64,650 | ESTIMATED |
| Railway hosting | $100 | ESTIMATED |
| Alpha Vantage | $49.99 | MEASURED |
| FMP | $14 | MEASURED |
| Finnhub | $0 (free tier) | MEASURED |
| LangSmith | Custom (Enterprise) | — |
| **Total (default model)** | **$2,864** + LangSmith | |
| **Total (mixed models)** | **$12,914** + LangSmith | |
| **Total (all Sonnet)** | **$64,814** + LangSmith | |

### 100,000 Users/month

| Category | Monthly Cost | Confidence |
|---|---|---|
| LLM API — if all gpt-4o-mini | $27,000 | ESTIMATED |
| LLM API — if mixed models | $127,500 | ESTIMATED (ASSUMED mix) |
| LLM API — if all claude-sonnet-4 | $646,500 | ESTIMATED |
| Railway hosting | $500 | ESTIMATED |
| Alpha Vantage | $49.99 | MEASURED |
| FMP | $14 | MEASURED |
| Finnhub | ~$500+ (paid tier needed) | ESTIMATED |
| LangSmith | Custom (Enterprise) | — |
| **Total (default model)** | **$28,064** + LangSmith | |
| **Total (mixed models)** | **$128,564** + LangSmith | |
| **Total (all Sonnet)** | **$647,564** + LangSmith | |

---

## 8. Cost Optimization Opportunities

| Optimization | Estimated Savings | Effort | Confidence |
|---|---|---|---|
| Add 5-min TTL cache on tool results | 20–30% fewer API + LLM calls | Low | ESTIMATED |
| Connection pooling (reuse httpx client) | Reduced latency, marginal cost savings | Low | MEASURED (no pooling exists) |
| Cap ReAct loop iterations (max 5) | Prevents pathological cost spikes | Low | MEASURED (no cap exists) |
| Skip verification for no-tool queries | 1 fewer Ghostfolio call on simple questions | Low | MEASURED (verifier always runs) |
| Batch Alpha Vantage calls (multi-symbol) | Reduce AV quota consumption | Medium | MEASURED (AV supports `tickers` param) |
| Switch to Gemini 2.0 Flash as default | 33% cheaper than gpt-4o-mini | Medium (requires eval) | MEASURED (pricing) |
| Implement semantic response caching | 40–50% reduction for repeated patterns | High | ASSUMED |

---

## Sources

- [OpenAI API Pricing](https://platform.openai.com/docs/pricing)
- [OpenRouter Pricing](https://openrouter.ai/pricing)
- [Claude API Pricing](https://platform.claude.com/docs/en/about-claude/pricing)
- [LLM API Pricing Comparison 2026](https://www.tldl.io/resources/llm-api-pricing-2026)
- [AI API Pricing Comparison 2026](https://dev.to/lemondata_dev/ai-api-pricing-comparison-2026-the-real-cost-of-gpt-41-claude-sonnet-46-and-gemini-25-11co)
