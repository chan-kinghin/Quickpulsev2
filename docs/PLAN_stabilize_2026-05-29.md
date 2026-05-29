# Plan: Stabilize QuickPulse — reconnect safety nets + fix silent failures

## Status: Complete (2026-05-29) — all 4 stages shipped on feat/saas-ui-restyle (local, not pushed)

Commits: `49ddaaf` (Stage 1 CI+parity), `6753219` (Stage 2 export-default+stale tests),
`43a3a33` (Stage 3 字段不存在 raise), `b84435e` (Stage 4 md:inline + tailwind guard).
D1 resolved = export defaults to live (interactive GET stays cache). Full gating suite:
**1054 passed, 0 failed**. Product status decided: **ACTIVE** (legacy freeze rescinded).

> Context: 22-agent health audit (2026-05-29) found the codebase "lying about its own
> health" — CI never runs the real suite, the #1-bug-class guard is disconnected AND red,
> a day-one silent-swallow remains, and a shipped frontend element is invisibly hidden.
> Owner decided 2026-05-29: **QuickPulse is an ACTIVE product** (the "legacy" label is retired).
> This plan covers ONLY the 4 strategy-independent fixes. Architectural work (cache deletion
> vs converter, agent-KB delete/revive) is deferred to a separate active-product backlog.

## Design Spec

### Problem
Verified red/broken state on `feat/saas-ui-restyle` (and main):
1. `.github/workflows/ci.yml:13` installs deps via `pip install -e .`, but the Kingdee SDK is a
   **vendored wheel** (`sdk/python_sdk_v8.2.0/*.whl`) NOT in `pyproject` deps — only `docker/Dockerfile`
   installs it. `src/kingdee/client.py:20` imports it at module top → the gating `test` job's import
   chain breaks. Reproduced locally: `.venv` without the wheel → `ModuleNotFoundError`.
2. `ci.yml:15` runs `pytest tests/ --ignore=tests/e2e --ignore=tests/integration`. The #1-bug-class
   guard `tests/integration/test_cache_live_parity.py` is a **pure-mock dataclass test misfiled under
   integration/** → runs in NO CI job, and is currently RED.
3. **6 red tests** (confirmed via `.venv` after installing the wheel):
   - `test_cache_live_parity.py::test_no_unexpected_extra_fields` + `::test_field_count_matches`
     (`BOMJoinedRow has 25 fields, expected 22` — `material_group_name/category_name/is_purchase`
     added by commit `2724bcf` without bumping `EXPECTED_FIELDS`).
   - `test_mto_endpoints.py::test_get_mto_success` (stale call signature, missing `strict_aux=False`).
   - `test_mto_endpoints.py::test_get_mto_use_cache_false` + `test_export_uses_live_data_by_default`
     (**doc-vs-code contradiction** — see Decision D1).
   - `test_database.py::TestCacheOperations::test_upsert_on_conflict` (asserts pre-migration-010
     3-col `ON CONFLICT`; live schema is the correct 4-col per migration 010).
4. `src/kingdee/client.py:202` swallows `字段不存在` (missing field = always a config bug) into `[]`
   with only a WARNING. Root cause of bug-patterns Pattern 12 (2-day prod stale-data incident):
   `sync_service.py` can't distinguish `[]` from genuinely-empty → records `status="success"`.
5. `hidden md:inline` used 9× across 5 HTML files, but precompiled `tailwind.min.css` has no
   `md:inline` rule → those spans are `display:none` at every viewport (shipped UX regression).

### Solution (by stage)

**Stage 1 — Reconnect CI** (`ci.yml`)
- Add `pip install sdk/python_sdk_v8.2.0/*.whl` to the `test` and `typecheck` jobs (after `pip install -e .`).
- Move `tests/integration/test_cache_live_parity.py` → `tests/unit/test_cache_live_parity.py` so the
  gating job runs it (it's pure-mock, no creds). Keep `--ignore=tests/integration` (real-creds tier).
- (Optional, audit "low") add `pytest-timeout` to dev extras + `--timeout=60` to the test run.

**Stage 2 — Green the 6 red tests** (test files only, except D1)
- Parity: add `material_group_name`, `category_name`, `is_purchase` to `EXPECTED_FIELDS` (→25).
  First re-confirm all 3 are populated in factory (live) + cache_reader SELECT + sync INSERT — the audit
  says they are; verify, don't just silence.
- `test_get_mto_success`: add `strict_aux=False` to the expected mock call (pure rot).
- `test_upsert_on_conflict`: update `ON CONFLICT` to `(bill_no, mto_number, material_code, aux_prop_id)`
  matching `migrations/010`; add a `# Pattern 5` comment so it isn't reverted to the narrow key.
- **D1 (decision required)**: `use_cache` default for `/api/mto/{n}` + export. Router defaults `True`,
  docstring says "live by default for accuracy", 2 tests expect `False`. Options in "Decisions" below.

**Stage 3 — Fix the silent-swallow at source** (`src/kingdee/client.py`)
- Split `字段不存在` out of the line-202 branch: keep `msg_code == 4 or "业务对象不存在"` → `return []`
  (a missing/optional FORM legitimately returns empty), but for `字段不存在` → `logger.error(...)` and
  `raise KingdeeQueryError(...)`. Apply symmetrically to the dict-path branch (line 176) for consistency.
- This makes `sync_service` count the chunk as failed (it keys off raised exceptions) → `status="partial"`
  or `"error"` instead of a false `"success"`.

**Stage 4 — Fix md:inline silent-hide + add a guard** (`main.css`, `ci.yml`/script)
- Add the needed responsive utilities to the `@media (min-width:768px)` block in `main.css`
  (`.md\:inline{display:inline}`), OR replace `hidden md:inline` with a plain always-visible class.
- Add a CI grep-assert (small script) that fails if any `(sm|md|lg|xl):<class>` used in `src/frontend/*.html`
  has no matching rule in `tailwind.min.css`. Wire into `ci.yml` lint job.

### Files to Modify
```
.github/workflows/ci.yml                      (modify — Stages 1 & 4)
tests/integration/test_cache_live_parity.py   (move → tests/unit/)
tests/unit/test_cache_live_parity.py          (create via move + edit EXPECTED_FIELDS)
tests/api/test_mto_endpoints.py               (modify — Stage 2)
tests/integration/test_database.py            (modify — Stage 2)
src/api/routers/mto.py                         (modify — ONLY if D1 = flip default to live)
src/kingdee/client.py                          (modify — Stage 3)
tests/unit/test_kingdee_client.py              (modify/create — assert 字段不存在 raises)
src/frontend/static/css/main.css               (modify — Stage 4)
scripts/check_tailwind_classes.sh              (create — Stage 4 guard)
pyproject.toml                                 (modify — optional pytest-timeout)
```

## Decisions Required
- **D1 — export/MTO `use_cache` default**: Now that QP is "active" and the docstring promises accuracy,
  (a) **flip router default to `use_cache=False`** (matches docstring + tests; every query hits Kingdee
  live, ~1–5s; closes the contradiction in the accurate direction) — *but* raises load + needs a glance at
  the CVM 512M ceiling; OR (b) **keep cache-default, fix the docstring + 2 tests** (fast, but the "live for
  accuracy" promise is abandoned). Recommend (a) for a 12-user tool unless latency/load is a known concern.

## Test Cases
### Unit / Integration
- [ ] `pytest tests/ --ignore=tests/e2e --ignore=tests/integration -q` exits 0 with the SDK wheel installed.
- [ ] `test_cache_live_parity.py` (now in tests/unit) passes (3 fields registered, count 25==25).
- [ ] `test_mto_endpoints.py` all green (signature + D1 resolution).
- [ ] `test_database.py::test_upsert_on_conflict` green against 4-col UNIQUE.
- [ ] New: `字段不存在` Kingdee error → `KingdeeQueryError` raised (not `[]`); `业务对象不存在`/MsgCode 4 → `[]`.
### Manual Verification
1. Push branch → GitHub Actions `test` job runs the full unit suite (not 0 collected) and is green.
2. Load `/dashboard` at ≥768px width → date/timestamp span + "退出" label are visible.
3. `scripts/check_tailwind_classes.sh` exits non-zero if a used responsive class is missing from the bundle.

## Acceptance Criteria
- [ ] `ci.yml` `test` job installs the SDK wheel and executes the unit suite (verifiable: job log shows >0 tests).
- [ ] 0 red tests in the gating tier; the cache==live parity guard runs IN that tier.
- [ ] `字段不存在` no longer silently returns `[]` (covered by a test).
- [ ] `md:inline` elements render at md+ breakpoints; the tailwind-class guard is wired into CI.
- [ ] D1 resolved and reflected in router default + docstring + tests (all consistent).

## Out of Scope (deferred — active-product backlog, separate plans + approval)
- Cache deletion vs `BOMJoinedRow`-aggregator unification (XL; needs CVM memory/latency load-test first).
- Delete or wire-in the ~1,800-line orphaned agent knowledge base (`src/agents/knowledge/`).
- Frontend BOM-table 5–7 parallel-list consolidation (`dashboard.js`/`.html`).
- `prompts.py` routing-anti-pattern cleanup; security hardening (cookie flags, sanitize_query, rate-limit).
- Drop the "legacy" framing from `CLAUDE.md` + reconcile `memory/feedback_query_strategy.md` (trivial; do alongside).
