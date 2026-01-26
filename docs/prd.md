# Crypto Trading Agent System - PRD & Roadmap

## Executive Summary
Build an autonomous AI agent system that mimics professional crypto futures traders using real-time market data, advanced technical analysis (SMC, ICT), and multi-agent orchestration to execute optimal trading decisions on perpetual futures markets.

---

## Phase 1: Core AI Agent System (MVP)

### 1. System Architecture Overview

```
┌─────────────────────────────────────────────────────────────┐
│                    ORCHESTRATION LAYER                       │
│  ┌──────────────────────────────────────────────────────┐   │
│  │         Agent Orchestrator (LangGraph/CrewAI)        │   │
│  └──────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────┘
                              │
        ┌─────────────────────┼─────────────────────┐
        │                     │                     │
┌───────▼────────┐   ┌────────▼────────┐   ┌──────▼────────┐
│  Data Agent    │   │ Strategy Agent  │   │ Execution     │
│                │   │                 │   │ Agent         │
│ - WebSocket    │   │ - Indicator     │   │               │
│ - Historical   │   │   Analysis      │   │ - Order Mgmt  │
│ - Order Book   │   │ - SMC/ICT       │   │ - Risk Mgmt   │
│ - Funding      │   │ - MTF Analysis  │   │ - Position    │
└────────────────┘   └─────────────────┘   └───────────────┘
```

### 2. Multi-Agent Architecture

#### **Agent 1: Data Collection Agent**
**Responsibilities:**
- Real-time WebSocket connections to Binance Futures
- Fetch 5m, 15m, 1h, 4h, 1D OHLCV data
- Stream order book depth (L2 data)
- Monitor funding rates
- Track liquidation data
- Aggregate market sentiment indicators

**Tools Required:**
- `binance_websocket_connector`: Real-time kline streams
- `historical_data_fetcher`: REST API for historical candles
- `orderbook_monitor`: Depth snapshot and updates
- `funding_rate_tracker`: Perpetual funding rates

**Tech Stack:**
- `ccxt` for exchange connectivity
- `websocket-client` or `python-binance` for WebSocket
- Redis/TimescaleDB for time-series storage

---

#### **Agent 2: Market Analysis Agent**
**Responsibilities:**
- Multi-timeframe technical analysis
- Smart Money Concepts (SMC) detection
- ICT methodology implementation
- Price action pattern recognition
- Market structure analysis

**Sub-Components:**

**2.1 Indicator Analysis Module**
- RSI (14, 21 periods) with divergence detection
- MACD (12, 26, 9) with histogram analysis
- Bollinger Bands (20, 2σ) squeeze detection
- Volume profile and VWAP
- EMA ribbons (9, 21, 50, 200)
- ATR for volatility measurement
- Stochastic RSI for momentum

**2.2 SMC (Smart Money Concepts) Module**
- Order Block detection (bullish/bearish)
- Fair Value Gap (FVG/Imbalance) identification
- Break of Structure (BOS) / Change of Character (CHoCH)
- Liquidity pools (SSL/BSL - swing lows/highs)
- Premium/Discount zones (Fibonacci retracement)
- Supply and Demand zones

**2.3 ICT Methodology Module**
- Killzones identification (London, NY, Asian sessions)
- Liquidity sweeps detection
- Order flow analysis
- Market maker models (Accumulation, Manipulation, Distribution)
- Optimal Trade Entry (OTE) - 0.62-0.79 Fibonacci
- Breaker blocks
- Mitigation blocks

**2.4 Multi-Timeframe Analysis**
```
1D  → Macro trend (HTF bias)
4H  → Swing structure
1H  → Intraday bias
15M → Entry refinement
5M  → Precise entry trigger
```

**Tools Required:**
- `calculate_indicators`: Technical indicator computation
- `detect_order_blocks`: SMC pattern recognition
- `identify_liquidity_zones`: ICT liquidity mapping
- `mtf_structure_analyzer`: Cross-timeframe correlation
- `pattern_recognition`: Chart patterns (H&S, wedges, flags)

**Tech Stack:**
- `ta-lib` or `pandas-ta` for indicators
- `numpy` for numerical computations
- Custom algorithms for SMC/ICT detection

---

#### **Agent 3: Strategy Generation Agent**
**Responsibilities:**
- Synthesize analysis from Market Analysis Agent
- Generate trade setups with entry/exit/SL/TP
- Confidence scoring for each setup
- Risk-reward ratio calculation (minimum 1:2)
- Identify trade type (scalp, day trade, swing)

**Decision Framework:**
```python
Trade Setup Schema:
{
  "symbol": "BTCUSDT",
  "timeframe": "1H",
  "type": "LONG/SHORT",
  "strategy_type": "SCALP/DAY_TRADE/SWING",
  "entry_price": 43250.00,
  "stop_loss": 42800.00,
  "take_profit": [43700.00, 44200.00, 44800.00],  # Multiple TPs
  "confidence_score": 0.85,  # 0-1 scale
  "risk_reward": 3.0,
  "reasoning": {
    "mtf_bias": "Bullish on 4H, 1H confirmed BOS",
    "smc_confluence": "Price at premium discount zone + FVG",
    "ict_setup": "Liquidity sweep at Asian low + OTE entry",
    "indicators": "RSI divergence + MACD bullish cross"
  },
  "invalidation_conditions": ["Break below 42500"],
  "position_size": 0.1  # Based on risk management
}
```

**Tools Required:**
- `generate_trade_setup`: Core strategy logic
- `calculate_position_size`: Kelly criterion / Fixed % risk
- `validate_setup`: Cross-check confluences
- `risk_calculator`: Max drawdown, portfolio heat

---

#### **Agent 4: Risk Management Agent**
**Responsibilities:**
- Portfolio heat monitoring (max 2% per trade)
- Position sizing based on volatility (ATR-based)
- Drawdown protection
- Correlation analysis (avoid over-exposure)
- Dynamic stop-loss adjustment (trailing stops)

**Risk Rules:**
- Max risk per trade: 2% of capital ($200 on $10k)
- Max portfolio exposure: 6% (3 concurrent trades max)
- Max daily loss: 5% ($500)
- Min Risk-Reward: 1:2
- No trading during high-impact news (NFP, FOMC)

**Tools Required:**
- `calculate_position_size`: ATR-based sizing
- `portfolio_heat_check`: Current exposure calculation
- `drawdown_monitor`: Track equity curve
- `correlation_matrix`: Asset correlation analysis

---

#### **Agent 5: Execution Agent**
**Responsibilities:**
- Order placement via BingX/CoinDCX API
- Order management (modify, cancel)
- Position monitoring
- Partial profit taking
- Emergency exit logic

**Order Types:**
- Market orders (immediate execution)
- Limit orders (better fills)
- Stop-loss orders (risk management)
- Take-profit orders (automated exits)
- Trailing stop-loss

**Tools Required:**
- `place_order`: Exchange API integration
- `modify_order`: Update SL/TP dynamically
- `close_position`: Emergency exit
- `check_order_status`: Order fill tracking
- `position_tracker`: Current P&L monitoring

**Tech Stack:**
- BingX API / CoinDCX API
- `ccxt` unified exchange interface
- WebSocket for order updates

---

#### **Agent 6: Memory & Context Manager**
**Responsibilities:**
- Store trade history and performance
- Market regime detection (trending/ranging/volatile)
- Strategy performance tracking
- Learning from past trades
- Context retention across analysis cycles

**Memory Structure:**
```
Short-term Memory (Redis):
- Last 100 candles per timeframe
- Current open positions
- Recent signal history (last 24h)
- Active order book state

Long-term Memory (PostgreSQL):
- All historical trades with outcomes
- Strategy performance metrics
- Market regime classifications
- Optimization parameters

Episodic Memory:
- Trade journal with reasoning
- Win/loss streaks
- Behavioral patterns
```

**Tools Required:**
- `store_trade_record`: Persist trade data
- `retrieve_market_regime`: Historical pattern matching
- `performance_analytics`: Win rate, Sharpe ratio, max DD
- `context_retrieval`: Fetch relevant past scenarios

**Tech Stack:**
- Redis for hot data
- PostgreSQL/MongoDB for persistent storage
- Vector DB (Pinecone/Chroma) for semantic memory

---

### 3. Orchestration Layer

**Framework Choice:** LangGraph (for complex workflows) or CrewAI (for simpler coordination)

**Orchestration Flow:**
```
Every 3 minutes:
1. Data Agent → Fetch latest candles + order book + funding
2. Market Analysis Agent → Run indicator + SMC + ICT analysis
3. Strategy Agent → If setup conditions met → Generate trade plan
4. Risk Management Agent → Validate risk parameters
5. (If approved) Execution Agent → Place orders
6. Memory Manager → Log analysis + decisions
```

**State Machine:**
```
IDLE → DATA_COLLECTION → ANALYSIS → STRATEGY_GENERATION 
→ RISK_CHECK → (if pass) EXECUTION → MONITORING → IDLE
                    ↓ (if fail)
                 IDLE
```

---

### 4. Technical Stack (Phase 1)

**Core Framework:**
- **Language:** Python 3.11+
- **Agent Framework:** LangGraph or CrewAI
- **LLM:** GPT-4o / Claude Sonnet 4.5 (for reasoning)

**Data & APIs:**
- **Exchange Data:** Binance WebSocket API
- **Execution:** BingX/CoinDCX REST API
- **Technical Analysis:** pandas-ta, ta-lib
- **Numerical:** NumPy, SciPy

**Storage:**
- **Hot Data:** Redis (real-time cache)
- **Time-Series:** TimescaleDB or InfluxDB
- **Persistent:** PostgreSQL
- **Vector Memory:** Pinecone or ChromaDB

**Monitoring:**
- **Logging:** Loguru or structlog
- **Metrics:** Prometheus + Grafana
- **Alerting:** Telegram bot for trade notifications

**Infrastructure:**
- **Containerization:** Docker
- **Process Management:** systemd or PM2
- **Environment:** Ubuntu 22.04 VPS (low latency)

---

### 5. Core Implementation Workflow

#### **5.1 Data Pipeline**
```python
class DataAgent:
    def __init__(self):
        self.ws_client = BinanceWebSocket()
        self.timeframes = ['5m', '15m', '1h', '4h', '1d']
        
    async def stream_data(self, symbol):
        # WebSocket for real-time klines
        await self.ws_client.subscribe_kline(symbol, self.timeframes)
        
    def get_historical_data(self, symbol, timeframe, limit=500):
        # Fetch historical candles for context
        return ccxt_client.fetch_ohlcv(symbol, timeframe, limit=limit)
```

#### **5.2 Analysis Pipeline**
```python
class MarketAnalysisAgent:
    def analyze(self, data_multi_tf):
        indicators = self.calculate_indicators(data_multi_tf)
        smc_signals = self.detect_smc_patterns(data_multi_tf)
        ict_setup = self.identify_ict_opportunities(data_multi_tf)
        
        return {
            'indicators': indicators,
            'smc': smc_signals,
            'ict': ict_setup,
            'mtf_bias': self.determine_bias(data_multi_tf)
        }
    
    def detect_order_blocks(self, candles):
        # Implementation of order block detection
        # Look for strong momentum candle followed by pullback
        pass
    
    def identify_fvg(self, candles):
        # Fair Value Gap detection
        # Gap where candle[i-1].high < candle[i+1].low (bullish FVG)
        pass
```

#### **5.3 Strategy Generation**
```python
class StrategyAgent:
    def generate_setup(self, analysis):
        if not self.check_confluence(analysis):
            return None
            
        setup = {
            'type': self.determine_direction(analysis),
            'entry': self.calculate_entry(analysis),
            'stop_loss': self.calculate_sl(analysis),
            'take_profit': self.calculate_tp_levels(analysis),
            'confidence': self.calculate_confidence(analysis)
        }
        
        return setup if setup['confidence'] > 0.75 else None
    
    def check_confluence(self, analysis):
        # Require at least 3 confluences
        confluences = []
        if analysis['indicators']['rsi_divergence']: confluences.append('rsi')
        if analysis['smc']['order_block_present']: confluences.append('ob')
        if analysis['ict']['liquidity_sweep']: confluences.append('liq')
        if analysis['mtf_bias'] == 'aligned': confluences.append('mtf')
        
        return len(confluences) >= 3
```

#### **5.4 Execution**
```python
class ExecutionAgent:
    def execute_trade(self, setup, capital=10000):
        position_size = self.risk_agent.calculate_size(
            capital=capital,
            risk_pct=0.02,
            entry=setup['entry'],
            stop_loss=setup['stop_loss']
        )
        
        order = self.exchange.place_limit_order(
            symbol=setup['symbol'],
            side=setup['type'],
            amount=position_size,
            price=setup['entry']
        )
        
        self.place_sl_tp(order.id, setup['stop_loss'], setup['take_profit'])
        return order
```

---

### 6. Key Features Implementation

#### **6.1 Professional Trading Logic**

**Entry Conditions (Must meet ALL):**
1. **MTF Alignment:** Higher timeframe (4H/1D) trend aligned with lower timeframe (1H/15M)
2. **SMC Confluence:** 
   - Price at premium/discount zone (Fibonacci 0.5-0.7)
   - Order block present
   - Fair Value Gap identified
3. **ICT Setup:**
   - Liquidity sweep confirmed
   - Trading during optimal killzone
   - Order flow supports direction
4. **Indicator Confirmation:**
   - RSI divergence or extreme levels
   - MACD momentum aligned
   - Volume profile supports move

**Exit Strategy:**
1. **Partial Profit Taking:**
   - 33% at 1:1 RR (move SL to breakeven)
   - 33% at 1:2 RR (trail stop)
   - 33% at 1:3+ RR (let it run)
2. **Stop Loss:**
   - Below/above order block
   - Never more than 2% capital risk
3. **Trailing Stop:**
   - ATR-based trailing (1.5x ATR distance)

#### **6.2 Market Regime Detection**
```python
def detect_market_regime(self, data):
    atr = calculate_atr(data, period=14)
    adx = calculate_adx(data, period=14)
    
    if adx > 25 and atr > atr.mean():
        return 'TRENDING_HIGH_VOL'  # Best for breakout trades
    elif adx > 25 and atr < atr.mean():
        return 'TRENDING_LOW_VOL'   # Good for swing trades
    elif adx < 25 and atr > atr.mean():
        return 'RANGING_HIGH_VOL'   # Choppy, avoid
    else:
        return 'RANGING_LOW_VOL'    # Mean reversion plays
```

#### **6.3 Smart Money Concepts Implementation**

**Order Block Detection:**
```python
def detect_order_blocks(self, candles):
    order_blocks = []
    
    for i in range(2, len(candles)-1):
        # Bullish Order Block
        if (candles[i].close > candles[i].open and  # Bullish candle
            candles[i].volume > candles[i-1:i+1].volume.mean() * 1.5 and  # High volume
            candles[i+1].low > candles[i].high):  # Gap up after
            
            order_blocks.append({
                'type': 'bullish',
                'zone': (candles[i].low, candles[i].high),
                'timestamp': candles[i].timestamp
            })
    
    return order_blocks
```

**Fair Value Gap (Imbalance):**
```python
def identify_fvg(self, candles):
    fvgs = []
    
    for i in range(1, len(candles)-1):
        # Bullish FVG: Gap between candle[i-1] high and candle[i+1] low
        if candles[i-1].high < candles[i+1].low:
            fvgs.append({
                'type': 'bullish',
                'gap': (candles[i-1].high, candles[i+1].low),
                'midpoint': (candles[i-1].high + candles[i+1].low) / 2
            })
    
    return fvgs
```

---

### 7. Development Roadmap (Phase 1)

#### **Week 1-2: Infrastructure Setup**
- [ ] Set up development environment
- [ ] Configure Binance WebSocket connection
- [ ] Implement historical data fetching
- [ ] Set up Redis + PostgreSQL databases
- [ ] Create data models and schemas

#### **Week 3-4: Data Agent**
- [ ] Build WebSocket manager for real-time data
- [ ] Implement multi-timeframe data aggregation
- [ ] Create order book depth monitoring
- [ ] Add funding rate tracking
- [ ] Build data validation and cleaning

#### **Week 5-6: Market Analysis Agent**
- [ ] Implement indicator calculation library
- [ ] Build SMC detection algorithms (OB, FVG, BOS)
- [ ] Implement ICT methodology logic
- [ ] Create multi-timeframe analysis engine
- [ ] Add pattern recognition module

#### **Week 7-8: Strategy Agent**
- [ ] Build confluence detection system
- [ ] Implement entry/exit logic
- [ ] Create confidence scoring algorithm
- [ ] Add risk-reward calculation
- [ ] Build setup validation framework

#### **Week 9-10: Risk Management Agent**
- [ ] Implement position sizing algorithms
- [ ] Build portfolio heat monitoring
- [ ] Create drawdown protection system
- [ ] Add correlation analysis
- [ ] Implement dynamic stop-loss logic

#### **Week 11-12: Execution Agent**
- [ ] Integrate BingX/CoinDCX API
- [ ] Build order management system
- [ ] Implement position monitoring
- [ ] Add emergency exit logic
- [ ] Create order status tracking

#### **Week 13-14: Memory & Orchestration**
- [ ] Build memory management system
- [ ] Implement trade logging
- [ ] Create performance analytics
- [ ] Set up agent orchestration (LangGraph)
- [ ] Build state machine workflow

#### **Week 15-16: Testing & Optimization**
- [ ] Backtesting on historical data (2+ years)
- [ ] Paper trading with real-time data
- [ ] Performance optimization
- [ ] Bug fixes and edge cases
- [ ] Documentation

**Total Phase 1 Timeline:** 16 weeks (4 months)

---

### 8. Risk Considerations & Safeguards

**Technical Risks:**
- WebSocket disconnections → Implement reconnection logic with exponential backoff
- API rate limits → Queue system with rate limiting
- Latency issues → Deploy on exchange-proximate servers
- Data quality → Validate and sanitize all inputs

**Trading Risks:**
- Overfitting → Validate on out-of-sample data
- Black swan events → Hard stop at 5% daily loss
- Flash crashes → Pause trading on extreme volatility
- API failures → Manual override capability

**Safeguards:**
- Maximum 3 concurrent positions
- Daily loss limit: 5% ($500)
- Per-trade risk: 2% ($200)
- Circuit breaker on 3 consecutive losses
- No trading during major news events

---

### 9. Performance Metrics

**Track These KPIs:**
- Win rate (target: >50%)
- Average RR ratio (target: >2.0)
- Sharpe ratio (target: >1.5)
- Max drawdown (target: <15%)
- Profit factor (target: >2.0)
- Average holding time
- Strategy type breakdown (scalp/day/swing)

---

## Phase 2: User-Facing Platform (Future)

### High-Level Overview
- **Frontend:** Next.js 14+ with TypeScript
- **Backend API:** FastAPI or NestJS
- **Authentication:** Clerk or Supabase Auth
- **Real-time Updates:** WebSocket + Server-Sent Events
- **Deployment:** Vercel (Frontend) + AWS/Railway (Backend)

### Key Features:
1. User dashboard with portfolio overview
2. Real-time trade signals display
3. Performance analytics and charts
4. Risk parameter configuration
5. Exchange API key management (encrypted)
6. Trade history and journal
7. Backtesting interface
8. Subscription/pricing tiers

**Phase 2 Timeline:** 12 weeks (after Phase 1 validation)

---

## Success Criteria (Phase 1)

**Minimum Viable Performance:**
- [ ] System runs autonomously for 30+ days
- [ ] Win rate > 45% with RR > 2.0
- [ ] Max drawdown < 20%
- [ ] Positive P&L over 3-month period
- [ ] <1% system downtime
- [ ] Average 3-5 quality setups per week

**Code Quality:**
- [ ] 80%+ test coverage
- [ ] Comprehensive logging
- [ ] Error handling for all edge cases
- [ ] Performance benchmarks met (<500ms analysis time)

---

## Technology Recommendations

**Agent Framework:** 
- **LangGraph** (preferred) - Better for complex state machines
- **CrewAI** (alternative) - Simpler setup, good for rapid prototyping

**LLM Provider:**
- **Anthropic Claude Sonnet 4.5** - Best reasoning, longer context
- **OpenAI GPT-4o** - Faster, good structured outputs

**Why AI/LLM for Trading?**
- Complex pattern recognition across multiple data sources
- Natural language reasoning for trade confluence
- Adaptive learning from market regime changes
- Context retention across analysis cycles
- Ability to explain trade decisions

---

## Budget Estimates (Phase 1)

**Infrastructure:**
- VPS (low latency): $50-100/month
- Database hosting: $20-50/month
- LLM API costs: $200-500/month (depending on usage)

**Development:**
- 4 months full-time development
- Testing capital: $10,000 (virtual/paper initially)

**Total Phase 1 Cost:** ~$1,500-2,500 (excluding labor)

---

## Next Steps

1. **Validate Core Assumptions:**
   - Test SMC/ICT detection accuracy on historical data
   - Validate LLM reasoning quality for trade setups
   - Benchmark strategy win rate with manual backtesting

2. **Start with Data Pipeline:**
   - Get Binance WebSocket streaming working
   - Build historical data fetcher
   - Set up database schemas

3. **Iterative Development:**
   - Build one agent at a time
   - Test each component independently
   - Integrate incrementally

4. **Paper Trade First:**
   - Run with paper money for minimum 2 months
   - Validate performance metrics
   - Only go live after consistent profitability

---

## Conclusion

This system combines cutting-edge AI agents with professional trading methodology (SMC/ICT) to create a truly autonomous trading system. The key to success is:

1. **Robust data infrastructure** - Clean, reliable data
2. **Multiple confluence requirements** - Never trade on single signal
3. **Strict risk management** - Preserve capital above all
4. **Continuous monitoring** - Track and adapt to market changes
5. **Disciplined execution** - Let the system work, avoid manual interference

The multi-agent architecture ensures each component specializes in its domain while the orchestrator coordinates them into a cohesive trading system that thinks and acts like a professional trader.

**Remember:** Past performance doesn't guarantee future results. Always start with paper trading and only deploy real capital after thorough validation.