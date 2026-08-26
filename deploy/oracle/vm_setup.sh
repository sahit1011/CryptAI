#!/usr/bin/env bash
# One-shot setup for a fresh Oracle Always-Free ARM instance (Ubuntu 22.04/24.04 aarch64).
# Run as the default 'ubuntu' user:  bash vm_setup.sh
set -euo pipefail

echo "== docker =="
if ! command -v docker >/dev/null 2>&1; then
  curl -fsSL https://get.docker.com | sudo sh
fi
sudo usermod -aG docker "$USER"

echo "== firewall: Oracle Ubuntu images ship restrictive iptables baked into the OS =="
# The cloud Security List controls the VCN edge; these rules control the OS. Both must
# allow 80/443 or the box is unreachable even with a correct Security List.
for port in 80 443; do
  if ! sudo iptables -C INPUT -p tcp --dport "$port" -j ACCEPT 2>/dev/null; then
    sudo iptables -I INPUT 5 -p tcp --dport "$port" -m state --state NEW -j ACCEPT
  fi
done
sudo apt-get update -qq && sudo apt-get install -y -qq netfilter-persistent iptables-persistent >/dev/null
sudo netfilter-persistent save

echo "== app dir =="
sudo mkdir -p /opt/cryptai
sudo chown "$USER":"$USER" /opt/cryptai

echo "== unattended security updates =="
sudo apt-get install -y -qq unattended-upgrades >/dev/null
sudo dpkg-reconfigure -f noninteractive unattended-upgrades

echo
echo "Done. Next (from the dev machine):"
echo "  1. scp deploy/oracle/{docker-compose.yml,Caddyfile} ubuntu@<ip>:/opt/cryptai/"
echo "  2. scripts/render_env_to_remote.sh <ip>        # writes /opt/cryptai/.env over SSH"
echo "  3. ssh ubuntu@<ip> 'cd /opt/cryptai && SITE_ADDRESS=<dashed-ip>.sslip.io docker compose up -d --build'"
echo "     (log out/in once first so the docker group applies)"
