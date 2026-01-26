"""
Unit tests for Error Handler
"""
import pytest
import asyncio
from unittest.mock import AsyncMock

from src.execution.error_handler import (
    ExchangeException,
    RateLimitException,
    InsufficientBalanceException,
    OrderRejectedException,
    NetworkException,
    AuthenticationException,
    InvalidParameterException,
    CircuitBreaker,
    CircuitBreakerState,
    RetryHandler,
    ErrorClassifier
)


def test_exception_hierarchy():
    """Test exception inheritance"""
    
    exc = RateLimitException("Rate limit exceeded", "429")
    
    assert isinstance(exc, ExchangeException)
    assert exc.message == "Rate limit exceeded"
    assert exc.error_code == "429"


def test_error_classifier_rate_limit():
    """Test error classification for rate limits"""
    
    exc = ErrorClassifier.classify_error("Too many requests", "429")
    
    assert isinstance(exc, RateLimitException)


def test_error_classifier_insufficient_balance():
    """Test error classification for balance errors"""
    
    exc = ErrorClassifier.classify_error("Insufficient funds")
    
    assert isinstance(exc, InsufficientBalanceException)


def test_error_classifier_authentication():
    """Test error classification for auth errors"""
    
    exc = ErrorClassifier.classify_error("Invalid API key")
    
    assert isinstance(exc, AuthenticationException)


def test_error_classifier_network():
    """Test error classification for network errors"""
    
    exc = ErrorClassifier.classify_error("Connection timeout")
    
    assert isinstance(exc, NetworkException)


def test_circuit_breaker_initial_state():
    """Test circuit breaker initial state"""
    
    cb = CircuitBreaker(failure_threshold=3, recovery_timeout=10)
    
    assert cb.state == CircuitBreakerState.CLOSED
    assert cb.can_execute() is True


def test_circuit_breaker_opens_after_failures():
    """Test circuit breaker opens after threshold"""
    
    cb = CircuitBreaker(failure_threshold=3)
    
    # Record failures
    cb.record_failure()
    cb.record_failure()
    assert cb.state == CircuitBreakerState.CLOSED
    
    cb.record_failure()
    assert cb.state == CircuitBreakerState.OPEN
    assert cb.can_execute() is False


def test_circuit_breaker_success_resets_count():
    """Test success resets failure count"""
    
    cb = CircuitBreaker(failure_threshold=3)
    
    cb.record_failure()
    cb.record_failure()
    cb.record_success()
    
    assert cb.failure_count == 0
    assert cb.state == CircuitBreakerState.CLOSED


def test_circuit_breaker_half_open():
    """Test circuit breaker half-open state"""
    
    cb = CircuitBreaker(failure_threshold=2, recovery_timeout=0)
    
    # Open the circuit
    cb.record_failure()
    cb.record_failure()
    assert cb.state == CircuitBreakerState.OPEN
    
    # Should transition to half-open
    assert cb.can_execute() is True
    assert cb.state == CircuitBreakerState.HALF_OPEN


def test_circuit_breaker_recovery():
    """Test circuit breaker recovery"""
    
    cb = CircuitBreaker(failure_threshold=2, recovery_timeout=0, half_open_max_calls=2)
    
    # Open the circuit
    cb.record_failure()
    cb.record_failure()
    
    # Transition to half-open
    cb.can_execute()
    
    # Successful calls should close circuit
    cb.record_success()
    cb.record_success()
    
    assert cb.state == CircuitBreakerState.CLOSED


@pytest.mark.asyncio
async def test_retry_handler_success_first_try():
    """Test retry handler succeeds on first try"""
    
    retry = RetryHandler(max_retries=3)
    
    async def success_func():
        return "success"
    
    result = await retry.execute_with_retry(success_func)
    
    assert result == "success"


@pytest.mark.asyncio
async def test_retry_handler_retries_on_network_error():
    """Test retry handler retries on network errors"""
    
    retry = RetryHandler(max_retries=2, base_delay=0.1)
    
    call_count = 0
    
    async def failing_func():
        nonlocal call_count
        call_count += 1
        if call_count < 3:
            raise NetworkException("Connection failed")
        return "success"
    
    result = await retry.execute_with_retry(failing_func)
    
    assert result == "success"
    assert call_count == 3


@pytest.mark.asyncio
async def test_retry_handler_exhausts_retries():
    """Test retry handler exhausts all retries"""
    
    retry = RetryHandler(max_retries=2, base_delay=0.1)
    
    async def always_fails():
        raise NetworkException("Always fails")
    
    with pytest.raises(NetworkException):
        await retry.execute_with_retry(always_fails)


@pytest.mark.asyncio
async def test_retry_handler_no_retry_on_auth_error():
    """Test retry handler doesn't retry auth errors"""
    
    retry = RetryHandler(max_retries=3)
    
    call_count = 0
    
    async def auth_error():
        nonlocal call_count
        call_count += 1
        raise AuthenticationException("Invalid credentials")
    
    with pytest.raises(AuthenticationException):
        await retry.execute_with_retry(auth_error)
    
    # Should only be called once (no retries)
    assert call_count == 1


def test_retry_handler_exponential_backoff():
    """Test exponential backoff calculation"""
    
    retry = RetryHandler(base_delay=1.0, exponential_base=2.0, max_delay=10.0)
    
    assert retry._calculate_delay(0) == 1.0
    assert retry._calculate_delay(1) == 2.0
    assert retry._calculate_delay(2) == 4.0
    assert retry._calculate_delay(3) == 8.0
    assert retry._calculate_delay(4) == 10.0  # Capped at max_delay
