# Backend Startup Guide 🚀

## The Issue You Encountered

The **WebSocket error** in your frontend was caused by the backend API server not running. The frontend tries to connect to `ws://127.0.0.1:8000/ws`, but without the server running on port 8000, the connection fails immediately.

## System Architecture

Your multi-agent crypto trading system has **two main components**:

### 1. Backend (Python FastAPI)
- **Location**: `crypto-trading-agent/`
- **Main Server**: `src/api/server.py`
- **Port**: 8000
- **Responsibilities**:
  - WebSocket server for real-time data streaming
  - Binance market data integration
  - Agent communication via MessageBus
  - Trading system coordination

### 2. Frontend (Next.js)
- **Location**: `frontend/`
- **Port**: 3000 (default Next.js dev server)
- **Responsibilities**:
  - Dashboard UI
  - Real-time data visualization
  - WebSocket client connection to backend

## How to Start the System

### Option 1: Automated Startup (Recommended) ✅

Use the PowerShell script to start everything:

```powershell
cd crypto-trading-agent
.\start_system.ps1
```

This will:
1. Start the API server on port 8000 (in a new window)
2. Start the paper trading simulation (in a new window)
3. Both will run in separate PowerShell windows

### Option 2: Manual Startup

If you prefer to start components individually:

#### Step 1: Start the API Server
```powershell
cd crypto-trading-agent
python -m uvicorn src.api.server:app --host 0.0.0.0 --port 8000 --reload
```

#### Step 2: Start the Trading System (Optional)
```powershell
cd crypto-trading-agent
python run_paper_trading_simulation.py
```

#### Step 3: Start the Frontend
```powershell
cd frontend
npm run dev
```

## Verifying the Backend is Running

### Check Health Endpoint
```powershell
curl http://127.0.0.1:8000/health
```

Expected response:
```json
{
  "status": "online",
  "connections": 0,
  "message_bus": true
}
```

### Check WebSocket Connection
Once the frontend is running, open the browser console (F12) and you should see:
```
✅ Connected to backend WebSocket
```

## Common Issues & Solutions

### Issue 1: "WebSocket error: {}"
**Cause**: Backend server not running  
**Solution**: Start the backend using Option 1 or 2 above

### Issue 2: Port 8000 Already in Use
**Cause**: Another process is using port 8000  
**Solution**: 
```powershell
# Find the process using port 8000
netstat -ano | findstr :8000

# Kill the process (replace PID with actual process ID)
taskkill /PID <PID> /F
```

### Issue 3: Redis Connection Error
**Cause**: Redis not running  
**Solution**:
```powershell
# Start Redis (if installed)
redis-server

# Or use Docker
docker run -d -p 6379:6379 redis:latest
```

### Issue 4: Module Import Errors
**Cause**: Virtual environment not activated  
**Solution**:
```powershell
cd crypto-trading-agent
.\venv312\Scripts\Activate.ps1
```

## System Startup Checklist

Before running the frontend, ensure:

- [ ] Redis is running (check with `redis-cli ping`)
- [ ] Backend API server is running on port 8000
- [ ] Environment variables are set (`.env` file in `crypto-trading-agent/`)
- [ ] Virtual environment is activated (if running manually)

## Development Workflow

### Typical Development Session

1. **Start Backend**:
   ```powershell
   cd crypto-trading-agent
   .\start_system.ps1
   ```

2. **Start Frontend** (in a separate terminal):
   ```powershell
   cd frontend
   npm run dev
   ```

3. **Open Browser**:
   Navigate to `http://localhost:3000`

4. **Monitor Logs**:
   - Backend logs: Check the PowerShell windows opened by `start_system.ps1`
   - Frontend logs: Check the terminal where you ran `npm run dev`
   - Browser console: Press F12 to see WebSocket connection status

## What the Backend Does

The `src/api/server.py` file:

1. **Starts a FastAPI server** with WebSocket support
2. **Connects to Binance** for real-time market data:
   - 24hr ticker (price updates)
   - Order book depth
   - Kline/candlestick data
3. **Initializes MessageBus** for agent communication
4. **Broadcasts updates** to all connected frontend clients
5. **Manages WebSocket connections** with automatic reconnection

## Next Steps

Now that your backend is running:

1. ✅ Frontend should connect successfully
2. ✅ Real-time market data should flow to the dashboard
3. ✅ Agent updates should appear in the logs
4. ✅ Trading system should be operational

## Quick Reference

| Component | Command | Port | Status Check |
|-----------|---------|------|--------------|
| Backend API | `.\start_system.ps1` | 8000 | `curl http://127.0.0.1:8000/health` |
| Frontend | `npm run dev` | 3000 | Open browser to `http://localhost:3000` |
| Redis | `redis-server` | 6379 | `redis-cli ping` |

---

**Your system is now ready! 🎉**

The WebSocket error should be resolved, and your frontend should successfully connect to the backend.
