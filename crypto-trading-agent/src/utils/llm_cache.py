"""
LLM Response Cache
Caches LLM responses to avoid redundant API calls and reduce costs
"""
import hashlib
import json
from datetime import datetime, timedelta, timezone
from typing import Dict, Any, Optional, Callable
from loguru import logger
import asyncio


class LLMResponseCache:
    """
    Intelligent cache for LLM responses
    
    Caches based on computational analysis results (not raw candles)
    to avoid re-analyzing the same market conditions.
    """
    
    def __init__(
        self,
        ttl_seconds: int = 300,  # 5 minutes default
        max_cache_size: int = 1000,
        name: str = "llm_cache"
    ):
        """
        Initialize LLM response cache
        
        Args:
            ttl_seconds: Time-to-live for cached responses
            max_cache_size: Maximum number of cached responses
            name: Cache name for logging
        """
        self.ttl = timedelta(seconds=ttl_seconds)
        self.max_cache_size = max_cache_size
        self.name = name
        
        # Cache storage: {cache_key: (response, timestamp)}
        self.cache: Dict[str, tuple[Any, datetime]] = {}
        
        # Cache statistics
        self.stats = {
            'hits': 0,
            'misses': 0,
            'evictions': 0,
            'total_calls': 0
        }
        
        # Lock for thread-safe access
        self.lock = asyncio.Lock()
        
        logger.info(
            f"LLMResponseCache '{name}' initialized: "
            f"TTL={ttl_seconds}s, Max Size={max_cache_size}"
        )
    
    def _generate_cache_key(self, context: Dict[str, Any]) -> str:
        """
        Generate cache key from computational analysis results
        
        We hash the computational results (not raw candles) because:
        - Same market structure = same analysis needed
        - Reduces cache size dramatically
        - Candles change constantly, but structure changes slowly
        
        Args:
            context: Analysis context with computational results
            
        Returns:
            SHA256 hash of relevant context
        """
        # Extract only the stable computational results
        cache_input = {
            'symbol': context.get('symbol'),
            'timeframe': context.get('primary_timeframe'),
            # Multi-timeframe bias (changes slowly)
            'mtf_bias': context.get('computational_analysis', {}).get('mtf_analysis', {}).get('overall_bias'),
            # SMC structure (order blocks, FVGs, BOS)
            'smc_structure': {
                'order_blocks': len(context.get('computational_analysis', {}).get('smc_analysis', {}).get('order_blocks', [])),
                'fvgs': len(context.get('computational_analysis', {}).get('smc_analysis', {}).get('fair_value_gaps', [])),
                'bos_count': context.get('computational_analysis', {}).get('smc_analysis', {}).get('bos_count', 0),
            },
            # ICT setup (killzone, sweeps)
            'ict_setup': {
                'in_killzone': context.get('computational_analysis', {}).get('ict_analysis', {}).get('in_killzone', False),
                'sweep_detected': context.get('computational_analysis', {}).get('ict_analysis', {}).get('sweep_detected', False),
            },
            # Key indicator values (rounded to reduce cache misses)
            'indicators': {
                'rsi_14': round(context.get('computational_analysis', {}).get('indicators', {}).get('rsi_14', 0), 0),
                'trend': context.get('computational_analysis', {}).get('indicators', {}).get('trend', 'neutral'),
            }
        }
        
        # Create deterministic JSON string
        cache_str = json.dumps(cache_input, sort_keys=True)
        
        # Generate SHA256 hash
        cache_key = hashlib.sha256(cache_str.encode()).hexdigest()
        
        return cache_key
    
    async def get_or_compute(
        self,
        context: Dict[str, Any],
        llm_call_fn: Callable,
        *args,
        **kwargs
    ) -> Any:
        """
        Get cached response or compute new one
        
        Args:
            context: Analysis context
            llm_call_fn: Async function to call LLM if cache miss
            *args, **kwargs: Arguments to pass to llm_call_fn
            
        Returns:
            LLM response (cached or fresh)
        """
        async with self.lock:
            self.stats['total_calls'] += 1
            
            # Generate cache key
            cache_key = self._generate_cache_key(context)
            
            # Check cache
            if cache_key in self.cache:
                cached_response, timestamp = self.cache[cache_key]
                
                # Check if still valid
                age = datetime.now(timezone.utc) - timestamp
                if age < self.ttl:
                    self.stats['hits'] += 1
                    hit_rate = (self.stats['hits'] / self.stats['total_calls']) * 100
                    
                    logger.info(
                        f"LLM Cache HIT ({self.name}): Saved API call! "
                        f"Hit rate: {hit_rate:.1f}% | Age: {age.total_seconds():.0f}s"
                    )
                    return cached_response
                else:
                    # Expired - remove it
                    del self.cache[cache_key]
                    logger.debug(f"Cache entry expired (age: {age.total_seconds():.0f}s)")
        
        # Cache miss - call LLM
        self.stats['misses'] += 1
        logger.info(
            f"LLM Cache MISS ({self.name}): Calling LLM... "
            f"Hit rate: {(self.stats['hits'] / self.stats['total_calls']) * 100:.1f}%"
        )
        
        # Call LLM (outside lock to avoid blocking)
        response = await llm_call_fn(context, *args, **kwargs)
        
        # Store in cache
        async with self.lock:
            # Check cache size and evict oldest if needed
            if len(self.cache) >= self.max_cache_size:
                # Find oldest entry
                oldest_key = min(
                    self.cache.keys(),
                    key=lambda k: self.cache[k][1]
                )
                del self.cache[oldest_key]
                self.stats['evictions'] += 1
                logger.debug(f"Cache full - evicted oldest entry")
            
            # Store new response
            self.cache[cache_key] = (response, datetime.now(timezone.utc))
            logger.debug(f"Cached new LLM response (cache size: {len(self.cache)})")
        
        return response
    
    async def invalidate(self, context: Optional[Dict[str, Any]] = None):
        """
        Invalidate cache entries
        
        Args:
            context: If provided, invalidate specific entry. Otherwise clear all.
        """
        async with self.lock:
            if context:
                cache_key = self._generate_cache_key(context)
                if cache_key in self.cache:
                    del self.cache[cache_key]
                    logger.info(f"Invalidated cache entry for {context.get('symbol')}")
            else:
                self.cache.clear()
                logger.info(f"Cleared all cache entries ({self.name})")
    
    def get_stats(self) -> Dict[str, Any]:
        """Get cache statistics"""
        total = self.stats['total_calls']
        hit_rate = (self.stats['hits'] / total * 100) if total > 0 else 0
        
        return {
            'name': self.name,
            'cache_size': len(self.cache),
            'max_size': self.max_cache_size,
            'ttl_seconds': self.ttl.total_seconds(),
            'total_calls': total,
            'hits': self.stats['hits'],
            'misses': self.stats['misses'],
            'hit_rate_percent': round(hit_rate, 2),
            'evictions': self.stats['evictions'],
            'estimated_cost_savings_usd': self.stats['hits'] * 0.015  # ~$0.015 per Claude call
        }
    
    async def log_stats(self):
        """Log cache statistics"""
        stats = self.get_stats()
        logger.info(
            f"\n{'='*60}\n"
            f"LLM Cache Stats ({self.name}):\n"
            f"  Total Calls: {stats['total_calls']}\n"
            f"  Cache Hits: {stats['hits']} ({stats['hit_rate_percent']}%)\n"
            f"  Cache Misses: {stats['misses']}\n"
            f"  Cache Size: {stats['cache_size']}/{stats['max_size']}\n"
            f"  Evictions: {stats['evictions']}\n"
            f"  Estimated Savings: ${stats['estimated_cost_savings_usd']:.2f}\n"
            f"{'='*60}"
        )


# Global cache instances for different agents
analysis_llm_cache = LLMResponseCache(
    ttl_seconds=300,  # 5 minutes
    max_cache_size=1000,
    name="analysis_agent"
)

strategy_llm_cache = LLMResponseCache(
    ttl_seconds=180,  # 3 minutes (strategies need to be fresher)
    max_cache_size=500,
    name="strategy_agent"
)
