#!/usr/bin/env bash
# Pre-deploy smoke test: HTTP-level sanity check against the deployed
# QuickPulse container. Hooked into /opt/ops/scripts/deploy.sh after the
# health-check passes. Non-zero exit → caller should roll back.
#
# Wave 3 design intent (was: pytest inside container — abandoned because
# tests/ isn't COPYed into the Docker image). HTTP smoke is what an
# operator would run anyway, requires no container internals, fails loud.
#
# Checks:
#   1. /health returns 200
#   2. /api/auth/token authenticates with the env's expected password
#   3. /api/mto/AK2510034?source=live returns non-empty child_items and
#      passes a sanity assertion per Wave 1-6 fixes — specifically that
#      05.02.08.027 (盒子) prod_instock_must_qty equals ~3744 (was 187200
#      pre-Wave-1, the canonical Bug-1 case).
#
# Usage (called by deploy.sh between [5/6] and [6/6]):
#     scripts/pre_deploy_smoke.sh quickpulse prod
#
# Or standalone:
#     scripts/pre_deploy_smoke.sh quickpulse prod
#
# Auth password is read from env QP_PROD_PASSWORD / QP_DEV_PASSWORD or
# from the secrets file at /opt/ops/secrets/quickpulse/${ENV}.env
# (ADMIN_PASSWORD field). Skips with exit 0 if the secret can't be loaded
# (smoke check is best-effort, not a blocker for environments without it).

set -euo pipefail

APP="${1:-quickpulse}"
ENV="${2:-prod}"

if [[ "$APP" != "quickpulse" ]]; then
    echo "[smoke] only quickpulse is supported (got: $APP)" >&2
    exit 0
fi

# Resolve the deployed URL by env
case "$ENV" in
    prod) URL="https://fltpulse.szfluent.cn" ;;
    dev)  URL="https://dev.fltpulse.szfluent.cn" ;;
    *)    echo "[smoke] unknown env: $ENV"; exit 0 ;;
esac

# Resolve admin password — env first, then secrets file
PASSWORD="${QP_PROD_PASSWORD:-${QP_DEV_PASSWORD:-}}"
if [[ -z "$PASSWORD" ]]; then
    SECRETS_FILE="/opt/ops/secrets/quickpulse/${ENV}.env"
    if [[ -r "$SECRETS_FILE" ]]; then
        PASSWORD=$(grep -E '^ADMIN_PASSWORD=' "$SECRETS_FILE" 2>/dev/null | cut -d= -f2- || true)
    fi
fi
if [[ -z "$PASSWORD" ]]; then
    # Fall back to the documented default for prod
    [[ "$ENV" == "prod" ]] && PASSWORD='FltPulse@2026!Prod'
    [[ "$ENV" == "dev"  ]] && PASSWORD='FltPulse@2026!Dev'
fi
if [[ -z "$PASSWORD" ]]; then
    echo "[smoke] no admin password resolvable for $ENV; skipping smoke." >&2
    exit 0
fi

# 1. /health
http_code=$(curl -s -o /dev/null -w '%{http_code}' --max-time 10 "${URL}/health" || echo "000")
if [[ "$http_code" != "200" ]]; then
    echo "[smoke] ❌ /health returned ${http_code}, expected 200" >&2
    exit 1
fi

# 2. /api/auth/token
token=$(curl -s --max-time 10 -X POST "${URL}/api/auth/token" \
    -H 'Content-Type: application/x-www-form-urlencoded' \
    -d "username=admin&password=${PASSWORD}" \
    | python3 -c 'import sys,json; d=json.load(sys.stdin); print(d.get("access_token",""))' \
    2>/dev/null || true)
if [[ -z "$token" ]]; then
    echo "[smoke] ❌ /api/auth/token did not return an access_token" >&2
    exit 1
fi

# 3. /api/mto/AK2510034?source=live — Bug-1 canonical case sanity
# 05.02.08.027 (盒子) SUM(prod_instock_must_qty) must be ~3744 (was 187,200
# pre-Wave-1). Allow some Kingdee data drift (3500-4000).
must_total=$(curl -s --max-time 60 \
    "${URL}/api/mto/AK2510034?source=live" \
    -H "Authorization: Bearer ${token}" \
    | python3 -c '
import sys, json
from decimal import Decimal
d = json.load(sys.stdin)
ch = d.get("child_items", [])
total = sum(
    Decimal(str(c.get("prod_instock_must_qty", 0) or 0))
    for c in ch
    if c.get("material_code") == "05.02.08.027"
)
print(int(total))
' 2>/dev/null || echo "0")

if [[ "$must_total" -lt 3500 || "$must_total" -gt 4000 ]]; then
    echo "[smoke] ❌ AK2510034 / 05.02.08.027 SUM(prod_instock_must_qty)=${must_total}." >&2
    echo "[smoke]    Expected ~3744. Bug-1 canonical case regressed?" >&2
    echo "[smoke]    Pre-Wave-1 value was 187,200 (50× via PPBOM cross-parent rollup)." >&2
    exit 1
fi

echo "[smoke] ✓ ${URL} smoke OK (Bug-1 canary 05.02.08.027 must_qty=${must_total})"
exit 0
