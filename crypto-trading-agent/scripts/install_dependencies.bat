@echo off
REM Crypto Trading Agent - Dependencies Installation Script (Windows)
REM This script installs all required Python packages and sets up external dependencies

echo 🚀 Installing dependencies for Crypto Trading Agent...

REM Check if we're in the right directory
if not exist "requirements.txt" (
    echo Error: requirements.txt not found. Please run this script from the project root.
    exit /b 1
)

REM Create virtual environment if it doesn't exist
if not exist "venv" (
    echo Creating virtual environment...
    python -m venv venv
    if errorlevel 1 (
        echo Error: Failed to create virtual environment. Make sure Python 3.11+ is installed.
        exit /b 1
    )
)

REM Activate virtual environment
echo Activating virtual environment...
call venv\Scripts\activate.bat
if errorlevel 1 (
    echo Error: Failed to activate virtual environment.
    exit /b 1
)

REM Upgrade pip
echo Upgrading pip...
python -m pip install --upgrade pip setuptools wheel
if errorlevel 1 (
    echo Warning: Failed to upgrade pip, continuing anyway...
)

REM Install TA-Lib (requires system dependencies)
echo Installing TA-Lib system dependencies...
echo Note: TA-Lib requires Microsoft Visual C++ Build Tools if not already installed.
echo If installation fails, download from: https://visualstudio.microsoft.com/visual-cpp-build-tools/

REM Try to install TA-Lib via conda if available, otherwise pip
where conda >nul 2>nul
if %errorlevel% == 0 (
    echo Installing TA-Lib via conda...
    conda install -c conda-forge ta-lib -y
) else (
    echo Installing TA-Lib via pip...
    pip install ta-lib
)

REM Install Python dependencies
echo Installing Python dependencies...
pip install -r requirements.txt
if errorlevel 1 (
    echo Error: Failed to install main requirements.
    exit /b 1
)

pip install -r requirements-dev.txt
if errorlevel 1 (
    echo Error: Failed to install development requirements.
    exit /b 1
)

REM Check if Docker is available
where docker >nul 2>nul
if %errorlevel% == 0 (
    echo Starting Docker services...
    docker-compose up -d
    if errorlevel 1 (
        echo Warning: Failed to start Docker services. Make sure Docker is running.
        echo You can start them manually with: docker-compose up -d
    ) else (
        echo ✅ Redis running on localhost:6379
        echo ✅ PostgreSQL running on localhost:5432
        echo ✅ PgAdmin available at http://localhost:5050
    )
) else (
    echo Warning: Docker not found. Please install Docker Desktop and run:
    echo docker-compose up -d
)

REM Verify installations
echo Verifying installations...
python -c "import pandas, numpy, redis, sqlalchemy; print('✅ Core dependencies installed successfully!')"

echo.
echo ✅ Dependencies installed successfully!
echo.
echo 📋 Next steps:
echo 1. Copy .env.example to .env and fill in your API keys
echo 2. Run: python scripts/setup_database.py
echo 3. Run: pytest tests/ -v (to verify everything works)
echo.
echo Happy coding! 🎯

REM Deactivate virtual environment
call deactivate