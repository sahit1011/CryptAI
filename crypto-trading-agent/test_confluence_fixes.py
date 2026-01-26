"""
Quick test script to verify ConfluenceScorer fixes
Tests type conversion and zone data extraction
"""
import pandas as pd
import sys
sys.path.insert(0, 'src')

from strategy.confluence_scorer import ConfluenceScorer

def test_type_conversion():
    """Test that pandas Series are properly converted to floats"""
    scorer = ConfluenceScorer()
    
    # Create test data with pandas Series (simulating real indicator data)
    test_indicators = {
        '1h': {
            'rsi_14': pd.Series([45.5, 50.2, 72.8]),  # Last value is 72.8 (overbought)
            'macd_histogram': pd.Series([0.5, -0.2, -1.5]),  # Last value is -1.5 (bearish)
            'volume': pd.Series([1000, 1200, 2500]),
            'volume_sma': pd.Series([1100, 1150, 1200])
        }
    }
    
    print("Testing indicator type conversion...")
    print(f"RSI type: {type(test_indicators['1h']['rsi_14'])}")
    print(f"RSI last value: {test_indicators['1h']['rsi_14'].iloc[-1]}")
    
    # This should NOT raise TypeError anymore
    try:
        confluences = scorer._score_indicators(test_indicators, 'SHORT')
        print(f"✅ SUCCESS: Found {len(confluences)} confluences for SHORT")
        for c in confluences:
            print(f"   - {c.factor}: {c.description}")
    except TypeError as e:
        print(f"❌ FAILED: {e}")
        return False
    
    return True

def test_zone_extraction():
    """Test that order block zones are properly extracted"""
    scorer = ConfluenceScorer()
    
    # Create test SMC data with zone as dict (real structure)
    test_smc = {
        'order_blocks': [
            {
                'type': 'bullish',
                'zone': {'high': 92000.0, 'low': 91500.0, 'open': 91800.0, 'close': 91600.0},
                'timeframe': '1h'
            }
        ],
        'fair_value_gaps': [
            {
                'type': 'bearish',
                'gap': {'high': 93000.0, 'low': 92500.0},
                'timeframe': '15m'
            }
        ]
    }
    
    print("\nTesting zone data extraction...")
    print(f"Order block zone type: {type(test_smc['order_blocks'][0]['zone'])}")
    
    # This should NOT raise KeyError anymore
    try:
        confluences = scorer._score_smc(test_smc, 'LONG')
        print(f"✅ SUCCESS: Found {len(confluences)} SMC confluences for LONG")
        for c in confluences:
            print(f"   - {c.factor}: {c.description}")
    except KeyError as e:
        print(f"❌ FAILED: KeyError {e}")
        return False
    
    return True

if __name__ == "__main__":
    print("="*60)
    print("ConfluenceScorer Fix Verification")
    print("="*60)
    
    test1 = test_type_conversion()
    test2 = test_zone_extraction()
    
    print("\n" + "="*60)
    if test1 and test2:
        print("✅ ALL TESTS PASSED")
    else:
        print("❌ SOME TESTS FAILED")
    print("="*60)
