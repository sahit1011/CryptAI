

"""
Data Collection Agent - FIXED VERSION
Responsible for fetching and distributing live market data
"""
import asyncio
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional
from loguru import logger

from src.agents.base_agent import BaseAgent
from src.core.message_bus import MessageBus, AgentMessage
from src.core.state_manager import StateManager
from src.data.binance_client import BinanceWebSocketClient
from src.data.historical_fetcher import HistoricalDataFetcher
from src.utils.config import get_config
from src.utils.enhanced_logging import PhaseLogger, StepLogger, MetricsLogger
from src.utils.pipeline_logger import PipelineLogger
from src.utils.data_validators import (
    validate_kline_message,
    validate_depth_message,
    validate_funding_rate_message,
    validate_ticker_message
)
from src.utils.quality_metrics import DataQualityMetrics

plog = PipelineLogger()

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
        self.ws_client = BinanceWebSocketClient(on_reconnect_callback=self._on_ws_reconnect)
        self.historical_fetcher = HistoricalDataFetcher(state_manager)

        # Data buffers
        self.candle_buffers: Dict[str, Dict[str, List]] = {}
        self.order_book_data: Dict[str, Dict] = {}
        self.live_price_data: Dict[str, Dict] = {}
        
        # Buffer management
        self.max_buffer_size = 1000  # Maximum candles per timeframe
        self.initial_candles = 500   # Initial candles to fetch
        
        # Track if initial data is loaded
        self.initial_data_loaded = False

        # Demand-gated stream state (see set_stream_profile)
        self._stream_profile: Optional[str] = None
        self._scan_streams_until: float = 0.0   # loop-clock time scan streams last ran
        self._depth_snapshot_at: Dict[str, float] = {}  # per-symbol REST snapshot age
        
        # CRITICAL FIX #1: Add locks for thread-safe buffer access
        self.buffer_locks: Dict[str, Dict[str, asyncio.Lock]] = {}
        
        # CRITICAL FIX #2: Add data quality metrics
        self.quality_metrics = DataQualityMetrics()

        # Build symbol mapping for O(1) lookups (instead of O(n) loops)
        self.binance_to_symbol = {}
        for symbol in self.config.trading.symbols:
            binance_format = symbol.replace('/', '').upper()
            self.binance_to_symbol[binance_format] = symbol
        
        # Normalize timeframes to lowercase consistently
        self.normalized_timeframes = [tf.lower() for tf in self.config.trading.timeframes]
        
        # Initialize buffers and locks for each symbol/timeframe
        for symbol in self.config.trading.symbols:
            self.candle_buffers[symbol] = {
                tf: [] for tf in self.normalized_timeframes
            }
            self.buffer_locks[symbol] = {
                tf: asyncio.Lock() for tf in self.normalized_timeframes
            }

        plog.info(
            f"Data Agent initialized with symbols: {self.config.trading.symbols}, timeframes: {self.normalized_timeframes}",
            agent="data_agent", phase="setup"
        )

    def _setup_handlers(self):
        """Setup message handlers"""
        self.register_handler("fetch_data", self._handle_fetch_data)
        self.register_handler("get_historical", self._handle_get_historical)
        # PHASE 1 FIX: Add handler for orchestrator's on-demand data requests
        self.register_handler("get_market_data", self._handle_get_market_data)

    async def start(self):
        """Start the data collection agent"""
        await super().start()

        try:
            async with PhaseLogger("data_initialization", "Data Collection Agent Startup", agent="data_agent"):
                # Step 1: Connect WebSocket
                step = StepLogger("1.1", "Connecting to Binance WebSocket", agent="data_agent")
                step.start()
                
                await self.ws_client.connect()
                
                step.complete(success=True, details="WebSocket connected")

                # Step 2: Fetch initial historical data
                step = StepLogger("1.2", f"Fetching initial {self.initial_candles} candles", agent="data_agent")
                step.start()
                
                await self._fetch_initial_data()
                self.initial_data_loaded = True
                # Buffers are fresh AS OF NOW: stamp it so the scan-gap refill logic
                # doesn't depend on the magnitude of the monotonic clock (which is
                # seconds-small on a freshly booted container — CI caught exactly that).
                self._scan_streams_until = asyncio.get_event_loop().time()

                step.complete(success=True, details="Initial data loaded")

                # Step 3: streams are DEMAND-GATED — nothing is subscribed here.
                # Subscribing every stream at startup is what suspended the Render
                # workspace on 2026-08-10 (~2.2GB/day flowing to nobody, kept alive
                # 24/7 by our own keepalive cron). The daemon's stream gate calls
                # set_stream_profile() when there is a live consumer: a scanning
                # session (full analysis feed) or an open position (price feed).
                step = StepLogger("1.3", "Market streams demand-gated (none subscribed)", agent="data_agent")
                step.start()
                step.complete(success=True, details="streams follow scan/position demand via set_stream_profile()")

                # Step 4: DISABLED - Auto-publish loop removed for sequential execution
                # PHASE 1 FIX: Data Agent now works on-demand only, triggered by orchestrator
                # The _publish_loop() is disabled to prevent overlapping trading cycles
                step = StepLogger("1.4", "Data Agent ready for on-demand requests", agent="data_agent")
                step.start()
                
                # COMMENTED OUT: asyncio.create_task(self._publish_loop())
                # Data will be published only when orchestrator requests it via 'get_market_data' message
                
                step.complete(success=True, details="Data Agent ready (on-demand mode)")

                plog.success("Data Agent started successfully with all components ready", agent="data_agent")
        except Exception as e:
            plog.error(f"Data Agent startup failed: {e}", exception=e, agent="data_agent", phase="data_initialization")
            raise

    async def stop(self):
        """Stop the agent"""
        try:
            await self.ws_client.disconnect()
            await self.historical_fetcher.close()
            await super().stop()
            plog.success("Data Agent stopped successfully", agent="data_agent", phase="shutdown")
        except Exception as e:
            plog.error(f"Data Agent error during stop: {e}", exception=e, agent="data_agent", phase="shutdown")

    # ------------------------------------------------------------------ #
    # Demand-gated stream profiles (the cost law: every stream names its
    # live consumer, or it does not run).
    #
    #   "scan"   — the full analysis feed: klines for every configured
    #              timeframe + mark-price (funding) per configured symbol.
    #              No depth stream (the analysis plane reads the book once
    #              per cycle, so _refresh_depth_snapshot fetches one REST
    #              snapshot at request time) and no ticker (every kline push
    #              already carries the current close into update_price).
    #   "prices" — kline_1m only, per symbol with exposure: enough to mark
    #              paper positions, fill resting SL/TP, and feed monitors,
    #              at ~one stream per held symbol instead of seven.
    #   None     — nothing subscribed. An idle backend costs nothing.
    #
    # Callbacks are bound methods (stable identity), so re-applying a profile
    # is idempotent: the ws client dedupes both the stream and the handler.
    # ------------------------------------------------------------------ #

    #: Re-run the candle backfill when entering scan mode after streams were
    #: quiet longer than this — buffers stop updating the moment klines
    #: unsubscribe, and analysis on gap-toothed buffers is worse than a few
    #: cached REST calls.
    SCAN_GAP_REFILL_S = 300.0

    async def set_stream_profile(self, profile: Optional[str], price_symbols: Optional[List[str]] = None):
        """Reconcile upstream subscriptions to the demanded profile. Never raises."""
        if profile not in (None, "prices", "scan"):
            plog.warning(f"Unknown stream profile {profile!r}; treating as None", agent="data_agent")
            profile = None

        desired: set = set()
        scan_symbols: List[str] = []
        light_symbols: List[str] = []
        if profile == "scan":
            for symbol in self.config.trading.symbols:
                b = symbol.replace('/', '').lower()
                scan_symbols.append(b)
                for tf in self.normalized_timeframes:
                    desired.add(f"{b}@kline_{tf}")
                desired.add(f"{b}@markprice@1s")
        elif profile == "prices":
            for symbol in (price_symbols or self.config.trading.symbols):
                sym = symbol.replace('/', '').upper()
                # Only feed symbols this agent actually tracks.
                if sym not in self.binance_to_symbol:
                    continue
                b = sym.lower()
                light_symbols.append(b)
                desired.add(f"{b}@kline_1m")

        try:
            current = set(self.ws_client.subscriptions)
            if desired == current and profile == self._stream_profile:
                return

            doomed = sorted(current - desired)
            if doomed:
                await self.ws_client.unsubscribe(doomed)

            for b in scan_symbols:
                await self.ws_client.subscribe_kline(b, self.normalized_timeframes, self._on_kline_update)
                await self.ws_client.subscribe_funding_rate(b, self._on_funding_update)
            for b in light_symbols:
                await self.ws_client.subscribe_kline(b, ["1m"], self._on_price_kline)

            # Entering scan mode after a quiet spell: the buffers have a hole where
            # the streams were off. Refill from REST (cached; ~15 calls) so the next
            # analysis cycle reads a continuous series, not a gap it can't see.
            now = asyncio.get_event_loop().time()
            if profile == "scan" and self._stream_profile != "scan":
                if (now - self._scan_streams_until) > self.SCAN_GAP_REFILL_S:
                    plog.info("Backfilling candle buffers after idle gap", agent="data_agent")
                    await self._fetch_initial_data()
            if self._stream_profile == "scan" and profile != "scan":
                self._scan_streams_until = now

            previous, self._stream_profile = self._stream_profile, profile
            plog.info(
                f"Stream profile {previous!r} → {profile!r} "
                f"({len(self.ws_client.subscriptions)} streams: "
                f"{', '.join(sorted(self.ws_client.subscriptions)) or 'none'})",
                agent="data_agent", phase="data_collection",
            )
        except Exception as e:
            plog.error(f"Stream profile change to {profile!r} failed: {e}",
                       exception=e, agent="data_agent", phase="data_collection")

    async def _on_price_kline(self, data: Dict[str, Any]):
        """kline_1m handler for the 'prices' profile: price only, no buffers.

        The 1m interval is deliberately NOT in the configured analysis timeframes,
        so this must never touch candle_buffers/buffer_locks (keyed by configured
        timeframes — a 1m write would KeyError). Its one job is keeping
        state_manager prices fresh so paper SL/TP fills and monitors stay honest
        while no session is scanning.
        """
        try:
            validated = validate_kline_message(data)
            if not validated:
                return
            symbol = self.binance_to_symbol.get(data['s'].upper())
            if not symbol:
                return
            await self.state_manager.update_price(symbol, validated.close)
        except Exception as e:
            plog.error(f"Error processing price kline: {e}", exception=e, agent="data_agent")

    async def _refresh_depth_snapshot(self, symbol: str):
        """Refresh the order book from REST, at most once per snapshot TTL.

        Replaces the depth20@100ms stream: the only consumer reads the book once
        per analysis cycle, so a snapshot at request time is equally fresh where
        it matters and ~50,000x cheaper. On failure the previous snapshot is kept
        (better a stamped stale book than none — consumers can read the timestamp).
        """
        try:
            now = asyncio.get_event_loop().time()
            last = self._depth_snapshot_at.get(symbol)
            if last is not None and (now - last) < 5.0:
                return  # a snapshot this fresh is indistinguishable from a stream's
            book = await self.historical_fetcher.fetch_order_book(symbol, limit=20)
            if not book or not book.get('bids') or not book.get('asks'):
                return
            self._depth_snapshot_at[symbol] = now
            ts = book.get('timestamp')
            self.order_book_data[symbol] = {
                'timestamp': (datetime.fromtimestamp(ts / 1000, tz=timezone.utc)
                              if ts else datetime.now(timezone.utc)),
                'bids': book['bids'][:10],
                'asks': book['asks'][:10],
                'best_bid': book['bids'][0][0],
                'best_ask': book['asks'][0][0],
            }
            await self.state_manager.set(f"order_book:{symbol}", self.order_book_data[symbol])
        except Exception as e:
            plog.warning(f"Depth snapshot for {symbol} failed: {e}", agent="data_agent")

    async def _fetch_initial_data(self):
        """Fetch initial historical data to populate buffers with exactly 500 candles"""
        plog.method_entry("_fetch_initial_data", agent="data_agent", phase="data_collection")
        try:
            for symbol in self.config.trading.symbols:
                plog.debug(f"Fetching {self.initial_candles} candles for {symbol}", agent="data_agent")
                
                for timeframe in self.config.trading.timeframes:
                    try:
                        # Fetch exactly 500 candles (or as close as possible)
                        historical_data = await self.historical_fetcher.fetch_ohlcv(
                            symbol=symbol,
                            timeframe=timeframe,
                            since=None,  # Let it fetch from now backwards
                            limit=self.initial_candles
                        )
                        
                        if not historical_data.empty:
                            # Convert DataFrame to our candle format
                            candles = []
                            for _, row in historical_data.iterrows():
                                candle = {
                                    'timestamp': row['timestamp'],
                                    'open': float(row['open']),
                                    'high': float(row['high']),
                                    'low': float(row['low']),
                                    'close': float(row['close']),
                                    'volume': float(row['volume']),
                                    'is_closed': True  # Historical data is always closed
                                }
                                candles.append(candle)
                            
                            # Sort by timestamp to ensure chronological order
                            candles.sort(key=lambda x: x['timestamp'])
                            
                            # Store in buffer (take last 500 to ensure we don't exceed)
                            self.candle_buffers[symbol][timeframe] = candles[-self.initial_candles:]
                            
                            # Log details about what we fetched
                            if candles:
                                first_candle = candles[0]
                                last_candle = candles[-1]
                                plog.success(
                                    f"Loaded {len(self.candle_buffers[symbol][timeframe])} {timeframe} candles for {symbol}",
                                    agent="data_agent", phase="data_collection"
                                )
                                
                                # Check for gaps in the loaded data
                                gaps = self._check_buffer_gaps(self.candle_buffers[symbol][timeframe], timeframe)
                                if gaps:
                                    plog.warning(f"Found {len(gaps)} gaps in {symbol} {timeframe} buffer", agent="data_agent")
                        else:
                            plog.warning(f"No data received for {symbol} {timeframe}", agent="data_agent")
                    
                    except Exception as e:
                        plog.error(f"Could not fetch {timeframe} data for {symbol}: {e}", exception=e, agent="data_agent")
                        
        except Exception as e:
            plog.error(f"Error fetching initial data: {e}", exception=e, agent="data_agent")
            # Don't raise - continue with live data collection
        
        plog.method_exit("_fetch_initial_data", result="Initial data fetch complete", agent="data_agent")

    def _check_buffer_gaps(self, candles: List[Dict], timeframe: str) -> List[Dict]:
        """Check for gaps in the buffer"""
        if len(candles) < 2:
            return []
        
        # Calculate expected interval in seconds
        interval_seconds = {
            '1m': 60, '5m': 300, '15m': 900, '30m': 1800,
            '1h': 3600, '4h': 14400, '1d': 86400
        }.get(timeframe, 3600)
        
        gaps = []
        for i in range(1, len(candles)):
            time_diff = (candles[i]['timestamp'] - candles[i-1]['timestamp']).total_seconds()
            expected_diff = interval_seconds
            
            # Allow 10% tolerance for timing variations
            if time_diff > expected_diff * 1.1:
                gaps.append({
                    'index': i,
                    'prev_time': candles[i-1]['timestamp'],
                    'curr_time': candles[i]['timestamp'],
                    'gap_seconds': time_diff - expected_diff
                })
        
        return gaps

    async def _fill_buffer_gaps(self, symbol: str, timeframe: str):
        """Fill gaps in buffer by fetching missing candles"""
        plog.method_entry("_fill_buffer_gaps", agent="data_agent", phase="data_collection")
        
        buffer = self.candle_buffers[symbol][timeframe]
        gaps = self._check_buffer_gaps(buffer, timeframe)
        
        if not gaps:
            plog.debug(f"No gaps found in {symbol} {timeframe} buffer", agent="data_agent")
            plog.method_exit("_fill_buffer_gaps", result="No gaps detected", agent="data_agent")
            return
        
        plog.warning(f"Found {len(gaps)} gaps in {symbol} {timeframe} buffer - initiating backfill", agent="data_agent")
        
        interval_map = {
            '1m': 60, '5m': 300, '15m': 900, '30m': 1800,
            '1h': 3600, '4h': 14400, '1d': 86400
        }
        interval_seconds = interval_map.get(timeframe, 3600)
        
        filled_count = 0
        failed_gaps = 0
        
        for gap in gaps:
            try:
                # Calculate how many candles are missing
                missing_count = int(gap['gap_seconds'] / interval_seconds)
                
                # Cap at 100 to avoid huge fetches
                missing_count = min(missing_count, 100)
                
                plog.debug(
                    f"Filling gap of {missing_count} candles in {symbol} {timeframe} "
                    f"from {gap['prev_time']} to {gap['curr_time']}",
                    agent="data_agent"
                )
                
                # Fetch missing candles
                missing_data = await self.historical_fetcher.fetch_ohlcv(
                    symbol=symbol,
                    timeframe=timeframe,
                    since=gap['prev_time'],
                    limit=missing_count + 1  # Include one extra to ensure coverage
                )
                
                if not missing_data.empty:
                    # Convert DataFrame to candle format
                    missing_candles = []
                    for _, row in missing_data.iterrows():
                        candle = {
                            'timestamp': row['timestamp'],
                            'open': float(row['open']),
                            'high': float(row['high']),
                            'low': float(row['low']),
                            'close': float(row['close']),
                            'volume': float(row['volume']),
                            'is_closed': True
                        }
                        # Only add if it's actually in the gap
                        if gap['prev_time'] < candle['timestamp'] < gap['curr_time']:
                            missing_candles.append(candle)
                    
                    if missing_candles:
                        # Insert at the gap index
                        insert_index = gap['index']
                        for candle in missing_candles:
                            buffer.insert(insert_index, candle)
                            insert_index += 1
                        
                        plog.success(
                            f"Filled gap with {len(missing_candles)} missing candles in {symbol} {timeframe}",
                            agent="data_agent"
                        )
                        filled_count += len(missing_candles)
                    else:
                        plog.warning(f"No candles found to fill gap in {symbol} {timeframe}", agent="data_agent")
                        failed_gaps += 1
                else:
                    plog.warning(f"Failed to fetch data to fill gap in {symbol} {timeframe}", agent="data_agent")
                    failed_gaps += 1
                    
            except Exception as e:
                plog.error(
                    f"Error filling gap in {symbol} {timeframe}: {e}",
                    exception=e,
                    agent="data_agent"
                )
                failed_gaps += 1
        
        # After filling all gaps, trim buffer if it exceeds max size
        if len(buffer) > self.max_buffer_size:
            excess = len(buffer) - self.max_buffer_size
            buffer[:] = buffer[excess:]  # Remove oldest candles
            plog.debug(
                f"Trimmed {excess} oldest candles from {symbol} {timeframe} after gap filling",
                agent="data_agent"
            )
        
        plog.method_exit(
            "_fill_buffer_gaps",
            result=f"Filled {filled_count} candles across {len(gaps)} gaps ({failed_gaps} failures)",
            agent="data_agent"
        )

    async def _on_ws_reconnect(self):
        """Called when WebSocket reconnects - backfill gaps"""
        plog.method_entry("_on_ws_reconnect", agent="data_agent", phase="data_collection")
        
        plog.warning(
            f"WebSocket reconnected - checking {len(self.config.trading.symbols)} symbols "
            f"across {len(self.config.trading.timeframes)} timeframes for gaps",
            agent="data_agent"
        )
        
        reconnect_step = StepLogger("ws_reconnect", "WebSocket Reconnection - Gap Backfill", agent="data_agent")
        reconnect_step.start()
        
        symbols_backfilled = 0
        gaps_found = 0
        
        for symbol in self.config.trading.symbols:
            for timeframe in self.config.trading.timeframes:
                try:
                    buffer = self.candle_buffers[symbol][timeframe]
                    gaps = self._check_buffer_gaps(buffer, timeframe)
                    if gaps:
                        gaps_found += len(gaps)
                        plog.debug(f"Detected {len(gaps)} gaps in {symbol} {timeframe}", agent="data_agent")
                    
                    await self._fill_buffer_gaps(symbol, timeframe)
                    symbols_backfilled += 1
                except Exception as e:
                    plog.error(
                        f"Error backfilling {symbol} {timeframe} after reconnect: {e}",
                        exception=e,
                        agent="data_agent"
                    )
        
        reconnect_step.complete(
            success=True,
            details=f"Backfill complete for all symbols/timeframes",
            metrics={'symbols_processed': symbols_backfilled, 'gaps_found': gaps_found}
        )
        
        plog.success(
            f"WebSocket reconnection recovery complete - processed {symbols_backfilled} symbol/timeframe combinations",
            agent="data_agent"
        )
        
        plog.method_exit("_on_ws_reconnect", result="Reconnection handling complete", agent="data_agent")

    async def _on_kline_update(self, data: Dict[str, Any]):
        """Handle kline update from WebSocket with validation and thread-safe buffer access"""
        # Don't process live updates until initial data is loaded
        if not self.initial_data_loaded:
            plog.debug("Skipping live candle update - initial data not loaded yet", agent="data_agent")
            return
            
        try:
            # CRITICAL FIX #2: Validate incoming data with Pydantic
            validated_kline = validate_kline_message(data)
            
            if not validated_kline:
                # Validation failed - already logged by validator
                await self.quality_metrics.record_validation_error()
                return
            
            binance_symbol = data['s'].upper()  # BTCUSDT format
            timeframe = data['k']['i'].lower()  # Normalize to lowercase

            # Fast O(1) symbol lookup
            symbol = self.binance_to_symbol.get(binance_symbol)
            
            if not symbol:
                plog.warning(f"Unknown symbol from WebSocket: {binance_symbol}", agent="data_agent")
                return

            # Convert validated data to candle format
            candle_timestamp = datetime.fromtimestamp(validated_kline.timestamp / 1000, tz=timezone.utc)
            
            candle = {
                'timestamp': candle_timestamp,
                'open': validated_kline.open,
                'high': validated_kline.high,
                'low': validated_kline.low,
                'close': validated_kline.close,
                'volume': validated_kline.volume,
                'is_closed': validated_kline.is_closed
            }

            # CRITICAL FIX #1: Use lock for thread-safe buffer access
            async with self.buffer_locks[symbol][timeframe]:
                buffer = self.candle_buffers[symbol][timeframe]
                
                # Improved candle deduplication logic
                if candle['is_closed']:
                    # Closed candle: check if it's an update to last or a new one
                    if buffer and buffer[-1]['timestamp'] == candle['timestamp']:
                        # Update the existing closed candle (rare but possible)
                        buffer[-1] = candle
                        plog.debug(
                            f"Updated closed {timeframe} candle for {symbol} at {candle_timestamp}: "
                            f"O:{candle['open']:.2f} H:{candle['high']:.2f} L:{candle['low']:.2f} C:{candle['close']:.2f}",
                            agent="data_agent"
                        )
                    elif not buffer or candle['timestamp'] > buffer[-1]['timestamp']:
                        # New candle - append it
                        buffer.append(candle)
                        
                        # Record metrics
                        await self.quality_metrics.record_candle_received(timeframe, is_valid=True)
                        
                        # Maintain max buffer size (sliding window)
                        if len(buffer) > self.max_buffer_size:
                            removed = buffer.pop(0)
                            plog.debug(
                                f"Removed oldest candle from {symbol} {timeframe} buffer to maintain size (removed: {removed['timestamp']})",
                                agent="data_agent"
                            )
                        
                        plog.success(
                            f"New closed {timeframe} candle for {symbol} at {candle_timestamp}: "
                            f"O:{candle['open']:.2f} H:{candle['high']:.2f} L:{candle['low']:.2f} C:{candle['close']:.2f} "
                            f"(buffer size: {len(buffer)})",
                            agent="data_agent", phase="data_collection"
                        )
                    else:
                        # Old candle, ignore it
                        await self.quality_metrics.record_duplicate_candle()
                        plog.debug(
                            f"Ignoring old closed candle for {symbol} {timeframe} at {candle_timestamp} "
                            f"(buffer ends at {buffer[-1]['timestamp']})",
                            agent="data_agent"
                        )
                else:
                    # Open candle: always update the last candle if timestamps match
                    if buffer and buffer[-1]['timestamp'] == candle['timestamp']:
                        # Update existing open candle
                        buffer[-1] = candle
                        plog.debug(
                            f"Updated open {timeframe} candle for {symbol} at {candle_timestamp}: C:{candle['close']:.2f}",
                            agent="data_agent"
                        )
                    elif not buffer or candle['timestamp'] > buffer[-1]['timestamp']:
                        # First time seeing this open candle
                        buffer.append(candle)
                        plog.debug(
                            f"New open {timeframe} candle for {symbol} at {candle_timestamp}: "
                            f"O:{candle['open']:.2f} C:{candle['close']:.2f} (buffer size: {len(buffer)})",
                            agent="data_agent"
                        )
                        
                        # Maintain max buffer size
                        if len(buffer) > self.max_buffer_size:
                            removed = buffer.pop(0)
                            plog.debug(
                                f"Removed oldest candle from {symbol} {timeframe} buffer (removed: {removed['timestamp']})",
                                agent="data_agent"
                            )
                    else:
                        # Ignore old open candle
                        plog.debug(f"Ignoring old open candle at {candle_timestamp}", agent="data_agent")

            # Update current price in state
            await self.state_manager.update_price(symbol, validated_kline.close)

        except Exception as e:
            plog.error(
                f"Error processing kline update: {e}",
                exception=e,
                agent="data_agent", phase="data_collection"
            )

    async def _on_depth_update(self, data: Dict[str, Any]):
        """Handle order book depth update with validation"""
        try:
            # Validate incoming data
            validated_depth = validate_depth_message(data)
            
            if not validated_depth:
                # Validation failed - already logged by validator
                await self.quality_metrics.record_validation_error()
                return
            
            binance_symbol = data['s'].upper()
            
            # Fast O(1) symbol lookup
            symbol = self.binance_to_symbol.get(binance_symbol)
            
            if not symbol:
                return

            self.order_book_data[symbol] = {
                'timestamp': datetime.fromtimestamp(validated_depth.timestamp / 1000, tz=timezone.utc),
                'bids': validated_depth.bids[:10],  # Top 10 levels
                'asks': validated_depth.asks[:10],  # Top 10 levels
                'best_bid': validated_depth.bids[0][0] if validated_depth.bids else None,
                'best_ask': validated_depth.asks[0][0] if validated_depth.asks else None
            }
            
            if self.order_book_data[symbol]['best_bid'] and self.order_book_data[symbol]['best_ask']:
                bid_ask_spread = (
                    (self.order_book_data[symbol]['best_ask'] - self.order_book_data[symbol]['best_bid']) 
                    / self.order_book_data[symbol]['best_bid'] * 100
                )
                plog.debug(
                    f"Updated order book for {symbol} - Best Bid: ${self.order_book_data[symbol]['best_bid']:.2f}, "
                    f"Best Ask: ${self.order_book_data[symbol]['best_ask']:.2f}, Spread: {bid_ask_spread:.3f}%",
                    agent="data_agent", phase="data_collection"
                )

            # Update State Manager so other agents can access it
            await self.state_manager.set(f"order_book:{symbol}", self.order_book_data[symbol])

        except Exception as e:
            plog.error(
                f"Error processing order book depth update: {e}",
                exception=e,
                agent="data_agent"
            )

    async def _on_funding_update(self, data: Dict[str, Any]):
        """Handle funding rate update with validation"""
        try:
            # Validate incoming data
            validated_funding = validate_funding_rate_message(data)
            
            if not validated_funding:
                # Validation failed - already logged by validator
                await self.quality_metrics.record_validation_error()
                return
            
            binance_symbol = validated_funding.symbol.upper()

            # Fast O(1) symbol lookup
            symbol = self.binance_to_symbol.get(binance_symbol)

            if not symbol:
                return

            await self.state_manager.set(
                f"funding_rate:{symbol}",
                {
                    'rate': validated_funding.funding_rate,
                    'timestamp': datetime.now(timezone.utc).isoformat()
                }
            )

            plog.debug(
                f"Updated funding rate for {symbol}: {validated_funding.funding_rate:.4f} ({validated_funding.funding_rate*100:+.2f}%)",
                agent="data_agent", phase="data_collection"
            )

        except Exception as e:
            plog.error(
                f"Error processing funding rate update: {e}",
                exception=e,
                agent="data_agent"
            )

    async def _on_ticker_update(self, data: Dict[str, Any]):
        """Handle live ticker update for real-time price with validation"""
        try:
            # Validate incoming data
            validated_ticker = validate_ticker_message(data)
            
            if not validated_ticker:
                # Validation failed - already logged by validator
                await self.quality_metrics.record_validation_error()
                return
            
            binance_symbol = validated_ticker.symbol.upper()

            # Fast O(1) symbol lookup
            symbol = self.binance_to_symbol.get(binance_symbol)

            if not symbol:
                return

            self.live_price_data[symbol] = {
                'price': validated_ticker.price,
                'change_percent': validated_ticker.price_change_percent,
                'volume': validated_ticker.volume,
                'timestamp': datetime.now(timezone.utc).isoformat()
            }

            # Update current price in state manager for other agents
            await self.state_manager.update_price(symbol, validated_ticker.price)

            plog.debug(
                f"Live price update for {symbol}: ${validated_ticker.price:.2f} ({validated_ticker.price_change_percent:+.2f}%) | Volume: {validated_ticker.volume:,.0f}",
                agent="data_agent", phase="data_collection"
            )

        except Exception as e:
            plog.error(
                f"Error processing ticker update: {e}",
                exception=e,
                agent="data_agent"
            )

    async def _publish_loop(self):
        """
        DISABLED - Auto-publish loop removed for sequential execution
        
        PHASE 1 FIX: This method is no longer called automatically.
        Data Agent now works on-demand only, triggered by orchestrator.
        This prevents overlapping trading cycles.
        
        Kept for backward compatibility but not used in the new architecture.
        """
        plog.warning(
            "_publish_loop() called but should be disabled. Data Agent works on-demand only.",
            agent="data_agent"
        )
        # Original implementation commented out
        # publish_cycle = 0
        # while self.running:
        #     try:
        #         await asyncio.sleep(self.config.trading.analysis_interval_seconds)
        #         if self.initial_data_loaded:
        #             publish_cycle += 1
        #             await self._publish_market_data()
        #             await self._log_buffer_status()
        #     except Exception as e:
        #         plog.error(f"Error in publish loop: {e}", exception=e, agent="data_agent")

    async def _publish_market_data(self):
        """Publish aggregated market data"""
        plog.method_entry("_publish_market_data", agent="data_agent", phase="data_collection")
        
        published_count = 0
        failed_count = 0
        
        for symbol in self.config.trading.symbols:
            try:
                # Get buffer stats
                buffer_stats = {}
                total_candles = 0
                for tf, candles in self.candle_buffers[symbol].items():
                    if candles:
                        buffer_stats[tf] = {
                            'count': len(candles),
                            'first': candles[0]['timestamp'].isoformat(),
                            'last': candles[-1]['timestamp'].isoformat()
                        }
                        total_candles += len(candles)
                
                plog.debug(
                    f"Preparing market data for {symbol}: {len(buffer_stats)} timeframes, "
                    f"{total_candles} total candles",
                    agent="data_agent"
                )
                
                market_data = {
                    'symbol': symbol,
                    'timestamp': datetime.now(timezone.utc).isoformat(),
                    'candles': self.candle_buffers.get(symbol, {}),
                    'order_book': self.order_book_data.get(symbol),
                    'funding_rate': await self.state_manager.get(f"funding_rate:{symbol}"),
                    'live_price': self.live_price_data.get(symbol),
                    'buffer_stats': buffer_stats
                }

                # CRITICAL: Store candles in State Manager so other agents can access them
                for tf, candles in self.candle_buffers[symbol].items():
                    if candles:
                        await self.state_manager.set(f"candles_{tf}:{symbol}", candles)
                
                # Also store order book if available
                if self.order_book_data.get(symbol):
                    await self.state_manager.set(f"order_book:{symbol}", self.order_book_data[symbol])

                # Send to analysis agent
                await self.send_message(
                    receiver="analysis_agent",
                    message_type="market_data_update",
                    payload=market_data,
                    priority=7
                )

                plog.success(
                    f"Published market data for {symbol} - {total_candles} candles across {len(buffer_stats)} timeframes",
                    agent="data_agent", phase="data_collection"
                )
                published_count += 1

            except Exception as e:
                plog.error(
                    f"Error publishing data for {symbol}: {e}",
                    exception=e,
                    agent="data_agent"
                )
                failed_count += 1
        
        plog.method_exit(
            "_publish_market_data",
            result=f"Published {published_count} symbols ({failed_count} failed)",
            agent="data_agent"
        )

    async def process_message(self, message: AgentMessage) -> Dict[str, Any]:
        """
        Process incoming messages
        
        PHASE 2 FIX: Now sends responses back to orchestrator for sequential execution
        """
        plog.debug(
            f"Processing message type: {message.type} from {message.sender}",
            agent="data_agent"
        )
        
        # Extract correlation_id from message
        correlation_id = getattr(message, 'correlation_id', None) or message.payload.get('correlation_id')
        
        handler = self.handlers.get(message.type)
        if handler:
            result = await handler(message.payload)
            
            # PHASE 2 FIX: Send response to orchestrator if sender is orchestrator
            if message.sender == "orchestrator":
                await self.send_response(result, correlation_id=correlation_id)
                plog.debug(
                    f"Sent response to orchestrator for {message.type} (correlation_id={correlation_id})",
                    agent="data_agent"
                )
            
            return result
        else:
            plog.warning(
                f"No handler registered for message type: {message.type} from {message.sender}",
                agent="data_agent"
            )
            error_response = {"status": "no_handler", "success": False}
            
            # Send error response to orchestrator if needed
            if message.sender == "orchestrator":
                await self.send_response(error_response, correlation_id=correlation_id)
            
            return error_response

    async def _handle_fetch_data(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Handle request to fetch specific data"""
        plog.method_entry("_handle_fetch_data", agent="data_agent", phase="data_collection")
        
        symbol = payload.get('symbol')
        timeframes = payload.get('timeframes', self.config.trading.timeframes)

        if symbol not in self.candle_buffers:
            plog.warning(
                f"Data request for untracked symbol: {symbol}",
                agent="data_agent"
            )
            plog.method_exit("_handle_fetch_data", result="Symbol not tracked", agent="data_agent")
            return {"status": "error", "message": f"Symbol {symbol} not tracked"}

        total_candles = sum(len(self.candle_buffers[symbol].get(tf, [])) for tf in timeframes)
        
        data = {
            'symbol': symbol,
            'candles': {
                tf: self.candle_buffers[symbol].get(tf, [])
                for tf in timeframes
            },
            'order_book': self.order_book_data.get(symbol)
        }

        plog.success(
            f"Fetched data for {symbol} - {len(timeframes)} timeframes, {total_candles} total candles",
            agent="data_agent", phase="data_collection"
        )
        plog.method_exit("_handle_fetch_data", result="Data fetch successful", agent="data_agent")
        return {"status": "success", "data": data}

    async def _handle_get_historical(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Handle request for historical data"""
        plog.method_entry("_handle_get_historical", agent="data_agent", phase="data_collection")
        
        symbol = payload.get('symbol')
        timeframes = payload.get('timeframes', ['1h'])
        lookback_days = payload.get('lookback_days', 30)

        try:
            plog.debug(
                f"Fetching historical data for {symbol}: {len(timeframes)} timeframes, {lookback_days} days lookback",
                agent="data_agent"
            )
            
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
            
            total_records = sum(len(records) for records in data_dict.values())

            plog.success(
                f"Fetched historical data for {symbol} - {total_records} records across {len(data_dict)} timeframes",
                agent="data_agent", phase="data_collection"
            )
            plog.method_exit("_handle_get_historical", result="Historical data fetch successful", agent="data_agent")
            return {"status": "success", "data": data_dict}

        except Exception as e:
            plog.error(
                f"Error fetching historical data for {symbol}: {e}",
                exception=e,
                agent="data_agent"
            )
            plog.method_exit("_handle_get_historical", result="Historical data fetch failed", agent="data_agent")
            return {"status": "error", "message": str(e)}

    async def _handle_get_market_data(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """
        PHASE 1 FIX: Handle on-demand market data request from orchestrator
        
        This replaces the automatic publish loop. The orchestrator now explicitly
        requests market data at the start of each trading cycle, ensuring sequential execution.
        
        Args:
            payload: Request payload containing:
                - symbol: Trading symbol (e.g., 'BTC/USDT')
                - timeframe: Optional specific timeframe (default: all configured timeframes)
                - limit: Optional candle limit (default: all available in buffer)
        
        Returns:
            Dict containing:
                - success: bool
                - data: Market data including candles, order book, funding rate
                - candles: Dict of timeframe -> candle list
        """
        plog.method_entry("_handle_get_market_data", agent="data_agent", phase="data_collection")
        
        # Publish activity to frontend neural feed
        await self.publish_activity(
            action="fetching_market_data",
            message="Fetching market data from buffers",
            phase="data_collection",
            severity="info"
        )
        
        try:
            symbol = payload.get('symbol')
            requested_timeframe = payload.get('timeframe')  # Optional: specific timeframe
            limit = payload.get('limit')  # Optional: limit number of candles
            
            if not symbol:
                plog.error("No symbol provided in get_market_data request", agent="data_agent")
                return {"success": False, "message": "Symbol required"}

            
            # Normalize symbol format (BTC/USDT or BTCUSDT both work)
            symbol_clean = symbol.replace('/', '')
            
            # Find matching symbol in our buffers
            matched_symbol = None
            for tracked_symbol in self.candle_buffers.keys():
                if tracked_symbol.replace('/', '') == symbol_clean:
                    matched_symbol = tracked_symbol
                    break
            
            if not matched_symbol:
                plog.warning(
                    f"Symbol {symbol} not found in tracked symbols: {list(self.candle_buffers.keys())}",
                    agent="data_agent"
                )
                return {"success": False, "message": f"Symbol {symbol} not tracked"}
            
            # Determine which timeframes to return
            if requested_timeframe:
                timeframes = [requested_timeframe.lower()]
            else:
                timeframes = self.normalized_timeframes
            
            # Build candles dict with timeframe-specific limits
            candles = {}
            total_candles = 0

            # Define candle limits per timeframe (optimized for LLM deep analysis)
            # These values balance comprehensive market context with efficient token usage
            timeframe_limits = {
                '1d': 120,   # Daily - 120 days (4 months) - Macro trends & cycles
                '4h': 168,   # 4-hour - 168 periods (28 days) - Monthly structure
                '1h': 168,   # 1-hour - 168 hours (7 days) - Weekly patterns
                '15m': 288,  # 15-min - 288 periods (3 days) - Intraday context
                '5m': 288    # 5-min - 288 periods (1 day) - Recent price action
            }
            # Total: ~1,032 candles = ~30,800 tokens (optimal for Claude Sonnet 4.5)

            for tf in timeframes:
                async with self.buffer_locks[matched_symbol][tf]:
                    buffer = self.candle_buffers[matched_symbol].get(tf, [])
                    if buffer:
                        # Use timeframe-specific limit, fallback to provided limit or all candles
                        tf_limit = timeframe_limits.get(tf, limit or len(buffer))
                        raw_candles = buffer[-tf_limit:]  # Get last N candles for this timeframe

                        # Keep timestamps as datetime objects for analysis agent
                        # Only convert to strings when sending to frontend/API
                        candles[tf] = [candle.copy() for candle in raw_candles]
                        total_candles += len(candles[tf])
            
            # Get buffer stats for logging (convert timestamps to strings here)
            buffer_stats = {}
            for tf, candle_list in candles.items():
                if candle_list:
                    # Safely get timestamp - handle both datetime objects and strings
                    first_ts = candle_list[0]['timestamp']
                    last_ts = candle_list[-1]['timestamp']
                    
                    # Convert to ISO format if it's a datetime object
                    first_ts_str = first_ts.isoformat() if hasattr(first_ts, 'isoformat') else str(first_ts)
                    last_ts_str = last_ts.isoformat() if hasattr(last_ts, 'isoformat') else str(last_ts)
                    
                    buffer_stats[tf] = {
                        'count': len(candle_list),
                        'first': first_ts_str,
                        'last': last_ts_str
                    }
            
            # The book comes from a REST snapshot taken now — the depth stream is gone
            # (10 msg/s feeding a consumer that looks once per cycle was most of the
            # bandwidth bill). Failure keeps the previous snapshot; consumers see its
            # timestamp.
            await self._refresh_depth_snapshot(matched_symbol)

            # Build complete market data response
            market_data = {
                'symbol': matched_symbol,
                'timestamp': datetime.now(timezone.utc).isoformat(),
                'candles': candles,
                'order_book': self.order_book_data.get(matched_symbol),
                'funding_rate': await self.state_manager.get(f"funding_rate:{matched_symbol}"),
                'live_price': self.live_price_data.get(matched_symbol),
                'buffer_stats': buffer_stats
            }
            
            # Also update State Manager for backward compatibility
            for tf, candle_list in candles.items():
                if candle_list:
                    await self.state_manager.set(f"candles_{tf}:{symbol_clean}", candle_list)
            
            if self.order_book_data.get(matched_symbol):
                await self.state_manager.set(f"order_book:{symbol_clean}", self.order_book_data[matched_symbol])
            
            plog.success(
                f"Provided market data for {matched_symbol} - {total_candles} candles across {len(candles)} timeframes",
                agent="data_agent", phase="data_collection"
            )
            
            # CRITICAL FIX: Log the exact response structure being returned
            response = {
                "success": True,
                "data": market_data,
                "candles": candles  # Also include candles at top level for easy access
            }
            
            plog.info(
                f"📤 Data Agent returning response with keys: {list(response.keys())}",
                agent="data_agent"
            )
            plog.info(
                f"📤 Response 'candles' key contains: {list(candles.keys()) if isinstance(candles, dict) else type(candles)}",
                agent="data_agent"
            )
            
            # Publish completion activity
            await self.publish_activity(
                action="market_data_fetched",
                message=f"Provided market data for {matched_symbol}",
                phase="data_collection",
                severity="success",
                metadata={
                    "symbol": matched_symbol,
                    "candles_count": total_candles,
                    "timeframes": list(candles.keys())
                }
            )
            
            plog.method_exit("_handle_get_market_data", result="Market data provided successfully", agent="data_agent")
            
            return response
            
        except Exception as e:
            plog.error(
                f"Error handling get_market_data request: {e}",
                exception=e,
                agent="data_agent"
            )
            plog.method_exit("_handle_get_market_data", result="Failed to provide market data", agent="data_agent")
            return {"success": False, "message": str(e)}

    async def _log_buffer_status(self):
        """Log current buffer status and update rates"""
        plog.method_entry("_log_buffer_status", agent="data_agent", phase="data_collection")
        
        try:
            status_step = StepLogger("buffer_status", "Logging Data Buffer Status", agent="data_agent")
            status_step.start()
            
            total_candles = 0
            status_summary = {}
            
            for symbol in self.config.trading.symbols:
                plog.info(
                    f"▓▓▓▓▓ {symbol.upper()} Buffer Status ▓▓▓▓▓",
                    agent="data_agent", phase="data_collection"
                )
                
                symbol_candles = 0

                # Log candle buffer status
                for timeframe, candles in self.candle_buffers[symbol].items():
                    if candles:
                        latest_candle = candles[-1]
                        oldest_candle = candles[0]
                        time_span = latest_candle['timestamp'] - oldest_candle['timestamp']
                        hours_span = time_span.total_seconds() / 3600
                        symbol_candles += len(candles)
                        total_candles += len(candles)

                        plog.debug(
                            f"{symbol.upper()}/{timeframe}: {len(candles)} candles | "
                            f"Span: {hours_span:.1f}h | "
                            f"Latest: {latest_candle['timestamp'].strftime('%H:%M:%S')} @ ${latest_candle['close']:.2f}",
                            agent="data_agent", phase="data_collection"
                        )
                    else:
                        plog.warning(f"{symbol.upper()}/{timeframe}: NO DATA", agent="data_agent")

                # Log order book status
                if symbol in self.order_book_data:
                    ob = self.order_book_data[symbol]
                    spread = ((ob.get('best_ask', 0) - ob.get('best_bid', 0)) / ob.get('best_bid', 1) * 100) if ob.get('best_bid') else 0
                    plog.debug(
                        f"{symbol.upper()} OrderBook: Bid ${ob.get('best_bid', 'N/A'):.2f} | "
                        f"Ask ${ob.get('best_ask', 'N/A'):.2f} | "
                        f"Spread {spread:.3f}%",
                        agent="data_agent"
                    )
                else:
                    plog.warning(f"{symbol.upper()} OrderBook: NO DATA", agent="data_agent")

                # Log live price status
                if symbol in self.live_price_data:
                    lp = self.live_price_data[symbol]
                    plog.debug(
                        f"{symbol.upper()} LivePrice: ${lp.get('price', 'N/A'):.2f} | "
                        f"Change {lp.get('change_percent', 0):+.2f}% | "
                        f"Volume {lp.get('volume', 0):,.0f}",
                        agent="data_agent"
                    )
                else:
                    plog.warning(f"{symbol.upper()} LivePrice: NO DATA", agent="data_agent")

                status_summary[symbol] = symbol_candles
                plog.info(
                    f"▓▓▓▓▓ End {symbol.upper()} Status ▓▓▓▓▓",
                    agent="data_agent"
                )

            status_step.complete(
                success=True,
                details=f"Logged status for {len(self.config.trading.symbols)} symbols",
                metrics={'total_candles': total_candles, 'symbols': len(status_summary)}
            )
            
            plog.method_exit(
                "_log_buffer_status",
                result=f"Total {total_candles} candles across {len(status_summary)} symbols",
                agent="data_agent"
            )

        except Exception as e:
            plog.error(
                f"Error logging buffer status: {e}",
                exception=e,
                agent="data_agent"
            )