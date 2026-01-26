"""
Pandas Serialization Utilities
Handles conversion of pandas objects to JSON-safe formats for message bus transmission
"""
from typing import Any, Dict, List
import pandas as pd
from loguru import logger


def serialize_pandas_object(obj: Any) -> Any:
    """
    Recursively serialize pandas objects to JSON-safe formats
    
    Args:
        obj: Any object that may contain pandas DataFrames or Series
        
    Returns:
        JSON-safe version of the object
    """
    if isinstance(obj, pd.DataFrame):
        # Convert DataFrame to list of dicts (records format)
        return obj.to_dict(orient='records')
    
    elif isinstance(obj, pd.Series):
        # Convert Series to list
        return obj.tolist()
    
    elif isinstance(obj, dict):
        # Recursively serialize dictionary values
        return {key: serialize_pandas_object(value) for key, value in obj.items()}
    
    elif isinstance(obj, (list, tuple)):
        # Recursively serialize list/tuple elements
        return [serialize_pandas_object(item) for item in obj]
    
    elif isinstance(obj, (pd.Timestamp, pd.Timedelta)):
        # Convert pandas timestamps to ISO format
        return obj.isoformat()
    
    elif pd.isna(obj):
        # Convert pandas NA to None
        return None
    
    else:
        # Return as-is for primitive types
        return obj


def deserialize_to_dataframe(data: List[Dict[str, Any]], index_col: str = None) -> pd.DataFrame:
    """
    Convert list of dicts back to DataFrame
    
    Args:
        data: List of dictionaries (records format)
        index_col: Optional column to use as index
        
    Returns:
        pandas DataFrame
    """
    if not data:
        return pd.DataFrame()
    
    df = pd.DataFrame(data)
    
    if index_col and index_col in df.columns:
        df.set_index(index_col, inplace=True)
    
    return df


def validate_serialization(obj: Any) -> bool:
    """
    Check if an object contains any pandas objects that need serialization
    
    Args:
        obj: Object to check
        
    Returns:
        True if pandas objects found, False otherwise
    """
    if isinstance(obj, (pd.DataFrame, pd.Series, pd.Timestamp, pd.Timedelta)):
        return True
    
    elif isinstance(obj, dict):
        return any(validate_serialization(value) for value in obj.values())
    
    elif isinstance(obj, (list, tuple)):
        return any(validate_serialization(item) for item in obj)
    
    return False


def serialize_analysis_result(analysis: Dict[str, Any]) -> Dict[str, Any]:
    """
    Serialize analysis results from Analysis Agent
    
    Specifically handles common analysis result structures:
    - DataFrames in 'indicators', 'patterns', 'structure' keys
    - Series in various metric keys
    - Nested dictionaries with pandas objects
    
    Args:
        analysis: Analysis result dictionary
        
    Returns:
        Serialized analysis dictionary safe for JSON transmission
    """
    if not analysis:
        return analysis
    
    # Check if serialization is needed
    if not validate_serialization(analysis):
        logger.debug("No pandas objects found in analysis result, skipping serialization")
        return analysis
    
    logger.debug("Serializing analysis result with pandas objects")
    serialized = serialize_pandas_object(analysis)
    
    logger.debug(f"Serialization complete - result type: {type(serialized)}")
    return serialized
