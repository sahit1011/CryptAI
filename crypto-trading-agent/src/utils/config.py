"""
Configuration management
"""
import os
import yaml
from pathlib import Path
from pydantic import BaseModel, Field
from typing import Optional
from dotenv import load_dotenv

load_dotenv()

# OpenRouter free-tier ROTATION list. OpenRouter's ':free' catalog rotates and
# rate-limits hard: any single free model can be pulled ("Provider returned
# error"), return 429, or hand back an empty/prose body at any moment. Pinning
# ONE free model makes that a single point of failure — so the fallback tries
# these in order and uses the first that returns a usable completion. Ordered by
# what actually serves reliably on the free tier today (verified 2026-07-18: the
# NVIDIA Nemotron family answers with clean JSON; the popular qwen/llama/gemma
# free slots are frequently hard-429'd but cost ~nothing to try, so they trail
# as opportunistic fallbacks). Override wholesale with OPENROUTER_FREE_MODELS
# (comma-separated) or promote a single model to the front with OPENROUTER_MODEL.
DEFAULT_OPENROUTER_FREE_MODELS = [
    "nvidia/nemotron-3-super-120b-a12b:free",   # fast (~3.4s) + 120B, best JSON adherence
    "nvidia/nemotron-3-nano-30b-a3b:free",      # smaller/faster to serve, reliable
    "nvidia/nemotron-3-ultra-550b-a55b:free",   # biggest brain, slower; strong tertiary
    "qwen/qwen3-next-80b-a3b-instruct:free",    # opportunistic (often 429 on free tier)
    "meta-llama/llama-3.3-70b-instruct:free",   # opportunistic
    "google/gemma-4-31b-it:free",               # opportunistic
]

class LLMConfig(BaseModel):
    anthropic_api_key: Optional[str] = None
    openai_api_key: Optional[str] = None
    openrouter_api_key: Optional[str] = None
    groq_api_key: Optional[str] = None
    google_api_key: Optional[str] = None
    # Best-in-class model per premium provider (used when that provider's key is set).
    claude_model: str = "claude-sonnet-4-20250514"
    gpt_model: str = "gpt-4o"
    gpt4o_model: str = "gpt-4o"
    gemini_model: str = "gemini-2.0-flash"
    groq_model: str = "llama-3.1-8b-instant"
    # OpenRouter is the universal fallback: a FREE open-source model used whenever no
    # premium key is set, so the whole system runs on an OpenRouter key alone (see
    # src/utils/llm_router.py). OpenRouter's free catalog ROTATES — override with the
    # OPENROUTER_MODEL env var when the default disappears (verified live 2026-07-16).
    deepseek_model: str = "nvidia/nemotron-3-super-120b-a12b:free"
    openrouter_fallback_model: str = "nvidia/nemotron-3-super-120b-a12b:free"
    # The ordered free-tier rotation the OpenRouter fallback tries in turn (see
    # DEFAULT_OPENROUTER_FREE_MODELS above). deepseek_model/openrouter_fallback_model
    # mirror the first entry for back-compat with existing logs and callers.
    openrouter_free_models: list = list(DEFAULT_OPENROUTER_FREE_MODELS)
    max_retries: int = 3
    timeout: int = 60

class ExchangeConfig(BaseModel):
    binance_api_key: Optional[str] = None
    binance_secret: Optional[str] = None
    bingx_api_key: Optional[str] = None
    bingx_secret: Optional[str] = None
    testnet: bool = True

class DatabaseConfig(BaseModel):
    redis_url: str
    postgres_url: str
    pinecone_api_key: Optional[str] = None
    pinecone_env: Optional[str] = None

class TradingConfig(BaseModel):
    initial_capital: float = 10000
    max_risk_per_trade: float = 0.02
    max_portfolio_heat: float = 0.06
    max_daily_loss: float = 0.05
    max_concurrent_positions: int = 3
    min_risk_reward: float = 1.0  # Changed from 2.0 to 1.0 for more trade opportunities
    analysis_interval_seconds: int = 180  # 3 minutes
    # Traded instruments: BTC, ETH, and GOLD. Gold = XAUTUSDT (Tether Gold, 1 XAUT ≈ 1
    # troy oz), the crypto gold instrument listed on Binance/Bybit/OKX — a literal
    # "XAUUSDT" pair isn't listed on crypto exchanges. Override via TRADING_SYMBOLS.
    symbols: list = ["BTCUSDT", "ETHUSDT", "XAUTUSDT"]
    timeframes: list = ["5m", "15m", "1h", "4h", "1d"]

class Config(BaseModel):
    environment: str = Field(default="development")
    log_level: str = Field(default="INFO")

    llm: LLMConfig
    exchange: ExchangeConfig
    database: DatabaseConfig
    trading: TradingConfig

def load_config(env: str = None) -> Config:
    """Load configuration from YAML and environment"""

    if env is None:
        env = os.getenv("ENVIRONMENT", "development")

    # Load YAML config
    config_path = Path(f"config/{env}.yaml")
    if config_path.exists():
        with open(config_path) as f:
            yaml_config = yaml.safe_load(f)
    else:
        yaml_config = {}

    # Override with environment variables
    config_dict = {
        "environment": env,
        "log_level": os.getenv("LOG_LEVEL", "INFO"),
        "llm": {
            "anthropic_api_key": os.getenv("ANTHROPIC_API_KEY"),
            "openai_api_key": os.getenv("OPENAI_API_KEY"),
            "openrouter_api_key": os.getenv("OPENROUTER_API_KEY"),
            "groq_api_key": os.getenv("GROQ_API_KEY"),
            "google_api_key": os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY"),
            **yaml_config.get("llm", {})
        },
        "exchange": {
            "binance_api_key": os.getenv("BINANCE_API_KEY"),
            "binance_secret": os.getenv("BINANCE_SECRET_KEY"),
            "bingx_api_key": os.getenv("BINGX_API_KEY"),
            "bingx_secret": os.getenv("BINGX_SECRET_KEY"),
            **yaml_config.get("exchange", {})
        },
        "database": {
            "redis_url": os.getenv("REDIS_URL", "redis://localhost:6379"),
            # No credentialed default: POSTGRES_URL must be set explicitly. A hardcoded
            # user:password fallback silently "worked" in dev and leaked into configs.
            "postgres_url": os.getenv("POSTGRES_URL", "postgresql://localhost:5432/trading_agent"),
            "pinecone_api_key": os.getenv("PINECONE_API_KEY"),
            "pinecone_env": os.getenv("PINECONE_ENV"),
            **yaml_config.get("database", {})
        },
        "trading": yaml_config.get("trading", {})
    }

    # TRADING_SYMBOLS env (comma-separated) overrides the traded instruments, e.g.
    # "BTCUSDT,ETHUSDT,PAXGUSDT". Drives both the data agent's subscriptions and the
    # daemon's per-symbol analysis loop.
    _symbols_env = os.getenv("TRADING_SYMBOLS", "").strip()
    if _symbols_env:
        config_dict["trading"] = {
            **config_dict["trading"],
            "symbols": [s.strip().upper() for s in _symbols_env.split(",") if s.strip()],
        }

    # OpenRouter free-tier rotation model list. The free catalog rotates, so the
    # models must be swappable without a code change:
    #   OPENROUTER_FREE_MODELS  (comma-separated) → replaces the whole list
    #   OPENROUTER_MODEL        (single)          → promoted to the front of the list
    # deepseek_model / openrouter_fallback_model track the first (primary) entry.
    _free_env = os.getenv("OPENROUTER_FREE_MODELS", "").strip()
    if _free_env:
        free_models = [m.strip() for m in _free_env.split(",") if m.strip()]
    else:
        free_models = list(
            config_dict["llm"].get("openrouter_free_models") or DEFAULT_OPENROUTER_FREE_MODELS
        )

    _or_model = os.getenv("OPENROUTER_MODEL", "").strip()
    if _or_model:
        # Promote to primary, keep the rest as fallbacks (dedup).
        free_models = [_or_model] + [m for m in free_models if m != _or_model]

    if free_models:
        config_dict["llm"]["openrouter_free_models"] = free_models
        config_dict["llm"]["deepseek_model"] = free_models[0]
        config_dict["llm"]["openrouter_fallback_model"] = free_models[0]

    return Config(**config_dict)

# Singleton instance
_config: Optional[Config] = None

def get_config() -> Config:
    """Get configuration singleton"""
    global _config
    if _config is None:
        _config = load_config()
    return _config