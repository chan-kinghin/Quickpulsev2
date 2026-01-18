# Repository Guidelines

## Project Structure & Module Organization
- `src/frontend/` holds the static UI: `index.html` plus `static/js/app.js` and `static/css/` assets.
- `scripts/` contains Python utilities for exploring Kingdee K3Cloud APIs and generating field docs.
- `docs/` stores architecture notes and field references (`docs/fields/`, `docs/api/`).
- `sdk/` vendors the Kingdee Python SDK and demo code used for experimentation.
- `data/` is reserved for generated JSON exports and large artifacts (ignored by Git).
- `conf.ini` stores local Kingdee credentials and connection settings.

## Build, Test, and Development Commands
- `cd src/frontend && python -m http.server 8000` serves the dashboard locally for quick UI checks.
- `python scripts/explore_all_api_fields.py` queries K3Cloud View APIs and writes raw JSON to `field_data/`.
- `python scripts/generate_fields_docs.py` regenerates markdown field docs in `docs/fields/` (requires SDK + `conf.ini`).
- `python scripts/explore_prd_mo_fields.py` focuses on production order fields for targeted analysis.

## Coding Style & Naming Conventions
- Python uses 4-space indentation, `snake_case` for modules/functions, and small single-purpose scripts.
- Frontend JavaScript uses 4-space indentation, semicolons, and descriptive Alpine.js method names.
- Prefer explicit filenames (`*_fields.json`, `test_*.py`) to match existing tooling and tests.

## Testing Guidelines
- Pytest-based demo tests live in `sdk/python_sdk_demo/`; run `pytest sdk/python_sdk_demo/...` with valid credentials.
- New tests should follow `test_*.py` naming and mirror module paths when applicable.

## Commit & Pull Request Guidelines
- Commit messages are short, imperative, and capitalized (e.g., "Add documentation and scaffold").
- PRs should include a concise summary, rationale/linked issue, and screenshots for UI changes.
- Call out any changes to `conf.ini`, `docs/fields/`, or generated data artifacts.

## Security & Configuration Tips
- Treat `conf.ini` as sensitive; keep real credentials local and avoid committing secrets.
- Place generated JSON and logs under `data/` and keep them out of version control.
