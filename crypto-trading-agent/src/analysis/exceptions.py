"""
Custom Exceptions for Market Analysis
Provides specific exception types for better error handling and debugging.
"""
from typing import Optional, Dict, Any


class MarketAnalysisError(Exception):
    """Base exception for market analysis errors"""
    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None):
        self.message = message
        self.details = details or {}
        super().__init__(self.message)
    
    def __str__(self):
        if self.details:
            return f"{self.message} | Details: {self.details}"
        return self.message


# ============================================================================
# Data Validation Errors
# ============================================================================

class DataValidationError(MarketAnalysisError):
    """Raised when data validation fails"""
    pass


class InvalidTimeframeError(DataValidationError):
    """Raised when an invalid timeframe is provided"""
    pass


class InvalidIndicatorDataError(DataValidationError):
    """Raised when indicator data is invalid or incomplete"""
    pass


class InvalidPriceDataError(DataValidationError):
    """Raised when price/OHLCV data is invalid"""
    pass


# ============================================================================
# Component Errors
# ============================================================================

class IndicatorCalculationError(MarketAnalysisError):
    """Raised when indicator calculation fails"""
    pass


class SMCDetectionError(MarketAnalysisError):
    """Raised when SMC detection fails"""
    pass


class ICTDetectionError(MarketAnalysisError):
    """Raised when ICT detection fails"""
    pass


class RegimeDetectionError(MarketAnalysisError):
    """Raised when regime detection fails"""
    pass


class ConfluenceScoringError(MarketAnalysisError):
    """Raised when confluence scoring fails"""
    pass


# ============================================================================
# LLM Errors
# ============================================================================

class LLMError(MarketAnalysisError):
    """Base exception for LLM-related errors"""
    pass


class LLMTimeoutError(LLMError):
    """Raised when LLM request times out"""
    pass


class LLMResponseError(LLMError):
    """Raised when LLM response is invalid or cannot be parsed"""
    pass


class LLMQuotaExceededError(LLMError):
    """Raised when LLM API quota is exceeded"""
    pass


# ============================================================================
# Integration Errors
# ============================================================================

class DataFlowError(MarketAnalysisError):
    """Raised when data flow between components fails"""
    pass


class TypeMismatchError(DataFlowError):
    """Raised when data types don't match expected format"""
    pass


class MissingDataError(DataFlowError):
    """Raised when required data is missing"""
    pass


# ============================================================================
# Trade Setup Errors
# ============================================================================

class TradeSetupError(MarketAnalysisError):
    """Base exception for trade setup errors"""
    pass


class InvalidEntryZoneError(TradeSetupError):
    """Raised when entry zone is invalid"""
    pass


class InvalidStopLossError(TradeSetupError):
    """Raised when stop loss is invalid"""
    pass


class InvalidTakeProfitError(TradeSetupError):
    """Raised when take profit levels are invalid"""
    pass


class InsufficientConfluenceError(TradeSetupError):
    """Raised when confluence count is below minimum"""
    pass


# ============================================================================
# Error Handler Utilities
# ============================================================================

class ErrorContext:
    """Context manager for error handling with logging"""
    def __init__(self, operation: str, logger, raise_on_error: bool = True):
        self.operation = operation
        self.logger = logger
        self.raise_on_error = raise_on_error
        self.error = None
    
    def __enter__(self):
        self.logger.debug(f"Starting: {self.operation}")
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        if exc_type is not None:
            self.error = exc_val
            self.logger.error(
                f"Error in {self.operation}: {exc_type.__name__}: {exc_val}",
                exc_info=True
            )
            if self.raise_on_error:
                return False  # Re-raise the exception
            return True  # Suppress the exception
        else:
            self.logger.debug(f"Completed: {self.operation}")
        return False


def handle_error(error: Exception, context: str, logger) -> MarketAnalysisError:
    """
    Convert generic exceptions to specific MarketAnalysisError types
    
    Args:
        error: The original exception
        context: Context where the error occurred
        logger: Logger instance
        
    Returns:
        Appropriate MarketAnalysisError subclass
    """
    error_msg = f"{context}: {str(error)}"
    details = {
        'original_error': type(error).__name__,
        'context': context
    }
    
    # Map common errors to specific types
    if isinstance(error, (ValueError, TypeError)):
        if 'indicator' in context.lower():
            return InvalidIndicatorDataError(error_msg, details)
        elif 'price' in context.lower() or 'ohlcv' in context.lower():
            return InvalidPriceDataError(error_msg, details)
        elif 'timeframe' in context.lower():
            return InvalidTimeframeError(error_msg, details)
        else:
            return DataValidationError(error_msg, details)
    
    elif isinstance(error, KeyError):
        return MissingDataError(error_msg, details)
    
    elif isinstance(error, TimeoutError):
        return LLMTimeoutError(error_msg, details)
    
    # Default to base error
    return MarketAnalysisError(error_msg, details)
