#!/usr/bin/env bash
# Render every deck HTML in this directory to a PDF one level up.
# Usage: bash build.sh [name.html ...]   (no args = all *.html)
set -euo pipefail
cd "$(dirname "$0")"

CHROME="/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
[ -x "$CHROME" ] || { echo "Chrome not found at $CHROME" >&2; exit 1; }

files=("$@")
[ ${#files[@]} -eq 0 ] && files=(*.html)

for f in "${files[@]}"; do
  out="../${f%.html}.pdf"
  "$CHROME" --headless --disable-gpu --no-pdf-header-footer \
    --print-to-pdf="$out" "file://$PWD/$f" 2>/dev/null
  echo "built $out"
done
