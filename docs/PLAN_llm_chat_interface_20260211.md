# Plan: LLM Chat Interface (DeepSeek) for QuickPulse Dashboard

## Status: Complete

## Context

Users query MTO status through manual number input and read raw tabular data. There's no way to ask business questions in natural language or get cross-MTO analytics. This feature adds an **integrated sidebar chat** powered by **DeepSeek API** that serves as a **navigation co-pilot**:

**Core workflow: Discovery → Verification**
```
Ask broad question → LLM lists MTO numbers → Click MTO link → Dashboard loads it → Ask follow-up
```

The LLM responses contain **clickable MTO numbers** — clicking one loads it in the dashboard, enabling a tight discovery-to-verification loop.

---

## Improvements Over Original Plan

| Area | Original | Improved |
|------|----------|----------|
| **LLM Client** | Raw httpx SSE parsing | `openai` SDK (v1.99.3, already installed) — DeepSeek is OpenAI-compatible |
| **Rate Limiting** | Custom deque-based sliding window | Reuse existing slowapi on endpoint — simpler, consistent |
| **Conversation History** | Not addressed | Sliding window with max_history_messages config |
| **SQL Guard** | Basic keyword blocklist | Also handles `--` comments, `/**/`, CTEs, UNION, subquery depth |
| **Frontend Layout** | Vague "flex row" | Specific: fixed right panel, CSS transition, z-index layering |
| **Error Handling** | Not detailed | Typed errors: ChatConnectionError, ChatRateLimitError, ChatSQLError |
| **.env.example** | Not updated | Add DEEPSEEK_* vars for discoverability |

---

## Implementation Steps

### Step 1: Config & Exceptions

**`src/config.py`** — Add `DeepSeekConfig` after `KingdeeConfig` (line ~112):
```python
class DeepSeekConfig(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="DEEPSEEK_", env_file=".env", extra="ignore")
    api_key: str = ""
    base_url: str = "https://api.deepseek.com"     # OpenAI-compatible endpoint
    model: str = "deepseek-chat"
    max_tokens: int = 1024
    temperature: float = 0.3
    timeout_seconds: int = 30
    max_history_messages: int = 20                   # Conversation window
    def is_available(self) -> bool: return bool(self.api_key)
```
- Add `deepseek: DeepSeekConfig` param to `Config.__init__` (line 216) with default `DeepSeekConfig()`
- Add `deepseek=DeepSeekConfig()` in `Config.load()` return (line 240)

**`src/exceptions.py`** — Add after `KingdeeQueryError` (line 21):
```python
class ChatError(QuickPulseError):
    """Chat/LLM service errors."""

class ChatConnectionError(ChatError):
    """Connection to LLM API failed."""

class ChatRateLimitError(ChatError):
    """LLM API rate limit exceeded."""

class ChatSQLError(ChatError):
    """SQL validation or execution failed."""
```

**`.env.example`** — Append DeepSeek vars for discoverability.

### Step 2: DeepSeek Client (`src/chat/` package — new)

**`src/chat/__init__.py`** — Exports `DeepSeekClient`

**`src/chat/client.py`** — Uses the `openai` SDK (already installed v1.99.3):
```python
from openai import AsyncOpenAI

class DeepSeekClient:
    def __init__(self, config: DeepSeekConfig):
        self._client = AsyncOpenAI(
            api_key=config.api_key,
            base_url=config.base_url,
            timeout=config.timeout_seconds,
        )
        self._model = config.model
        self._max_tokens = config.max_tokens
        self._temperature = config.temperature

    async def stream_chat(self, messages, system_prompt) -> AsyncIterator[str]:
        """Stream chat completions, yielding content deltas."""
        full_messages = [{"role": "system", "content": system_prompt}] + messages
        stream = await self._client.chat.completions.create(
            model=self._model,
            messages=full_messages,
            max_tokens=self._max_tokens,
            temperature=self._temperature,
            stream=True,
        )
        async for chunk in stream:
            delta = chunk.choices[0].delta.content
            if delta:
                yield delta

    async def close(self):
        await self._client.close()
```

**Why `openai` SDK over raw httpx:**
- Handles SSE parsing, retries, error types automatically
- DeepSeek officially supports this approach
- 80% less code, zero SSE parsing bugs
- Already installed in project (v1.99.3)

### Step 3: Context & Prompts

**`src/chat/context.py`** — Two context builders:
- `build_mto_context(mto_data: dict) -> str` — Serialize MTO JSON into compact text. Group by material type (成品/自制/外购), cap 20 items/type, include metrics. Target <2K tokens.
- `build_sql_result_context(rows, column_names) -> str` — Format SQL results as markdown table. Cap at 50 rows.

**`src/chat/prompts.py`** — Chinese system prompts:
- `SYSTEM_PROMPT_MTO` — ERP domain knowledge:
  - Material types: 07.xx=成品, 05.xx=自制, 03.xx=外购
  - Quantity fields mapping per material type
  - Semantic metrics (fulfillment_rate, completion_status, over_pick)
  - MTO number format: `AKYYNNnnn` (e.g., AK2510034)
  - Response rules: use MTO numbers inline, answer in Chinese
- `SYSTEM_PROMPT_ANALYTICS` — SQL analytics mode:
  - Complete schema reference (all 10 cache tables with columns from schema.sql)
  - SQL-only instructions: respond ONLY with a SQL query wrapped in ```sql
  - Table relationships (mto_number is the join key across tables)
  - Common query patterns

**`src/chat/sql_guard.py`** — SQL safety validation:
```python
def validate_sql(query: str) -> str:
    """Validate and sanitize SQL. Returns cleaned query or raises ChatSQLError."""
```
- Strip `--` line comments and `/* */` block comments
- Must start with SELECT (or WITH for CTEs)
- Block: INSERT, UPDATE, DELETE, DROP, ALTER, CREATE, ATTACH, PRAGMA, REPLACE
- Block semicolons (no multi-statement)
- Only whitelisted tables (10 cache tables + sync_history)
- Auto-append `LIMIT 100` if no LIMIT clause present
- Max query length: 2000 chars

### Step 4: API Router

**`src/api/routers/chat.py`** — Following existing router pattern:
```python
router = APIRouter(prefix="/api/chat", tags=["chat"])

@router.post("/stream")
@limiter.limit("20/minute")
async def stream_chat(request: Request, body: ChatRequest, current_user = Depends(get_current_user)):
    """SSE streaming chat endpoint."""
    # Returns StreamingResponse with text/event-stream
    # Body: { messages: [...], mode: "mto"|"analytics", mto_context?: {...} }

@router.get("/status")
async def chat_status(request: Request):
    """Returns { available: bool, model: str }"""
```

**`ChatRequest` model** (in same file or models):
```python
class ChatRequest(BaseModel):
    messages: list[dict]          # [{role, content}, ...]
    mode: str = "mto"             # "mto" or "analytics"
    mto_context: Optional[dict]   # Current MTO data from dashboard (for mto mode)
```

**SSE response format** (server → client):
```
data: {"type": "token", "content": "partial text"}

data: {"type": "sql", "query": "SELECT ..."}

data: {"type": "sql_result", "columns": [...], "rows": [...]}

data: {"type": "error", "message": "..."}

data: {"type": "done"}
```

**Analytics mode flow** (in router):
1. Send user message + schema prompt to DeepSeek
2. Collect full response (non-streaming for SQL)
3. Extract SQL from ```sql block
4. Validate with `sql_guard.validate_sql()`
5. Execute via `db.execute_read()`
6. Send SQL + results as SSE events
7. Send results back to DeepSeek for natural language summary
8. Stream the summary

**`src/main.py`** changes:
- Import `DeepSeekConfig` and `DeepSeekClient`
- In lifespan: `chat_client = DeepSeekClient(config.deepseek) if config.deepseek.is_available() else None`
- Register: `app.state.chat_client = chat_client`
- On shutdown: `if chat_client: await chat_client.close()`
- Import and register chat router

### Step 5: Frontend — Integrated Sidebar

**Layout architecture:**
```
<body>
  <div class="flex h-screen">
    <div class="flex-1 overflow-auto">   ← Existing dashboard (shrinks)
      <header>...</header>
      <main>...</main>
    </div>
    <div class="chat-sidebar">           ← NEW: Right sidebar
      ...
    </div>
  </div>
</body>
```

**Sidebar states:**
1. **Hidden** (no API key) — Nothing rendered, `x-if="chatAvailable"`
2. **Collapsed** — 48px icon strip on right edge, chat bubble icon
3. **Expanded** — 384px panel with header, messages, input

**`dashboard.html`** additions:
- Chat sidebar HTML after main content div
- Chat bubble toggle button (fixed position)
- Message list with auto-scroll
- Input area with send button and mode toggle
- Each message: role indicator, markdown-rendered content, clickable MTO links

**`dashboard.js`** additions to `mtoSearch()` state:
```javascript
// Chat state
chatAvailable: false,        // Set from /api/chat/status on init
chatOpen: false,             // Sidebar expanded
chatMessages: [],            // [{role, content, timestamp}]
chatInput: '',               // Current input text
chatLoading: false,          // Streaming in progress
chatMode: 'mto',            // 'mto' or 'analytics'
```

**Key JS methods:**
- `initChat()` — Check `/api/chat/status`, set `chatAvailable`
- `sendChat()` — POST to `/api/chat/stream`, read SSE via `fetch()` + `ReadableStream`
- `renderMtoLinks(text)` — Regex `AK\d{7,}` → clickable `<a>` that calls `searchMto(number)`
- `toggleChat()` — Open/close sidebar
- `clearChat()` — Reset conversation

**CSS additions (`main.css`):**
- `.chat-sidebar` — Fixed right, transition width, dark theme matching
- `.chat-message` — Bubble styling, user vs assistant differentiation
- `.chat-input` — Fixed bottom of sidebar, auto-resize textarea
- `.mto-link` — Clickable MTO number styling (underline, hover effect)

### Step 6: Tests

**`tests/unit/test_sql_guard.py`** — SQL validation:
- Valid SELECT queries pass
- INSERT/UPDATE/DELETE/DROP blocked
- Comment stripping works
- Table whitelist enforced
- LIMIT auto-appended
- Multi-statement blocked
- CTE (WITH) queries allowed
- Max length enforced

**`tests/unit/test_chat_context.py`** — Context builders:
- MTO context serialization
- Large data truncation
- Empty data handling
- SQL result formatting

**`tests/unit/test_chat_client.py`** — DeepSeek client:
- Mock `openai.AsyncOpenAI` to test stream_chat
- Error handling (connection, rate limit, timeout)
- Close cleanup

**`tests/api/test_chat_endpoints.py`** — API endpoints:
- `/api/chat/status` returns availability
- `/api/chat/stream` requires auth
- SSE response format validation
- Analytics mode SQL flow
- Error responses (no API key, bad request)

---

## Files Summary

| Action | File | Purpose |
|--------|------|---------|
| Create | `src/chat/__init__.py` | Package exports |
| Create | `src/chat/client.py` | DeepSeek client via `openai` SDK |
| Create | `src/chat/context.py` | MTO data & SQL result serializers |
| Create | `src/chat/prompts.py` | Chinese system prompts |
| Create | `src/chat/sql_guard.py` | SQL safety validation |
| Create | `src/api/routers/chat.py` | SSE streaming endpoint + ChatRequest model |
| Modify | `src/config.py` | Add `DeepSeekConfig`, update `Config` |
| Modify | `src/exceptions.py` | Add `ChatError` hierarchy |
| Modify | `src/main.py` | Init client, register router, shutdown cleanup |
| Modify | `src/frontend/static/js/dashboard.js` | Chat state, SSE streaming, MTO link rendering |
| Modify | `src/frontend/dashboard.html` | Chat sidebar HTML |
| Modify | `src/frontend/static/css/main.css` | Chat sidebar styles |
| Modify | `.env.example` | Add DEEPSEEK_* vars |
| Create | `tests/unit/test_sql_guard.py` | SQL guard tests |
| Create | `tests/unit/test_chat_context.py` | Context builder tests |
| Create | `tests/unit/test_chat_client.py` | Client tests |
| Create | `tests/api/test_chat_endpoints.py` | Endpoint tests |

---

## Key Design Decisions

1. **`openai` SDK** — DeepSeek is OpenAI-compatible; SDK handles SSE parsing, retries, error types. Already installed (v1.99.3). 80% less code than raw httpx.
2. **Integrated sidebar, not floating overlay** — Dashboard content shrinks via flex layout; sidebar is always accessible.
3. **Clickable MTO links** — Regex `AK\d{7,}` in responses become clickable links that load in dashboard.
4. **Icon strip when collapsed** — 48px strip always visible when API key configured.
5. **`fetch()` + `ReadableStream`** for SSE — Supports POST with JSON body + auth headers.
6. **Server-side SQL execution for analytics** — LLM generates SQL, server validates (sql_guard) and executes read-only.
7. **Graceful degradation** — No API key → `chatAvailable=false` → sidebar hidden entirely.
8. **No server-side conversation storage** — All state in Alpine.js. Server is stateless.
9. **Reuse slowapi** for rate limiting — No custom limiter; 20/min on the stream endpoint.
10. **Typed SSE events** — `{type: "token"|"sql"|"sql_result"|"error"|"done"}` for structured client handling.

---

## Acceptance Criteria
- [x] Chat sidebar opens/closes correctly with smooth transition
- [x] MTO mode streams responses with current MTO context
- [x] Analytics mode generates SQL, validates, executes, and summarizes
- [x] Clickable MTO links load data in dashboard
- [x] Graceful degradation without API key (sidebar hidden)
- [x] All new tests pass (45 new tests)
- [x] No regressions in existing test suite (310 → 355 total)
- [x] .env.example documents new DEEPSEEK_* variables
