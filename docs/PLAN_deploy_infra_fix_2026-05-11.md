# Plan: Fix Deploy Infrastructure (Root Cause)

## Status: Not Started — awaiting approval

## Problem statement

Today (2026-05-11) the CD workflow failed because `/opt/ops/scripts/deploy.sh` didn't exist. A subagent audit revealed the actual situation is **not** "deploy.sh was deprecated and replaced":

| Reality | Implication |
|---|---|
| `deploy.sh.deprecated-2026-04-28` is the **build-from-source** script | Still works; I used it today for the dev + prod quickpulse deploys |
| `deploy-pull.sh` is jiejiawater-only (11+ hardcoded refs) | "deploy-pull" sounds generic but it isn't |
| 3 of 4 apps (`quickpulse`, `fluent-skills`, `autoresearch`) need build-from-source | `deploy-pull.sh` can't deploy any of them |
| Only `jiejiawater` uses pull-from-GHCR | That's the only app `deploy-pull.sh` serves |
| `cd.yml:37` still calls `/opt/ops/scripts/deploy.sh quickpulse <env>` | Always 404s — CD has been broken since the rename |
| `rollback.sh` calls `deploy-pull.sh` (jiejia-only) | Quickpulse rollback path is broken too |
| CLAUDE.md still documents `deploy.sh` as canonical | Docs match what SHOULD exist, not what does |

**No PR, no commit, no CHANGELOG explains the rename.** Appears to be a CVM-side action taken in haste — perhaps after a successful jiejiawater migration to GHCR — without follow-through on the CI workflow or the other apps.

## Root causes

1. **Premature deprecation**: `deploy.sh` was marked `.deprecated-YYYY-MM-DD` based on a false assumption that `deploy-pull.sh` would replace it universally. It can't — `deploy-pull.sh` is structurally jiejia-only.

2. **Misleading naming**: `deploy-pull.sh` sits in a generic path (`/opt/ops/scripts/`) with a generic name. The name implies "deploy by pulling images" (universal); the implementation is "deploy jiejiawater by pulling from ghcr.io" (specific).

3. **CI workflow drift**: `cd.yml` was never updated when CVM-side files moved. There's no CI test that exercises the deploy script, so the breakage went unnoticed for 2 weeks.

4. **No dispatcher pattern**: With 4 apps using 2 different strategies (build vs pull), the right shape is a thin dispatcher (`deploy.sh`) that delegates to per-app scripts (`deploy-build.sh`, `deploy-pull.sh`). Today there's no dispatcher — each script tries to be universal but isn't.

## Proposed fix

### Step 1 — Rename on CVM (atomic, reversible)

```bash
# Un-deprecate the build-from-source script — it's still in active use
mv /opt/ops/scripts/deploy.sh.deprecated-2026-04-28 /opt/ops/scripts/deploy-build.sh

# Clarify that deploy-pull.sh is jiejia-only
mv /opt/ops/scripts/deploy-pull.sh /opt/ops/scripts/deploy-jiejia.sh

# Clean up obsolete backups
mv /opt/ops/scripts/deploy.sh.bak.1777286901 /opt/ops/scripts/_archive/
mv /opt/ops/scripts/deploy-pull.sh.bak /opt/ops/scripts/_archive/
```

### Step 2 — Write a thin dispatcher `deploy.sh`

`/opt/ops/scripts/deploy.sh` becomes a 20-line router:

```bash
#!/usr/bin/env bash
# Universal deploy entry-point. Routes to the per-app strategy.
# Usage: deploy.sh <app> <env> [tag]
#   app:  quickpulse | fluent-skills | autoresearch | jiejiawater
#   env:  prod | dev
#   tag:  (optional, only used by jiejiawater for GHCR image tag)
set -euo pipefail

APP="${1:?Usage: $0 <app> <env> [tag]}"

case "$APP" in
  jiejiawater)
    exec /opt/ops/scripts/deploy-jiejia.sh "$@"
    ;;
  quickpulse|fluent-skills|autoresearch)
    exec /opt/ops/scripts/deploy-build.sh "$@"
    ;;
  *)
    echo "ERROR: unknown app '$APP'. Supported: quickpulse, fluent-skills, autoresearch, jiejiawater" >&2
    exit 2
    ;;
esac
```

This restores the contract `cd.yml` expects (`deploy.sh quickpulse dev`) without any CI changes.

### Step 3 — Fix `rollback.sh` to dispatch too

`rollback.sh` currently calls `deploy-pull.sh` unconditionally. Update it to use the same case-statement pattern:

```bash
case "$APP" in
  jiejiawater) exec /opt/ops/scripts/deploy-jiejia.sh "$APP" "$ENV" "$PREV_TAG" ;;
  *)           exec /opt/ops/scripts/deploy-build.sh "$APP" "$ENV" ;;  # build script accepts no tag arg
esac
```

(The build script uses git refs, not tags, so it rolls back by checking out the previous commit instead.)

### Step 4 — Document in repo

Add `docs/CVM_DEPLOY_SCRIPTS.md` covering:
- Which app uses which strategy (build vs pull) and why
- The dispatcher pattern (`deploy.sh` → `deploy-{build,jiejia}.sh`)
- How to add a 5th app (drop into the build path by default; add a case for special strategies)
- Where to find each script and how to test changes
- Rollback semantics per strategy

Update `CLAUDE.md` (the project one) to point at the new doc.

### Step 5 — Add a thin guard against silent breakage

Add a step to `cd.yml` BEFORE the deploy action that confirms the script exists:

```yaml
- name: Verify deploy script exists
  uses: appleboy/ssh-action@v1
  with:
    host: ${{ secrets.CVM_HOST }}
    username: ${{ secrets.CVM_USER }}
    key: ${{ secrets.CVM_SSH_KEY }}
    script: test -x /opt/ops/scripts/deploy.sh || (echo 'FATAL: deploy.sh missing on CVM' && exit 1)
```

Without this, future renames will silently fail again. With it, the CD workflow fails at the verification step with a clear error.

### Step 6 — Verify

After all changes:
1. `gh workflow run cd.yml -f environment=dev` → expect success, expect `quickpulse-dev` container restart
2. `gh workflow run cd.yml -f environment=prod` → expect success
3. Verify the deployed JS shows the latest commit's code (e.g., `inlinePhotoOpen` for current state)
4. Run the e2e Playwright suite against both environments to prove end-to-end

## Files to modify

### CVM (via Aliyun RunCommand)
- `/opt/ops/scripts/deploy.sh.deprecated-2026-04-28` — rename to `deploy-build.sh`
- `/opt/ops/scripts/deploy-pull.sh` — rename to `deploy-jiejia.sh`
- `/opt/ops/scripts/deploy.sh` — **new** 20-line dispatcher
- `/opt/ops/scripts/rollback.sh` — update case-statement to dispatch
- `/opt/ops/scripts/_archive/` — **new** dir; move `.bak` files there
- `/opt/ops/scripts/README.md` — **new** quick reference

### Repo
- `.github/workflows/cd.yml` — add the existence-check step before deploy
- `docs/CVM_DEPLOY_SCRIPTS.md` — **new** documentation
- `CLAUDE.md` — update the "Deploying" section to point at the new doc

## Acceptance criteria

- [ ] `gh workflow run cd.yml -f environment=dev` succeeds, builds + restarts `quickpulse-dev` from current `main`
- [ ] `gh workflow run cd.yml -f environment=prod` succeeds, builds + restarts `quickpulse-prod` from current `main`
- [ ] Pushing to `develop` (if it exists; falls back to `main`) auto-deploys dev
- [ ] `deploy.sh jiejiawater <env>` still works (routes to deploy-jiejia.sh)
- [ ] `deploy.sh quickpulse <env>` works directly on CVM (routes to deploy-build.sh)
- [ ] `deploy.sh nonexistent-app <env>` exits 2 with a clear error
- [ ] Verify-script step in CI catches a future rename
- [ ] CLAUDE.md "Deploying" section reflects reality

## Estimated effort

| Step | Effort |
|---|---|
| Rename scripts on CVM | 5 min |
| Write dispatcher | 10 min |
| Update rollback.sh | 15 min |
| Update cd.yml with guard step | 10 min |
| Write CVM_DEPLOY_SCRIPTS.md | 30 min |
| Update CLAUDE.md | 5 min |
| End-to-end verification | 20 min |
| **Total** | **~95 min** |

## Risk / blast radius

- **CVM script renames are reversible** — `mv` is atomic, and we keep backups in `_archive/`
- **The dispatcher pattern is additive** — calling `deploy.sh quickpulse dev` keeps working before AND after (the old path was the deprecated script we're just re-exposing under a thin layer)
- **rollback.sh change is the riskiest** — it affects rollback flow. Test in dev first.
- **No data migration, no DB changes** — pure deploy plumbing.

## Out of scope (deliberately, can do later)

- Refactoring `deploy-jiejia.sh` to use less hardcoding (it works for its app; not blocking)
- Migrating quickpulse to GHCR-pull (would simplify CVM resource use but is a separate decision)
- Removing the orphan jiejia .env backups in `/opt/ops/secrets/jiejiawater/`
- Adding healthcheck assertions to the build script (it has some; could be stricter)
