# System Diagnostic Script
# Checks all components of the trading system

Write-Host "`n========================================" -ForegroundColor Cyan
Write-Host "  Trading System Diagnostic Tool" -ForegroundColor Cyan
Write-Host "========================================`n" -ForegroundColor Cyan

$allGood = $true

# 1. Check if Redis is running
Write-Host "[1/5] Checking Redis..." -ForegroundColor Yellow
try {
    $redisCheck = redis-cli ping 2>&1
    if ($redisCheck -match "PONG") {
        Write-Host "  ✅ Redis is running" -ForegroundColor Green
    } else {
        Write-Host "  ❌ Redis is not responding" -ForegroundColor Red
        Write-Host "     Run: redis-server" -ForegroundColor Gray
        $allGood = $false
    }
} catch {
    Write-Host "  ❌ Redis is not installed or not in PATH" -ForegroundColor Red
    Write-Host "     Install Redis or run: docker run -d -p 6379:6379 redis:latest" -ForegroundColor Gray
    $allGood = $false
}

# 2. Check if backend is running on port 8000
Write-Host "`n[2/5] Checking Backend Server (port 8000)..." -ForegroundColor Yellow
$port8000 = netstat -ano | findstr ":8000"
if ($port8000) {
    Write-Host "  ✅ Backend server is running on port 8000" -ForegroundColor Green
    
    # Try to hit the health endpoint
    try {
        $health = Invoke-RestMethod -Uri "http://127.0.0.1:8000/health" -Method Get -TimeoutSec 5
        Write-Host "  ✅ Health check passed" -ForegroundColor Green
        Write-Host "     Status: $($health.status)" -ForegroundColor Gray
        Write-Host "     Connections: $($health.connections)" -ForegroundColor Gray
        Write-Host "     MessageBus: $($health.message_bus)" -ForegroundColor Gray
    } catch {
        Write-Host "  ⚠️  Port 8000 is in use but health check failed" -ForegroundColor Yellow
        Write-Host "     The process might not be the backend server" -ForegroundColor Gray
        $allGood = $false
    }
} else {
    Write-Host "  ❌ No process listening on port 8000" -ForegroundColor Red
    Write-Host "     Run: cd crypto-trading-agent && .\start_system.ps1" -ForegroundColor Gray
    $allGood = $false
}

# 3. Check if frontend is running on port 3000
Write-Host "`n[3/5] Checking Frontend (port 3000)..." -ForegroundColor Yellow
$port3000 = netstat -ano | findstr ":3000"
if ($port3000) {
    Write-Host "  ✅ Frontend is running on port 3000" -ForegroundColor Green
} else {
    Write-Host "  ⚠️  Frontend not detected on port 3000" -ForegroundColor Yellow
    Write-Host "     Run: cd frontend && npm run dev" -ForegroundColor Gray
}

# 4. Check Python processes
Write-Host "`n[4/5] Checking Python processes..." -ForegroundColor Yellow
$pythonProcesses = Get-Process | Where-Object {$_.ProcessName -like "*python*"}
if ($pythonProcesses) {
    Write-Host "  ✅ Found $($pythonProcesses.Count) Python process(es)" -ForegroundColor Green
    foreach ($proc in $pythonProcesses) {
        Write-Host "     PID: $($proc.Id) - Started: $($proc.StartTime)" -ForegroundColor Gray
    }
} else {
    Write-Host "  ⚠️  No Python processes found" -ForegroundColor Yellow
    Write-Host "     Backend might not be running" -ForegroundColor Gray
}

# 5. Test WebSocket connection
Write-Host "`n[5/5] Testing WebSocket connection..." -ForegroundColor Yellow
if (Test-Path ".\frontend\test-websocket.js") {
    try {
        Push-Location ".\frontend"
        $wsTest = node test-websocket.js 2>&1 | Select-Object -First 10
        Pop-Location
        
        if ($wsTest -match "SUCCESSFUL") {
            Write-Host "  ✅ WebSocket connection test passed" -ForegroundColor Green
        } else {
            Write-Host "  ❌ WebSocket connection test failed" -ForegroundColor Red
            Write-Host "     Output: $wsTest" -ForegroundColor Gray
            $allGood = $false
        }
    } catch {
        Write-Host "  ⚠️  Could not run WebSocket test" -ForegroundColor Yellow
        Write-Host "     Error: $_" -ForegroundColor Gray
    }
} else {
    Write-Host "  ⚠️  WebSocket test script not found" -ForegroundColor Yellow
}

# Summary
Write-Host "`n========================================" -ForegroundColor Cyan
if ($allGood) {
    Write-Host "  ✅ ALL SYSTEMS OPERATIONAL" -ForegroundColor Green
    Write-Host "`n  Your trading system is ready!" -ForegroundColor Green
    Write-Host "  Dashboard: http://localhost:3000/dashboard" -ForegroundColor Cyan
} else {
    Write-Host "  ⚠️  SOME ISSUES DETECTED" -ForegroundColor Yellow
    Write-Host "`n  Please fix the issues above and run this script again." -ForegroundColor Yellow
    Write-Host "`n  Quick fix:" -ForegroundColor Cyan
    Write-Host "  1. cd crypto-trading-agent" -ForegroundColor Gray
    Write-Host "  2. .\start_system.ps1" -ForegroundColor Gray
    Write-Host "  3. cd ..\frontend" -ForegroundColor Gray
    Write-Host "  4. npm run dev" -ForegroundColor Gray
}
Write-Host "========================================`n" -ForegroundColor Cyan
