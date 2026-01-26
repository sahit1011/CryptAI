import asyncio
from datetime import datetime, timezone
from src.data.historical_fetcher import HistoricalDataFetcher
from src.core.state_manager import StateManager

async def test_fetch():
    state_manager = StateManager()
    await state_manager.connect()
    
    fetcher = HistoricalDataFetcher(state_manager)
    
    # Test 5m timeframe with 500 candles
    df = await fetcher.fetch_ohlcv('BTC/USDT', '5m', since=None, limit=500)
    
    print(f"Fetched {len(df)} candles")
    print(f"First candle: {df.iloc[0]['timestamp']}")
    print(f"Last candle: {df.iloc[-1]['timestamp']}")
    
    # Check for gaps
    gaps = await fetcher._detect_gaps(df, '5m')
    print(f"Found {len(gaps)} gaps")
    
    for gap in gaps[:5]:
        print(f"  Gap: {gap['start']} to {gap['end']} ({gap['duration_minutes']:.1f} min)")
    
    await fetcher.close()
    await state_manager.disconnect()

if __name__ == "__main__":
    asyncio.run(test_fetch())