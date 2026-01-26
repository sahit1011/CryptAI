"""
Restore Deleted Trades
Re-inserts the trades that were accidentally deleted
"""
import psycopg2
import os
from dotenv import load_dotenv
from urllib.parse import urlparse
from datetime import datetime

def restore_trades():
    try:
        # Connect to PostgreSQL
        load_dotenv()
        postgres_url = os.getenv("POSTGRES_URL", "postgresql://trader:secure_password_here@localhost:5432/trading_agent")
        parsed = urlparse(postgres_url)
        
        conn = psycopg2.connect(
            dbname=parsed.path[1:],
            user=parsed.username,
            password=parsed.password,
            host=parsed.hostname,
            port=parsed.port or 5432
        )
        cursor = conn.cursor()
        print("✅ Connected to PostgreSQL")
        
        # Trades to restore (from the deletion output)
        trades = [
            {
                'trade_id': 'HIST_001_1764139179',
                'symbol': 'BTCUSDT',
                'direction': 'LONG',
                'entry_price': 95420.5,
                'exit_price': 96150.3,
                'exit_reason': 'TP1_HIT',
                'entry_time': '2025-11-26 14:09:39.809935',
                'exit_time': '2025-11-26 15:30:00',
                'position_size': 0.1,
                'stop_loss': 95000.0,
                'risk_amount': 42.05
            },
            {
                'trade_id': 'HIST_002_1764167979',
                'symbol': 'BTCUSDT',
                'direction': 'SHORT',
                'entry_price': 96200.0,
                'exit_price': 95650.5,
                'exit_reason': 'TP1_HIT',
                'entry_time': '2025-11-26 20:24:39.809935',
                'exit_time': '2025-11-26 21:45:00',
                'position_size': 0.1,
                'stop_loss': 96700.0,
                'risk_amount': 50.0
            },
            {
                'trade_id': 'HIST_003_1764196779',
                'symbol': 'BTCUSDT',
                'direction': 'LONG',
                'entry_price': 95700.0,
                'exit_price': 95320.0,
                'exit_reason': 'STOP_LOSS',
                'entry_time': '2025-11-27 04:39:39.809935',
                'exit_time': '2025-11-27 05:15:00',
                'position_size': 0.1,
                'stop_loss': 95300.0,
                'risk_amount': 40.0
            },
            {
                'trade_id': 'HIST_004_1764236379',
                'symbol': 'BTCUSDT',
                'direction': 'LONG',
                'entry_price': 95100.0,
                'exit_price': 95820.0,
                'exit_reason': 'TP1_HIT',
                'entry_time': '2025-11-27 15:29:39.809935',
                'exit_time': '2025-11-27 17:00:00',
                'position_size': 0.1,
                'stop_loss': 94650.0,
                'risk_amount': 45.0
            },
            {
                'trade_id': 'HIST_005_1764275979',
                'symbol': 'BTCUSDT',
                'direction': 'SHORT',
                'entry_price': 96500.0,
                'exit_price': 96050.0,
                'exit_reason': 'TP1_HIT',
                'entry_time': '2025-11-28 02:24:39.809935',
                'exit_time': '2025-11-28 03:30:00',
                'position_size': 0.1,
                'stop_loss': 97000.0,
                'risk_amount': 50.0
            },
            {
                'trade_id': 'HIST_006_1764329979',
                'symbol': 'BTCUSDT',
                'direction': 'LONG',
                'entry_price': 96200.0,
                'exit_price': 97100.0,
                'exit_reason': 'TP2_HIT',
                'entry_time': '2025-11-28 17:54:39.809935',
                'exit_time': '2025-11-28 19:30:00',
                'position_size': 0.1,
                'stop_loss': 95750.0,
                'risk_amount': 45.0
            },
            {
                'trade_id': 'HIST_007_1764376779',
                'symbol': 'BTCUSDT',
                'direction': 'SHORT',
                'entry_price': 97200.0,
                'exit_price': 97620.0,
                'exit_reason': 'STOP_LOSS',
                'entry_time': '2025-11-29 06:19:39.809935',
                'exit_time': '2025-11-29 07:00:00',
                'position_size': 0.1,
                'stop_loss': 97650.0,
                'risk_amount': 45.0
            },
            {
                'trade_id': 'HIST_008_1764419979',
                'symbol': 'BTCUSDT',
                'direction': 'LONG',
                'entry_price': 97400.0,
                'exit_price': 98050.0,
                'exit_reason': 'TP1_HIT',
                'entry_time': '2025-11-29 18:39:39.809935',
                'exit_time': '2025-11-29 20:00:00',
                'position_size': 0.1,
                'stop_loss': 96950.0,
                'risk_amount': 45.0
            },
            {
                'trade_id': 'HIST_009_1764455979',
                'symbol': 'BTCUSDT',
                'direction': 'LONG',
                'entry_price': 98100.0,
                'exit_price': 98520.0,
                'exit_reason': 'TP1_HIT',
                'entry_time': '2025-11-30 04:49:39.809935',
                'exit_time': '2025-11-30 06:00:00',
                'position_size': 0.1,
                'stop_loss': 97650.0,
                'risk_amount': 45.0
            },
            {
                'trade_id': '24c30e75-8abe-4b73-942d-f51cb7499dce',
                'symbol': 'BTC/USDT',
                'direction': 'SHORT',
                'entry_price': 87150.0,
                'exit_price': 85371.56311760879,
                'exit_reason': 'TP_HIT',
                'entry_time': '2025-12-01 14:53:29.810324',
                'exit_time': '2025-12-01 16:30:00',
                'position_size': 0.25,
                'stop_loss': 87900.0,
                'risk_amount': 187.5
            }
        ]
        
        print(f"\n📊 Restoring {len(trades)} trades...")
        
        insert_query = """
            INSERT INTO trades (
                trade_id, symbol, direction, entry_price, exit_price, exit_reason,
                entry_time, exit_time, position_size, stop_loss, risk_amount,
                pnl, pnl_percentage, is_winner, take_profit_levels
            ) VALUES (
                %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
            )
        """
        
        restored_count = 0
        for trade in trades:
            # Calculate P&L
            if trade['direction'] == 'LONG':
                pnl = (trade['exit_price'] - trade['entry_price']) * trade['position_size']
            else:
                pnl = (trade['entry_price'] - trade['exit_price']) * trade['position_size']
            
            pnl_pct = (pnl / (trade['entry_price'] * trade['position_size'])) * 100
            is_winner = pnl > 0
            
            cursor.execute(insert_query, (
                trade['trade_id'],
                trade['symbol'],
                trade['direction'],
                trade['entry_price'],
                trade['exit_price'],
                trade['exit_reason'],
                trade['entry_time'],
                trade['exit_time'],
                trade['position_size'],
                trade['stop_loss'],
                trade['risk_amount'],
                pnl,
                pnl_pct,
                is_winner,
                []  # Empty take_profit_levels
            ))
            
            restored_count += 1
            print(f"  ✅ Restored: {trade['trade_id']} - {trade['direction']} {trade['symbol']} | P&L: ${pnl:.2f}")
        
        conn.commit()
        print(f"\n✅ Successfully restored {restored_count} trades!")
        
        cursor.close()
        conn.close()
        
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    restore_trades()
