#!/usr/bin/env bash
# Move the production secrets Render -> the Oracle VM without ever displaying them.
#
# Reads every env var from the (suspended) Render service via its API — including the
# 8 dashboard secrets (VAULT_ENC_KEY above all: losing it orphans every stored exchange
# key) — and writes them straight into /opt/cryptai/.env over SSH. Values exist only
# in this process's pipe; nothing lands on the local disk, nothing is echoed.
#
# Usage: scripts/render_env_to_remote.sh <vm-ip> [ssh-user]
set -euo pipefail

VM_IP="${1:?usage: render_env_to_remote.sh <vm-ip> [ssh-user]}"
SSH_USER="${2:-ubuntu}"
SRV="srv-d9cavh37uimc73d4vli0"   # cryptai-backend

python3 - "$SRV" <<'EOF' | ssh "${SSH_USER}@${VM_IP}" 'umask 077 && cat > /opt/cryptai/.env && wc -l < /opt/cryptai/.env | xargs echo "wrote /opt/cryptai/.env lines:"'
import json, sys, urllib.request, yaml, os

srv = sys.argv[1]
key = (yaml.safe_load(open(os.path.expanduser("~/.render/cli.yaml"))).get("api") or {}).get("key", "")
req = urllib.request.Request(
    f"https://api.render.com/v1/services/{srv}/env-vars?limit=60",
    headers={"Authorization": f"Bearer {key}"},
)
rows = json.load(urllib.request.urlopen(req))

# Non-secret runtime flags are pinned in docker-compose.yml; carry over ONLY the
# secrets + service wiring. REDIS_URL is deliberately excluded (in-cluster redis now).
CARRY = {
    "POSTGRES_URL", "SUPABASE_URL", "VAULT_ENC_KEY", "API_AUTH_TOKEN",
    "ADMIN_USER_IDS", "API_CORS_ORIGINS", "OPENROUTER_API_KEY", "MULTI_USER_SEED_IDS",
}
lines = []
for row in rows:
    ev = row.get("envVar", {})
    if ev.get("key") in CARRY and ev.get("value"):
        lines.append(f"{ev['key']}={ev['value']}")

missing = CARRY - {l.split('=', 1)[0] for l in lines}
if missing:
    print(f"MISSING FROM RENDER: {sorted(missing)}", file=sys.stderr)

sys.stdout.write("\n".join(lines) + "\n")
EOF

echo "Secrets transferred. Verify names only:"
ssh "${SSH_USER}@${VM_IP}" "cut -d= -f1 /opt/cryptai/.env"
