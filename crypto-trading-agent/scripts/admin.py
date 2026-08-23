#!/usr/bin/env python3.12
"""
admin.py - Consolidated safe admin CLI for the crypto trading agent.

This single argparse CLI replaces a sprawl of ~54 loose, one-off root scripts
that each performed a dangerous, destructive operation (wiping the trades
table, flushing Redis state, force-closing live/paper positions, etc.) with no
guard rails. Every destructive subcommand here:

  * requires --confirm to actually mutate anything,
  * supports --dry-run to preview without touching state,
  * refuses to run when ENVIRONMENT=production unless --i-understand is given,
  * reads DB / Redis credentials from the environment only (never hardcoded).

Credentials (read from env, with safe local defaults that are NOT production):
  POSTGRES_URL   e.g. postgresql://user:pass@localhost:5432/trading_agent
  REDIS_URL      e.g. redis://localhost:6379/0
  ENVIRONMENT    development | staging | production (default: development)

Usage examples:
  python3.12 scripts/admin.py clear-redis --dry-run
  python3.12 scripts/admin.py clear-redis --confirm
  python3.12 scripts/admin.py delete-trades --confirm
  python3.12 scripts/admin.py force-close --confirm
  python3.12 scripts/admin.py close-all --confirm

This CLI is the ONLY sanctioned path for these operations. The loose one-off
scripts it superseded (nuclear_clear_positions.py, delete_all_trades.py, …) were
retired to repo-root `_attic/cta-scripts/` on 2026-08-24 and are excluded from
the production image. Never run anything from _attic against live state.
"""
from __future__ import annotations

import argparse
import os
import sys
from datetime import datetime
from urllib.parse import urlparse

# Redis keys used by the trading agent for live state.
REDIS_PORTFOLIO_KEY = "state:portfolio"
REDIS_POSITIONS_KEY = "state:positions"

DEFAULT_POSTGRES_URL = "postgresql://trader:secure_password_here@localhost:5432/trading_agent"
DEFAULT_REDIS_URL = "redis://localhost:6379/0"
DEFAULT_API_BASE = "http://localhost:8000"


def _env() -> str:
    return os.getenv("ENVIRONMENT", "development").strip().lower()


def _guard(args: argparse.Namespace) -> None:
    """Enforce production + confirmation safety rules. Exits on violation."""
    if _env() == "production" and not args.i_understand:
        print(
            "REFUSING: ENVIRONMENT=production. This is a destructive operation.\n"
            "Re-run with --i-understand if you really mean to do this in production.",
            file=sys.stderr,
        )
        sys.exit(2)
    if not args.dry_run and not args.confirm:
        print(
            "REFUSING: no --confirm given. Re-run with --confirm to apply, "
            "or --dry-run to preview.",
            file=sys.stderr,
        )
        sys.exit(2)


def _mode_banner(args: argparse.Namespace) -> None:
    mode = "DRY-RUN (no changes)" if args.dry_run else "LIVE (applying changes)"
    print(f"[admin] environment={_env()} mode={mode}")


def _postgres_url() -> str:
    return os.getenv("POSTGRES_URL", DEFAULT_POSTGRES_URL)


def _redis_url() -> str:
    return os.getenv("REDIS_URL", DEFAULT_REDIS_URL)


def _connect_postgres():
    import psycopg2  # imported lazily so --help works without deps

    parsed = urlparse(_postgres_url())
    conn = psycopg2.connect(
        dbname=parsed.path[1:],
        user=parsed.username,
        password=parsed.password,
        host=parsed.hostname,
        port=parsed.port or 5432,
    )
    return conn


def _connect_redis():
    import redis  # imported lazily so --help works without deps

    client = redis.Redis.from_url(_redis_url(), decode_responses=True)
    client.ping()
    return client


# --------------------------------------------------------------------------- #
# Subcommand implementations
# --------------------------------------------------------------------------- #
def cmd_clear_redis(args: argparse.Namespace) -> int:
    """Delete the portfolio + positions state keys from Redis."""
    _guard(args)
    _mode_banner(args)

    client = _connect_redis()
    keys = [REDIS_PORTFOLIO_KEY, REDIS_POSITIONS_KEY]
    for key in keys:
        exists = client.exists(key)
        if not exists:
            print(f"  - {key}: not present, skipping")
            continue
        if args.dry_run:
            print(f"  - {key}: WOULD delete")
        else:
            client.delete(key)
            print(f"  - {key}: deleted")
    print("[admin] clear-redis done")
    return 0


def cmd_delete_trades(args: argparse.Namespace) -> int:
    """Delete ALL rows from the trades table."""
    _guard(args)
    _mode_banner(args)

    conn = _connect_postgres()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM trades")
        total = cursor.fetchone()[0]
        print(f"  - trades table currently has {total} row(s)")
        if args.dry_run:
            print(f"  - WOULD delete {total} row(s)")
        else:
            cursor.execute("DELETE FROM trades")
            deleted = cursor.rowcount
            conn.commit()
            print(f"  - deleted {deleted} row(s)")
        cursor.close()
    finally:
        conn.close()
    print("[admin] delete-trades done")
    return 0


def cmd_force_close(args: argparse.Namespace) -> int:
    """Mark all open trades (exit_time IS NULL) as force-closed in the DB."""
    _guard(args)
    _mode_banner(args)

    conn = _connect_postgres()
    try:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT trade_id, symbol, direction, entry_price "
            "FROM trades WHERE exit_time IS NULL"
        )
        open_trades = cursor.fetchall()
        print(f"  - found {len(open_trades)} open trade(s)")
        for t in open_trades:
            print(f"    * {t[0]} {t[1]} {t[2]} @ {t[3]}")
        if args.dry_run:
            print(f"  - WOULD force-close {len(open_trades)} trade(s)")
        elif open_trades:
            cursor.execute(
                "UPDATE trades "
                "SET exit_time = %s, exit_price = entry_price, "
                "    exit_reason = 'FORCE_CLOSE_ADMIN_CLI', pnl = 0 "
                "WHERE exit_time IS NULL",
                (datetime.utcnow(),),
            )
            conn.commit()
            print(f"  - force-closed {cursor.rowcount} trade(s)")
        cursor.close()
    finally:
        conn.close()
    print("[admin] force-close done")
    return 0


def cmd_close_all(args: argparse.Namespace) -> int:
    """Ask the running API to cleanly close all positions via its endpoint."""
    _guard(args)
    _mode_banner(args)

    import requests  # imported lazily so --help works without deps

    base = os.getenv("API_BASE_URL", DEFAULT_API_BASE).rstrip("/")
    url = f"{base}/api/close-positions"
    if args.dry_run:
        print(f"  - WOULD POST {url}")
        print("[admin] close-all done")
        return 0

    print(f"  - POST {url}")
    try:
        resp = requests.post(url, timeout=30)
    except requests.RequestException as exc:
        print(f"  - connection error: {exc}", file=sys.stderr)
        print("    Is the API server running?", file=sys.stderr)
        return 1

    if resp.status_code != 200:
        print(f"  - API error: {resp.status_code} {resp.text}", file=sys.stderr)
        return 1

    result = resp.json()
    if result.get("success"):
        print(f"  - closed {result.get('closed_count')} position(s)")
        print(f"  - realized P&L: {result.get('total_pnl', 0)}")
    else:
        print(f"  - API reported failure: {result.get('error')}", file=sys.stderr)
        return 1
    print("[admin] close-all done")
    return 0


# --------------------------------------------------------------------------- #
# Argument parsing
# --------------------------------------------------------------------------- #
def _add_common_flags(sub: argparse.ArgumentParser) -> None:
    sub.add_argument(
        "--confirm",
        action="store_true",
        help="Actually perform the destructive operation (required for live runs).",
    )
    sub.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview the operation without changing any state.",
    )
    sub.add_argument(
        "--i-understand",
        action="store_true",
        help="Required to run when ENVIRONMENT=production.",
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="admin.py",
        description="Safe consolidated admin CLI for the crypto trading agent.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_redis = sub.add_parser(
        "clear-redis",
        help="Delete portfolio/positions state keys from Redis.",
    )
    _add_common_flags(p_redis)
    p_redis.set_defaults(func=cmd_clear_redis)

    p_del = sub.add_parser(
        "delete-trades",
        help="Delete ALL rows from the trades table.",
    )
    _add_common_flags(p_del)
    p_del.set_defaults(func=cmd_delete_trades)

    p_force = sub.add_parser(
        "force-close",
        help="Mark all open trades as force-closed in the DB.",
    )
    _add_common_flags(p_force)
    p_force.set_defaults(func=cmd_force_close)

    p_close = sub.add_parser(
        "close-all",
        help="Ask the running API to cleanly close all positions.",
    )
    _add_common_flags(p_close)
    p_close.set_defaults(func=cmd_close_all)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
