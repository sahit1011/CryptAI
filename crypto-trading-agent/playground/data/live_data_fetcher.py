"""
Live Data Fetcher for Testing Playground
Fetches real-time market data from Binance Futures
"""
import asyncio
from datetime import datetime, timezone
from typing import Dict, List, Optional, Any
import ccxt.async_support as ccxt
from loguru import logger
import yaml
from pathlib import Path


class LiveDataFetcher:
    """
    Fetch live market data from Binance Futures for testing
    
    Features:
    - Multi-timeframe candle fetching
    - Order book snapshots
    - Funding rate data
    - Rate limiting compliance
    - Error handling and retries
    """
    
    def __init__(self, config_path: Optional[str] = None):
        """
        Initialize live data fetcher
        
        Args:
            config_path: Path to test_config.yaml (optional)
        """
        # Load configuration
        if config_path is None:
            config_path = Path(__file__).parent.parent / "config" / "test_config.yaml"
        
        with open(config_path, 'r') as f:
            self.config = yaml.safe_load(f)
        
        # Initialize exchange
        self.exchange = ccxt.binance({
            'enableRateLimit': True,
            'options': {'defaultType': 'future'}
        })
        
        self.data_config = self.config.get('data', {})
        self.candle_limits = self.data_config.get('candle_limits', {})
        
        logger.info("LiveDataFetcher initialized with Binance Futures")
    
    async def connect(self):
        """Load markets and establish connection"""
        try:
            await self.exchange.load_markets()
            logger.success(f"Connected to Binance - {len(self.exchange.markets)} markets loaded")
        except Exception as e:
            logger.error(f"Failed to connect to Binance: {e}")
            raise
    
    async def disconnect(self):
        """Close exchange connection"""
        if self.exchange:
            await self.exchange.close()
            logger.info("Disconnected from Binance")
    
    async def fetch_candles(
        self,
        symbol: str,
        timeframes: Optional[List[str]] = None
    ) -> Dict[str, List[Dict[str, Any]]]:
        """
        Fetch OHLCV candles for multiple timeframes
        
        Args:
            symbol: Trading pair (e.g., 'BTC/USDT')
            timeframes: List of timeframes (e.g., ['1d', '4h', '1h'])
        
        Returns:
            Dictionary mapping timeframe to list of candles
        """
        if timeframes is None:
            timeframes = self.config.get('timeframes', ['1d', '4h', '1h', '15m', '5m'])
        
        logger.info(f"Fetching candles for {symbol} across {len(timeframes)} timeframes")
        
        candles_data = {}
        
        for tf in timeframes:
            try:
                limit = self.candle_limits.get(tf, 100)
                
                logger.debug(f"Fetching {tf} candles (limit: {limit})")
                
                ohlcv = await self.exchange.fetch_ohlcv(
                    symbol=symbol,
                    timeframe=tf,
                    limit=limit
                )
                
                # Convert to our format
                candles = []
                for candle in ohlcv:
                    candles.append({
                        'timestamp': datetime.fromtimestamp(candle[0] / 1000, tz=timezone.utc),
                        'open': float(candle[1]),
                        'high': float(candle[2]),
                        'low': float(candle[3]),
                        'close': float(candle[4]),
                        'volume': float(candle[5])
                    })
                
                candles_data[tf] = candles
                
                logger.success(f"Fetched {len(candles)} {tf} candles for {symbol}")
                
            except Exception as e:
                logger.error(f"Failed to fetch {tf} candles: {e}")
                candles_data[tf] = []
        
        return candles_data
    
    async def fetch_order_book(
        self,
        symbol: str,
        limit: int = 20
    ) -> Optional[Dict[str, Any]]:
        """
        Fetch order book snapshot
        
        Args:
            symbol: Trading pair
            limit: Number of bid/ask levels
        
        Returns:
            Order book data or None if failed
        """
        try:
            logger.debug(f"Fetching order book for {symbol}")
            
            order_book = await self.exchange.fetch_order_book(symbol, limit=limit)
            
            result = {
                'bids': order_book['bids'][:10],
                'asks': order_book['asks'][:10],
                'timestamp': datetime.now(timezone.utc),
                'best_bid': order_book['bids'][0][0] if order_book['bids'] else None,
                'best_ask': order_book['asks'][0][0] if order_book['asks'] else None
            }
            
            logger.success(f"Fetched order book: {len(result['bids'])} bids, {len(result['asks'])} asks")
            
            return result
            
        except Exception as e:
            logger.error(f"Failed to fetch order book: {e}")
            return None
    
    async def fetch_funding_rate(
        self,
        symbol: str
    ) -> Optional[Dict[str, Any]]:
        """
        Fetch current funding rate
        
        Args:
            symbol: Trading pair
        
        Returns:
            Funding rate data or None if failed
        """
        try:
            logger.debug(f"Fetching funding rate for {symbol}")
            
            funding = await self.exchange.fetch_funding_rate(symbol)
            
            result = {
                'rate': funding.get('fundingRate'),
                'timestamp': funding.get('fundingTimestamp'),
                'next_funding': funding.get('fundingDatetime')
            }
            
            logger.success(f"Fetched funding rate: {result['rate']*100:.4f}%")
            
            return result
            
        except Exception as e:
            logger.error(f"Failed to fetch funding rate: {e}")
            return None
    
    async def fetch_all_data(
        self,
        symbol: str,
        timeframes: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """
        Fetch all market data (candles + order book + funding)
        
        Args:
            symbol: Trading pair
            timeframes: List of timeframes
        
        Returns:
            Complete market data package
        """
        logger.info(f"Fetching complete market data for {symbol}")
        
        # Fetch all data in parallel
        candles_task = self.fetch_candles(symbol, timeframes)
        order_book_task = self.fetch_order_book(symbol)
        funding_task = self.fetch_funding_rate(symbol)
        
        candles, order_book, funding = await asyncio.gather(
            candles_task,
            order_book_task,
            funding_task
        )
        
        result = {
            'symbol': symbol,
            'timestamp': datetime.now(timezone.utc).isoformat(),
            'candles': candles,
            'order_book': order_book,
            'funding_rate': funding
        }
        
        logger.success(f"Complete market data fetched for {symbol}")
        
        return result


async def main():
    """Test the live data fetcher"""
    fetcher = LiveDataFetcher()
    
    try:
        await fetcher.connect()
        
        # Fetch data for BTC
        data = await fetcher.fetch_all_data('BTC/USDT', ['1h', '15m', '5m'])
        
        logger.info(f"Fetched data for {data['symbol']}")
        logger.info(f"Timeframes: {list(data['candles'].keys())}")
        logger.info(f"Order book: {data['order_book'] is not None}")
        logger.info(f"Funding rate: {data['funding_rate']}")
        
    finally:
        await fetcher.disconnect()


if __name__ == "__main__":
    asyncio.run(main())
