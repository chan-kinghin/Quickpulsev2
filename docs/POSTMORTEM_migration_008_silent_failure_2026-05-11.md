# Postmortem: Migration 008 silent failure on legacy dev DBs (2026-03-20 → 2026-05-11)

**Discovered**: 2026-05-11, while running a manual sync to backfill `material_group_name` cache data.
**Affected**: Local dev DBs created before 2026-03-16 (when `schema.sql` first added inline `UNIQUE` to cached_* tables).
**Production impact**: None (prod was hand-rebuilt on 2026-03-20). See "What saved prod" below.
**Duration on dev**: ~52 days of silent auto-sync failures.

## Summary

Migration 008 (2026-03-20, commit `bf386c1`) dropped unique INDEXES previously
created by migrations 001/004. The author's stated reason — `schema.sql`'s
inline `UNIQUE(...)` makes the index redundant — is correct for **fresh** DBs.
On **legacy** DBs whose `CREATE TABLE` predates the inline UNIQUE (added in
`schema.sql` on 2026-03-16, commit `d2d9172`), the inline UNIQUE simply doesn't
exist: SQLite doesn't retroactively apply `CREATE TABLE` constraints to
already-existing tables.

After migration 008 ran on those DBs, the upsert pattern
`INSERT … ON CONFLICT(…) DO UPDATE` had no matching unique constraint to target
and failed with:

```
sqlite3.OperationalError: ON CONFLICT clause does not match any PRIMARY KEY or
UNIQUE constraint
```

Every scheduled sync (07:00 / 12:00 / 16:00 / 18:00 daily) then failed. The
dashboard kept rendering data from stale cache. Nobody noticed for 52 days.

## Timeline

| Date | Event |
|---|---|
| 2026-01-18 | Initial `schema.sql` lands without inline UNIQUE constraints on `cached_*` tables |
| 2026-01-19 → 2026-02-11 | Migrations 001 / 004 add unique INDEXES (`idx_bom_unique`, etc.) — upserts work via these |
| 2026-02-19 | Last successful sync on user's local dev DB |
| 2026-03-16 (`d2d9172`) | `schema.sql` updated: inline `UNIQUE(mo_bill_no, material_code, aux_prop_id)` added so fresh DBs get a wider 3-column key |
| **2026-03-20 (`bf386c1`)** | **Migration 008 added — drops `idx_bom_unique` and 7 other indexes.** Author tested on a fresh DB. Legacy dev DBs lose their only unique constraint. |
| 2026-03-20 ~ 2026-05-11 | Auto-sync fails 4× daily on legacy DBs. `WARNING ... serving stale cache data` log line goes unread. Prod *would* have failed too, but was hand-rebuilt the same day (we see a `quickpulse.db.bak` from 2026-03-20 15:45 in the prod volume — someone caught it manually) |
| 2026-05-11 | Manual sync attempted while testing `material_group_name`; ON CONFLICT error finally surfaces |

## Root causes

### 1. SQLite-specific footgun
`ALTER TABLE ADD CONSTRAINT` is a Postgres pattern. SQLite has no equivalent;
adding `UNIQUE(...)` inside `CREATE TABLE` only affects DBs created from that
point forward. Existing DBs need a `CREATE UNIQUE INDEX` to gain the constraint.

Migration 008's commit message even hints at the assumption that bit it:
> "On fresh databases, both run, creating TWO conflicting unique constraints."

The author was only thinking about fresh DBs. There was no "on legacy DBs the
index IS the only constraint we have" sentence.

### 2. No upgrade-path tests
CI runs `pytest tests/...` against a brand-new DB each run. Migrations are
exercised in the order: fresh schema.sql → run all migrations → run tests. The
**upgrade path** — start from an older DB snapshot, apply migrations forward —
is not tested.

A test that loaded a pre-2026-03-16 `cached_production_bom` (no inline UNIQUE),
applied migration 008, then attempted a sync upsert would have caught this in
seconds.

### 3. Silent sync failures
The scheduler logs `ERROR` + `WARNING serving stale cache data` lines for every
failure, but:
- No alerting wired to those log lines
- `/health` only checked DB connectivity, not sync freshness
- Dashboard happily serves stale cache; users see no degradation

50 days × 4 syncs/day = 200 failed syncs no human noticed.

### 4. What saved prod
Forensics: `/var/lib/docker/volumes/prod_qp-prod-data/_data/` contains
`quickpulse.db.bak` dated `2026-03-20 15:45`. Migration 008 commit lands the
same day at 16:38 CST. Someone (likely the migration author themselves) noticed
the upsert error on prod, backed up the DB, and rebuilt it from scratch using
the new `schema.sql`. So prod ran on a clean DB while the migration's design
flaw stayed latent on every legacy dev environment.

## Fix shipped today

1. **Migration 014** (`014_heal_stale_unique_indexes.sql`): idempotently recreates
   all 9 unique indexes using `CREATE UNIQUE INDEX IF NOT EXISTS … _v2`.
   No-op on healthy DBs; heals legacy DBs.
2. **`/health` exposes sync staleness**: `last_success_age_seconds`,
   `last_error_message`. Returns 503 when last success > 24h ago. Tested in
   `tests/api/test_health_sync_staleness.py`.

## Recommended follow-ups (not done today)

- **Migration upgrade-path tests**. Snapshot 2-3 historical `quickpulse.db`
  states (post each major schema change), add `tests/database/test_upgrade_path.py`
  that runs migrations forward against each and verifies a representative
  upsert succeeds. This is the test that would have caught 008 pre-merge.
- **Auto-sync alert wiring**. The `/health` endpoint now exposes staleness, but
  nothing currently scrapes it. Wire to Loki/Grafana or run a cron probe.
- **Migration template**: when an SRE writes a migration that DROPs or REPLACEs
  a constraint, the template should force them to answer "does this need a
  matching CREATE step for older DBs that won't get the new constraint from
  schema.sql?" — even just a checkbox prompts the thought.
