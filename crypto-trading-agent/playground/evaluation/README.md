# Regime-Adaptive Analysis Strategy - Summary

## Overview

The regime-adaptive analysis strategy is a professional-grade market analysis framework that mimics how quantitative traders approach the markets. It automatically adapts its analysis based on market conditions.

## Core Components

### 1. Regime Detector (`regime_detector.py`)
**Purpose**: Classify market conditions

**Regimes**:
- **TRENDING_BULLISH**: Strong uptrend (ADX >25, price above EMAs)
- **TRENDING_BEARISH**: Strong downtrend (ADX >25, price below EMAs)
- **RANGING**: Consolidation (ADX <20, tight Bollinger Bands)
- **VOLATILE**: High volatility (ATR >1.5x average)

**Output**: Market regime with confidence score and reasoning

### 2. Adaptive Timeframe Selector (`adaptive_timeframe_selector.py`)
**Purpose**: Choose optimal timeframes based on regime and trading style

**Strategy**:
- **Trending Markets**: HTF (4H/1H) for bias, MTF (15M) for entry, avoid LTF noise
- **Ranging Markets**: MTF (1H/15M) for boundaries, LTF (5M/1M) for scalps
- **Volatile Markets**: HTF only (1D/4H), avoid all LTF

**Output**: Timeframe strategy with primary/secondary/reference/avoid lists

### 3. Quant Trader Psychology (`quant_trader_psychology.py`)
**Purpose**: Professional trader decision-making framework

**Principles**:
1. **Top-Down Analysis**: HTF bias → MTF setup → LTF entry
2. **Risk-First Mindset**: "Where am I wrong?" before "Where's the opportunity?"
3. **Confluence-Based**: Minimum 3-5 confluences depending on regime
4. **Regime-Adaptive**: Adjust position size based on conditions
5. **Probability Thinking**: Focus on edge, not individual trades

**Output**: Trading decision with action, confidence, position size, and reasoning

### 4. Confluence Scorer (`confluence_scorer.py`)
**Purpose**: Score trade setups based on multiple factors

**Categories**:
- **SMC**: Order Blocks, FVGs, BOS/CHoCH (weight: 1.0)
- **ICT**: Killzones, Liquidity Sweeps, OTE (weight: 1.0)
- **Structure**: HTF/MTF trend alignment (weight: 0.9)
- **Patterns**: Chart patterns (weight: 0.8)
- **Indicators**: RSI, MACD, Volume (weight: 0.7)

**Output**: Confluence score with count, quality rating, and detailed breakdown

### 5. Regime-Adaptive Analyzer (`regime_adaptive_analyzer.py`)
**Purpose**: Integration layer that coordinates all modules

**Workflow**:
1. Detect market regime
2. Select optimal timeframes
3. Perform top-down analysis (HTF → MTF → LTF)
4. Score confluences
5. Make trading decision
6. Return comprehensive analysis

**Output**: Complete analysis with regime, timeframes, confluences, and decision

## Professional Trader Workflow

```
┌─────────────────────────────────────────────────────────────┐
│                    REGIME DETECTION                          │
│  What is the market doing? (Trending/Ranging/Volatile)      │
└────────────────────┬────────────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────────────┐
│                TIMEFRAME SELECTION                           │
│  Which timeframes should I focus on?                         │
│  - Trending: HTF bias, MTF entry                            │
│  - Ranging: MTF boundaries, LTF scalps                      │
│  - Volatile: HTF only, reduce size                          │
└────────────────────┬────────────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────────────┐
│                 TOP-DOWN ANALYSIS                            │
│  HTF (4H/1D): What's the bias? (Bullish/Bearish/Neutral)   │
│  MTF (1H/15M): Where's the setup? (Pullback/Breakout)      │
│  LTF (5M/1M): Where's the entry? (Trigger confirmation)    │
└────────────────────┬────────────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────────────┐
│                CONFLUENCE SCORING                            │
│  How many confluences? (Minimum 3-5 depending on regime)    │
│  - SMC: Order Blocks, FVGs, BOS                             │
│  - ICT: Killzones, Liquidity, OTE                           │
│  - Structure: Trend alignment                               │
│  - Indicators: RSI, MACD, Volume                            │
└────────────────────┬────────────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────────────┐
│                 RISK ASSESSMENT                              │
│  Where am I wrong? (Stop loss placement)                    │
│  What's the R:R? (Minimum 2:1, target 3:1)                  │
│  How much to risk? (Position sizing based on confidence)    │
└────────────────────┬────────────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────────────┐
│                 FINAL DECISION                               │
│  LONG / SHORT / WAIT                                         │
│  Confidence: 0-100%                                          │
│  Position Size: 0.1x - 1.0x                                  │
└─────────────────────────────────────────────────────────────┘
```

## Key Advantages

1. **Adaptive**: Automatically adjusts to market conditions
2. **Professional**: Mimics real quant trader decision-making
3. **Risk-Aware**: Always considers "where am I wrong?"
4. **Confluence-Based**: Requires multiple confirmations
5. **Transparent**: Provides detailed reasoning for every decision
6. **Scalable**: Works across different trading styles (swing/day/scalp)

## Usage Example

```python
from playground.evaluation.regime_adaptive_analyzer import RegimeAdaptiveAnalyzer

analyzer = RegimeAdaptiveAnalyzer()

result = await analyzer.analyze(
    candles={'1h': candles_1h, '4h': candles_4h},
    indicators={'1h': indicators_1h, '4h': indicators_4h},
    smc_analysis=smc_results,
    ict_analysis=ict_results,
    patterns=pattern_results,
    trading_style='swing'
)

# Result includes:
# - Regime classification
# - Optimal timeframes
# - Top-down analysis (HTF/MTF/LTF)
# - Confluence score
# - Trading decision
```

## Next Steps

1. **Integration**: Integrate into existing `MarketAnalysisAgent`
2. **Testing**: Test with live data in playground
3. **Validation**: Compare against manual analysis
4. **Refinement**: Tune parameters based on results
5. **Production**: Deploy to live trading system
