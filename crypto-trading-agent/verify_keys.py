import os
import sys
from pathlib import Path

# Add src to path
sys.path.append(str(Path(__file__).parent))

from src.utils.config import load_config

def verify_keys():
    print("Verifying API Keys...")
    
    # Load config
    try:
        config = load_config()
        print(f"Environment: {config.environment}")
    except Exception as e:
        print(f"Error loading config: {e}")
        return

    # Check LLM keys
    print("\n--- LLM Keys ---")
    keys_to_check = [
        ("Anthropic", config.llm.anthropic_api_key),
        ("OpenAI", config.llm.openai_api_key),
        ("OpenRouter", config.llm.openrouter_api_key),
        ("Groq", config.llm.groq_api_key),
    ]

    for name, key in keys_to_check:
        if key:
            masked = f"{key[:8]}...{key[-4:]}" if len(key) > 12 else "***"
            print(f"✅ {name}: Present (Length: {len(key)}) - {masked}")
        else:
            print(f"❌ {name}: Missing")

    # Check Exchange Keys
    print("\n--- Exchange Keys ---")
    exchange_keys = [
        ("Binance Key", config.exchange.binance_api_key),
        ("Binance Secret", config.exchange.binance_secret),
        ("BingX Key", config.exchange.bingx_api_key),
        ("BingX Secret", config.exchange.bingx_secret),
    ]

    for name, key in exchange_keys:
        if key:
            print(f"✅ {name}: Present")
        else:
            print(f"❌ {name}: Missing")

if __name__ == "__main__":
    verify_keys()
