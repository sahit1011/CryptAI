"""Seed realistic closed trades into the trades table for dashboard trade history.

Uses the real TradeHistoryManager schema so /api/trades serves them.
Run: PYTHONPATH=<backend> POSTGRES_URL=... python seed_trades.py
"""
import os
import sys
from datetime import datetime, timedelta

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from sqlalchemy.schema import CreateTable

from src.memory.trade_history_manager import TradeRecord

# (symbol, dir, entry, exit, size, sl, strategy, exit_reason, conf, regime, hours_ago, dur_min)
TRADES = [
    ("BTCUSDT", "LONG", 61200, 63850, 0.15, 59800, "SWING", "take_profit", 0.74, "trending", 96, 640),
    ("ETHUSDT", "SHORT", 3320, 3180, 1.8, 3420, "DAY_TRADE", "take_profit", 0.69, "trending", 88, 210),
    ("SOLUSDT", "LONG", 142.0, 138.4, 25, 139.5, "SCALP", "stop_loss", 0.58, "volatile", 80, 45),
    ("BTCUSDT", "LONG", 62800, 64100, 0.1, 61500, "DAY_TRADE", "take_profit", 0.72, "trending", 72, 320),
    ("BNBUSDT", "SHORT", 612, 598, 5, 628, "SWING", "take_profit", 0.66, "ranging", 60, 500),
    ("ETHUSDT", "LONG", 3060, 3020, 1.2, 2990, "SCALP", "stop_loss", 0.55, "ranging", 52, 38),
    ("SOLUSDT", "LONG", 145.5, 152.8, 18, 141.0, "SWING", "take_profit", 0.78, "trending", 40, 720),
    ("BTCUSDT", "SHORT", 65200, 64300, 0.08, 66400, "DAY_TRADE", "take_profit", 0.63, "ranging", 30, 180),
    ("XRPUSDT", "LONG", 0.512, 0.498, 8000, 0.503, "SCALP", "stop_loss", 0.52, "volatile", 22, 55),
    ("ETHUSDT", "LONG", 3110, 3240, 1.5, 3040, "SWING", "take_profit", 0.71, "trending", 12, 610),
    ("BTCUSDT", "LONG", 63900, 64980, 0.12, 62800, "DAY_TRADE", "take_profit", 0.70, "trending", 5, 260),
]


def main():
    url = os.environ["POSTGRES_URL"]
    engine = create_engine(url)
    # Two TradeRecord definitions map to 'trades' via extend_existing, so the metadata
    # has 12 duplicate indexes and create_all() throws. Emit just the CREATE TABLE from
    # the merged model (all columns the ORM SELECT needs), skipping the separate index
    # DDL — indexes aren't needed for the demo dataset.
    with engine.begin() as conn:
        conn.execute(text("DROP TABLE IF EXISTS trades CASCADE"))
        conn.execute(CreateTable(TradeRecord.__table__))
    session = sessionmaker(bind=engine)()
    added = 0
    try:
        for i, (sym, direction, entry, exit_p, size, sl, strat, reason, conf, regime, hrs, dur) in enumerate(TRADES):
            tid = f"seed-{i:03d}-{sym}"
            if session.query(TradeRecord).filter_by(trade_id=tid).first():
                continue
            long = direction == "LONG"
            gross = (exit_p - entry) if long else (entry - exit_p)
            pnl = round(gross * size, 2)
            pnl_pct = round((gross / entry) * 100, 2)
            entry_time = datetime.now() - timedelta(hours=hrs)
            exit_time = entry_time + timedelta(minutes=dur)
            rr = round(abs(exit_p - entry) / max(abs(entry - sl), 1e-9), 2)
            session.add(TradeRecord(
                trade_id=tid, user_id=os.getenv("SEED_USER_ID"),
                symbol=sym, direction=direction, strategy_type=strat,
                entry_price=entry, entry_time=entry_time, position_size=size,
                exit_price=exit_p, exit_time=exit_time, exit_reason=reason,
                stop_loss=sl, take_profit_levels=[round(exit_p, 4)], risk_amount=round(abs(entry - sl) * size, 2),
                pnl=pnl, pnl_percentage=pnl_pct, risk_reward_ratio=rr, duration_minutes=dur,
                confidence_score=conf, confluence_count=3, market_regime=regime,
                is_winner=pnl > 0,
            ))
            added += 1
        session.commit()
        total = session.query(TradeRecord).count()
        wins = session.query(TradeRecord).filter_by(is_winner=True).count()
        print(f"[seed] added {added}; table now has {total} trades ({wins} winners = {wins/total*100:.1f}% win rate)")
    finally:
        session.close()


if __name__ == "__main__":
    main()
