
# Start Redis (assuming it's a service or user handles it, but we can try to start it if needed)
# Write-Host "Ensure Redis is running..."

# Start the API Server in a new window
Write-Host "Starting API Server..."
Start-Process powershell -ArgumentList "-NoExit", "-Command", "python -m uvicorn src.api.server:app --host 0.0.0.0 --port 8000 --reload"

# Wait for API to initialize
Start-Sleep -Seconds 5

# Start the Trading System in a new window
Write-Host "Starting Trading System..."
Start-Process powershell -ArgumentList "-NoExit", "-Command", "python run_paper_trading_simulation.py"

Write-Host "System started! Run 'npm run dev' in the frontend directory to view the dashboard."
