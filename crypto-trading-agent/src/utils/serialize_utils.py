"""
Data Serialization Utilities for Message Bus
Fixes pandas serialization issues that cause ConfluenceScorer to receive string representations
"""
import pandas as pd
import numpy as np
from typing import Any, Dict, List
from datetime import datetime


def serialize_for_message_bus(data: Any) -> Any:
    """
    Serialize data for safe transmission through message bus.
    
    CRITICAL FIX: Converts pandas objects to JSON-safe formats to prevent
    the ConfluenceScorer from receiving string representations like "0    42500\n1    42600\n..."
    
    Args:
        data: Data to serialize (can be dict, list, DataFrame, Series, etc.)
        
    Returns:
        JSON-safe version of the data
    """
    if isinstance(data, pd.DataFrame):
        # Convert DataFrame to list of dicts
        return data.to_dict(orient='records')
    
    elif isinstance(data, pd.Series):
        # Convert Series to list
        return data.tolist()
    
    elif isinstance(data, np.ndarray):
        # Convert numpy array to list
        return data.tolist()
    
    elif isinstance(data, (np.integer, np.floating)):
        # Convert numpy scalars to Python types
        return float(data)
    
    elif isinstance(data, np.bool_):
        # Convert numpy bool to Python bool
        return bool(data)
    
    elif isinstance(data, datetime):
        # Convert datetime to ISO format string
        return data.isoformat()
    
    elif isinstance(data, dict):
        # Recursively serialize dict values
        return {key: serialize_for_message_bus(value) for key, value in data.items()}
    
    elif isinstance(data, (list, tuple)):
        # Recursively serialize list/tuple items
        return [serialize_for_message_bus(item) for item in data]
    
    elif pd.isna(data):
        # Convert NaN/None to None
        return None
    
    else:
        # Return as-is for primitive types (int, float, str, bool, None)
        return data


def deserialize_from_message_bus(data: Any, expected_type: str = None) -> Any:
    """
    Deserialize data received from message bus back to original types.
    
    Args:
        data: Data received from message bus
        expected_type: Optional hint about expected type ('dataframe', 'series', 'array')
        
    Returns:
        Deserialized data in appropriate format
    """
    if expected_type == 'dataframe' and isinstance(data, list):
        # Convert list of dicts back to DataFrame
        return pd.DataFrame(data)
    
    elif expected_type == 'series' and isinstance(data, list):
        # Convert list back to Series
        return pd.Series(data)
    
    elif expected_type == 'array' and isinstance(data, list):
        # Convert list back to numpy array
        return np.array(data)
    
    elif isinstance(data, dict):
        # Recursively deserialize dict values
        return {key: deserialize_from_message_bus(value) for key, value in data.items()}
    
    elif isinstance(data, list):
        # Recursively deserialize list items
        return [deserialize_from_message_bus(item) for item in data]
    
    else:
        # Return as-is
        return data
