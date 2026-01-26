"""
Centralized logging system using Loguru
"""
from loguru import logger
import sys
from pathlib import Path
from src.utils.config import get_config

def setup_logger():
    """Configure Loguru logger"""

    config = get_config()

    # Remove default handler
    logger.remove()

    # Console handler with colors
    logger.add(
        sys.stdout,
        colorize=True,
        format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan> | <level>{message}</level>",
        level=config.log_level
    )

    # File handler with rotation
    log_path = Path("logs")
    log_path.mkdir(exist_ok=True)

    logger.add(
        log_path / "trading_agent_{time:YYYY-MM-DD}.log",
        rotation="00:00",  # New file at midnight
        retention="30 days",
        compression="zip",
        format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {name}:{function}:{line} | {message}",
        level="DEBUG"
    )

    # Error file handler
    logger.add(
        log_path / "errors_{time:YYYY-MM-DD}.log",
        rotation="00:00",
        retention="90 days",
        compression="zip",
        format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {name}:{function}:{line} | {message}",
        level="ERROR"
    )

    # Data agent specific logging
    data_agent_log_path = log_path / "data_agent_logs"
    data_agent_log_path.mkdir(exist_ok=True)

    logger.add(
        data_agent_log_path / "websocket_data_{time:YYYY-MM-DD}.log",
        rotation="00:00",
        retention="7 days",
        compression="zip",
        format="{time:YYYY-MM-DD HH:mm:ss.SSS} | {level: <8} | {name}:{function}:{line} | {message}",
        level="DEBUG",
        filter=lambda record: "data_agent" in record["name"].lower() or "websocket" in record["message"].lower()
    )

    logger.add(
        data_agent_log_path / "data_processing_{time:YYYY-MM-DD}.log",
        rotation="00:00",
        retention="7 days",
        compression="zip",
        format="{time:YYYY-MM-DD HH:mm:ss.SSS} | {level: <8} | {name}:{function}:{line} | {message}",
        level="INFO",
        filter=lambda record: "DataAgent" in record["message"] or "data_agent" in record["name"].lower()
    )

    return logger

# Initialize logger
log = setup_logger()