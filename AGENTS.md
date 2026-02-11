# Repository Guidelines

## Project Structure & Module Organization
- `src/` — Backend: FastAPI app, Kingdee client, readers, query handler, sync service
- `src/frontend/` — Frontend: Alpine.js + Tailwind (login, dashboard, sync pages)
- `config/` — `mto_config.json` (material type routing + semantic metrics config)
- `scripts/` — Python utilities for exploring Kingdee K3Cloud APIs
- `docs/` — Architecture notes, field references (`docs/fields/`, `docs/api/`), CVM infrastructure
- `tests/` — Pytest suite (289 tests, ~4s with `--ignore=tests/e2e --ignore=tests/integration`)
- `data/` — SQLite database + generated artifacts (gitignored)

## Build, Test, and Development Commands
- `pip install -e .` — Install dependencies
- `uvicorn src.main:app --reload --port 8000` — Run dev server
- `pytest` — Run all tests
- `pytest --ignore=tests/e2e --ignore=tests/integration` — Fast unit tests (~4s)
- `docker-compose -f docker-compose.dev.yml up --build` — Run with Docker (dev)
- `python scripts/explore_all_api_fields.py` — Explore Kingdee API fields

## Deployment (CVM)
- **Server**: `root@121.41.81.36` (shared Aliyun ECS)
- **Prod**: `https://fltpulse.szfluent.cn` (branch: `main`, legacy `:8003`)
- **Dev**: `https://dev.fltpulse.szfluent.cn` (branch: `develop`, legacy `:8004`)
- **SSL**: Let's Encrypt, auto-renewal via certbot (expires 2026-05-12)
- **Deploy**: `/opt/ops/scripts/deploy.sh quickpulse <prod|dev>`
- **CI/CD**: Push to `develop` auto-deploys dev; manual dispatch for prod
- **Full docs**: `docs/CVM_INFRASTRUCTURE.md`

## Coding Style & Naming Conventions
- Python uses 4-space indentation, `snake_case` for modules/functions
- Frontend JavaScript uses 4-space indentation, semicolons, and descriptive Alpine.js method names
- Prefer explicit filenames (`*_fields.json`, `test_*.py`)

## Testing Guidelines
- Pytest-based tests in `tests/`; run `pytest` for full suite
- New tests should follow `test_*.py` naming and mirror module paths
- Use `--ignore=tests/e2e --ignore=tests/integration` for fast runs

## Commit & Pull Request Guidelines
- Commit messages are short, imperative, and capitalized
- PRs should include a concise summary, rationale/linked issue, and screenshots for UI changes

## Security & Configuration Tips
- **NEVER commit credentials to git** — use `.env` (gitignored) or CVM secrets
- `.env.example` has template for Kingdee API + CVM credentials
- CVM secrets at `/opt/ops/secrets/quickpulse/{prod,dev}.env`
