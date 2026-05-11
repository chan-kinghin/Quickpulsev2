# CVM Deploy Scripts

The shared Aliyun CVM (`121.41.81.36`) hosts four apps under `/opt/ops/apps/`. This doc covers how each gets deployed.

## TL;DR

```bash
# Single entry point — works for every app:
/opt/ops/scripts/deploy.sh <app> <env> [tag]

# Examples
deploy.sh quickpulse dev          # build quickpulse-dev from main
deploy.sh quickpulse prod         # build quickpulse-prod from main
deploy.sh jiejiawater prod abc123 # pull jiejia GHCR image tagged abc123
deploy.sh fluent-skills dev       # build fluent-skills-dev
```

The GitHub Actions CD workflow (`.github/workflows/cd.yml`) calls exactly this.

## The script directory

```
/opt/ops/scripts/
├── deploy.sh                 # ← Universal dispatcher. Always call this.
├── deploy-build.sh           # Build-from-source strategy
├── deploy-jiejia.sh          # Pull-from-GHCR strategy (jiejiawater only)
├── rollback-jiejia.sh        # Re-deploy jiejiawater at previous tag
├── smoke-test-jiejia.sh      # Called internally by deploy-jiejia.sh
├── README.md                 # CVM-side quick reference
└── _archive/                 # historical backups
```

## Strategy per app

| App | Strategy | Dockerfile | Container name | Why |
|---|---|---|---|---|
| **quickpulse** | build | `repo/docker/Dockerfile` | `quickpulse-{env}` | Single FastAPI service; no separate CI image pipeline |
| **fluent-skills** | build | `repo/Dockerfile` | `fluent-skills-{env}` | Same shape as quickpulse |
| **autoresearch** | build | `repo/Dockerfile` | `autoresearch-{streamlit,wecom-bot}` | Same shape; prod-only (no dev env) |
| **jiejiawater** | pull | (built in CI, pushed to GHCR) | `jiejia-{api,admin}-{env}` | Two services, separate image pipeline, GHCR is the source of truth |

## Build strategy (`deploy-build.sh`)

For build-strategy apps, deploy flow is:

1. Save current container image IDs for rollback
2. (prod only) Trigger pre-deploy backup at `/opt/ops/backups/`
3. `cd /opt/ops/apps/<app>/<env>/repo && git fetch && git reset --hard origin/<branch>`
4. `cd /opt/ops/apps/<app>/<env> && docker compose build`
5. `docker compose up -d`
6. Health check (5 retries × 30 s)
7. Run repo's `scripts/pre_deploy_smoke.sh` if present
8. Image cleanup (`docker image prune`)
9. Auto-rollback to saved image IDs on any failure

Branch selection: `dev` env tries `develop` first, falls back to `main` if `develop` doesn't exist. `prod` always uses `main`.

## Pull strategy (`deploy-jiejia.sh`)

For jiejiawater only:

1. Save current `IMAGE_TAG` from running container to `.last-deploy`
2. Pull `ghcr.io/chan-kinghin/jiejiawater-{api,admin}:<tag>` (default `latest`)
3. Local-build fallback if GHCR pulls fail (cn-hangzhou ↔ ghcr.io throughput drops periodically)
4. Recreate `jiejia-{api,admin}-{env}` containers via compose
5. Run prisma migrate inside the api container
6. Health check on the api container (port 3000)
7. Call `smoke-test-jiejia.sh` for HTTP-level + Playwright-level checks

## Rollback semantics

| App | Method |
|---|---|
| **jiejiawater** | `rollback-jiejia.sh jiejiawater <env>` — reads `.last-deploy`, redeploys at that GHCR tag |
| **build-strategy apps** | `git revert <bad-commit>` on the repo's `main`/`develop` branch, then re-run `deploy.sh <app> <env>`. The build script ALSO does in-flight auto-rollback if the new build fails its health check, restoring the previous container image. |

## What the CI/CD workflow does

`.github/workflows/cd.yml` triggers on:

- **Push to `develop`** → auto-deploys to dev
- **Manual dispatch** → choose `dev` or `prod`

Three steps:

1. **Determine environment** — picks `dev` for push, `inputs.environment` for manual dispatch
2. **Verify deploy script exists** — SSHes to CVM, fails fast if `/opt/ops/scripts/deploy.sh` is missing or non-executable. **Added 2026-05-11** after the silent-CD-failure incident.
3. **Deploy to CVM** — SSHes again and runs `deploy.sh quickpulse <env>`

The workflow only deploys quickpulse. Other apps have their own CD workflows in their own repos.

## Adding a new app

1. **If build-strategy** (most cases):
   - Create `/opt/ops/apps/<new-app>/{dev,prod}/docker-compose.yml` with a `build:` clause pointing at `./repo`
   - `git clone` your app into `/opt/ops/apps/<new-app>/{dev,prod}/repo`
   - Create `/opt/ops/secrets/<new-app>/{dev,prod}.env` (chmod 600, root-owned)
   - Add the app name to the case-statement in `/opt/ops/scripts/deploy.sh`
   - Done — `deploy.sh <new-app> <env>` now works

2. **If pull-strategy or something else**:
   - Write `/opt/ops/scripts/deploy-<new-app>.sh` following the `deploy-jiejia.sh` shape
   - Add a new case in `deploy.sh` that `exec`s into it

## History / why this layout exists

| Date | Event |
|---|---|
| 2026-04-17 | `deploy-pull.sh.bak` predecessor of jiejia pull script |
| 2026-04-27 | `deploy.sh` (the original universal build script) backed up at `deploy.sh.bak.1777286901` |
| 2026-04-28 | `deploy.sh` renamed to `deploy.sh.deprecated-2026-04-28`. **No matching commit on CD workflow** — every CD run silently 404'd from this date forward |
| 2026-05-11 | **This fix**: dispatcher + rename + CI verify-step. Restored `deploy.sh` as a thin router |

## Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| CD run fails at "Verify deploy script exists" | Script moved or perms changed | SSH to CVM, restore `/opt/ops/scripts/deploy.sh +x` |
| CD run fails at "Deploy to CVM" with `No such file or directory` | Per-app sub-script (`deploy-build.sh` / `deploy-jiejia.sh`) is missing | SSH to CVM, restore from `_archive/` or this doc |
| Deploy succeeds but the wrong container restarted | Dispatcher routed to wrong sub-script | Check the case-statement in `deploy.sh`; verify `$APP` exactly matches a case label |
| Build-strategy deploy succeeds but new code isn't visible | `repo` checkout fell behind | SSH to CVM, `cd /opt/ops/apps/<app>/<env>/repo && git log -1` to verify HEAD |
| Jiejia health check fails after deploy | Prisma migrate timed out or DB issue | Check `docker logs jiejia-api-{env}` and `pg-jiejia-{env}` logs |
