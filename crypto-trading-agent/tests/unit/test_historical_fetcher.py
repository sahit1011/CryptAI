"""
Unit tests for Historical Data Fetcher
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime, timedelta, timezone
import pandas as pd
import asyncio

from src.data.historical_fetcher import HistoricalDataFetcher
from src.core.state_manager import StateManager


@pytest.fixture
def mock_state_manager():
    manager = AsyncMock(spec=StateManager)
    # Mock the async_session property
    session_mock = AsyncMock()
    manager.async_session = AsyncMock()
    manager.async_session.return_value.__aenter__ = AsyncMock(return_value=session_mock)
    manager.async_session.return_value.__aexit__ = AsyncMock(return_value=None)
    return manager


@pytest.fixture
def fetcher(mock_state_manager):
    return HistoricalDataFetcher(mock_state_manager)


@pytest.mark.asyncio
async def test_fetcher_initialization(fetcher):
    """Test fetcher initializes correctly"""
    assert fetcher.state_manager is not None
    assert fetcher.exchange is not None
    assert fetcher.request_count == 0


@pytest.mark.asyncio
async def test_calculate_limit(fetcher):
    """Test limit calculation for different timeframes"""
    # Test 1 day of 1m data
    limit = fetcher._calculate_limit('1m', 1)
    assert limit == 1000  # Capped at 1000 by Binance

    # Test 1 day of 1h data
    limit = fetcher._calculate_limit('1h', 1)
    assert limit == 24

    # Test Binance limit cap
    limit = fetcher._calculate_limit('1m', 2)
    assert limit == 1000  # Capped at 1000


@pytest.mark.asyncio
async def test_fetch_ohlcv_success(fetcher, mock_state_manager):
    """Test successful OHLCV fetch"""
    # Mock the entire fetch process
    with patch.object(fetcher, '_check_cache', return_value=None) as mock_check, \
         patch.object(fetcher, '_apply_rate_limit') as mock_rate_limit, \
         patch.object(fetcher.exchange, 'fetch_ohlcv') as mock_fetch, \
         patch.object(fetcher, '_validate_data') as mock_validate, \
         patch.object(fetcher, '_cache_data') as mock_cache:

        # Mock OHLCV data
        mock_ohlcv = [
            [1699999999000, 43000, 43100, 42900, 43050, 100],
            [1700000000000, 43050, 43150, 42950, 43100, 150]
        ]
        mock_fetch.return_value = mock_ohlcv

        # Fetch data
        df = await fetcher.fetch_ohlcv('BTC/USDT', '5m', limit=2)

        # Assertions
        assert len(df) == 2
        assert df['symbol'].iloc[0] == 'BTCUSDT'
        assert df['timeframe'].iloc[0] == '5m'
        assert df['close'].iloc[0] == 43050
        assert df['volume'].iloc[0] == 100

        mock_check.assert_called_once()
        mock_rate_limit.assert_called_once()
        mock_fetch.assert_called_once()
        mock_validate.assert_called_once()
        mock_cache.assert_called_once()


@pytest.mark.asyncio
async def test_fetch_multi_timeframe(fetcher):
    """Test fetching multiple timeframes"""
    with patch.object(fetcher, 'fetch_ohlcv') as mock_fetch:
        # Mock individual fetches
        df1 = pd.DataFrame({'timestamp': [datetime.now(timezone.utc)], 'close': [43000]})
        df2 = pd.DataFrame({'timestamp': [datetime.now(timezone.utc)], 'close': [43100]})

        mock_fetch.side_effect = [df1, df2]

        timeframes = ['1h', '4h']
        result = await fetcher.fetch_multi_timeframe('BTC/USDT', timeframes, 1)

        assert len(result) == 2
        assert '1h' in result
        assert '4h' in result
        assert mock_fetch.call_count == 2


@pytest.mark.asyncio
async def test_rate_limiting(fetcher):
    """Test rate limiting functionality"""
    # Set up rate limiting state
    fetcher.request_count = fetcher.max_requests_per_window
    fetcher.last_request_time = datetime.now(timezone.utc)

    with patch('asyncio.sleep') as mock_sleep:
        await fetcher._apply_rate_limit()

        # Should have waited
        mock_sleep.assert_called_once()
        # Counter should be reset
        assert fetcher.request_count == 1


@pytest.mark.asyncio
async def test_data_validation_success(fetcher):
    """Test data validation with valid data"""
    df = pd.DataFrame({
        'timestamp': [datetime.now(timezone.utc)],
        'open': [43000],
        'high': [43100],
        'low': [42900],
        'close': [43050],
        'volume': [100]
    })

    # Should not raise exception
    await fetcher._validate_data(df, 'BTC/USDT', '5m')


@pytest.mark.asyncio
async def test_data_validation_failure(fetcher):
    """Test data validation with invalid data"""
    # Test empty dataframe
    df_empty = pd.DataFrame()
    with pytest.raises(ValueError, match="No data received"):
        await fetcher._validate_data(df_empty, 'BTC/USDT', '5m')

    # Test invalid OHLC
    df_invalid = pd.DataFrame({
        'timestamp': [datetime.now(timezone.utc)],
        'open': [43000],
        'high': [42900],  # High < Open
        'low': [43100],   # Low > Open
        'close': [43050],
        'volume': [100]
    })
    with pytest.raises(ValueError, match="Invalid OHLC relationships"):
        await fetcher._validate_data(df_invalid, 'BTC/USDT', '5m')


@pytest.mark.asyncio
async def test_gap_detection(fetcher):
    """Test gap detection in data"""
    base_time = datetime.now(timezone.utc)

    # Create data with a gap (missing 5m candle)
    df = pd.DataFrame({
        'timestamp': [
            base_time,
            base_time + timedelta(minutes=5),  # Normal
            base_time + timedelta(minutes=15)  # Gap of 10 minutes
        ],
        'open': [43000, 43050, 43100],
        'high': [43100, 43150, 43200],
        'low': [42900, 42950, 43000],
        'close': [43050, 43100, 43150],
        'volume': [100, 150, 200]
    })

    gaps = await fetcher._detect_gaps(df, '5m')

    assert len(gaps) == 1
    assert gaps[0]['duration_minutes'] == 10.0


@pytest.mark.asyncio
async def test_cache_check_hit(fetcher, mock_state_manager):
    """Test cache hit scenario"""
    # Mock cached data
    mock_session = AsyncMock()
    mock_state_manager.async_session.return_value.__aenter__.return_value = mock_session

    mock_record = MagicMock()
    mock_record.timestamp = datetime.now(timezone.utc)
    mock_record.open = 43000
    mock_record.high = 43100
    mock_record.low = 42900
    mock_record.close = 43050
    mock_record.volume = 100
    mock_record.symbol = 'BTCUSDT'
    mock_record.timeframe = '5m'

    mock_result = AsyncMock()
    mock_result.scalars.return_value.all.return_value = [mock_record] * 10  # Enough records
    mock_session.execute.return_value = mock_result

    df = await fetcher._check_cache('BTC/USDT', '5m', None, 1)

    assert df is not None
    assert len(df) == 10
    assert df['close'].iloc[0] == 43050


@pytest.mark.asyncio
async def test_cache_check_miss(fetcher, mock_state_manager):
    """Test cache miss scenario"""
    # Mock empty cache
    mock_session = AsyncMock()
    mock_state_manager.async_session.return_value.__aenter__.return_value = mock_session

    mock_result = AsyncMock()
    mock_result.scalars.return_value.all.return_value = []
    mock_session.execute.return_value = mock_result

    df = await fetcher._check_cache('BTC/USDT', '5m', None, 100)

    assert df is None


@pytest.mark.asyncio
async def test_paginated_fetch(fetcher):
    """Test paginated data fetching"""
    with patch.object(fetcher, 'fetch_ohlcv') as mock_fetch:
        # Mock fetch returns
        df1 = pd.DataFrame({
            'timestamp': [datetime(2023, 1, 1, 10, 0)],
            'open': [43000], 'high': [43100], 'low': [42900], 'close': [43050], 'volume': [100]
        })
        df2 = pd.DataFrame({
            'timestamp': [datetime(2023, 1, 1, 11, 0)],
            'open': [43050], 'high': [43150], 'low': [42950], 'close': [43100], 'volume': [150]
        })
        df_empty = pd.DataFrame()

        mock_fetch.side_effect = [df1, df2, df_empty]

        start_date = datetime(2023, 1, 1, 9, 0)
        end_date = datetime(2023, 1, 1, 12, 0)

        result = await fetcher.fetch_paginated('BTC/USDT', '1h', start_date, end_date)

        assert len(result) == 2
        assert mock_fetch.call_count == 3  # Third call returns empty


@pytest.mark.asyncio
async def test_get_cache_stats(fetcher, mock_state_manager):
    """Test cache statistics retrieval"""
    mock_session = AsyncMock()
    mock_state_manager.async_session.return_value.__aenter__.return_value = mock_session

    # Mock count query
    count_result = AsyncMock()
    count_result.scalar.return_value = 1000
    mock_session.execute.return_value = count_result

    # Mock range query
    range_result = AsyncMock()
    range_result.first.return_value = (datetime(2023, 1, 1), datetime(2023, 1, 31))
    mock_session.execute.side_effect = [count_result, range_result]

    stats = await fetcher.get_cache_stats('BTC/USDT', '1h')

    assert stats['total_records'] == 1000
    assert stats['symbol'] == 'BTC/USDT'
    assert stats['timeframe'] == '1h'
    assert 'date_range' in stats
    assert stats['date_range']['start'] == '2023-01-01T00:00:00'
    assert stats['date_range']['end'] == '2023-01-31T00:00:00'


@pytest.mark.asyncio
async def test_clear_cache(fetcher, mock_state_manager):
    """Test cache clearing"""
    mock_session = AsyncMock()
    mock_state_manager.async_session.return_value.__aenter__.return_value = mock_session

    mock_record = MagicMock()
    mock_result = AsyncMock()
    mock_result.scalars.return_value.all.return_value = [mock_record]
    mock_session.execute.return_value = mock_result

    await fetcher.clear_cache('BTC/USDT', '1h')

    # Verify delete was called (may be called multiple times in loop)
    assert mock_session.delete.called
    mock_session.commit.assert_called_once()


@pytest.mark.asyncio
async def test_fetch_ohlcv_with_cache_hit(fetcher, mock_state_manager):
    """Test that fetch_ohlcv uses cache when available"""
    # Mock cache hit
    cached_df = pd.DataFrame({
        'timestamp': [datetime.now(timezone.utc)],
        'open': [43000], 'high': [43100], 'low': [42900], 'close': [43050], 'volume': [100],
        'symbol': ['BTCUSDT'], 'timeframe': ['5m']
    })

    with patch.object(fetcher, '_check_cache', return_value=cached_df) as mock_check:
        result = await fetcher.fetch_ohlcv('BTC/USDT', '5m')

        assert result.equals(cached_df)
        mock_check.assert_called_once()


@pytest.mark.asyncio
async def test_fetch_ohlcv_with_cache_miss(fetcher, mock_state_manager):
    """Test that fetch_ohlcv fetches from exchange when cache misses"""
    with patch.object(fetcher, '_check_cache', return_value=None) as mock_check, \
         patch.object(fetcher, '_apply_rate_limit') as mock_rate_limit, \
         patch.object(fetcher, '_validate_data') as mock_validate, \
         patch.object(fetcher, '_cache_data') as mock_cache, \
         patch.object(fetcher.exchange, 'fetch_ohlcv') as mock_fetch:

        # Mock exchange response
        mock_fetch.return_value = [[1699999999000, 43000, 43100, 42900, 43050, 100]]

        result = await fetcher.fetch_ohlcv('BTC/USDT', '5m', limit=1)

        assert len(result) == 1
        mock_check.assert_called_once()
        mock_rate_limit.assert_called_once()
        mock_validate.assert_called_once()
        mock_cache.assert_called_once()
        mock_fetch.assert_called_once()