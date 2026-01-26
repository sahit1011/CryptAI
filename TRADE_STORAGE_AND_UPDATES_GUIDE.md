# Trade Storage & Real-time Updates Guide

## 📊 Overview

This guide explains how trades are stored in your system and how real-time updates flow from backend to frontend.

---

## 🗄️ Trade Storage Architecture

### Database: PostgreSQL
- **Location**: `postgresql://trader:secure_password_here@localhost:5432/trading_agent`
- **Table**: `trades`
- **Manager**: `TradeHistoryManager` (`src/memory/trade_history_manager.py`)

### Trade Table Schema

```sql
CREATE TABLE trades (
    id SERIAL PRIMARY KEY,
    trade_id VARCHAR(100) UNIQUE NOT NULL,
    symbol VARCHAR(20) NOT NULL,
    direction VARCHAR(10) NOT NULL,          -- LONG/SHORT
    entry_price DECIMAL(20, 8) NOT NULL,
    entry_time TIMESTAMP NOT NULL,
    exit_price DECIMAL(20, 8),
    exit_time TIMESTAMP,
    position_size DECIMAL(20, 8) NOT NULL,
    stop_loss DECIMAL(20, 8) NOT NULL,
    take_profit_levels JSONB,               -- Array of TP levels
    risk_amount DECIMAL(20, 8) NOT NULL,
    pnl DECIMAL(20, 8),
    pnl_percentage DECIMAL(10, 4),
    is_winner BOOLEAN,
    strategy_type VARCHAR(50),               -- ICT_BREAKOUT, SMC_REVERSAL, etc.
    confidence_score DECIMAL(5, 4),
    confluence_count INTEGER,
    market_regime VARCHAR(50),               -- TRENDING_UP, RANGING, CHOPPY
    atr_at_entry DECIMAL(20, 8),
    smc_patterns JSONB,                      -- Array of SMC patterns
    ict_setups JSONB,                        -- Array of ICT setups
    exit_reason VARCHAR(100),                -- TP1_HIT, STOP_LOSS, etc.
    notes TEXT,
    risk_reward_ratio DECIMAL(10, 2),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
)
```

### How Trades Are Saved

1. **Entry**: When a trade is executed
   ```python
   manager.store_trade(
       trade_id="TRADE_001",
       symbol="BTCUSDT",
       direction="LONG",
       entry_price=95420.50,
       entry_time=datetime.now(),
       position_size=0.5,
       stop_loss=95100.00,
       take_profit_levels=[96000.00, 96500.00],
       # ... other fields
   )
   ```

2. **Exit**: When a trade is closed
   ```python
   manager.update_trade_exit(
       trade_id="TRADE_001",
       exit_price=96150.30,
       exit_time=datetime.now(),
       exit_reason="TP1_HIT",
       notes="Clean breakout with strong volume"
   )
   ```

---

## 🔄 Real-time Update Flow

### Architecture Diagram

```
┌─────────────────────┐
│ PaperTradingEngine  │
│  (Backend)          │
└──────────┬──────────┘
           │
           │ 1. Updates portfolio/positions
           │
           ▼
┌─────────────────────┐
│   MessageBus        │
│   (Redis Pub/Sub)   │
└──────────┬──────────┘
           │
           │ 2. Publishes to channel "execution_status"
           │
           ▼
┌─────────────────────┐
│   server.py         │
│   (FastAPI)         │
└──────────┬──────────┘
           │
           │ 3. Broadcasts via WebSocket
           │
           ▼
┌─────────────────────┐
│  useMarketData.ts   │
│  (Frontend Hook)    │
└──────────┬──────────┘
           │
           │ 4. Updates Zustand store
           │
           ▼
┌─────────────────────┐
│   Dashboard UI      │
│   (React)           │
└─────────────────────┘
```

### Detailed Flow

#### 1. Backend: PaperTradingEngine
**File**: `crypto-trading-agent/src/execution/paper_trading_engine.py`

```python
# When position changes (entry/exit)
async def _update_position(self, order: PaperOrder):
    # ... update position logic ...
    
    # Publish to MessageBus
    await self.publish_portfolio_update()

# Publish method
async def publish_portfolio_update(self):
    perf = self.get_performance_summary()
    positions = self.get_positions()
    
    # Persist to Redis StateManager
    await self.state_manager.update_portfolio(perf)
    
    # Publish balance update
    await self._publish_update("execution_status", "balance_update", {
        "initial_balance": perf["initial_balance"],
        "current_balance": perf["current_balance"],
        "total_equity": perf["total_equity"],
        "unrealized_pnl": perf["unrealized_pnl"],
        "realized_pnl": perf["realized_pnl"],
        # ... other fields
    })
    
    # Publish position update
    await self._publish_update("execution_status", "position_update", positions)
```

#### 2. MessageBus: Redis Pub/Sub
**File**: `crypto-trading-agent/src/core/message_bus.py`

- Channel: `execution_status`
- Payload format:
  ```json
  {
    "type": "balance_update" | "position_update",
    "payload": { ... },
    "timestamp": "2025-12-01T12:00:00"
  }
  ```

#### 3. Backend Server: WebSocket Broadcast
**File**: `crypto-trading-agent/src/api/server.py`

```python
async def handle_agent_message(data: Dict[str, Any]):
    """Callback for agent messages from MessageBus"""
    msg_type = "agent_update"
    
    # Check if this is an execution update
    if data.get("type") in ["balance_update", "position_update"]:
        msg_type = "execution_status"
    
    payload = {
        "type": msg_type,
        "data": data
    }
    await manager.broadcast(payload)
```

**On Client Connection**:
```python
async def connect(self, websocket: WebSocket):
    await websocket.accept()
    
    # Send initial state immediately
    portfolio = await self.state_manager.get_portfolio_state()
    positions = await self.state_manager.get_positions()
    
    await websocket.send_text(json.dumps({
        "type": "execution_status",
        "data": {
            "type": "balance_update",
            "payload": portfolio
        }
    }))
    
    await websocket.send_text(json.dumps({
        "type": "execution_status",
        "data": {
            "type": "position_update",
            "payload": positions
        }
    }))
```

#### 4. Frontend: WebSocket Handler
**File**: `frontend/src/hooks/useMarketData.ts`

```typescript
ws.onmessage = (event) => {
    const payload = JSON.parse(event.data)
    const { type, data } = payload

    if (type === 'execution_status') {
        const { type: updateType, payload: execPayload } = data

        if (updateType === 'balance_update') {
            console.log('📊 Portfolio update received:', execPayload)
            useStore.getState().setPortfolio({
                totalValue: execPayload.total_equity,
                totalInvested: execPayload.total_equity - execPayload.current_balance,
                totalPnl: execPayload.realized_pnl + execPayload.unrealized_pnl,
                totalPnlPercent: ((execPayload.realized_pnl + execPayload.unrealized_pnl) / execPayload.initial_balance) * 100,
                balance: execPayload.current_balance,
                unrealizedPnl: execPayload.unrealized_pnl,
                realizedPnl: execPayload.realized_pnl,
                winRate: execPayload.win_rate,
                totalTrades: execPayload.total_trades
            })
        } else if (updateType === 'position_update') {
            console.log('📈 Position update received:', execPayload)
            const trades = execPayload.map((pos: any) => ({
                id: pos.symbol,
                symbol: pos.symbol,
                side: pos.positionSide,
                entry: parseFloat(pos.entryPrice),
                current: parseFloat(pos.markPrice),
                pnl: parseFloat(pos.unRealizedProfit),
                pnlPercent: (parseFloat(pos.unRealizedProfit) / (parseFloat(pos.entryPrice) * parseFloat(pos.positionAmt))) * 100,
                status: 'OPEN'
            }))
            useStore.getState().setTrades(trades)
        }
    }
}
```

#### 5. Frontend: Zustand Store
**File**: `frontend/src/store/useStore.ts`

```typescript
interface Store {
    portfolio: {
        totalValue: number
        totalPnl: number
        balance: number
        unrealizedPnl: number
        realizedPnl: number
        winRate: number
        totalTrades: number
    }
    trades: Trade[]
    setPortfolio: (portfolio: Partial<Portfolio>) => void
    setTrades: (trades: Trade[]) => void
}
```

---

## 🐛 Troubleshooting: Why You're Seeing Default Values

### Issue
Frontend displays:
```
Portfolio Value: $0.00
Total P&L: $0.00
Win Rate: 0%
```

### Root Causes

1. **PaperTradingEngine not publishing initial state**
   - ✅ **FIXED**: `publish_initial_state()` is called in `run_paper_trading_simulation.py` line 122
   
2. **StateManager not persisting data**
   - Check if Redis is running: `docker ps | grep redis`
   - Check Redis data: `redis-cli HGETALL state:portfolio`

3. **MessageBus not connected**
   - Check logs for "MessageBus connected" message
   - Verify Redis URL in config

4. **WebSocket not receiving messages**
   - Check browser console for "Connected to backend WebSocket"
   - Check for errors in `useMarketData.ts`

### Debugging Steps

1. **Check Backend Logs**
   ```bash
   # Look for these messages:
   # ✅ Paper Trading Engine initialized - Published initial $10,000.00
   # 📊 Published initial portfolio state: $10,000.00
   # 💾 Persisted initial portfolio state to Redis
   ```

2. **Check Redis State**
   ```bash
   redis-cli
   > HGETALL state:portfolio
   > LRANGE state:positions 0 -1
   ```

3. **Check WebSocket Messages**
   - Open browser DevTools → Network → WS
   - Look for messages with type `execution_status`

4. **Check Frontend Console**
   ```
   ✅ Connected to backend WebSocket
   📊 Portfolio update received: { ... }
   📈 Position update received: [ ... ]
   ```

---

## 🔧 Continuous Updates

### Background Task
**File**: `run_paper_trading_simulation.py`

```python
async def continuous_pnl_updates(self):
    """
    Continuously update position P&L and broadcast to frontend
    Runs every 10 seconds independently of trading cycles
    """
    while True:
        try:
            positions = self.paper_engine.get_positions()
            
            if positions:
                for position in positions:
                    symbol = position['symbol']
                    current_price = await self.state_manager.get(f"current_price:{symbol}")
                    
                    if current_price:
                        # Update position P&L
                        await self.paper_engine.update_positions(symbol, float(current_price))
                        
                        # Check SL/TP triggers
                        await self.paper_engine.check_limit_orders(symbol, float(current_price))
                
                # Broadcast updated portfolio
                await self.paper_engine.publish_portfolio_update()
            
            await asyncio.sleep(10)  # Update every 10 seconds
            
        except Exception as e:
            logger.error(f"Error in continuous P&L updates: {e}")
            await asyncio.sleep(10)
```

This ensures:
- Real-time P&L updates every 10 seconds
- SL/TP triggers are checked continuously
- Frontend always shows current data

---

## 📝 Populating Historical Trades

### Script
**File**: `crypto-trading-agent/populate_historical_trades.py`

Run this to add 9 historical trades (7 wins, 2 losses) from 5 days ago:

```bash
cd crypto-trading-agent
python populate_historical_trades.py
```

This will:
- Create 9 realistic trades with proper SMC/ICT patterns
- Set final capital to $11,850 (profit of $1,850)
- Store in PostgreSQL `trades` table
- Display summary table

---

## 🎯 Expected Behavior

### On System Startup
1. Backend starts → `PaperTradingEngine` initialized
2. `publish_initial_state()` called → Sends $10,000 to Redis + MessageBus
3. Frontend connects → Receives initial state immediately
4. Dashboard displays: **Portfolio Value: $10,000.00**

### During Trading
1. Trade executed → Position opened
2. `_update_position()` called → Updates internal state
3. `publish_portfolio_update()` called → Broadcasts to frontend
4. Dashboard updates in real-time

### Continuous Updates
1. Every 10 seconds → `continuous_pnl_updates()` runs
2. Gets current prices → Updates position P&L
3. Broadcasts to frontend → Dashboard shows live P&L

---

## 🚀 Quick Fix Checklist

If frontend shows default values:

- [ ] Redis is running (`docker ps`)
- [ ] Backend server is running (`python -m uvicorn src.api.server:app`)
- [ ] Paper trading simulation is running (`python run_paper_trading_simulation.py`)
- [ ] Frontend is connected (check browser console for "✅ Connected")
- [ ] Check backend logs for "Published initial portfolio state"
- [ ] Check Redis: `redis-cli HGETALL state:portfolio`
- [ ] Check WebSocket messages in browser DevTools → Network → WS

---

## 📚 Related Files

### Backend
- `src/execution/paper_trading_engine.py` - Trading engine
- `src/api/server.py` - WebSocket server
- `src/core/message_bus.py` - Redis pub/sub
- `src/core/state_manager.py` - State persistence
- `src/memory/trade_history_manager.py` - Database operations

### Frontend
- `frontend/src/hooks/useMarketData.ts` - WebSocket handler
- `frontend/src/store/useStore.ts` - Zustand store
- `frontend/src/components/Dashboard.tsx` - UI components

### Scripts
- `run_paper_trading_simulation.py` - Main simulation
- `populate_historical_trades.py` - Populate test data
- `init_database.py` - Initialize PostgreSQL schema
