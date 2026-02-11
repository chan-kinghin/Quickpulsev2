# Plan: LLM Business Queries (DeepSeek Integration)

## Status: Not Started

## Design Spec

### Problem
Users currently query MTO status through manual number input and read raw tabular data. There's no way to ask business questions in natural language like "which materials are delayed?", get auto-generated summaries, or perform cross-MTO analytics. Understanding the business scenario requires manual interpretation of quantities and fulfillment rates.

### Solution
Add a **collapsible side panel** chat interface powered by **DeepSeek API** that lets users:

1. **Natural language Q&A** about loaded MTO data ("哪些物料还没到货?", "What's blocking this order?")
2. **Business summaries** ("summarize the current status", auto-generated insights)
3. **Cross-MTO analytics** via SQLite queries ("which MTOs have fulfillment < 50%?", "show all delayed orders for customer X")

**Architecture**: The LLM does NOT query Kingdee directly. Instead:
- For **single-MTO queries**: The backend serializes the current MTO data (already fetched) into a structured context, sends it to DeepSeek with the user's question
- For **cross-MTO analytics**: The backend uses the SQLite cache to gather aggregate data, then sends that as context to DeepSeek for natural language analysis
- All queries go through a new `/api/llm/chat` endpoint

```
User Question (frontend)
    │
    ▼
POST /api/llm/chat
    │ { question, mto_number?, mode: "mto" | "analytics" }
    │
    ▼
LLM Service (src/llm/service.py)
    ├─ mode="mto": Serialize MTOStatusResponse → context
    ├─ mode="analytics": Run SQL aggregation → context
    │
    ▼
DeepSeek API (chat completion)
    │ system prompt + context + user question
    │
    ▼
Stream response back to frontend (SSE)
```

### Files to Create
| File | Purpose |
|------|---------|
| `src/llm/__init__.py` | Package init |
| `src/llm/service.py` | DeepSeek API client + context builder |
| `src/llm/prompts.py` | System prompts for different query modes |
| `src/llm/context.py` | MTO data serializer + SQL analytics context builder |
| `src/api/routers/llm.py` | `/api/llm/chat` endpoint (SSE streaming) |
| `src/frontend/static/js/chat.js` | Alpine.js chat component |
| `tests/test_llm_service.py` | Unit tests for LLM service |
| `tests/test_llm_router.py` | API endpoint tests |

### Files to Modify
| File | Change |
|------|--------|
| `src/config.py` | Add `DeepSeekConfig` class (api_key, model, base_url) |
| `src/main.py` | Initialize LLM service in lifespan, register router |
| `src/frontend/dashboard.html` | Add side panel HTML structure + chat toggle button |
| `src/frontend/static/css/main.css` | Chat panel styles |
| `pyproject.toml` | Add `httpx` (already present) or `openai` SDK dependency |
| `.env.example` | Already has `DEEPSEEK_API_KEY` placeholder (no change needed) |

### Key Design Decisions

1. **DeepSeek API via OpenAI-compatible SDK**: DeepSeek uses the OpenAI chat completions format. We'll use `httpx` directly (already a dependency) to avoid adding `openai` package.

2. **SSE Streaming**: Stream responses token-by-token for better UX. Use FastAPI's `StreamingResponse` with `text/event-stream`.

3. **Context Strategy**:
   - **MTO mode**: Serialize current MTO's `ParentItem` + `ChildItem[]` + metrics into a structured text block (~1-2K tokens). No extra API/DB calls needed.
   - **Analytics mode**: Run pre-defined SQL queries against SQLite cache tables to get aggregate stats (total MTOs, average fulfillment, delayed items, etc.), then include as context (~500-1K tokens).

4. **System Prompt**: Domain-specific prompt that explains the Kingdee ERP context, material types (成品/自制/包材), quantity fields, and how to interpret fulfillment rates. Written in Chinese to match the UI language.

5. **Rate Limiting**: 10 req/min for LLM queries (more expensive than data queries).

6. **Graceful Degradation**: If `DEEPSEEK_API_KEY` is not set, the chat panel is hidden and the LLM router returns 503.

### Data Flow: MTO Chat Query

```
1. User loads MTO AK2510034 (normal flow, data in frontend)
2. User opens chat panel, types: "哪些物料入库率低于50%?"
3. Frontend sends POST /api/llm/chat:
   { "question": "哪些物料入库率低于50%?", "mto_number": "AK2510034" }
4. Backend fetches MTO data (from cache/memory, fast)
5. Backend builds context:
   "MTO: AK2510034 | 客户: XX公司 | 交期: 2025-03-15
    物料清单:
    - 07.01.001 成品A: 订单100, 入库80, 完成率80%
    - 05.02.003 自制件B: 应收200, 实收50, 完成率25% ⚠️
    - 03.04.005 包材C: 采购500, 入库500, 完成率100% ✓"
6. DeepSeek receives system prompt + context + question
7. Response streamed back: "以下物料入库率低于50%：
    1. 05.02.003 自制件B - 完成率仅25%，应收200但实收只有50..."
```

### Data Flow: Cross-MTO Analytics Query

```
1. User types: "最近有哪些MTO的整体完成率不到50%?"
2. Frontend sends POST /api/llm/chat:
   { "question": "...", "mode": "analytics" }
3. Backend queries SQLite:
   - Get all distinct MTOs from last 30 days
   - Aggregate fulfillment by MTO
   - Filter where avg fulfillment < 50%
4. Backend builds context with aggregated data
5. DeepSeek analyzes and responds naturally
```

## Implementation Steps

### Step 1: Config & Dependencies
- Add `DeepSeekConfig` to `src/config.py`
- No new pip dependencies needed (httpx already available)

### Step 2: LLM Service Core
- Create `src/llm/service.py` with DeepSeek client
- Implement streaming chat completion via httpx
- Create `src/llm/prompts.py` with system prompts
- Create `src/llm/context.py` with MTO data serializer

### Step 3: API Endpoint
- Create `src/api/routers/llm.py` with SSE streaming endpoint
- Register in `src/main.py`

### Step 4: Frontend Chat Panel
- Add chat panel HTML to `dashboard.html`
- Create `src/frontend/static/js/chat.js` with Alpine.js component
- Add chat panel CSS styles

### Step 5: Tests
- Unit tests for context building and prompt assembly
- API endpoint tests with mocked DeepSeek responses

## Test Cases

### Unit Tests
- [ ] `test_deepseek_config_loads_from_env`: Config reads DEEPSEEK_API_KEY from env
- [ ] `test_deepseek_config_optional`: App starts without DEEPSEEK_API_KEY (chat disabled)
- [ ] `test_mto_context_serialization`: MTO data correctly serialized to text context
- [ ] `test_analytics_context_from_sql`: SQL aggregation produces valid context
- [ ] `test_system_prompt_includes_domain_knowledge`: Prompt contains material type explanations
- [ ] `test_message_history_truncation`: Conversation history stays within token limit

### Integration Tests
- [ ] `test_llm_chat_endpoint_returns_sse`: Endpoint returns SSE stream
- [ ] `test_llm_chat_requires_auth`: Endpoint requires JWT auth
- [ ] `test_llm_chat_no_api_key_returns_503`: Returns 503 when no API key configured
- [ ] `test_llm_chat_rate_limited`: Rate limiting at 10/min works

### Manual Verification
1. Open dashboard, load an MTO number
2. Click chat toggle button — side panel slides in from right
3. Type a question in Chinese → see streaming response
4. Ask about specific materials → response references actual data
5. Switch to analytics mode → ask cross-MTO question
6. Close panel → state preserved (conversation history)
7. Without DEEPSEEK_API_KEY → chat button hidden

## Acceptance Criteria
- [ ] Chat side panel opens/closes smoothly on dashboard
- [ ] Natural language questions about loaded MTO get accurate answers referencing actual data
- [ ] Cross-MTO analytics queries work against SQLite cache
- [ ] Responses stream token-by-token (SSE)
- [ ] Chat panel hidden when DEEPSEEK_API_KEY not configured
- [ ] Rate limited to 10 req/min
- [ ] All tests pass
- [ ] No regressions in existing MTO query functionality
