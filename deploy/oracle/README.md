# CryptAI on Oracle Cloud Always Free — the "own box" deployment (R1.8)

Replaces Render as the compute host. **Vercel (frontend) and Supabase (auth/DB) stay
unchanged** — only the backend moves. Target: VM.Standard.A1.Flex, **4 OCPU / 24 GB /
200 GB disk / 10 TB egress**, $0 forever. No sleep, no bandwidth suspensions, no
keepalive cron needed (an external uptime ping replaces it as *monitoring*).

## Founder steps (browser, once)

1. **Sign up**: oracle.com/cloud/free → Start for free. Country India, account type
   Personal. **Home region: India West (Mumbai)** — permanent choice; Always Free
   resources live there, and Supabase sits in ap-south-1 next door. Fallback if Mumbai
   won't take the card/capacity: Hyderabad.
   Card notes: a **credit card** clears verification most reliably (a ~₹2 hold is
   placed and reversed); many Indian debit cards and all RuPay cards fail Oracle's
   check. You are NOT charged unless you explicitly upgrade — and even upgraded
   (Pay-As-You-Go), Always-Free shapes stay $0.
2. Wait for the "account is ready" email (minutes to a few hours).
3. Tell the assistant — auth from the CLI is `oci session authenticate`
   (browser SSO, no API-key ceremony).

## Assistant steps (CLI, after auth)

1. Provision: VCN + subnet + internet gateway + security list (22/80/443) + the A1.Flex
   instance (Ubuntu 24.04 aarch64, 4 OCPU/24 GB, public IP, our SSH key).
   *"Out of host capacity" is normal for A1 — the launch retries across ADs/time.*
2. `bash vm_setup.sh` on the box (docker, OS firewall — Oracle Ubuntu images ship
   restrictive iptables baked in; the Security List alone is NOT enough).
3. `scp docker-compose.yml Caddyfile ubuntu@<ip>:/opt/cryptai/`
4. `scripts/render_env_to_remote.sh <ip>` — the 8 secrets go Render→VM over SSH,
   never displayed, never on local disk. (VAULT_ENC_KEY finally gets a home we control.)
5. `SITE_ADDRESS=<dashed-ip>.sslip.io docker compose up -d --build` — builds the full
   image (Rust + Python) from the public GitHub repo at the pinned ref; Caddy gets real
   Let's Encrypt TLS on the sslip.io hostname, so `wss://` works.
6. Verify: /health/ready → redis+db true · session endpoints 401 · CORS 200 ·
   "Daemon started" + monitors online in `docker compose logs`.
7. Cutover: update Vercel env `NEXT_PUBLIC_API_URL` / `NEXT_PUBLIC_WS_URL` to the new
   hostname (assistant does this via Vercel CLI) + add the origin to API_CORS_ORIGINS.
8. Aftercare: retire the keepalive cron (replace with an UptimeRobot ping on
   /health/live); Render stays suspended as the documented fallback; update the plan
   decks (doc 05) once 48h of probes are green.

## What changes vs Render — and what doesn't

- 24 GB RAM: the memory agent (chromadb) may return; the Rust engine ships in the image
  (still env-gated OFF until R1.4 proves pulses in logs).
- The cost law does NOT retire: 10 TB/mo removes the *bandwidth* anxiety, but
  demand-gated streams remain correct engineering (CPU, honesty, and the day we ever
  move hosts again).
- New responsibilities: we are the platform now — unattended-upgrades is enabled by
  vm_setup.sh; disk, uptime monitoring, and SSH key hygiene are ours.
