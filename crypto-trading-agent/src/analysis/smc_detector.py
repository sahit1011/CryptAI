"""
Smart Money Concepts (SMC) Detector
Identifies institutional trading patterns and price action structures
"""
import pandas as pd
import numpy as np
from typing import Dict, Any, List, Tuple, Optional
from dataclasses import dataclass
from datetime import datetime
from loguru import logger

@dataclass
class OrderBlock:
    """Order Block data structure"""
    type: str  # 'bullish' or 'bearish'
    high: float
    low: float
    open: float
    close: float
    timestamp: pd.Timestamp
    index: int
    strength: float  # 0-1 score
    volume: float
    tested: bool = False
    retest_count: int = 0

@dataclass
class FairValueGap:
    """Fair Value Gap (Imbalance) structure"""
    type: str  # 'bullish' or 'bearish'
    top: float
    bottom: float
    midpoint: float
    size: float
    timestamp: pd.Timestamp
    filled: bool = False
    fill_percentage: float = 0.0

@dataclass
class SwingPoint:
    """Swing High/Low structure"""
    type: str  # 'high' or 'low'
    price: float
    index: int
    timestamp: pd.Timestamp
    strength: int

class SMCDetector:
    """
    Smart Money Concepts Pattern Detector

    Usage:
        detector = SMCDetector()
        results = detector.analyze(df)
    """

    def __init__(self):
        self.order_blocks: List[OrderBlock] = []
        self.fvgs: List[FairValueGap] = []
        self.swing_highs: List[SwingPoint] = []
        self.swing_lows: List[SwingPoint] = []

    def analyze(self, df: pd.DataFrame) -> Dict[str, Any]:
        """
        Complete SMC analysis

        Args:
            df: DataFrame with OHLCV data

        Returns:
            Dictionary containing all SMC structures:
            {
                'order_blocks': List[Dict],
                'fair_value_gaps': List[Dict],
                'break_of_structure': Dict,
                'liquidity_zones': Dict,
                'fibonacci_zones': Dict,
                'supply_demand': Dict,
                'current_zone': str
            }
        """
        try:
            if len(df) < 50:
                logger.warning("Insufficient data for SMC analysis (need >50 candles)")
                return self._empty_result()

            logger.info(f"Starting SMC analysis on {len(df)} candles")
            start_time = datetime.now()

            # 1. Order Block Detection
            order_blocks = self.detect_order_blocks(df)
            logger.debug(f"Found {len(order_blocks)} Order Blocks")

            # 2. Fair Value Gap Detection
            fvgs = self.detect_fair_value_gaps(df)
            logger.debug(f"Found {len(fvgs)} Fair Value Gaps")

            # 3. Break of Structure Analysis
            bos_data = self.detect_break_of_structure(df)
            logger.debug(f"BOS Analysis: {bos_data['current_trend']} trend")

            # 4. Liquidity Zone Mapping
            liquidity = self.map_liquidity_zones(df)
            logger.debug(f"Mapped liquidity zones: {len(liquidity['sell_side'])} SSL, {len(liquidity['buy_side'])} BSL")

            # 5. Fibonacci Zones
            fib_zones = self.calculate_fibonacci_zones(df)

            # 6. Supply/Demand Zones
            sd_zones = self.identify_supply_demand_zones(df)

            # 7. Current Price Classification
            current_zone = self.classify_current_zone(df, fib_zones)

            elapsed = (datetime.now() - start_time).total_seconds() * 1000
            logger.info(f"✅ SMC analysis complete in {elapsed:.0f}ms")

            return {
                'order_blocks': order_blocks,
                'fair_value_gaps': fvgs,
                'break_of_structure': bos_data,
                'liquidity_zones': liquidity,
                'fibonacci_zones': fib_zones,
                'supply_demand': sd_zones,
                'current_zone': current_zone,
                'analysis_timestamp': datetime.utcnow().isoformat(),
                'candles_analyzed': len(df),
                'performance_ms': round(elapsed, 2)
            }

        except Exception as e:
            logger.error(f"❌ Error in SMC analysis: {e}", exc_info=True)
            return self._empty_result()

    def detect_order_blocks(
        self,
        df: pd.DataFrame,
        lookback: int = 50,
        volume_threshold: float = 1.5
    ) -> List[Dict[str, Any]]:
        """
        Detect Order Blocks

        Order Block = Strong momentum candle with high volume followed by reversal

        Bullish OB: Strong bearish candle → price reverses up
        Bearish OB: Strong bullish candle → price reverses down

        Args:
            df: OHLCV DataFrame
            lookback: Candles to look back
            volume_threshold: Volume multiplier for significance (default 1.5x)

        Returns:
            List of order block dictionaries
        """
        order_blocks = []

        for i in range(lookback, len(df) - 2):
            candle = df.iloc[i]
            next_candle = df.iloc[i + 1]

            # Calculate candle metrics
            body_size = abs(candle['close'] - candle['open'])
            candle_range = candle['high'] - candle['low']

            # Skip small/doji candles
            if candle_range == 0 or body_size < candle_range * 0.3:
                continue

            body_percent = (body_size / candle_range) * 100

            # Calculate average volume
            avg_volume = df['volume'].iloc[max(0, i-10):i].mean()
            if avg_volume == 0:
                continue

            volume_ratio = candle['volume'] / avg_volume

            # BULLISH Order Block Detection
            is_bearish_candle = candle['close'] < candle['open']
            strong_body = body_size > candle_range * 0.6
            high_volume = volume_ratio > volume_threshold
            bullish_reversal = next_candle['close'] > candle['high']

            if is_bearish_candle and strong_body and high_volume and bullish_reversal:
                strength = self._calculate_ob_strength(df, i, 'bullish')
                tested = self._check_if_tested(df, i, candle['low'], candle['high'], 'bullish')

                current_price = df['close'].iloc[-1]
                distance = ((current_price - candle['low']) / candle['low']) * 100

                order_blocks.append({
                    'type': 'bullish',
                    'zone': {
                        'high': float(candle['high']),
                        'low': float(candle['low']),
                        'open': float(candle['open']),
                        'close': float(candle['close'])
                    },
                    'timestamp': str(candle.name),
                    'index': i,
                    'strength': round(strength, 3),
                    'volume': float(candle['volume']),
                    'volume_ratio': round(volume_ratio, 2),
                    'body_percent': round(body_percent, 1),
                    'current_distance_percent': round(distance, 2),
                    'tested': tested,
                    'age_candles': len(df) - i,
                    'mitigation_level': float(candle['low'])  # Key level for entry
                })

            # BEARISH Order Block Detection
            is_bullish_candle = candle['close'] > candle['open']
            bearish_reversal = next_candle['close'] < candle['low']

            if is_bullish_candle and strong_body and high_volume and bearish_reversal:
                strength = self._calculate_ob_strength(df, i, 'bearish')
                tested = self._check_if_tested(df, i, candle['low'], candle['high'], 'bearish')

                current_price = df['close'].iloc[-1]
                distance = ((candle['high'] - current_price) / current_price) * 100

                order_blocks.append({
                    'type': 'bearish',
                    'zone': {
                        'high': float(candle['high']),
                        'low': float(candle['low']),
                        'open': float(candle['open']),
                        'close': float(candle['close'])
                    },
                    'timestamp': str(candle.name),
                    'index': i,
                    'strength': round(strength, 3),
                    'volume': float(candle['volume']),
                    'volume_ratio': round(volume_ratio, 2),
                    'body_percent': round(body_percent, 1),
                    'current_distance_percent': round(distance, 2),
                    'tested': tested,
                    'age_candles': len(df) - i,
                    'mitigation_level': float(candle['high'])
                })

        # Filter and sort
        recent_obs = [
            ob for ob in order_blocks
            if ob['age_candles'] <= 50 or ob['strength'] > 0.7
        ]

        recent_obs.sort(key=lambda x: x['strength'], reverse=True)

        # Apply Premium/Discount filtering (Professional Enhancement)
        filtered_obs = self.filter_order_blocks_by_zone(recent_obs[:10], df)
        
        return filtered_obs

    def filter_order_blocks_by_zone(
        self,
        order_blocks: List[Dict[str, Any]],
        df: pd.DataFrame
    ) -> List[Dict[str, Any]]:
        """
        Filter Order Blocks by Premium/Discount zones (Professional Enhancement)
        
        ICT Concept: Only trade OBs in optimal zones
        - Bullish OB: Valid only in Discount zone (price < 0.5 Fib)
        - Bearish OB: Valid only in Premium zone (price > 0.5 Fib)
        
        This filters out counter-trend setups and improves trade quality.
        
        Args:
            order_blocks: List of detected order blocks
            df: DataFrame with price data
            
        Returns:
            Filtered list of order blocks in optimal zones
        """
        if not order_blocks or len(df) < 50:
            return order_blocks
        
        # Calculate Fibonacci zones
        fib_zones = self.calculate_fibonacci_zones(df)
        equilibrium = fib_zones.get('equilibrium', 0)
        
        if equilibrium == 0:
            logger.warning("Could not calculate Fibonacci zones for OB filtering")
            return order_blocks
        
        current_price = df['close'].iloc[-1]
        
        # Determine current zone
        in_discount = current_price < equilibrium
        in_premium = current_price > equilibrium
        
        filtered = []
        filtered_count = {'bullish': 0, 'bearish': 0}
        
        for ob in order_blocks:
            ob_type = ob.get('type')
            
            # Bullish OB: Only valid in Discount zone
            if ob_type == 'bullish' and in_discount:
                ob['zone_filter'] = 'discount'
                ob['zone_valid'] = True
                filtered.append(ob)
                filtered_count['bullish'] += 1
            
            # Bearish OB: Only valid in Premium zone
            elif ob_type == 'bearish' and in_premium:
                ob['zone_filter'] = 'premium'
                ob['zone_valid'] = True
                filtered.append(ob)
                filtered_count['bearish'] += 1
        
        # Log filtering results
        original_count = len(order_blocks)
        if filtered_count['bullish'] > 0 or filtered_count['bearish'] > 0:
            logger.info(
                f"Premium/Discount filter: {original_count} OBs → {len(filtered)} OBs "
                f"({filtered_count['bullish']} bullish in discount, {filtered_count['bearish']} bearish in premium)"
            )
        else:
            logger.debug(
                f"Premium/Discount filter: No valid OBs in current zone "
                f"(price at {current_price:.2f}, equilibrium at {equilibrium:.2f})"
            )
        
        return filtered

    def _calculate_ob_strength(self, df: pd.DataFrame, index: int, ob_type: str) -> float:
        """
        Calculate Order Block strength (0-1)

        Factors:
        1. Volume (higher = stronger)
        2. Successful retests (more = stronger)
        3. Age (newer = stronger)
        4. Body-to-wick ratio (larger body = stronger)
        """
        strength = 0.5  # Base

        candle = df.iloc[index]

        # Volume factor (+0.25 max)
        avg_volume = df['volume'].iloc[max(0, index-20):index].mean()
        if avg_volume > 0:
            volume_ratio = candle['volume'] / avg_volume
            strength += min(0.25, (volume_ratio - 1) * 0.1)

        # Retest factor (+0.3 max)
        retest_count = 0
        for i in range(index + 1, min(index + 30, len(df))):
            if ob_type == 'bullish':
                if candle['low'] <= df['low'].iloc[i] <= candle['high']:
                    if df['close'].iloc[i] > candle['high']:
                        retest_count += 1
            else:
                if candle['low'] <= df['high'].iloc[i] <= candle['high']:
                    if df['close'].iloc[i] < candle['low']:
                        retest_count += 1

        strength += min(0.3, retest_count * 0.1)

        # Age factor (+0.15 max)
        age = len(df) - index
        if age < 5:
            strength += 0.15
        elif age < 15:
            strength += 0.10
        elif age < 30:
            strength += 0.05

        # Body ratio (+0.1 max)
        body_size = abs(candle['close'] - candle['open'])
        candle_range = candle['high'] - candle['low']
        if candle_range > 0:
            body_ratio = body_size / candle_range
            if body_ratio > 0.8:
                strength += 0.1
            elif body_ratio > 0.6:
                strength += 0.05

        return min(strength, 1.0)

    def _check_if_tested(
        self,
        df: pd.DataFrame,
        ob_index: int,
        low: float,
        high: float,
        ob_type: str
    ) -> bool:
        """Check if OB has been retested"""
        for i in range(ob_index + 1, len(df)):
            if ob_type == 'bullish':
                if low <= df['low'].iloc[i] <= high:
                    return True
            else:
                if low <= df['high'].iloc[i] <= high:
                    return True
        return False

    def detect_fair_value_gaps(self, df: pd.DataFrame) -> List[Dict[str, Any]]:
        """
        Detect Fair Value Gaps (Price Imbalances)

        FVG = Gap in price where no trading occurred
        - Bullish FVG: candle[i-1].high < candle[i+1].low
        - Bearish FVG: candle[i-1].low > candle[i+1].high

        Price tends to "fill" these gaps
        """
        fvgs = []

        for i in range(1, len(df) - 1):
            prev = df.iloc[i-1]
            curr = df.iloc[i]
            next_c = df.iloc[i+1]

            # BULLISH FVG (gap up)
            if prev['high'] < next_c['low']:
                gap_size = next_c['low'] - prev['high']
                midpoint = (prev['high'] + next_c['low']) / 2

                # Filter insignificant gaps
                if gap_size / midpoint > 0.001:  # >0.1% gap
                    filled, fill_pct = self._check_fvg_fill(
                        df, i+2, next_c['low'], prev['high'], 'bullish'
                    )

                    current_price = df['close'].iloc[-1]
                    distance = ((current_price - midpoint) / midpoint) * 100

                    fvgs.append({
                        'type': 'bullish',
                        'top': float(next_c['low']),
                        'bottom': float(prev['high']),
                        'midpoint': float(midpoint),
                        'size': float(gap_size),
                        'size_percent': round((gap_size / midpoint) * 100, 3),
                        'timestamp': str(curr.name),
                        'index': i,
                        'filled': filled,
                        'fill_percentage': round(fill_pct * 100, 1),
                        'current_distance_percent': round(distance, 2),
                        'age_candles': len(df) - i
                    })

            # BEARISH FVG (gap down)
            elif prev['low'] > next_c['high']:
                gap_size = prev['low'] - next_c['high']
                midpoint = (prev['low'] + next_c['high']) / 2

                if gap_size / midpoint > 0.001:
                    filled, fill_pct = self._check_fvg_fill(
                        df, i+2, prev['low'], next_c['high'], 'bearish'
                    )

                    current_price = df['close'].iloc[-1]
                    distance = ((midpoint - current_price) / current_price) * 100

                    fvgs.append({
                        'type': 'bearish',
                        'top': float(prev['low']),
                        'bottom': float(next_c['high']),
                        'midpoint': float(midpoint),
                        'size': float(gap_size),
                        'size_percent': round((gap_size / midpoint) * 100, 3),
                        'timestamp': str(curr.name),
                        'index': i,
                        'filled': filled,
                        'fill_percentage': round(fill_pct * 100, 1),
                        'current_distance_percent': round(distance, 2),
                        'age_candles': len(df) - i
                    })

        # Filter: Active FVGs only (not fully filled, recent)
        active_fvgs = [
            fvg for fvg in fvgs
            if fvg['fill_percentage'] < 80 and fvg['age_candles'] <= 100
        ]

        active_fvgs.sort(key=lambda x: x['size_percent'], reverse=True)

        return active_fvgs[:15]

    def _check_fvg_fill(
        self,
        df: pd.DataFrame,
        start_idx: int,
        top: float,
        bottom: float,
        fvg_type: str
    ) -> Tuple[bool, float]:
        """Check if FVG has been filled"""

        midpoint = (top + bottom) / 2
        gap_size = abs(top - bottom)

        for i in range(start_idx, len(df)):
            if fvg_type == 'bullish':
                if df['low'].iloc[i] <= midpoint:
                    if df['low'].iloc[i] <= bottom:
                        return True, 1.0  # Fully filled
                    else:
                        fill_pct = (top - df['low'].iloc[i]) / gap_size
                        return False, fill_pct
            else:
                if df['high'].iloc[i] >= midpoint:
                    if df['high'].iloc[i] >= top:
                        return True, 1.0
                    else:
                        fill_pct = (df['high'].iloc[i] - bottom) / gap_size
                        return False, fill_pct

        return False, 0.0

    def detect_break_of_structure(self, df: pd.DataFrame, swing_period: int = 10) -> Dict[str, Any]:
        """
        Detect Break of Structure (BOS) and Change of Character (CHoCH)

        BOS: Price breaks previous swing in trend direction
        CHoCH: Price breaks previous swing against trend (reversal signal)
        """
        self.swing_highs = self._find_swing_highs(df, swing_period)
        self.swing_lows = self._find_swing_lows(df, swing_period)

        trend = self._determine_trend(self.swing_highs, self.swing_lows)

        bos_points = []
        choch_points = []

        current_price = df['close'].iloc[-1]

        # Check for BOS
        if len(self.swing_highs) >= 2:
            last_high = self.swing_highs[-1]
            if current_price > last_high['price']:
                bos_points.append({
                    'type': 'bullish_bos',
                    'level': last_high['price'],
                    'timestamp': str(df.index[-1]),
                    'strength': 'strong' if current_price > last_high['price'] * 1.005 else 'moderate'
                })

        if len(self.swing_lows) >= 2:
            last_low = self.swing_lows[-1]
            if current_price < last_low['price']:
                bos_points.append({
                    'type': 'bearish_bos',
                    'level': last_low['price'],
                    'timestamp': str(df.index[-1]),
                    'strength': 'strong' if current_price < last_low['price'] * 0.995 else 'moderate'
                })

        # Check for CHoCH (trend reversal)
        if trend == 'bullish' and len(self.swing_lows) >= 2:
            if self.swing_lows[-1]['price'] < self.swing_lows[-2]['price']:
                choch_points.append({
                    'type': 'bearish_choch',
                    'level': self.swing_lows[-1]['price'],
                    'timestamp': str(self.swing_lows[-1]['timestamp']),
                    'previous_trend': 'bullish'
                })

        elif trend == 'bearish' and len(self.swing_highs) >= 2:
            if self.swing_highs[-1]['price'] > self.swing_highs[-2]['price']:
                choch_points.append({
                    'type': 'bullish_choch',
                    'level': self.swing_highs[-1]['price'],
                    'timestamp': str(self.swing_highs[-1]['timestamp']),
                    'previous_trend': 'bearish'
                })

        return {
            'bos': bos_points,
            'choch': choch_points,
            'current_trend': trend,
            'swing_highs': [
                {'price': float(sh['price']), 'timestamp': str(sh['timestamp'])}
                for sh in self.swing_highs[-3:]
            ],
            'swing_lows': [
                {'price': float(sl['price']), 'timestamp': str(sl['timestamp'])}
                for sl in self.swing_lows[-3:]
            ]
        }

    def _find_swing_highs(self, df: pd.DataFrame, period: int) -> List[Dict]:
        """Find swing high points"""
        swings = []
        for i in range(period, len(df) - period):
            high = df['high'].iloc[i]
            is_swing = all(
                high >= df['high'].iloc[j]
                for j in range(i - period, i + period + 1) if j != i
            )
            if is_swing:
                swings.append({
                    'price': float(high),
                    'index': i,
                    'timestamp': df.index[i]
                })
        return swings

    def _find_swing_lows(self, df: pd.DataFrame, period: int) -> List[Dict]:
        """Find swing low points"""
        swings = []
        for i in range(period, len(df) - period):
            low = df['low'].iloc[i]
            is_swing = all(
                low <= df['low'].iloc[j]
                for j in range(i - period, i + period + 1) if j != i
            )
            if is_swing:
                swings.append({
                    'price': float(low),
                    'index': i,
                    'timestamp': df.index[i]
                })
        return swings

    def _determine_trend(self, swing_highs: List, swing_lows: List) -> str:
        """Determine trend from swing structure"""
        if len(swing_highs) >= 2 and len(swing_lows) >= 2:
            hh = swing_highs[-1]['price'] > swing_highs[-2]['price']
            hl = swing_lows[-1]['price'] > swing_lows[-2]['price']
            if hh and hl:
                return 'bullish'

            lh = swing_highs[-1]['price'] < swing_highs[-2]['price']
            ll = swing_lows[-1]['price'] < swing_lows[-2]['price']
            if lh and ll:
                return 'bearish'

        return 'neutral'

    def map_liquidity_zones(self, df: pd.DataFrame, lookback: int = 50) -> Dict[str, Any]:
        """Map liquidity zones (stop loss clusters)"""
        recent_df = df.iloc[-lookback:]

        swing_highs = self._find_swing_highs(recent_df, 5)
        swing_lows = self._find_swing_lows(recent_df, 5)

        current_price = df['close'].iloc[-1]

        sell_side = []
        for sh in swing_highs[-5:]:
            swept = df['high'].iloc[-10:].max() > sh['price']
            sell_side.append({
                'price': float(sh['price']),
                'timestamp': str(sh['timestamp']),
                'swept': swept,
                'distance_percent': round(((sh['price'] - current_price) / current_price) * 100, 2)
            })

        buy_side = []
        for sl in swing_lows[-5:]:
            swept = df['low'].iloc[-10:].min() < sl['price']
            buy_side.append({
                'price': float(sl['price']),
                'timestamp': str(sl['timestamp']),
                'swept': swept,
                'distance_percent': round(((current_price - sl['price']) / sl['price']) * 100, 2)
            })

        return {
            'sell_side': sell_side,
            'buy_side': buy_side,
            'recent_sweeps': [l for l in sell_side + buy_side if l['swept']]
        }

    def calculate_fibonacci_zones(self, df: pd.DataFrame, lookback: int = 100) -> Dict[str, Any]:
        """Calculate Fibonacci retracement zones"""
        recent_df = df.iloc[-lookback:]

        highest = recent_df['high'].max()
        lowest = recent_df['low'].min()
        range_size = highest - lowest

        levels = {
            '0.0': lowest,
            '0.236': lowest + range_size * 0.236,
            '0.382': lowest + range_size * 0.382,
            '0.5': lowest + range_size * 0.5,
            '0.618': lowest + range_size * 0.618,
            '0.786': lowest + range_size * 0.786,
            '1.0': highest
        }

        return {
            'levels': {k: float(v) for k, v in levels.items()},
            'equilibrium': float(levels['0.5']),
            'premium_zone': (float(levels['0.618']), float(levels['1.0'])),
            'discount_zone': (float(levels['0.0']), float(levels['0.382'])),
            'ote_zone': (float(levels['0.618']), float(levels['0.786']))
        }

    def identify_supply_demand_zones(self, df: pd.DataFrame) -> Dict[str, Any]:
        """Identify supply/demand zones"""
        # Simplified implementation
        return {
            'supply_zones': [],
            'demand_zones': []
        }

    def classify_current_zone(self, df: pd.DataFrame, fib_zones: Dict) -> str:
        """Classify where price is relative to Fib zones"""
        current_price = df['close'].iloc[-1]
        eq = fib_zones['equilibrium']

        discount_top = fib_zones['discount_zone'][1]
        premium_bottom = fib_zones['premium_zone'][0]

        if current_price <= discount_top:
            return 'discount'
        elif current_price >= premium_bottom:
            return 'premium'
        else:
            return 'equilibrium'

    def _empty_result(self) -> Dict[str, Any]:
        """Return empty result structure"""
        return {
            'order_blocks': [],
            'fair_value_gaps': [],
            'break_of_structure': {'bos': [], 'choch': [], 'current_trend': 'unknown'},
            'liquidity_zones': {'sell_side': [], 'buy_side': []},
            'fibonacci_zones': {},
            'supply_demand': {'supply_zones': [], 'demand_zones': []},
            'current_zone': 'unknown'
        }