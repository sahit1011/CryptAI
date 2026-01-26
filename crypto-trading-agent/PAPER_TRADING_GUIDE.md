# Paper Trading Simulation Guide

## Overview

The paper trading simulation runs your complete multi-agent trading system with realistic order execution, mimicking BingX exchange behavior without risking real capital.

## Features

### Realistic Order Execution
- **Slippage Modeling**: 0.01% - 0.05% realistic slippage
- **Commission Fees**: 
  - Maker: 0.04%
  - Taker: 0.06%
- **Order Types**: Market, Limit, Stop-Market, Take-Profit
- **Position Tracking**: Real-time P&L calculation
- **Order Fill Simulation**: Realistic timing and price improvement

### Complete Trading Pipeline
1. **Data Collection** - Live Binance data
2. **Market Analysis** - SMC/ICT + LLM analysis
3. **Regime Detection** - Market condition classification
4. **Strategy Generation** - Trade setup creation
5. **Risk Validation** - Portfolio heat and risk checks
6. **Paper Execution** - Simulated order placement
7. **Memory Logging** - Trade history and analytics

## Quick Start

### 1. Install Dependencies
```bash
cd crypto-trading-agent
pip install -r requirements.txt
```

### 2. Set Environment Variables
```bash
# Required
export OPENAI_API_KEY="your_openai_key"
export ANTHROPIC_API_KEY="your_anthropic_key"

# Optional (for data only)
export BINANCE_API_KEY="your_binance_key"
export BINANCE_SECRET_KEY="your_binance_secret"
```

### 3. Start Redis (Required)
```bash
# Windows (if using Docker)
docker run -d -p 6379:6379 redis:latest

# Or use local Redis installation
redis-server
```

### 4. Run Simulation

#### Short Test (10 cycles = 30 minutes)
```bash
python run_paper_trading_simulation.py
```

#### Full Day Simulation (480 cycles = 24 hours)
Edit `run_paper_trading_simulation.py`:
```python
max_cycles = 480  # 24 hours
cycle_interval = 180  # 3 minutes
```

Then run:
```bash
python run_paper_trading_simulation.py
```

## Simulation Parameters

### Default Configuration
```python
initial_balance = 10000.0      # Starting capital
symbol = "BTC/USDT"            # Trading pair
cycle_interval = 180           # 3 minutes between cycles
max_cycles = 10                # Number of cycles (default: 10 for testing)
```

### Customization
Edit these parameters in `run_paper_trading_simulation.py`:

```python
simulation = PaperTradingSimulation(
    initial_balance=10000.0,   # Change starting balance
    symbol="BTC/USDT",         # Change trading pair
    cycle_interval=180,        # Change cycle frequency
    max_cycles=480             # Change simulation duration
)
```

## Expected Output

### Console Output
```
╭─────────────────────────────────────────────────────────╮
│        Paper Trading Simulation Setup                   │
│  Initial Balance: $10,000.00                            │
│  Symbol: BTC/USDT                                       │
│  Cycle Interval: 180s                                   │
│  Max Cycles: 10                                         │
╰─────────────────────────────────────────────────────────╯

✅ Data Agent initialized
✅ Analysis Agent initialized
✅ Memory Agent initialized
✅ Strategy Agent initialized
✅ Risk Agent initialized

All systems ready! Starting simulation...

================================================================================
Cycle #1 - 04:24:41
================================================================================

📊 Phase 1: Data Collection
  Current Price: $43,250.00
  Candles Fetched: 100

🔍 Phase 2: Market Analysis
  Opportunities Found: 1
  Direction: LONG
  Confidence: 82.00%
  Confluences: 5

🌍 Phase 3: Regime Detection
  Regime: TRENDING_BULLISH

⚡ Phase 4: Strategy Generation
  Entry: $43,050.00
  Stop Loss: $42,750.00
  R/R Ratio: 3.89

🛡️ Phase 5: Risk Validation
  ✅ Trade APPROVED
  Position Size: 0.667 BTC
  Risk Amount: $200.00

🚀 Phase 6: Paper Trading Execution
  Entry Order: PT_20251127_042441_0001
  Status: OPEN
  Stop-Loss Order: PT_20251127_042441_0002
  TP1 Order: PT_20251127_042441_0003 @ $43,650.00
  TP2 Order: PT_20251127_042441_0004 @ $44,200.00
  TP3 Order: PT_20251127_042441_0005 @ $44,800.00

💾 Phase 7: Memory Logging
  ✅ Trade logged to database
```

### Performance Table (Every 10 Cycles)
```
┏━━━━━━━━━━━━━━━━━━━━━━┳━━━━━━━━━━━━━━━━━━┓
┃ Metric               ┃ Value            ┃
┡━━━━━━━━━━━━━━━━━━━━━━╇━━━━━━━━━━━━━━━━━━┩
│ Initial Balance      │ $10,000.00       │
│ Current Balance      │ $10,776.00       │
│ Total Equity         │ $10,901.00       │
│ Realized P&L         │ +$776.00 (+7.76%)│
│ Unrealized P&L       │ +$125.00         │
│ Total Trades         │ 3                │
│ Win Rate             │ 100.0%           │
│ Total Commission     │ $45.20           │
│ Max Drawdown         │ 0.05%            │
│ Open Positions       │ 2                │
└──────────────────────┴──────────────────┘
```

## Performance Metrics

### What to Expect (24-Hour Simulation)

**Conservative System:**
- **Trades per Day**: 3-5 high-quality setups
- **Win Rate Target**: >50%
- **Average R/R**: >2.0
- **Daily Return**: 2-10% (varies by market conditions)

**Good Day:**
- 3-5 trades executed
- 5-10% profit
- 80%+ win rate

**Average Day:**
- 1-2 trades executed
- 2-4% profit
- 50-60% win rate

**Bad Day:**
- 0-1 trades
- -2% to 0%
- Risk management prevents large losses

**No-Trade Day:**
- 0 trades (no quality setups)
- 0% return
- System waits for optimal conditions

## Logs and Reports

### Log Files
```
logs/paper_trading_YYYY-MM-DD.log  # Daily rotation
```

### Performance Data
- Trade history stored in PostgreSQL
- Vector embeddings in ChromaDB
- Analysis results in JSON files

## Troubleshooting

### Redis Connection Error
```
Error: Could not connect to Redis
```
**Solution**: Start Redis server
```bash
redis-server
# or
docker run -d -p 6379:6379 redis:latest
```

### API Key Error
```
Error: OPENAI_API_KEY not found
```
**Solution**: Set environment variables
```bash
export OPENAI_API_KEY="your_key"
export ANTHROPIC_API_KEY="your_key"
```

### No Opportunities Found
```
Opportunities Found: 0
```
**Normal**: System is selective. It only trades high-quality setups with 3+ confluences.

### High LLM Costs
```
Daily LLM Cost: $300+
```
**Solution**: 
- Reduce cycle frequency (3min → 5min)
- Enable LLM caching (already implemented)
- Use conditional LLM calls

## Advanced Configuration

### Paper Trading Engine Settings

Edit `src/execution/paper_trading_engine.py`:

```python
engine = PaperTradingEngine(
    initial_balance=10000.0,
    maker_fee=0.0004,              # 0.04% (BingX rate)
    taker_fee=0.0006,              # 0.06% (BingX rate)
    slippage_range=(0.0001, 0.0005), # 0.01% - 0.05%
    enable_realistic_fills=True    # Realistic order fills
)
```

### Risk Parameters

Edit `src/agents/risk_agent.py`:

```python
risk_params = RiskParameters(
    max_risk_per_trade=0.02,      # 2% per trade
    max_portfolio_heat=0.06,      # 6% total exposure
    max_daily_loss=0.05,          # 5% daily loss limit
    max_concurrent_positions=3    # Max 3 positions
)
```

## Next Steps

### After Successful Simulation

1. **Analyze Results**
   - Review trade history
   - Check win rate and R/R ratios
   - Identify improvement areas

2. **Optimize Parameters**
   - Adjust risk limits
   - Fine-tune confluence requirements
   - Optimize entry/exit logic

3. **Extended Testing**
   - Run 7-day simulation
   - Test different market conditions
   - Validate across multiple symbols

4. **Real Exchange Integration**
   - Integrate BingX API
   - Start with testnet
   - Deploy with small capital

## Safety Features

### Built-in Protections
- ✅ Maximum 2% risk per trade
- ✅ Maximum 6% portfolio heat
- ✅ Daily loss limit (5%)
- ✅ Circuit breaker on losing streaks
- ✅ Correlation analysis
- ✅ Position size validation

### What Can't Go Wrong
- No real money at risk
- No exchange API errors
- No slippage surprises (simulated)
- No unexpected fees

## Support

### Issues?
1. Check logs: `logs/paper_trading_*.log`
2. Verify Redis is running
3. Confirm API keys are set
4. Review error messages

### Questions?
- Review architecture docs: `docs/architecture_workflow_guide.md`
- Check PRD: `docs/prd.md`
- See 24-hour workflow: `TYPICAL_24HR_WORKFLOW.md`

---

**Ready to trade!** 🚀

Start with a short simulation (10 cycles) to verify everything works, then run a full 24-hour simulation to see your system in action.
