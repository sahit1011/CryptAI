#!/usr/bin/env python3
"""
Debug script to inspect LLM context being sent to analysis agent
"""
import sys
import os
from pathlib import Path
import json

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "crypto-trading-agent"))
sys.path.insert(0, str(Path(__file__).parent / "crypto-trading-agent" / "src"))

from src.analysis.llm_context_builder import LLMContextBuilder
from src.data.historical_fetcher import HistoricalDataFetcher
from src.utils.config import get_config

async def debug_context():
    """Debug the context being built for different timeframes"""

    config = get_config()
    fetcher = HistoricalDataFetcher(None)  # No state manager needed for this
    builder = LLMContextBuilder()

    # Fetch 5m data (the problematic timeframe)
    print("Fetching 5m data...")
    df_5m = await fetcher.fetch_ohlcv(
        symbol="BTCUSDT",
        timeframe="5m",
        limit=500  # Same limit as in research
    )

    if df_5m.empty:
        print("No 5m data available")
        return

    print(f"Fetched {len(df_5m)} 5m candles")

    # Convert to expected format
    candles_5m = []
    for _, row in df_5m.iterrows():
        candles_5m.append({
            'timestamp': str(row['timestamp']),
            'open': float(row['open']),
            'high': float(row['high']),
            'low': float(row['low']),
            'close': float(row['close']),
            'volume': float(row['volume'])
        })

    # Build context
    print("Building context...")
    context = builder.build_analysis_context(
        symbol="BTCUSDT",
        candles={'5m': candles_5m},
        indicators={},
        smc_results={},
        ict_results={},
        patterns={}
    )

    # Analyze context size
    print(f"\nContext sections:")
    for key, value in context.items():
        if key == 'current_data':
            candle_count = len(value.get('5m', []))
            print(f"  {key}: {candle_count} candles")
        elif isinstance(value, str):
            print(f"  {key}: {len(value)} chars")
        else:
            print(f"  {key}: {type(value)}")

    # Estimate tokens
    estimated_tokens = builder._estimate_tokens(context)
    print(f"\nEstimated tokens: {estimated_tokens}")

    # Save context for inspection
    with open("context_debug.json", "w") as f:
        json.dump(context, f, indent=2, default=str)

    print("Context saved to context_debug.json")

    # Calculate actual content size
    user_message = f"""
Analyze the following market data:

## Current Market Data
{json.dumps(context['current_data'], indent=2)}

## Technical Indicators
{json.dumps(context['indicators'], indent=2)}

## Smart Money Concepts Analysis
{json.dumps(context['smc_analysis'], indent=2)}

## ICT Methodology Analysis
{json.dumps(context['ict_analysis'], indent=2)}

## Chart Patterns
{json.dumps(context['patterns'], indent=2)}

## Historical Context
{json.dumps(context['historical_context'], indent=2)}

{context['task_instructions']}
"""

    print(f"\nActual user message length: {len(user_message)} chars")
    print(f"Estimated tokens in user message: {len(user_message) * 0.25:.0f}")

    # Show sample of candle data
    print("\nSample candle data (first 3):")
    for candle in context['current_data']['5m'][:3]:
        print(f"  {candle}")

if __name__ == "__main__":
    import asyncio
    asyncio.run(debug_context())