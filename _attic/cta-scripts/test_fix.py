
import asyncio
import pandas as pd
import numpy as np
from src.agents.analysis_agent import MarketAnalysisAgent
from src.strategy.confluence_scorer import ConfluenceScorer
from src.core.message_bus import MessageBus
from src.core.state_manager import StateManager

async def test_fix():
    print("Testing AnalysisAgent serialization and ConfluenceScorer list handling...")
    
    # Mock dependencies
    message_bus = MessageBus("redis://localhost:6379")
    state_manager = StateManager()
    
    agent = MarketAnalysisAgent(message_bus, state_manager)
    scorer = ConfluenceScorer()
    
    # Create a pandas Series (simulating indicator data)
    s = pd.Series([10, 20, 30, 40, 50], name="rsi")
    
    # Test _make_serializable
    print("\n1. Testing _make_serializable with pandas Series...")
    serialized = agent._make_serializable(s)
    print(f"Serialized type: {type(serialized)}")
    print(f"Serialized value: {serialized}")
    
    if isinstance(serialized, list) and serialized == [10, 20, 30, 40, 50]:
        print("✅ _make_serializable working correctly for Series")
    else:
        print("❌ _make_serializable FAILED for Series")
        
    # Test ConfluenceScorer with list
    print("\n2. Testing ConfluenceScorer._get_last_value with list...")
    last_val = scorer._get_last_value(serialized)
    print(f"Last value: {last_val}")
    
    if last_val == 50:
        print("✅ ConfluenceScorer._get_last_value working correctly for list")
    else:
        print(f"❌ ConfluenceScorer._get_last_value FAILED for list (got {last_val})")

    # Test nested dict serialization (simulating computational results)
    print("\n3. Testing nested dict serialization...")
    computational = {
        "indicators": {
            "rsi": s,
            "macd": pd.Series([1, 2, 3])
        }
    }
    sanitized = agent._make_serializable(computational)
    print(f"Sanitized keys: {sanitized.keys()}")
    print(f"Sanitized indicators keys: {sanitized['indicators'].keys()}")
    print(f"Sanitized rsi type: {type(sanitized['indicators']['rsi'])}")
    
    if isinstance(sanitized['indicators']['rsi'], list):
        print("✅ Nested serialization working correctly")
    else:
        print("❌ Nested serialization FAILED")

if __name__ == "__main__":
    asyncio.run(test_fix())
