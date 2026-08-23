# EPIC 2: Data Collection Agent
**Duration:** Weeks 3-4  
**Priority:** P0

## Ticket #2.1.1: Binance WebSocket Client
**Story Points:** 8  
**Priority:** P0

**Description:**
Implement real-time WebSocket connection to Binance for live market data.

**Acceptance Criteria:**
- [ ] WebSocket connection with auto-reconnect
- [ ] Multi-timeframe kline streams (5m, 15m, 1h, 4h, 1d)
- [ ] Order book depth stream
- [ ] Funding rate stream
- [ ] Connection health monitoring
- [ ] Data validation and error handling

**Deliverables:**

**File:** `src/data/binance_client.py`
```python
"""
Binance WebSocket client for real-time market data
"""
import asyncio
import json
from datetime import datetime
from typing import Dict, Any, List, Callable, Optional
from websockets import connect, WebSocketClientProtocol
from loguru import logger
from tenacity import retry, stop_after_attempt, wait_exponential

class BinanceWebSocketClient:
    """
    Real-time WebSocket client for Binance Futures
    """
    
    BASE_URL = "wss://fstream.binance.com/ws"
    
    def __init__(self):
        self.ws: Optional[WebSocketClientProtocol] = None
        self.subscriptions: List[str] = []
        self.callbacks: Dict[str, List[Callable]] = {}
        self.running = False
        self.reconnect_attempts = 0
        self.max_reconnect_attempts = 10
        
    async def connect(self):
        """Establish WebSocket connection"""
        try:
            self.ws = await connect(self.BASE_URL)
            self.running = True
            self.reconnect_attempts = 0
            logger.info("✅ Connected to Binance WebSocket")
            
            # Resubscribe to streams
            if self.subscriptions:
                await self._resubscribe()
            
            # Start message loop
            asyncio.create_task(self._message_loop())
            
        except Exception as e:
            logger.error(f"Failed to connect to Binance: {e}")
            await self._handle_reconnect()
    
    async def disconnect(self):
        """Close WebSocket connection"""
        self.running = False
        if self.ws:
            await self.ws.close()
        logger.info("Disconnected from Binance WebSocket")
    
    async def subscribe_kline(
        self,
        symbol: str,
        intervals: List[str],
        callback: Callable
    ):
        """
        Subscribe to kline (candlestick) streams
        
        Args:
            symbol: Trading pair (e.g., 'btcusdt')
            intervals: List of intervals ['5m', '15m', '1h', '4h', '1d']
            callback: Function to call with kline data
        """
        symbol = symbol.lower()
        
        for interval in intervals:
            stream = f"{symbol}@kline_{interval}"
            self.subscriptions.append(stream)
            
            if stream not in self.callbacks:
                self.callbacks[stream] = []
            self.callbacks[stream].append(callback)
            
            logger.info(f"Subscribed to {stream}")
        
        # Send subscription message
        if self.ws:
            await self._subscribe(self.subscriptions)
    
    async def subscribe_depth(
        self,
        symbol: str,
        levels: int = 20,
        update_speed: str = "100ms",
        callback: Callable = None
    ):
        """
        Subscribe to order book depth stream
        
        Args:
            symbol: Trading pair
            levels: Depth levels (5, 10, 20)
            update_speed: '100ms' or '500ms'
            callback: Function to call with depth data
        """
        symbol = symbol.lower()
        stream = f"{symbol}@depth{levels}@{update_speed}"
        
        self.subscriptions.append(stream)
        if callback:
            if stream not in self.callbacks:
                self.callbacks[stream] = []
            self.callbacks[stream].append(callback)
        
        if self.ws:
            await self._subscribe([stream])
        
        logger.info(f"Subscribed to {stream}")
    
    async def subscribe_funding_rate(self, symbol: str, callback: Callable):
        """Subscribe to funding rate updates"""
        symbol = symbol.lower()
        stream = f"{symbol}@markPrice@1s"
        
        self.subscriptions.append(stream)
        if stream not in self.callbacks:
            self.callbacks[stream] = []
        self.callbacks[stream].append(callback)
        
        if self.ws:
            await self._subscribe([stream])
        
        logger.info(f"Subscribed to funding rate: {stream}")
    
    async def _subscribe(self, streams: List[str]):
        """Send subscription message"""
        subscribe_message = {
            "method": "SUBSCRIBE",
            "params": streams,
            "id": int(datetime.now(timezone.utc).timestamp())
        }
        
        await self.ws.send(json.dumps(subscribe_message))
    
    async def _resubscribe(self):
        """Resubscribe to all streams after reconnection"""
        if self.subscriptions:
            await self._subscribe(self.subscriptions)
            logger.info(f"Resubscribed to {len(self.subscriptions)} streams")
    
    async def _message_loop(self):
        """Main message receiving loop"""
        while self.running:
            try:
                message = await asyncio.wait_for(self.ws.recv(), timeout=30.0)
                data = json.loads(message)
                
                # Handle different message types
                if 'e' in data:  # Event type present
                    await self._handle_event(data)
                
            except asyncio.TimeoutError:
                # Send ping to keep connection alive
                await self._send_ping()
            except Exception as e:
                logger.error(f"Error in message loop: {e}")
                await self._handle_reconnect()
                break
    
    async def _handle_event(self, data: Dict[str, Any]):
        """Handle incoming event"""
        event_type = data.get('e')
        stream_name = data.get('s', '').lower()
        
        # Find matching callbacks
        matching_callbacks = []
        for subscription, callbacks in self.callbacks.items():
            if stream_name in subscription or subscription.startswith(stream_name):
                matching_callbacks.extend(callbacks)
        
        # Call all matching callbacks
        for callback in matching_callbacks:
            try:
                await callback(data)
            except Exception as e:
                logger.error(f"Error in callback: {e}")
    
    async def _send_ping(self):
        """Send ping to keep connection alive"""
        try:
            await self.ws.ping()
        except Exception as e:
            logger.warning(f"Ping failed: {e}")
    
    @retry(
        stop=stop_after_attempt(10),
        wait=wait_exponential(multiplier=1, min=4, max=60)
    )
    async def _handle_reconnect(self):
        """Handle reconnection with exponential backoff"""
        if self.reconnect_attempts >= self.max_reconnect_attempts:
            logger.critical("Max reconnection attempts reached. Stopping.")
            self.running = False
            return
        
        self.reconnect_attempts += 1
        logger.warning(f"Reconnecting... Attempt {self.reconnect_attempts}")
        
        await self.disconnect()
        await asyncio.sleep(2 ** self.reconnect_attempts)
        await self.connect()
```

---

## Ticket #2.1.2: Historical Data Fetcher
**Story Points:** 5  
**Priority:** P0

**Description:**
Implement historical data fetching from Binance REST API for backtesting and context.

**Acceptance Criteria:**
- [ ] Fetch OHLCV data for multiple timeframes
- [ ] Rate limiting compliance
- [ ] Data caching in PostgreSQL
- [ ] Data validation and gap detection
- [ ] Pagination handling for large datasets

**Deliverables:**

**File:** `src/data/historical_fetcher.py`
```python
"""
Historical data fetcher for Binance
"""
import asyncio
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional
import ccxt.async_support as ccxt
from loguru import logger
import pandas as pd

from src.core.state_manager import StateManager
from src.data.data_models import MarketData

class HistoricalDataFetcher:
    """
    Fetch and cache historical market data
    """
    
    def __init__(self, state_manager: StateManager):
        self.state_manager = state_manager
        self.exchange = ccxt.binance({
            'enableRateLimit': True,
            'options': {'defaultType': 'future'}
        })
        
    async def fetch_ohlcv(
        self,
        symbol: str,
        timeframe: str,
        since: Optional[datetime] = None,
        limit: int = 1000
    ) -> pd.DataFrame:
        """
        Fetch OHLCV data
        
        Args:
            symbol: Trading pair (e.g., 'BTC/USDT')
            timeframe: Timeframe ('5m', '15m', '1h', '4h', '1d')
            since: Start date
            limit: Number of candles
            
        Returns:
            DataFrame with OHLCV data
        """
        try:
            # Check cache first
            cached = await self._check_cache(symbol, timeframe, since, limit)
            if cached is not None:
                logger.info(f"Cache HIT for {symbol} {timeframe}")
                return cached
            
            # Fetch from exchange
            logger.info(f"Fetching {symbol} {timeframe} data from Binance...")
            
            since_ts = int(since.timestamp() * 1000) if since else None
            ohlcv = await self.exchange.fetch_ohlcv(
                symbol,
                timeframe,
                since=since_ts,
                limit=limit
            )
            
            # Convert to DataFrame
            df = pd.DataFrame(
                ohlcv,
                columns=['timestamp', 'open', 'high', 'low', 'close', 'volume']
            )
            df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
            df['symbol'] = symbol.replace('/', '')
            df['timeframe'] = timeframe
            
            # Cache the data
            await self._cache_data(df)
            
            logger.success(f"Fetched {len(df)} candles for {symbol} {timeframe}")
            return df
            
        except Exception as e:
            logger.error(f"Error fetching OHLCV: {e}")
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
            lookback_days: Days of historical data
            
        Returns:
            Dict mapping timeframe to DataFrame
        """
        since = datetime.now(timezone.utc) - timedelta(days=lookback_days)
        
        tasks = []
        for tf in timeframes:
            limit = self._calculate_limit(tf, lookback_days)
            task = self.fetch_ohlcv(symbol, tf, since, limit)
            tasks.append(task)
        
        results = await asyncio.gather(*tasks)
        
        return {tf: df for tf, df in zip(timeframes, results)}
    
    def _calculate_limit(self, timeframe: str, days: int) -> int:
        """Calculate number of candles needed"""
        timeframe_minutes = {
            '1m': 1, '5m': 5, '15m': 15, '30m': 30,
            '1h': 60, '4h': 240, '1d': 1440
        }
        
        minutes = timeframe_minutes.get(timeframe, 60)
        total_minutes = days * 24 * 60
        candles = total_minutes // minutes
        
        return min(candles, 1000)  # Binance limit
    
    async def _check_cache(
        self,
        symbol: str,
        timeframe: str,
        since: Optional[datetime],
        limit: int
    ) -> Optional[pd.DataFrame]:
        """Check if data exists in cache"""
        # Query PostgreSQL for cached data
        # Implementation depends on your caching strategy
        return None
    
    async def _cache_data(self, df: pd.DataFrame):
        """Cache data to PostgreSQL"""
        try:
            # Bulk insert to database
            # This is a simplified version
            for _, row in df.iterrows():
                # Check if exists first to avoid duplicates
                pass
        except Exception as e:
            logger.warning(f"Failed to cache data: {e}")
    
    async def close(self):
        """Close exchange connection"""
        await self.exchange.close()
```

---

## Ticket #2.1.3: Data Collection Agent Implementation
**Story Points:** 8  
**Priority:** P0

**Description:**
Implement the complete Data Collection Agent that orchestrates WebSocket and historical data fetching.

**Acceptance Criteria:**
- [ ] Inherits from BaseAgent
- [ ] Manages WebSocket connections
- [ ] Handles data validation
- [ ] Publishes data to other agents
- [ ] Monitors connection health
- [ ] Unit tests with 80%+ coverage

**Deliverables:**

**File:** `src/agents/data_agent.py`
```python
"""
Data Collection Agent
Responsible for fetching and distributing live market data
"""
import asyncio
from datetime import datetime
from typing import Dict, Any, List
from loguru import logger

from src.agents.base_agent import BaseAgent
from src.core.message_bus import MessageBus, AgentMessage
from src.core.state_manager import StateManager
from src.data.binance_client import BinanceWebSocketClient
from src.data.historical_fetcher import HistoricalDataFetcher
from src.utils.config import get_config

class DataCollectionAgent(BaseAgent):
    """
    Agent responsible for collecting and distributing market data
    """
    
    def __init__(
        self,
        message_bus: MessageBus,
        state_manager: StateManager
    ):
        super().__init__("data_agent", message_bus, state_manager)
        
        self.config = get_config()
        self.ws_client = BinanceWebSocketClient()
        self.historical_fetcher = HistoricalDataFetcher(state_manager)
        
        # Data buffers
        self.candle_buffers: Dict[str, Dict[str, List]] = {}
        self.order_book_data: Dict[str, Dict] = {}
        
        # Initialize buffers for each symbol/timeframe
        for symbol in self.config.trading.symbols:
            self.candle_buffers[symbol] = {
                tf: [] for tf in self.config.trading.timeframes
            }
    
    def _setup_handlers(self):
        """Setup message handlers"""
        self.register_handler("fetch_data", self._handle_fetch_data)
        self.register_handler("get_historical", self._handle_get_historical)
    
    async def start(self):
        """Start the data collection agent"""
        await super().start()
        
        # Connect WebSocket
        await self.ws_client.connect()
        
        # Subscribe to streams for all symbols
        for symbol in self.config.trading.symbols:
            await self._subscribe_symbol(symbol)
        
        # Start data publishing loop
        asyncio.create_task(self._publish_loop())
        
        logger.info("[DataAgent] Started successfully")
    
    async def stop(self):
        """Stop the agent"""
        await self.ws_client.disconnect()
        await self.historical_fetcher.close()
        await super().stop()
    
    async def _subscribe_symbol(self, symbol: str):
        """Subscribe to all data streams for a symbol"""
        
        # Subscribe to klines (candlesticks)
        await self.ws_client.subscribe_kline(
            symbol=symbol.replace('/', '').lower(),
            intervals=self.config.trading.timeframes,
            callback=self._on_kline_update
        )
        
        # Subscribe to order book
        await self.ws_client.subscribe_depth(
            symbol=symbol.replace('/', '').lower(),
            levels=20,
            callback=self._on_depth_update
        )
        
        # Subscribe to funding rate
        await self.ws_client.subscribe_funding_rate(
            symbol=symbol.replace('/', '').lower(),
            callback=self._on_funding_update
        )
        
        logger.info(f"[DataAgent] Subscribed to {symbol} streams")
    
    async def _on_kline_update(self, data: Dict[str, Any]):
        """Handle kline update from WebSocket"""
        try:
            kline = data['k']
            symbol = data['s']
            timeframe = kline['i']
            
            # Extract candle data
            candle = {
                'timestamp': datetime.fromtimestamp(kline['t'] / 1000),
                'open': float(kline['o']),
                'high': float(kline['h']),
                'low': float(kline['l']),
                'close': float(kline['c']),
                'volume': float(kline['v']),
                'is_closed': kline['x']  # Is this candle closed?
            }
            
            # Only store closed candles
            if candle['is_closed']:
                if symbol not in self.candle_buffers:
                    self.candle_buffers[symbol] = {}
                if timeframe not in self.candle_buffers[symbol]:
                    self.candle_buffers[symbol][timeframe] = []
                
                self.candle_buffers[symbol][timeframe].append(candle)
                
                # Keep only last 500 candles
                if len(self.candle_buffers[symbol][timeframe]) > 500:
                    self.candle_buffers[symbol][timeframe].pop(0)
                
                logger.debug(f"New {timeframe} candle for {symbol}: {candle['close']}")
            
            # Update current price in state
            await self.state_manager.update_price(symbol, float(kline['c']))
            
        except Exception as e:
            logger.error(f"Error processing kline: {e}")
    
    async def _on_depth_update(self, data: Dict[str, Any]):
        """Handle order book depth update"""
        try:
            symbol = data['s']
            
            self.order_book_data[symbol] = {
                'timestamp': datetime.fromtimestamp(data['E'] / 1000),
                'bids': [[float(p), float(q)] for p, q in data['b'][:10]],
                'asks': [[float(p), float(q)] for p, q in data['a'][:10]],
                'best_bid': float(data['b'][0][0]) if data['b'] else None,
                'best_ask': float(data['a'][0][0]) if data['a'] else None
            }
            
        except Exception as e:
            logger.error(f"Error processing depth: {e}")
    
    async def _on_funding_update(self, data: Dict[str, Any]):
        """Handle funding rate update"""
        try:
            symbol = data['s']
            funding_rate = float(data['r'])
            
            await self.state_manager.set(
                f"funding_rate:{symbol}",
                {
                    'rate': funding_rate,
                    'timestamp': datetime.now(timezone.utc).isoformat()
                }
            )
            
        except Exception as e:
            logger.error(f"Error processing funding rate: {e}")
    
    async def _publish_loop(self):
        """Periodically publish market data to other agents"""
        while self.running:
            try:
                # Wait for analysis interval
                await asyncio.sleep(self.config.trading.analysis_interval_seconds)
                
                # Publish market data update
                await self._publish_market_data()
                
            except Exception as e:
                logger.error(f"Error in publish loop: {e}")
    
    async def _publish_market_data(self):
        """Publish aggregated market data"""
        for symbol in self.config.trading.symbols:
            try:
                market_data = {
                    'symbol': symbol,
                    'timestamp': datetime.now(timezone.utc).isoformat(),
                    'candles': self.candle_buffers.get(symbol, {}),
                    'order_book': self.order_book_data.get(symbol),
                    'funding_rate': await self.state_manager.get(f"funding_rate:{symbol}")
                }
                
                # Send to analysis agent
                await self.send_message(
                    receiver="analysis_agent",
                    message_type="market_data_update",
                    payload=market_data,
                    priority=7
                )
                
                logger.info(f"[DataAgent] Published market data for {symbol}")
                
            except Exception as e:
                logger.error(f"Error publishing data for {symbol}: {e}")
    
    async def process_message(self, message: AgentMessage) -> Dict[str, Any]:
        """Process incoming messages"""
        handler = self.handlers.get(message.type)
        if handler:
            return await handler(message.payload)
        else:
            logger.warning(f"No handler for message type: {message.type}")
            return {"status": "no_handler"}
    
    async def _handle_fetch_data(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Handle request to fetch specific data"""
        symbol = payload.get('symbol')
        timeframes = payload.get('timeframes', self.config.trading.timeframes)
        
        if symbol not in self.candle_buffers:
            return {"status": "error", "message": f"Symbol {symbol} not tracked"}
        
        data = {
            'symbol': symbol,
            'candles': {
                tf: self.candle_buffers[symbol].get(tf, [])
                for tf in timeframes
            },
            'order_book': self.order_book_data.get(symbol)
        }
        
        return {"status": "success", "data": data}
    
    async def _handle_get_historical(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Handle request for historical data"""
        symbol = payload.get('symbol')
        timeframes = payload.get('timeframes', ['1h'])
        lookback_days = payload.get('lookback_days', 30)
        
        try:
            historical_data = await self.historical_fetcher.fetch_multi_timeframe(
                symbol=symbol,
                timeframes=timeframes,
                lookback_days=lookback_days
            )
            
            # Convert DataFrames to dict
            data_dict = {
                tf: df.to_dict('records')
                for tf, df in historical_data.items()
            }
            
            return {"status": "success", "data": data_dict}
            
        except Exception as e:
            logger.error(f"Error fetching historical data: {e}")
            return {"status": "error", "message": str(e)}
```

**File:** `tests/unit/test_data_agent.py`
```python
"""
Unit tests for Data Collection Agent
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime

from src.agents.data_agent import DataCollectionAgent
from src.core.message_bus import MessageBus, AgentMessage
from src.core.state_manager import StateManager

@pytest.fixture
def mock_message_bus():
    bus = AsyncMock(spec=MessageBus)
    return bus

@pytest.fixture
def mock_state_manager():
    manager = AsyncMock(spec=StateManager)
    return manager

@pytest.fixture
async def data_agent(mock_message_bus, mock_state_manager):
    agent = DataCollectionAgent(mock_message_bus, mock_state_manager)
    return agent

@pytest.mark.asyncio
async def test_agent_initialization(data_agent):
    """Test agent initializes correctly"""
    assert data_agent.name == "data_agent"
    assert data_agent.state == "IDLE"
    assert data_agent.candle_buffers is not None

@pytest.mark.asyncio
async def test_kline_update_processing(data_agent):
    """Test processing of kline updates"""
    kline_data = {
        's': 'BTCUSDT',
        'k': {
            't': 1699999999000,
            'i': '5m',
            'o': '43000',
            'h': '43100',
            'l': '42900',
            'c': '43050',
            'v': '100',
            'x': True  # Closed candle
        }
    }
    
    await data_agent._on_kline_update(kline_data)
    
    # Check if candle was added to buffer
    assert 'BTCUSDT' in data_agent.candle_buffers
    assert '5m' in data_agent.candle_buffers['BTCUSDT']
    assert len(data_agent.candle_buffers['BTCUSDT']['5m']) == 1

@pytest.mark.asyncio
async def test_order_book_update(data_agent):
    """Test order book depth processing"""
    depth_data = {
        's': 'BTCUSDT',
        'E': 1699999999000,
        'b': [['43000', '1.5'], ['42999', '2.0']],
        'a': [['43001', '1.2'], ['43002', '1.8']]
    }
    
    await data_agent._on_depth_update(depth_data)
    
    assert 'BTCUSDT' in data_agent.order_book_data
    assert data_agent.order_book_data['BTCUSDT']['best_bid'] == 43000
    assert data_agent.order_book_data['BTCUSDT']['best_ask'] == 43001

@pytest.mark.asyncio
async def test_message_handling(data_agent, mock_message_bus):
    """Test message handling"""
    message = AgentMessage(
        id="123",
        sender="test",
        receiver="data_agent",
        type="fetch_data",
        payload={'symbol': 'BTCUSDT', 'timeframes': ['5m']}
    )
    
    # Setup some data
    data_agent.candle_buffers['BTCUSDT'] = {
        '5m': [{'close': 43000}]
    }
    
    result = await data_agent.process_message(message)
    
    assert result['status'] == 'success'
    assert 'data' in result
```

---
