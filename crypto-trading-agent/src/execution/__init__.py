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

from src.execution.execution_agent import ExecutionAgent
from src.execution.emergency_exit import EmergencyExit

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
