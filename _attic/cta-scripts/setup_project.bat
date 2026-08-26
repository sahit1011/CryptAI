@echo off
REM Crypto Trading Agent - Project Setup Script (Windows)
REM This script sets up the project structure and initializes the environment

echo 🚀 Setting up Crypto Trading Agent project...

REM Create project structure
echo Creating directory structure...
mkdir src 2>nul
cd src
mkdir agents core data analysis strategy risk execution memory utils 2>nul
cd ..

mkdir tests 2>nul
cd tests
mkdir unit integration 2>nul
cd ..

mkdir scripts config .github\workflows 2>nul

REM Create __init__.py files
echo Creating __init__.py files...
powershell -Command "Get-ChildItem -Path src -Directory -Recurse | ForEach-Object { New-Item -Path $_.FullName -Name '__init__.py' -ItemType File -Force }"
powershell -Command "Get-ChildItem -Path tests -Directory -Recurse | ForEach-Object { New-Item -Path $_.FullName -Name '__init__.py' -ItemType File -Force }"

REM Create .gitignore
echo Creating .gitignore...
(
echo # Python
echo __pycache__/
echo *.py[cod]
echo *$py.class
echo *.so
echo .Python
echo env/
echo venv/
echo ENV/
echo.
echo # IDEs
echo .vscode/
echo .idea/
echo *.swp
echo.
echo # Environment
echo .env
echo *.log
echo.
echo # Data
echo data/
echo *.db
echo *.sqlite
echo.
echo # Testing
echo .pytest_cache/
echo .coverage
echo htmlcov/
) > .gitignore

REM Create .env.example
echo Creating .env.example...
(
echo # LLM API Keys
echo ANTHROPIC_API_KEY=your_anthropic_key_here
echo OPENAI_API_KEY=your_openai_key_here
echo.
echo # Exchange API Keys
echo BINANCE_API_KEY=your_binance_key_here
echo BINANCE_SECRET_KEY=your_binance_secret_here
echo BINGX_API_KEY=your_bingx_key_here
echo BINGX_SECRET_KEY=your_bingx_secret_here
echo.
echo # Database
echo REDIS_URL=redis://localhost:6379
echo POSTGRES_URL=postgresql://localhost:5432/trading_agent
echo.
echo # Vector Database
echo PINECONE_API_KEY=your_pinecone_key_here
echo PINECONE_ENV=your_environment
echo.
echo # Configuration
echo ENVIRONMENT=development
echo LOG_LEVEL=INFO
) > .env.example

echo ✅ Project structure created successfully!
echo.
echo 📋 Next steps:
echo 1. Copy .env.example to .env and fill in your API keys
echo 2. Run: pip install -r requirements.txt
echo 3. Run: pip install -r requirements-dev.txt
echo 4. Run: docker-compose up -d  (for Redis and PostgreSQL)
echo 5. Run: python scripts/setup_database.py
echo.
echo Happy coding! 🎯