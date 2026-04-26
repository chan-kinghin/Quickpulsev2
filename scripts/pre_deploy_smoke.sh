#!/usr/bin/env bash
# Pre-deploy smoke test: run the Kingdee parity integration suite against the
# already-built (but not yet traffic-cutover) container.
#
# Wave 3 of the systematic data-integrity fix. Hooked in after the container
# health-check but before nginx routes traffic. If any of the canary MTOs
# show a structural regression (Bug 1 inflation, Bug 5b/6 aux-drop, Bug 7
# ghost rows), this exits non-zero and the caller (deploy.sh) should
# rollback.
#
# Usage (intended caller is /opt/ops/scripts/deploy.sh between steps 5 and 6):
#     scripts/pre_deploy_smoke.sh quickpulse prod
#
# Or standalone for manual verification:
#     scripts/pre_deploy_smoke.sh quickpulse prod
#
# Exits:
#   0 — parity tests pass (or were skipped because credentials absent)
#   1 — a regression was detected; deploy should be rolled back

set -euo pipefail

APP="${1:-quickpulse}"
ENV="${2:-prod}"

if [[ "$APP" != "quickpulse" ]]; then
    echo "[smoke] only quickpulse is supported (got: $APP)" >&2
    exit 0
fi

CONTAINER="${APP}-${ENV}"

# 1. Sanity: container must be running and healthy
status=$(docker inspect --format='{{.State.Status}}' "$CONTAINER" 2>/dev/null || echo missing)
if [[ "$status" != "running" ]]; then
    echo "[smoke] container $CONTAINER is not running (status=$status); skipping smoke." >&2
    exit 0
fi

# 2. Run the integration suite from inside the container — the .env at
# /app/.env is sourced automatically by load_dotenv() in the test module.
# pytest's exit code is what matters: 0 = pass, non-zero = regression.
echo "[smoke] running Kingdee parity test inside $CONTAINER ..."
if ! docker exec "$CONTAINER" python3 -m pytest \
        tests/integration/test_kingdee_parity.py \
        --timeout=120 \
        -q --no-header 2>&1; then
    echo ""
    echo "[smoke] ❌ Kingdee parity test FAILED on the new container."
    echo "[smoke] One of the canary MTOs hit a Bug 1/5b/6/7 regression."
    echo "[smoke] Caller (deploy.sh) should roll back to the previous image."
    exit 1
fi

echo "[smoke] ✓ Kingdee parity OK across canary MTOs."
exit 0
