# WebSocket Connection Troubleshooting Guide

## Current Status ✅

Based on testing:
- ✅ Backend server is running on port 8000
- ✅ WebSocket endpoint `/ws` is accessible
- ✅ Node.js can connect successfully
- ✅ Messages are being received from Binance

## Issues Found

### 1. Runtime Error (FIXED ✅)
**Error**: `Cannot read properties of undefined (reading 'toLocaleString')`

**Fix Applied**: Updated `OverviewSection.tsx` to handle `undefined` values:
```typescript
const formatCurrency = (value: number | undefined) => {
    if (value === undefined || value === null) return "---";
    // ... rest of function
}
```

### 2. WebSocket Error in Browser (INVESTIGATING 🔍)
**Error**: `WebSocket error: {}`

**Possible Causes**:
1. Browser security/CORS restrictions
2. Next.js hot reload interfering with WebSocket
3. Connection timing issue during page load
4. Browser caching old code

## Solutions to Try

### Solution 1: Hard Refresh the Browser
The frontend code has been updated. Clear the browser cache:
1. Open your dashboard at `http://localhost:3000/dashboard`
2. Press `Ctrl + Shift + R` (Windows) or `Cmd + Shift + R` (Mac)
3. Or press `F12` → Right-click refresh button → "Empty Cache and Hard Reload"

### Solution 2: Check Browser Console
1. Press `F12` to open Developer Tools
2. Go to the "Console" tab
3. Look for the enhanced error messages now showing:
   - WebSocket readyState
   - Connection URL
   - Detailed error information

### Solution 3: Verify Backend is Running
Run this command to check backend health:
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

### Solution 4: Restart Backend (If Needed)
If the backend isn't responding:

```powershell
# Navigate to backend directory
cd crypto-trading-agent

# Run the startup script
.\start_system.ps1
```

This will open two PowerShell windows:
- Window 1: API Server (uvicorn)
- Window 2: Paper Trading Simulation

### Solution 5: Check for Port Conflicts
```powershell
# Check what's using port 8000
netstat -ano | findstr :8000

# If wrong process, kill it (replace PID)
taskkill /PID <PID> /F

# Then restart backend
cd crypto-trading-agent
.\start_system.ps1
```

## Testing the Connection

### Test 1: HTML Test Page
Open `test_websocket_connection.html` in your browser:
1. Navigate to the file in File Explorer
2. Right-click → Open with → Your browser
3. Should show "✅ Connected to backend WebSocket"
4. Should display incoming Binance market data

### Test 2: Node.js Test Script
```powershell
cd frontend
node test-websocket.js
```

Should output:
```
✅ WebSocket connection SUCCESSFUL!
📨 Received message: depthUpdate
📨 Received message: 24hrTicker
```

## Expected Behavior After Fixes

### In Browser Console (F12)
```
WebSocket error occurred: {
  readyState: 3,
  url: "ws://127.0.0.1:8000/ws",
  error: Event {...}
}
❌ Cannot connect to backend. Please ensure:
   1. Backend server is running on port 8000
   2. Run: cd crypto-trading-agent && .\start_system.ps1
   3. Or manually: python -m uvicorn src.api.server:app --host 0.0.0.0 --port 8000 --reload
```

OR if successful:
```
✅ Connected to backend WebSocket
```

### In Dashboard UI
- Connection indicator should show "Connected" (green)
- Portfolio values should show "---" until data arrives
- No runtime errors about `toLocaleString`

## Common Issues

### Issue: "WebSocket error: {}"
**Cause**: Backend not running or connection refused  
**Solution**: Run `.\start_system.ps1` in `crypto-trading-agent` directory

### Issue: "Cannot read properties of undefined"
**Cause**: Portfolio data not initialized  
**Solution**: Already fixed! Hard refresh browser (Ctrl+Shift+R)

### Issue: Connection keeps disconnecting
**Cause**: Backend crashed or Redis not running  
**Solution**: 
1. Check backend PowerShell window for errors
2. Ensure Redis is running: `redis-cli ping`
3. Restart backend

### Issue: "ERR_CONNECTION_REFUSED"
**Cause**: Backend server not listening on port 8000  
**Solution**: 
1. Check if backend is running: `netstat -ano | findstr :8000`
2. Start backend: `.\start_system.ps1`

## Next Steps

1. **Hard refresh your browser** (Ctrl+Shift+R) to load the updated code
2. **Check the browser console** (F12) for the new detailed error messages
3. **Verify backend is running**: `curl http://127.0.0.1:8000/health`
4. **Test with HTML page**: Open `test_websocket_connection.html`

## Files Modified

✅ `frontend/src/components/dashboard/sections/OverviewSection.tsx`
   - Fixed `formatCurrency` and `formatPercent` to handle undefined values

✅ `frontend/src/hooks/useMarketData.ts`
   - Enhanced WebSocket error logging
   - Added helpful troubleshooting messages

✅ Created test files:
   - `test_websocket_connection.html` - Browser WebSocket test
   - `frontend/test-websocket.js` - Node.js WebSocket test

## Summary

The runtime error is **FIXED** ✅. The WebSocket connection should work after a hard browser refresh. If you still see WebSocket errors, check the browser console for the new detailed error messages that will help diagnose the issue.

**Most likely solution**: Hard refresh your browser with `Ctrl + Shift + R`
