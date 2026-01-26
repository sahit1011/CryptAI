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