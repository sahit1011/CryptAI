#!/usr/bin/env python3
"""
BingX VST testnet smoke test for the live execution path.

Validates that signing, transport, order placement, status, and cancellation all
work against BingX's VST testnet BEFORE any real-money trading is enabled. This is
the gate the LIVE_TRADING_CONFIRMED flag depends on — run this green first.

SAFETY:
- Refuses to run unless USE_TESTNET=true (never touches mainnet).
- Read-only by default (balance + open positions + open orders).
- With --order it places ONE tiny LIMIT order far from market (won't fill), queries
  it, then cancels it — proving the full place/query/cancel round-trip.

Usage:
  USE_TESTNET=true BINGX_API_KEY=... BINGX_SECRET_KEY=... \
      python scripts/testnet_smoke.py [--symbol BTC-USDT] [--order]
"""
import argparse
import asyncio
import os
import sys

from src.execution.exchange_client import BingXClient, OrderSide


async def main() -> int:
    parser = argparse.ArgumentParser(description="BingX VST testnet smoke test")
    parser.add_argument("--symbol", default="BTC-USDT")
    parser.add_argument("--order", action="store_true",
                        help="also place + cancel one tiny far-from-market limit order")
    parser.add_argument("--qty", type=float, default=0.0001)
    args = parser.parse_args()

    if os.getenv("USE_TESTNET", "true").lower() != "true":
        print("REFUSING: USE_TESTNET must be 'true' for the smoke test (never runs on mainnet).")
        return 2

    api_key = os.getenv("BINGX_API_KEY", "")
    api_secret = os.getenv("BINGX_SECRET_KEY", "")
    if not api_key or not api_secret:
        print("Missing BINGX_API_KEY / BINGX_SECRET_KEY env vars.")
        return 2

    client = BingXClient(api_key=api_key, api_secret=api_secret, testnet=True)
    print(f"Base URL: {client.base_url}  (must be the VST testnet host)\n")

    try:
        print("1) get_account_balance ...")
        balance = await client.get_account_balance()
        print(f"   OK: {balance}\n")

        print("2) get_open_positions ...")
        positions = await client.get_open_positions()
        print(f"   OK: {len(positions)} open position(s)\n")

        if args.order:
            # Far-from-market limit so it rests and never fills.
            far_price = 1000.0
            print(f"3) place_limit_order (rest @ ${far_price}, qty {args.qty}) ...")
            order = await client.place_limit_order(
                args.symbol, OrderSide.BUY, args.qty, far_price,
                client_order_id="caismoketest1",
            )
            print(f"   OK: order_id={order.order_id} status={order.status}\n")

            print("4) get_order_status ...")
            status = await client.get_order_status(args.symbol, order.order_id)
            print(f"   OK: status={status.status}\n")

            print("5) cancel_order ...")
            ok = await client.cancel_order(args.symbol, order.order_id)
            print(f"   OK: cancelled={ok}\n")

            print("6) cancel_all_orders (cleanup) ...")
            ok = await client.cancel_all_orders(args.symbol)
            print(f"   OK: {ok}\n")

        print("✅ Testnet smoke test passed. The live signing/transport/order path works on VST.")
        return 0

    except Exception as e:
        print(f"\n❌ Smoke test FAILED: {type(e).__name__}: {e}")
        print("Do NOT enable LIVE_TRADING_CONFIRMED until this passes green.")
        return 1
    finally:
        await client.close()


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
