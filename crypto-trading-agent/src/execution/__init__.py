"""
Execution Module
Handles order placement and execution on exchanges
"""

from src.execution.exchange_client import (
    ExchangeClient,
    BingXClient,
    CoinDCXClient,
    ExchangeClientFactory,
    Order,
    Position,
    OrderType,
    OrderSide,
    OrderStatus
)

from src.execution.order_manager import (
    OrderManager,
    TradeExecution,
    ExecutionStrategy
)

from src.execution.order_tracker import (
    OrderTracker,
    OrderUpdate
)

from src.execution.error_handler import (
    ExchangeException,
    RateLimitException,
    InsufficientBalanceException,
    OrderRejectedException,
    NetworkException,
    AuthenticationException,
    InvalidParameterException,
    CircuitBreaker,
    RetryHandler,
    ErrorClassifier,
    ErrorRecoveryStrategy
)

# ExecutionAgent / EmergencyExit pull in the full agent + DB + LLM stack
# (base_agent -> state_manager -> sqlalchemy, message_bus -> redis, ...). Import
# them lazily (PEP 562) so lightweight consumers of this package — e.g. just the
# exchange client or error types — don't drag in that whole chain. The package-level
# names `ExecutionAgent` and `EmergencyExit` still resolve on first access.
def __getattr__(name):
    if name == "ExecutionAgent":
        from src.execution.execution_agent import ExecutionAgent
        return ExecutionAgent
    if name == "EmergencyExit":
        from src.execution.emergency_exit import EmergencyExit
        return EmergencyExit
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = [
    # Exchange Client
    'ExchangeClient',
    'BingXClient',
    'CoinDCXClient',
    'ExchangeClientFactory',
    'Order',
    'Position',
    'OrderType',
    'OrderSide',
    'OrderStatus',
    
    # Order Manager
    'OrderManager',
    'TradeExecution',
    'ExecutionStrategy',
    
    # Order Tracker
    'OrderTracker',
    'OrderUpdate',
    
    # Error Handling
    'ExchangeException',
    'RateLimitException',
    'InsufficientBalanceException',
    'OrderRejectedException',
    'NetworkException',
    'AuthenticationException',
    'InvalidParameterException',
    'CircuitBreaker',
    'RetryHandler',
    'ErrorClassifier',
    'ErrorRecoveryStrategy',
    
    # Agent Core
    'ExecutionAgent',
    'EmergencyExit',
]
