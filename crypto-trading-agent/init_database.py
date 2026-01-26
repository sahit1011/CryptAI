#!/usr/bin/env python3
"""
Initialize PostgreSQL Database
Creates all required tables for the trading system
"""

import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from sqlalchemy import create_engine, text
from loguru import logger
from rich.console import Console
from rich.panel import Panel

console = Console()

# Database connection
DATABASE_URL = "postgresql://trader:secure_password_here@localhost:5432/trading_agent"

def init_database():
    """Initialize database with all required tables"""
    
    console.print(Panel.fit(
        "[bold cyan]Initializing PostgreSQL Database[/bold cyan]\n"
        f"Database: trading_agent\n"
        f"Host: localhost:5432"
    ))
    
    try:
        # Create engine
        engine = create_engine(DATABASE_URL, echo=False)
        
        with engine.connect() as conn:
            # Test connection
            result = conn.execute(text("SELECT version()"))
            version = result.fetchone()[0]
            console.print(f"✅ Connected to PostgreSQL: {version[:50]}...")
            
            # Check if trades table exists
            result = conn.execute(text("""
                SELECT EXISTS (
                    SELECT FROM information_schema.tables 
                    WHERE table_name = 'trades'
                )
            """))
            table_exists = result.fetchone()[0]
            
            if table_exists:
                console.print("\n[yellow]trades table already exists - checking schema...[/yellow]")
                
                # Get existing columns
                result = conn.execute(text("""
                    SELECT column_name 
                    FROM information_schema.columns 
                    WHERE table_name = 'trades'
                """))
                existing_columns = {row[0] for row in result.fetchall()}
                console.print(f"  Existing columns: {len(existing_columns)}")
                
                # Add missing columns
                required_columns = {
                    'market_regime': 'VARCHAR(50)',
                    'atr_at_entry': 'DECIMAL(20, 8)',
                    'smc_patterns': 'JSONB',
                    'ict_setups': 'JSONB',
                    'risk_reward_ratio': 'DECIMAL(10, 2)',
                    'confidence_score': 'DECIMAL(5, 4)',
                    'confluence_count': 'INTEGER'
                }
                
                for col_name, col_type in required_columns.items():
                    if col_name not in existing_columns:
                        try:
                            conn.execute(text(f"""
                                ALTER TABLE trades 
                                ADD COLUMN {col_name} {col_type}
                            """))
                            console.print(f"  ✅ Added column: {col_name}")
                        except Exception as e:
                            console.print(f"  ⚠️  Could not add {col_name}: {str(e)[:50]}")
                
                conn.commit()
                
            else:
                # Create trades table
                console.print("\n[bold]Creating tables...[/bold]")
                
                conn.execute(text("""
                    CREATE TABLE trades (
                        id SERIAL PRIMARY KEY,
                        trade_id VARCHAR(100) UNIQUE NOT NULL,
                        symbol VARCHAR(20) NOT NULL,
                        direction VARCHAR(10) NOT NULL,
                        entry_price DECIMAL(20, 8) NOT NULL,
                        entry_time TIMESTAMP NOT NULL,
                        exit_price DECIMAL(20, 8),
                        exit_time TIMESTAMP,
                        position_size DECIMAL(20, 8) NOT NULL,
                        stop_loss DECIMAL(20, 8) NOT NULL,
                        take_profit_levels JSONB,
                        risk_amount DECIMAL(20, 8) NOT NULL,
                        pnl DECIMAL(20, 8),
                        pnl_percentage DECIMAL(10, 4),
                        is_winner BOOLEAN,
                        strategy_type VARCHAR(50),
                        confidence_score DECIMAL(5, 4),
                        confluence_count INTEGER,
                        market_regime VARCHAR(50),
                        atr_at_entry DECIMAL(20, 8),
                        smc_patterns JSONB,
                        ict_setups JSONB,
                        exit_reason VARCHAR(100),
                        notes TEXT,
                        risk_reward_ratio DECIMAL(10, 2),
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                """))
                console.print("  ✅ trades table created")
                conn.commit()
            
            # Create indexes (safe - IF NOT EXISTS)
            console.print("\n[bold]Creating indexes...[/bold]")
            conn.execute(text("""
                CREATE INDEX IF NOT EXISTS idx_trades_symbol ON trades(symbol)
            """))
            conn.execute(text("""
                CREATE INDEX IF NOT EXISTS idx_trades_entry_time ON trades(entry_time)
            """))
            conn.execute(text("""
                CREATE INDEX IF NOT EXISTS idx_trades_strategy ON trades(strategy_type)
            """))
            console.print("  ✅ Indexes created")
            conn.commit()
            
            # Create performance_snapshots table
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS performance_snapshots (
                    id SERIAL PRIMARY KEY,
                    snapshot_time TIMESTAMP NOT NULL,
                    total_trades INTEGER,
                    win_rate DECIMAL(5, 4),
                    profit_factor DECIMAL(10, 4),
                    total_pnl DECIMAL(20, 8),
                    sharpe_ratio DECIMAL(10, 4),
                    max_drawdown DECIMAL(10, 4),
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """))
            console.print("  ✅ performance_snapshots table created")
            conn.commit()
            
            # Check table counts
            result = conn.execute(text("SELECT COUNT(*) FROM trades"))
            trade_count = result.fetchone()[0]
            
            console.print(f"\n[bold green]Database initialized successfully![/bold green]")
            console.print(f"  Existing trades: {trade_count}")
            
    except Exception as e:
        console.print(f"\n[bold red]Error initializing database:[/bold red]")
        console.print(f"  {str(e)}")
        logger.error(f"Database initialization failed: {e}")
        raise

if __name__ == "__main__":
    init_database()
