# Testing Playground

## Overview

This playground provides isolated testing infrastructure for individual agents with live market data integration. It enables systematic evaluation and improvement of agent performance without running the full multi-agent pipeline.

## Directory Structure

```
playground/
├── config/                    # Test configurations
│   ├── test_config.yaml      # Main test configuration
│   └── agent_configs/        # Agent-specific configs
├── data/                      # Data infrastructure
│   ├── live_data_fetcher.py  # Live Binance data fetcher
│   └── test_data_cache.py    # Cache for repeated tests
├── tests/                     # Test suites
│   ├── test_market_analysis_agent.py
│   ├── test_strategy_agent.py
│   └── test_integration.py
├── evaluation/                # Performance evaluation
│   ├── smc_evaluator.py      # SMC detection accuracy
│   ├── ict_evaluator.py      # ICT setup quality
│   ├── regime_detector.py    # Market regime classification
│   └── performance_metrics.py
└── reports/                   # Generated reports
    ├── analysis_performance.md
    ├── critical_issues.md
    └── improvement_log.md
```

## Infrastructure

**Uses Existing Production Infrastructure:**
- ✅ Real MessageBus (Redis) - connects to your running Redis instance
- ✅ Real StateManager (Redis) - uses the same state storage
- ✅ Real Analysis Agent - tests the actual agent implementation
- ✅ Live Binance Data - fetches real-time market data

**No Mocks Required** - This playground integrates directly with your existing server infrastructure for realistic testing.

## Quick Start

### 1. Run Market Analysis Agent Test
```bash
cd crypto-trading-agent
python -m playground.tests.test_market_analysis_agent --symbol BTCUSDT --live
```

### 2. Run Strategy Agent Test
```bash
python -m playground.tests.test_strategy_agent --symbol BTCUSDT --live
```

### 3. Run Full Integration Test
```bash
python -m playground.tests.test_integration --symbol BTCUSDT --timeframes 1d,4h,1h,15m,5m
```

### 4. Evaluate Performance
```bash
python -m playground.evaluation.performance_metrics --report
```

## Features

### Regime-Adaptive Analysis
- **Trending Market**: Focus on 4H/1H for structure, 15M for entry
- **Ranging Market**: Focus on 1H/15M for range boundaries, 5M for scalps
- **Volatile Market**: Focus on HTF (4H/1D) for bias, avoid LTF noise

### Live Data Integration
- Real-time Binance futures data
- Multi-timeframe candle fetching
- Order book snapshots
- Funding rate tracking
- Data caching for repeated tests

### Real Infrastructure Integration
- Uses your existing Redis MessageBus
- Uses your existing Redis StateManager
- Tests actual agent implementations
- No mocking required

### Performance Evaluation
- SMC detection accuracy measurement
- ICT setup quality scoring
- Indicator effectiveness tracking
- LLM context optimization metrics

## Configuration

Edit `config/test_config.yaml` to customize:
- Symbols to test
- Timeframes to analyze
- LLM providers (Claude/OpenRouter/Groq)
- Performance thresholds
- Caching behavior

## Testing Philosophy

**Professional Quant Trader Psychology:**
1. **Top-Down Analysis**: HTF bias → MTF setup → LTF entry
2. **Risk-First Mindset**: "Where am I wrong?" before "Where's the opportunity?"
3. **Confluence-Based**: Minimum 3 confluences for trade signals
4. **Regime-Adaptive**: Adjust strategy based on market conditions

## Performance Targets

- ✅ Analysis time: <60 seconds
- ✅ LLM context: <100K tokens
- ✅ SMC/ICT accuracy: >80%
- ✅ Minimum confluences: 3+
- ✅ Consistent results across runs

## Reports

Generated reports are saved in `reports/`:
- **analysis_performance.md**: Detailed performance metrics
- **critical_issues.md**: Identified problems and bugs
- **improvement_log.md**: Tracking improvements over time
