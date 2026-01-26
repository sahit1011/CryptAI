# Testing Playground - Quick Start Guide

## What is This?

The testing playground is a dedicated environment for testing individual agents with **live market data** using your **existing infrastructure** (Redis MessageBus and StateManager).

## Key Features

✅ **Real Infrastructure** - Uses your running Redis instance, no mocks  
✅ **Live Data** - Fetches real-time data from Binance Futures  
✅ **Regime-Adaptive** - Automatically detects market conditions (trending/ranging/volatile)  
✅ **Isolated Testing** - Test agents independently without running full pipeline  
✅ **Performance Metrics** - Track analysis time, accuracy, and LLM costs  

## Quick Start

### 1. Test Market Analysis Agent
```bash
cd crypto-trading-agent
python -m playground.tests.test_market_analysis_agent --symbol BTC/USDT --live
```

### 2. Test Strategy Generation Agent
```bash
python -m playground.tests.test_strategy_agent --symbol BTC/USDT
```

### 3. Run All Tests
```bash
python -m playground.run_tests --test all
```

## What Gets Tested?

### Market Analysis Agent
- ✅ Live data fetching from Binance
- ✅ Market regime detection (trending/ranging/volatile)
- ✅ SMC/ICT computational analysis
- ✅ LLM analysis with Claude Sonnet 4.5
- ✅ Trade opportunity identification
- ✅ Performance metrics (time, context size, accuracy)

### Strategy Generation Agent
- ✅ Analysis-to-strategy conversion
- ✅ Entry/SL/TP calculation
- ✅ Risk-reward ratio validation
- ✅ Position sizing
- ✅ Confidence scoring

## Configuration

Edit `playground/config/test_config.yaml` to customize:
- Symbols to test
- Timeframes to analyze
- LLM providers
- Performance thresholds

## Reports

After running tests, check `playground/reports/` for:
- `analysis_performance.md` - Detailed performance metrics
- `critical_issues.md` - Identified problems
- `improvement_log.md` - Tracking improvements

## Troubleshooting

**Redis Connection Error?**
- Make sure your Redis server is running
- Check `config.yaml` for correct Redis URL

**Binance API Error?**
- Check your internet connection
- Binance may rate-limit - wait a few seconds and retry

**LLM API Error?**
- Verify API keys in `config.yaml`
- Check API quotas/limits

## Next Steps

1. Run initial tests to establish baseline metrics
2. Review `critical_issues.md` for identified problems
3. Implement improvements
4. Re-run tests to validate improvements
5. Update `improvement_log.md` with results
