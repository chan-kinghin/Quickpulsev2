# Plan: Unify chat modes + document FStatus enum + rename MTO → 计划跟踪号

## Status: Awaiting Approval (expanded from original scope 2026-05-12)

## Problem

Single user-visible question — "最近一周有多少个MTO在生产?" — exposed three coupled defects:

1. **Silent enum hallucination (FStatus)** — Neither 简单 nor 智能 chat prompt enumerates `cached_production_orders.status` values. Storage holds Kingdee numeric codes `'1'..'6'` (`docs/MTO_CONFIG_GUIDE.md:77`, `factory.py:271`). LLM invented `'已审核'/'进行中'/'已完成'` (简单 → 0 rows) or `'in_production'/'started'/'processing'` (智能 → 848, also wrong — `NOT IN` against fictional enums matched everything). **Correct answer = 48 distinct 计划跟踪号** (`status='4'`, last 7d, verified against local cache).

2. **Two modes drift on the same schema** — `src/chat/prompts.py` (one-shot SQL) and `src/agents/chat/prompts.py` (dual-agent) declare the same tables independently. Same Pattern 9 fix must be applied twice and stays out of sync. User decision: **merge into one mode** (智能 only).

3. **Term inconsistency** — UI mixes "MTO", "MTO单号", "MTO跟踪号", "计划跟踪号" for the same concept. User decision: **rename user-facing strings to 计划跟踪号** (code identifiers like `mtoNumber`, `/api/mto/{mto_number}` stay — API stability).

This is the **4th recurrence of Pattern 9 (Agent Prompt Schema Drift)** plus an architectural unification.

## Design Spec

### FStatus enum (canonical — source: `docs/MTO_CONFIG_GUIDE.md:77-85`)

| Code | Chinese | Business phrase the LLM will see |
|------|---------|----------------------------------|
| `'1'` | 计划 | "已计划" |
| `'2'` | 计划确认 | "已确认" |
| `'3'` | 下达 | "已下达" |
| `'4'` | **开工** | **"在生产" / "进行中"** |
| `'5'` | 完工 | "已完工" |
| `'6'` | 结案 | "已结案" |

Prompt convention to encode:
- `status TEXT` — Kingdee FStatus numeric code, stored as string
- "在生产 / 进行中" → `status = '4'`
- "已完工" → `status = '5'`
- "活跃订单（含已下达至完工）" → `status IN ('3','4','5')`
- ⚠️ MUST quote: `status='4'` not `status=4`

### Mode unification

Per user decision: **delete the 简单 path entirely**. Route everything through the 智能 (dual-agent) pipeline.

The "多Agent协作分析" tab visible in the screenshot is just a **label** for agent mode, not a separate pipeline (audit confirmed). After this change, the tab toggle goes away — there is one chat path.

### MTO → 计划跟踪号 rename scope (user-facing only)

| Surface | Files | Refs |
|---------|-------|------|
| Frontend UI | `src/frontend/dashboard.html`, `src/frontend/static/js/dashboard.js` | ~10 |
| Agent prompts | `src/agents/chat/prompts.py` | 5 |
| API docs | `docs/API_REFERENCE.md` | 8 |
| Internal reports | `docs/金蝶数据异常综合报告_20260130.md`, `docs/超领异常报告_20260130.md` | ~20 |
| Memory | `~/.claude/.../memory/MEMORY.md`, `memory/bug-patterns.md` | scattered |

**Code identifiers stay untouched** — `mtoNumber`, `mto_number`, `MTOStatusResponse`, `/api/mto/{mto_number}`, `cached_*` column names, Kingdee field names (`FMtoNo`, `FMTONo`). Renaming those would be a multi-day diff with API-breakage risk and zero user-facing benefit.

**Special case** (`dashboard.html:150`): the inline badge `<span>MTO</span>` is too short to fit "计划跟踪号" without layout overflow. Use **"计划"** (3 chars) — keeps the badge tight while staying in-language.

### Architecture after this change

```
Before:                          After:
┌─────────────┐                  ┌─────────────────┐
│ Tab: 简单    │→ /api/chat      │ (single chat)   │
│ Tab: 智能    │→ /api/agent-chat│  → /api/agent-chat
│ Tab: 多Agent│→ /api/agent-chat└─────────────────┘
└─────────────┘                  src/chat/ deleted
src/chat/ exists                 src/agents/tools/sql_guard.py (migrated)
src/agents/ exists               src/agents/tools/context.py (migrated)
DeepSeekConfig in config.py      DeepSeekConfig removed
```

## File Ownership for Wave 2 (parallel subagents — disjoint file sets)

### Agent 2A: Backend cleanup + agent prompt edits
**Owns:**
- `src/chat/sql_guard.py` → MIGRATE to `src/agents/tools/sql_guard.py`
- `src/chat/context.py` → MIGRATE to `src/agents/tools/context.py`
- `src/chat/*` (other files) → DELETE entire package
- `src/api/routers/chat.py` → DELETE
- `src/main.py` → remove chat router import + `app.include_router(chat.router)` + DeepSeek provider init block (lines 38, 39, 154–166, 322)
- `src/config.py` → remove `DeepSeekConfig` class (lines 118–146) and its `deepseek` field reference
- `src/agents/tools/schema_lookup.py` → update `from src.chat.sql_guard import` → `from src.agents.tools.sql_guard import`
- `src/agents/tools/sql_query.py` → same import fix for both `sql_guard` and `context`
- `src/agents/chat/prompts.py` → ADD FStatus enum block in both RETRIEVAL_AGENT_PROMPT and REASONING_AGENT_PROMPT; rename 5 MTO refs to 计划跟踪号
- `tests/unit/test_chat_*.py` → DELETE
- `tests/api/test_chat_endpoints.py` → DELETE
- `tests/unit/test_sql_guard.py` → MOVE to `tests/unit/test_agents_sql_guard.py` + fix import

### Agent 2B: Frontend mode-merge + label rename
**Owns:**
- `src/frontend/dashboard.html`:
  - Lines 897–909 → DELETE chat mode toggle (`简单`/`智能` buttons)
  - Line 914 → DELETE provider selector conditional (only relevant to simple mode)
  - Line 923 → hard-code label to `多Agent协作分析`
  - Lines 62, 73, 126, 846, 854, 855, 867, 949, 957 → rename "MTO" / "MTO单号" → "计划跟踪号"
  - Line 150 → rename badge "MTO" → "计划" (short form, layout constraint)
- `src/frontend/static/js/dashboard.js`:
  - Line 86 → delete `chatMode: 'simple'` default; remove `chatMode` state entirely OR hard-set to `'agent'`
  - Lines 1066–1083 → DELETE `switchChatMode()` function
  - Line 1172 → hard-route to `/api/agent-chat/stream`
  - Lines 649/653/914/923/1059 → remove `agentChatAvailable` fallback branches

### Agent 2C: Docs + memory + new enum guard tests
**Owns:**
- `docs/API_REFERENCE.md` → 8 MTO renames
- `docs/金蝶数据异常综合报告_20260130.md` → ~10 MTO renames (table headers, section titles)
- `docs/超领异常报告_20260130.md` → ~10 MTO renames
- `~/.claude/projects/-Users-kinghinchan-Documents-Cursor-Projects-Quickpulsev2-Quickpulsev2/memory/MEMORY.md` → remove "Chat Feature (DeepSeek LLM)" section (lines ~63–73); update Agent Pipeline section to drop benchmark-comparison wording; rename incidental MTO references
- `~/.claude/.../memory/bug-patterns.md` → append Pattern 9 occurrence 2026-05-12 with full reproducer evidence; tighten prevention rule to require enum docs for TEXT columns with bounded value sets
- `tests/unit/test_prompt_schema_sync.py` → add 4 new tests:
  1. `test_status_enum_documented_in_retrieval_agent_prompt` — codes `'1'..'6'` all present
  2. `test_status_enum_documented_in_reasoning_agent_prompt` — codes `'1'..'6'` all present
  3. `test_business_phrase_in_production_mapping` — "在生产" within 200 chars of `'4'` in each prompt
  4. `test_simple_chat_prompts_removed` — assert `src/chat/prompts.py` no longer exists (regression-proof the mode merge)

### What no agent touches in Wave 2 (deliberately)
- `scripts/benchmark_chat_pipelines.py`, `scripts/evaluate_quality.py` — both compare simple vs agent. Flagged for separate decision (retire vs rewrite). Out of scope.
- `src/query/mto_handler.py`, `src/readers/*` — no change.
- Database schema, migrations, sync logic — unchanged.

## Test Cases

### Unit (auto-runnable)
- [ ] `pytest tests/unit/test_prompt_schema_sync.py -v` — 4 new tests pass
- [ ] `pytest tests/unit/test_agents_sql_guard.py -v` — migrated test passes at new path
- [ ] `pytest tests/ --ignore=tests/e2e --ignore=tests/integration` — full unit suite green (no leftover imports from deleted `src/chat/`)
- [ ] `grep -r "from src.chat" src/ tests/` — returns zero matches

### Manual (after merge + local server restart)
1. Open `http://localhost:8000` — confirm chat panel has **no** 简单/智能 toggle buttons; only the "多Agent协作分析" label remains.
2. Search box shows "**计划跟踪号**" not "MTO单号".
3. Ask "**最近一周有多少个计划跟踪号在生产?**" → expect SQL `WHERE status='4' AND create_date >= date('now','-7 days')` → expect **~48 distinct 计划跟踪号**.
4. Ask "**已完工但未结案的有多少?**" → expect SQL with `status='5'` (or `status IN ('5')`).
5. Verify no JS console errors (no calls to `/api/chat/stream`, no references to undefined `chatMode`).

## Acceptance Criteria

- [ ] Reproducer question returns 48 (±a few; depends on which interpretation of "在生产" the LLM picks, but must be in the right order of magnitude — NOT 0 and NOT 848)
- [ ] `pytest tests/unit/` exits 0
- [ ] `grep -r "MTO" src/frontend/ src/agents/chat/prompts.py` returns only allowed technical refs (PRD_MO, FMtoNo, code identifiers — none in visible strings)
- [ ] `ls src/chat/` returns "No such file or directory"
- [ ] memory/bug-patterns.md Pattern 9 has 2026-05-12 entry
- [ ] No `from src.chat` imports anywhere in `src/` or `tests/`

## Out of Scope (explicit non-goals)

- Renaming code identifiers (`mtoNumber`, `mto_number`, etc.)
- Renaming API routes (`/api/mto/{mto_number}`)
- Renaming column names in `cached_*` tables (would require schema migration)
- Renaming Kingdee field names (`FMtoNo`, `FMTONo`) — those are external
- Retiring or rewriting `scripts/benchmark_chat_pipelines.py` and `scripts/evaluate_quality.py`
- Removing `DEEPSEEK_*` env vars from `/opt/ops/secrets/quickpulse/{prod,dev}.env` — separate CVM op
- Investigating why 智能 mode returned 848 (per user: patch enum + verify, no forensic)

## Risk + Mitigation

| Risk | Mitigation |
|------|------------|
| Deleting `DeepSeekConfig` breaks startup if agents secretly fall back to it | Audit confirmed agents use independent `AgentLLMConfig` (per memory + `src/config.py:185`). Test before commit. |
| `sql_guard.py` migration leaves stale imports | Agent 2A runs `grep -r "from src.chat" src/ tests/` as its final step. CI test asserts zero matches. |
| Frontend `chatMode` removal breaks existing user sessions with persisted preferences | Audit `dashboard.js` localStorage keys; clear if needed. (Memory's `STORAGE_VERSION` mechanism already covers this — bump if `chatMode` is in saved state.) |
| Memory file edits drift from actual repo state | Wave 2C subagent must verify before writing; cross-check with grep on the final repo. |

## Estimated Scope

- ~800 lines deleted (`src/chat/`)
- ~50 lines deleted in `main.py` + `config.py` + frontend
- ~80 lines added (FStatus enum docs in both agent prompts + 4 new test cases)
- ~50 string renames across docs + frontend + agent prompt
- 3 parallel subagents, ~15 min each, ~15 min merge + verification = ~45 min wall clock

## Dispatch Order

1. **NOW**: Get user approval on this updated plan
2. **Wave 2 parallel**: dispatch Agent 2A, 2B, 2C concurrently with `isolation: "worktree"`
3. **Merge gate**: verify each worktree's diff before merging into main; run `git diff` after each merge
4. **Test gate**: `pytest tests/unit/` must pass before declaring done
5. **Manual verify**: local server + reproducer question
6. **Commit + deploy**: one commit per agent + final integration commit; deploy to dev (`/opt/ops/scripts/deploy.sh quickpulse dev`) and re-test on https://dev.fltpulse.szfluent.cn
