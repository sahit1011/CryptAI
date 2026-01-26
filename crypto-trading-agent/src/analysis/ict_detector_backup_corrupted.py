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

            # 5. Silver Bullet Detection (Professional Enhancement)
            silver_bullet = self.detect_silver_bullet(df, sweeps)

            # 6. Setup Quality Assessment
            setup_quality = self.assess_setup_quality(
                killzone_data, sweeps, order_flow, ote_zones, silver_bullet
            )

            # 7. Calculate overall confluence score
            confluence_score = self._calculate_confluence_score(
                killzone_data, sweeps, order_flow, ote_zones, silver_bullet
            )

            elapsed = (datetime.now() - start_time).total_seconds() * 1000
            logger.info(f"✅ ICT analysis complete in {elapsed:.0f}ms")

            return {
                'killzone': killzone_data,
                'liquidity_sweeps': sweeps,
                'order_flow': order_flow,
                'ote_zones': ote_zones,
                'silver_bullet_setups': silver_bullet,  # Professional Enhancement
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
            -len(df) + df.index.get_loc(pd.Timestamp(x['timestamp']))
        ), reverse=True)

        return sweeps[:10]  # Top 10 most significant

    def detect_silver_bullet(
        self,
        df: pd.DataFrame,
        sweeps: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """
        Detect Silver Bullet setups (Professional Enhancement)
        
        Silver Bullet = Session-specific institutional manipulation pattern
        
        High-probability setup:
        1. Asian Low/High swept during London Open killzone (2:00-5:00 EST)
        2. Price reverses after sweep
        3. Creates optimal entry for institutional traders
        
        This is one of ICT's most powerful concepts for catching smart money moves.
        
        Args:
            df: DataFrame with OHLCV data
            sweeps: List of detected liquidity sweeps
            
        Returns:
            List of Silver Bullet setups with metadata
        """
        silver_bullets = []
        
        if not sweeps or len(df) < 50:
            return silver_bullets
        
        london_kz = self.KILL_ZONES['london']
        
        for sweep in sweeps:
            # Only consider Asian sweeps
            if sweep['type'] not in ['asian_low_sweep', 'asian_high_sweep']:
                continue
            
            # Check if sweep occurred during London Open
            sweep_time = pd.Timestamp(sweep['timestamp'])
            
            # Check if timestamp has time component
            if hasattr(sweep_time, 'hour'):
                sweep_hour = sweep_time.hour
                
                # Check if in London killzone (2:00-5:00 EST)
                in_london_kz = self._is_time_in_killzone(
                    time(sweep_hour, sweep_time.minute),
                    london_kz
                )
                
                if in_london_kz and sweep.get('reversed', False):
                    # This is a Silver Bullet setup!
                    setup_type = 'silver_bullet_long' if sweep['type'] == 'asian_low_sweep' else 'silver_bullet_short'
                    
                    # Calculate setup quality
                    strength = sweep.get('strength', 0)
                    if strength > 0.5:
                        quality = 'excellent'
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
        ote: Dict,
        silver_bullet: List[Dict] = None
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

        # Silver Bullet scoring (+3) - Professional Enhancement
        if silver_bullet and len(silver_bullet) > 0:
            # Silver Bullet is a very high-probability setup
            if any(sb.get('setup_quality') == 'excellent' for sb in silver_bullet):
                score += 3
            elif any(sb.get('setup_quality') == 'good' for sb in silver_bullet):
                score += 2
            else:
                score += 1

        # Quality classification (adjusted for Silver Bullet)
        if score >= 10:
            return 'excellent'
        elif score >= 7:
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
        ote: Dict,
        silver_bullet: List[Dict] = None
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

        # Silver Bullet (0.25 max) - Professional Enhancement
        if silver_bullet and len(silver_bullet) > 0:
            # Silver Bullet is the highest probability setup
            if any(sb.get('setup_quality') == 'excellent' for sb in silver_bullet):
                score += 0.25
            elif any(sb.get('setup_quality') == 'good' for sb in silver_bullet):
                score += 0.15
            else:
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