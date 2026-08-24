#!/usr/bin/env python3
"""Render runbook automation — env parity + resume, via the Render REST API.

The Render CLI (v2.x) has no env-var or resume commands, so the un-suspend
runbook (docs/plan-2026-08/05-infra-free-tier.pdf, slide 4) needs the REST API.
Auth comes from the CLI's own login (~/.render/cli.yaml); no key is ever printed.

Usage:
  python3 scripts/render_ops.py status                 # suspension + safe config flags
  python3 scripts/render_ops.py set-env                # apply the runbook env deltas below
  python3 scripts/render_ops.py resume                 # resume cryptai-backend + cryptai-redis ONLY
  python3 scripts/render_ops.py verify                 # post-resume probes

SAFETY RULES BAKED IN:
- Only ever touches ALLOWED_SERVICES — never klaro-backend / SlackBot (the 750h
  workspace cap binds at three always-on services).
- set-env applies exactly RUNBOOK_ENV: engine flags OFF until R1.4 (the
  Pulse-dataclass bug makes SIGNAL_PLANE_ENABLED=true drain every session's
  clock), symbols aligned to BTC/ETH/SOL, cadence 180.
- Secret values are never read or printed; only names and non-secret flags.
"""
import json
import sys
import time
import urllib.request

import yaml

API = "https://api.render.com/v1"
BACKEND = "srv-d9cavh37uimc73d4vli0"          # cryptai-backend (hand-configured — never recreate)
ALLOWED_SERVICES = {BACKEND}                   # web services this script may mutate
KV_NAME = "cryptai-redis"                      # resolved to an ID at runtime

RUNBOOK_ENV = {
    # R1.1 runbook deltas. Engine stays dark until R1.3 lands (Pulse bug) — R1.4 flips these.
    "RUN_SIGNAL_ENGINE_IN_API": "false",
    "SIGNAL_PLANE_ENABLED": "false",
    "TRADING_SYMBOLS": "BTCUSDT,ETHUSDT,SOLUSDT",
    "PLATFORM_SYMBOLS": "BTCUSDT,ETHUSDT,SOLUSDT",
    "CYCLE_INTERVAL": "180",
    "DAEMON_DISABLE_AGENTS": "memory",         # chromadb+ONNX don't fit 512MB
}

SAFE_TO_PRINT = set(RUNBOOK_ENV) | {
    "USE_TESTNET", "LIVE_TRADING_CONFIRMED", "RUN_DAEMON_IN_API",
    "ENVIRONMENT", "SYMBOLS", "ANALYSIS_KEEP_WARM",
}


def _key() -> str:
    import os
    cfg = yaml.safe_load(open(os.path.expanduser("~/.render/cli.yaml")))
    return (cfg.get("api") or {}).get("key", "")


def _req(method: str, path: str, body: dict | None = None) -> tuple[int, dict | list | None]:
    req = urllib.request.Request(
        f"{API}{path}",
        method=method,
        headers={"Authorization": f"Bearer {_key()}", "Content-Type": "application/json"},
        data=json.dumps(body).encode() if body is not None else None,
    )
    try:
        with urllib.request.urlopen(req) as r:
            raw = r.read()
            return r.status, (json.loads(raw) if raw else None)
    except urllib.error.HTTPError as e:
        raw = e.read()
        try:
            return e.code, json.loads(raw)
        except Exception:
            return e.code, {"raw": raw.decode(errors="replace")[:300]}


def status() -> None:
    code, svc = _req("GET", f"/services/{BACKEND}")
    print(f"cryptai-backend [{code}]: suspended={svc.get('suspended')} suspenders={svc.get('suspenders')} "
          f"branch={svc.get('branch')} autoDeploy={svc.get('autoDeploy')}")
    code, envs = _req("GET", f"/services/{BACKEND}/env-vars?limit=60")
    if code == 200:
        for e in envs:
            ev = e.get("envVar", {})
            if ev.get("key") in SAFE_TO_PRINT:
                print(f"  {ev['key']} = {ev.get('value')!r}")
    kv = _find_kv()
    if kv:
        print(f"{KV_NAME}: id={kv['id']} status={kv.get('status', kv.get('suspended', '?'))}")


def _find_kv() -> dict | None:
    for path, field in (("/key-value?limit=20", "keyValue"), ("/redis?limit=20", "redis")):
        code, items = _req("GET", path)
        if code == 200 and isinstance(items, list):
            for it in items:
                obj = it.get(field) or {}
                if obj.get("name") == KV_NAME:
                    return obj
    return None


def set_env() -> None:
    for k, v in RUNBOOK_ENV.items():
        code, _ = _req("PUT", f"/services/{BACKEND}/env-vars/{k}", {"value": v})
        print(f"  {k} -> {v} : HTTP {code}")
    print("re-reading to verify:")
    status()


def resume() -> None:
    kv = _find_kv()
    if kv:
        # The instance type moved from /redis to /key-value across API versions — try both.
        for path in (f"/key-value/{kv['id']}/resume", f"/redis/{kv['id']}/resume"):
            code, body = _req("POST", path)
            print(f"  resume {KV_NAME} via {path}: HTTP {code}" + (f" {body}" if code >= 400 else ""))
            if code < 400:
                break
    else:
        print(f"  {KV_NAME}: not found via API (may not need a resume)")
    code, body = _req("POST", f"/services/{BACKEND}/resume")
    print(f"  resume cryptai-backend: HTTP {code}" + (f" {body}" if code >= 400 else " (autoDeploy will deploy HEAD)"))


def verify() -> None:
    for path, want in (("/health", "any"), ("/health/ready", "any"), ("/health/live", "any")):
        try:
            with urllib.request.urlopen(f"https://cryptai-backend.onrender.com{path}", timeout=30) as r:
                print(f"  {path}: {r.status} {r.read()[:120].decode(errors='replace')}")
        except Exception as e:
            print(f"  {path}: {type(e).__name__}: {str(e)[:100]}")
    code, svc = _req("GET", f"/services/{BACKEND}")
    print(f"  service: suspended={svc.get('suspended')} suspenders={svc.get('suspenders')}")


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "status"
    {"status": status, "set-env": set_env, "resume": resume, "verify": verify}[cmd]()
