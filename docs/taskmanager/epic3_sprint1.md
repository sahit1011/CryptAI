# EPIC 3: Market Analysis Agent
**Duration:** Weeks 5-6  
**Priority:** P0 (Critical)  
**Status:** 🟡 In Development  
**Dependencies:** EPIC 2 (Data Collection Agent) ✅ Complete

---

## 📋 Epic Overview

The Market Analysis Agent is the intelligence core of the trading system. It leverages LLM-powered reasoning (Claude Sonnet 4.5) to analyze multi-timeframe data, detect Smart Money Concepts (SMC), apply Inner Circle Trader (ICT) methodology, and identify high-probability trade setups.

### Key Responsibilities
- Multi-timeframe technical analysis (5m, 15m, 1h, 4h, 1d)
- Smart Money Concepts (Order Blocks, FVGs, BOS/CHoCH)
- ICT methodology (Killzones, Liquidity, OTE)
- Market structure and regime classification
- Trade opportunity identification with confluences

### Success Metrics
- Analysis completion time: <60 seconds
- Confluence detection accuracy: >85%
- LLM context optimization: <150K tokens/call
- Integration test pass rate: 100%
- Unit test coverage: >80%

---

## 🎯 Sprint Breakdown

### Sprint 3.1: Technical Indicators & SMC Foundation (Week 5)
**Goal:** Build the computational foundation for market analysis

**Tickets:**
1. ✅ Technical Indicators Module (8 SP)
2. ✅ SMC Detector Implementation (10 SP)
3. ⏳ ICT Methodology Module (10 SP)
4. ⏳ Pattern Recognition Module (6 SP)

### Sprint 3.2: LLM Integration & Analysis Agent (Week 6)
**Goal:** Integrate LLM reasoning and complete the agent

**Tickets:**
5. ⏳ LLM Context Preparation System (8 SP)
6. ⏳ Market Analysis Agent Core (12 SP)
7. ⏳ Multi-Timeframe Analyzer (8 SP)
8. ⏳ Integration Testing (6 SP)

**Total Story Points:** 68 SP (~2 developer-weeks)

---

# 🎫 Ticket #3.1.1: Technical Indicators Module
**Story Points:** 8  
**Priority:** P0  
**Status:** ✅ COMPLETE  
**Assignee:** Backend Developer

## Description
Implement comprehensive technical indicators calculation module using pandas-ta and custom algorithms.

## Acceptance Criteria
- [x] RSI (14, 21) with divergence detection
- [x] MACD (12, 26, 9) with histogram analysis
- [x] Bollinger Bands with squeeze detection
- [x] EMA ribbons (9, 21, 50, 200)
- [x] Volume profile and VWAP
- [x] ATR for volatility
- [x] Stochastic RSI
- [x] ADX for trend strength
- [x] Unit tests with >80% coverage
- [x] Performance: <100ms for 500 candles

## Implementation
*See previous document - indicators.py already implemented*

---

# 🎫 Ticket #3.1.2: SMC Detector Implementation
**Story Points:** 10  
**Priority:** P0  
**Status:** ✅ COMPLETE  
**Assignee:** Backend Developer

## Description
Implement Smart Money Concepts pattern detector for institutional trading signals.

## Acceptance Criteria
- [x] Order Block detection (bullish/bearish)
- [x] Fair Value Gap identification
- [x] Break of Structure detection
- [x] Liquidity zone mapping
- [x] Fibonacci retracement zones
- [x] Supply/Demand zone identification
- [x] Strength scoring for all patterns
- [x] Unit tests with >80% coverage
- [x] Performance: <200ms for 500 candles

## Implementation
*See previous document - smc_detector.py already implemented*

---
**Deliverables:**

**File:** `src/analysis/indicators.py`
```python
"""
Technical Indicators Module
Comprehensive indicator calculations for market analysis
"""
import pandas as pd
import numpy as np
from typing import Dict, Any, List, Tuple
import pandas_ta as ta
from loguru import logger

class TechnicalIndicators:
    """
    Calculate and analyze technical indicators
    """
    
    @staticmethod
    def calculate_all(df: pd.DataFrame) -> Dict[str, pd.Series]:
        """
        Calculate all indicators for a DataFrame
        
        Args:
            df: DataFrame with OHLCV data
            
        Returns:
            Dictionary of indicator series
        """
        indicators = {}
        
        try:
            # RSI
            indicators['rsi_14'] = ta.rsi(df['close'], length=14)
            indicators['rsi_21'] = ta.rsi(df['close'], length=21)
            
            # MACD
            macd = ta.macd(df['close'], fast=12, slow=26, signal=9)
            indicators['macd'] = macd['MACD_12_26_9']
            indicators['macd_signal'] = macd['MACDs_12_26_9']
            indicators['macd_histogram'] = macd['MACDh_12_26_9']
            
            # Bollinger Bands
            bb = ta.bbands(df['close'], length=20, std=2)
            indicators['bb_upper'] = bb['BBU_20_2.0']
            indicators['bb_middle'] = bb['BBM_20_2.0']
            indicators['bb_lower'] = bb['BBL_20_2.0']
            indicators['bb_width'] = (bb['BBU_20_2.0'] - bb['BBL_20_2.0']) / bb['BBM_20_2.0']
            
            # EMAs
            indicators['ema_9'] = ta.ema(df['close'], length=9)
            indicators['ema_21'] = ta.ema(df['close'], length=21)
            indicators['ema_50'] = ta.ema(df['close'], length=50)
            indicators['ema_200'] = ta.ema(df['close'], length=200)
            
            # Volume indicators
            indicators['volume_sma'] = ta.sma(df['volume'], length=20)
            indicators['vwap'] = ta.vwap(df['high'], df['low'], df['close'], df['volume'])
            
            # Volatility
            indicators['atr_14'] = ta.atr(df['high'], df['low'], df['close'], length=14)
            
            # Stochastic
            stoch = ta.stoch(df['high'], df['low'], df['close'])
            indicators['stoch_k'] = stoch['STOCHk_14_3_3']
            indicators['stoch_d'] = stoch['STOCHd_14_3_3']
            
            # ADX (trend strength)
            adx = ta.adx(df['high'], df['low'], df['close'], length=14)
            indicators['adx'] = adx['ADX_14']
            indicators['di_plus'] = adx['DMP_14']
            indicators['di_minus'] = adx['DMN_14']
            
            logger.debug(f"Calculated {len(indicators)} indicators")
            return indicators
            
        except Exception as e:
            logger.error(f"Error calculating indicators: {e}")
            return {}
    
    @staticmethod
    def detect_rsi_divergence(
        df: pd.DataFrame,
        rsi_series: pd.Series,
        lookback: int = 14
    ) -> Dict[str, Any]:
        """
        Detect RSI divergence
        
        Returns:
            Dict with divergence type and strength
        """
        if len(df) < lookback * 2:
            return {'divergence': None}
        
        price = df['close'].values
        rsi = rsi_series.values
        
        # Find peaks and troughs
        price_peaks = TechnicalIndicators._find_peaks(price, lookback)
        price_troughs = TechnicalIndicators._find_troughs(price, lookback)
        
        rsi_peaks = TechnicalIndicators._find_peaks(rsi, lookback)
        rsi_troughs = TechnicalIndicators._find_troughs(rsi, lookback)
        
        # Bullish divergence: Lower price low, higher RSI low
        if len(price_troughs) >= 2 and len(rsi_troughs) >= 2:
            if (price[price_troughs[-1]] < price[price_troughs[-2]] and
                rsi[rsi_troughs[-1]] > rsi[rsi_troughs[-2]]):
                return {
                    'divergence': 'bullish',
                    'strength': abs(rsi[rsi_troughs[-1]] - rsi[rsi_troughs[-2]]),
                    'location': price_troughs[-1]
                }
        
        # Bearish divergence: Higher price high, lower RSI high
        if len(price_peaks) >= 2 and len(rsi_peaks) >= 2:
            if (price[price_peaks[-1]] > price[price_peaks[-2]] and
                rsi[rsi_peaks[-1]] < rsi[rsi_peaks[-2]]):
                return {
                    'divergence': 'bearish',
                    'strength': abs(rsi[rsi_peaks[-1]] - rsi[rsi_peaks[-2]]),
                    'location': price_peaks[-1]
                }
        
        return {'divergence': None}
    
    @staticmethod
    def _find_peaks(series: np.ndarray, window: int) -> List[int]:
        """Find peaks in series"""
        peaks = []
        for i in range(window, len(series) - window):
            if all(series[i] > series[i-j] for j in range(1, window+1)) and \
               all(series[i] > series[i+j] for j in range(1, window+1)):
                peaks.append(i)
        return peaks
    
    @staticmethod
    def _find_troughs(series: np.ndarray, window: int) -> List[int]:
        """Find troughs in series"""
        troughs = []
        for i in range(window, len(series) - window):
            if all(series[i] < series[i-j] for j in range(1, window+1)) and \
               all(series[i] < series[i+j] for j in range(1, window+1)):
                troughs.append(i)
        return troughs
    
    @staticmethod
    def detect_bb_squeeze(bb_width: pd.Series, threshold: float = 0.02) -> bool:
        """
        Detect Bollinger Bands squeeze
        
        Args:
            bb_width: BB width series
            threshold: Threshold for squeeze detection
            
        Returns:
            True if squeeze detected
        """
        if len(bb_width) < 20:
            return False
        
        current_width = bb_width.iloc[-1]
        avg_width = bb_width.rolling(20).mean().iloc[-1]
        
        return current_width < threshold and current_width < avg_width * 0.5
    
    @staticmethod
    def get_ema_trend(ema_dict: Dict[str, pd.Series]) -> str:
        """
        Determine trend based on EMA alignment
        
        Returns:
            'bullish', 'bearish', or 'neutral'
        """
        try:
            ema_9 = ema_dict['ema_9'].iloc[-1]
            ema_21 = ema_dict['ema_21'].iloc[-1]
            ema_50 = ema_dict['ema_50'].iloc[-1]
            ema_200 = ema_dict['ema_200'].iloc[-1]
            
            if ema_9 > ema_21 > ema_50 > ema_200:
                return 'bullish'
            elif ema_9 < ema_21 < ema_50 < ema_200:
                return 'bearish'
            else:
                return 'neutral'
        except:
            return 'neutral'
    
    @staticmethod
    def get_market_regime(df: pd.DataFrame, indicators: Dict[str, pd.Series]) -> Dict[str, Any]:
        """
        Classify current market regime
        
        Returns:
            Dict with regime classification
        """
        try:
            adx = indicators['adx'].iloc[-1]
            atr = indicators['atr_14'].iloc[-1]
            atr_sma = indicators['atr_14'].rolling(14).mean().iloc[-1]
            
            # Determine trend strength
            if adx > 25:
                trend_strength = 'strong'
            elif adx > 20:
                trend_strength = 'moderate'
            else:
                trend_strength = 'weak'
            
            # Determine volatility
            if atr > atr_sma * 1.5:
                volatility = 'high'
            elif atr > atr_sma:
                volatility = 'moderate'
            else:
                volatility = 'low'
            
            # Classify regime
            if trend_strength in ['strong', 'moderate']:
                if indicators['di_plus'].iloc[-1] > indicators['di_minus'].iloc[-1]:
                    regime = 'TRENDING_BULLISH'
                else:
                    regime = 'TRENDING_BEARISH'
            else:
                if volatility == 'high':
                    regime = 'RANGING_HIGH_VOL'
                else:
                    regime = 'RANGING_LOW_VOL'
            
            return {
                'regime': regime,
                'trend_strength': trend_strength,
                'volatility': volatility,
                'adx': adx,
                'atr': atr
            }
            
        except Exception as e:
            logger.error(f"Error determining market regime: {e}")
            return {'regime': 'UNKNOWN'}
```

# 🎫 Ticket #3.1.3: ICT Methodology Module
**Story Points:** 10  
**Priority:** P0  
**Status:** 🟡 IN PROGRESS  
**Assignee:** Backend Developer  
**Sprint:** Week 5, Days 3-5

## 📋 Description

Implement Inner Circle Trader (ICT) methodology detection system including killzones, liquidity sweeps, order flow analysis, and optimal trade entry (OTE) zones.

## 🎯 Acceptance Criteria

- [ ] **Killzone Detection**
  - Identify London killzone (02:00-05:00 EST)
  - Identify New York killzone (07:00-10:00 EST)
  - Identify Asian killzone (20:00-00:00 EST)
  - Detect current active killzone
  - Calculate killzone volatility scores

- [ ] **Liquidity Sweep Detection**
  - Detect sweep of Asian lows
  - Detect sweep of Asian highs
  - Detect sweep of previous day highs/lows
  - Identify stop hunts (false breakouts)
  - Calculate sweep strength

- [ ] **Order Flow Analysis**
  - Detect accumulation phases
  - Detect manipulation phases (stop hunts)
  - Detect distribution phases
  - Identify smart money footprints
  - Track order block mitigation

- [ ] **Optimal Trade Entry (OTE)**
  - Calculate 0.62-0.79 Fibonacci zone
  - Identify power of 3 setups
  - Detect breaker blocks
  - Identify mitigation blocks
  - Score OTE quality

- [ ] **Market Maker Model**
  - Detect AMD phases (Accumulation, Manipulation, Distribution)
  - Identify turtle soup patterns
  - Track failed auction areas
  - Detect engineered liquidity

- [ ] **Quality & Performance**
  - Unit tests with 80%+ coverage
  - Integration with SMC detector
  - Performance: <150ms for analysis
  - Real-time killzone tracking

## 📦 Deliverables

### File: `src/analysis/ict_detector.py`

```python
"""
Inner Circle Trader (ICT) Methodology Detector
Implements ICT concepts for institutional order flow analysis
"""
import pandas as pd
import numpy as np
from typing import Dict, Any, List, Optional, Tuple
from datetime import datetime, time, timedelta
from dataclasses import dataclass
from loguru import logger

@dataclass
class KillZone:
    """ICT Kill Zone structure"""
    name: str
    start_time: time
    end_time: time
    timezone: str = "EST"
    volatility_score: float = 0.0
    active: bool = False

@dataclass
class LiquiditySweep:
    """Liquidity sweep event"""
    type: str  # 'asian_low', 'asian_high', 'previous_day', etc.
    level: float
    sweep_price: float
    timestamp: pd.Timestamp
    strength: float  # How far beyond level
    reversed: bool  # Did price reverse after sweep?

@dataclass
class OrderFlowPhase:
    """Market maker phase"""
    phase: str  # 'accumulation', 'manipulation', 'distribution'
    start_time: pd.Timestamp
    end_time: Optional[pd.Timestamp]
    confidence: float

class ICTDetector:
    """
    ICT Methodology Pattern Detector
    
    Implements concepts from Inner Circle Trader methodology:
    - Kill Zones (optimal trading windows)
    - Liquidity Sweeps (stop hunts)
    - Order Flow (AMD model)
    - Optimal Trade Entry zones
    """
    
    # ICT Kill Zone definitions (EST)
    KILL_ZONES = {
        'london': KillZone('London Open', time(2, 0), time(5, 0)),
        'new_york': KillZone('New York Open', time(7, 0), time(10, 0)),
        'asian': KillZone('Asian Range', time(20, 0), time(0, 0)),
        'london_close': KillZone('London Close', time(10, 0), time(12, 0))
    }
    
    def __init__(self):
        self.liquidity_sweeps: List[LiquiditySweep] = []
        self.order_flow_phases: List[OrderFlowPhase] = []
        
    def analyze(self, df: pd.DataFrame) -> Dict[str, Any]:
        """
        Complete ICT analysis
        
        Args:
            df: DataFrame with OHLCV data and timezone info
            
        Returns:
            Dict with ICT analysis:
            {
                'killzone': Dict,
                'liquidity_sweeps': List[Dict],
                'order_flow': Dict,
                'ote_zones': Dict,
                'setup_quality': str,
                'confluence_score': float
            }
        """
        try:
            if len(df) < 50:
                logger.warning("Insufficient data for ICT analysis")
                return self._empty_result()
            
            logger.info(f"Starting ICT analysis on {len(df)} candles")
            start_time = datetime.now()
            
            # 1. Killzone Analysis
            killzone_data = self.analyze_killzone(df)
            
            # 2. Liquidity Sweep Detection
            sweeps = self.detect_liquidity_sweeps(df)
            
            # 3. Order Flow Analysis
            order_flow = self.analyze_order_flow(df)
            
            # 4. OTE Zone Calculation
            ote_zones = self.calculate_ote_zones(df)
            
            # 5. Setup Quality Assessment
            setup_quality = self.assess_setup_quality(
                killzone_data, sweeps, order_flow, ote_zones
            )
            
            # 6. Calculate overall confluence score
            confluence_score = self._calculate_confluence_score(
                killzone_data, sweeps, order_flow, ote_zones
            )
            
            elapsed = (datetime.now() - start_time).total_seconds() * 1000
            logger.info(f"✅ ICT analysis complete in {elapsed:.0f}ms")
            
            return {
                'killzone': killzone_data,
                'liquidity_sweeps': sweeps,
                'order_flow': order_flow,
                'ote_zones': ote_zones,
                'setup_quality': setup_quality,
                'confluence_score': round(confluence_score, 3),
                'analysis_timestamp': datetime.utcnow().isoformat(),
                'performance_ms': round(elapsed, 2)
            }
            
        except Exception as e:
            logger.error(f"❌ Error in ICT analysis: {e}", exc_info=True)
            return self._empty_result()
    
    def analyze_killzone(self, df: pd.DataFrame) -> Dict[str, Any]:
        """
        Analyze which killzone is currently active
        and historical killzone performance
        """
        current_time = datetime.now()
        
        # Determine active killzone
        active_kz = None
        for name, kz in self.KILL_ZONES.items():
            if self._is_time_in_killzone(current_time.time(), kz):
                active_kz = name
                kz.active = True
                break
        
        # Calculate killzone statistics
        kz_stats = {}
        for name, kz in self.KILL_ZONES.items():
            # Get candles in this killzone
            kz_candles = self._filter_by_killzone(df, kz)
            
            if len(kz_candles) > 0:
                # Calculate volatility score
                avg_range = (kz_candles['high'] - kz_candles['low']).mean()
                overall_avg = (df['high'] - df['low']).mean()
                volatility_score = (avg_range / overall_avg) if overall_avg > 0 else 1.0
                
                kz_stats[name] = {
                    'active': kz.active,
                    'volatility_score': round(volatility_score, 3),
                    'avg_range': float(avg_range),
                    'candle_count': len(kz_candles),
                    'time_window': f"{kz.start_time.strftime('%H:%M')}-{kz.end_time.strftime('%H:%M')} {kz.timezone}"
                }
            else:
                kz_stats[name] = {
                    'active': kz.active,
                    'volatility_score': 0.0,
                    'avg_range': 0.0,
                    'candle_count': 0,
                    'time_window': f"{kz.start_time.strftime('%H:%M')}-{kz.end_time.strftime('%H:%M')} {kz.timezone}"
                }
        
        return {
            'current_killzone': active_kz or 'none',
            'killzone_stats': kz_stats,
            'optimal_for_trading': active_kz in ['london', 'new_york'],
            'recommendation': self._get_killzone_recommendation(active_kz)
        }
    
    def _is_time_in_killzone(self, current: time, kz: KillZone) -> bool:
        """Check if current time is within killzone"""
        if kz.start_time < kz.end_time:
            return kz.start_time <= current <= kz.end_time
        else:  # Crosses midnight
            return current >= kz.start_time or current <= kz.end_time
    
    def _filter_by_killzone(self, df: pd.DataFrame, kz: KillZone) -> pd.DataFrame:
        """Filter DataFrame to killzone hours"""
        if not hasattr(df.index, 'hour'):
            return pd.DataFrame()
        
        if kz.start_time < kz.end_time:
            mask = (df.index.hour >= kz.start_time.hour) & (df.index.hour < kz.end_time.hour)
        else:
            mask = (df.index.hour >= kz.start_time.hour) | (df.index.hour < kz.end_time.hour)
        
        return df[mask]
    
    def _get_killzone_recommendation(self, active_kz: Optional[str]) -> str:
        """Get trading recommendation based on killzone"""
        if active_kz == 'london':
            return "HIGH - London killzone active, expect strong directional moves"
        elif active_kz == 'new_york':
            return "HIGH - NY killzone active, highest liquidity and volatility"
        elif active_kz == 'asian':
            return "LOW - Asian range, typically consolidation phase"
        else:
            return "MEDIUM - Outside primary killzones, wait for setup confirmation"
    
    def detect_liquidity_sweeps(self, df: pd.DataFrame, lookback: int = 50) -> List[Dict[str, Any]]:
        """
        Detect liquidity sweeps (stop hunts)
        
        A liquidity sweep occurs when:
        1. Price briefly breaks a key level (swing high/low)
        2. Triggers stop losses
        3. Quickly reverses direction
        """
        sweeps = []
        
        # Get Asian session range (if available)
        asian_high, asian_low = self._get_asian_range(df)
        
        # Get previous day high/low
        prev_day_high, prev_day_low = self._get_previous_day_range(df)
        
        # Find swing highs and lows
        swing_highs = self._find_swing_points(df, 'high', period=10)
        swing_lows = self._find_swing_points(df, 'low', period=10)
        
        # Check for sweeps in recent candles
        recent_df = df.iloc[-lookback:]
        
        for i in range(len(recent_df)):
            candle = recent_df.iloc[i]
            
            # Check Asian Low Sweep
            if asian_low and candle['low'] < asian_low:
                # Did it reverse?
                if i < len(recent_df) - 1:
                    next_candle = recent_df.iloc[i + 1]
                    if next_candle['close'] > asian_low:
                        sweep_strength = abs(candle['low'] - asian_low) / asian_low
                        sweeps.append({
                            'type': 'asian_low_sweep',
                            'level': float(asian_low),
                            'sweep_price': float(candle['low']),
                            'timestamp': str(candle.name),
                            'strength': round(sweep_strength * 100, 3),
                            'reversed': True,
                            'significance': 'high'
                        })
            
            # Check Asian High Sweep
            if asian_high and candle['high'] > asian_high:
                if i < len(recent_df) - 1:
                    next_candle = recent_df.iloc[i + 1]
                    if next_candle['close'] < asian_high:
                        sweep_strength = abs(candle['high'] - asian_high) / asian_high
                        sweeps.append({
                            'type': 'asian_high_sweep',
                            'level': float(asian_high),
                            'sweep_price': float(candle['high']),
                            'timestamp': str(candle.name),
                            'strength': round(sweep_strength * 100, 3),
                            'reversed': True,
                            'significance': 'high'
                        })
            
            # Check Previous Day Low Sweep
            if prev_day_low and candle['low'] < prev_day_low:
                if i < len(recent_df) - 1:
                    next_candle = recent_df.iloc[i + 1]
                    if next_candle['close'] > prev_day_low:
                        sweep_strength = abs(candle['low'] - prev_day_low) / prev_day_low
                        sweeps.append({
                            'type': 'previous_day_low_sweep',
                            'level': float(prev_day_low),
                            'sweep_price': float(candle['low']),
                            'timestamp': str(candle.name),
                            'strength': round(sweep_strength * 100, 3),
                            'reversed': True,
                            'significance': 'medium'
                        })
            
            # Check swing high sweeps
            for swing in swing_highs[-5:]:
                if candle['high'] > swing['price']:
                    if i < len(recent_df) - 1:
                        next_candle = recent_df.iloc[i + 1]
                        if next_candle['close'] < swing['price']:
                            sweep_strength = abs(candle['high'] - swing['price']) / swing['price']
                            sweeps.append({
                                'type': 'swing_high_sweep',
                                'level': float(swing['price']),
                                'sweep_price': float(candle['high']),
                                'timestamp': str(candle.name),
                                'strength': round(sweep_strength * 100, 3),
                                'reversed': True,
                                'significance': 'medium'
                            })
        
        # Sort by significance and recency
        sweeps.sort(key=lambda x: (
            {'high': 3, 'medium': 2, 'low': 1}[x['significance']],
            -len(df) + df.index.get_loc(pd.Timestamp(x['timestamp']))
        ), reverse=True)
        
        return sweeps[:10]  # Top 10 most significant
    
    def _get_asian_range(self, df: pd.DataFrame) -> Tuple[Optional[float], Optional[float]]:
        """Get Asian session high and low"""
        asian_kz = self.KILL_ZONES['asian']
        asian_candles = self._filter_by_killzone(df.iloc[-100:], asian_kz)
        
        if len(asian_candles) > 0:
            return asian_candles['high'].max(), asian_candles['low'].min()
        return None, None
    
    def _get_previous_day_range(self, df: pd.DataFrame) -> Tuple[Optional[float], Optional[float]]:
        """Get previous day high and low"""
        if len(df) < 24:
            return None, None
        
        yesterday = df.iloc[-48:-24]  # Assuming hourly data
        return yesterday['high'].max(), yesterday['low'].min()
    
    def _find_swing_points(self, df: pd.DataFrame, column: str, period: int = 10) -> List[Dict]:
        """Find swing highs or lows"""
        swings = []
        
        for i in range(period, len(df) - period):
            value = df[column].iloc[i]
            
            if column == 'high':
                is_swing = all(
                    value >= df[column].iloc[j]
                    for j in range(i - period, i + period + 1) if j != i
                )
            else:  # low
                is_swing = all(
                    value <= df[column].iloc[j]
                    for j in range(i - period, i + period + 1) if j != i
                )
            
            if is_swing:
                swings.append({
                    'price': float(value),
                    'index': i,
                    'timestamp': df.index[i]
                })
        
        return swings
    
    def analyze_order_flow(self, df: pd.DataFrame) -> Dict[str, Any]:
        """
        Analyze order flow using AMD model:
        - Accumulation: Smart money buying
        - Manipulation: Stop hunts, fake moves
        - Distribution: Smart money selling
        """
        if len(df) < 30:
            return {'phase': 'unknown', 'confidence': 0.0}
        
        recent = df.iloc[-30:]
        
        # Calculate metrics
        price_range = recent['high'].max() - recent['low'].min()
        volume_trend = recent['volume'].rolling(5).mean().iloc[-1] / recent['volume'].rolling(5).mean().iloc[-10]
        
        # Detect consolidation (accumulation/distribution)
        is_consolidating = price_range / recent['close'].mean() < 0.05  # <5% range
        
        # Detect manipulation (wicks, reversals)
        recent_wicks = []
        for i in range(len(recent)):
            candle = recent.iloc[i]
            upper_wick = candle['high'] - max(candle['open'], candle['close'])
            lower_wick = min(candle['open'], candle['close']) - candle['low']
            body = abs(candle['close'] - candle['open'])
            
            if body > 0:
                wick_ratio = max(upper_wick, lower_wick) / body
                recent_wicks.append(wick_ratio)
        
        avg_wick_ratio = np.mean(recent_wicks) if recent_wicks else 0
        has_manipulation = avg_wick_ratio > 2.0  # Large wicks indicate manipulation
        
        # Detect distribution/accumulation
        price_trend = recent['close'].iloc[-1] / recent['close'].iloc[0]
        
        # Classify phase
        if is_consolidating and volume_trend > 1.2:
            if price_trend > 1.01:
                phase = 'accumulation'
                confidence = 0.75
            else:
                phase = 'distribution'
                confidence = 0.75
        elif has_manipulation:
            phase = 'manipulation'
            confidence = 0.80
        elif price_trend > 1.05:
            phase = 'markup'
            confidence = 0.70
        elif price_trend < 0.95:
            phase = 'markdown'
            confidence = 0.70
        else:
            phase = 'neutral'
            confidence = 0.50
        
        return {
            'phase': phase,
            'confidence': round(confidence, 3),
            'details': {
                'consolidating': is_consolidating,
                'manipulation_detected': has_manipulation,
                'volume_trend': round(volume_trend, 3),
                'price_trend': round((price_trend - 1) * 100, 2),
                'avg_wick_ratio': round(avg_wick_ratio, 2)
            },
            'interpretation': self._interpret_order_flow(phase)
        }
    
    def _interpret_order_flow(self, phase: str) -> str:
        """Provide interpretation of order flow phase"""
        interpretations = {
            'accumulation': "Smart money buying, expect markup. Look for long entries.",
            'manipulation': "Stop hunts active, wait for clear direction. Risk of false breakouts.",
            'distribution': "Smart money selling, expect markdown. Look for short entries.",
            'markup': "Bullish trend continuation, buy pullbacks to demand.",
            'markdown': "Bearish trend continuation, sell rallies to supply.",
            'neutral': "No clear institutional activity, wait for setup."
        }
        return interpretations.get(phase, "Unknown phase")
    
    def calculate_ote_zones(self, df: pd.DataFrame) -> Dict[str, Any]:
        """
        Calculate Optimal Trade Entry (OTE) zones
        OTE = 0.62 to 0.79 Fibonacci retracement zone
        """
        if len(df) < 50:
            return {}
        
        recent = df.iloc[-50:]
        
        # Find swing high and low
        swing_high = recent['high'].max()
        swing_low = recent['low'].min()
        range_size = swing_high - swing_low
        
        if range_size == 0:
            return {}
        
        # Calculate OTE zones
        ote_low = swing_low + (range_size * 0.62)
        ote_high = swing_low + (range_size * 0.79)
        
        # Determine if current price is in OTE
        current_price = df['close'].iloc[-1]
        in_ote_zone = ote_low <= current_price <= ote_high
        
        # Bullish or bearish OTE?
        if current_price < (swing_high + swing_low) / 2:
            ote_bias = 'bullish'  # In discount, expect up
        else:
            ote_bias = 'bearish'  # In premium, expect down
        
        return {
            'ote_low': float(ote_low),
            'ote_high': float(ote_high),
            'ote_midpoint': float((ote_low + ote_high) / 2),
            'swing_high': float(swing_high),
            'swing_low': float(swing_low),
            'current_price': float(current_price),
            'in_ote_zone': in_ote_zone,
            'bias': ote_bias,
            'distance_to_ote': round(abs(current_price - (ote_low + ote_high) / 2) / current_price * 100, 2)
        }
    
    def assess_setup_quality(
        self,
        killzone: Dict,
        sweeps: List[Dict],
        order_flow: Dict,
        ote: Dict
    ) -> str:
        """
        Assess overall ICT setup quality
        
        Returns: 'excellent', 'good', 'fair', 'poor'
        """
        score = 0
        
        # Killzone scoring (+3)
        if killzone['current_killzone'] in ['london', 'new_york']:
            score += 3
        elif killzone['current_killzone'] == 'london_close':
            score += 2
        
        # Liquidity sweep scoring (+3)
        recent_sweeps = [s for s in sweeps if s['reversed']]
        if len(recent_sweeps) > 0:
            if any(s['significance'] == 'high' for s in recent_sweeps):
                score += 3
            else:
                score += 2
        
        # Order flow scoring (+2)
        if order_flow['phase'] in ['accumulation', 'distribution']:
            if order_flow['confidence'] > 0.7:
                score += 2
            else:
                score += 1
        
        # OTE scoring (+2)
        if ote.get('in_ote_zone'):
            score += 2
        elif ote.get('distance_to_ote', 100) < 5:  # Within 5%
            score += 1
        
        # Quality classification
        if score >= 8:
            return 'excellent'
        elif score >= 6:
            return 'good'
        elif score >= 4:
            return 'fair'
        else:
            return 'poor'
    
    def _calculate_confluence_score(
        self,
        killzone: Dict,
        sweeps: List[Dict],
        order_flow: Dict,
        ote: Dict
    ) -> float:
        """Calculate overall confluence score (0-1)"""
        score = 0.0
        
        # Killzone (0.25 max)
        if killzone['current_killzone'] in ['london', 'new_york']:
            score += 0.25
        elif killzone['current_killzone'] == 'london_close':
            score += 0.15
        
        # Liquidity sweeps (0.30 max)
        high_sig_sweeps = [s for s in sweeps if s['significance'] == 'high' and s['reversed']]
        if len(high_sig_sweeps) > 0:
            score += 0.30
        elif len(sweeps) > 0:
            score += 0.15
        
        # Order flow (0.25 max)
        if order_flow['phase'] in ['accumulation', 'distribution']:
            score += order_flow['confidence'] * 0.25
        
        # OTE (0.20 max)
        if ote.get('in_ote_zone'):
            score += 0.20
        elif ote.get('distance_to_ote', 100) < 10:
            score += 0.10
        
        return min(score, 1.0)
    
    def _empty_result(self) -> Dict[str, Any]:
        """Return empty result structure"""
        return {
            'killzone': {'current_killzone': 'none', 'killzone_stats': {}},
            'liquidity_sweeps': [],
            'order_flow': {'phase': 'unknown', 'confidence': 0.0},
            'ote_zones': {},
            'setup_quality': 'poor',
            'confluence_score': 0.0
        }
```

### File: `tests/unit/test_ict_detector.py`

```python
"""
Unit tests for ICT Detector
"""
import pytest
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from src.analysis.ict_detector import ICTDetector

@pytest.fixture
def sample_data():
    """Generate sample OHLCV data"""
    dates = pd.date_range(start='2024-01-01', periods=100, freq='1H')
    
    # Create realistic price movement
    np.random.seed(42)
    base_price = 43000
    
    data = []
    for i, date in enumerate(dates):
        # Add some trend and volatility
        trend = (i / 100) * 1000
        volatility = np.random.randn() * 100
        
        close = base_price + trend + volatility
        high = close + abs(np.random.randn() * 50)
        low = close - abs(np.random.randn() * 50)
        open_price = close + np.random.randn() * 30
        volume = 1000 + np.random.randint(-200, 200)
        
        data.append({
            'timestamp': date,
            'open': max(low, open_price),
            'high': high,
            'low': low,
            'close': close,
            'volume': volume
        })
    
    df = pd.DataFrame(data)
    df.set_index('timestamp', inplace=True)
    return df

@pytest.mark.asyncio
async def test_ict_detector_initialization():
    """Test ICT detector initializes correctly"""
    detector = ICTDetector()
    assert len(detector.KILL_ZONES) == 4
    assert 'london' in detector.KILL_ZONES
    assert 'new_york' in detector.KILL_ZONES

@pytest.mark.asyncio
async def test_killzone_detection(sample_data):
    """Test killzone identification"""
    detector = ICTDetector()
    result = detector.analyze_killzone(sample_data)
    
    assert 'current_killzone' in result
    assert 'killzone_stats' in result
    assert 'optimal_for_trading' in result

@pytest.mark.asyncio
async def test_liquidity_sweep_detection(sample_data):
    """Test liquidity sweep detection"""
    detector = ICTDetector()
    sweeps = detector.detect_liquidity_sweeps(sample_data)
    
    assert isinstance(sweeps, list)
    if len(sweeps) > 0:
        sweep = sweeps[0]
        assert 'type' in sweep
        assert 'level' in sweep
        assert 'strength' in sweep

@pytest.mark.asyncio
async def test_order_flow_analysis(sample_data):
    """Test order flow phase detection"""
    detector = ICTDetector()
    flow = detector.analyze_order_flow(sample_data)
    
    assert 'phase' in flow
    assert 'confidence' in flow
    assert flow['phase'] in ['accumulation', 'manipulation', 'distribution', 'markup', 'markdown', 'neutral']
    assert 0 <= flow['confidence'] <= 1

@pytest.mark.asyncio
async def test_ote_zone_calculation(sample_data):
    """Test OTE zone calculation"""
    detector = ICTDetector()
    ote = detector.calculate_ote_zones(sample_data)
    
    assert 'ote_low' in ote
    assert 'ote_high' in ote
    assert 'bias' in ote
    assert ote['ote_high'] > ote['ote_low']

@pytest.mark.asyncio
async def test_complete_ict_analysis(sample_data):
    """Test complete ICT analysis"""
    detector = ICTDetector()
    result = detector.analyze(sample_data)
    
    assert 'killzone' in result
    assert 'liquidity_sweeps' in result
    assert 'order_flow' in result
    assert 'ote_zones' in result
    assert 'setup_quality' in result
    assert 'confluence_score' in result
    
    # Check performance
    assert result['performance_ms'] < 200

@pytest.mark.asyncio
async def test_setup_quality_assessment(sample_data):
    """Test setup quality classification"""
    detector = ICTDetector()
    result = detector.analyze(sample_data)
    
    assert result['setup_quality'] in ['excellent', 'good', 'fair', 'poor']
    assert 0 <= result['confluence_score'] <= 1
```

---

# 🎫 Ticket #3.1.4: Pattern Recognition Module
**Story Points:** 6  
**Priority:** P1 (High)  
**Status:** 🟡 IN PROGRESS  
**Assignee:** Backend Developer  
**Sprint:** Week 5, Day 5

## 📋 Description

Implement chart pattern recognition for common technical patterns (Head & Shoulders, Triangles, Wedges, Flags, Channels, etc.)

## 🎯 Acceptance Criteria

- [ ] **Classic Patterns**
  - Head and Shoulders (bullish/bearish)
  - Double Top/Bottom
  - Triple Top/Bottom
  - Ascending/Descending Triangles
  - Symmetrical Triangles
  
- [ ] **Continuation Patterns**
  - Bull/Bear Flags
  - Pennants
  - Wedges (rising/falling)
  - Rectangles
  
- [ ] **Channel Detection**
  - Parallel channels
  - Trend lines
  - Support/Resistance levels
  
- [ ] **Pattern Validation**
  - Confidence scoring
  - Volume confirmation
  - Breakout detection
  - Target projection
  
- [ ] **Quality**
  - Unit tests >80% coverage
  - Performance <100ms
  - Integration with analysis agent

## 📦 Deliverables

### File: `src/analysis/pattern_recognition.py`

```python
"""
Chart Pattern Recognition Module
Identifies classical technical analysis patterns
"""
import pandas as pd
import numpy as np
from typing import Dict, Any, List, Optional, Tuple
from dataclasses import dataclass
from scipy.signal import find_peaks, argrelextrema
from loguru import logger

@dataclass
class Pattern:
    """Chart pattern structure"""
    type: str
    name: str
    direction: str  # 'bullish' or 'bearish'
    confidence: float
    start_index: int
    end_index: int
    key_levels: Dict[str, float]
    target: Optional[float] = None
    invalidation: Optional[float] = None

class PatternRecognizer:
    """
    Classical chart pattern recognition
    """
    
    def __init__(self):
        self.patterns_found: List[Pattern] = []
        
    def analyze(self, df: pd.DataFrame) -> Dict[str, Any]:
        """
        Complete pattern recognition analysis
        
        Returns:
            Dict with all detected patterns and their details
        """
        try:
            if len(df) < 30:
                logger.warning("Insufficient data for pattern recognition")
                return {'patterns': [], 'count': 0}
            
            logger.info("Starting pattern recognition")
            
            patterns = []
            
            # Detect reversal patterns
            patterns.extend(self.detect_head_and_shoulders(df))
            patterns.extend(self.detect_double_top_bottom(df))
            
            # Detect continuation patterns
            patterns.extend(self.detect_flags(df))
            patterns.extend(self.detect_triangles(df))
            
            # Detect channels
            channels = self.detect_channels(df)
            
            # Sort by confidence
            patterns.sort(key=lambda x: x.confidence, reverse=True)
            
            return {
                'patterns': [self._pattern_to_dict(p) for p in patterns[:10]],
                'channels': channels,
                'count': len(patterns),
                'most_recent': self._pattern_to_dict(patterns[0]) if patterns else None
            }
            
        except Exception as e:
            logger.error(f"Error in pattern recognition: {e}", exc_info=True)
            return {'patterns': [], 'count': 0}
    
    def detect_head_and_shoulders(self, df: pd.DataFrame) -> List[Pattern]:
        """Detect Head and Shoulders patterns"""
        patterns = []
        
        # Find peaks (potential shoulders and head)
        peaks_idx = argrelextrema(df['high'].values, np.greater, order=5)[0]
        
        if len(peaks_idx) < 3:
            return patterns
        
        # Check for H&S formation
        for i in range(len(peaks_idx) - 2):
            left_shoulder_idx = peaks_idx[i]
            head_idx = peaks_idx[i + 1]
            right_shoulder_idx = peaks_idx[i + 2]
            
            left_shoulder = df['high'].iloc[left_shoulder_idx]
            head = df['high'].iloc[head_idx]
            right_shoulder = df['high'].iloc[right_shoulder_idx]
            
            # H&S criteria: head > shoulders, shoulders roughly equal
            if (head > left_shoulder and head > right_shoulder):
                shoulder_diff = abs(left_shoulder - right_shoulder) / left_shoulder
                
                if shoulder_diff < 0.03:  # Shoulders within 3%
                    # Find neckline (lowest low between shoulders)
                    neckline_range = df.iloc[left_shoulder_idx:right_shoulder_idx + 1]
                    neckline = neckline_range['low'].min()
                    
                    # Calculate target (head to neckline distance projected down)
                    pattern_height = head - neckline
                    target = neckline - pattern_height
                    
                    confidence = 0.7 + (0.3 * (1 - shoulder_diff))
                    
                    patterns.append(Pattern(
                        type='reversal',
                        name='Head and Shoulders',
                        direction='bearish',
                        confidence=confidence,
                        start_index=left_shoulder_idx,
                        end_index=right_shoulder_idx,
                        key_levels={
                            'left_shoulder': float(left_shoulder),
                            'head': float(head),
                            'right_shoulder': float(right_shoulder),
                            'neckline': float(neckline)
                        },
                        target=float(target),
                        invalidation=float(head)
                    ))
        
        # Inverse H&S (bullish)
        troughs_idx = argrelextrema(df['low'].values, np.less, order=5)[0]
        
        if len(troughs_idx) < 3:
            return patterns
        
        for i in range(len(troughs_idx) - 2):
            left_shoulder_idx = troughs_idx[i]
            head_idx = troughs_idx[i + 1]
            right_shoulder_idx = troughs_idx[i + 2]
            
            left_shoulder = df['low'].iloc[left_shoulder_idx]
            head = df['low'].iloc[head_idx]
            right_shoulder = df['low'].iloc[right_shoulder_idx]
            
            if (head < left_shoulder and head < right_shoulder):
                shoulder_diff = abs(left_shoulder - right_shoulder) / left_shoulder
                
                if shoulder_diff < 0.03:
                    neckline_range = df.iloc[left_shoulder_idx:right_shoulder_idx + 1]
                    neckline = neckline_range['high'].max()
                    
                    pattern_height = neckline - head
                    target = neckline + pattern_height
                    
                    confidence = 0.7 + (0.3 * (1 - shoulder_diff))
                    
                    patterns.append(Pattern(
                        type='reversal',
                        name='Inverse Head and Shoulders',
                        direction='bullish',
                        confidence=confidence,
                        start_index=left_shoulder_idx,
                        end_index=right_shoulder_idx,
                        key_levels={
                            'left_shoulder': float(left_shoulder),
                            'head': float(head),
                            'right_shoulder': float(right_shoulder),
                            'neckline': float(neckline)
                        },
                        target=float(target),
                        invalidation=float(head)
                    ))
        
        return patterns
    
    def detect_double_top_bottom(self, df: pd.DataFrame) -> List[Pattern]:
        """Detect Double Top and Double Bottom patterns"""
        patterns = []
        
        # Double Top (bearish)
        peaks_idx = argrelextrema(df['high'].values, np.greater, order=5)[0]
        
        if len(peaks_idx) >= 2:
            for i in range(len(peaks_idx) - 1):
                first_peak_idx = peaks_idx[i]
                second_peak_idx = peaks_idx[i + 1]
                
                first_peak = df['high'].iloc[first_peak_idx]
                second_peak = df['high'].iloc[second_peak_idx]
                
                # Check if peaks are roughly equal (within 2%)
                peak_diff = abs(first_peak - second_peak) / first_peak
                
                if peak_diff < 0.02:
                    # Find trough between peaks
                    between = df.iloc[first_peak_idx:second_peak_idx + 1]
                    trough = between['low'].min()
                    
                    pattern_height = first_peak - trough
                    target = trough - pattern_height
                    
                    confidence = 0.75 + (0.25 * (1 - peak_diff))
                    
                    patterns.append(Pattern(
                        type='reversal',
                        name='Double Top',
                        direction='bearish',
                        confidence=confidence,
                        start_index=first_peak_idx,
                        end_index=second_peak_idx,
                        key_levels={
                            'first_peak': float(first_peak),
                            'second_peak': float(second_peak),
                            'support': float(trough)
                        },
                        target=float(target),
                        invalidation=float(max(first_peak, second_peak))
                    ))
        
        # Double Bottom (bullish)
        troughs_idx = argrelextrema(df['low'].values, np.less, order=5)[0]
        
        if len(troughs_idx) >= 2:
            for i in range(len(troughs_idx) - 1):
                first_trough_idx = troughs_idx[i]
                second_trough_idx = troughs_idx[i + 1]
                
                first_trough = df['low'].iloc[first_trough_idx]
                second_trough = df['low'].iloc[second_trough_idx]
                
                trough_diff = abs(first_trough - second_trough) / first_trough
                
                if trough_diff < 0.02:
                    between = df.iloc[first_trough_idx:second_trough_idx + 1]
                    peak = between['high'].max()
                    
                    pattern_height = peak - first_trough
                    target = peak + pattern_height
                    
                    confidence = 0.75 + (0.25 * (1 - trough_diff))
                    
                    patterns.append(Pattern(
                        type='reversal',
                        name='Double Bottom',
                        direction='bullish',
                        confidence=confidence,
                        start_index=first_trough_idx,
                        end_index=second_trough_idx,
                        key_levels={
                            'first_bottom': float(first_trough),
                            'second_bottom': float(second_trough),
                            'resistance': float(peak)
                        },
                        target=float(target),
                        invalidation=float(min(first_trough, second_trough))
                    ))
        
        return patterns
    
    def detect_flags(self, df: pd.DataFrame, lookback: int = 30) -> List[Pattern]:
        """Detect Bull and Bear Flag patterns"""
        patterns = []
        
        if len(df) < lookback:
            return patterns
        
        recent = df.iloc[-lookback:]
        
        # Bull Flag: Strong uptrend followed by consolidation
        # Check for strong move up
        initial_price = recent['close'].iloc[0]
        highest = recent['high'].max()
        move_up = (highest - initial_price) / initial_price
        
        if move_up > 0.05:  # >5% move
            # Check for consolidation
            consolidation_start = recent['high'].idxmax()
            consolidation_idx = recent.index.get_loc(consolidation_start)
            
            if consolidation_idx < len(recent) - 5:
                consolidation = recent.iloc[consolidation_idx:]
                
                # Check if consolidating (range < 3%)
                cons_range = (consolidation['high'].max() - consolidation['low'].min()) / consolidation['close'].mean()
                
                if cons_range < 0.03:
                    target = highest + (highest - initial_price) * 0.5
                    
                    patterns.append(Pattern(
                        type='continuation',
                        name='Bull Flag',
                        direction='bullish',
                        confidence=0.70,
                        start_index=0,
                        end_index=len(recent) - 1,
                        key_levels={
                            'flagpole_bottom': float(initial_price),
                            'flagpole_top': float(highest),
                            'consolidation_support': float(consolidation['low'].min())
                        },
                        target=float(target),
                        invalidation=float(consolidation['low'].min())
                    ))
        
        # Bear Flag: Strong downtrend followed by consolidation
        lowest = recent['low'].min()
        move_down = (initial_price - lowest) / initial_price
        
        if move_down > 0.05:
            consolidation_start = recent['low'].idxmin()
            consolidation_idx = recent.index.get_loc(consolidation_start)
            
            if consolidation_idx < len(recent) - 5:
                consolidation = recent.iloc[consolidation_idx:]
                
                cons_range = (consolidation['high'].max() - consolidation['low'].min()) / consolidation['close'].mean()
                
                if cons_range < 0.03:
                    target = lowest - (initial_price - lowest) * 0.5
                    
                    patterns.append(Pattern(
                        type='continuation',
                        name='Bear Flag',
                        direction='bearish',
                        confidence=0.70,
                        start_index=0,
                        end_index=len(recent) - 1,
                        key_levels={
                            'flagpole_top': float(initial_price),
                            'flagpole_bottom': float(lowest),
                            'consolidation_resistance': float(consolidation['high'].max())
                        },
                        target=float(target),
                        invalidation=float(consolidation['high'].max())
                    ))
        
        return patterns
    
    def detect_triangles(self, df: pd.DataFrame, lookback: int = 50) -> List[Pattern]:
        """Detect Triangle patterns (Ascending, Descending, Symmetrical)"""
        patterns = []
        
        if len(df) < lookback:
            return patterns
        
        recent = df.iloc[-lookback:]
        
        # Find swing highs and lows
        highs = argrelextrema(recent['high'].values, np.greater, order=3)[0]
        lows = argrelextrema(recent['low'].values, np.less, order=3)[0]
        
        if len(highs) < 3 or len(lows) < 3:
            return patterns
        
        # Analyze high trendline
        high_prices = recent['high'].iloc[highs].values
        high_slope = np.polyfit(highs, high_prices, 1)[0]
        
        # Analyze low trendline
        low_prices = recent['low'].iloc[lows].values
        low_slope = np.polyfit(lows, low_prices, 1)[0]
        
        # Classify triangle type
        if abs(high_slope) < 0.5 and low_slope > 1:
            # Ascending triangle (bullish)
            resistance = np.mean(high_prices)
            support_start = low_prices[0]
            support_end = low_prices[-1]
            
            patterns.append(Pattern(
                type='continuation',
                name='Ascending Triangle',
                direction='bullish',
                confidence=0.75,
                start_index=len(df) - lookback,
                end_index=len(df) - 1,
                key_levels={
                    'resistance': float(resistance),
                    'support_start': float(support_start),
                    'support_end': float(support_end)
                },
                target=float(resistance + (resistance - support_start)),
                invalidation=float(support_end)
            ))
        
        elif high_slope < -1 and abs(low_slope) < 0.5:
            # Descending triangle (bearish)
            support = np.mean(low_prices)
            resistance_start = high_prices[0]
            resistance_end = high_prices[-1]
            
            patterns.append(Pattern(
                type='continuation',
                name='Descending Triangle',
                direction='bearish',
                confidence=0.75,
                start_index=len(df) - lookback,
                end_index=len(df) - 1,
                key_levels={
                    'support': float(support),
                    'resistance_start': float(resistance_start),
                    'resistance_end': float(resistance_end)
                },
                target=float(support - (resistance_start - support)),
                invalidation=float(resistance_end)
            ))
        
        elif high_slope < -0.5 and low_slope > 0.5:
            # Symmetrical triangle (neutral, awaits breakout)
            apex_price = (high_prices[-1] + low_prices[-1]) / 2
            
            patterns.append(Pattern(
                type='continuation',
                name='Symmetrical Triangle',
                direction='neutral',
                confidence=0.65,
                start_index=len(df) - lookback,
                end_index=len(df) - 1,
                key_levels={
                    'apex': float(apex_price),
                    'resistance_slope': float(high_slope),
                    'support_slope': float(low_slope)
                },
                target=None,
                invalidation=None
            ))
        
        return patterns
    
    def detect_channels(self, df: pd.DataFrame, lookback: int = 50) -> Dict[str, Any]:
        """Detect price channels"""
        if len(df) < lookback:
            return {'channels': []}
        
        recent = df.iloc[-lookback:]
        
        # Linear regression on highs and lows
        x = np.arange(len(recent))
        
        # Upper channel (resistance)
        highs = recent['high'].values
        upper_coef = np.polyfit(x, highs, 1)
        upper_line = np.poly1d(upper_coef)
        
        # Lower channel (support)
        lows = recent['low'].values
        lower_coef = np.polyfit(x, lows, 1)
        lower_line = np.poly1d(lower_coef)
        
        # Check if parallel (similar slopes)
        slope_diff = abs(upper_coef[0] - lower_coef[0])
        
        if slope_diff < 1.0:
            channel_type = 'parallel'
            if upper_coef[0] > 0.5:
                direction = 'ascending'
            elif upper_coef[0] < -0.5:
                direction = 'descending'
            else:
                direction = 'horizontal'
            
            current_price = df['close'].iloc[-1]
            upper_level = upper_line(len(recent) - 1)
            lower_level = lower_line(len(recent) - 1)
            
            # Position in channel
            channel_position = (current_price - lower_level) / (upper_level - lower_level)
            
            return {
                'channels': [{
                    'type': channel_type,
                    'direction': direction,
                    'upper_level': float(upper_level),
                    'lower_level': float(lower_level),
                    'channel_width': float(upper_level - lower_level),
                    'current_position': round(channel_position * 100, 1),  # %
                    'slope': float(upper_coef[0])
                }]
            }
        
        return {'channels': []}
    
    def _pattern_to_dict(self, pattern: Pattern) -> Dict[str, Any]:
        """Convert Pattern object to dictionary"""
        return {
            'type': pattern.type,
            'name': pattern.name,
            'direction': pattern.direction,
            'confidence': round(pattern.confidence, 3),
            'key_levels': pattern.key_levels,
            'target': pattern.target,
            'invalidation': pattern.invalidation
        }
```

---

