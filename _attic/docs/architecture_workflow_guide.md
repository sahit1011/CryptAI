# Crypto Trading Agent System - Complete Architecture & Workflow

## Table of Contents
1. [Multi-Agent Orchestration Strategy](#multi-agent-orchestration)
2. [LLM Context Management](#llm-context-management)
3. [Detailed Agent Workflows](#detailed-agent-workflows)
4. [Communication Protocols](#communication-protocols)
5. [Implementation Guide](#implementation-guide)

---

# 1. Multi-Agent Orchestration Strategy

## 1.1 Orchestration Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                  MASTER ORCHESTRATOR (LangGraph)                 │
│  ┌───────────────────────────────────────────────────────────┐  │
│  │  State Machine Controller                                  │  │
│  │  - Manages agent lifecycle                                 │  │
│  │  - Routes messages between agents                          │  │
│  │  - Handles failures & retries                              │  │
│  │  - Maintains global state                                  │  │
│  └───────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
                              │
        ┌─────────────────────┼─────────────────────┐
        │                     │                     │
┌───────▼────────┐   ┌────────▼────────┐   ┌──────▼────────┐
│  SENSING       │   │  REASONING      │   │  ACTING       │
│  LAYER         │   │  LAYER          │   │  LAYER        │
│                │   │                 │   │               │
│ • Data Agent   │   │ • Analysis      │   │ • Execution   │
│ • Market       │   │   Agent         │   │   Agent       │
│   Monitor      │   │ • Strategy      │   │ • Risk Agent  │
│                │   │   Agent         │   │               │
└────────────────┘   │ • Memory Agent  │   └───────────────┘
                     └─────────────────┘
```

## 1.2 Agent Communication Protocol

### Message Bus Architecture
```python
class MessageBus:
    """
    Central message routing system for inter-agent communication
    Uses Redis Pub/Sub for real-time messaging
    """
    
    channels = {
        'market_data': ['data_agent' → 'analysis_agent'],
        'analysis_results': ['analysis_agent' → 'strategy_agent'],
        'trade_signals': ['strategy_agent' → 'risk_agent'],
        'approved_trades': ['risk_agent' → 'execution_agent'],
        'execution_status': ['execution_agent' → 'memory_agent'],
        'alerts': ['any_agent' → 'orchestrator']
    }
```

### Event-Driven Communication
```python
class AgentMessage:
    """Standard message format for inter-agent communication"""
    
    id: str              # Unique message ID
    timestamp: datetime  # When message was created
    sender: str         # Agent that sent message
    receiver: str       # Target agent
    priority: int       # 1-10 (10 = critical)
    message_type: str   # 'data', 'signal', 'alert', 'command'
    payload: dict       # Actual data
    requires_ack: bool  # Whether acknowledgment is needed
    parent_id: str      # For tracking conversation threads
```

---

# 2. LLM Context Management

## 2.1 Context Strategy Per Agent

### **Agent 1: Data Collection Agent**
**LLM Usage:** ❌ **NO LLM REQUIRED**
- Pure computational agent
- Uses deterministic algorithms only
- Faster execution without LLM overhead

**Why No LLM?**
- Data fetching is purely procedural
- No reasoning or decision-making needed
- Reduces costs and latency

---

### **Agent 2: Market Analysis Agent**
**LLM Usage:** ✅ **PRIMARY LLM CONSUMER**
**Model:** Claude Sonnet 4.5 (200K context window)

**Context Window Structure:**
```python
context = {
    # System Prompt (2K tokens)
    "role": "Expert technical analyst specializing in SMC, ICT, and multi-timeframe analysis",
    
    # Market Data (50K tokens)
    "current_data": {
        "1d_candles": last_100_candles,   # 5K tokens
        "4h_candles": last_200_candles,   # 8K tokens
        "1h_candles": last_300_candles,   # 10K tokens
        "15m_candles": last_400_candles,  # 12K tokens
        "5m_candles": last_500_candles,   # 15K tokens
    },
    
    # Pre-computed Indicators (20K tokens)
    "indicators": {
        "rsi": [...],
        "macd": [...],
        "bollinger_bands": [...],
        "ema_ribbon": [...],
        "volume_profile": [...],
    },
    
    # SMC/ICT Context (30K tokens)
    "smc_context": {
        "order_blocks": [...],
        "fvg_zones": [...],
        "liquidity_pools": [...],
        "supply_demand_zones": [...],
    },
    
    # Historical Context (40K tokens)
    "memory": {
        "recent_trades": last_20_trades,
        "market_regime": "trending_bullish",
        "performance_stats": {...},
    },
    
    # Instructions (8K tokens)
    "task": """
    Analyze the provided multi-timeframe data and identify:
    1. Current market structure (bullish/bearish/neutral)
    2. Key support/resistance levels
    3. SMC confluences (Order Blocks, FVGs, BOS/CHoCH)
    4. ICT setups (liquidity sweeps, killzones, OTE)
    5. Potential trade opportunities with confluence
    
    Provide detailed reasoning for each finding.
    """
}

# Total: ~150K tokens, leaving 50K for response
```

**Optimization Strategies:**
```python
# 1. Sliding Window for Historical Data
def optimize_candle_data(candles, max_tokens=15000):
    """Only include relevant recent candles"""
    token_per_candle = 30  # Approximate
    max_candles = max_tokens // token_per_candle
    return candles[-max_candles:]

# 2. Compress Indicator Data
def compress_indicators(indicators):
    """Send only critical values, not full arrays"""
    return {
        "rsi": {
            "current": indicators['rsi'][-1],
            "divergence": detect_divergence(indicators['rsi']),
            "trend": "oversold" if indicators['rsi'][-1] < 30 else "overbought"
        },
        # Compress other indicators similarly
    }

# 3. Smart Context Pruning
def prune_context(context, priority_threshold=0.7):
    """Remove low-priority information based on current market regime"""
    if context['market_regime'] == 'ranging':
        # In ranging market, remove trend-following indicators
        del context['indicators']['ema_ribbon']
    return context
```

---

### **Agent 3: Strategy Generation Agent**
**LLM Usage:** ✅ **SECONDARY LLM CONSUMER**
**Model:** GPT-4o (128K context window) - Faster, cheaper for structured output

**Context Window Structure:**
```python
context = {
    # System Prompt (3K tokens)
    "role": """Professional crypto trader generating trade setups.
    You must output structured JSON with entry, SL, TP, and detailed reasoning.
    Follow strict risk-reward ratios (min 1:2).""",
    
    # Analysis Results (40K tokens)
    "analysis_results": {
        "from": "analysis_agent",
        "timestamp": "2025-11-06T10:30:00Z",
        "findings": {
            "mtf_bias": "Bullish on 4H, neutral on 1H",
            "smc_confluences": [...],
            "ict_setups": [...],
            "indicator_signals": [...]
        }
    },
    
    # Current Market State (20K tokens)
    "market_state": {
        "symbol": "BTCUSDT",
        "current_price": 43250.00,
        "atr_14": 1250.00,
        "volatility": "moderate",
        "order_book_imbalance": "neutral"
    },
    
    # Risk Parameters (5K tokens)
    "risk_parameters": {
        "account_balance": 10000,
        "max_risk_per_trade": 200,  # 2%
        "current_positions": 1,
        "available_exposure": 400   # 4% remaining
    },
    
    # Historical Performance (30K tokens)
    "historical_context": {
        "similar_setups_win_rate": 0.62,
        "avg_rr_ratio": 2.4,
        "recent_trades": [...],
        "lessons_learned": [
            "Bitcoin tends to respect 4H order blocks during London session",
            "FVG fills occur 78% of the time in current regime"
        ]
    },
    
    # Structured Output Schema (10K tokens)
    "output_schema": {
        "trade_setup": {
            "symbol": "string",
            "direction": "LONG|SHORT",
            "entry_price": "float",
            "stop_loss": "float",
            "take_profit_levels": ["float", "float", "float"],
            "position_size": "float",
            "risk_reward_ratio": "float",
            "confidence_score": "float (0-1)",
            "strategy_type": "SCALP|DAY_TRADE|SWING",
            "reasoning": {
                "confluence_count": "int",
                "key_factors": ["string"],
                "invalidation_conditions": ["string"]
            }
        }
    }
}

# Total: ~108K tokens, leaving 20K for response
```

**Prompt Engineering for Strategy Agent:**
```python
STRATEGY_AGENT_PROMPT = """
You are an expert crypto futures trader generating high-probability trade setups.

CRITICAL RULES:
1. Only suggest trades with 3+ confluences
2. Minimum risk-reward ratio: 1:2
3. Confidence score must be >0.75 to trade
4. Always provide clear invalidation conditions
5. Consider current market regime

DECISION FRAMEWORK:
Step 1: Verify multi-timeframe alignment
Step 2: Check SMC/ICT confluences
Step 3: Validate with indicators
Step 4: Calculate risk-reward
Step 5: Assess confidence based on historical performance
Step 6: Generate structured trade setup

OUTPUT FORMAT:
Return ONLY valid JSON matching the provided schema.
If no high-quality setup exists, return: {"trade_setup": null, "reason": "..."}

Current Analysis:
{analysis_results}

Your task: Generate a trade setup or explain why conditions aren't met.
"""
```

---

### **Agent 4: Risk Management Agent**
**LLM Usage:** ⚠️ **MINIMAL LLM - HYBRID APPROACH**
**Model:** GPT-4o-mini (128K context window) - For edge case reasoning only

**Why Minimal LLM?**
- Risk calculations are mostly deterministic
- LLM only used for complex scenario analysis
- 95% of decisions are rule-based

**Context Window Structure:**
```python
context = {
    # System Prompt (1K tokens)
    "role": "Risk management validator. Verify trade meets risk parameters.",
    
    # Proposed Trade (5K tokens)
    "proposed_trade": {
        "symbol": "BTCUSDT",
        "type": "LONG",
        "entry": 43250,
        "sl": 42800,
        "tp": [43700, 44200, 44800],
        "position_size": 0.1
    },
    
    # Risk State (10K tokens)
    "risk_state": {
        "account_balance": 10000,
        "current_positions": [
            {"symbol": "ETHUSDT", "exposure": 150, "unrealized_pnl": 50}
        ],
        "daily_pnl": -80,
        "max_daily_loss": -500,
        "portfolio_heat": 0.035  # 3.5%
    },
    
    # Rules (5K tokens)
    "risk_rules": {
        "max_risk_per_trade": 0.02,      # 2%
        "max_portfolio_heat": 0.06,       # 6%
        "max_daily_loss": 0.05,           # 5%
        "max_concurrent_positions": 3,
        "min_risk_reward": 2.0,
        "correlated_assets": ["BTCUSDT", "ETHUSDT"]  # Don't double-up
    },
    
    # Task (2K tokens)
    "task": """
    Validate if this trade meets all risk parameters.
    Return: {"approved": true/false, "reason": "...", "adjusted_size": float}
    
    If trade violates rules, suggest adjustments or reject.
    """
}

# Total: ~23K tokens - Very lightweight
```

**Deterministic Pre-Checks (No LLM):**
```python
class RiskManager:
    def deterministic_check(self, trade, portfolio):
        """Fast rule-based validation before LLM"""
        
        # Calculate position size
        risk_amount = portfolio.balance * 0.02
        price_risk = abs(trade.entry - trade.stop_loss)
        max_size = risk_amount / price_risk
        
        # Check 1: Position size within limits
        if trade.position_size > max_size:
            return {"approved": False, "reason": "Position too large"}
        
        # Check 2: Portfolio heat
        new_heat = portfolio.heat + (trade.position_size * price_risk / portfolio.balance)
        if new_heat > 0.06:
            return {"approved": False, "reason": "Exceeds portfolio heat limit"}
        
        # Check 3: Daily loss limit
        if portfolio.daily_pnl < -500:
            return {"approved": False, "reason": "Daily loss limit hit"}
        
        # Check 4: Concurrent positions
        if len(portfolio.positions) >= 3:
            return {"approved": False, "reason": "Max positions reached"}
        
        # Check 5: Risk-reward ratio
        avg_tp = sum(trade.take_profit) / len(trade.take_profit)
        rr_ratio = (avg_tp - trade.entry) / price_risk
        if rr_ratio < 2.0:
            return {"approved": False, "reason": f"RR ratio too low: {rr_ratio:.2f}"}
        
        # All checks passed
        return {"approved": True, "continue_to_llm": True}
    
    def llm_validation(self, trade, portfolio):
        """LLM for complex scenarios only"""
        # Only called if deterministic checks pass
        # Handles edge cases like:
        # - Correlated positions (BTC + ETH both long)
        # - Market regime changes (high volatility event)
        # - Recent losing streak (should reduce size?)
        pass
```

---

### **Agent 5: Execution Agent**
**LLM Usage:** ❌ **NO LLM REQUIRED**
- Pure API integration
- Deterministic order placement
- Error handling with retries

---

### **Agent 6: Memory & Context Manager**
**LLM Usage:** ✅ **SEMANTIC SEARCH & LEARNING**
**Model:** GPT-4o (for embedding generation) + Vector DB

**Context Window Structure:**
```python
context = {
    # System Prompt (2K tokens)
    "role": "Trade historian and pattern recognizer",
    
    # Current Query (5K tokens)
    "query": {
        "type": "similar_scenarios",
        "current_setup": {
            "symbol": "BTCUSDT",
            "pattern": "bullish_order_block_at_discount",
            "timeframe": "1H",
            "market_regime": "trending_bullish"
        }
    },
    
    # Retrieved Memories (80K tokens)
    "similar_trades": [
        # Vector DB returns most similar past trades
        {
            "trade_id": "2024-03-15-001",
            "setup": {...},
            "outcome": "win",
            "pnl": 3.2,  # R multiple
            "duration": "6 hours",
            "lessons": "Entry near OTE zone improved RR"
        },
        # ... top 20 similar trades
    ],
    
    # Performance Analysis (20K tokens)
    "performance_context": {
        "strategy_stats": {
            "bullish_ob_at_discount": {
                "win_rate": 0.64,
                "avg_rr": 2.8,
                "sample_size": 45
            }
        },
        "regime_performance": {
            "trending_bullish": {
                "win_rate": 0.58,
                "best_strategy": "breakout_retests"
            }
        }
    },
    
    # Task (3K tokens)
    "task": """
    Based on similar historical trades, provide:
    1. Expected win probability for current setup
    2. Optimal entry refinement suggestions
    3. Common failure modes to watch for
    4. Recommended adjustments based on past performance
    """
}

# Total: ~110K tokens
```

**Vector Database Structure:**
```python
class MemoryManager:
    def __init__(self):
        self.vector_db = ChromaDB()  # or Pinecone
        self.embedding_model = OpenAIEmbeddings()
    
    def store_trade(self, trade_record):
        """Store trade with semantic embedding"""
        
        # Create semantic representation
        embedding_text = f"""
        Symbol: {trade_record.symbol}
        Setup: {trade_record.setup_type}
        Confluences: {', '.join(trade_record.confluences)}
        Market Regime: {trade_record.regime}
        Timeframe: {trade_record.timeframe}
        Outcome: {trade_record.outcome}
        Lessons: {trade_record.lessons_learned}
        """
        
        embedding = self.embedding_model.embed(embedding_text)
        
        self.vector_db.add(
            id=trade_record.id,
            embedding=embedding,
            metadata=trade_record.to_dict()
        )
    
    def retrieve_similar_scenarios(self, current_setup, top_k=20):
        """Semantic search for similar past trades"""
        
        query_text = f"""
        Symbol: {current_setup.symbol}
        Setup: {current_setup.setup_type}
        Confluences: {', '.join(current_setup.confluences)}
        Market Regime: {current_setup.regime}
        """
        
        query_embedding = self.embedding_model.embed(query_text)
        
        similar_trades = self.vector_db.query(
            embedding=query_embedding,
            top_k=top_k,
            filter={"outcome": {"$ne": None}}  # Only completed trades
        )
        
        return similar_trades
```

---

# 3. Detailed Agent Workflows

## 3.1 Complete Trading Cycle (Every 3 Minutes)

```
┌─────────────────────────────────────────────────────────────┐
│                    CYCLE START (Every 3 min)                 │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│  PHASE 1: DATA COLLECTION (No LLM - 10 seconds)            │
├─────────────────────────────────────────────────────────────┤
│  Data Agent:                                                 │
│  1. Fetch latest candles (5m, 15m, 1h, 4h, 1d)             │
│  2. Get order book snapshot                                  │
│  3. Check funding rates                                      │
│  4. Validate data quality                                    │
│  5. Store in Redis cache                                     │
│                                                              │
│  Output → Message to Analysis Agent:                         │
│  {                                                           │
│    "type": "market_data_update",                            │
│    "timestamp": "2025-11-06T10:33:00Z",                     │
│    "data": {                                                 │
│      "candles": {...},                                       │
│      "order_book": {...},                                    │
│      "funding_rate": 0.0001                                  │
│    }                                                         │
│  }                                                           │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│  PHASE 2: PRE-PROCESSING (No LLM - 15 seconds)             │
├─────────────────────────────────────────────────────────────┤
│  Analysis Agent (Computational Part):                        │
│  1. Calculate technical indicators (RSI, MACD, BB, etc.)    │
│  2. Detect chart patterns (H&S, triangles, channels)        │
│  3. Identify SMC structures:                                 │
│     - Scan for Order Blocks                                  │
│     - Detect Fair Value Gaps                                 │
│     - Mark Break of Structure points                         │
│     - Map liquidity pools                                    │
│  4. Apply ICT filters:                                       │
│     - Check if in killzone (London/NY open)                  │
│     - Identify liquidity sweeps                              │
│     - Calculate OTE zones (0.62-0.79 Fib)                    │
│  5. Compress data for LLM context                            │
│                                                              │
│  Quick Filter: If no basic setup conditions → Skip to end    │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│  PHASE 3: DEEP ANALYSIS (LLM - 30-45 seconds)              │
├─────────────────────────────────────────────────────────────┤
│  Analysis Agent (LLM Component - Claude Sonnet 4.5):        │
│                                                              │
│  Context Preparation:                                        │
│  • Load 150K token context (candles + indicators + SMC)     │
│  • Include recent memory from Memory Agent                   │
│                                                              │
│  LLM Task:                                                   │
│  "Analyze the multi-timeframe data and identify:            │
│   1. Overall market structure (trend/range)                  │
│   2. Key confluence zones                                    │
│   3. Potential trade setups with detailed reasoning          │
│   4. Risk factors and invalidation levels"                   │
│                                                              │
│  LLM Output → Structured Analysis:                           │
│  {                                                           │
│    "market_structure": {                                     │
│      "1d": "bullish_trend",                                  │
│      "4h": "bullish_continuation",                           │
│      "1h": "pullback_to_demand",                             │
│      "alignment": "aligned"                                  │
│    },                                                        │
│    "key_levels": {                                           │
│      "resistance": [44500, 45000, 46200],                    │
│      "support": [43000, 42500, 41800]                        │
│    },                                                        │
│    "smc_confluences": [                                      │
│      {                                                       │
│        "type": "bullish_order_block",                        │
│        "zone": [42800, 43100],                               │
│        "strength": 0.85,                                     │
│        "timeframe": "4H"                                     │
│      },                                                      │
│      {                                                       │
│        "type": "fair_value_gap",                             │
│        "zone": [43200, 43350],                               │
│        "filled": false,                                      │
│        "probability": 0.78                                   │
│      }                                                       │
│    ],                                                        │
│    "ict_setup": {                                            │
│      "killzone": "london_open",                              │
│      "liquidity_sweep": "asian_low_taken",                   │
│      "ote_zone": [43050, 43180],                             │
│      "setup_quality": "high"                                 │
│    },                                                        │
│    "trade_opportunities": [                                  │
│      {                                                       │
│        "direction": "LONG",                                  │
│        "confluence_count": 5,                                │
│        "key_factors": [                                      │
│          "Price at 4H OB + discount zone",                   │
│          "FVG above current price (magnet)",                 │
│          "Liquidity swept below Asian low",                  │
│          "RSI bullish divergence on 1H",                     │
│          "MACD curling up on 15M"                            │
│        ],                                                    │
│        "recommended_entry_zone": [43000, 43150]              │
│      }                                                       │
│    ],                                                        │
│    "reasoning": "Multi-timeframe alignment shows..."         │
│  }                                                           │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│  PHASE 4: STRATEGY GENERATION (LLM - 20-30 seconds)        │
├─────────────────────────────────────────────────────────────┤
│  Strategy Agent (GPT-4o):                                    │
│                                                              │
│  Input: Analysis results from Phase 3                        │
│                                                              │
│  Context Preparation (100K tokens):                          │
│  • Full analysis results                                     │
│  • Current market state (price, volatility)                  │
│  • Risk parameters (balance, exposure)                       │
│  • Historical performance of similar setups                  │
│  • Structured output schema                                  │
│                                                              │
│  LLM Task:                                                   │
│  "Based on the analysis, generate a precise trade setup      │
│   with exact entry, stop-loss, and take-profit levels.       │
│   Ensure minimum 1:2 RR ratio and >0.75 confidence."        │
│                                                              │
│  Reasoning Chain (Chain-of-Thought):                         │
│  Step 1: "I see 5 confluences - 4H OB, FVG, liq sweep..."   │
│  Step 2: "MTF alignment confirmed, bias is bullish"          │
│  Step 3: "Optimal entry is at OB low: 43050"                 │
│  Step 4: "SL below Asian low: 42750 (300 pips risk)"        │
│  Step 5: "TP at FVG fill: 43650, then 44200, final 44800"   │
│  Step 6: "RR = (43650-43050)/(43050-42750) = 2.0 ✓"        │
│  Step 7: "Similar setups won 64%, confidence: 0.82"          │
│                                                              │
│  Output → Trade Setup:                                       │
│  {                                                           │
│    "symbol": "BTCUSDT",                                      │
│    "direction": "LONG",                                      │
│    "strategy_type": "DAY_TRADE",                             │
│    "entry_price": 43050,                                     │
│    "stop_loss": 42750,                                       │
│    "take_profit": [43650, 44200, 44800],                     │
│    "position_size": null,  # Calculated by Risk Agent        │
│    "confidence": 0.82,                                       │
│    "risk_reward": 2.0,                                       │
│    "expected_duration": "4-8 hours",                         │
│    "reasoning": {                                            │
│      "confluences": 5,                                       │
│      "primary_factors": [...],                               │
│      "invalidation": "Break below 42500",                    │
│      "profit_taking_plan": "33% at each TP level"            │
│    }                                                         │
│  }                                                           │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│  PHASE 5: RISK VALIDATION (Hybrid - 5-10 seconds)          │
├─────────────────────────────────────────────────────────────┤
│  Risk Agent:                                                 │
│                                                              │
│  Step 1: Deterministic Checks (No LLM - 2 seconds)         │
│  ┌────────────────────────────────────────────────────┐    │
│  │ • Check account balance: $10,000 ✓                  │    │
│  │ • Max risk per trade: 2% = $200                     │    │
│  │ • Price risk: 43050 - 42750 = 300 pips              │    │
│  │ • Calculate position size:                          │    │
│  │   $200 / 300 = 0.666 BTC                            │    │
│  │ • Current exposure: 1 position (ETHUSDT) = 1.5%     │    │
│  │ • New exposure: 1.5% + 2% = 3.5% < 6% ✓             │    │
│  │ • Daily P&L: -$80 > -$500 ✓                         │    │
│  │ • Concurrent positions: 1 < 3 ✓                     │    │
│  │ • RR ratio: 2.0 >= 2.0 ✓                            │    │
│  │                                                      │    │in
│  │ Result: All checks PASSED ✓                         │    │
│  └────────────────────────────────────────────────────┘    │
│                                                              │
│  Step 2: LLM Edge Case Analysis (GPT-4o-mini - 8 sec)      │
│  (Only if deterministic checks pass)                         │
│  ┌────────────────────────────────────────────────────┐    │
│  │ Context: Current positions, market conditions       │    │
│  │                                                      │    │
│  │ LLM Task: "Check for:                               │    │
│  │ 1. Correlation risk (both BTC and ETH long?)        │    │
│  │ 2. Recent losing streak (adjust size?)              │    │
│  │ 3. High volatility event (reduce risk?)             │    │
│  │ 4. Market regime shift warnings"                    │    │
│  │                                                      │    │
│  │ LLM Output:                                         │    │
│  │ {                                                  │    │
│  │   "correlation_risk": "Medium - BTC and ETH       │    │
│  │     both long but different setups",              │    │
│  │   "adjustment": "Reduce BTC size by 20% to 0.53", │    │
│  │   "reasoning": "Crypto correlation at 0.85 today",│    │
│  │   "approved": true                                │    │
│  │ }                                                  │    │
│  └────────────────────────────────────────────────────┘    │
│                                                              │
│  Final Decision:                                             │
│  ✓ APPROVED with adjusted position size: 0.53 BTC          │
│                                                              │
│  Output → Approved Trade:                                    │
│  {                                                           │
│    "approved": true,                                         │
│    "position_size": 0.53,  # Adjusted                       │
│    "risk_amount": 159,  # 1.59% instead of 2%               │
│    "adjustments": "Reduced due to correlation risk",         │
│    "proceed_to_execution": true                              │
│  }                                                           │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│  PHASE 6: ORDER EXECUTION (No LLM - 5-10 seconds)          │
├─────────────────────────────────────────────────────────────┤
│  Execution Agent:                                            │
│                                                              │
│  Step 1: Pre-Flight Checks                                  │
│  • Verify exchange connectivity ✓                           │
│  • Check account balance ✓                                  │
│  • Validate symbol trading status ✓                         │
│  • Check leverage settings ✓                                │
│                                                              │
│  Step 2: Place Entry Order                                  │
│  POST /api/v1/order                                          │
│  {                                                           │
│    "symbol": "BTCUSDT",                                      │
│    "side": "BUY",                                            │
│    "type": "LIMIT",                                          │
│    "quantity": 0.53,                                         │
│    "price": 43050,                                           │
│    "timeInForce": "GTC"                                      │
│  }                                                           │
│  → Order ID: 12345678                                        │
│                                                              │
│  Step 3: Place Stop-Loss Order                              │
│  POST /api/v1/order                                          │
│  {                                                           │
│    "symbol": "BTCUSDT",                                      │
│    "side": "SELL",                                           │
│    "type": "STOP_MARKET",                                    │
│    "quantity": 0.53,                                         │
│    "stopPrice": 42750,                                       │
│    "reduceOnly": true                                        │
│  }                                                           │
│  → SL Order ID: 12345679                                     │
│                                                              │
│  Step 4: Place Take-Profit Orders (3 levels)               │
│  TP1 (33%): 0.176 BTC @ 43650                               │
│  TP2 (33%): 0.176 BTC @ 44200                               │
│  TP3 (34%): 0.178 BTC @ 44800                               │
│                                                              │
│  Step 5: Monitor Order Status                               │
│  • Subscribe to order updates via WebSocket                  │
│  • Track fill status                                         │
│  • Log execution metrics                                     │
│                                                              │
│  Output → Execution Report:                                  │
│  {                                                           │
│    "status": "ORDERS_PLACED",                                │
│    "entry_order_id": "12345678",                             │
│    "sl_order_id": "12345679",                                │
│    "tp_order_ids": ["12345680", "12345681", "12345682"],     │
│    "timestamp": "2025-11-06T10:34:23Z",                      │
│    "execution_time_ms": 487                                  │
│  }                                                           │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│  PHASE 7: MEMORY STORAGE & LEARNING (LLM - 5 seconds)      │
├─────────────────────────────────────────────────────────────┤
│  Memory Agent:                                               │
│                                                              │
│  Step 1: Store Trade Record                                 │
│  • Save to PostgreSQL with full context                      │
│  • Generate semantic embedding                               │
│  • Store in vector database for future retrieval            │
│                                                              │
│  Step 2: Update Performance Metrics                         │
│  • Increment strategy counter                                │
│  • Update correlation matrix                                 │
│  • Refresh market regime classification                      │
│                                                              │
│  Step 3: Extract Lessons (LLM - GPT-4o)                     │
│  Context (30K tokens):                                       │
│  • Current trade setup + reasoning                           │
│  • Recent similar trades (last 10)                           │
│  • Current performance stats                                 │
│                                                              │
│  LLM Task:                                                   │
│  "Extract key lessons and patterns from this trade setup.    │
│   What made this a high-quality setup? What should we        │
│   watch for in similar future scenarios?"                    │
│                                                              │
│  LLM Output:                                                 │
│  {                                                           │
│    "lessons": [                                              │
│      "4H OB + FVG combination has 72% win rate",            │
│      "London killzone entries fill faster",                  │
│      "Liquidity sweeps increase confidence by 15%"           │
│    ],                                                        │
│    "patterns_identified": [                                  │
│      "asian_low_sweep_then_reversal",                        │
│      "fvg_magnet_effect"                                     │
│    ],                                                        │
│    "risk_factors": [                                         │
│      "Watch for false breakout above 44500",                 │
│      "FOMC tomorrow - volatility risk"                       │
│    ]                                                         │
│  }                                                           │
│                                                              │
│  Step 4: Alert Orchestrator                                 │
│  • Send notification to monitoring dashboard                 │
│  • Log to Telegram bot                                       │
│  • Update state machine                                      │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│  PHASE 8: POSITION MONITORING (Continuous)                  │
├─────────────────────────────────────────────────────────────┤
│  Execution Agent (Background Task):                          │
│                                                              │
│  • Monitor order fills via WebSocket                         │
│  • Track unrealized P&L                                      │
│  • Implement trailing stop logic                             │
│  • Watch for invalidation conditions                         │
│  • Adjust orders if needed                                   │
│                                                              │
│  Trailing Stop Logic (No LLM):                              │
│  IF price reaches TP1 (43650):                              │
│    → Take 33% profit                                         │
│    → Move SL to breakeven (43050)                            │
│    → Log partial exit                                        │
│                                                              │
│  IF price reaches TP2 (44200):                              │
│    → Take another 33% profit                                 │
│    → Trail SL to TP1 level (43650)                           │
│                                                              │
│  IF price reaches TP3 (44800):                              │
│    → Close remaining position                                │
│    → Calculate final P&L                                     │
│    → Send to Memory Agent for post-trade analysis            │
│                                                              │
│  Invalidation Check (Every 1 min):                          │
│  IF price < 42500:                                           │
│    → Emergency exit (setup invalidated)                      │
│    → Cancel all pending orders                               │
│    → Log reason for exit                                     │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
                    ┌─────────────────┐
                    │  CYCLE COMPLETE  │
                    │  Wait 3 minutes  │
                    │  → Restart       │
                    └─────────────────┘
```

---

## 3.2 Parallel Monitoring Workflows

### Position Management Loop (Every 30 seconds)
```
┌─────────────────────────────────────────────────────────────┐
│  CONTINUOUS MONITORING (Runs in parallel)                    │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│  FOR EACH open position:                                     │
│                                                              │
│  1. Check current price                                      │
│  2. Calculate unrealized P&L                                 │
│  3. Check if trailing stop should activate                   │
│  4. Monitor for invalidation signals                         │
│  5. Check for partial profit-taking opportunities            │
│                                                              │
│  IF significant price move (>2%):                            │
│    → Alert Analysis Agent for re-evaluation                  │
│    → Update stop-loss if needed                              │
│                                                              │
│  IF high volatility spike (ATR > 2x normal):                │
│    → Consider tightening stops                               │
│    → Alert Risk Agent                                        │
└─────────────────────────────────────────────────────────────┘
```

### Market Regime Detection (Every 15 minutes)
```
┌─────────────────────────────────────────────────────────────┐
│  REGIME DETECTION (Background task)                          │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│  1. Calculate ADX, ATR, volatility metrics                   │
│  2. Classify current regime:                                 │
│     • TRENDING_BULLISH                                       │
│     • TRENDING_BEARISH                                       │
│     • RANGING_LOW_VOL                                        │
│     • RANGING_HIGH_VOL (choppy)                              │
│                                                              │
│  3. IF regime changed:                                       │
│     → Alert all agents                                       │
│     → Adjust strategy parameters                             │
│     → Review open positions                                  │
│                                                              │
│  Example: TRENDING → RANGING                                │
│    → Tighten stops                                           │
│    → Reduce position sizes                                   │
│    → Favor mean-reversion setups                             │
└─────────────────────────────────────────────────────────────┘
```

---

# 4. Communication Protocols

## 4.1 Message Types & Priority Levels

```python
class MessageType(Enum):
    # Data flow messages (Priority 5)
    MARKET_DATA_UPDATE = "market_data_update"
    INDICATOR_CALCULATED = "indicator_calculated"
    
    # Analysis messages (Priority 7)
    ANALYSIS_COMPLETE = "analysis_complete"
    TRADE_SIGNAL = "trade_signal"
    
    # Execution messages (Priority 9)
    TRADE_APPROVED = "trade_approved"
    ORDER_PLACED = "order_placed"
    ORDER_FILLED = "order_filled"
    
    # Alerts (Priority 10 - Highest)
    EMERGENCY_EXIT = "emergency_exit"
    RISK_LIMIT_BREACH = "risk_limit_breach"
    SYSTEM_ERROR = "system_error"
    
    # System messages (Priority 3)
    HEARTBEAT = "heartbeat"
    STATUS_UPDATE = "status_update"

class MessagePriority:
    CRITICAL = 10    # Immediate action required
    HIGH = 9         # Execution-related
    MEDIUM = 7       # Analysis and signals
    NORMAL = 5       # Data updates
    LOW = 3          # Status updates
```

## 4.2 Inter-Agent Communication Patterns

### Request-Response Pattern
```python
class AgentCommunication:
    async def request_response(self, sender, receiver, request):
        """Synchronous request-response pattern"""
        
        # Sender creates request
        message = AgentMessage(
            id=generate_uuid(),
            sender=sender.name,
            receiver=receiver.name,
            message_type="request",
            payload=request,
            requires_ack=True,
            timeout=30  # seconds
        )
        
        # Send via message bus
        await self.message_bus.publish(f"{receiver.name}_inbox", message)
        
        # Wait for response
        response = await self.message_bus.wait_for_response(
            message.id, 
            timeout=30
        )
        
        return response

# Example Usage:
# Strategy Agent requests analysis from Analysis Agent
analysis = await comm.request_response(
    sender=strategy_agent,
    receiver=analysis_agent,
    request={
        "action": "analyze_current_market",
        "symbols": ["BTCUSDT"],
        "timeframes": ["5m", "15m", "1h", "4h"]
    }
)
```

### Pub-Sub Pattern
```python
class PubSubManager:
    def __init__(self):
        self.redis_client = redis.Redis()
        self.subscribers = {}
    
    async def subscribe(self, agent_name, channels):
        """Subscribe agent to specific channels"""
        
        pubsub = self.redis_client.pubsub()
        await pubsub.subscribe(*channels)
        
        self.subscribers[agent_name] = pubsub
        
        # Start listening loop
        asyncio.create_task(
            self._listen_loop(agent_name, pubsub)
        )
    
    async def publish(self, channel, message):
        """Publish message to channel"""
        
        await self.redis_client.publish(
            channel,
            json.dumps(message.to_dict())
        )
    
    async def _listen_loop(self, agent_name, pubsub):
        """Listen for messages on subscribed channels"""
        
        async for message in pubsub.listen():
            if message['type'] == 'message':
                data = json.loads(message['data'])
                
                # Route to agent's handler
                await self.route_to_agent(agent_name, data)

# Example: Data Agent publishes market updates
await pubsub.publish(
    channel='market_data',
    message=AgentMessage(
        type='market_data_update',
        payload={'btc_price': 43250, ...}
    )
)

# Multiple agents subscribe to market data
await pubsub.subscribe('analysis_agent', ['market_data'])
await pubsub.subscribe('risk_agent', ['market_data'])
```

### Event-Driven Orchestration
```python
class EventOrchestrator:
    def __init__(self):
        self.event_handlers = {}
        self.event_queue = asyncio.Queue()
    
    def register_handler(self, event_type, handler):
        """Register handler for specific event type"""
        if event_type not in self.event_handlers:
            self.event_handlers[event_type] = []
        self.event_handlers[event_type].append(handler)
    
    async def emit_event(self, event):
        """Emit event to all registered handlers"""
        await self.event_queue.put(event)
    
    async def process_events(self):
        """Process events from queue"""
        while True:
            event = await self.event_queue.get()
            
            handlers = self.event_handlers.get(event.type, [])
            
            # Execute handlers in parallel
            tasks = [handler(event) for handler in handlers]
            await asyncio.gather(*tasks)
            
            self.event_queue.task_done()

# Example: Order filled event triggers multiple actions
orchestrator.register_handler(
    'order_filled',
    execution_agent.update_position_tracker
)
orchestrator.register_handler(
    'order_filled',
    memory_agent.log_execution
)
orchestrator.register_handler(
    'order_filled',
    risk_agent.update_exposure
)

# When order fills, all handlers execute
await orchestrator.emit_event(
    Event(type='order_filled', data={...})
)
```

---

## 4.3 State Management

### Global Trading State
```python
class TradingState:
    """Shared state across all agents"""
    
    def __init__(self):
        self.redis = redis.Redis()
        
    # Current market state
    market_state = {
        'current_prices': {},      # Latest prices per symbol
        'regime': 'TRENDING',      # Current market regime
        'volatility': 'MODERATE',  # Volatility level
        'last_update': None        # Last data update timestamp
    }
    
    # Portfolio state
    portfolio_state = {
        'balance': 10000,
        'equity': 10000,
        'unrealized_pnl': 0,
        'daily_pnl': 0,
        'positions': [],
        'pending_orders': []
    }
    
    # Risk state
    risk_state = {
        'portfolio_heat': 0.0,      # Current exposure %
        'daily_loss': 0,            # Today's realized loss
        'consecutive_losses': 0,     # Streak tracking
        'circuit_breaker': False    # Emergency stop
    }
    
    # Agent state
    agent_states = {
        'data_agent': 'ACTIVE',
        'analysis_agent': 'PROCESSING',
        'strategy_agent': 'IDLE',
        'risk_agent': 'ACTIVE',
        'execution_agent': 'MONITORING',
        'memory_agent': 'ACTIVE'
    }
    
    async def get_state(self, key):
        """Get state value from Redis"""
        value = await self.redis.get(f"state:{key}")
        return json.loads(value) if value else None
    
    async def set_state(self, key, value):
        """Set state value in Redis"""
        await self.redis.set(
            f"state:{key}",
            json.dumps(value)
        )
    
    async def update_position(self, position_update):
        """Atomic position update"""
        async with self.redis.pipeline() as pipe:
            current_positions = await self.get_state('positions')
            current_positions.append(position_update)
            await self.set_state('positions', current_positions)
            
            # Update portfolio metrics
            equity = await self.calculate_equity(current_positions)
            await self.set_state('equity', equity)
```

---

# 5. Implementation Guide

## 5.1 LangGraph Implementation

```python
from langgraph.graph import StateGraph, END
from typing import TypedDict, Annotated
import operator

# Define the shared state
class TradingGraphState(TypedDict):
    # Market data
    candles: dict
    indicators: dict
    order_book: dict
    
    # Analysis results
    analysis: dict
    trade_signals: list
    
    # Strategy outputs
    trade_setup: dict
    
    # Risk validation
    risk_approved: bool
    adjusted_size: float
    
    # Execution results
    orders_placed: dict
    
    # Metadata
    cycle_start: str
    messages: Annotated[list, operator.add]

# Create the graph
workflow = StateGraph(TradingGraphState)

# Define agent nodes
def data_collection_node(state: TradingGraphState):
    """Data Agent - Fetch live market data"""
    
    print(f"[{datetime.now()}] Data Agent: Fetching market data...")
    
    # Fetch data from Binance
    candles = fetch_multi_timeframe_data(['5m', '15m', '1h', '4h', '1d'])
    order_book = fetch_order_book('BTCUSDT')
    
    # Calculate indicators (no LLM)
    indicators = calculate_all_indicators(candles)
    
    return {
        "candles": candles,
        "indicators": indicators,
        "order_book": order_book,
        "messages": ["Data collection complete"]
    }

def analysis_node(state: TradingGraphState):
    """Analysis Agent - LLM-powered deep analysis"""
    
    print(f"[{datetime.now()}] Analysis Agent: Running SMC/ICT analysis...")
    
    # Prepare context for LLM
    context = prepare_analysis_context(
        candles=state['candles'],
        indicators=state['indicators'],
        order_book=state['order_book']
    )
    
    # Call Claude Sonnet for analysis
    analysis_result = llm_analyze_market(context)
    
    return {
        "analysis": analysis_result,
        "trade_signals": analysis_result.get('trade_opportunities', []),
        "messages": [f"Analysis complete: {len(analysis_result['trade_opportunities'])} signals found"]
    }

def should_generate_strategy(state: TradingGraphState):
    """Router: Check if we should generate strategy"""
    
    if len(state['trade_signals']) > 0:
        return "generate_strategy"
    else:
        return "skip_to_end"

def strategy_node(state: TradingGraphState):
    """Strategy Agent - Generate trade setup"""
    
    print(f"[{datetime.now()}] Strategy Agent: Generating trade setup...")
    
    # Call GPT-4o for strategy generation
    trade_setup = llm_generate_trade_setup(
        analysis=state['analysis'],
        signals=state['trade_signals']
    )
    
    return {
        "trade_setup": trade_setup,
        "messages": [f"Strategy generated: {trade_setup['direction']} @ {trade_setup['entry_price']}"]
    }

def risk_validation_node(state: TradingGraphState):
    """Risk Agent - Validate and adjust"""
    
    print(f"[{datetime.now()}] Risk Agent: Validating trade...")
    
    # Deterministic checks
    initial_check = deterministic_risk_check(
        trade=state['trade_setup'],
        portfolio=get_portfolio_state()
    )
    
    if not initial_check['passed']:
        return {
            "risk_approved": False,
            "messages": [f"Trade rejected: {initial_check['reason']}"]
        }
    
    # LLM for edge cases
    if initial_check['requires_llm_review']:
        llm_decision = llm_risk_validation(
            trade=state['trade_setup'],
            portfolio=get_portfolio_state()
        )
        
        return {
            "risk_approved": llm_decision['approved'],
            "adjusted_size": llm_decision['adjusted_size'],
            "messages": [f"Risk check complete: {llm_decision['reasoning']}"]
        }
    
    return {
        "risk_approved": True,
        "adjusted_size": initial_check['position_size'],
        "messages": ["Trade approved - proceeding to execution"]
    }

def should_execute(state: TradingGraphState):
    """Router: Check if trade is approved"""
    return "execute" if state['risk_approved'] else "end"

def execution_node(state: TradingGraphState):
    """Execution Agent - Place orders"""
    
    print(f"[{datetime.now()}] Execution Agent: Placing orders...")
    
    # Place orders on exchange
    orders = place_trade_orders(
        setup=state['trade_setup'],
        size=state['adjusted_size']
    )
    
    return {
        "orders_placed": orders,
        "messages": [f"Orders placed successfully: {orders['entry_order_id']}"]
    }

def memory_node(state: TradingGraphState):
    """Memory Agent - Store and learn"""
    
    print(f"[{datetime.now()}] Memory Agent: Storing trade record...")
    
    # Store in database
    store_trade_record(state)
    
    # Generate embeddings and store in vector DB
    store_semantic_memory(state)
    
    # Extract lessons via LLM
    lessons = llm_extract_lessons(state)
    
    return {
        "messages": [f"Trade logged. Lessons: {len(lessons)}"]
    }

# Build the graph
workflow.add_node("data_collection", data_collection_node)
workflow.add_node("analysis", analysis_node)
workflow.add_node("strategy", strategy_node)
workflow.add_node("risk_validation", risk_validation_node)
workflow.add_node("execution", execution_node)
workflow.add_node("memory", memory_node)

# Define edges
workflow.set_entry_point("data_collection")
workflow.add_edge("data_collection", "analysis")

# Conditional routing after analysis
workflow.add_conditional_edges(
    "analysis",
    should_generate_strategy,
    {
        "generate_strategy": "strategy",
        "skip_to_end": END
    }
)

workflow.add_edge("strategy", "risk_validation")

# Conditional routing after risk validation
workflow.add_conditional_edges(
    "risk_validation",
    should_execute,
    {
        "execute": "execution",
        "end": END
    }
)

workflow.add_edge("execution", "memory")
workflow.add_edge("memory", END)

# Compile the graph
app = workflow.compile()

# Run the workflow
async def run_trading_cycle():
    """Execute one complete trading cycle"""
    
    initial_state = {
        "cycle_start": datetime.now().isoformat(),
        "messages": []
    }
    
    result = await app.ainvoke(initial_state)
    
    print("\n=== Cycle Complete ===")
    for msg in result['messages']:
        print(f"  • {msg}")
    
    return result

# Main loop - runs every 3 minutes
async def main():
    while True:
        try:
            await run_trading_cycle()
        except Exception as e:
            print(f"Error in cycle: {e}")
            # Log error and continue
        
        # Wait 3 minutes before next cycle
        await asyncio.sleep(180)

if __name__ == "__main__":
    asyncio.run(main())
```

---

## 5.2 LLM Context Optimization Techniques

### Technique 1: Dynamic Context Pruning
```python
class ContextOptimizer:
    def __init__(self, max_tokens=150000):
        self.max_tokens = max_tokens
    
    def optimize_context(self, full_context, priority_map):
        """Intelligently prune context to fit token limit"""
        
        total_tokens = self.estimate_tokens(full_context)
        
        if total_tokens <= self.max_tokens:
            return full_context
        
        # Priority-based pruning
        optimized = {}
        remaining_tokens = self.max_tokens
        
        # Sort by priority
        sorted_sections = sorted(
            full_context.items(),
            key=lambda x: priority_map.get(x[0], 0),
            reverse=True
        )
        
        for key, value in sorted_sections:
            section_tokens = self.estimate_tokens({key: value})
            
            if section_tokens <= remaining_tokens:
                optimized[key] = value
                remaining_tokens -= section_tokens
            else:
                # Compress or truncate
                compressed = self.compress_section(
                    value, 
                    target_tokens=remaining_tokens
                )
                optimized[key] = compressed
                break
        
        return optimized
    
    def compress_section(self, data, target_tokens):
        """Compress data to fit target token count"""
        
        if isinstance(data, list):
            # For lists (e.g., candles), take most recent items
            tokens_per_item = self.estimate_tokens(data[0]) if data else 0
            max_items = target_tokens // tokens_per_item
            return data[-max_items:]
        
        elif isinstance(data, dict):
            # For dicts, keep essential keys only
            essential_keys = ['current', 'latest', 'important']
            return {
                k: v for k, v in data.items() 
                if any(ek in k.lower() for ek in essential_keys)
            }
        
        return data

# Usage
optimizer = ContextOptimizer(max_tokens=150000)

priority_map = {
    'current_data': 10,      # Highest priority
    'indicators': 9,
    'smc_context': 9,
    'ict_context': 8,
    'historical_context': 6,
    'performance_stats': 5
}

optimized_context = optimizer.optimize_context(
    full_context,
    priority_map
)
```

### Technique 2: Incremental Context Updates
```python
class IncrementalContextManager:
    """Maintain context between cycles, only update changed parts"""
    
    def __init__(self):
        self.previous_context = {}
        self.context_cache = {}
    
    def prepare_context(self, new_data):
        """Only include changed or new information"""
        
        context = {
            "system_prompt": self.get_cached("system_prompt"),
            "updated_data": {},
            "unchanged_references": []
        }
        
        for key, value in new_data.items():
            if self.has_changed(key, value):
                context["updated_data"][key] = value
                self.context_cache[key] = value
            else:
                # Just reference: "Use cached {key} from previous analysis"
                context["unchanged_references"].append(key)
        
        return context
    
    def has_changed(self, key, value):
        """Check if data has meaningfully changed"""
        
        if key not in self.previous_context:
            return True
        
        # For candles, check if new candles added
        if key == 'candles':
            prev_last_time = self.previous_context[key][-1]['timestamp']
            new_last_time = value[-1]['timestamp']
            return new_last_time > prev_last_time
        
        # For indicators, check if values changed significantly
        if key == 'indicators':
            prev_rsi = self.previous_context[key]['rsi'][-1]
            new_rsi = value['rsi'][-1]
            return abs(prev_rsi - new_rsi) > 5  # 5 point change threshold
        
        return True  # Default to changed

# Usage
context_mgr = IncrementalContextManager()

# First cycle: Full context
context = context_mgr.prepare_context(full_market_data)

# Subsequent cycles: Only deltas
context = context_mgr.prepare_context(new_market_data)
# Result: Much smaller context, faster LLM calls
```

### Technique 3: Summarization Layer
```python
class ContextSummarizer:
    """Summarize historical data using LLM before main analysis"""
    
    async def summarize_historical_context(self, trades, max_tokens=10000):
        """Use cheap LLM to summarize past trades"""
        
        prompt = f"""
        Summarize the following {len(trades)} recent trades into key insights.
        Focus on: win patterns, loss patterns, market regimes, lessons learned.
        Maximum {max_tokens} tokens.
        
        Trades:
        {json.dumps(trades, indent=2)}
        """
        
        summary = await self.llm_client.complete(
            model="gpt-4o-mini",  # Cheaper model for summaries
            prompt=prompt,
            max_tokens=max_tokens
        )
        
        return summary
    
    async def prepare_analyzed_context(self, full_context):
        """Pre-process context with summarization"""
        
        # Summarize historical trades
        if 'historical_trades' in full_context:
            full_context['historical_summary'] = \
                await self.summarize_historical_context(
                    full_context['historical_trades']
                )
            del full_context['historical_trades']  # Remove raw data
        
        # Summarize indicator data
        if 'indicators' in full_context:
            full_context['indicator_summary'] = \
                self.summarize_indicators(full_context['indicators'])
        
        return full_context

# Usage
summarizer = ContextSummarizer()
optimized_context = await summarizer.prepare_analyzed_context(full_context)
# Result: 80K tokens instead of 150K, same insights
```

---

## 5.3 Cost Optimization Strategies

### Token Usage Tracking
```python
class CostTracker:
    def __init__(self):
        self.costs = {
            'claude-sonnet-4.5': {'input': 0.003, 'output': 0.015},  # per 1K tokens
            'gpt-4o': {'input': 0.0025, 'output': 0.01},
            'gpt-4o-mini': {'input': 0.00015, 'output': 0.0006}
        }
        
        self.daily_usage = {
            'claude-sonnet-4.5': {'input_tokens': 0, 'output_tokens': 0},
            'gpt-4o': {'input_tokens': 0, 'output_tokens': 0},
            'gpt-4o-mini': {'input_tokens': 0, 'output_tokens': 0}
        }
    
    def track_call(self, model, input_tokens, output_tokens):
        """Track LLM API call costs"""
        
        self.daily_usage[model]['input_tokens'] += input_tokens
        self.daily_usage[model]['output_tokens'] += output_tokens
        
        cost = (
            (input_tokens / 1000) * self.costs[model]['input'] +
            (output_tokens / 1000) * self.costs[model]['output']
        )
        
        return cost
    
    def get_daily_cost(self):
        """Calculate total daily cost"""
        
        total = 0
        for model, usage in self.daily_usage.items():
            total += (
                (usage['input_tokens'] / 1000) * self.costs[model]['input'] +
                (usage['output_tokens'] / 1000) * self.costs[model]['output']
            )
        
        return total
    
    def should_throttle(self, max_daily_budget=100):
        """Check if we should reduce LLM usage"""
        return self.get_daily_cost() > max_daily_budget * 0.8

# Usage
cost_tracker = CostTracker()

# After each LLM call
cost = cost_tracker.track_call(
    model='claude-sonnet-4.5',
    input_tokens=150000,
    output_tokens=2000
)

print(f"Call cost: ${cost:.4f}")
print(f"Daily total: ${cost_tracker.get_daily_cost():.2f}")

# Expected daily costs at 3-min cycles:
# - 480 cycles/day (24 hours)
# - Analysis Agent: 150K input + 2K output per cycle
# - Strategy Agent: 100K input + 1K output per cycle
# - Risk Agent (LLM): 20K input + 500 output per cycle (only when needed)
# - Memory Agent: 30K input + 500 output per cycle
#
# Estimated daily cost:
# Analysis: 480 * ((150*0.003) + (2*0.015)) = $230/day
# Strategy: 480 * ((100*0.0025) + (1*0.01)) = $125/day
# Risk: 100 * ((20*0.00015) + (0.5*0.0006)) = $0.33/day
# Memory: 480 * ((30*0.00015) + (0.5*0.0006)) = $2.30/day
#
# Total: ~$357/day (can be reduced with optimizations)
```

### Smart Caching
```python
class IntelligentCache:
    """Cache LLM responses for similar market conditions"""
    
    def __init__(self):
        self.redis = redis.Redis()
        self.cache_ttl = 1800  # 30 minutes
    
    def generate_cache_key(self, context):
        """Create cache key from context fingerprint"""
        
        # Extract key features
        fingerprint = {
            'symbol': context['symbol'],
            'price_range': self.discretize_price(context['current_price']),
            'regime': context['market_regime'],
            'primary_pattern': context.get('primary_pattern'),
            'timeframe': context['timeframe']
        }
        
        # Hash the fingerprint
        key = hashlib.md5(
            json.dumps(fingerprint, sort_keys=True).encode()
        ).hexdigest()
        
        return f"analysis_cache:{key}"
    
    def discretize_price(self, price, bucket_size=100):
        """Group similar prices into buckets"""
        return (price // bucket_size) * bucket_size
    
    async def get_cached_analysis(self, context):
        """Try to get cached analysis"""
        
        cache_key = self.generate_cache_key(context)
        cached = await self.redis.get(cache_key)
        
        if cached:
            print("Cache HIT - Saved LLM call!")
            return json.loads(cached)
        
        return None
    
    async def cache_analysis(self, context, analysis):
        """Cache analysis result"""
        
        cache_key = self.generate_cache_key(context)
        await self.redis.setex(
            cache_key,
            self.cache_ttl,
            json.dumps(analysis)
        )

# Usage
cache = IntelligentCache()

# Before calling LLM
cached_result = await cache.get_cached_analysis(context)
if cached_result:
    return cached_result

# Call LLM
result = await llm_analyze_market(context)

# Cache the result
await cache.cache_analysis(context, result)

# Expected cache hit rate: 30-40% (saves ~$120/day)
```

---

## 5.4 Complete Agent Implementation Example

```python
# agent_framework.py

import asyncio
from typing import Dict, Any
from datetime import datetime
import json

class BaseAgent:
    """Base class for all agents"""
    
    def __init__(self, name: str, llm_client=None):
        self.name = name
        self.llm_client = llm_client
        self.state = "IDLE"
        self.message_queue = asyncio.Queue()
        self.running = False
    
    async def start(self):
        """Start agent's message processing loop"""
        self.running = True
        asyncio.create_task(self._process_messages())
        print(f"[{self.name}] Started")
    
    async def stop(self):
        """Stop agent"""
        self.running = False
        print(f"[{self.name}] Stopped")
    
    async def _process_messages(self):
        """Process incoming messages"""
        while self.running:
            try:
                message = await asyncio.wait_for(
                    self.message_queue.get(),
                    timeout=1.0
                )
                await self.handle_message(message)
            except asyncio.TimeoutError:
                continue
            except Exception as e:
                print(f"[{self.name}] Error: {e}")
    
    async def handle_message(self, message: Dict[str, Any]):
        """Override in subclass"""
        raise NotImplementedError
    
    async def send_message(self, receiver: str, payload: Dict[str, Any]):
        """Send message to another agent"""
        message = {
            'sender': self.name,
            'receiver': receiver,
            'timestamp': datetime.now().isoformat(),
            'payload': payload
        }
        
        # Publish to message bus
        await message_bus.publish(f"{receiver}_inbox", message)

class MarketAnalysisAgent(BaseAgent):
    """Agent responsible for market analysis using LLM"""
    
    def __init__(self, llm_client):
        super().__init__("analysis_agent", llm_client)
        self.context_optimizer = ContextOptimizer()
        self.cache = IntelligentCache()
    
    async def handle_message(self, message):
        """Handle incoming messages"""
        
        if message['payload']['action'] == 'analyze_market':
            await self.analyze_market(message['payload']['data'])
    
    async def analyze_market(self, market_data):
        """Main analysis function"""
        
        self.state = "ANALYZING"
        
        try:
            # Check cache first
            cached = await self.cache.get_cached_analysis(market_data)
            if cached:
                await self.send_message(
                    'strategy_agent',
                    {'analysis': cached}
                )
                return
            
            # Prepare optimized context
            context = self.prepare_context(market_data)
            
            # Call LLM
            analysis = await self.llm_analyze(context)
            
            # Cache result
            await self.cache.cache_analysis(market_data, analysis)
            
            # Send to strategy agent
            await self.send_message(
                'strategy_agent',
                {'analysis': analysis}
            )
            
        finally:
            self.state = "IDLE"
    
    def prepare_context(self, market_data):
        """Prepare LLM context"""
        
        context = {
            "role": """You are an expert crypto technical analyst specializing in 
            Smart Money Concepts (SMC) and Inner Circle Trader (ICT) methodology.""",
            
            "current_data": {
                "candles_5m": market_data['candles']['5m'][-500:],
                "candles_15m": market_data['candles']['15m'][-400:],
                "candles_1h": market_data['candles']['1h'][-300:],
                "candles_4h": market_data['candles']['4h'][-200:],
                "candles_1d": market_data['candles']['1d'][-100:],
            },
            
            "indicators": self.compress_indicators(market_data['indicators']),
            
            "smc_data": market_data['smc_structures'],
            
            "ict_data": market_data['ict_setups'],
            
            "task": """
            Analyze the multi-timeframe data and provide:
            
            1. Market Structure Analysis:
               - Overall trend direction per timeframe
               - Key support/resistance levels
               - Market phase (accumulation/distribution/trend)
            
            2. SMC Analysis:
               - Order Blocks (bullish/bearish)
               - Fair Value Gaps
               - Break of Structure / Change of Character
               - Liquidity pools
            
            3. ICT Analysis:
               - Current killzone status
               - Liquidity sweeps
               - Optimal Trade Entry zones
               - Power of 3 setup
            
            4. Trade Opportunities:
               - List potential setups with confluences
               - Specify entry zones, invalidation levels
               - Rate confidence for each setup (0-1)
            
            Output as structured JSON.
            """
        }
        
        # Optimize to fit token limit
        return self.context_optimizer.optimize_context(context, {
            'current_data': 10,
            'indicators': 9,
            'smc_data': 9,
            'ict_data': 8,
            'task': 10
        })
    
    async def llm_analyze(self, context):
        """Call LLM for analysis"""
        
        response = await self.llm_client.create_completion(
            model="claude-sonnet-4.5",
            messages=[
                {"role": "system", "content": context['role']},
                {"role": "user", "content": json.dumps({
                    "data": context['current_data'],
                    "indicators": context['indicators'],
                    "smc": context['smc_data'],
                    "ict": context['ict_data'],
                    "task": context['task']
                }, indent=2)}
            ],
            max_tokens=4000
        )
        
        # Parse JSON response
        analysis = json.loads(response['content'])
        
        return analysis

# Main orchestrator
class TradingOrchestrator:
    def __init__(self):
        self.agents = {}
        self.state_manager = TradingState()
    
    async def initialize(self):
        """Initialize all agents"""
        
        # Create LLM clients
        claude_client = AnthropicClient(api_key=os.getenv('ANTHROPIC_API_KEY'))
        openai_client = OpenAIClient(api_key=os.getenv('OPENAI_API_KEY'))
        
        # Initialize agents
        self.agents['data'] = DataCollectionAgent()
        self.agents['analysis'] = MarketAnalysisAgent(claude_client)
        self.agents['strategy'] = StrategyGenerationAgent(openai_client)
        self.agents['risk'] = RiskManagementAgent(openai_client)
        self.agents['execution'] = ExecutionAgent()
        self.agents['memory'] = MemoryAgent(openai_client)
        
        # Start all agents
        for agent in self.agents.values():
            await agent.start()
    
    async def run_cycle(self):
        """Run one complete trading cycle"""
        
        print("\n" + "="*60)
        print(f"Starting cycle at {datetime.now()}")
        print("="*60)
        
        # Trigger data collection
        await self.agents['data'].send_message(
            'data_agent',
            {'action': 'fetch_data', 'symbols': ['BTCUSDT']}
        )
        
        # The rest is handled by agent message passing
        
        # Wait for cycle to complete (timeout after 2 minutes)
        await asyncio.sleep(120)
    
    async def run_forever(self):
        """Main loop - runs every 3 minutes"""
        
        await self.initialize()
        
        while True:
            try:
                await self.run_cycle()
                
                # Wait 3 minutes before next cycle
                await asyncio.sleep(180)
                
            except KeyboardInterrupt:
                print("\nShutting down gracefully...")
                break
            except Exception as e:
                print(f"Error in cycle: {e}")
                # Log error and continue
        
        # Cleanup
        for agent in self.agents.values():
            await agent.stop()

# Entry point
if __name__ == "__main__":
    orchestrator = TradingOrchestrator()
    asyncio.run(orchestrator.run_forever())
```

---

## Summary: Multi-Agent System Design

### LLM Usage Breakdown

| Agent | LLM Required? | Model | Avg Tokens/Call | Cost/Call | Calls/Day |
|-------|--------------|-------|-----------------|-----------|-----------|
| Data Collection | ❌ No | - | 0 | $0 | 0 |
| Market Analysis | ✅ Yes | Claude Sonnet 4.5 | 150K in + 2K out | $0.48 | 480 |
| Strategy Generation | ✅ Yes | GPT-4o | 100K in + 1K out | $0.26 | 480 |
| Risk Management | ⚠️ Selective | GPT-4o-mini | 20K in + 500 out | $0.003 | 100 |
| Execution | ❌ No | - | 0 | $0 | 0 |
| Memory | ✅ Yes | GPT-4o | 30K in + 500 out | $0.08 | 480 |

**Daily Cost Estimate:** ~$357 (before optimizations), ~$200-250 (with caching & optimization)

### Key Architectural Decisions

1. **Event-Driven Architecture** - Agents communicate via message bus, enabling async processing
2. **Hybrid Approach** - Use deterministic algorithms where possible, LLM for complex reasoning
3. **Context Optimization** - Aggressive pruning, caching, and incremental updates
4. **Fault Tolerance** - Each agent can retry, fallback strategies, circuit breakers
5. **Observability** - Comprehensive logging, metrics, trade journals

This architecture ensures your AI trading system behaves like a professional trader while remaining cost-effective and scalable!