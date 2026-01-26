import asyncio
import os
import sys
from pathlib import Path

# Add src to path
sys.path.append(str(Path(__file__).parent))

from src.utils.config import get_config
from openai import OpenAI
from groq import Groq

async def test_llms():
    config = get_config()
    print(f"Testing LLM connections...")
    
    # Test OpenRouter
    print("\n--- Testing OpenRouter ---")
    if config.llm.openrouter_api_key:
        try:
            client = OpenAI(
                api_key=config.llm.openrouter_api_key,
                base_url="https://openrouter.ai/api/v1"
            )
            print(f"Model: {config.llm.deepseek_model}")
            response = client.chat.completions.create(
                model=config.llm.deepseek_model,
                messages=[{"role": "user", "content": "Say hello"}],
            )
            print(f"[SUCCESS] OpenRouter Success: {response.choices[0].message.content}")
        except Exception as e:
            print(f"[FAILED] OpenRouter Failed: {e}")
    else:
        print("Skipping OpenRouter (no key)")

    # Test Groq
    print("\n--- Testing Groq ---")
    if config.llm.groq_api_key:
        try:
            client = Groq(api_key=config.llm.groq_api_key)
            print(f"Model: {config.llm.groq_model}")
            response = client.chat.completions.create(
                model=config.llm.groq_model,
                messages=[{"role": "user", "content": "Say hello"}],
            )
            print(f"[SUCCESS] Groq Success: {response.choices[0].message.content}")
        except Exception as e:
            print(f"[FAILED] Groq Failed: {e}")
    else:
        print("Skipping Groq (no key)")

if __name__ == "__main__":
    asyncio.run(test_llms())
