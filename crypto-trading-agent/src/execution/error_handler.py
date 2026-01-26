"""
Exchange Error Handling
Comprehensive error handling and recovery for exchange operations
"""
from typing import Optional, Callable, Any
from enum import Enum
import time
import asyncio
from loguru import logger
from datetime import datetime, timedelta


class ExchangeException(Exception):
    """Base exception for exchange errors"""
    def __init__(self, message: str, error_code: Optional[str] = None):
        self.message = message
        self.error_code = error_code
        super().__init__(self.message)


class RateLimitException(ExchangeException):
    """Rate limit exceeded"""
    pass


class InsufficientBalanceException(ExchangeException):
    """Insufficient balance for order"""
    pass


class OrderRejectedException(ExchangeException):
    """Order rejected by exchange"""
    pass


class NetworkException(ExchangeException):
    """Network connectivity error"""
    pass


class AuthenticationException(ExchangeException):
    """Authentication failed"""
    pass


class InvalidParameterException(ExchangeException):
    """Invalid order parameters"""
    pass


class CircuitBreakerState(Enum):
    """Circuit breaker states"""
    CLOSED = "closed"      # Normal operation
    OPEN = "open"          # Blocking requests
    HALF_OPEN = "half_open"  # Testing recovery


class CircuitBreaker:
    """
    Circuit breaker for API failures
    Prevents cascading failures by blocking requests after threshold
    """
    
    def __init__(
        self,
        failure_threshold: int = 5,
        recovery_timeout: int = 60,
        half_open_max_calls: int = 3
    ):
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.half_open_max_calls = half_open_max_calls
        
        self.failure_count = 0
        self.last_failure_time: Optional[datetime] = None
        self.state = CircuitBreakerState.CLOSED
        self.half_open_calls = 0
        
        logger.info(
            f"Circuit breaker initialized: "
            f"threshold={failure_threshold}, timeout={recovery_timeout}s"
        )
    
    def record_success(self):
        """Record successful API call"""
        if self.state == CircuitBreakerState.HALF_OPEN:
            self.half_open_calls += 1
            if self.half_open_calls >= self.half_open_max_calls:
                # Recovered successfully
                self._close()
        elif self.state == CircuitBreakerState.CLOSED:
            # Reset failure count on success
            self.failure_count = 0
    
    def record_failure(self):
        """Record failed API call"""
        self.failure_count += 1
        self.last_failure_time = datetime.now()
        
        if self.failure_count >= self.failure_threshold:
            self._open()
    
    def can_execute(self) -> bool:
        """Check if request can be executed"""
        if self.state == CircuitBreakerState.CLOSED:
            return True
        
        if self.state == CircuitBreakerState.OPEN:
            # Check if recovery timeout has passed
            if self.last_failure_time:
                elapsed = (datetime.now() - self.last_failure_time).total_seconds()
                if elapsed >= self.recovery_timeout:
                    self._half_open()
                    return True
            return False
        
        if self.state == CircuitBreakerState.HALF_OPEN:
            return self.half_open_calls < self.half_open_max_calls
        
        return False
    
    def _open(self):
        """Open circuit breaker (block requests)"""
        self.state = CircuitBreakerState.OPEN
        logger.error(
            f"🚨 Circuit breaker OPENED after {self.failure_count} failures. "
            f"Blocking requests for {self.recovery_timeout}s"
        )
    
    def _half_open(self):
        """Half-open circuit breaker (test recovery)"""
        self.state = CircuitBreakerState.HALF_OPEN
        self.half_open_calls = 0
        logger.warning("Circuit breaker HALF-OPEN. Testing recovery...")
    
    def _close(self):
        """Close circuit breaker (normal operation)"""
        self.state = CircuitBreakerState.CLOSED
        self.failure_count = 0
        self.half_open_calls = 0
        logger.info("✅ Circuit breaker CLOSED. Normal operation resumed.")
    
    def get_state(self) -> str:
        """Get current state"""
        return self.state.value


class RetryHandler:
    """
    Retry handler with exponential backoff
    """
    
    def __init__(
        self,
        max_retries: int = 3,
        base_delay: float = 1.0,
        max_delay: float = 60.0,
        exponential_base: float = 2.0
    ):
        self.max_retries = max_retries
        self.base_delay = base_delay
        self.max_delay = max_delay
        self.exponential_base = exponential_base
    
    async def execute_with_retry(
        self,
        func: Callable,
        *args,
        **kwargs
    ) -> Any:
        """
        Execute function with retry logic
        
        Args:
            func: Async function to execute
            *args: Function arguments
            **kwargs: Function keyword arguments
            
        Returns:
            Function result
            
        Raises:
            Last exception if all retries fail
        """
        last_exception = None
        
        for attempt in range(self.max_retries + 1):
            try:
                result = await func(*args, **kwargs)
                
                if attempt > 0:
                    logger.info(f"✅ Retry successful on attempt {attempt + 1}")
                
                return result
                
            except (NetworkException, RateLimitException) as e:
                last_exception = e
                
                if attempt < self.max_retries:
                    delay = self._calculate_delay(attempt)
                    logger.warning(
                        f"Attempt {attempt + 1}/{self.max_retries + 1} failed: {e}. "
                        f"Retrying in {delay:.2f}s..."
                    )
                    await asyncio.sleep(delay)
                else:
                    logger.error(
                        f"All {self.max_retries + 1} attempts failed. "
                        f"Last error: {e}"
                    )
            
            except (AuthenticationException, InvalidParameterException) as e:
                # Don't retry on these errors
                logger.error(f"Non-retryable error: {e}")
                raise
        
        # All retries exhausted
        if last_exception:
            raise last_exception
    
    def _calculate_delay(self, attempt: int) -> float:
        """Calculate exponential backoff delay"""
        delay = self.base_delay * (self.exponential_base ** attempt)
        return min(delay, self.max_delay)


class ErrorClassifier:
    """
    Classify exchange errors into appropriate exception types
    """
    
    @staticmethod
    def classify_error(error_message: str, error_code: Optional[str] = None) -> ExchangeException:
        """
        Classify error message into specific exception type
        
        Args:
            error_message: Error message from exchange
            error_code: Optional error code
            
        Returns:
            Appropriate ExchangeException subclass
        """
        error_lower = error_message.lower()
        
        # Rate limit errors
        if any(keyword in error_lower for keyword in ['rate limit', 'too many requests', '429']):
            return RateLimitException(error_message, error_code)
        
        # Balance errors
        if any(keyword in error_lower for keyword in ['insufficient', 'balance', 'funds']):
            return InsufficientBalanceException(error_message, error_code)
        
        # Authentication errors
        if any(keyword in error_lower for keyword in ['auth', 'signature', 'api key', 'unauthorized', '401']):
            return AuthenticationException(error_message, error_code)
        
        # Order rejection
        if any(keyword in error_lower for keyword in ['rejected', 'invalid order', 'order failed']):
            return OrderRejectedException(error_message, error_code)
        
        # Network errors
        if any(keyword in error_lower for keyword in ['timeout', 'connection', 'network', 'unreachable']):
            return NetworkException(error_message, error_code)
        
        # Invalid parameters
        if any(keyword in error_lower for keyword in ['invalid', 'parameter', 'bad request', '400']):
            return InvalidParameterException(error_message, error_code)
        
        # Default to base exception
        return ExchangeException(error_message, error_code)


class ErrorRecoveryStrategy:
    """
    Define recovery strategies for different error types
    """
    
    @staticmethod
    async def handle_rate_limit(delay: int = 60):
        """Handle rate limit error"""
        logger.warning(f"Rate limit hit. Waiting {delay}s before retry...")
        await asyncio.sleep(delay)
    
    @staticmethod
    async def handle_network_error(retry_count: int = 3):
        """Handle network error"""
        logger.warning(f"Network error. Will retry {retry_count} times...")
        # Retry logic handled by RetryHandler
    
    @staticmethod
    async def handle_insufficient_balance():
        """Handle insufficient balance"""
        logger.error("Insufficient balance. Cannot proceed with order.")
        # Should trigger circuit breaker or alert
        raise InsufficientBalanceException("Insufficient balance to execute order")
    
    @staticmethod
    async def handle_authentication_error():
        """Handle authentication error"""
        logger.error("Authentication failed. Check API credentials.")
        raise AuthenticationException("Invalid API credentials")
