#!/usr/bin/env python3
"""
Test script for Configuration & Logging System (Ticket 1.1.4)
"""
import os
import sys
from pathlib import Path

# Add src to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))
sys.path.insert(0, str(project_root / "src"))

from src.utils.config import get_config, load_config
from src.utils.logger import log, setup_logger
import tempfile
import shutil

def test_config_loading():
    """Test configuration loading from YAML and environment"""
    print("Testing configuration loading...")

    # Test default config loading
    config = get_config()
    assert config.environment == "development"
    assert config.log_level == "INFO"
    assert config.trading.initial_capital == 10000
    assert config.trading.symbols == ["BTCUSDT", "ETHUSDT"]
    print("Default config loaded successfully")

    # Test environment override
    os.environ["ENVIRONMENT"] = "test"
    os.environ["LOG_LEVEL"] = "DEBUG"
    config_test = load_config("test")
    assert config_test.environment == "test"
    assert config_test.log_level == "DEBUG"
    print("Environment variable override works")

    # Clean up
    del os.environ["ENVIRONMENT"]
    del os.environ["LOG_LEVEL"]

def test_logging_functionality():
    """Test logging functionality"""
    print("Testing logging functionality...")

    # Create temporary log directory
    temp_log_dir = Path(tempfile.mkdtemp())
    original_log_path = Path("logs")

    try:
        # Temporarily modify logger to use temp directory
        import src.utils.logger as logger_module
        logger_module.log.remove()

        # Add temp directory handlers
        logger_module.log.add(
            sys.stdout,
            colorize=True,
            format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan> | <level>{message}</level>",
            level="INFO"
        )

        logger_module.log.add(
            temp_log_dir / "test_trading_agent_{time:YYYY-MM-DD}.log",
            rotation="00:00",
            retention="30 days",
            compression="zip",
            format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {name}:{function}:{line} | {message}",
            level="DEBUG"
        )

        logger_module.log.add(
            temp_log_dir / "test_errors_{time:YYYY-MM-DD}.log",
            rotation="00:00",
            retention="90 days",
            compression="zip",
            format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {name}:{function}:{line} | {message}",
            level="ERROR"
        )

        # Test different log levels
        log.info("Test info message")
        log.debug("Test debug message")
        log.warning("Test warning message")
        log.error("Test error message")

        # Check if log files were created
        log_files = list(temp_log_dir.glob("*.log"))
        assert len(log_files) >= 1, "Log files should be created"
        print("Log files created successfully")

        # Check log content
        with open(log_files[0], 'r') as f:
            content = f.read()
            assert "Test info message" in content
            assert "Test error message" in content
        print("Log content verification passed")

    finally:
        # Close all log handlers
        logger_module.log.remove()
        # Restore original logger
        setup_logger()
        # Cleanup temp directory
        import time
        time.sleep(0.1)  # Small delay to ensure file handles are released
        shutil.rmtree(temp_log_dir)

def test_yaml_config_structure():
    """Test YAML configuration structure"""
    print("Testing YAML configuration structure...")

    config = get_config()

    # Test LLM config
    assert hasattr(config.llm, 'claude_model')
    assert hasattr(config.llm, 'gpt_model')
    assert config.llm.claude_model == "claude-sonnet-4-20250514"

    # Test trading config
    assert hasattr(config.trading, 'symbols')
    assert isinstance(config.trading.symbols, list)
    assert "BTCUSDT" in config.trading.symbols

    # Test exchange config
    assert hasattr(config.exchange, 'testnet')
    assert config.exchange.testnet == True

    print("YAML configuration structure validated")

def main():
    """Run all tests"""
    print("Starting Configuration & Logging System Tests\n")

    try:
        test_config_loading()
        test_yaml_config_structure()
        test_logging_functionality()

        print("\nAll tests passed! Configuration & Logging System is working correctly.")
        print("Ticket 1.1.4 implementation verified.")

    except Exception as e:
        print(f"\nTest failed: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()