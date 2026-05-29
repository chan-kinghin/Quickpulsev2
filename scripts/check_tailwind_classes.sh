#!/usr/bin/env bash
# Guard against the precompiled-tailwind gap.
#
# The committed src/frontend/static/css/tailwind.min.css is a precompiled bundle
# that does NOT contain every class the markup uses. When a responsive variant
# like `md:inline` is used but absent from the bundle, `hidden md:inline` resolves
# to display:none at ALL viewports — an invisible, shipped UI regression with no
# runtime error. (See the "MISSING RESPONSIVE UTILITIES" block in main.css.)
#
# This script fails CI if any responsive class used in a class="..." attribute in
# src/frontend/*.html is missing from BOTH the bundle and main.css. It scans only
# class attributes, so prose comments mentioning a class do not create false hits.
set -uo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
HTML_DIR="$ROOT/src/frontend"
BUNDLE="$HTML_DIR/static/css/tailwind.min.css"
MAIN="$HTML_DIR/static/css/main.css"

used=$(grep -rhoE 'class="[^"]*"' "$HTML_DIR"/*.html \
  | grep -oE '(sm|md|lg|xl|2xl):[A-Za-z0-9./_:-]+' \
  | sort -u || true)

missing=()
for cls in $used; do
  # Tailwind escapes ':', '.', and '/' in generated selectors.
  esc=$(printf '%s' "$cls" | sed -e 's/[:]/\\:/g' -e 's/[.]/\\./g' -e 's#/#\\/#g')
  if ! grep -Fq ".$esc" "$BUNDLE" && ! grep -Fq ".$esc" "$MAIN"; then
    missing+=("$cls")
  fi
done

if [ ${#missing[@]} -gt 0 ]; then
  echo "✗ Responsive classes used in src/frontend/*.html but missing from BOTH"
  echo "  tailwind.min.css and main.css (they will silently fail to apply):"
  printf '   - %s\n' "${missing[@]}"
  echo "  Fix: add them to the 'MISSING RESPONSIVE UTILITIES' block at the end of main.css."
  exit 1
fi

echo "✓ All responsive classes used in HTML are defined (bundle or main.css)."
