# AI Trading Agent System - Development Plan & Task Manager

## Project Overview
**Goal:** Build an autonomous AI agent system for crypto futures trading using multi-agent architecture, LLM-powered analysis, and professional trading strategies (SMC/ICT).

**Timeline:** 16 weeks (4 months)  
**Budget:** $10,000 initial capital + ~$250/day LLM costs  
**Tech Stack:** Python 3.11+, LangGraph, Claude Sonnet 4.5, GPT-4o, Redis, PostgreSQL, Binance API, BingX API

---

## Development Phases

### Phase 1: Foundation & Infrastructure (Weeks 1-2)
### Phase 2: Data Collection Agent (Weeks 3-4)
### Phase 3: Market Analysis Agent (Weeks 5-6)
### Phase 4: Strategy Generation Agent (Weeks 7-8)
### Phase 5: Risk Management Agent (Weeks 9-10)
### Phase 6: Execution Agent (Weeks 11-12)
### Phase 7: Memory & Orchestration (Weeks 13-14)
### Phase 8: Testing & Optimization (Weeks 15-16)

---

# EPIC 1: Foundation & Infrastructure Setup
**Duration:** Weeks 1-2  
**Priority:** P0 (Critical)  
**Owner:** Backend Developer

## Sprint 1.1: Development Environment Setup

### Ticket #1.1.1: Project Structure & Repository Setup
**Story Points:** 2  
**Priority:** P0

**Description:**
Set up the foundational project structure with proper organization for a multi-agent system.

**Acceptance Criteria:**
- [ ] GitHub repository created with proper .gitignore
- [ ] Project follows standard Python package structure
- [ ] Virtual environment configured (Python 3.11+)
- [ ] README.md with setup instructions
- [ ] LICENSE file added (MIT recommended)
- [ ] .env.example file for environment variables

**Deliverables:**
```
📁 Project Structure:
crypto-trading-agent/
├── .github/
│   └── workflows/
│       └── ci.yml
├── src/
│   ├── agents/
│   │   ├── __init__.py
│   │   ├── base_agent.py
│   │   ├── data_agent.py
│   │   ├── analysis_agent.py
│   │   ├── strategy_agent.py
│   │   ├── risk_agent.py
│   │   ├── execution_agent.py
│   │   └── memory_agent.py
│   ├── core/
│   │   ├── __init__.py
│   │   ├── orchestrator.py
│   │   ├── message_bus.py
│   │   └── state_manager.py
│   ├── data/
│   │   ├── __init__.py
│   │   ├── binance_client.py
│   │   ├── exchange_client.py
│   │   └── data_models.py
│   ├── analysis/
│   │   ├── __init__.py
│   │   ├── indicators.py
│   │   ├── smc_detector.py
│   │   ├── ict_detector.py
│   │   └── pattern_recognition.py
│   ├── strategy/
│   │   ├── __init__.py
│   │   ├── trade_generator.py
│   │   └── confluence_validator.py
│   ├── risk/
│   │   ├── __init__.py
│   │   ├── position_sizer.py
│   │   └── portfolio_manager.py
│   ├── execution/
│   │   ├── __init__.py
│   │   ├── order_manager.py
│   │   └── exchange_adapter.py
│   ├── memory/
│   │   ├── __init__.py
│   │   ├── trade_logger.py
│   │   └── vector_store.py
│   └── utils/
│       ├── __init__.py
│       ├── logger.py
│       ├── config.py
│       └── helpers.py
├── tests/
│   ├── unit/
│   ├── integration/
│   └── conftest.py
├── scripts/
│   ├── setup_database.py
│   └── backtest_runner.py
├── config/
│   ├── dev.yaml
│   └── prod.yaml
├── requirements.txt
├── requirements-dev.txt
├── setup.py
├── .env.example
├── .gitignore
├── README.md
└── LICENSE
```

**Implementation Script:** `scripts/setup_project.sh`
```bash
#!/bin/bash

# Create project structure
mkdir -p crypto-trading-agent/{src/{agents,core,data,analysis,strategy,risk,execution,memory,utils},tests/{unit,integration},scripts,config}

# Create __init__.py files
find crypto-trading-agent/src -type d -exec touch {}/__init__.py \;

# Create .gitignore
cat > crypto-trading-agent/.gitignore << 'EOF'
# Python
__pycache__/
*.py[cod]
*$py.class
*.so
.Python
env/
venv/
ENV/

# IDEs
.vscode/
.idea/
*.swp

# Environment
.env
*.log

# Data
data/
*.db
*.sqlite

# Testing
.pytest_cache/
.coverage
htmlcov/
EOF

# Create .env.example
cat > crypto-trading-agent/.env.example << 'EOF'
# LLM API Keys
ANTHROPIC_API_KEY=your_anthropic_key_here
OPENAI_API_KEY=your_openai_key_here

# Exchange API Keys
BINANCE_API_KEY=your_binance_key_here
BINANCE_SECRET_KEY=your_binance_secret_here
BINGX_API_KEY=your_bingx_key_here
BINGX_SECRET_KEY=your_bingx_secret_here

# Database
REDIS_URL=redis://localhost:6379
POSTGRES_URL=postgresql://localhost:5432/trading_agent

# Vector Database
PINECONE_API_KEY=your_pinecone_key_here
PINECONE_ENV=your_environment

# Configuration
ENVIRONMENT=development
LOG_LEVEL=INFO
INITIAL_CAPITAL=10000
MAX_DAILY_LOSS=500
EOF

echo "✅ Project structure created successfully!"
```

---

### Ticket #1.1.2: Dependencies & Requirements Installation
**Story Points:** 3  
**Priority:** P0

**Description:**
Install and configure all required Python packages and external dependencies.

**Acceptance Criteria:**
- [ ] requirements.txt created with all dependencies
- [ ] requirements-dev.txt for development tools
- [ ] All packages install without errors
- [ ] Version constraints properly specified
- [ ] Docker configuration for services (Redis, PostgreSQL)

**Deliverables:**

**File:** `requirements.txt`
```txt
# Core Framework
langgraph==0.2.0
langchain==0.2.0
langchain-anthropic==0.1.15
langchain-openai==0.1.8

# LLM Clients
anthropic==0.28.0
openai==1.35.0

# Exchange & Market Data
ccxt==4.3.50
python-binance==1.0.19
websocket-client==1.8.0
requests==2.31.0

# Data Processing
pandas==2.2.2
numpy==1.26.4
ta-lib==0.4.28
pandas-ta==0.3.14b0

# Database
redis==5.0.5
psycopg2-binary==2.9.9
sqlalchemy==2.0.30
alembic==1.13.1

# Vector Database
pinecone-client==3.2.2
chromadb==0.5.0

# Async & Concurrency
asyncio==3.4.3
aiohttp==3.9.5
asyncpg==0.29.0

# Utilities
python-dotenv==1.0.1
pydantic==2.7.3
pyyaml==6.0.1
loguru==0.7.2
tenacity==8.3.0

# Monitoring
prometheus-client==0.20.0
python-telegram-bot==21.3

# Testing (move to requirements-dev.txt)
pytest==8.2.2
pytest-asyncio==0.23.7
pytest-cov==5.0.0
pytest-mock==3.14.0
```

**File:** `requirements-dev.txt`
```txt
-r requirements.txt

# Development Tools
black==24.4.2
flake8==7.0.0
mypy==1.10.0
isort==5.13.2
pre-commit==3.7.1

# Testing
pytest==8.2.2
pytest-asyncio==0.23.7
pytest-cov==5.0.0
pytest-mock==3.14.0
faker==25.3.0

# Documentation
mkdocs==1.6.0
mkdocs-material==9.5.25

# Debugging
ipython==8.24.0
ipdb==0.13.13
```

**File:** `docker-compose.yml`
```yaml
version: '3.8'

services:
  redis:
    image: redis:7-alpine
    ports:
      - "6379:6379"
    volumes:
      - redis_data:/data
    command: redis-server --appendonly yes

  postgres:
    image: postgres:16-alpine
    environment:
      POSTGRES_DB: trading_agent
      POSTGRES_USER: trader
      POSTGRES_PASSWORD: secure_password_here
    ports:
      - "5432:5432"
    volumes:
      - postgres_data:/var/lib/postgresql/data

  pgadmin:
    image: dpage/pgadmin4:latest
    environment:
      PGADMIN_DEFAULT_EMAIL: admin@trading.local
      PGADMIN_DEFAULT_PASSWORD: admin
    ports:
      - "5050:80"
    depends_on:
      - postgres

volumes:
  redis_data:
  postgres_data:
```

**Implementation Script:** `scripts/install_dependencies.sh`
```bash
#!/bin/bash

echo "🚀 Installing dependencies..."

# Create virtual environment
python3.11 -m venv venv
source venv/bin/activate

# Upgrade pip
pip install --upgrade pip setuptools wheel

# Install TA-Lib (requires system dependencies)
if [[ "$OSTYPE" == "darwin"* ]]; then
    # macOS
    brew install ta-lib
elif [[ "$OSTYPE" == "linux-gnu"* ]]; then
    # Linux
    wget http://prdownloads.sourceforge.net/ta-lib/ta-lib-0.4.0-src.tar.gz
    tar -xzf ta-lib-0.4.0-src.tar.gz
    cd ta-lib/
    ./configure --prefix=/usr
    make
    sudo make install
    cd ..
    rm -rf ta-lib ta-lib-0.4.0-src.tar.gz
fi

# Install Python dependencies
pip install -r requirements.txt
pip install -r requirements-dev.txt

# Start Docker services
docker-compose up -d

echo "✅ Dependencies installed successfully!"
echo "✅ Redis running on localhost:6379"
echo "✅ PostgreSQL running on localhost:5432"
echo "✅ PgAdmin available at http://localhost:5050"
```

---

### Ticket #1.1.3: Database Schema Design & Setup
**Story Points:** 5  
**Priority:** P0

**Description:**
Design and implement database schemas for trades, market data, and agent state.

**Acceptance Criteria:**
- [ ] PostgreSQL schema created with all tables
- [ ] Redis key structure documented
- [ ] Alembic migrations configured
- [ ] Database initialization script working
- [ ] Indexes created for query optimization

**Deliverables:**

**File:** `src/data/data_models.py`
```python
"""
Database models for trading system
"""
from datetime import datetime
from typing import Optional, List
from sqlalchemy import Column, Integer, String, Float, DateTime, Boolean, JSON, ForeignKey, Index
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship
from pydantic import BaseModel, Field

Base = declarative_base()

class Trade(Base):
    """Trade records table"""
    __tablename__ = 'trades'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    trade_id = Column(String(50), unique=True, nullable=False, index=True)
    
    # Trade details
    symbol = Column(String(20), nullable=False, index=True)
    direction = Column(String(10), nullable=False)  # LONG/SHORT
    strategy_type = Column(String(20))  # SCALP/DAY_TRADE/SWING
    
    # Entry
    entry_price = Column(Float, nullable=False)
    entry_time = Column(DateTime, nullable=False, index=True)
    position_size = Column(Float, nullable=False)
    
    # Exit
    exit_price = Column(Float)
    exit_time = Column(DateTime)
    stop_loss = Column(Float, nullable=False)
    take_profit = Column(JSON)  # List of TP levels
    
    # Performance
    pnl = Column(Float)
    pnl_percentage = Column(Float)
    r_multiple = Column(Float)  # Risk-reward multiple achieved
    duration_minutes = Column(Integer)
    
    # Status
    status = Column(String(20), default='OPEN')  # OPEN/CLOSED/CANCELLED
    exit_reason = Column(String(50))  # TP_HIT/SL_HIT/MANUAL/INVALIDATED
    
    # Analysis context
    analysis_snapshot = Column(JSON)  # Full analysis at trade time
    confluences = Column(JSON)  # List of confluences
    confidence_score = Column(Float)
    
    # Orders
    entry_order_id = Column(String(50))
    sl_order_id = Column(String(50))
    tp_order_ids = Column(JSON)
    
    # Metadata
    created_at = Column(DateTime, default=datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=datetime.now(timezone.utc), onupdate=datetime.now(timezone.utc))
    
    # Relationships
    executions = relationship("TradeExecution", back_populates="trade")
    
    __table_args__ = (
        Index('idx_symbol_entry_time', 'symbol', 'entry_time'),
        Index('idx_status_strategy', 'status', 'strategy_type'),
    )

class TradeExecution(Base):
    """Order execution records"""
    __tablename__ = 'trade_executions'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    trade_id = Column(String(50), ForeignKey('trades.trade_id'), nullable=False)
    
    order_id = Column(String(50), unique=True, nullable=False)
    order_type = Column(String(20))  # ENTRY/SL/TP1/TP2/TP3
    side = Column(String(10))  # BUY/SELL
    quantity = Column(Float, nullable=False)
    price = Column(Float, nullable=False)
    
    status = Column(String(20))  # PENDING/FILLED/CANCELLED
    filled_quantity = Column(Float, default=0)
    average_price = Column(Float)
    
    execution_time = Column(DateTime)
    created_at = Column(DateTime, default=datetime.now(timezone.utc))
    
    trade = relationship("Trade", back_populates="executions")

class MarketData(Base):
    """Historical market data cache"""
    __tablename__ = 'market_data'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    symbol = Column(String(20), nullable=False, index=True)
    timeframe = Column(String(10), nullable=False)  # 5m/15m/1h/4h/1d
    
    timestamp = Column(DateTime, nullable=False, index=True)
    open = Column(Float, nullable=False)
    high = Column(Float, nullable=False)
    low = Column(Float, nullable=False)
    close = Column(Float, nullable=False)
    volume = Column(Float, nullable=False)
    
    # Technical indicators (cached)
    rsi = Column(Float)
    macd = Column(Float)
    macd_signal = Column(Float)
    bb_upper = Column(Float)
    bb_lower = Column(Float)
    
    created_at = Column(DateTime, default=datetime.now(timezone.utc))
    
    __table_args__ = (
        Index('idx_symbol_timeframe_timestamp', 'symbol', 'timeframe', 'timestamp', unique=True),
    )

class PerformanceMetrics(Base):
    """Aggregated performance metrics"""
    __tablename__ = 'performance_metrics'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    date = Column(DateTime, nullable=False, unique=True, index=True)
    
    # Daily metrics
    total_trades = Column(Integer, default=0)
    winning_trades = Column(Integer, default=0)
    losing_trades = Column(Integer, default=0)
    win_rate = Column(Float, default=0)
    
    # P&L
    daily_pnl = Column(Float, default=0)
    cumulative_pnl = Column(Float, default=0)
    
    # Risk metrics
    max_drawdown = Column(Float, default=0)
    sharpe_ratio = Column(Float)
    profit_factor = Column(Float)
    
    # Strategy breakdown
    scalp_trades = Column(Integer, default=0)
    day_trades = Column(Integer, default=0)
    swing_trades = Column(Integer, default=0)
    
    created_at = Column(DateTime, default=datetime.now(timezone.utc))

class AgentState(Base):
    """Agent state persistence"""
    __tablename__ = 'agent_states'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    agent_name = Column(String(50), unique=True, nullable=False)
    
    state = Column(String(20))  # IDLE/PROCESSING/ERROR
    last_heartbeat = Column(DateTime)
    
    # State data
    state_data = Column(JSON)  # Agent-specific state
    
    # Error tracking
    error_count = Column(Integer, default=0)
    last_error = Column(String(500))
    last_error_time = Column(DateTime)
    
    updated_at = Column(DateTime, default=datetime.now(timezone.utc), onupdate=datetime.now(timezone.utc))

class SystemLog(Base):
    """System-wide logging"""
    __tablename__ = 'system_logs'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    timestamp = Column(DateTime, nullable=False, default=datetime.now(timezone.utc), index=True)
    
    level = Column(String(10), nullable=False)  # INFO/WARNING/ERROR/CRITICAL
    agent = Column(String(50))
    message = Column(String(1000))
    context = Column(JSON)
    
    __table_args__ = (
        Index('idx_timestamp_level', 'timestamp', 'level'),
    )

# Pydantic models for API/validation
class TradeSetup(BaseModel):
    """Trade setup schema"""
    symbol: str
    direction: str  # LONG/SHORT
    strategy_type: str
    entry_price: float
    stop_loss: float
    take_profit: List[float]
    position_size: Optional[float] = None
    confidence: float
    risk_reward: float
    reasoning: dict

class MarketAnalysis(BaseModel):
    """Market analysis result schema"""
    timestamp: datetime
    symbol: str
    market_structure: dict
    key_levels: dict
    smc_confluences: List[dict]
    ict_setup: dict
    trade_opportunities: List[dict]
    reasoning: str

class RiskParameters(BaseModel):
    """Risk management parameters"""
    account_balance: float
    max_risk_per_trade: float = 0.02
    max_portfolio_heat: float = 0.06
    max_daily_loss: float = 0.05
    max_concurrent_positions: int = 3
    min_risk_reward: float = 2.0
```

**File:** `scripts/setup_database.py`
```python
"""
Database initialization script
"""
import asyncio
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from src.data.data_models import Base
from src.utils.config import get_config
import redis

async def setup_postgresql():
    """Initialize PostgreSQL database"""
    config = get_config()
    
    # Create engine
    engine = create_engine(config.postgres_url)
    
    # Create all tables
    Base.metadata.create_all(engine)
    
    print("✅ PostgreSQL tables created successfully!")
    
    # Create session
    Session = sessionmaker(bind=engine)
    session = Session()
    
    return session

async def setup_redis():
    """Initialize Redis structure"""
    config = get_config()
    
    r = redis.from_url(config.redis_url)
    
    # Define Redis key structure
    redis_structure = {
        # Market data cache (TTL: 5 minutes)
        "market_data:{symbol}:{timeframe}": "hash",
        
        # Current state
        "state:current_prices": "hash",
        "state:positions": "list",
        "state:portfolio": "hash",
        
        # Agent states
        "agent:{agent_name}:state": "string",
        "agent:{agent_name}:last_update": "string",
        
        # Message queues
        "queue:{agent_name}_inbox": "list",
        
        # Pub/Sub channels
        "channel:market_data": "pubsub",
        "channel:trade_signals": "pubsub",
        "channel:alerts": "pubsub",
        
        # Cache
        "cache:analysis:{context_hash}": "string",  # TTL: 30 min
        
        # Rate limiting
        "ratelimit:llm_calls:{model}": "string",  # TTL: 1 hour
    }
    
    print("✅ Redis structure initialized!")
    print("\n📋 Redis Key Structure:")
    for key, type_ in redis_structure.items():
        print(f"  • {key} ({type_})")
    
    return r

async def main():
    print("🚀 Initializing databases...")
    
    # Setup PostgreSQL
    pg_session = await setup_postgresql()
    
    # Setup Redis
    redis_client = await setup_redis()
    
    print("\n✅ All databases initialized successfully!")
    print("\nYou can now:")
    print("  1. View PostgreSQL: http://localhost:5050")
    print("  2. Connect to Redis: redis-cli")

if __name__ == "__main__":
    asyncio.run(main())
```

**Implementation Command:**
```bash
python scripts/setup_database.py
```

---

### Ticket #1.1.4: Configuration & Logging System
**Story Points:** 3  
**Priority:** P0

**Description:**
Implement centralized configuration management and structured logging.

**Acceptance Criteria:**
- [ ] Config loaded from YAML and environment variables
- [ ] Different configs for dev/prod
- [ ] Structured logging with Loguru
- [ ] Log rotation configured
- [ ] Logging to file and console

**Deliverables:**

**File:** `src/utils/config.py`
```python
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

class LLMConfig(BaseModel):
    anthropic_api_key: str
    openai_api_key: str
    claude_model: str = "claude-sonnet-4-20250514"
    gpt_model: str = "gpt-4o"
    max_retries: int = 3
    timeout: int = 60

class ExchangeConfig(BaseModel):
    binance_api_key: str
    binance_secret: str
    bingx_api_key: str
    bingx_secret: str
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
    min_risk_reward: float = 2.0
    analysis_interval_seconds: int = 180  # 3 minutes
    symbols: list = ["BTCUSDT", "ETHUSDT"]
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
            "postgres_url": os.getenv("POSTGRES_URL", 
                                      "postgresql://trader:secure_password_here@localhost:5432/trading_agent"),
            "pinecone_api_key": os.getenv("PINECONE_API_KEY"),
            "pinecone_env": os.getenv("PINECONE_ENV"),
            **yaml_config.get("database", {})
        },
        "trading": yaml_config.get("trading", {})
    }
    
    return Config(**config_dict)

# Singleton instance
_config: Optional[Config] = None

def get_config() -> Config:
    """Get configuration singleton"""
    global _config
    if _config is None:
        _config = load_config()
    return _config
```

**File:** `config/dev.yaml`
```yaml
llm:
  claude_model: "claude-sonnet-4-20250514"
  gpt_model: "gpt-4o"
  max_retries: 3
  timeout: 60

exchange:
  testnet: true

trading:
  initial_capital: 10000
  max_risk_per_trade: 0.02
  max_portfolio_heat: 0.06
  max_daily_loss: 0.05
  max_concurrent_positions: 3
  min_risk_reward: 2.0
  analysis_interval_seconds: 180
  symbols:
    - BTCUSDT
    - ETHUSDT
  timeframes:
    - 5m
    - 15m
    - 1h
    - 4h
    - 1d
```

**File:** `src/utils/logger.py`
```python
"""
Centralized logging system using Loguru
"""
from loguru import logger
import sys
from pathlib import Path
from src.utils.config import get_config

def setup_logger():
    """Configure Loguru logger"""
    
    config = get_config()
    
    # Remove default handler
    logger.remove()
    
    # Console handler with colors
    logger.add(
        sys.stdout,
        colorize=True,
        format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan> | <level>{message}</level>",
        level=config.log_level
    )
    
    # File handler with rotation
    log_path = Path("logs")
    log_path.mkdir(exist_ok=True)
    
    logger.add(
        log_path / "trading_agent_{time:YYYY-MM-DD}.log",
        rotation="00:00",  # New file at midnight
        retention="30 days",
        compression="zip",
        format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {name}:{function}:{line} | {message}",
        level="DEBUG"
    )
    
    # Error file handler
    logger.add(
        log_path / "errors_{time:YYYY-MM-DD}.log",
        rotation="00:00",
        retention="90 days",
        compression="zip",
        format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {name}:{function}:{line} | {message}",
        level="ERROR"
    )
    
    return logger

# Initialize logger
log = setup_logger()
```

---

## Sprint 1.2: Core Framework Implementation

### Ticket #1.2.1: Base Agent Class Implementation
**Story Points:** 5  
**Priority:** P0

**Description:**
Implement the base agent class that all specialized agents will inherit from.

**Acceptance Criteria:**
- [ ] BaseAgent class with lifecycle management
- [ ] Message handling infrastructure
- [ ] State management methods
- [ ] Error handling and retries
- [ ] Heartbeat mechanism
- [ ] Unit tests with >80% coverage

**Deliverables:**

**File:** `src/agents/base_agent.py`
```python
"""
Base Agent class for all trading agents
"""
import asyncio
import uuid
from datetime import datetime
from typing import Dict, Any, Optional, Callable
from abc import ABC, abstractmethod
from loguru import logger
from tenacity import retry, stop_after_attempt, wait_exponential

from src.core.message_bus import MessageBus, AgentMessage
from src.core.state_manager import StateManager

class BaseAgent(ABC):
    """
    Base class for all agents in the system.
    Provides common functionality for message handling, state management, and lifecycle.
    """
    
    def __init__(
        self,
        name: str,
        message_bus: MessageBus,
        state_manager: StateManager
    ):
        self.name = name
        self.id = str(uuid.uuid4())
        self.message_bus = message_bus
        self.state_manager = state_manager
        
        self.state = "IDLE"
        self.running = False
        self.message_queue = asyncio.Queue()
        self.handlers: Dict[str, Callable] = {}
        
        self._setup_handlers()
        logger.info(f"[{self.name}] Agent initialized with ID: {self.id}")
    
    @abstractmethod
    def _setup_handlers(self):
        """Setup message handlers - must be implemented by subclass"""
        pass
    
    @abstractmethod
    async def process_message(self, message: AgentMessage) -> Optional[Dict[str, Any]]:
        """Process incoming message - must be implemented by subclass"""
        pass
    
    async def start(self):
        """Start the agent"""
        if self.running:
            logger.warning(f"[{self.name}] Agent already running")
            return
        
        self.running = True
        self.state = "ACTIVE"
        
        # Subscribe to message bus
        await self.message_bus.subscribe(f"{self.name}_inbox", self._on_message)
        
        # Start heartbeat
        asyncio.create_task(self._heartbeat_loop())
        
        # Start message processing loop
        asyncio.create_task(self._message_loop())
        
        logger.info(f"[{self.name}] Agent started")
    
    async def stop(self):
        """Stop the agent"""
        self.running = False
        self.state = "STOPPED"
        logger.info(f"[{self.name}] Agent stopped")
    
    async def _message_loop(self):
        """Main message processing loop"""
        while self.running:
            try:
                # Wait for message with timeout
                message = await asyncio.wait_for(
                    self.message_queue.get(),
                    timeout=1.0
                )
                
                # Process message
                await self._handle_message(message)
                
            except asyncio.TimeoutError:
                continue
            except Exception as e:
                logger.error(f"[{self.name}] Error in message loop: {e}")
                await self._handle_error(e)
    
    async def _handle_message(self, message: AgentMessage):
        """Handle incoming message with retry logic"""
        try:
            self.state = "PROCESSING"
            logger.debug(f"[{self.name}] Processing message: {message.type}")
            
            # Call message processor
            result = await self.process_message(message)
            
            # Send acknowledgment if required
            if message.requires_ack:
                await self.send_ack(message.id, result)
            
            self.state = "ACTIVE"
            
        except Exception as e:
            logger.error(f"[{self.name}] Error processing message: {e}")
            self.state = "ERROR"
            await self._handle_error(e)
    
    async def _on_message(self, message: Dict[str, Any]):
        """Callback for message bus"""
        agent_message = AgentMessage(**message)
        await self.message_queue.put(agent_message)
    
    async def send_message(
        self,
        receiver: str,
        message_type: str,
        payload: Dict[str, Any],
        priority: int = 5,
        requires_ack: bool = False
    ) -> str:
        """Send message to another agent"""
        
        message = AgentMessage(
            id=str(uuid.uuid4()),
            sender=self.name,
            receiver=receiver,
            type=message_type,
            payload=payload,
            priority=priority,
            requires_ack=requires_ack,
            timestamp=datetime.now(timezone.utc)
        )
        
        await self.message_bus.publish(f"{receiver}_inbox", message.dict())
        logger.debug(f"[{self.name}] Sent message to {receiver}: {message_type}")
        
        return message.id
    
    async def send_ack(self, message_id: str, result: Optional[Dict[str, Any]] = None):
        """Send acknowledgment"""
        await self.message_bus.publish(
            "acks",
            {
                "message_id": message_id,
                "agent": self.name,
                "result": result,
                "timestamp": datetime.now(timezone.utc).isoformat()
            }
        )
    
    async def _heartbeat_loop(self):
        """Send periodic heartbeat"""
        while self.running:
            try:
                await self.state_manager.update_agent_state(
                    agent_name=self.name,
                    state=self.state,
                    last_heartbeat=datetime.now(timezone.utc)
                )
                await asyncio.sleep(30)  # Heartbeat every 30 seconds
            except Exception as e:
                logger.error(f"[{self.name}] Heartbeat error: {e}")
    
    async def _handle_error(self, error: Exception):
        """Handle errors"""
        await self.state_manager.log_error(
            agent_name=self.name,
            error=str(error)
        )
        
        # Alert orchestrator
        await self.send_message(
            receiver="orchestrator",
            message_type="agent_error",
            payload={
                "error": str(error),
                "agent": self.name,
                "state": self.state
            },
            priority=10
        )
    
    def register_handler(self, message_type: str, handler: Callable):
        """Register handler for specific message type"""
        self.handlers[message_type] = handler
        logger.debug(f"[{self.name}] Registered handler for: {message_type}")
    
    async def get_state(self, key: str) -> Any:
        """Get value from state manager"""
        return await self.state_manager.get(key)
    
    async def set_state(self, key: str, value: Any):
        """Set value in state manager"""
        await self.state_manager.set(key, value)
```

---

### Ticket #1.2.2: Message Bus Implementation
**Story Points:** 5  
**Priority:** P0

**Description:**
Implement Redis-based message bus for inter-agent communication.

**Acceptance Criteria:**
- [ ] Pub/Sub implementation with Redis
- [ ] Message routing and priority queues
- [ ] Message persistence option
- [ ] Dead letter queue for failed messages
- [ ] Unit tests with mocked Redis

**Deliverables:**

**File:** `src/core/message_bus.py`
```python
"""
Message Bus for inter-agent communication using Redis Pub/Sub
"""
import asyncio
import json
from datetime import datetime
from typing import Dict, Any, Callable, Optional
from dataclasses import dataclass, asdict
import redis.asyncio as redis
from loguru import logger

@dataclass
class AgentMessage:
    """Standard message format"""
    id: str
    sender: str
    receiver: str
    type: str
    payload: Dict[str, Any]
    priority: int = 5
    requires_ack: bool = False
    timestamp: datetime = None
    parent_id: Optional[str] = None
    
    def __post_init__(self):
        if self.timestamp is None:
            self.timestamp = datetime.now(timezone.utc)
    
    def dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d['timestamp'] = self.timestamp.isoformat()
        return d

class MessageBus:
    """
    Redis-based message bus for agent communication
    """
    
    def __init__(self, redis_url: str):
        self.redis_url = redis_url
        self.redis_client: Optional[redis.Redis] = None
        self.pubsub: Optional[redis.client.PubSub] = None
        self.subscribers: Dict[str, Callable] = {}
        self.running = False
        
    async def connect(self):
        """Connect to Redis"""
        self.redis_client = await redis.from_url(self.redis_url)
        self.pubsub = self.redis_client.pubsub()
        logger.info("Message bus connected to Redis")
    
    async def disconnect(self):
        """Disconnect from Redis"""
        if self.pubsub:
            await self.pubsub.close()
        if self.redis_client:
            await self.redis_client.close()
        logger.info("Message bus disconnected")
    
    async def publish(self, channel: str, message: Dict[str, Any]):
        """Publish message to channel"""
        try:
            message_json = json.dumps(message, default=str)
            await self.redis_client.publish(channel, message_json)
            
            # Also store in queue for persistence
            await self.redis_client.lpush(f"queue:{channel}", message_json)
            await self.redis_client.expire(f"queue:{channel}", 3600)  # 1 hour TTL
            
            logger.debug(f"Published to {channel}: {message.get('type', 'unknown')}")
        except Exception as e:
            logger.error(f"Error publishing message: {e}")
            raise
    
    async def subscribe(self, channel: str, callback: Callable):
        """Subscribe to channel"""
        self.subscribers[channel] = callback
        await self.pubsub.subscribe(channel)
        logger.info(f"Subscribed to channel: {channel}")
        
        # Start listener if not running
        if not self.running:
            self.running = True
            asyncio.create_task(self._listen_loop())
    
    async def unsubscribe(self, channel: str):
        """Unsubscribe from channel"""
        await self.pubsub.unsubscribe(channel)
        if channel in self.subscribers:
            del self.subscribers[channel]
        logger.info(f"Unsubscribed from channel: {channel}")
    
    async def _listen_loop(self):
        """Listen for messages on subscribed channels"""
        async for message in self.pubsub.listen():
            try:
                if message['type'] == 'message':
                    channel = message['channel'].decode()
                    data = json.loads(message['data'].decode())
                    
                    # Call registered callback
                    if channel in self.subscribers:
                        await self.subscribers[channel](data)
                    
            except Exception as e:
                logger.error(f"Error in listen loop: {e}")
    
    async def get_queue_length(self, channel: str) -> int:
        """Get number of messages in queue"""
        return await self.redis_client.llen(f"queue:{channel}")
    
    async def get_from_queue(self, channel: str, timeout: int = 0) -> Optional[Dict[str, Any]]:
        """Pop message from queue"""
        result = await self.redis_client.brpop(f"queue:{channel}", timeout=timeout)
        if result:
            _, message_json = result
            return json.loads(message_json)
        return None
    
    async def send_to_dlq(self, message: Dict[str, Any], reason: str):
        """Send failed message to Dead Letter Queue"""
        dlq_message = {
            **message,
            "dlq_reason": reason,
            "dlq_timestamp": datetime.now(timezone.utc).isoformat()
        }
        await self.redis_client.lpush("dlq", json.dumps(dlq_message, default=str))
        logger.warning(f"Message sent to DLQ: {reason}")
```

**File:** `tests/unit/test_message_bus.py`
```python
"""
Unit tests for Message Bus
"""
import pytest
import asyncio
from src.core.message_bus import MessageBus, AgentMessage
from unittest.mock import AsyncMock, MagicMock

@pytest.fixture
async def message_bus():
    """Message bus fixture with mocked Redis"""
    bus = MessageBus("redis://localhost:6379")
    bus.redis_client = AsyncMock()
    bus.pubsub = AsyncMock()
    return bus

@pytest.mark.asyncio
async def test_publish_message(message_bus):
    """Test publishing message"""
    message = {
        "id": "123",
        "sender": "test_agent",
        "type": "test_message",
        "payload": {"data": "test"}
    }
    
    await message_bus.publish("test_channel", message)
    
    message_bus.redis_client.publish.assert_called_once()
    message_bus.redis_client.lpush.assert_called_once()

@pytest.mark.asyncio
async def test_subscribe_channel(message_bus):
    """Test subscribing to channel"""
    callback = AsyncMock()
    
    await message_bus.subscribe("test_channel", callback)
    
    assert "test_channel" in message_bus.subscribers
    message_bus.pubsub.subscribe.assert_called_once_with("test_channel")

@pytest.mark.asyncio
async def test_agent_message_creation():
    """Test AgentMessage creation"""
    msg = AgentMessage(
        id="123",
        sender="agent_a",
        receiver="agent_b",
        type="test",
        payload={"key": "value"}
    )
    
    assert msg.id == "123"
    assert msg.priority == 5  # Default
    assert msg.timestamp is not None
    
    msg_dict = msg.dict()
    assert isinstance(msg_dict['timestamp'], str)
```

---

### Ticket #1.2.3: State Manager Implementation
**Story Points:** 4  
**Priority:** P0

**Description:**
Implement state management system using Redis for real-time state and PostgreSQL for persistence.

**Acceptance Criteria:**
- [ ] Redis for hot state (positions, prices, agent states)
- [ ] PostgreSQL for persistent state
- [ ] Atomic operations for critical updates
- [ ] State recovery mechanism
- [ ] Unit tests

**Deliverables:**

**File:** `src/core/state_manager.py`
```python
"""
State Manager for managing system-wide state
"""
import json
from datetime import datetime
from typing import Any, Dict, Optional, List
import redis.asyncio as redis
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from loguru import logger

from src.data.data_models import AgentState, Trade
from src.utils.config import get_config

class StateManager:
    """
    Manages system state across Redis (hot) and PostgreSQL (persistent)
    """
    
    def __init__(self):
        config = get_config()
        
        # Redis for hot state
        self.redis_url = config.database.redis_url
        self.redis: Optional[redis.Redis] = None
        
        # PostgreSQL for persistent state
        self.postgres_url = config.database.postgres_url.replace('postgresql://', 'postgresql+asyncpg://')
        self.engine = create_async_engine(self.postgres_url)
        self.async_session = sessionmaker(
            self.engine, class_=AsyncSession, expire_on_commit=False
        )
        
    async def connect(self):
        """Initialize connections"""
        self.redis = await redis.from_url(self.redis_url)
        logger.info("State Manager connected")
    
    async def disconnect(self):
        """Close connections"""
        if self.redis:
            await self.redis.close()
        await self.engine.dispose()
        logger.info("State Manager disconnected")
    
    # === Hot State (Redis) ===
    
    async def get(self, key: str) -> Optional[Any]:
        """Get value from hot state"""
        value = await self.redis.get(f"state:{key}")
        if value:
            return json.loads(value)
        return None
    
    async def set(self, key: str, value: Any, ttl: Optional[int] = None):
        """Set value in hot state"""
        value_json = json.dumps(value, default=str)
        if ttl:
            await self.redis.setex(f"state:{key}", ttl, value_json)
        else:
            await self.redis.set(f"state:{key}", value_json)
    
    async def delete(self, key: str):
        """Delete key from hot state"""
        await self.redis.delete(f"state:{key}")
    
    async def get_hash(self, key: str, field: str) -> Optional[str]:
        """Get hash field"""
        return await self.redis.hget(f"state:{key}", field)
    
    async def set_hash(self, key: str, field: str, value: Any):
        """Set hash field"""
        await self.redis.hset(f"state:{key}", field, json.dumps(value, default=str))
    
    async def get_all_hash(self, key: str) -> Dict[str, Any]:
        """Get all hash fields"""
        data = await self.redis.hgetall(f"state:{key}")
        return {k.decode(): json.loads(v.decode()) for k, v in data.items()}
    
    # === Portfolio State ===
    
    async def get_portfolio_state(self) -> Dict[str, Any]:
        """Get current portfolio state"""
        return await self.get_all_hash("portfolio")
    
    async def update_portfolio(self, updates: Dict[str, Any]):
        """Update portfolio state"""
        for key, value in updates.items():
            await self.set_hash("portfolio", key, value)
    
    async def get_positions(self) -> List[Dict[str, Any]]:
        """Get open positions"""
        positions_json = await self.redis.lrange("state:positions", 0, -1)
        return [json.loads(p) for p in positions_json]
    
    async def add_position(self, position: Dict[str, Any]):
        """Add new position"""
        await self.redis.lpush("state:positions", json.dumps(position, default=str))
    
    async def remove_position(self, position_id: str):
        """Remove position"""
        positions = await self.get_positions()
        updated_positions = [p for p in positions if p.get('id') != position_id]
        
        # Clear and repopulate
        await self.redis.delete("state:positions")
        for pos in updated_positions:
            await self.redis.lpush("state:positions", json.dumps(pos, default=str))
    
    # === Agent State ===
    
    async def update_agent_state(
        self,
        agent_name: str,
        state: str,
        last_heartbeat: datetime,
        state_data: Optional[Dict[str, Any]] = None
    ):
        """Update agent state"""
        async with self.async_session() as session:
            # Check if agent exists
            result = await session.execute(
                f"SELECT * FROM agent_states WHERE agent_name = '{agent_name}'"
            )
            agent_state = result.first()
            
            if agent_state:
                # Update existing
                await session.execute(
                    f"""UPDATE agent_states 
                    SET state = '{state}', 
                        last_heartbeat = '{last_heartbeat}',
                        state_data = '{json.dumps(state_data or {})}',
                        updated_at = NOW()
                    WHERE agent_name = '{agent_name}'"""
                )
            else:
                # Create new
                new_state = AgentState(
                    agent_name=agent_name,
                    state=state,
                    last_heartbeat=last_heartbeat,
                    state_data=state_data or {}
                )
                session.add(new_state)
            
            await session.commit()
    
    async def get_agent_state(self, agent_name: str) -> Optional[Dict[str, Any]]:
        """Get agent state"""
        async with self.async_session() as session:
            result = await session.execute(
                f"SELECT * FROM agent_states WHERE agent_name = '{agent_name}'"
            )
            agent_state = result.first()
            if agent_state:
                return {
                    "agent_name": agent_state.agent_name,
                    "state": agent_state.state,
                    "last_heartbeat": agent_state.last_heartbeat,
                    "state_data": agent_state.state_data
                }
        return None
    
    async def log_error(self, agent_name: str, error: str):
        """Log agent error"""
        async with self.async_session() as session:
            await session.execute(
                f"""UPDATE agent_states 
                SET error_count = error_count + 1,
                    last_error = '{error}',
                    last_error_time = NOW()
                WHERE agent_name = '{agent_name}'"""
            )
            await session.commit()
    
    # === Market State ===
    
    async def update_price(self, symbol: str, price: float):
        """Update current price"""
        await self.set_hash("current_prices", symbol, price)
    
    async def get_price(self, symbol: str) -> Optional[float]:
        """Get current price"""
        price_str = await self.get_hash("current_prices", symbol)
        return float(json.loads(price_str)) if price_str else None
    
    async def get_all_prices(self) -> Dict[str, float]:
        """Get all current prices"""
        return await self.get_all_hash("current_prices")
    
    # === Trade Persistence ===
    
    async def save_trade(self, trade_data: Dict[str, Any]) -> str:
        """Save trade to database"""
        async with self.async_session() as session:
            trade = Trade(**trade_data)
            session.add(trade)
            await session.commit()
            await session.refresh(trade)
            return trade.trade_id
    
    async def update_trade(self, trade_id: str, updates: Dict[str, Any]):
        """Update trade"""
        async with self.async_session() as session:
            await session.execute(
                f"""UPDATE trades 
                SET {', '.join(f"{k} = '{v}'" for k, v in updates.items())},
                    updated_at = NOW()
                WHERE trade_id = '{trade_id}'"""
            )
            await session.commit()
    
    async def get_trade(self, trade_id: str) -> Optional[Dict[str, Any]]:
        """Get trade by ID"""
        async with self.async_session() as session:
            result = await session.execute(
                f"SELECT * FROM trades WHERE trade_id = '{trade_id}'"
            )
            trade = result.first()
            if trade:
                return dict(trade._mapping)
        return None
```

---

## Summary of Epic 1 Deliverables

### Files Created:
1. ✅ Complete project structure (40+ directories/files)
2. ✅ `requirements.txt` with all dependencies
3. ✅ `docker-compose.yml` for Redis & PostgreSQL
4. ✅ Database models with SQLAlchemy (`data_models.py`)
5. ✅ Configuration system (`config.py` + YAML files)
6. ✅ Logging system with Loguru (`logger.py`)
7. ✅ Base Agent class (`base_agent.py`)
8. ✅ Message Bus with Redis Pub/Sub (`message_bus.py`)
9. ✅ State Manager (`state_manager.py`)
10. ✅ Setup scripts (database initialization, dependency installation)
11. ✅ Unit tests for core components

### Setup Commands:
```bash
# Clone and setup
git clone <your-repo>
cd crypto-trading-agent

# Run setup
chmod +x scripts/setup_project.sh scripts/install_dependencies.sh
./scripts/setup_project.sh
./scripts/install_dependencies.sh

# Initialize databases
python scripts/setup_database.py

# Run tests
pytest tests/ -v --cov=src
```

---

