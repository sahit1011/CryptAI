from src.memory.trade_history_manager import TradeHistoryManager
from src.utils.config import get_config

config = get_config()
tm = TradeHistoryManager(config.database.postgres_url)
trades = tm.get_recent_trades(limit=20)

print(f"\n{'='*80}")
print(f"TRADES IN YOUR POSTGRESQL DATABASE")
print(f"{'='*80}")
print(f"\nTotal trades found: {len(trades)}\n")

for i, t in enumerate(trades, 1):
    print(f"\n{'─'*80}")
    print(f"Trade #{i}")
    print(f"{'─'*80}")
    print(f"  Trade ID:      {t.trade_id}")
    print(f"  Symbol:        {t.symbol}")
    print(f"  Direction:     {t.direction}")
    print(f"  Entry Price:   ${t.entry_price:,.2f}")
    print(f"  Exit Price:    ${t.exit_price:,.2f}" if t.exit_price else "  Exit Price:    Not closed yet")
    print(f"  Entry Time:    {t.entry_time}")
    print(f"  Exit Time:     {t.exit_time}" if t.exit_time else "  Exit Time:     Not closed yet")
    print(f"  P&L:           ${t.pnl:.2f}" if t.pnl else "  P&L:           $0.00 (still open)")
    print(f"  Status:        {'CLOSED' if t.exit_price else 'OPEN'}")
    print(f"  Strategy:      {t.strategy_type or 'N/A'}")
    print(f"  Exit Reason:   {t.exit_reason or 'N/A'}")
    print(f"  Is Winner:     {t.is_winner if t.is_winner is not None else 'N/A'}")

print(f"\n{'='*80}\n")
