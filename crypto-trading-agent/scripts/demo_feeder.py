"""Demo data feeder for CryptAI dashboard polish.

Publishes realistic paper-trading state through the SAME Redis MessageBus the API
server subscribes to, so the dashboard's POPULATED states render (portfolio, active
positions, agent feed). Market data (ticker/chart/orderbook) comes from Binance which
is blocked in this sandbox, so those panels stay in their honest offline states.

Run: PYTHONPATH=<backend> python demo_feeder.py [seconds]
"""
import asyncio
import math
import os
import sys
import time

from src.core.message_bus import MessageBus

INITIAL = 10000.0

# Three open positions with entry/SL/TP; mark price drifts to animate P&L.
positions = [
    {"position_id": "px-btc-1", "symbol": "BTCUSDT", "positionSide": "LONG",
     "entryPrice": 64200.0, "markPrice": 64980.0, "positionAmt": 0.12,
     "stopLoss": 62800.0, "takeProfit": 67500.0},
    {"position_id": "px-eth-1", "symbol": "ETHUSDT", "positionSide": "SHORT",
     "entryPrice": 3180.0, "markPrice": 3142.0, "positionAmt": 1.5,
     "stopLoss": 3260.0, "takeProfit": 2980.0},
    {"position_id": "px-sol-1", "symbol": "SOLUSDT", "positionSide": "LONG",
     "entryPrice": 148.5, "markPrice": 151.2, "positionAmt": 20.0,
     "stopLoss": 141.0, "takeProfit": 162.0},
]

FEED = [
    ("data_agent", "Streaming BTCUSDT 1m klines — 500 candles buffered", "info"),
    ("analysis_agent", "SMC scan: bullish order block confirmed at 64.1k, FVG intact", "info"),
    ("analysis_agent", "Regime: TRENDING_BULLISH (ADX 27, +DI dominant)", "success"),
    ("strategy_agent", "Signal: LONG BTCUSDT @ 64.2k — RR 2.6, confidence 0.71", "info"),
    ("risk_agent", "Approved: 1.2% portfolio heat, correlation OK", "success"),
    ("execution_agent", "Filled: LONG 0.12 BTCUSDT @ 64,200 · SL 62.8k · TP 67.5k", "success"),
    ("analysis_agent", "ETHUSDT liquidity sweep + CHoCH — short bias", "info"),
    ("strategy_agent", "Signal: SHORT ETHUSDT @ 3,180 — RR 2.1", "info"),
    ("risk_agent", "Approved: within daily-loss + heat limits", "success"),
    ("execution_agent", "Filled: SHORT 1.5 ETHUSDT @ 3,180", "success"),
]


def unrealized(p):
    diff = p["markPrice"] - p["entryPrice"]
    if p["positionSide"] == "SHORT":
        diff = -diff
    return round(diff * p["positionAmt"], 2)


# Owning tenant for the published state (multi-tenancy). Unset => untenanted/global.
USER_ID = os.getenv("BOT_USER_ID")


def _own(msg: dict) -> dict:
    """Stamp the owning tenant so the API routes this only to that user's sockets."""
    if USER_ID:
        msg["user_id"] = USER_ID
    return msg


async def balance_payload():
    unreal = round(sum(unrealized(p) for p in positions), 2)
    realized = 842.15
    equity = round(INITIAL + realized + unreal, 2)
    return _own({
        "type": "balance_update",
        "payload": {
            "total_equity": equity,
            "current_balance": round(INITIAL + realized, 2),
            "realized_pnl": realized,
            "unrealized_pnl": unreal,
            "win_rate": 68.4,
            "total_trades": 24,
            "initial_balance": INITIAL,
        },
    })


def position_payload():
    return _own({
        "type": "position_update",
        "payload": [
            {**p, "unRealizedProfit": unrealized(p)} for p in positions
        ],
    })


async def main():
    duration = int(sys.argv[1]) if len(sys.argv) > 1 else 120
    bus = MessageBus(redis_url=os.getenv("REDIS_URL", "redis://localhost:6379"))
    await bus.connect()
    print(f"[feeder] connected; feeding for {duration}s")

    # Initial burst: portfolio + positions + agent history
    await bus.publish("execution_status", await balance_payload(), persist=False)
    await bus.publish("execution_status", position_payload(), persist=False)
    for i, (sender, msg, sev) in enumerate(FEED):
        await bus.publish("agent_activity",
                          _own({"action": "activity", "sender": sender, "message": msg, "severity": sev, "id": f"seed-{i}"}), persist=False)
        await asyncio.sleep(0.15)

    # Live loop: drift marks, refresh portfolio, occasional agent chatter.
    start = time.time()
    tick = 0
    heartbeat = [
        ("data_agent", "Tick: BTC 1m candle updated", "info"),
        ("analysis_agent", "Confluence recheck — score 0.74", "info"),
        ("risk_agent", "Portfolio heat 1.2% — nominal", "info"),
        ("execution_agent", "Trailing stop advanced on BTCUSDT", "success"),
    ]
    while time.time() - start < duration:
        tick += 1
        for p in positions:
            wobble = math.sin(tick / 6 + hash(p["symbol"]) % 7) * (p["entryPrice"] * 0.0015)
            p["markPrice"] = round(p["markPrice"] + wobble, 2)
        await bus.publish("execution_status", position_payload(), persist=False)
        await bus.publish("execution_status", await balance_payload(), persist=False)
        if tick % 3 == 0:
            s, m, sev = heartbeat[tick // 3 % len(heartbeat)]
            await bus.publish("agent_activity",
                              _own({"action": "activity", "sender": s, "message": m, "severity": sev, "id": f"hb-{tick}"}), persist=False)
        await asyncio.sleep(2)

    await bus.disconnect()
    print("[feeder] done")


if __name__ == "__main__":
    asyncio.run(main())
