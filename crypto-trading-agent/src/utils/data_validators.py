"""
Data Validators for WebSocket Messages
Ensures data integrity and prevents malformed data from corrupting the system
"""
from typing import List, Optional, Tuple
from datetime import datetime
from pydantic import BaseModel, Field, validator, model_validator
from loguru import logger


class KlineData(BaseModel):
    """Validator for Binance kline (candlestick) data"""
    
    timestamp: int = Field(..., gt=0, description="Candle open time in milliseconds")
    open: float = Field(..., gt=0, description="Open price")
    high: float = Field(..., gt=0, description="High price")
    low: float = Field(..., gt=0, description="Low price")
    close: float = Field(..., gt=0, description="Close price")
    volume: float = Field(..., ge=0, description="Volume")
    is_closed: bool = Field(..., description="Is candle closed")
    
    @validator('high')
    def high_gte_low(cls, v, values):
        """Ensure high >= low"""
        if 'low' in values and v < values['low']:
            raise ValueError(f'High ({v}) must be >= Low ({values["low"]})')
        return v
    
    @validator('high')
    def high_gte_open_close(cls, v, values):
        """Ensure high >= open and close"""
        if 'open' in values and v < values['open']:
            raise ValueError(f'High ({v}) must be >= Open ({values["open"]})')
        if 'close' in values and v < values['close']:
            raise ValueError(f'High ({v}) must be >= Close ({values["close"]})')
        return v
    
    @validator('low')
    def low_lte_open_close(cls, v, values):
        """Ensure low <= open and close"""
        if 'open' in values and v > values['open']:
            raise ValueError(f'Low ({v}) must be <= Open ({values["open"]})')
        if 'close' in values and v > values['close']:
            raise ValueError(f'Low ({v}) must be <= Close ({values["close"]})')
        return v
    
    @validator('open', 'high', 'low', 'close')
    def price_reasonable(cls, v):
        """Ensure price is within reasonable bounds (not NaN, Inf, or extreme values)"""
        if v != v:  # Check for NaN
            raise ValueError('Price cannot be NaN')
        if v == float('inf') or v == float('-inf'):
            raise ValueError('Price cannot be infinite')
        if v > 1_000_000_000:  # Sanity check for extremely high prices
            raise ValueError(f'Price {v} exceeds reasonable bounds')
        return v
    
    @validator('volume')
    def volume_reasonable(cls, v):
        """Ensure volume is reasonable"""
        if v != v:  # Check for NaN
            raise ValueError('Volume cannot be NaN')
        if v == float('inf'):
            raise ValueError('Volume cannot be infinite')
        return v
    
    class Config:
        extra = 'ignore'  # Ignore extra fields from Binance


class DepthData(BaseModel):
    """Validator for order book depth data"""
    
    timestamp: int = Field(..., gt=0, description="Update time in milliseconds")
    bids: List[Tuple[float, float]] = Field(..., min_items=1, description="Bid levels [price, quantity]")
    asks: List[Tuple[float, float]] = Field(..., min_items=1, description="Ask levels [price, quantity]")
    
    @validator('bids', 'asks', each_item=True)
    def validate_level(cls, v):
        """Validate each price level"""
        price, quantity = v
        if price <= 0:
            raise ValueError(f'Price {price} must be positive')
        if quantity < 0:
            raise ValueError(f'Quantity {quantity} cannot be negative')
        if price != price or quantity != quantity:  # NaN check
            raise ValueError('Price or quantity cannot be NaN')
        return v
    
    @model_validator(mode='after')
    def validate_spread(self):
        """Ensure best ask > best bid"""
        bids = self.bids
        asks = self.asks
        
        if bids and asks:
            best_bid = bids[0][0]
            best_ask = asks[0][0]
            
            if best_ask <= best_bid:
                raise ValueError(f'Best ask ({best_ask}) must be > best bid ({best_bid})')
        
        return self
    
    class Config:
        extra = 'ignore'


class FundingRateData(BaseModel):
    """Validator for funding rate data"""
    
    timestamp: int = Field(..., gt=0, description="Update time in milliseconds")
    symbol: str = Field(..., min_length=1, description="Trading symbol")
    funding_rate: float = Field(..., description="Funding rate")
    
    @validator('funding_rate')
    def funding_rate_reasonable(cls, v):
        """Ensure funding rate is within reasonable bounds"""
        if v != v:  # NaN check
            raise ValueError('Funding rate cannot be NaN')
        if abs(v) > 0.1:  # 10% funding rate is extreme
            logger.warning(f'Extreme funding rate detected: {v:.4f}')
        return v
    
    class Config:
        extra = 'ignore'


class TickerData(BaseModel):
    """Validator for 24hr ticker data"""
    
    symbol: str = Field(..., min_length=1, description="Trading symbol")
    price: float = Field(..., gt=0, description="Last price")
    price_change_percent: float = Field(..., description="24h price change %")
    volume: float = Field(..., ge=0, description="24h volume")
    
    @validator('price')
    def price_reasonable(cls, v):
        """Ensure price is reasonable"""
        if v != v:  # NaN check
            raise ValueError('Price cannot be NaN')
        if v == float('inf') or v == float('-inf'):
            raise ValueError('Price cannot be infinite')
        if v > 1_000_000_000:
            raise ValueError(f'Price {v} exceeds reasonable bounds')
        return v
    
    @validator('price_change_percent')
    def price_change_reasonable(cls, v):
        """Ensure price change is reasonable"""
        if v != v:  # NaN check
            raise ValueError('Price change cannot be NaN')
        if abs(v) > 100:  # 100% change in 24h is extreme but possible
            logger.warning(f'Extreme price change detected: {v:.2f}%')
        return v
    
    class Config:
        extra = 'ignore'


def validate_kline_message(data: dict) -> Optional[KlineData]:
    """
    Validate and parse kline WebSocket message
    
    Args:
        data: Raw WebSocket message
        
    Returns:
        Validated KlineData or None if invalid
    """
    try:
        kline = data.get('k')
        if not kline:
            logger.error("Missing 'k' field in kline message")
            return None
        
        validated = KlineData(
            timestamp=kline['t'],
            open=float(kline['o']),
            high=float(kline['h']),
            low=float(kline['l']),
            close=float(kline['c']),
            volume=float(kline['v']),
            is_closed=kline['x']
        )
        return validated
        
    except ValueError as e:
        logger.error(f"Kline validation failed: {e}")
        return None
    except KeyError as e:
        logger.error(f"Missing required field in kline data: {e}")
        return None
    except Exception as e:
        logger.error(f"Unexpected error validating kline: {e}")
        return None


def validate_depth_message(data: dict) -> Optional[DepthData]:
    """
    Validate and parse depth WebSocket message
    
    Args:
        data: Raw WebSocket message
        
    Returns:
        Validated DepthData or None if invalid
    """
    try:
        bids = [[float(p), float(q)] for p, q in data.get('b', [])]
        asks = [[float(p), float(q)] for p, q in data.get('a', [])]
        
        if not bids or not asks:
            logger.warning("Depth message missing bids or asks")
            return None
        
        validated = DepthData(
            timestamp=data['E'],
            bids=bids,
            asks=asks
        )
        return validated
        
    except ValueError as e:
        logger.error(f"Depth validation failed: {e}")
        return None
    except KeyError as e:
        logger.error(f"Missing required field in depth data: {e}")
        return None
    except Exception as e:
        logger.error(f"Unexpected error validating depth: {e}")
        return None


def validate_funding_rate_message(data: dict) -> Optional[FundingRateData]:
    """
    Validate and parse funding rate WebSocket message
    
    Args:
        data: Raw WebSocket message
        
    Returns:
        Validated FundingRateData or None if invalid
    """
    try:
        validated = FundingRateData(
            timestamp=data['E'],
            symbol=data['s'],
            funding_rate=float(data['r'])
        )
        return validated
        
    except ValueError as e:
        logger.error(f"Funding rate validation failed: {e}")
        return None
    except KeyError as e:
        logger.error(f"Missing required field in funding rate data: {e}")
        return None
    except Exception as e:
        logger.error(f"Unexpected error validating funding rate: {e}")
        return None


def validate_ticker_message(data: dict) -> Optional[TickerData]:
    """
    Validate and parse ticker WebSocket message
    
    Args:
        data: Raw WebSocket message
        
    Returns:
        Validated TickerData or None if invalid
    """
    try:
        validated = TickerData(
            symbol=data['s'],
            price=float(data['c']),
            price_change_percent=float(data['P']),
            volume=float(data['v'])
        )
        return validated
        
    except ValueError as e:
        logger.error(f"Ticker validation failed: {e}")
        return None
    except KeyError as e:
        logger.error(f"Missing required field in ticker data: {e}")
        return None
    except Exception as e:
        logger.error(f"Unexpected error validating ticker: {e}")
        return None
