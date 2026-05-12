#!/usr/bin/env bash
# Rebuild src/frontend/static/css/tailwind.min.css from the current HTML/JS.
#
# Why this exists: in 2026-02 we switched from Tailwind CDN (JIT) to a
# pre-built CSS file (commit a297bba) to avoid CDN failures in China.
# Pre-built CSS only contains classes that were used at build time. Any
# utility or arbitrary-value class added LATER (flex-col, object-contain,
# ring-2, min-h-[400px], …) is a silent no-op — the HTML looks right but
# the layout breaks. Re-run this script after adding new Tailwind classes.
#
# Requires node/npm in PATH. Uses Tailwind v3.4.19 (matches what generated
# the original file).

set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

cat > "$TMP/input.css" <<'EOF'
@tailwind base;
@tailwind components;
@tailwind utilities;
EOF

cd "$TMP"
npx -y tailwindcss@3.4.19 \
  -i "$TMP/input.css" \
  -o "$ROOT/src/frontend/static/css/tailwind.min.css" \
  --content "$ROOT/src/frontend/**/*.html,$ROOT/src/frontend/static/js/**/*.js" \
  --minify

echo "Rebuilt: $ROOT/src/frontend/static/css/tailwind.min.css"
