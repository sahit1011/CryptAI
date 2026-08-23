#!/usr/bin/env bash
# Add redirect URLs to the Supabase auth allowlist — read-modify-write, never clobber.
#
# Why this exists: `supabase config push` would push the WHOLE local [auth] block,
# silently resetting anything not represented in a local config.toml (providers, JWT
# expiry, email templates). This touches exactly one field.
#
# Run it yourself rather than having an agent do it: the CLI's token lives in the macOS
# keychain, and reading it requires the GUI approval prompt that a headless process
# cannot answer.
#
#   ./scripts/add-supabase-redirect.sh                        # adds the defaults below
#   ./scripts/add-supabase-redirect.sh "http://localhost:3005/**"   # adds one more
set -euo pipefail

PROJECT_REF="${SUPABASE_PROJECT_REF:-idilvhmgdxybplgglicm}"

# The origins the app actually redirects to. signInWithOAuth sends the browser to
# `${window.location.origin}/auth/callback`, so every origin you sign in from must be
# here or Supabase refuses the exchange and the callback lands on the error page.
DEFAULT_URLS=(
  "http://localhost:3000/**"
  "http://localhost:3001/**"   # CryptAI takes 3001 when another dev server holds 3000
  "https://cryptai-app.vercel.app/**"
)

TOKEN="${SUPABASE_ACCESS_TOKEN:-}"
if [ -z "$TOKEN" ]; then
  # Approve the keychain prompt if macOS shows one.
  TOKEN=$(security find-generic-password -s "Supabase CLI" -a supabase -w 2>/dev/null || true)
fi
if [ -z "$TOKEN" ]; then
  echo "No Supabase access token." >&2
  echo "Either run 'supabase login', or create one at" >&2
  echo "https://supabase.com/dashboard/account/tokens and export SUPABASE_ACCESS_TOKEN." >&2
  exit 1
fi

API="https://api.supabase.com/v1/projects/${PROJECT_REF}/config/auth"

echo "Reading current auth config for ${PROJECT_REF}…"
CURRENT=$(curl -fsS -H "Authorization: Bearer ${TOKEN}" "$API")

python3 - "$CURRENT" "$@" <<'PY' > /tmp/supabase-redirect-payload.json
import json, sys, os
current = json.loads(sys.argv[1])
extra = sys.argv[2:]
defaults = [
    "http://localhost:3000/**",
    "http://localhost:3001/**",
    "https://cryptai-app.vercel.app/**",
]
existing_raw = current.get("uri_allow_list") or ""
existing = [u.strip() for u in existing_raw.split(",") if u.strip()]

merged = list(existing)
for u in defaults + extra:
    if u not in merged:
        merged.append(u)

print(json.dumps({"uri_allow_list": ",".join(merged)}))
sys.stderr.write(f"site_url        : {current.get('site_url')}\n")
sys.stderr.write(f"google enabled  : {current.get('external_google_enabled')}\n")
sys.stderr.write(f"before ({len(existing)}): {existing_raw or '(empty)'}\n")
sys.stderr.write(f"after  ({len(merged)}): {','.join(merged)}\n")
if merged == existing:
    sys.stderr.write("\nNothing to add — every URL is already allowlisted.\n")
PY

echo
read -r -p "Apply this change? [y/N] " reply
[ "$reply" = "y" ] || [ "$reply" = "Y" ] || { echo "Aborted; nothing changed."; exit 0; }

curl -fsS -X PATCH "$API" \
  -H "Authorization: Bearer ${TOKEN}" \
  -H "Content-Type: application/json" \
  --data @/tmp/supabase-redirect-payload.json \
| python3 -c "import sys,json; print('now allowed:', json.load(sys.stdin).get('uri_allow_list'))"

rm -f /tmp/supabase-redirect-payload.json
echo "Done. Retry Google sign-in."
