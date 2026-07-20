<div align="center">

# CryptAI — Autonomous Multi-Agent Crypto Trading System

**A team of specialized AI agents that analyze markets, build trade setups, validate risk, and execute crypto-futures trades in real time — with a live dashboard for portfolio and agent activity.**

[![Live App](https://img.shields.io/badge/Live-cryptai--app.vercel.app-7FE0C2?style=flat-square)](https://cryptai-app.vercel.app)
[![Python](https://img.shields.io/badge/Python-3.11+-3776AB?style=flat-square&logo=python&logoColor=white)](https://www.python.org/)
[![LangGraph](https://img.shields.io/badge/LangGraph-multi--agent-1C3C3C?style=flat-square)](https://langchain-ai.github.io/langgraph/)
[![Next.js](https://img.shields.io/badge/Next.js-frontend-000000?style=flat-square&logo=next.js&logoColor=white)](https://nextjs.org/)
[![License: MIT](https://img.shields.io/badge/License-MIT-green?style=flat-square)](crypto-trading-agent/LICENSE)

</div>

---

## Overview

CryptAI is an autonomous crypto-futures trading system built on a **multi-agent architecture**. Instead of one monolithic bot, it splits the job across specialized agents — data, analysis, strategy, risk, execution, and memory — orchestrated with **LangGraph**. Each agent has a single responsibility and hands structured output to the next, so decisions are traceable and every trade passes through a deterministic risk gate before a single order is placed.

Market reasoning combines **computational analysis** (Smart Money Concepts, ICT, multi-timeframe confluence, classic indicators) with **LLM reasoning** (Claude + GPT), and every action is streamed to a real-time **Next.js dashboard**.

> ⚠️ **Research & educational project.** Trading crypto derivatives carries substantial risk. CryptAI defaults to **testnet / paper trading** with execution disabled — enable live trading at your own risk. Nothing here is financial advice.

**Live app:** https://cryptai-app.vercel.app

---

## How it works

Agents run as a pipeline; the risk gate is a hard stop between a proposed setup and execution.

```
┌────────────┐   ┌──────────────┐   ┌───────────────┐   ┌────────────┐   ┌───────────────┐
│ Data Agent │──▶│ Analysis     │──▶│ Strategy      │──▶│ Risk Agent │──▶│ Execution     │
│ live feeds │   │ SMC/ICT+LLM  │   │ trade setups  │   │ validate ✋ │   │ place & watch │
└────────────┘   └──────────────┘   └───────────────┘   └────────────┘   └───────────────┘
       │                                                        │                  │
       └───────────────────────  Memory Agent  ◀───────────────┴──────────────────┘
                          trade history · analytics · learning
```

| Agent | Responsibility |
|-------|----------------|
| **Data Agent** | Fetches and distributes live market data from Binance Futures (REST + WebSocket streams). |
| **Analysis Agent** | Orchestrates market analysis — SMC/ICT structure detection, multi-timeframe confluence, and LLM reasoning over the computed context. |
| **Strategy Agent** | Turns analysis into precise swing/scalp trade setups: entries, stops, targets, confluence score, and risk/reward. |
| **Risk Agent** | Validates every setup against a rules engine, circuit breaker, correlation and portfolio-heat checks, and drawdown limits — deterministic calc backed by an LLM risk advisor. |
| **Execution Agent** | Places and monitors orders via exchange APIs, with error handling, retries, and position reconciliation. |
| **Memory Agent** | Persists trade history and performance analytics, and surfaces learnings from past trades via a vector store. |

---

## Features

- **Six specialized agents** orchestrated with LangGraph — traceable, single-responsibility decisions.
- **Smart Money Concepts & ICT** structure detection plus multi-timeframe confluence scoring.
- **Hybrid reasoning** — deterministic quant signals combined with LLM judgment (Claude + GPT).
- **Deterministic risk gate** — position sizing, portfolio heat, correlation, drawdown protection, and a global circuit breaker before any order.
- **Real-time execution** on Binance/BingX with WebSocket order monitoring and position reconciliation.
- **Live dashboard** — portfolio, open positions, live candles, and per-agent activity in real time.
- **Paper-trading mode** — full simulation loop with no capital at risk (default).
- **Persistent memory & analytics** — trade journaling, performance metrics, and vector-backed retrieval.

---

## Tech stack

| Layer | Technologies |
|-------|--------------|
| **Agents / AI** | LangGraph · LangChain · Claude (Anthropic) · GPT-4o (OpenAI) |
| **Analysis** | pandas · NumPy · SciPy · TA-Lib · pandas-ta · custom SMC/ICT detectors |
| **Market data / exec** | ccxt · python-binance · WebSockets · BingX / CoinDCX |
| **Backend** | Python 3.11 · FastAPI · asyncio · Pydantic · Loguru · Prometheus |
| **Data stores** | PostgreSQL (SQLAlchemy + Alembic) · Redis (streams/state) · Pinecone / ChromaDB (memory) |
| **Frontend** | Next.js · React · TypeScript · Tailwind CSS · Radix UI · TanStack Query · Zustand · lightweight-charts · Supabase (auth) |
| **Infra** | Docker Compose · Vercel (frontend) · Render (backend) |

---

## Repository structure

```
CryptAI/
├── crypto-trading-agent/        # Python backend — the agent system
│   ├── src/
│   │   ├── agents/              # data · analysis · strategy · risk · memory
│   │   ├── analysis/            # SMC/ICT detectors, indicators, MTF analyzer
│   │   ├── strategy/            # setup builder, confluence, sizing, R:R
│   │   ├── risk/                # rules engine, circuit breaker, portfolio heat
│   │   ├── execution/           # order placement & monitoring
│   │   ├── memory/              # trade history & vector retrieval
│   │   ├── core/ · data/ · api/ · utils/
│   ├── alembic/                 # DB migrations
│   ├── docker-compose.yml       # Redis + PostgreSQL
│   └── requirements.txt
├── frontend/                    # Next.js dashboard
└── docs (SETUP.md, ARCHITECTURE_DEEP_DIVE.md, PAPER_TRADING_GUIDE.md, …)
```

---

## Getting started

### Prerequisites
- **Python 3.11+**, **Node.js 18+**, **Docker Desktop**
- API keys: Anthropic and OpenAI (required); Binance (market data); BingX (optional, live trading); Pinecone (optional, memory)

### 1. Backend

```bash
git clone https://github.com/sahit1011/CryptAI.git
cd CryptAI/crypto-trading-agent

python -m venv venv
source venv/bin/activate           # Windows: venv\Scripts\activate
pip install -r requirements.txt

cp .env.example .env               # then fill in your keys
docker-compose up -d               # starts Redis + PostgreSQL
python init_database.py            # run migrations / seed schema
```

Keep the defaults `USE_TESTNET=true` and `ENABLE_EXECUTION=false` for safe paper trading. See [`crypto-trading-agent/PAPER_TRADING_GUIDE.md`](crypto-trading-agent/PAPER_TRADING_GUIDE.md).

### 2. Frontend

```bash
cd frontend
npm install
# create .env.local with your Supabase keys + backend API URL, e.g.
#   NEXT_PUBLIC_SUPABASE_URL=...
#   NEXT_PUBLIC_SUPABASE_ANON_KEY=...
#   NEXT_PUBLIC_API_URL=http://localhost:8000
npm run dev                        # http://localhost:3000
```

### 3. Configuration

All backend settings live in `crypto-trading-agent/.env` (see `.env.example`):

| Key | Purpose |
|-----|---------|
| `ANTHROPIC_API_KEY` / `OPENAI_API_KEY` | LLM reasoning |
| `BINANCE_API_KEY` / `BINANCE_SECRET_KEY` | Market data |
| `BINGX_API_KEY` / `BINGX_SECRET_KEY` | Live execution (optional) |
| `REDIS_URL` / `POSTGRES_URL` | State & persistence |
| `USE_TESTNET` / `ENABLE_EXECUTION` | Safety switches (`true` / `false` by default) |

> 🔐 Never commit real keys. `.env` is gitignored — only `.env.example` (placeholders) belongs in git.

Detailed guides: [`SETUP.md`](SETUP.md) · [`crypto-trading-agent/ARCHITECTURE_DEEP_DIVE.md`](crypto-trading-agent/ARCHITECTURE_DEEP_DIVE.md) · [`BACKEND_STARTUP_GUIDE.md`](BACKEND_STARTUP_GUIDE.md)

---

## Disclaimer

CryptAI is provided for research and educational purposes. Automated trading of leveraged crypto derivatives can lead to significant financial loss. Use testnet/paper mode unless you fully understand the risks, and never trade capital you can't afford to lose. The author accepts no liability for financial losses. This is not financial advice.

## License

Released under the [MIT License](crypto-trading-agent/LICENSE).

---

<div align="center">
Built by <a href="https://anil-portfolio-chi.vercel.app">Anil Sahith</a> · <a href="https://cryptai-app.vercel.app">Live demo</a>
</div>
