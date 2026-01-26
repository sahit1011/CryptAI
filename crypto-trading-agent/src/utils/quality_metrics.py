"""
Data Quality Metrics Tracker
Monitors and tracks data collection quality metrics
"""
import asyncio
from datetime import datetime, timezone
from typing import Dict, Any, Optional
from dataclasses import dataclass, field, asdict
from loguru import logger


@dataclass
class DataQualityMetrics:
    """Tracks data quality metrics for monitoring and debugging"""
    
    # Candle metrics
    total_candles_received: int = 0
    candles_by_timeframe: Dict[str, int] = field(default_factory=dict)
    duplicate_candles_rejected: int = 0
    invalid_candles_rejected: int = 0
    
    # Gap metrics
    gaps_detected: int = 0
    gaps_filled: int = 0
    gap_fill_failures: int = 0
    total_candles_backfilled: int = 0
    
    # WebSocket metrics
    websocket_connects: int = 0
    websocket_disconnects: int = 0
    websocket_reconnects: int = 0
    websocket_errors: int = 0
    
    # Latency metrics (in milliseconds)
    avg_message_latency_ms: float = 0.0
    max_message_latency_ms: float = 0.0
    min_message_latency_ms: float = float('inf')
    
    # Error metrics
    validation_errors: int = 0
    api_errors: int = 0
    rate_limit_hits: int = 0
    
    # Timestamps
    started_at: Optional[str] = None
    last_update: Optional[str] = None
    
    # Internal tracking
    _latency_samples: list = field(default_factory=list, repr=False)
    _lock: asyncio.Lock = field(default_factory=asyncio.Lock, repr=False)
    
    def __post_init__(self):
        if self.started_at is None:
            self.started_at = datetime.now(timezone.utc).isoformat()
    
    async def record_candle_received(self, timeframe: str, is_valid: bool = True):
        """Record a candle reception"""
        async with self._lock:
            if is_valid:
                self.total_candles_received += 1
                self.candles_by_timeframe[timeframe] = self.candles_by_timeframe.get(timeframe, 0) + 1
            else:
                self.invalid_candles_rejected += 1
            
            self.last_update = datetime.now(timezone.utc).isoformat()
    
    async def record_duplicate_candle(self):
        """Record a duplicate candle rejection"""
        async with self._lock:
            self.duplicate_candles_rejected += 1
            self.last_update = datetime.now(timezone.utc).isoformat()
    
    async def record_gap_detected(self, gap_count: int = 1):
        """Record gap detection"""
        async with self._lock:
            self.gaps_detected += gap_count
            self.last_update = datetime.now(timezone.utc).isoformat()
    
    async def record_gap_filled(self, candles_filled: int, success: bool = True):
        """Record gap filling attempt"""
        async with self._lock:
            if success:
                self.gaps_filled += 1
                self.total_candles_backfilled += candles_filled
            else:
                self.gap_fill_failures += 1
            
            self.last_update = datetime.now(timezone.utc).isoformat()
    
    async def record_websocket_event(self, event_type: str):
        """
        Record WebSocket event
        
        Args:
            event_type: 'connect', 'disconnect', 'reconnect', 'error'
        """
        async with self._lock:
            if event_type == 'connect':
                self.websocket_connects += 1
            elif event_type == 'disconnect':
                self.websocket_disconnects += 1
            elif event_type == 'reconnect':
                self.websocket_reconnects += 1
            elif event_type == 'error':
                self.websocket_errors += 1
            
            self.last_update = datetime.now(timezone.utc).isoformat()
    
    async def record_latency(self, latency_ms: float):
        """Record message latency"""
        async with self._lock:
            self._latency_samples.append(latency_ms)
            
            # Keep only last 1000 samples
            if len(self._latency_samples) > 1000:
                self._latency_samples.pop(0)
            
            # Update stats
            self.avg_message_latency_ms = sum(self._latency_samples) / len(self._latency_samples)
            self.max_message_latency_ms = max(self._latency_samples)
            self.min_message_latency_ms = min(self._latency_samples)
            
            self.last_update = datetime.now(timezone.utc).isoformat()
    
    async def record_validation_error(self):
        """Record a validation error"""
        async with self._lock:
            self.validation_errors += 1
            self.last_update = datetime.now(timezone.utc).isoformat()
    
    async def record_api_error(self):
        """Record an API error"""
        async with self._lock:
            self.api_errors += 1
            self.last_update = datetime.now(timezone.utc).isoformat()
    
    async def record_rate_limit_hit(self):
        """Record a rate limit hit"""
        async with self._lock:
            self.rate_limit_hits += 1
            self.last_update = datetime.now(timezone.utc).isoformat()
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert metrics to dictionary (excluding internal fields)"""
        data = asdict(self)
        # Remove internal fields
        data.pop('_latency_samples', None)
        data.pop('_lock', None)
        return data
    
    def get_summary(self) -> str:
        """Get a human-readable summary"""
        uptime = "N/A"
        if self.started_at:
            started = datetime.fromisoformat(self.started_at.replace('Z', '+00:00'))
            uptime_seconds = (datetime.now(timezone.utc) - started).total_seconds()
            hours = int(uptime_seconds // 3600)
            minutes = int((uptime_seconds % 3600) // 60)
            uptime = f"{hours}h {minutes}m"
        
        summary = f"""
╔══════════════════════════════════════════════════════════════╗
║                  DATA QUALITY METRICS                        ║
╠══════════════════════════════════════════════════════════════╣
║ Uptime: {uptime:<50} ║
║                                                              ║
║ CANDLES:                                                     ║
║   Total Received: {self.total_candles_received:<43} ║
║   Invalid Rejected: {self.invalid_candles_rejected:<41} ║
║   Duplicates Rejected: {self.duplicate_candles_rejected:<38} ║
║                                                              ║
║ GAPS:                                                        ║
║   Detected: {self.gaps_detected:<49} ║
║   Filled: {self.gaps_filled:<51} ║
║   Fill Failures: {self.gap_fill_failures:<44} ║
║   Candles Backfilled: {self.total_candles_backfilled:<39} ║
║                                                              ║
║ WEBSOCKET:                                                   ║
║   Connects: {self.websocket_connects:<49} ║
║   Disconnects: {self.websocket_disconnects:<46} ║
║   Reconnects: {self.websocket_reconnects:<47} ║
║   Errors: {self.websocket_errors:<51} ║
║                                                              ║
║ LATENCY:                                                     ║
║   Avg: {self.avg_message_latency_ms:.2f}ms{'':<46} ║
║   Min: {self.min_message_latency_ms if self.min_message_latency_ms != float('inf') else 0:.2f}ms{'':<46} ║
║   Max: {self.max_message_latency_ms:.2f}ms{'':<46} ║
║                                                              ║
║ ERRORS:                                                      ║
║   Validation: {self.validation_errors:<47} ║
║   API: {self.api_errors:<54} ║
║   Rate Limits: {self.rate_limit_hits:<46} ║
╚══════════════════════════════════════════════════════════════╝
        """
        return summary.strip()
    
    async def log_summary(self):
        """Log the metrics summary"""
        logger.info(f"\n{self.get_summary()}")
    
    async def reset(self):
        """Reset all metrics"""
        async with self._lock:
            self.__init__()
            logger.info("Data quality metrics reset")


class MetricsAggregator:
    """Aggregates metrics from multiple sources"""
    
    def __init__(self):
        self.symbol_metrics: Dict[str, DataQualityMetrics] = {}
        self.global_metrics = DataQualityMetrics()
    
    def get_or_create_symbol_metrics(self, symbol: str) -> DataQualityMetrics:
        """Get or create metrics for a symbol"""
        if symbol not in self.symbol_metrics:
            self.symbol_metrics[symbol] = DataQualityMetrics()
        return self.symbol_metrics[symbol]
    
    async def get_aggregated_summary(self) -> str:
        """Get summary across all symbols"""
        summaries = [f"GLOBAL METRICS:\n{self.global_metrics.get_summary()}"]
        
        for symbol, metrics in self.symbol_metrics.items():
            summaries.append(f"\n{symbol} METRICS:\n{metrics.get_summary()}")
        
        return "\n".join(summaries)
