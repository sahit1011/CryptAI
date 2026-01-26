# CryptAI - Complete Setup Guide

This guide will help you clone and run the entire CryptAI multi-agent crypto trading system on a new device.

---

## 📋 Prerequisites

Before you begin, ensure you have the following installed on your system:

### Required Software

1. **Git** (for cloning the repository)
   - Download: https://git-scm.com/downloads
   - Verify: `git --version`

2. **Python 3.11+** (backend)
   - Download: https://www.python.org/downloads/
   - Verify: `python --version` or `python3 --version`
   - **Important**: During installation, check "Add Python to PATH"

3. **Node.js 18+** (frontend)
   - Download: https://nodejs.org/ (LTS version recommended)
   - Verify: `node --version` and `npm --version`

4. **Docker Desktop** (for databases)
   - Download: https://www.docker.com/products/docker-desktop/
   - Verify: `docker --version` and `docker-compose --version`

### Required API Keys

You'll need API keys from the following services:

- **Anthropic** (for Claude Sonnet 4.5): https://console.anthropic.com/
- **OpenAI** (for GPT-4o): https://platform.openai.com/api-keys
- **Binance** (for market data): https://www.binance.com/en/my/settings/api-management
- **BingX** (optional, for trading): https://bingx.com/en-us/account/api/
- **Pinecone** (optional, for vector DB): https://www.pinecone.io/

---

## 🚀 Step-by-Step Setup

### Step 1: Clone the Repository

```bash
# Clone the repository
git clone https://github.com/sahit1011/CryptAI.git

# Navigate to the project directory
cd CryptAI
```

---

### Step 2: Backend Setup (Python)

#### 2.1 Navigate to Backend Directory
```bash
cd crypto-trading-agent
```

#### 2.2 Create Virtual Environment
```bash
# Create virtual environment
python -m venv venv

# Activate virtual environment
# On Windows:
venv\Scripts\activate

# On macOS/Linux:
source venv/bin/activate
```

#### 2.3 Install Python Dependencies
```bash
# Upgrade pip
pip install --upgrade pip

# Install production dependencies
pip install -r requirements.txt

# Install development dependencies (optional, for testing)
pip install -r requirements-dev.txt
```

#### 2.4 Install TA-Lib (Technical Analysis Library)

**Windows:**
```bash
# Download the wheel file for your Python version from:
# https://www.lfd.uci.edu/~gohlke/pythonlibs/#ta-lib
# Example: TA_Lib‑0.4.28‑cp311‑cp311‑win_amd64.whl

# Install the downloaded wheel
pip install TA_Lib‑0.4.28‑cp311‑cp311‑win_amd64.whl
```

**macOS:**
```bash
brew install ta-lib
pip install ta-lib
```

**Linux:**
```bash
sudo apt-get install ta-lib
pip install ta-lib
```

---

### Step 3: Database Setup (Docker)

#### 3.1 Start Docker Services
```bash
# Make sure Docker Desktop is running, then:
docker-compose up -d
```

This will start:
- **Redis** (port 6379) - Message bus and cache
- **PostgreSQL** (port 5432) - Trade history storage
- **pgAdmin** (port 5050) - Database management UI

#### 3.2 Verify Services are Running
```bash
docker ps
```

You should see 3 containers running: `redis`, `postgres`, and `pgadmin`.

#### 3.3 Initialize Database Schema
```bash
# Run database setup script
python scripts/setup_database.py
```

---

### Step 4: Environment Configuration

#### 4.1 Create Environment File
```bash
# In the crypto-trading-agent directory
cp .env.example .env
```

If `.env.example` doesn't exist, create `.env` manually:

```bash
# Create .env file
touch .env  # On Windows: type nul > .env
```

#### 4.2 Configure Environment Variables

Edit the `.env` file with your API keys and settings:

```env
# LLM API Keys
ANTHROPIC_API_KEY=your_anthropic_api_key_here
OPENAI_API_KEY=your_openai_api_key_here

# Exchange API Keys
BINANCE_API_KEY=your_binance_api_key_here
BINANCE_API_SECRET=your_binance_secret_here
BINGX_API_KEY=your_bingx_api_key_here
BINGX_API_SECRET=your_bingx_secret_here

# Database Configuration
REDIS_URL=redis://localhost:6379/0
POSTGRES_URL=postgresql://trader:secure_password_here@localhost:5432/trading_agent

# Vector Database (Optional)
PINECONE_API_KEY=your_pinecone_api_key_here
PINECONE_ENVIRONMENT=your_pinecone_environment

# Trading Configuration
INITIAL_CAPITAL=10000.0
MAX_RISK_PER_TRADE=0.02
MAX_PORTFOLIO_HEAT=0.06
TRADING_MODE=paper  # paper or live

# Logging
LOG_LEVEL=INFO
```

**Important Notes:**
- Replace all `your_*_here` placeholders with your actual API keys
- For **paper trading** (recommended for testing), set `TRADING_MODE=paper`
- The `POSTGRES_URL` password should match the one in `docker-compose.yml`

---

### Step 5: Frontend Setup (Next.js)

#### 5.1 Navigate to Frontend Directory
```bash
# From project root
cd ../frontend
```

#### 5.2 Install Node Dependencies
```bash
npm install
```

#### 5.3 Configure Frontend Environment (Optional)
```bash
# Create .env.local if you need custom API endpoints
touch .env.local  # On Windows: type nul > .env.local
```

Add to `.env.local` if needed:
```env
NEXT_PUBLIC_API_URL=http://localhost:8000
NEXT_PUBLIC_WS_URL=ws://localhost:8000/ws
```

---

## 🏃 Running the Application

### Option 1: Run All Services Separately (Recommended for Development)

#### Terminal 1: Start Backend API Server
```bash
# Navigate to backend directory
cd crypto-trading-agent

# Activate virtual environment
venv\Scripts\activate  # Windows
# source venv/bin/activate  # macOS/Linux

# Start FastAPI server
python -m src.api.server
```

The API will be available at: `http://localhost:8000`

#### Terminal 2: Start Trading System
```bash
# In a new terminal, navigate to backend directory
cd crypto-trading-agent

# Activate virtual environment
venv\Scripts\activate  # Windows

# Run the paper trading simulation
python run_paper_trading_simulation.py
```

#### Terminal 3: Start Frontend
```bash
# In a new terminal, navigate to frontend directory
cd frontend

# Start Next.js development server
npm run dev
```

The frontend will be available at: `http://localhost:3000`

---

### Option 2: Run with Process Manager (Production-like)

You can use a process manager like `pm2` or `supervisor` to run all services together.

---

## 🧪 Verify Installation

### 1. Check Backend Health
```bash
curl http://localhost:8000/health
```

Expected response:
```json
{
  "status": "online",
  "connections": 0,
  "message_bus": true
}
```

### 2. Check Database Connection
```bash
# Access pgAdmin at http://localhost:5050
# Login: admin@example.com / admin
# Connect to PostgreSQL server with credentials from docker-compose.yml
```

### 3. Check Frontend
Open your browser and navigate to `http://localhost:3000`

You should see the CryptAI dashboard with:
- Portfolio overview
- Live BTC price chart
- Agent activity feed
- Active trades section

---

## 📊 Running Tests

```bash
# Navigate to backend directory
cd crypto-trading-agent

# Activate virtual environment
venv\Scripts\activate

# Run all tests
pytest tests/ -v

# Run with coverage
pytest --cov=src --cov-report=html

# Run specific test file
pytest tests/unit/test_agent.py -v
```

---

## 🔧 Troubleshooting

### Issue: "ModuleNotFoundError: No module named 'src'"
**Solution:** Make sure you're in the `crypto-trading-agent` directory and virtual environment is activated.

### Issue: "Connection refused" for Redis/PostgreSQL
**Solution:** 
```bash
# Check if Docker containers are running
docker ps

# Restart containers if needed
docker-compose restart
```

### Issue: "TA-Lib installation failed"
**Solution:** Follow the TA-Lib installation guide for your OS (see Step 2.4)

### Issue: Frontend can't connect to backend
**Solution:** 
- Ensure backend API is running on port 8000
- Check CORS settings in `src/api/server.py`
- Verify WebSocket connection in browser console

### Issue: LLM API errors
**Solution:** 
- Verify API keys in `.env` file
- Check API key validity and credits
- Review rate limits for your API tier

---

## 📁 Project Structure

```
CryptAI/
├── crypto-trading-agent/          # Backend (Python)
│   ├── src/
│   │   ├── agents/                # Agent implementations
│   │   ├── api/                   # FastAPI server
│   │   ├── core/                  # Message bus, state manager
│   │   ├── data/                  # Database models & clients
│   │   ├── analysis/              # Technical analysis
│   │   ├── strategy/              # Trade generation
│   │   ├── risk/                  # Risk management
│   │   ├── execution/             # Order execution
│   │   ├── memory/                # Trade history & learning
│   │   └── utils/                 # Utilities & config
│   ├── tests/                     # Unit & integration tests
│   ├── scripts/                   # Setup & utility scripts
│   ├── config/                    # Configuration files
│   ├── requirements.txt           # Python dependencies
│   ├── docker-compose.yml         # Database services
│   └── .env                       # Environment variables
│
├── frontend/                      # Frontend (Next.js)
│   ├── app/                       # Next.js app directory
│   ├── components/                # React components
│   ├── lib/                       # Utilities & hooks
│   ├── public/                    # Static assets
│   └── package.json               # Node dependencies
│
├── docs/                          # Documentation
├── .gitignore                     # Git ignore rules
├── SETUP.md                       # This file
└── README.md                      # Project overview
```

---

## 🎯 Next Steps

1. **Review Documentation**: Check the `docs/` folder for detailed architecture guides
2. **Configure Trading Parameters**: Edit `config/dev.yaml` or `config/prod.yaml`
3. **Test Paper Trading**: Run the system in paper trading mode first
4. **Monitor Logs**: Check `logs/` directory for system activity
5. **Customize Strategies**: Modify agents in `src/agents/` to fit your trading style

---

## 🛡️ Security Best Practices

- **Never commit `.env` files** to Git (already in `.gitignore`)
- **Use environment variables** for all sensitive data
- **Rotate API keys** regularly
- **Start with paper trading** before going live
- **Set up proper monitoring** and alerts
- **Keep dependencies updated**: `pip list --outdated`

---

## 📞 Support

For issues or questions:
- Check the `docs/` folder for detailed guides
- Review `ISSUE_RESOLUTION_SUMMARY.md` for common problems
- Open an issue on GitHub: https://github.com/sahit1011/CryptAI/issues

---

## 📝 Quick Reference Commands

```bash
# Start databases
docker-compose up -d

# Activate Python environment
venv\Scripts\activate  # Windows
source venv/bin/activate  # macOS/Linux

# Run backend API
python -m src.api.server

# Run trading system
python run_paper_trading_simulation.py

# Run frontend
npm run dev

# Run tests
pytest tests/ -v

# Stop databases
docker-compose down

# View logs
docker-compose logs -f
```

---

**Happy Trading! 🚀📈**
