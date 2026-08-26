import os
import sys
from sqlalchemy import create_engine, text
from dotenv import load_dotenv

# Add src to path
sys.path.append(os.path.join(os.getcwd()))

from src.utils.config import load_config

def fix_schema():
    config = load_config()
    db_url = config.database.postgres_url
    
    print(f"Connecting to database: {db_url}")
    engine = create_engine(db_url)
    
    with engine.connect() as conn:
        print("Dropping trades table...")
        conn.execute(text("DROP TABLE IF EXISTS trades CASCADE"))
        conn.commit()
        print("Trades table dropped.")
        
    print("Schema fix complete. The table will be recreated on next run.")

if __name__ == "__main__":
    fix_schema()
