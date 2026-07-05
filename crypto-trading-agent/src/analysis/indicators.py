"""
Technical Indicators Module - FIXED for pandas-ta compatibility
Handles both old and new pandas-ta versions
"""
import pandas as pd
import numpy as np
from typing import Dict, Any, List, Tuple
try:
    import pandas_ta as ta
except ImportError:
    ta = None
from loguru import logger


class TechnicalIndicators:
    """
    Calculate and analyze technical indicators
    Compatible with all pandas-ta versions
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
            if ta is None:
                logger.warning("pandas-ta not available, using basic calculations")
                return TechnicalIndicators._calculate_basic_indicators(df)

            # RSI
            try:
                indicators['rsi_14'] = ta.rsi(df['close'], length=14)
                indicators['rsi_21'] = ta.rsi(df['close'], length=21)
            except Exception as e:
                logger.error(f"RSI calculation error: {e}")
                indicators['rsi_14'] = TechnicalIndicators._calculate_rsi(df['close'], 14)
                indicators['rsi_21'] = TechnicalIndicators._calculate_rsi(df['close'], 21)

            # MACD
            try:
                macd_result = ta.macd(df['close'], fast=12, slow=26, signal=9)
                
                # Handle different column naming formats
                if isinstance(macd_result, pd.DataFrame):
                    # Try different possible column names
                    macd_cols = macd_result.columns.tolist()
                    
                    # Find MACD line
                    macd_line = None
                    for col in macd_cols:
                        if 'MACD_' in col and 'h' not in col and 's' not in col:
                            macd_line = macd_result[col]
                            break
                    
                    # Find Signal line
                    signal_line = None
                    for col in macd_cols:
                        if 'MACADs_' in col or 'MACD_signal' in col:
                            signal_line = macd_result[col]
                            break
                    
                    # Find Histogram
                    histogram = None
                    for col in macd_cols:
                        if 'MACDh_' in col or 'MACD_hist' in col:
                            histogram = macd_result[col]
                            break
                    
                    indicators['macd'] = macd_line if macd_line is not None else macd_result.iloc[:, 0]
                    indicators['macd_signal'] = signal_line if signal_line is not None else macd_result.iloc[:, 1]
                    indicators['macd_histogram'] = histogram if histogram is not None else macd_result.iloc[:, 2]
                else:
                    # Fallback calculation
                    macd_calc = TechnicalIndicators._calculate_macd(df['close'])
                    indicators['macd'] = macd_calc['macd']
                    indicators['macd_signal'] = macd_calc['signal']
                    indicators['macd_histogram'] = macd_calc['histogram']
                    
            except Exception as e:
                logger.error(f"MACD calculation error: {e}")
                macd_calc = TechnicalIndicators._calculate_macd(df['close'])
                indicators['macd'] = macd_calc['macd']
                indicators['macd_signal'] = macd_calc['signal']
                indicators['macd_histogram'] = macd_calc['histogram']

            # Bollinger Bands
            try:
                bb_result = ta.bbands(df['close'], length=20, std=2)
                
                if isinstance(bb_result, pd.DataFrame):
                    bb_cols = bb_result.columns.tolist()
                    
                    # Find columns
                    upper, middle, lower = None, None, None
                    for col in bb_cols:
                        # NOTE: pandas-ta bbands returns BBL/BBM/BBU plus BBB_
                        # (bandwidth) and BBP_ (percent). The middle band is BBM_ only —
                        # matching 'BBB_' here overwrote the middle band with bandwidth
                        # (a ~0.02 value), corrupting bb_middle and bb_width.
                        if 'BBU_' in col or 'upper' in col.lower():
                            upper = bb_result[col]
                        elif 'BBM_' in col or 'middle' in col.lower():
                            middle = bb_result[col]
                        elif 'BBL_' in col or 'lower' in col.lower():
                            lower = bb_result[col]
                    
                    indicators['bb_upper'] = upper if upper is not None else bb_result.iloc[:, 0]
                    indicators['bb_middle'] = middle if middle is not None else bb_result.iloc[:, 1]
                    indicators['bb_lower'] = lower if lower is not None else bb_result.iloc[:, 2]
                    indicators['bb_width'] = (indicators['bb_upper'] - indicators['bb_lower']) / indicators['bb_middle'].replace(0, np.nan)
                else:
                    bb_calc = TechnicalIndicators._calculate_bollinger_bands(df['close'])
                    indicators['bb_upper'] = bb_calc['upper']
                    indicators['bb_middle'] = bb_calc['middle']
                    indicators['bb_lower'] = bb_calc['lower']
                    indicators['bb_width'] = bb_calc['width']
                    
            except Exception as e:
                logger.error(f"Bollinger Bands calculation error: {e}")
                bb_calc = TechnicalIndicators._calculate_bollinger_bands(df['close'])
                indicators['bb_upper'] = bb_calc['upper']
                indicators['bb_middle'] = bb_calc['middle']
                indicators['bb_lower'] = bb_calc['lower']
                indicators['bb_width'] = bb_calc['width']

            # EMAs
            try:
                indicators['ema_9'] = ta.ema(df['close'], length=9)
                indicators['ema_21'] = ta.ema(df['close'], length=21)
                indicators['ema_50'] = ta.ema(df['close'], length=50)
                indicators['ema_200'] = ta.ema(df['close'], length=200)
            except Exception as e:
                logger.error(f"EMA calculation error: {e}")
                indicators['ema_9'] = df['close'].ewm(span=9, adjust=False).mean()
                indicators['ema_21'] = df['close'].ewm(span=21, adjust=False).mean()
                indicators['ema_50'] = df['close'].ewm(span=50, adjust=False).mean()
                indicators['ema_200'] = df['close'].ewm(span=200, adjust=False).mean()

            # Volume indicators
            try:
                indicators['volume_sma'] = ta.sma(df['volume'], length=20)
                indicators['vwap'] = ta.vwap(df['high'], df['low'], df['close'], df['volume'])
                indicators['volume'] = df['volume']  # Add raw volume for confluence scoring
            except Exception as e:
                logger.error(f"Volume indicator error: {e}")
                indicators['volume_sma'] = df['volume'].rolling(window=20).mean()
                indicators['vwap'] = TechnicalIndicators._calculate_vwap(df)
                indicators['volume'] = df['volume']

            # ATR
            try:
                indicators['atr_14'] = ta.atr(df['high'], df['low'], df['close'], length=14)
            except Exception as e:
                logger.error(f"ATR calculation error: {e}")
                indicators['atr_14'] = TechnicalIndicators._calculate_atr(df)

            # Stochastic
            try:
                stoch_result = ta.stoch(df['high'], df['low'], df['close'], k=14, d=3, smooth_k=3)
                
                if isinstance(stoch_result, pd.DataFrame):
                    stoch_cols = stoch_result.columns.tolist()
                    
                    k_line, d_line = None, None
                    for col in stoch_cols:
                        if 'STOCHk_' in col or '_k' in col.lower():
                            k_line = stoch_result[col]
                        elif 'STOCHd_' in col or '_d' in col.lower():
                            d_line = stoch_result[col]
                    
                    indicators['stoch_k'] = k_line if k_line is not None else stoch_result.iloc[:, 0]
                    indicators['stoch_d'] = d_line if d_line is not None else stoch_result.iloc[:, 1]
                else:
                    stoch_calc = TechnicalIndicators._calculate_stochastic(df)
                    indicators['stoch_k'] = stoch_calc['k']
                    indicators['stoch_d'] = stoch_calc['d']
                    
            except Exception as e:
                logger.error(f"Stochastic calculation error: {e}")
                stoch_calc = TechnicalIndicators._calculate_stochastic(df)
                indicators['stoch_k'] = stoch_calc['k']
                indicators['stoch_d'] = stoch_calc['d']

            # ADX
            try:
                adx_result = ta.adx(df['high'], df['low'], df['close'], length=14)
                
                if isinstance(adx_result, pd.DataFrame):
                    adx_cols = adx_result.columns.tolist()
                    
                    adx_line, di_plus, di_minus = None, None, None
                    for col in adx_cols:
                        if 'ADX_' in col:
                            adx_line = adx_result[col]
                        elif 'DMP_' in col or 'DIp' in col:
                            di_plus = adx_result[col]
                        elif 'DMN_' in col or 'DIn' in col:
                            di_minus = adx_result[col]
                    
                    indicators['adx'] = adx_line if adx_line is not None else adx_result.iloc[:, 0]
                    indicators['di_plus'] = di_plus if di_plus is not None else adx_result.iloc[:, 1]
                    indicators['di_minus'] = di_minus if di_minus is not None else adx_result.iloc[:, 2]
                else:
                    adx_calc = TechnicalIndicators._calculate_adx(df)
                    indicators['adx'] = adx_calc['adx']
                    indicators['di_plus'] = adx_calc['di_plus']
                    indicators['di_minus'] = adx_calc['di_minus']
                    
            except Exception as e:
                logger.error(f"ADX calculation error: {e}")
                adx_calc = TechnicalIndicators._calculate_adx(df)
                indicators['adx'] = adx_calc['adx']
                indicators['di_plus'] = adx_calc['di_plus']
                indicators['di_minus'] = adx_calc['di_minus']

            logger.debug(f"Calculated {len(indicators)} indicators successfully")
            return indicators

        except Exception as e:
            logger.error(f"Error calculating indicators: {e}")
            return TechnicalIndicators._calculate_basic_indicators(df)

    @staticmethod
    def _calculate_basic_indicators(df: pd.DataFrame) -> Dict[str, pd.Series]:
        """Basic indicator calculations without pandas-ta"""
        indicators = {}

        try:
            # RSI
            indicators['rsi_14'] = TechnicalIndicators._calculate_rsi(df['close'], 14)
            indicators['rsi_21'] = TechnicalIndicators._calculate_rsi(df['close'], 21)

            # EMAs
            indicators['ema_9'] = df['close'].ewm(span=9, adjust=False).mean()
            indicators['ema_21'] = df['close'].ewm(span=21, adjust=False).mean()
            indicators['ema_50'] = df['close'].ewm(span=50, adjust=False).mean()
            indicators['ema_200'] = df['close'].ewm(span=200, adjust=False).mean()

            # MACD
            macd_calc = TechnicalIndicators._calculate_macd(df['close'])
            indicators['macd'] = macd_calc['macd']
            indicators['macd_signal'] = macd_calc['signal']
            indicators['macd_histogram'] = macd_calc['histogram']

            # Bollinger Bands
            bb_calc = TechnicalIndicators._calculate_bollinger_bands(df['close'])
            indicators['bb_upper'] = bb_calc['upper']
            indicators['bb_middle'] = bb_calc['middle']
            indicators['bb_lower'] = bb_calc['lower']
            indicators['bb_width'] = bb_calc['width']

            # Volume
            indicators['volume_sma'] = df['volume'].rolling(window=20).mean()
            indicators['vwap'] = TechnicalIndicators._calculate_vwap(df)
            indicators['volume'] = df['volume']

            # ATR
            indicators['atr_14'] = TechnicalIndicators._calculate_atr(df)

            # Stochastic
            stoch_calc = TechnicalIndicators._calculate_stochastic(df)
            indicators['stoch_k'] = stoch_calc['k']
            indicators['stoch_d'] = stoch_calc['d']

            # ADX
            adx_calc = TechnicalIndicators._calculate_adx(df)
            indicators['adx'] = adx_calc['adx']
            indicators['di_plus'] = adx_calc['di_plus']
            indicators['di_minus'] = adx_calc['di_minus']

            logger.debug(f"Calculated {len(indicators)} basic indicators")
            return indicators

        except Exception as e:
            logger.error(f"Error calculating basic indicators: {e}")
            return {}

    @staticmethod
    def _calculate_rsi(series: pd.Series, period: int = 14) -> pd.Series:
        """Calculate RSI

        Guards the zero-loss case (a window with no down moves): rs = gain/loss
        would divide by zero -> inf. We treat loss==0 as a maxed-out RSI (100)
        and gain==0 with loss==0 (flat window) as neutral (50).
        """
        delta = series.diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
        # Avoid div-by-zero: replace zero loss with NaN so rs->NaN, then resolve.
        rs = gain / loss.replace(0, np.nan)
        rsi = 100 - (100 / (1 + rs))
        # loss==0 & gain>0  -> all gains -> RSI 100
        rsi = rsi.mask((loss == 0) & (gain > 0), 100.0)
        # loss==0 & gain==0 -> flat window -> neutral 50
        rsi = rsi.mask((loss == 0) & (gain == 0), 50.0)
        return rsi

    @staticmethod
    def _calculate_macd(series: pd.Series, fast=12, slow=26, signal=9) -> Dict[str, pd.Series]:
        """Calculate MACD"""
        ema_fast = series.ewm(span=fast, adjust=False).mean()
        ema_slow = series.ewm(span=slow, adjust=False).mean()
        macd_line = ema_fast - ema_slow
        signal_line = macd_line.ewm(span=signal, adjust=False).mean()
        histogram = macd_line - signal_line
        
        return {
            'macd': macd_line,
            'signal': signal_line,
            'histogram': histogram
        }

    @staticmethod
    def _calculate_bollinger_bands(series: pd.Series, period=20, std_dev=2) -> Dict[str, pd.Series]:
        """Calculate Bollinger Bands"""
        middle = series.rolling(window=period).mean()
        std = series.rolling(window=period).std()
        upper = middle + (std * std_dev)
        lower = middle - (std * std_dev)
        # Guard a zero/NaN middle band (e.g. a flat zero-price window) so width
        # doesn't become inf; an undefined width is reported as NaN.
        width = (upper - lower) / middle.replace(0, np.nan)
        
        return {
            'upper': upper,
            'middle': middle,
            'lower': lower,
            'width': width
        }

    @staticmethod
    def _calculate_atr(df: pd.DataFrame, period=14) -> pd.Series:
        """Calculate Average True Range"""
        high_low = df['high'] - df['low']
        high_close = np.abs(df['high'] - df['close'].shift())
        low_close = np.abs(df['low'] - df['close'].shift())
        
        true_range = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
        atr = true_range.rolling(window=period).mean()
        
        return atr

    @staticmethod
    def _calculate_stochastic(df: pd.DataFrame, k_period=14, d_period=3) -> Dict[str, pd.Series]:
        """Calculate Stochastic Oscillator"""
        low_min = df['low'].rolling(window=k_period).min()
        high_max = df['high'].rolling(window=k_period).max()

        # Guard a flat window (high_max == low_min) which would divide by zero.
        rng = (high_max - low_min).replace(0, np.nan)
        k = 100 * (df['close'] - low_min) / rng
        # Flat window -> price sits at the band edge; report neutral 50.
        k = k.mask(high_max == low_min, 50.0)
        d = k.rolling(window=d_period).mean()
        
        return {
            'k': k,
            'd': d
        }

    @staticmethod
    def _calculate_adx(df: pd.DataFrame, period=14) -> Dict[str, pd.Series]:
        """Calculate ADX and Directional Indicators"""
        # Calculate +DM and -DM
        high_diff = df['high'].diff()
        low_diff = -df['low'].diff()
        
        pos_dm = high_diff.where((high_diff > low_diff) & (high_diff > 0), 0)
        neg_dm = low_diff.where((low_diff > high_diff) & (low_diff > 0), 0)
        
        # Calculate TR
        tr = TechnicalIndicators._calculate_atr(df, period=1)
        
        # Calculate smoothed +DM, -DM, and TR
        pos_dm_smooth = pos_dm.rolling(window=period).sum()
        neg_dm_smooth = neg_dm.rolling(window=period).sum()
        tr_smooth = tr.rolling(window=period).sum()
        
        # Calculate +DI and -DI. Guard a zero true-range sum (a perfectly flat
        # window) which would make the directional indicators divide by zero.
        tr_smooth = tr_smooth.replace(0, np.nan)
        pos_di = (100 * pos_dm_smooth / tr_smooth).fillna(0)
        neg_di = (100 * neg_dm_smooth / tr_smooth).fillna(0)

        # Calculate DX and ADX. When +DI and -DI are both zero (no directional
        # movement) the denominator is zero -> treat DX as 0 (no trend).
        di_sum = (pos_di + neg_di).replace(0, np.nan)
        dx = (100 * np.abs(pos_di - neg_di) / di_sum).fillna(0)
        adx = dx.rolling(window=period).mean()
        
        return {
            'adx': adx,
            'di_plus': pos_di,
            'di_minus': neg_di
        }

    @staticmethod
    def _calculate_vwap(df: pd.DataFrame) -> pd.Series:
        """Calculate VWAP"""
        typical_price = (df['high'] + df['low'] + df['close']) / 3
        # Guard zero cumulative volume (no trades yet) -> fall back to typical price.
        cum_vol = df['volume'].cumsum().replace(0, np.nan)
        vwap = (typical_price * df['volume']).cumsum() / cum_vol
        vwap = vwap.fillna(typical_price)
        return vwap

    @staticmethod
    def detect_rsi_divergence(
        df: pd.DataFrame,
        rsi_series: pd.Series,
        lookback: int = 14
    ) -> Dict[str, Any]:
        """
        Detect RSI divergence
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

        # Bullish divergence
        if len(price_troughs) >= 2 and len(rsi_troughs) >= 2:
            if (price[price_troughs[-1]] < price[price_troughs[-2]] and
                rsi[rsi_troughs[-1]] > rsi[rsi_troughs[-2]]):
                return {
                    'divergence': 'bullish',
                    'strength': abs(rsi[rsi_troughs[-1]] - rsi[rsi_troughs[-2]]),
                    'location': price_troughs[-1]
                }

        # Bearish divergence
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
        """Detect Bollinger Bands squeeze"""
        if len(bb_width) < 20:
            return False

        current_width = bb_width.iloc[-1]
        avg_width = bb_width.rolling(20).mean().iloc[-1]

        return current_width < threshold and current_width < avg_width * 0.5

    @staticmethod
    def get_ema_trend(ema_dict: Dict[str, pd.Series]) -> str:
        """Determine trend based on EMA alignment"""
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
        """Classify current market regime"""
        try:
            adx = indicators['adx'].iloc[-1]
            atr = indicators['atr_14'].iloc[-1]
            atr_sma = indicators['atr_14'].rolling(14).mean().iloc[-1]

            # Trend strength
            if adx > 25:
                trend_strength = 'strong'
            elif adx > 20:
                trend_strength = 'moderate'
            else:
                trend_strength = 'weak'

            # Volatility
            if atr > atr_sma * 1.5:
                volatility = 'high'
            elif atr > atr_sma:
                volatility = 'moderate'
            else:
                volatility = 'low'

            # Regime classification
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