# Agent Development Guide

## Commands
- **Run tests**: `pytest tests/ -v` (all tests) or `pytest tests/unit/test_agent.py -v` (single test)
- **Test with coverage**: `pytest --cov=src --cov-report=html`
- **Lint**: `flake8 src/` and `black src/`
- **Type check**: `mypy src/`
- **Format code**: `black src/ && isort src/`
- **Run system**: `python -m src.main`
- **Setup database**: `python scripts/setup_database.py`
- **Start services**: `docker-compose up -d`
- **Test single analysis snapshot**: `python test_deep_analysis_snapshot.py` (single 1H analysis)
- **Test dual-context analysis**: `python test_dual_context_analysis.py` (swing + scalping multi-TF)

## Architecture
Multi-agent crypto trading system built with LangGraph orchestration. Main subproject: `crypto-trading-agent/`

**Core components**: `src/agents/` (agent implementations), `src/core/` (message bus, state manager), `src/data/` (DB models), `src/analysis/` (technical analysis), `src/strategy/` (trade generation), `src/risk/` (risk management), `src/execution/` (order execution), `src/memory/` (learning)

**Database**: Redis (hot cache), PostgreSQL (persistent storage via SQLAlchemy), Alembic (migrations)

**LLM usage**: Claude Sonnet 4.5 (analysis agent), GPT-4o (strategy agent), GPT-4o-mini (risk agent selective use)

## Code Style
- **Imports**: Standard lib → third-party → local (`from src.module import Class`)
- **Formatting**: Black (line length 100), isort for import sorting
- **Types**: Use type hints everywhere (enforced by mypy). Use `dataclass` for data structures
- **Naming**: snake_case (functions/vars), PascalCase (classes), UPPER_CASE (constants)
- **Error handling**: Use `loguru` logger, `tenacity` for retries
- **Async**: All agent methods are `async`, use `asyncio.Queue` for messaging
- **Testing**: pytest with async support (`pytest-asyncio`), use `faker` for test data
