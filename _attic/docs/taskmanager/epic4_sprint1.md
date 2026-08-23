# 🎫 EPIC 4: Strategy Generation Agent

**Duration:** Weeks 7-8  
**Priority:** P0 (Critical)  
**Status:** 🔴 NOT STARTED  
**Dependencies:** EPIC 3 (Market Analysis Agent) ✅ Complete

---

## 📋 Epic Overview

The Strategy Generation Agent transforms market analysis into actionable trade setups. It takes the comprehensive analysis from the Market Analysis Agent and generates precise entry/exit plans with proper risk-reward ratios, position sizing recommendations, and detailed execution logic.

### Key Responsibilities
- Receive analysis from Market Analysis Agent
- Generate structured trade setups (entry, SL, TP levels)
- Calculate risk-reward ratios (minimum 1:2)
- Determine position sizing recommendations
- Assign confidence scores based on confluence
- Provide clear invalidation conditions
- Generate multiple TP levels for scaling out

### Success Metrics
- Trade setup generation time: <10 seconds
- Minimum RR ratio: 2.0
- Setup confidence correlation with win rate: >0.7
- Valid setups per analysis: 1-3
- LLM context optimization: <100K tokens
- Integration test pass rate: 100%

---

## 🎯 Sprint Breakdown

### Sprint 4.1: Core Strategy Logic (Week 7, Days 1-3)
**Goal:** Build the computational foundation for strategy generation

**Tickets:**
1. ✅ Trade Setup Builder (10 SP)
2. ✅ Risk-Reward Calculator (8 SP)
3. ✅ Position Sizing Engine (8 SP)
4. ✅ Confluence Scorer (6 SP)

### Sprint 4.2: LLM Integration & Agent (Week 7-8, Days 4-10)
**Goal:** Integrate LLM reasoning and complete the agent

**Tickets:**
5. ⏳ LLM Strategy Prompt System (8 SP)
6. ⏳ Strategy Generation Agent Core (12 SP)
7. ⏳ Multi-Strategy Optimizer (8 SP)
8. ⏳ Integration & Validation Tests (8 SP)

**Total Story Points:** 68 SP (~2 developer-weeks)

---

# 🎫 Ticket #4.1.1: Trade Setup Builder
**Story Points:** 10  
**Priority:** P0  
**Status:** 🔴 NOT STARTED  
**Assignee:** Backend Developer  
**Sprint:** Week 7, Days 1-2

## 📋 Description

Implement the core trade setup builder that constructs structured trade plans from market analysis. This module determines entry zones, stop-loss levels, and take-profit targets based on SMC/ICT principles.

## 🎯 Acceptance Criteria

- [ ] **Entry Zone Calculation**
  - Calculate optimal entry zone from Order Blocks
  - Consider FVG levels as entry magnets
  - Use OTE zones (0.62-0.79 Fib) for pullback entries
  - Support both limit and market entry strategies
  
- [ ] **Stop-Loss Placement**
  - Place SL below/above invalidation levels
  - Consider ATR for volatility-adjusted stops
  - Respect SMC structure (below OB, beyond liquidity)
  - Maximum 2% account risk per trade
  
- [ ] **Take-Profit Levels**
  - Generate 3-level TP strategy (33% each)
  - TP1: 1:1 or 1:1.5 RR (quick profit)
  - TP2: 1:2 to 1:3 RR (main target)
  - TP3: 1:4+ RR (runner)
  - Use supply/demand zones as TP targets
  - Consider FVG fills as profit targets

- [ ] **Trade Metadata**
  - Strategy type classification (SCALP/DAY_TRADE/SWING)
  - Expected holding time estimation
  - Confluence factor list
  - Invalidation conditions
  - Partial exit strategy

- [ ] **Quality & Performance**
  - Unit tests >80% coverage
  - Setup generation <2 seconds
  - Valid setup validation
  - Edge case handling

## 📦 Deliverables

### File: `src/strategy/trade_setup_builder.py`

```python
"""
Trade Setup Builder
Constructs structured trade setups from market analysis
"""
import numpy as np
from typing import Dict, Any, List, Optional, Tuple
from dataclasses import dataclass, asdict
from datetime import datetime, timedelta
from loguru import logger

@dataclass
class TradeSetup:
    """Structured trade setup"""
    # Identification
    setup_id: str
    symbol: str
    timestamp: str
    
    # Direction & Type
    direction: str  # 'LONG' or 'SHORT'
    strategy_type: str  # 'SCALP', 'DAY_TRADE', 'SWING'
    
    # Entry
    entry_type: str  # 'LIMIT', 'MARKET', 'STOP_LIMIT'
    entry_price: float
    entry_zone_low: float
    entry_zone_high: float
    
    # Risk Management
    stop_loss: float
    stop_loss_type: str  # 'HARD', 'TRAILING'
    risk_amount: float  # Dollar amount at risk
    risk_percentage: float  # % of account
    
    # Profit Targets
    take_profit_levels: List[Dict[str, float]]  # [{'price': X, 'size': 0.33}, ...]
    final_target: float
    
    # Metrics
    risk_reward_ratio: float
    expected_duration_hours: float
    confidence_score: float  # 0-1
    
    # Context
    confluences: List[str]
    key_levels: Dict[str, List[float]]
    invalidation_conditions: List[str]
    setup_reasoning: str
    
    # Position Sizing (to be filled by sizing engine)
    recommended_position_size: Optional[float] = None
    max_position_size: Optional[float] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return asdict(self)
    
    def is_valid(self) -> bool:
        """Validate setup integrity"""
        # Check RR ratio
        if self.risk_reward_ratio < 2.0:
            return False
        
        # Check entry vs SL
        if self.direction == 'LONG':
            if self.entry_price <= self.stop_loss:
                return False
        else:
            if self.entry_price >= self.stop_loss:
                return False
        
        # Check TPs are in correct direction
        for tp in self.take_profit_levels:
            if self.direction == 'LONG':
                if tp['price'] <= self.entry_price:
                    return False
            else:
                if tp['price'] >= self.entry_price:
                    return False
        
        # Check confidence threshold
        if self.confidence_score < 0.65:
            return False
        
        return True


class TradeSetupBuilder:
    """
    Builds structured trade setups from market analysis
    
    Core Logic:
    1. Identify optimal entry based on SMC/ICT confluences
    2. Calculate stop-loss at invalidation level
    3. Generate multi-level take-profits
    4. Calculate risk-reward metrics
    5. Assign confidence score
    """
    
    def __init__(self):
        self.setup_counter = 0
        
    def build_setup(
        self,
        symbol: str,
        analysis: Dict[str, Any],
        current_price: float,
        atr: float
    ) -> Optional[TradeSetup]:
        """
        Build complete trade setup from analysis
        
        Args:
            symbol: Trading symbol
            analysis: Complete analysis from Market Analysis Agent
            current_price: Current market price
            atr: Current ATR for volatility context
            
        Returns:
            TradeSetup object or None if no valid setup
        """
        try:
            logger.info(f"Building trade setup for {symbol}...")
            
            # Extract relevant data
            opportunities = analysis.get('trade_opportunities', [])
            smc_data = analysis.get('smc_analysis', {})
            ict_data = analysis.get('ict_analysis', {})
            market_structure = analysis.get('market_structure', {})
            
            if not opportunities:
                logger.info("No trade opportunities found in analysis")
                return None
            
            # Get best opportunity
            best_opportunity = self._select_best_opportunity(opportunities)
            
            if not best_opportunity:
                return None
            
            # Determine direction
            direction = best_opportunity['direction']
            
            # Calculate entry zone
            entry_zone = self._calculate_entry_zone(
                direction=direction,
                opportunity=best_opportunity,
                smc_data=smc_data,
                ict_data=ict_data,
                current_price=current_price
            )
            
            # Calculate stop-loss
            stop_loss = self._calculate_stop_loss(
                direction=direction,
                entry_zone=entry_zone,
                smc_data=smc_data,
                ict_data=ict_data,
                atr=atr,
                invalidation_level=best_opportunity.get('invalidation_level')
            )
            
            # Generate take-profit levels
            tp_levels = self._generate_take_profits(
                direction=direction,
                entry_price=entry_zone['optimal_entry'],
                stop_loss=stop_loss,
                smc_data=smc_data,
                analysis=analysis
            )
            
            # Calculate risk-reward
            risk_reward = self._calculate_risk_reward(
                entry_price=entry_zone['optimal_entry'],
                stop_loss=stop_loss,
                take_profits=tp_levels
            )
            
            # Determine strategy type
            strategy_type = self._classify_strategy_type(
                ict_data=ict_data,
                market_structure=market_structure,
                tp_distance=tp_levels[-1]['price'] - entry_zone['optimal_entry']
                if direction == 'LONG' else entry_zone['optimal_entry'] - tp_levels[-1]['price']
            )
            
            # Build setup
            setup = TradeSetup(
                setup_id=self._generate_setup_id(symbol),
                symbol=symbol,
                timestamp=datetime.utcnow().isoformat(),
                direction=direction,
                strategy_type=strategy_type,
                entry_type='LIMIT',  # Default to limit orders
                entry_price=entry_zone['optimal_entry'],
                entry_zone_low=entry_zone['zone_low'],
                entry_zone_high=entry_zone['zone_high'],
                stop_loss=stop_loss,
                stop_loss_type='HARD',
                risk_amount=0.0,  # Will be calculated by position sizing
                risk_percentage=2.0,  # Default 2%
                take_profit_levels=tp_levels,
                final_target=tp_levels[-1]['price'],
                risk_reward_ratio=risk_reward,
                expected_duration_hours=self._estimate_duration(strategy_type),
                confidence_score=best_opportunity.get('confidence', 0.75),
                confluences=best_opportunity.get('key_factors', []),
                key_levels=analysis.get('key_levels', {}),
                invalidation_conditions=self._build_invalidation_conditions(
                    direction, stop_loss, market_structure
                ),
                setup_reasoning=self._build_reasoning(
                    best_opportunity, smc_data, ict_data
                )
            )
            
            # Validate setup
            if not setup.is_valid():
                logger.warning("Generated setup failed validation")
                return None
            
            logger.success(f"✅ Trade setup built: {direction} @ {setup.entry_price:.2f}, "
                          f"RR: {setup.risk_reward_ratio:.2f}, Confidence: {setup.confidence_score:.2f}")
            
            return setup
            
        except Exception as e:
            logger.error(f"Error building trade setup: {e}", exc_info=True)
            return None
    
    def _select_best_opportunity(
        self,
        opportunities: List[Dict[str, Any]]
    ) -> Optional[Dict[str, Any]]:
        """Select best opportunity from multiple options"""
        
        if not opportunities:
            return None
        
        # Sort by confluence count and confidence
        sorted_opps = sorted(
            opportunities,
            key=lambda x: (
                x.get('confluence_count', 0),
                x.get('confidence', 0)
            ),
            reverse=True
        )
        
        best = sorted_opps[0]
        
        # Must have minimum requirements
        if best.get('confluence_count', 0) < 3:
            logger.warning("Best opportunity has <3 confluences")
            return None
        
        if best.get('confidence', 0) < 0.65:
            logger.warning("Best opportunity has low confidence")
            return None
        
        return best
    
    def _calculate_entry_zone(
        self,
        direction: str,
        opportunity: Dict[str, Any],
        smc_data: Dict[str, Any],
        ict_data: Dict[str, Any],
        current_price: float
    ) -> Dict[str, float]:
        """
        Calculate optimal entry zone
        
        Priority:
        1. Order Block zone
        2. FVG level
        3. OTE zone
        4. Entry zone from opportunity
        """
        
        entry_zone = opportunity.get('entry_zone', [current_price, current_price])
        
        # Start with opportunity zone
        zone_low = entry_zone[0] if len(entry_zone) >= 2 else current_price * 0.995
        zone_high = entry_zone[1] if len(entry_zone) >= 2 else current_price * 1.005
        
        # Refine with Order Blocks
        smc_computational = smc_data.get('computational', {})
        order_blocks = smc_computational.get('order_blocks', [])
        
        if order_blocks:
            # Filter by direction
            relevant_obs = [
                ob for ob in order_blocks
                if ob['type'] == ('bullish' if direction == 'LONG' else 'bearish')
            ]
            
            if relevant_obs:
                # Use highest strength OB
                best_ob = max(relevant_obs, key=lambda x: x.get('strength', 0))
                zone_low = best_ob['zone'][0]
                zone_high = best_ob['zone'][1]
        
        # Consider FVG as entry magnet
        fvgs = smc_computational.get('fair_value_gaps', [])
        if fvgs:
            relevant_fvgs = [
                fvg for fvg in fvgs
                if fvg['type'] == ('bullish' if direction == 'LONG' else 'bearish')
                and not fvg.get('filled', False)
            ]
            
            if relevant_fvgs:
                # FVG can be additional entry confirmation
                fvg = relevant_fvgs[0]
                fvg_midpoint = (fvg['gap'][0] + fvg['gap'][1]) / 2
                
                # If FVG is within 1% of entry zone, adjust to it
                if abs(fvg_midpoint - zone_low) / zone_low < 0.01:
                    zone_low = fvg['gap'][0]
                    zone_high = fvg['gap'][1]
        
        # Check OTE zone
        ict_computational = ict_data.get('computational', {})
        ote_zones = ict_computational.get('ote_zones', {})
        
        if ote_zones and ote_zones.get('in_ote_zone'):
            # If currently in OTE, use that as entry zone
            zone_low = ote_zones['ote_low']
            zone_high = ote_zones['ote_high']
        
        # Calculate optimal entry (middle of zone, slightly biased)
        if direction == 'LONG':
            # For longs, prefer lower end of zone (better entry)
            optimal_entry = zone_low + (zone_high - zone_low) * 0.3
        else:
            # For shorts, prefer upper end of zone
            optimal_entry = zone_low + (zone_high - zone_low) * 0.7
        
        return {
            'optimal_entry': round(optimal_entry, 2),
            'zone_low': round(zone_low, 2),
            'zone_high': round(zone_high, 2)
        }
    
    def _calculate_stop_loss(
        self,
        direction: str,
        entry_zone: Dict[str, float],
        smc_data: Dict[str, Any],
        ict_data: Dict[str, Any],
        atr: float,
        invalidation_level: Optional[float] = None
    ) -> float:
        """
        Calculate stop-loss level
        
        Priority:
        1. Invalidation level from analysis
        2. Beyond Order Block
        3. ATR-based (1.5x ATR)
        4. Fixed % (2%)
        """
        
        entry_price = entry_zone['optimal_entry']
        
        # Start with invalidation level if provided
        if invalidation_level:
            return round(invalidation_level, 2)
        
        # Check SMC structures
        smc_computational = smc_data.get('computational', {})
        order_blocks = smc_computational.get('order_blocks', [])
        
        if order_blocks:
            relevant_obs = [
                ob for ob in order_blocks
                if ob['type'] == ('bullish' if direction == 'LONG' else 'bearish')
            ]
            
            if relevant_obs:
                best_ob = max(relevant_obs, key=lambda x: x.get('strength', 0))
                
                # SL beyond the order block
                if direction == 'LONG':
                    sl = best_ob['zone'][0] - (atr * 0.5)  # Below OB
                else:
                    sl = best_ob['zone'][1] + (atr * 0.5)  # Above OB
                
                return round(sl, 2)
        
        # Fallback to ATR-based
        if direction == 'LONG':
            sl = entry_price - (atr * 1.5)
        else:
            sl = entry_price + (atr * 1.5)
        
        return round(sl, 2)
    
    def _generate_take_profits(
        self,
        direction: str,
        entry_price: float,
        stop_loss: float,
        smc_data: Dict[str, Any],
        analysis: Dict[str, Any]
    ) -> List[Dict[str, float]]:
        """
        Generate multi-level take-profit targets
        
        Strategy:
        - TP1: 1:1.5 RR (33% position)
        - TP2: 1:2.5 RR (33% position)
        - TP3: 1:4+ RR (34% position)
        
        Refine with supply/demand zones and FVGs
        """
        
        risk = abs(entry_price - stop_loss)
        
        # Base TP levels (RR multiples)
        if direction == 'LONG':
            tp1_base = entry_price + (risk * 1.5)
            tp2_base = entry_price + (risk * 2.5)
            tp3_base = entry_price + (risk * 4.0)
        else:
            tp1_base = entry_price - (risk * 1.5)
            tp2_base = entry_price - (risk * 2.5)
            tp3_base = entry_price - (risk * 4.0)
        
        # Refine with key levels
        key_levels = analysis.get('key_levels', {})
        
        tp1 = self._refine_tp_with_levels(
            tp1_base, direction, key_levels, smc_data, tolerance=0.02
        )
        tp2 = self._refine_tp_with_levels(
            tp2_base, direction, key_levels, smc_data, tolerance=0.02
        )
        tp3 = self._refine_tp_with_levels(
            tp3_base, direction, key_levels, smc_data, tolerance=0.03
        )
        
        return [
            {'level': 1, 'price': round(tp1, 2), 'size': 0.33},
            {'level': 2, 'price': round(tp2, 2), 'size': 0.33},
            {'level': 3, 'price': round(tp3, 2), 'size': 0.34}
        ]
    
    def _refine_tp_with_levels(
        self,
        tp_price: float,
        direction: str,
        key_levels: Dict[str, List[float]],
        smc_data: Dict[str, Any],
        tolerance: float = 0.02
    ) -> float:
        """Refine TP by snapping to nearby key levels"""
        
        # Check resistance/support levels
        target_levels = key_levels.get(
            'resistance' if direction == 'LONG' else 'support',
            []
        )
        
        for level in target_levels:
            if abs(level - tp_price) / tp_price < tolerance:
                # Snap to this level (just before it)
                if direction == 'LONG':
                    return level * 0.999  # Just below resistance
                else:
                    return level * 1.001  # Just above support
        
        # Check FVG levels
        smc_computational = smc_data.get('computational', {})
        fvgs = smc_computational.get('fair_value_gaps', [])
        
        for fvg in fvgs:
            if not fvg.get('filled', False):
                fvg_mid = (fvg['gap'][0] + fvg['gap'][1]) / 2
                if abs(fvg_mid - tp_price) / tp_price < tolerance:
                    return fvg_mid  # FVG fill is good TP
        
        return tp_price
    
    def _calculate_risk_reward(
        self,
        entry_price: float,
        stop_loss: float,
        take_profits: List[Dict[str, float]]
    ) -> float:
        """Calculate average risk-reward ratio"""
        
        risk = abs(entry_price - stop_loss)
        
        # Weighted average reward
        total_reward = 0.0
        for tp in take_profits:
            reward = abs(tp['price'] - entry_price)
            total_reward += reward * tp['size']
        
        return round(total_reward / risk, 2) if risk > 0 else 0.0
    
    def _classify_strategy_type(
        self,
        ict_data: Dict[str, Any],
        market_structure: Dict[str, Any],
        tp_distance: float
    ) -> str:
        """Classify strategy type based on context"""
        
        # Check if in killzone
        ict_computational = ict_data.get('computational', {})
        killzone = ict_computational.get('killzone', {})
        
        if killzone.get('current_killzone') in ['london', 'new_york']:
            # Active killzone = likely day trade or scalp
            if tp_distance < 200:  # Small target
                return 'SCALP'
            else:
                return 'DAY_TRADE'
        
        # Check timeframe alignment
        mtf_bias = market_structure.get('alignment', 'conflicting')
        
        if 'strongly_aligned' in mtf_bias and tp_distance > 500:
            return 'SWING'
        elif tp_distance > 300:
            return 'DAY_TRADE'
        else:
            return 'SCALP'
    
    def _estimate_duration(self, strategy_type: str) -> float:
        """Estimate expected holding time in hours"""
        
        duration_map = {
            'SCALP': 1.5,       # 30 min to 2 hours
            'DAY_TRADE': 6.0,   # 4-8 hours
            'SWING': 48.0       # 1-3 days
        }
        
        return duration_map.get(strategy_type, 6.0)
    
    def _build_invalidation_conditions(
        self,
        direction: str,
        stop_loss: float,
        market_structure: Dict[str, Any]
    ) -> List[str]:
        """Build list of invalidation conditions"""
        
        conditions = [
            f"Price breaks {stop_loss:.2f} ({direction} setup invalidated)"
        ]
        
        # Add structure breaks
        if direction == 'LONG':
            conditions.append("Break of bullish structure on higher timeframe")
            conditions.append("Failure to hold above entry zone after 2+ retests")
        else:
            conditions.append("Break of bearish structure on higher timeframe")
            conditions.append("Failure to stay below entry zone after 2+ retests")
        
        return conditions
    
    def _build_reasoning(
        self,
        opportunity: Dict[str, Any],
        smc_data: Dict[str, Any],
        ict_data: Dict[str, Any]
    ) -> str:
        """Build detailed setup reasoning"""
        
        key_factors = opportunity.get('key_factors', [])
        
        reasoning_parts = [
            f"Trade Setup: {opportunity.get('direction')} with {opportunity.get('confluence_count', 0)} confluences",
            "",
            "Key Confluences:"
        ]
        
        for i, factor in enumerate(key_factors, 1):
            reasoning_parts.append(f"  {i}. {factor}")
        
        # Add ICT context
        ict_computational = ict_data.get('computational', {})
        killzone = ict_computational.get('killzone', {})
        
        if killzone.get('current_killzone'):
            reasoning_parts.append("")
            reasoning_parts.append(f"ICT Context: {killzone['current_killzone']} killzone active")
        
        # Add order flow
        order_flow = ict_computational.get('order_flow', {})
        if order_flow.get('phase'):
            reasoning_parts.append(f"Order Flow: {order_flow['phase']} phase detected")
        
        return "\n".join(reasoning_parts)
    
    def _generate_setup_id(self, symbol: str) -> str:
        """Generate unique setup ID"""
        self.setup_counter += 1
        timestamp = int(datetime.utcnow().timestamp())
        return f"{symbol}_{timestamp}_{self.setup_counter}"
```

### File: `tests/unit/test_trade_setup_builder.py`

```python
"""
Unit tests for Trade Setup Builder
"""
import pytest
from src.strategy.trade_setup_builder import TradeSetupBuilder, TradeSetup

@pytest.fixture
def sample_analysis():
    return {
        'trade_opportunities': [
            {
                'direction': 'LONG',
                'entry_zone': [43000, 43100],
                'confluence_count': 5,
                'confidence': 0.85,
                'invalidation_level': 42750,
                'key_factors': [
                    'Bullish order block at 43000',
                    'FVG above at 43500',
                    'Liquidity sweep below Asian low',
                    'RSI bullish divergence',
                    'MACD bullish crossover'
                ]
            }
        ],
        'smc_analysis': {
            'computational': {
                'order_blocks': [
                    {
                        'type': 'bullish',
                        'zone': [43000, 43100],
                        'strength': 0.85
                    }
                ],
                'fair_value_gaps': [
                    {
                        'type': 'bullish',
                        'gap': [43450, 43550],
                        'filled': False
                    }
                ]
            }
        },
        'ict_analysis': {
            'computational': {
                'killzone': {'current_killzone': 'london'},
                'order_flow': {'phase': 'accumulation'}
            }
        },
        'key_levels': {
            'resistance': [43500, 44000, 44500],
            'support': [43000, 42500, 42000]
        },
        'market_structure': {
            'alignment': 'strongly_aligned_bullish'
        }
    }

def test_builder_initialization():
    builder = TradeSetupBuilder()
    assert builder.setup_counter == 0

def test_build_setup(sample_analysis):
    builder = TradeSetupBuilder()
    
    setup = builder.build_setup(
        symbol='BTCUSDT',
        analysis=sample_analysis,
        current_price=43050,
        atr=150
    )
    
    assert setup is not None
    assert setup.symbol == 'BTCUSDT'
    assert setup.direction == 'LONG'
    assert setup.entry_price > 0
    assert setup.stop_loss < setup.entry_price
    assert len(setup.take_profit_levels) == 3

def test_risk_reward_calculation(sample_analysis):
    builder = TradeSetupBuilder()
    
    setup = builder.build_setup(
        symbol='BTCUSDT',
        analysis=sample_analysis,
        current_price=43050,
        atr=150
    )
    
    assert setup.risk_reward_ratio >= 2.0

def test_setup_validation():
    setup = TradeSetup(
        setup_id='test_1',
        symbol='BTCUSDT',
        timestamp='2024-01-01T00:00:00',
        direction='LONG',
        strategy_type='DAY_TRADE',
        entry_type='LIMIT',
        entry_price=43050,
        entry_zone_low=43000,
        entry_zone_high=43100,
        stop_loss=42750,
        stop_loss_type='HARD',
        risk_amount=200,
        risk_percentage=2.0,
        take_profit_levels=[
            {'level': 1, 'price': 43500, 'size': 0.33},
            {'level': 2, 'price': 43800, 'size': 0.33},
            {'level': 3, 'price': 44200, 'size': 0.34}
        ],
        final_target=44200,
        risk_reward_ratio=2.5,
        expected_duration_hours=6.0,
        confidence_score=0.85,
        confluences=['test'],
        key_levels={},
        invalidation_conditions=['test'],
        setup_reasoning='test'
    )
    
    assert setup.is_valid() == True

def test_invalid_setup_low_rr():
    setup = TradeSetup(
        setup_id='test_2',
        symbol='BTCUSDT',
        timestamp='2024-01-01T00:00:00',
        direction='LONG',
        strategy_type='DAY_TRADE',
        entry_type='LIMIT',
        entry_price=43050,
        entry_zone_low=43000,
        entry_zone_high=43100,
        stop_loss=42950,  # Very close SL
        stop_loss_type='HARD',
        risk_amount=100,
        risk_percentage=1.0,
        take_profit_levels=[
            {'level': 1, 'price': 43200, 'size': 1.0}  # Only 1.5:1 RR
        ],
        final_target=43200,
        risk_reward_ratio=1.5,  # Below 2.0 minimum
        expected_duration_hours=6.0,
        confidence_score=0.85,
        confluences=['test'],
        key_levels={},
        invalidation_conditions=['test'],
        setup_reasoning='test'
    )
    
    assert setup.is_valid() == False
```

---

# 🎫 Ticket #4.1.2: Risk-Reward Calculator
**Story Points:** 8  
**Priority:** P0  
**Status:** 🔴 NOT STARTED  
**Assignee:** Backend Developer  
**Sprint:** Week 7, Day 2-3

## 📋 Description

Implement comprehensive risk-reward calculation system that ensures all setups meet minimum RR requirements and optimizes TP placement.

## 🎯 Acceptance Criteria

- [ ] **RR Calculation**
  - Accurate entry-to-SL risk calculation
  - Multi-level TP weighted reward calculation
  - Minimum 2:1 RR requirement enforcement
  - Support for partial exits

- [ ] **TP Optimization**
  - Adjust TPs to improve RR while respecting levels
  - Calculate optimal scaling-out strategy
  - Consider commission/slippage impact
  - Maximize expectancy

- [ ] **Scenario Analysis**
  - Calculate expected value for setup
  - Simulate partial exit scenarios
  - Probability-weighted outcomes
  - Break-even analysis

- [ ] **Quality**
  - Unit tests >85% coverage
  - Performance <100ms
  - Accurate floating-point math

## 📦 Deliverables

### File: `src/strategy/risk_reward_calculator.py`

```python
"""
Risk-Reward Calculator
Advanced RR calculation and optimization
"""
import numpy as np
from typing import Dict, Any, List, Tuple, Optional
from dataclasses import dataclass
from loguru import logger

@dataclass
class RiskRewardAnalysis:
    """Complete RR analysis result"""
    risk_amount: float
    reward_amount: float
    risk_reward_ratio: float
    expected_value: float
    break_even_win_rate: float
    optimized_tp_levels: List[Dict[str, float]]
    scenario_analysis: Dict[str, float]
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'risk_amount': round(self.risk_amount, 2),
            'reward_amount': round(self.reward_amount, 2),
            'risk_reward_ratio': round(self.risk_reward_ratio, 2),
            'expected_value': round(self.expected_value, 2),
            'break_even_win_rate': round(self.break_even_win_rate, 3),
            'optimized_tp_levels': self.optimized_tp_levels,
            'scenario_analysis': self.scenario_analysis
        }

class RiskRewardCalculator:
    """
    Calculate and optimize risk-reward metrics
    """
    
    # Trading costs
    COMMISSION_RATE = 0.0004  # 0.04% per side (Binance futures)
    SLIPPAGE_RATE = 0.0002    # 0.02% estimated slippage
    
    def __init__(self):
        pass
    
    def calculate(
        self,
        entry_price: float,
        stop_loss: float,
        take_profit_levels: List[Dict[str, float]],
        win_rate_estimate: float = 0.5,
        include_costs: bool = True
    ) -> RiskRewardAnalysis:
        """
        Complete risk-reward analysis
        
        Args:
            entry_price: Entry price
            stop_loss: Stop-loss price
            take_profit_levels: List of TPs with sizes
            win_rate_estimate: Expected win rate (0-1)
            include_costs: Include commission/slippage
            
        Returns:
            RiskRewardAnalysis object
        """
        try:
            # Calculate base risk
            risk = abs(entry_price - stop_loss)
            
            # Calculate weighted reward
            total_reward = 0.0
            for tp in take_profit_levels:
                tp_reward = abs(tp['price'] - entry_price)
                total_reward += tp_reward * tp['size']
            
            # Apply costs if requested
            if include_costs:
                cost_per_dollar = self.COMMISSION_RATE + self.SLIPPAGE_RATE
                risk_with_costs = risk + (entry_price * cost_per_dollar * 2)  # Entry + Exit
                reward_with_costs = total_reward - (entry_price * cost_per_dollar * 2)
                
                risk = risk_with_costs
                total_reward = max(reward_with_costs, 0)
            
            # Calculate RR ratio
            rr_ratio = total_reward / risk if risk > 0 else 0
            
            # Calculate expected value
            expected_value = self._calculate_expected_value(
                risk, total_reward, win_rate_estimate
            )
            
            # Calculate break-even win rate
            break_even_wr = self._calculate_break_even_win_rate(risk, total_reward)
            
            # Optimize TP levels
            optimized_tps = self._optimize_tp_levels(
                entry_price, stop_loss, take_profit_levels
            )
            
            # Scenario analysis
            scenarios = self._run_scenario_analysis(
                entry_price, stop_loss, take_profit_levels, win_rate_estimate
            )
            
            return RiskRewardAnalysis(
                risk_amount=risk,
                reward_amount=total_reward,
                risk_reward_ratio=rr_ratio,
                expected_value=expected_value,
                break_even_win_rate=break_even_wr,
                optimized_tp_levels=optimized_tps,
                scenario_analysis=scenarios
            )
            
        except Exception as e:
            logger.error(f"Error calculating RR: {e}", exc_info=True)
            raise
    
    def _calculate_expected_value(
        self,
        risk: float,
        reward: float,
        win_rate: float
    ) -> float:
        """
        Calculate expected value (expectancy)
        EV = (Win% × Reward) - (Loss% × Risk)
        """
        loss_rate = 1 - win_rate
        ev = (win_rate * reward) - (loss_rate * risk)
        return ev
    
    def _calculate_break_even_win_rate(
        self,
        risk: float,
        reward: float
    ) -> float:
        """
        Calculate minimum win rate needed to break even
        BE_WR = Risk / (Risk + Reward)
        """
        if risk + reward == 0:
            return 1.0
        
        be_wr = risk / (risk + reward)
        return min(be_wr, 1.0)
    
    def _optimize_tp_levels(
        self,
        entry_price: float,
        stop_loss: float,
        tp_levels: List[Dict[str, float]]
    ) -> List[Dict[str, float]]:
        """
        Optimize TP levels to maximize RR while maintaining structure
        
        Strategy:
        - Keep TP1 conservative (quick profit, move SL to BE)
        - Extend TP2 and TP3 if possible
        - Maintain logical progression
        """
        
        if len(tp_levels) < 3:
            return tp_levels
        
        risk = abs(entry_price - stop_loss)
        direction = 1 if tp_levels[0]['price'] > entry_price else -1
        
        # Optimize each TP level
        optimized = []
        
        for i, tp in enumerate(tp_levels):
            current_rr = abs(tp['price'] - entry_price) / risk
            
            if i == 0:
                # TP1: Keep conservative (1.5:1 to 2:1)
                target_rr = max(1.5, min(current_rr, 2.0))
            elif i == 1:
                # TP2: Aim for 2.5:1 to 3:1
                target_rr = max(2.5, min(current_rr, 3.5))
            else:
                # TP3+: Aim for 4:1+
                target_rr = max(4.0, current_rr)
            
            optimized_price = entry_price + (direction * risk * target_rr)
            
            optimized.append({
                'level': tp['level'],
                'price': round(optimized_price, 2),
                'size': tp['size'],
                'rr_ratio': round(target_rr, 2)
            })
        
        return optimized
    
    def _run_scenario_analysis(
        self,
        entry_price: float,
        stop_loss: float,
        tp_levels: List[Dict[str, float]],
        win_rate: float
    ) -> Dict[str, float]:
        """
        Run various scenario simulations
        """
        
        risk = abs(entry_price - stop_loss)
        
        scenarios = {}
        
        # Scenario 1: Full loss
        scenarios['full_loss'] = -risk
        
        # Scenario 2: Partial hits (only TP1)
        if len(tp_levels) >= 1:
            tp1_reward = abs(tp_levels[0]['price'] - entry_price) * tp_levels[0]['size']
            scenarios['tp1_only'] = tp1_reward - (risk * (1 - tp_levels[0]['size']))
        
        # Scenario 3: TP1 + TP2
        if len(tp_levels) >= 2:
            tp1_reward = abs(tp_levels[0]['price'] - entry_price) * tp_levels[0]['size']
            tp2_reward = abs(tp_levels[1]['price'] - entry_price) * tp_levels[1]['size']
            remaining_risk = risk * (1 - tp_levels[0]['size'] - tp_levels[1]['size'])
            scenarios['tp1_tp2'] = tp1_reward + tp2_reward - remaining_risk
        
        # Scenario 4: All TPs hit
        total_reward = sum(
            abs(tp['price'] - entry_price) * tp['size']
            for tp in tp_levels
        )
        scenarios['all_tps'] = total_reward
        
        # Scenario 5: Average outcome (probability-weighted)
        scenarios['expected_outcome'] = self._calculate_expected_value(
            risk,
            sum(abs(tp['price'] - entry_price) * tp['size'] for tp in tp_levels),
            win_rate
        )
        
        return {k: round(v, 2) for k, v in scenarios.items()}
    
    def validate_minimum_rr(
        self,
        entry_price: float,
        stop_loss: float,
        take_profit_levels: List[Dict[str, float]],
        minimum_rr: float = 2.0
    ) -> Tuple[bool, float]:
        """
        Validate if setup meets minimum RR requirement
        
        Returns:
            (meets_requirement, actual_rr)
        """
        
        risk = abs(entry_price - stop_loss)
        
        total_reward = sum(
            abs(tp['price'] - entry_price) * tp['size']
            for tp in take_profit_levels
        )
        
        actual_rr = total_reward / risk if risk > 0 else 0
        
        return (actual_rr >= minimum_rr, actual_rr)
    
    def calculate_position_risk(
        self,
        entry_price: float,
        stop_loss: float,
        position_size: float,
        account_balance: float
    ) -> Dict[str, float]:
        """
        Calculate position risk metrics
        """
        
        risk_per_unit = abs(entry_price - stop_loss)
        total_risk = risk_per_unit * position_size
        risk_percentage = (total_risk / account_balance) * 100 if account_balance > 0 else 0
        
        return {
            'risk_per_unit': round(risk_per_unit, 2),
            'total_risk_dollars': round(total_risk, 2),
            'risk_percentage': round(risk_percentage, 2),
            'position_value': round(entry_price * position_size, 2)
        }
    
    def adjust_tp_for_better_rr(
        self,
        entry_price: float,
        stop_loss: float,
        current_tp: float,
        target_rr: float
    ) -> float:
        """
        Adjust a single TP to achieve target RR
        """
        
        risk = abs(entry_price - stop_loss)
        required_reward = risk * target_rr
        
        direction = 1 if current_tp > entry_price else -1
        new_tp = entry_price + (direction * required_reward)
        
        return round(new_tp, 2)
```

---

# 🎫 Ticket #4.1.3: Position Sizing Engine
**Story Points:** 8  
**Priority:** P0  
**Status:** 🔴 NOT STARTED  
**Assignee:** Backend Developer  
**Sprint:** Week 7, Day 3

## 📋 Description

Implement intelligent position sizing engine that calculates optimal position sizes based on risk parameters, volatility, and account balance.

## 🎯 Acceptance Criteria

- [ ] **Fixed Risk Sizing**
  - Calculate size for fixed % risk (default 2%)
  - Account balance consideration
  - Leverage calculation for futures
  - Minimum/maximum size limits

- [ ] **Volatility-Adjusted Sizing**
  - ATR-based size adjustment
  - Reduce size in high volatility
  - Increase size in low volatility
  - Volatility normalization

- [ ] **Kelly Criterion** (Optional)
  - Calculate optimal f (Kelly %)
  - Conservative Kelly (half-Kelly, quarter-Kelly)
  - Win rate and RR inputs
  - Risk of ruin calculation

- [ ] **Portfolio Heat Management**
  - Consider existing positions
  - Correlation-adjusted sizing
  - Maximum portfolio exposure (6%)
  - Available buying power

- [ ] **Quality**
  - Unit tests >85% coverage
  - Handles edge cases (zero balance, etc.)
  - Accurate decimal precision

## 📦 Deliverables

### File: `src/strategy/position_sizer.py`

```python
"""
Position Sizing Engine
Calculates optimal position sizes based on risk parameters
"""
import numpy as np
from typing import Dict, Any, Optional, List
from dataclasses import dataclass
from loguru import logger

@dataclass
class PositionSizeResult:
    """Position sizing calculation result"""
    recommended_size: float
    max_size: float
    risk_amount: float
    position_value: float
    leverage_used: float
    sizing_method: str
    warnings: List[str]
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'recommended_size': round(self.recommended_size, 6),
            'max_size': round(self.max_size, 6),
            'risk_amount': round(self.risk_amount, 2),
            'position_value': round(self.position_value, 2),
            'leverage_used': round(self.leverage_used, 2),
            'sizing_method': self.sizing_method,
            'warnings': self.warnings
        }

class PositionSizer:
    """
    Intelligent position sizing engine
    
    Methods:
    1. Fixed Risk % (default 2%)
    2. Volatility-Adjusted (ATR-based)
    3. Kelly Criterion (optional)
    4. Portfolio Heat-Aware
    """
    
    def __init__(
        self,
        default_risk_percent: float = 2.0,
        max_portfolio_heat: float = 6.0,
        max_leverage: float = 10.0
    ):
        self.default_risk_percent = default_risk_percent
        self.max_portfolio_heat = max_portfolio_heat
        self.max_leverage = max_leverage
    
    def calculate_size(
        self,
        account_balance: float,
        entry_price: float,
        stop_loss: float,
        risk_percent: Optional[float] = None,
        atr: Optional[float] = None,
        current_exposure: float = 0.0,
        method: str = 'fixed_risk'
    ) -> PositionSizeResult:
        """
        Calculate position size
        
        Args:
            account_balance: Account balance in USD
            entry_price: Entry price
            stop_loss: Stop-loss price
            risk_percent: Risk percentage (default: 2%)
            atr: ATR for volatility adjustment
            current_exposure: Current portfolio exposure (%)
            method: 'fixed_risk', 'volatility_adjusted', 'kelly'
            
        Returns:
            PositionSizeResult object
        """
        try:
            risk_pct = risk_percent or self.default_risk_percent
            warnings = []
            
            # Check if risk exceeds available exposure
            available_exposure = self.max_portfolio_heat - current_exposure
            if risk_pct > available_exposure:
                warnings.append(
                    f"Risk {risk_pct}% exceeds available exposure {available_exposure:.1f}%"
                )
                risk_pct = available_exposure
            
            # Calculate based on method
            if method == 'volatility_adjusted' and atr:
                size = self._calculate_volatility_adjusted_size(
                    account_balance, entry_price, stop_loss, risk_pct, atr
                )
            elif method == 'kelly':
                size = self._calculate_kelly_size(
                    account_balance, entry_price, stop_loss
                )
            else:  # fixed_risk
                size = self._calculate_fixed_risk_size(
                    account_balance, entry_price, stop_loss, risk_pct
                )
            
            # Calculate max size (with leverage)
            max_size = self._calculate_max_size(
                account_balance, entry_price, self.max_leverage
            )
            
            # Cap at max size
            if size > max_size:
                warnings.append(
                    f"Position size {size:.4f} exceeds max {max_size:.4f}, capping"
                )
                size = max_size
            
            # Calculate metrics
            risk_per_unit = abs(entry_price - stop_loss)
            risk_amount = size * risk_per_unit
            position_value = size * entry_price
            leverage_used = position_value / account_balance if account_balance > 0 else 0
            
            # Validate reasonable size
            if size <= 0:
                warnings.append("Calculated size is zero or negative")
            
            if leverage_used > self.max_leverage:
                warnings.append(
                    f"Leverage {leverage_used:.1f}x exceeds max {self.max_leverage}x"
                )
            
            return PositionSizeResult(
                recommended_size=size,
                max_size=max_size,
                risk_amount=risk_amount,
                position_value=position_value,
                leverage_used=leverage_used,
                sizing_method=method,
                warnings=warnings
            )
            
        except Exception as e:
            logger.error(f"Error calculating position size: {e}", exc_info=True)
            raise
    
    def _calculate_fixed_risk_size(
        self,
        balance: float,
        entry: float,
        stop_loss: float,
        risk_percent: float
    ) -> float:
        """
        Fixed risk percentage method
        Size = (Balance × Risk%) / (Entry - StopLoss)
        """
        
        risk_amount = balance * (risk_percent / 100)
        price_risk = abs(entry - stop_loss)
        
        if price_risk == 0:
            return 0.0
        
        size = risk_amount / price_risk
        return size
    
    def _calculate_volatility_adjusted_size(
        self,
        balance: float,
        entry: float,
        stop_loss: float,
        risk_percent: float,
        atr: float
    ) -> float:
        """
        Volatility-adjusted sizing
        Reduce size when volatility is high, increase when low
        """
        
        # Calculate base size
        base_size = self._calculate_fixed_risk_size(
            balance, entry, stop_loss, risk_percent
        )
        
        # Calculate volatility adjustment factor
        price_risk = abs(entry - stop_loss)
        
        # Normalize ATR
        atr_ratio = atr / entry  # ATR as % of price
        
        # Adjustment factor (reduce size if stop is wider than ATR)
        if atr > 0:
            volatility_factor = min(atr / price_risk, 2.0)  # Cap at 2x
            volatility_factor = max(volatility_factor, 0.5)  # Floor at 0.5x
        else:
            volatility_factor = 1.0
        
        adjusted_size = base_size * volatility_factor
        
        return adjusted_size
    
    def _calculate_kelly_size(
        self,
        balance: float,
        entry: float,
        stop_loss: float,
        win_rate: float = 0.5,
        avg_rr: float = 2.5
    ) -> float:
        """
        Kelly Criterion sizing (Conservative - Quarter Kelly)
        
        Kelly % = (Win% × RR - Loss%) / RR
        Position Size = Balance × Kelly% / Price Risk
        """
        
        loss_rate = 1 - win_rate
        
        # Kelly formula
        kelly_percent = ((win_rate * avg_rr) - loss_rate) / avg_rr
        kelly_percent = max(kelly_percent, 0)  # No negative
        
        # Use Quarter Kelly for safety
        conservative_kelly = kelly_percent * 0.25
        
        # Cap at 5% (safety)
        conservative_kelly = min(conservative_kelly, 0.05)
        
        # Calculate size
        risk_amount = balance * conservative_kelly
        price_risk = abs(entry - stop_loss)
        
        if price_risk == 0:
            return 0.0
        
        size = risk_amount / price_risk
        return size
    
    def _calculate_max_size(
        self,
        balance: float,
        entry_price: float,
        max_leverage: float
    ) -> float:
        """
        Calculate maximum possible position size with leverage
        """
        
        max_position_value = balance * max_leverage
        max_size = max_position_value / entry_price if entry_price > 0 else 0
        
        return max_size
    
    def calculate_with_correlation(
        self,
        account_balance: float,
        entry_price: float,
        stop_loss: float,
        existing_positions: List[Dict[str, Any]],
        correlation_matrix: Dict[str, float]
    ) -> PositionSizeResult:
        """
        Calculate position size considering correlation with existing positions
        
        Reduce size if highly correlated positions exist
        """
        
        # Calculate base size
        base_result = self.calculate_size(
            account_balance, entry_price, stop_loss
        )
        
        # Calculate correlation adjustment
        correlation_factor = 1.0
        
        for position in existing_positions:
            symbol_pair = f"{position['symbol']}"
            correlation = correlation_matrix.get(symbol_pair, 0.0)
            
            # If highly correlated (>0.7), reduce size
            if abs(correlation) > 0.7:
                reduction = abs(correlation) * 0.5  # Up to 50% reduction
                correlation_factor *= (1 - reduction)
        
        # Adjust size
        adjusted_size = base_result.recommended_size * correlation_factor
        
        base_result.recommended_size = adjusted_size
        base_result.warnings.append(
            f"Size adjusted by {correlation_factor:.2f}x for correlation"
        )
        
        return base_result
    
    def validate_size(
        self,
        position_size: float,
        entry_price: float,
        stop_loss: float,
        account_balance: float,
        max_risk_percent: float = 2.5
    ) -> Tuple[bool, List[str]]:
        """
        Validate if position size is safe
        
        Returns:
            (is_valid, list_of_issues)
        """
        
        issues = []
        
        # Check if size is positive
        if position_size <= 0:
            issues.append("Position size must be positive")
        
        # Check risk amount
        risk_per_unit = abs(entry_price - stop_loss)
        risk_amount = position_size * risk_per_unit
        risk_percent = (risk_amount / account_balance) * 100 if account_balance > 0 else 100
        
        if risk_percent > max_risk_percent:
            issues.append(
                f"Risk {risk_percent:.2f}% exceeds maximum {max_risk_percent}%"
            )
        
        # Check leverage
        position_value = position_size * entry_price
        leverage = position_value / account_balance if account_balance > 0 else 999
        
        if leverage > self.max_leverage:
            issues.append(
                f"Leverage {leverage:.1f}x exceeds maximum {self.max_leverage}x"
            )
        
        # Check minimum size
        if position_size < 0.001:
            issues.append("Position size too small (< 0.001)")
        
        return (len(issues) == 0, issues)
```

---

# 🎫 Ticket #4.1.4: Confluence Scorer
**Story Points:** 6  
**Priority:** P0  
**Status:** 🔴 NOT STARTED  
**Assignee:** Backend Developer  
**Sprint:** Week 7, Day 3

## 📋 Description

Implement confluence scoring system that quantifies setup quality based on multiple confirming factors from SMC, ICT, and technical analysis.

## 🎯 Acceptance Criteria

- [ ] **Confluence Detection**
  - Count SMC factors (OB, FVG, BOS)
  - Count ICT factors (Killzone, Sweeps, OTE)
  - Count indicator confluences (RSI, MACD, etc.)
  - Count pattern confirmations

- [ ] **Weighted Scoring**
  - Assign weights to different confluence types
  - Higher timeframe factors weight more
  - SMC/ICT factors prioritized
  - Calculate total confluence score (0-1)

- [ ] **Confidence Mapping**
  - Map confluence count to confidence %
  - 3 confluences = 0.65 confidence
  - 5 confluences = 0.85 confidence
  - 7+ confluences = 0.95 confidence

- [ ] **Quality Classification**
  - Excellent: 7+ confluences
  - Good: 5-6 confluences
  - Fair: 3-4 confluences
  - Poor: <3 confluences

## 📦 Deliverables

### File: `src/strategy/confluence_scorer.py`

```python
"""
Confluence Scorer
Quantifies setup quality based on multiple confirming factors
"""
from typing import Dict, Any, List, Tuple
from dataclasses import dataclass
from loguru import logger

@dataclass
class ConfluenceScore:
    """Confluence scoring result"""
    total_score: float  # 0-1
    confluence_count: int
    confidence_level: float  # 0-1
    quality_rating: str  # 'excellent', 'good', 'fair', 'poor'
    factors: List[Dict[str, Any]]
    breakdown: Dict[str, float]
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'total_score': round(self.total_score, 3),
            'confluence_count': self.confluence_count,
            'confidence_level': round(self.confidence_level, 3),
            'quality_rating': self.quality_rating,
            'factors': self.factors,
            'breakdown': {k: round(v, 3) for k, v in self.breakdown.items()}
        }

class ConfluenceScorer:
    """
    Calculate confluence scores for trade setups
    
    Confluence Categories:
    1. SMC Factors (0.35 weight)
    2. ICT Factors (0.30 weight)
    3. Technical Indicators (0.20 weight)
    4. Multi-Timeframe Alignment (0.15 weight)
    """
    
    # Factor weights
    WEIGHTS = {
        'smc': 0.35,
        'ict': 0.30,
        'indicators': 0.20,
        'mtf': 0.15
    }
    
    # Individual factor scores
    FACTOR_SCORES = {
        # SMC Factors
        'order_block': 0.15,
        'fvg': 0.12,
        'bos': 0.10,
        'liquidity_zone': 0.08,
        'supply_demand': 0.10,
        
        # ICT Factors
        'killzone_active': 0.12,
        'liquidity_sweep': 0.15,
        'ote_zone': 0.10,
        'order_flow': 0.08,
        'manipulation': 0.10,
        
        # Indicator Factors
        'rsi_divergence': 0.10,
        'macd_crossover': 0.08,
        'ema_alignment': 0.08,
        'volume_confirmation': 0.06,
        'bb_squeeze': 0.06,
        
        # MTF Factors
        'htf_alignment': 0.10,
        'mtf_confirmation': 0.08,
        'trend_alignment': 0.07
    }
    
    def __init__(self):
        pass
    
    def calculate(
        self,
        direction: str,
        smc_data: Dict[str, Any],
        ict_data: Dict[str, Any],
        indicators: Dict[str, Any],
        mtf_analysis: Dict[str, Any]
    ) -> ConfluenceScore:
        """
        Calculate comprehensive confluence score
        
        Args:
            direction: 'LONG' or 'SHORT'
            smc_data: SMC analysis results
            ict_data: ICT analysis results
            indicators: Technical indicators
            mtf_analysis: Multi-timeframe analysis
            
        Returns:
            ConfluenceScore object
        """
        try:
            factors = []
            scores = {
                'smc': 0.0,
                'ict': 0.0,
                'indicators': 0.0,
                'mtf': 0.0
            }
            
            # Score SMC factors
            smc_score, smc_factors = self._score_smc_factors(
                direction, smc_data
            )
            scores['smc'] = smc_score
            factors.extend(smc_factors)
            
            # Score ICT factors
            ict_score, ict_factors = self._score_ict_factors(
                direction, ict_data
            )
            scores['ict'] = ict_score
            factors.extend(ict_factors)
            
            # Score indicator factors
            ind_score, ind_factors = self._score_indicator_factors(
                direction, indicators
            )
            scores['indicators'] = ind_score
            factors.extend(ind_factors)
            
            # Score MTF factors
            mtf_score, mtf_factors = self._score_mtf_factors(
                direction, mtf_analysis
            )
            scores['mtf'] = mtf_score
            factors.extend(mtf_factors)
            
            # Calculate weighted total score
            total_score = (
                scores['smc'] * self.WEIGHTS['smc'] +
                scores['ict'] * self.WEIGHTS['ict'] +
                scores['indicators'] * self.WEIGHTS['indicators'] +
                scores['mtf'] * self.WEIGHTS['mtf']
            )
            
            # Count confluences
            confluence_count = len(factors)
            
            # Map to confidence level
            confidence = self._map_to_confidence(confluence_count, total_score)
            
            # Determine quality rating
            quality = self._determine_quality(confluence_count)
            
            return ConfluenceScore(
                total_score=total_score,
                confluence_count=confluence_count,
                confidence_level=confidence,
                quality_rating=quality,
                factors=factors,
                breakdown=scores
            )
            
        except Exception as e:
            logger.error(f"Error calculating confluence: {e}", exc_info=True)
            raise
    
    def _score_smc_factors(
        self,
        direction: str,
        smc_data: Dict[str, Any]
    ) -> Tuple[float, List[Dict[str, Any]]]:
        """Score SMC factors"""
        
        score = 0.0
        factors = []
        
        computational = smc_data.get('computational', {})
        
        # Order Blocks
        obs = computational.get('order_blocks', [])
        relevant_obs = [
            ob for ob in obs
            if ob['type'] == ('bullish' if direction == 'LONG' else 'bearish')
        ]
        
        if relevant_obs:
            best_ob = max(relevant_obs, key=lambda x: x.get('strength', 0))
            ob_score = self.FACTOR_SCORES['order_block'] * best_ob['strength']
            score += ob_score
            factors.append({
                'type': 'smc',
                'name': 'Order Block',
                'description': f"{direction} OB at {best_ob['zone']}",
                'score': ob_score,
                'strength': best_ob['strength']
            })
        
        # Fair Value Gaps
        fvgs = computational.get('fair_value_gaps', [])
        relevant_fvgs = [
            fvg for fvg in fvgs
            if fvg['type'] == ('bullish' if direction == 'LONG' else 'bearish')
            and not fvg.get('filled', False)
        ]
        
        if relevant_fvgs:
            fvg = relevant_fvgs[0]
            fvg_score = self.FACTOR_SCORES['fvg']
            score += fvg_score
            factors.append({
                'type': 'smc',
                'name': 'Fair Value Gap',
                'description': f"Unfilled FVG at {fvg['gap']}",
                'score': fvg_score,
                'strength': 1.0
            })
        
        # Break of Structure
        bos_events = computational.get('break_of_structure', [])
        if bos_events:
            recent_bos = bos_events[-1]
            if recent_bos['type'] == ('bullish' if direction == 'LONG' else 'bearish'):
                bos_score = self.FACTOR_SCORES['bos']
                score += bos_score
                factors.append({
                    'type': 'smc',
                    'name': 'Break of Structure',
                    'description': f"{direction} BOS confirmed",
                    'score': bos_score,
                    'strength': 1.0
                })
        
        # Liquidity Zones
        liquidity = computational.get('liquidity_zones', [])
        if liquidity:
            liq_score = self.FACTOR_SCORES['liquidity_zone']
            score += liq_score
            factors.append({
                'type': 'smc',
                'name': 'Liquidity Zone',
                'description': f"Liquidity mapped",
                'score': liq_score,
                'strength': 0.8
            })
        
        return (min(score, 1.0), factors)
    
    def _score_ict_factors(
        self,
        direction: str,
        ict_data: Dict[str, Any]
    ) -> Tuple[float, List[Dict[str, Any]]]:
        """Score ICT factors"""
        
        score = 0.0
        factors = []
        
        computational = ict_data.get('computational', {})
        
        # Killzone
        killzone = computational.get('killzone', {})
        if killzone.get('current_killzone') in ['london', 'new_york']:
            kz_score = self.FACTOR_SCORES['killzone_active']
            score += kz_score
            factors.append({
                'type': 'ict',
                'name': 'Killzone Active',
                'description': f"{killzone['current_killzone']} killzone",
                'score': kz_score,
                'strength': 1.0
            })
        
        # Liquidity Sweeps
        sweeps = computational.get('liquidity_sweeps', [])
        relevant_sweeps = [
            s for s in sweeps
            if s.get('reversed', False) and s.get('significance') == 'high'
        ]
        
        if relevant_sweeps:
            sweep_score = self.FACTOR_SCORES['liquidity_sweep']
            score += sweep_score
            factors.append({
                'type': 'ict',
                'name': 'Liquidity Sweep',
                'description': f"{relevant_sweeps[0]['type']} swept",
                'score': sweep_score,
                'strength': 1.0
            })
        
        # OTE Zone
        ote = computational.get('ote_zones', {})
        if ote.get('in_ote_zone'):
            if ote.get('bias') == direction.lower():
                ote_score = self.FACTOR_SCORES['ote_zone']
                score += ote_score
                factors.append({
                    'type': 'ict',
                    'name': 'OTE Zone',
                    'description': f"Price in optimal trade entry zone",
                    'score': ote_score,
                    'strength': 0.9
                })
        
        # Order Flow
        order_flow = computational.get('order_flow', {})
        phase = order_flow.get('phase')
        
        if phase in ['accumulation', 'distribution']:
            expected_phase = 'accumulation' if direction == 'LONG' else 'distribution'
            if phase == expected_phase:
                of_score = self.FACTOR_SCORES['order_flow'] * order_flow.get('confidence', 0.7)
                score += of_score
                factors.append({
                    'type': 'ict',
                    'name': 'Order Flow',
                    'description': f"{phase} phase detected",
                    'score': of_score,
                    'strength': order_flow.get('confidence', 0.7)
                })
        
        return (min(score, 1.0), factors)
    
    def _score_indicator_factors(
        self,
        direction: str,
        indicators: Dict[str, Any]
    ) -> Tuple[float, List[Dict[str, Any]]]:
        """Score technical indicator factors"""
        
        score = 0.0
        factors = []
        
        # Use 1H or 4H indicators as primary
        primary_tf = '1h' if '1h' in indicators else '4h'
        if primary_tf not in indicators:
            return (0.0, [])
        
        ind = indicators[primary_tf]
        
        # RSI Divergence
        rsi_div = ind.get('rsi', {}).get('divergence')
        if rsi_div:
            expected_div = 'bullish' if direction == 'LONG' else 'bearish'
            if rsi_div == expected_div:
                rsi_score = self.FACTOR_SCORES['rsi_divergence']
                score += rsi_score
                factors.append({
                    'type': 'indicator',
                    'name': 'RSI Divergence',
                    'description': f"{expected_div} divergence",
                    'score': rsi_score,
                    'strength': 0.85
                })
        
        # MACD
        macd = ind.get('macd', {})
        macd_trend = macd.get('trend', 'neutral')
        expected_trend = 'bullish' if direction == 'LONG' else 'bearish'
        
        if macd_trend == expected_trend:
            macd_score = self.FACTOR_SCORES['macd_crossover']
            score += macd_score
            factors.append({
                'type': 'indicator',
                'name': 'MACD',
                'description': f"MACD {expected_trend}",
                'score': macd_score,
                'strength': 0.75
            })
        
        # EMA Alignment
        ema_alignment = ind.get('ema', {}).get('alignment', 'neutral')
        if ema_alignment == expected_trend:
            ema_score = self.FACTOR_SCORES['ema_alignment']
            score += ema_score
            factors.append({
                'type': 'indicator',
                'name': 'EMA Alignment',
                'description': f"EMAs aligned {expected_trend}",
                'score': ema_score,
                'strength': 0.8
            })
        
        # Bollinger Band Squeeze
        bb_squeeze = ind.get('bollinger', {}).get('squeeze', False)
        if bb_squeeze:
            bb_score = self.FACTOR_SCORES['bb_squeeze']
            score += bb_score
            factors.append({
                'type': 'indicator',
                'name': 'BB Squeeze',
                'description': "Volatility squeeze detected",
                'score': bb_score,
                'strength': 0.7
            })
        
        return (min(score, 1.0), factors)
    
    def _score_mtf_factors(
        self,
        direction: str,
        mtf_analysis: Dict[str, Any]
    ) -> Tuple[float, List[Dict[str, Any]]]:
        """Score multi-timeframe factors"""
        
        score = 0.0
        factors = []
        
        # Overall bias alignment
        overall_bias = mtf_analysis.get('overall_bias', 'neutral')
        expected_bias = direction.lower()
        
        if overall_bias == expected_bias:
            # Check strength of alignment
            alignment = mtf_analysis.get('alignment', 'conflicting')
            
            if 'strongly_aligned' in alignment:
                htf_score = self.FACTOR_SCORES['htf_alignment']
                score += htf_score
                factors.append({
                    'type': 'mtf',
                    'name': 'Strong HTF Alignment',
                    'description': f"All timeframes aligned {expected_bias}",
                    'score': htf_score,
                    'strength': 0.95
                })
            elif 'moderately_aligned' in alignment:
                mtf_score = self.FACTOR_SCORES['mtf_confirmation']
                score += mtf_score
                factors.append({
                    'type': 'mtf',
                    'name': 'MTF Confirmation',
                    'description': f"Majority timeframes {expected_bias}",
                    'score': mtf_score,
                    'strength': 0.75
                })
        
        # Entry timing
        entry_timing = mtf_analysis.get('entry_timing', 'poor')
        if entry_timing in ['excellent', 'good']:
            timing_score = self.FACTOR_SCORES['trend_alignment'] * (
                1.0 if entry_timing == 'excellent' else 0.7
            )
            score += timing_score
            factors.append({
                'type': 'mtf',
                'name': 'Entry Timing',
                'description': f"{entry_timing} entry timing",
                'score': timing_score,
                'strength': 1.0 if entry_timing == 'excellent' else 0.7
            })
        
        return (min(score, 1.0), factors)
    
    def _map_to_confidence(
        self,
        confluence_count: int,
        total_score: float
    ) -> float:
        """
        Map confluence count and score to confidence level
        
        Formula: Base confidence from count + score adjustment
        """
        
        # Base confidence from count
        if confluence_count >= 7:
            base_confidence = 0.90
        elif confluence_count >= 5:
            base_confidence = 0.80
        elif confluence_count >= 3:
            base_confidence = 0.65
        else:
            base_confidence = 0.45
        
        # Adjust with total score
        score_adjustment = (total_score - 0.5) * 0.2  # ±10% adjustment
        
        final_confidence = base_confidence + score_adjustment
        
        # Clamp between 0 and 1
        return max(0.0, min(1.0, final_confidence))
    
    def _determine_quality(self, confluence_count: int) -> str:
        """Determine quality rating from confluence count"""
        
        if confluence_count >= 7:
            return 'excellent'
        elif confluence_count >= 5:
            return 'good'
        elif confluence_count >= 3:
            return 'fair'
        else:
            return 'poor'
```

---

