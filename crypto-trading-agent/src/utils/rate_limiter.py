"""
Rate Limiter for API Calls
Prevents hitting Binance API rate limits (1200 requests/minute for futures)
"""
import asyncio
from collections import deque
from datetime import datetime, timedelta
from typing import Optional
from loguru import logger


class RateLimiter:
    """
    Sliding window rate limiter for API calls
    
    Ensures we don't exceed API rate limits by tracking requests
    in a sliding time window.
    """
    
    def __init__(
        self,
        max_requests: int = 1000,
        window_seconds: int = 60,
        name: str = "default"
    ):
        """
        Initialize rate limiter
        
        Args:
            max_requests: Maximum requests allowed in the window
            window_seconds: Time window in seconds
            name: Name for logging purposes
        """
        self.max_requests = max_requests
        self.window = timedelta(seconds=window_seconds)
        self.name = name
        self.requests = deque()  # Stores timestamps of requests
        self.lock = asyncio.Lock()  # Thread-safe access
        
        logger.info(
            f"RateLimiter '{name}' initialized: {max_requests} requests per {window_seconds}s"
        )
    
    async def acquire(self, weight: int = 1) -> None:
        """
        Acquire permission to make an API call
        
        This will block if we're at the rate limit until a slot becomes available.
        
        Args:
            weight: Request weight (some endpoints count as multiple requests)
        """
        async with self.lock:
            now = datetime.now()
            
            # Remove old requests outside the window
            while self.requests and now - self.requests[0][0] > self.window:
                self.requests.popleft()
            
            # Check if we're at the limit
            current_count = sum(w for _, w in self.requests)
            
            if current_count + weight > self.max_requests:
                # Calculate how long to wait
                oldest_request_time, _ = self.requests[0]
                wait_until = oldest_request_time + self.window
                wait_seconds = (wait_until - now).total_seconds()
                
                if wait_seconds > 0:
                    logger.warning(
                        f"RateLimiter '{self.name}' hit limit ({current_count}/{self.max_requests}). "
                        f"Waiting {wait_seconds:.2f}s..."
                    )
                    await asyncio.sleep(wait_seconds)
                    
                    # After waiting, remove old requests again
                    now = datetime.now()
                    while self.requests and now - self.requests[0][0] > self.window:
                        self.requests.popleft()
            
            # Record this request
            self.requests.append((now, weight))
            
            logger.debug(
                f"RateLimiter '{self.name}': {len(self.requests)}/{self.max_requests} requests in window"
            )
    
    async def try_acquire(self, weight: int = 1) -> bool:
        """
        Try to acquire permission without blocking
        
        Args:
            weight: Request weight
            
        Returns:
            True if acquired, False if would exceed limit
        """
        async with self.lock:
            now = datetime.now()
            
            # Remove old requests
            while self.requests and now - self.requests[0][0] > self.window:
                self.requests.popleft()
            
            # Check if we can make the request
            current_count = sum(w for _, w in self.requests)
            
            if current_count + weight <= self.max_requests:
                self.requests.append((now, weight))
                return True
            else:
                logger.debug(
                    f"RateLimiter '{self.name}': Cannot acquire "
                    f"({current_count + weight} would exceed {self.max_requests})"
                )
                return False
    
    def get_current_usage(self) -> dict:
        """
        Get current rate limiter statistics
        
        Returns:
            Dict with usage stats
        """
        now = datetime.now()
        
        # Count requests in current window
        valid_requests = [
            (ts, w) for ts, w in self.requests
            if now - ts <= self.window
        ]
        
        current_count = sum(w for _, w in valid_requests)
        
        return {
            'name': self.name,
            'current_requests': current_count,
            'max_requests': self.max_requests,
            'window_seconds': self.window.total_seconds(),
            'usage_percent': (current_count / self.max_requests) * 100,
            'available': self.max_requests - current_count
        }
    
    async def reset(self) -> None:
        """Reset the rate limiter (clear all tracked requests)"""
        async with self.lock:
            self.requests.clear()
            logger.info(f"RateLimiter '{self.name}' reset")


class MultiEndpointRateLimiter:
    """
    Manages rate limiters for multiple API endpoints
    
    Different endpoints may have different rate limits.
    """
    
    def __init__(self):
        self.limiters = {}
        self.default_limiter = RateLimiter(
            max_requests=1000,
            window_seconds=60,
            name="default"
        )
    
    def add_limiter(
        self,
        endpoint: str,
        max_requests: int,
        window_seconds: int = 60
    ) -> None:
        """
        Add a rate limiter for a specific endpoint
        
        Args:
            endpoint: Endpoint name/path
            max_requests: Max requests for this endpoint
            window_seconds: Time window
        """
        self.limiters[endpoint] = RateLimiter(
            max_requests=max_requests,
            window_seconds=window_seconds,
            name=endpoint
        )
        logger.info(f"Added rate limiter for endpoint: {endpoint}")
    
    async def acquire(self, endpoint: Optional[str] = None, weight: int = 1) -> None:
        """
        Acquire permission for an endpoint
        
        Args:
            endpoint: Endpoint name (uses default if None)
            weight: Request weight
        """
        limiter = self.limiters.get(endpoint, self.default_limiter)
        await limiter.acquire(weight)
    
    async def try_acquire(self, endpoint: Optional[str] = None, weight: int = 1) -> bool:
        """
        Try to acquire permission without blocking
        
        Args:
            endpoint: Endpoint name
            weight: Request weight
            
        Returns:
            True if acquired
        """
        limiter = self.limiters.get(endpoint, self.default_limiter)
        return await limiter.try_acquire(weight)
    
    def get_all_usage(self) -> dict:
        """Get usage stats for all limiters"""
        stats = {
            'default': self.default_limiter.get_current_usage()
        }
        
        for endpoint, limiter in self.limiters.items():
            stats[endpoint] = limiter.get_current_usage()
        
        return stats


# Global rate limiter instance for Binance API
binance_rate_limiter = MultiEndpointRateLimiter()

# Configure Binance-specific limits
binance_rate_limiter.add_limiter('klines', max_requests=1000, window_seconds=60)
binance_rate_limiter.add_limiter('depth', max_requests=500, window_seconds=60)
binance_rate_limiter.add_limiter('trades', max_requests=1000, window_seconds=60)
