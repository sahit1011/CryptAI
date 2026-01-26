"""
Historical data fetcher for Binance - FIXED VERSION with Rate Limiter
"""
import asyncio
from datetime import datetime, timedelta, timezone
from typing import List, Dict, Any, Optional
import ccxt.async_support as ccxt
from loguru import logger
import pandas as pd
from sqlalchemy import select, and_, func
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.state_manager import StateManager
from src.data.data_models import MarketData
from src.utils.config import get_config
from src.utils.rate_limiter import binance_rate_limiter


class HistoricalDataFetcher:
    """
    Fetch and cache historical market data with rate limiting
    """

    def __init__(self, state_manager: StateManager):
        self.state_manager = state_manager
        self.config = get_config()

        # Initialize exchange with rate limiting
        self.exchange = ccxt.binance({
            'enableRateLimit': True,
            'options': {
                'defaultType': 'future',  # Use futures market
                'warnOnFetchOHLCVLimitArgument': False,
            },
            'rateLimit': 1200,  # 1200ms between requests (50 req/min)
        })
        
        logger.info(f"Historical fetcher initialized for Binance Futures")
        logger.info(f"Exchange type: {self.exchange.options.get('defaultType')}")
        logger.info(f"Exchange has futures: {self.exchange.has.get('fetchOHLCV')}")
        logger.info(f"Rate limiter integrated: {binance_rate_limiter is not None}")

    async def fetch_ohlcv(
        self,
        symbol: str,
        timeframe: str,
        since: Optional[datetime] = None,
        limit: int = 500
    ) -> pd.DataFrame:
        """
        Fetch OHLCV data with rate limiting

        Args:
            symbol: Trading pair (e.g., 'BTC/USDT')
            timeframe: Timeframe ('5m', '15m', '1h', '4h', '1d')
            since: Start date (if None, fetch most recent candles up to now)
            limit: Number of candles

        Returns:
            DataFrame with OHLCV data
        """
        try:
            # Check cache first (but be more selective for initial loads)
            cached = await self._check_cache(symbol, timeframe, since, limit)
            if cached is not None and len(cached) >= limit * 0.95:  # Must have at least 95% of requested candles
                logger.info(f"Cache HIT for {symbol} {timeframe} with {len(cached)} candles")
                return cached

            # RATE LIMITER: Acquire permission before API call
            await binance_rate_limiter.acquire('klines', weight=1)

            # Fetch from exchange
            if since is None:
                # Fetch most recent candles - DO NOT use 'since' parameter
                logger.info(f"Fetching most recent {limit} candles of {symbol} {timeframe} from Binance...")
                
                # Binance has a max limit of 1500 for futures
                fetch_limit = min(limit, 1500)
                
                logger.debug(f"Fetching {fetch_limit} most recent candles (no 'since' parameter)")
                logger.debug(f"Current time: {datetime.now(timezone.utc)}")
                
                # Load markets to ensure symbol is valid
                if not self.exchange.markets:
                    await self.exchange.load_markets()
                
                # When 'since' is not provided, CCXT/Binance returns the most recent candles
                ohlcv = await self.exchange.fetch_ohlcv(
                    symbol,
                    timeframe,
                    limit=fetch_limit
                )
            else:
                # Fetch from specific date forward
                logger.info(f"Fetching {limit} candles of {symbol} {timeframe} from {since}...")
                
                since_ts = int(since.timestamp() * 1000)
                fetch_limit = min(limit, 1500)
                
                ohlcv = await self.exchange.fetch_ohlcv(
                    symbol,
                    timeframe,
                    since=since_ts,
                    limit=fetch_limit
                )

            if not ohlcv:
                logger.warning(f"No data returned from Binance for {symbol} {timeframe}")
                return pd.DataFrame()

            # Debug: Log what we got from exchange
            logger.debug(f"Received {len(ohlcv)} candles from exchange")
            if ohlcv:
                first_ts = datetime.fromtimestamp(ohlcv[0][0] / 1000, tz=timezone.utc)
                last_ts = datetime.fromtimestamp(ohlcv[-1][0] / 1000, tz=timezone.utc)
                logger.info(f"Exchange data range: {first_ts} to {last_ts}")

            # Convert to DataFrame
            df = pd.DataFrame(
                ohlcv,
                columns=['timestamp', 'open', 'high', 'low', 'close', 'volume']
            )
            df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms', utc=True)
            df['symbol'] = symbol.replace('/', '')
            df['timeframe'] = timeframe

            # Sort by timestamp to ensure chronological order
            df = df.sort_values('timestamp').reset_index(drop=True)
            
            # If we fetched more than requested (due to buffer), take only the most recent ones
            if len(df) > limit:
                logger.debug(f"Trimming {len(df)} candles to most recent {limit}")
                df = df.tail(limit).reset_index(drop=True)
            
            # Debug: Verify DataFrame timestamps
            logger.debug(f"DataFrame after processing: {len(df)} candles, first={df.iloc[0]['timestamp']}, last={df.iloc[-1]['timestamp']}")

            # Validate data
            await self._validate_data(df, symbol, timeframe)

            # Check for gaps
            gaps = await self._detect_gaps(df, timeframe)
            if gaps:
                logger.warning(f"Found {len(gaps)} gaps in {symbol} {timeframe}")
                # Log details of gaps
                for i, gap in enumerate(gaps[:5]):  # Log first 5 gaps
                    logger.warning(
                        f"  Gap {i+1}: {gap['start']} to {gap['end']} "
                        f"({gap['duration_minutes']:.1f} minutes)"
                    )
                
                # Try to fill gaps
                df = await self._fill_gaps(df, gaps, symbol, timeframe)

            # Cache the data
            await self._cache_data(df)

            logger.success(f"Fetched {len(df)} candles for {symbol} {timeframe}")
            
            # Final validation - check we got approximately what was requested
            if len(df) < limit * 0.9:
                logger.warning(
                    f"Received fewer candles than expected for {symbol} {timeframe}: "
                    f"got {len(df)}, expected ~{limit}"
                )
            
            return df

        except Exception as e:
            logger.error(f"Error fetching OHLCV for {symbol} {timeframe}: {e}")
            import traceback
            logger.error(traceback.format_exc())
            raise

    async def fetch_multi_timeframe(
        self,
        symbol: str,
        timeframes: List[str],
        lookback_days: int = 30
    ) -> Dict[str, pd.DataFrame]:
        """
        Fetch data for multiple timeframes

        Args:
            symbol: Trading pair
            timeframes: List of timeframes
            lookback_days: Days of historical data (ignored if limit would be better)

        Returns:
            Dict mapping timeframe to DataFrame
        """
        tasks = []
        for tf in timeframes:
            # For initial load, use a fixed 500 candles (most recent)
            limit = 500
            
            task = self.fetch_ohlcv(symbol, tf, since=None, limit=limit)
            tasks.append(task)

        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        output = {}
        for tf, result in zip(timeframes, results):
            if isinstance(result, Exception):
                logger.error(f"Failed to fetch {tf} for {symbol}: {result}")
                output[tf] = pd.DataFrame()
            else:
                output[tf] = result

        return output

    async def fetch_paginated(
        self,
        symbol: str,
        timeframe: str,
        start_date: datetime,
        end_date: datetime,
        batch_size: int = 1000
    ) -> pd.DataFrame:
        """
        Fetch large datasets with pagination

        Args:
            symbol: Trading pair
            timeframe: Timeframe
            start_date: Start date
            end_date: End date
            batch_size: Records per batch

        Returns:
            Combined DataFrame
        """
        all_data = []
        current_date = start_date

        while current_date < end_date:
            # Calculate limit for this batch
            batch_limit = min(batch_size, 1500)  # Binance futures limit

            try:
                # Fetch batch
                df = await self.fetch_ohlcv(symbol, timeframe, current_date, batch_limit)

                if df.empty:
                    break

                all_data.append(df)

                # Update current date to last timestamp + 1 interval
                interval_delta = self._get_interval_delta(timeframe)
                current_date = df['timestamp'].max() + interval_delta

                # Safety check to prevent infinite loops
                if len(all_data) > 100:  # Max 100 batches
                    logger.warning("Reached maximum batch limit")
                    break

            except ValueError as e:
                # No more data available, break the loop
                if "No data received" in str(e):
                    logger.debug(f"No more data available for {symbol} {timeframe} from {current_date}")
                    break
                else:
                    raise  # Re-raise other validation errors

        if all_data:
            combined_df = pd.concat(all_data, ignore_index=True)
            # Remove duplicates
            combined_df = combined_df.drop_duplicates(subset=['timestamp'], keep='first')
            combined_df = combined_df.sort_values('timestamp').reset_index(drop=True)
            return combined_df
        else:
            return pd.DataFrame()

    def _get_interval_delta(self, timeframe: str) -> timedelta:
        """Get timedelta for a timeframe"""
        timeframe_minutes = {
            '1m': 1, '5m': 5, '15m': 15, '30m': 30,
            '1h': 60, '4h': 240, '1d': 1440
        }
        minutes = timeframe_minutes.get(timeframe, 60)
        return timedelta(minutes=minutes)

    def _calculate_limit(self, timeframe: str, days: int) -> int:
        """Calculate number of candles needed"""
        timeframe_minutes = {
            '1m': 1, '5m': 5, '15m': 15, '30m': 30,
            '1h': 60, '4h': 240, '1d': 1440
        }

        minutes = timeframe_minutes.get(timeframe, 60)
        total_minutes = days * 24 * 60
        candles = total_minutes // minutes

        # Binance futures limit is 1500
        return max(1, min(candles, 1500))

    async def _check_cache(
        self,
        symbol: str,
        timeframe: str,
        since: Optional[datetime],
        limit: int
    ) -> Optional[pd.DataFrame]:
        """Check if data exists in cache"""
        try:
            async with self.state_manager.async_session() as session:
                # Build query
                query = select(MarketData).where(
                    and_(
                        MarketData.symbol == symbol.replace('/', ''),
                        MarketData.timeframe == timeframe
                    )
                )

                if since:
                    # Convert timezone-aware datetime to naive for database query
                    since_naive = since.replace(tzinfo=None) if since.tzinfo else since
                    query = query.where(MarketData.timestamp >= since_naive)
                else:
                    # For "most recent" requests, check if cache is up-to-date
                    # Data should be within last 2 hours for it to be useful
                    now = datetime.now(timezone.utc)
                    cutoff = now - timedelta(hours=2)
                    cutoff_naive = cutoff.replace(tzinfo=None)
                    query = query.where(MarketData.timestamp >= cutoff_naive)

                query = query.order_by(MarketData.timestamp.desc()).limit(limit * 2)  # Fetch more to account for gaps

                result = await session.execute(query)
                records = result.scalars().all()

                if not records:
                    logger.debug(f"Cache miss: no records found for {symbol} {timeframe}")
                    return None

                # Convert to DataFrame
                data = []
                for record in reversed(records):  # Reverse to chronological order
                    data.append({
                        'timestamp': record.timestamp,
                        'open': record.open,
                        'high': record.high,
                        'low': record.low,
                        'close': record.close,
                        'volume': record.volume,
                        'symbol': record.symbol,
                        'timeframe': record.timeframe
                    })

                df = pd.DataFrame(data)
                
                # Make timestamps timezone-aware
                df['timestamp'] = pd.to_datetime(df['timestamp'], utc=True)

                # Take only the requested number of most recent candles
                df = df.tail(limit)

                # For "most recent" requests, verify the data is actually recent
                if since is None and not df.empty:
                    now = datetime.now(timezone.utc)
                    latest_candle = df['timestamp'].max()
                    
                    # Define how recent the data should be based on timeframe
                    max_age_minutes = {
                        '1m': 5, '5m': 15, '15m': 45, '30m': 90,
                        '1h': 180, '4h': 720, '1d': 2880
                    }.get(timeframe, 180)
                    
                    age_minutes = (now - latest_candle).total_seconds() / 60
                    
                    if age_minutes > max_age_minutes:
                        logger.debug(
                            f"Cache miss: data too old for {symbol} {timeframe}. "
                            f"Latest: {latest_candle}, Age: {age_minutes:.0f} min, Max: {max_age_minutes} min"
                        )
                        return None

                logger.debug(f"Cache check: found {len(df)} records for {symbol} {timeframe}")
                return df if len(df) >= limit * 0.95 else None

        except Exception as e:
            logger.warning(f"Cache check failed for {symbol} {timeframe}: {e}")
            return None

    async def _cache_data(self, df: pd.DataFrame):
        """Cache data to PostgreSQL"""
        if df.empty:
            return
            
        try:
            async with self.state_manager.async_session() as session:
                cached_count = 0
                for _, row in df.iterrows():
                    # Convert timezone-aware timestamp to naive for database
                    timestamp_naive = row['timestamp'].replace(tzinfo=None) if row['timestamp'].tzinfo else row['timestamp']
                    
                    # Check if exists first to avoid duplicates
                    existing = await session.execute(
                        select(MarketData).where(
                            and_(
                                MarketData.symbol == row['symbol'],
                                MarketData.timeframe == row['timeframe'],
                                MarketData.timestamp == timestamp_naive
                            )
                        )
                    )

                    if existing.scalar_one_or_none() is None:
                        # Create new record
                        market_data = MarketData(
                            symbol=row['symbol'],
                            timeframe=row['timeframe'],
                            timestamp=timestamp_naive,
                            open=float(row['open']),
                            high=float(row['high']),
                            low=float(row['low']),
                            close=float(row['close']),
                            volume=float(row['volume'])
                        )
                        session.add(market_data)
                        cached_count += 1

                await session.commit()
                if cached_count > 0:
                    logger.debug(f"Cached {cached_count} new records")

        except Exception as e:
            logger.warning(f"Failed to cache data: {e}")

    async def _validate_data(self, df: pd.DataFrame, symbol: str, timeframe: str):
        """Validate fetched data for gaps and anomalies"""
        if df.empty:
            raise ValueError(f"No data received for {symbol} {timeframe}")

        # Basic validation
        required_cols = ['timestamp', 'open', 'high', 'low', 'close', 'volume']
        missing_cols = [col for col in required_cols if col not in df.columns]
        if missing_cols:
            raise ValueError(f"Missing required columns: {missing_cols}")

        # Check for negative values
        numeric_cols = ['open', 'high', 'low', 'close', 'volume']
        for col in numeric_cols:
            if (df[col] < 0).any():
                raise ValueError(f"Negative values found in {col}")

        # Check OHLC logic
        invalid_ohlc = (
            (df['high'] < df['low']) |
            (df['high'] < df['open']) |
            (df['high'] < df['close']) |
            (df['low'] > df['open']) |
            (df['low'] > df['close'])
        )
        if invalid_ohlc.any():
            logger.warning(f"Invalid OHLC relationships detected in {symbol} {timeframe}")
            # Don't raise, just warn - some edge cases might be legitimate

    async def _detect_gaps(self, df: pd.DataFrame, timeframe: str) -> List[Dict[str, Any]]:
        """Detect gaps in the data with stricter tolerance"""
        gaps = []

        if len(df) < 2:
            return gaps

        # Calculate expected interval
        interval_minutes = {
            '1m': 1, '5m': 5, '15m': 15, '30m': 30,
            '1h': 60, '4h': 240, '1d': 1440
        }.get(timeframe, 60)

        expected_interval = pd.Timedelta(minutes=interval_minutes)

        # Sort by timestamp
        df_sorted = df.sort_values('timestamp').reset_index(drop=True)

        for i in range(1, len(df_sorted)):
            current_time = df_sorted.iloc[i]['timestamp']
            previous_time = df_sorted.iloc[i-1]['timestamp']

            gap_duration = current_time - previous_time
            
            # Use stricter tolerance - only 5% wiggle room
            if gap_duration > expected_interval * 1.05:
                gaps.append({
                    'start': previous_time,
                    'end': current_time,
                    'duration_minutes': gap_duration.total_seconds() / 60,
                    'index': i
                })

        return gaps

    async def _fill_gaps(self, df: pd.DataFrame, gaps: List[Dict[str, Any]], symbol: str, timeframe: str) -> pd.DataFrame:
        """Fill detected gaps in the data by fetching missing periods"""
        if not gaps:
            return df

        # Limit number of gaps to fill to avoid excessive API calls
        max_gaps_to_fill = 5
        if len(gaps) > max_gaps_to_fill:
            logger.warning(f"Too many gaps ({len(gaps)}), will only fill first {max_gaps_to_fill}")
            gaps = gaps[:max_gaps_to_fill]

        logger.info(f"Attempting to fill {len(gaps)} gaps for {symbol} {timeframe}")

        filled_dataframes = [df]

        for idx, gap in enumerate(gaps):
            try:
                # Calculate how many candles we need
                interval_minutes = {
                    '1m': 1, '5m': 5, '15m': 15, '30m': 30,
                    '1h': 60, '4h': 240, '1d': 1440
                }.get(timeframe, 60)

                gap_duration_minutes = gap['duration_minutes']
                expected_candles = int(gap_duration_minutes / interval_minutes)

                if expected_candles <= 1:
                    continue

                # Limit fetch to reasonable amount
                fetch_limit = min(expected_candles + 5, 1500)

                logger.debug(f"Gap {idx+1}: Fetching {fetch_limit} candles from {gap['start']} to {gap['end']}")

                # RATE LIMITER: Acquire permission before API call
                await binance_rate_limiter.acquire('klines', weight=1)

                # Fetch data for the gap period
                since_ts = int(gap['start'].timestamp() * 1000)
                ohlcv = await self.exchange.fetch_ohlcv(
                    symbol,
                    timeframe,
                    since=since_ts,
                    limit=fetch_limit
                )

                if ohlcv:
                    # Convert to DataFrame
                    gap_df = pd.DataFrame(
                        ohlcv,
                        columns=['timestamp', 'open', 'high', 'low', 'close', 'volume']
                    )
                    gap_df['timestamp'] = pd.to_datetime(gap_df['timestamp'], unit='ms', utc=True)
                    gap_df['symbol'] = symbol.replace('/', '')
                    gap_df['timeframe'] = timeframe

                    # Filter to only include data within the gap period
                    gap_df = gap_df[
                        (gap_df['timestamp'] > gap['start']) &
                        (gap_df['timestamp'] < gap['end'])
                    ]

                    if not gap_df.empty:
                        filled_dataframes.append(gap_df)
                        logger.info(f"Gap {idx+1}: Filled with {len(gap_df)} candles")
                    else:
                        logger.warning(f"Gap {idx+1}: No data returned for gap period")

            except Exception as e:
                logger.warning(f"Failed to fill gap {idx+1}: {e}")
                continue

        # Combine all dataframes
        if len(filled_dataframes) > 1:
            combined_df = pd.concat(filled_dataframes, ignore_index=True)
            # Remove duplicates and sort
            combined_df = combined_df.drop_duplicates(subset=['timestamp'], keep='first')
            combined_df = combined_df.sort_values('timestamp').reset_index(drop=True)
            logger.success(f"Successfully combined data, total candles: {len(combined_df)}")
            return combined_df
        else:
            return df

    async def get_cache_stats(self, symbol: str, timeframe: str) -> Dict[str, Any]:
        """Get cache statistics for a symbol/timeframe"""
        try:
            async with self.state_manager.async_session() as session:
                # Count records
                count_query = select(func.count(MarketData.id)).where(
                    and_(
                        MarketData.symbol == symbol.replace('/', ''),
                        MarketData.timeframe == timeframe
                    )
                )
                count_result = await session.execute(count_query)
                total_records = count_result.scalar()

                # Get date range
                range_query = select(
                    func.min(MarketData.timestamp),
                    func.max(MarketData.timestamp)
                ).where(
                    and_(
                        MarketData.symbol == symbol.replace('/', ''),
                        MarketData.timeframe == timeframe
                    )
                )
                range_result = await session.execute(range_query)
                min_date, max_date = range_result.first()

                return {
                    'symbol': symbol,
                    'timeframe': timeframe,
                    'total_records': total_records,
                    'date_range': {
                        'start': min_date.isoformat() if min_date else None,
                        'end': max_date.isoformat() if max_date else None
                    }
                }

        except Exception as e:
            logger.error(f"Failed to get cache stats: {e}")
            return {}

    async def clear_cache(self, symbol: Optional[str] = None, timeframe: Optional[str] = None):
        """Clear cached data"""
        try:
            async with self.state_manager.async_session() as session:
                query = select(MarketData)

                conditions = []
                if symbol:
                    conditions.append(MarketData.symbol == symbol.replace('/', ''))
                if timeframe:
                    conditions.append(MarketData.timeframe == timeframe)

                if conditions:
                    query = query.where(and_(*conditions))

                result = await session.execute(query)
                records = result.scalars().all()

                for record in records:
                    await session.delete(record)

                await session.commit()
                logger.info(f"Cleared {len(records)} cached records")

        except Exception as e:
            logger.error(f"Failed to clear cache: {e}")

    async def close(self):
        """Close exchange connection"""
        await self.exchange.close()