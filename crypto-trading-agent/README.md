# Crypto Trading Agent System

An autonomous AI-powered crypto futures trading system using multi-agent architecture and advanced technical analysis.

## Overview

This system implements a sophisticated trading bot that combines:
- Real-time market data collection from Binance Futures
- AI-powered market analysis using Claude Sonnet 4.5
- Smart Money Concepts (SMC) and Inner Circle Trader (ICT) methodologies
- Multi-agent orchestration with LangGraph
- Risk management and automated execution

## Features

- **Multi-Agent Architecture**: Specialized agents for data, analysis, strategy, risk, execution, and memory
- **Advanced Analysis**: SMC patterns, ICT setups, multi-timeframe confluence
- **AI Reasoning**: LLM-powered trade setup generation with confidence scoring
- **Risk Management**: Position sizing, portfolio heat monitoring, drawdown protection
- **Real-time Execution**: Automated order placement via BingX/CoinDCX APIs
- **Performance Tracking**: Comprehensive trade journaling and analytics

## Quick Start

### Prerequisites
- Python 3.11+
- Docker (for databases)
- API keys for Anthropic, OpenAI, Binance, BingX

### Installation

1. Clone the repository:
```bash
git clone <your-repo-url>
cd crypto-trading-agent
```

2. Set up environment:
```bash
# Create virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt
pip install -r requirements-dev.txt
```

3. Configure environment variables:
```bash
cp .env.example .env
# Edit .env with your API keys
```

4. Start databases:
```bash
docker-compose up -d
```

5. Initialize database:
```bash
python scripts/setup_database.py
```

### Running the System

```bash
# Run tests
pytest tests/ -v

# Start the trading system
python -m src.main
```

## Architecture

### Agents
- **Data Agent**: Real-time market data collection
- **Analysis Agent**: Technical analysis and pattern recognition
- **Strategy Agent**: Trade setup generation
- **Risk Agent**: Position sizing and risk validation
- **Execution Agent**: Order management and execution
- **Memory Agent**: Trade history and learning

### Tech Stack
- **Framework**: LangGraph for agent orchestration
- **LLMs**: Claude Sonnet 4.5 (analysis), GPT-4o (strategy)
- **Data**: Redis (hot cache), PostgreSQL (persistent)
- **APIs**: Binance WebSocket, BingX REST API
- **Analysis**: TA-Lib, Pandas-TA, custom SMC/ICT algorithms

## Development

### Project Structure
```
crypto-trading-agent/
├── src/
│   ├── agents/          # Agent implementations
│   ├── core/            # Orchestration & messaging
│   ├── data/            # Database models & clients
│   ├── analysis/        # Technical analysis
│   ├── strategy/        # Trade generation
│   ├── risk/            # Risk management
│   ├── execution/       # Order execution
│   ├── memory/          # Learning & memory
│   └── utils/           # Utilities & config
├── tests/               # Unit & integration tests
├── scripts/             # Setup & utility scripts
├── config/              # Configuration files
└── docs/                # Documentation
```

### Testing
```bash
# Run all tests
pytest

# Run with coverage
pytest --cov=src --cov-report=html

# Run specific test
pytest tests/unit/test_agent.py -v
```

## Configuration

Edit `config/dev.yaml` or `config/prod.yaml` for environment-specific settings.

Key parameters:
- `trading.initial_capital`: Starting account balance
- `trading.max_risk_per_trade`: Risk per trade (percentage)
- `trading.symbols`: Trading pairs to monitor
- `llm.max_retries`: LLM API retry attempts

## Risk Disclaimer

⚠️ **This software is for educational and research purposes only.**

- Past performance does not guarantee future results
- Cryptocurrency trading involves substantial risk of loss
- Always start with paper trading
- Never risk more than you can afford to lose
- Consult with financial advisors before live trading

## License

MIT License - see LICENSE file for details.

## Contributing

1. Fork the repository
2. Create a feature branch
3. Add tests for new functionality
4. Ensure all tests pass
5. Submit a pull request

## Support

For questions or issues:
- Create an issue on GitHub
- Check the documentation in `docs/`
- Review the PRD and architecture guides