"""
Enhanced Logging Configuration for Trading System
Fixes formatting, race conditions, and improves clarity
"""

import sys
from pathlib import Path
from loguru import logger
from datetime import datetime
import asyncio
from contextvars import ContextVar

# Context variable for tracking current phase
current_phase: ContextVar[str] = ContextVar('current_phase', default='general')
current_agent: ContextVar[str] = ContextVar('current_agent', default='system')

class LoggingConfig:
    """Centralized logging configuration"""
    
    # ANSI color codes - using bright colors for better visibility
    COLORS = {
        'PHASE': '\033[35m',      # Magenta (bright)
        'SUCCESS': '\033[32m',    # Green (bright)
        'WARNING': '\033[33m',    # Yellow/Orange (bright)
        'ERROR': '\033[31m',      # Red (bright)
        'INFO': '\033[36m',       # Cyan (bright)
        'DEBUG': '\033[90m',      # Dark gray
        'RESET': '\033[0m',       # Reset
        'BOLD': '\033[1m',        # Bold
        'BRIGHT_CYAN': '\033[96m',    # Bright Cyan
        'BRIGHT_GREEN': '\033[92m',   # Bright Green
        'BRIGHT_YELLOW': '\033[93m',  # Bright Yellow
        'BRIGHT_RED': '\033[91m',     # Bright Red
        'BRIGHT_MAGENTA': '\033[95m', # Bright Magenta
        'BRIGHT_BLUE': '\033[94m',    # Bright Blue
    }
    
    # Phase definitions
    PHASES = {
        'setup': 'SYSTEM SETUP',
        'data_collection': 'DATA COLLECTION',
        'data_storage': 'DATA STORAGE',
        'analysis': 'MARKET ANALYSIS',
        'strategy_generation': 'STRATEGY GENERATION',
        'risk_validation': 'RISK VALIDATION',
        'results_compilation': 'RESULTS COMPILATION',
        'results_display': 'RESULTS DISPLAY',
    }
    
    # Component/Agent names
    COMPONENTS = {
        'system': 'SYSTEM',
        'exchange': 'EXCHANGE',
        'message_bus': 'MESSAGE_BUS',
        'state_manager': 'STATE_MGR',
        'analysis_agent': 'ANALYSIS',
        'strategy_agent': 'STRATEGY',
        'data_agent': 'DATA',
    }
    
    @classmethod
    def format_record(cls, record):
        """
        Custom log formatter with consistent structure and colors
        
        Format: [TIMESTAMP] [LEVEL] [COMPONENT] [PHASE] [FILE:LINE] | Message
        """
        # Extract metadata
        level = record["level"].name
        message = record["message"]
        extra = record.get("extra", {})
        
        # Get phase and component from context or extra
        phase = extra.get('phase', current_phase.get('general'))
        agent = extra.get('agent', current_agent.get('system'))
        
        # Map to display names
        phase_display = cls.PHASES.get(phase, phase.upper().replace('_', ' '))
        component_display = cls.COMPONENTS.get(agent, agent.upper())
        
        # Get timestamp
        timestamp = record["time"].strftime("%H:%M:%S.%f")[:-3]  # ms precision
        
        # Get file and line info
        file_info = extra.get('location', None)
        if not file_info:
            # Extract from record if not in extra
            file_name = Path(record["file"].name).stem
            line_no = record["line"]
            func_name = record["function"]
            file_info = f"{file_name}.py:{line_no}:{func_name}"
        
        # Select color based on level - use bright colors
        level_color_map = {
            'DEBUG': cls.COLORS['DEBUG'],
            'INFO': cls.COLORS['BRIGHT_CYAN'],
            'SUCCESS': cls.COLORS['BRIGHT_GREEN'],
            'WARNING': cls.COLORS['BRIGHT_YELLOW'],
            'ERROR': cls.COLORS['BRIGHT_RED'],
        }
        level_color = level_color_map.get(level, cls.COLORS['BRIGHT_CYAN'])
        
        # Build formatted string with colors and proper spacing
        # Level in color
        colored_level = f"{cls.COLORS['BOLD']}{level_color}{level:8}{cls.COLORS['RESET']}"
        # Component in bright cyan with bold
        colored_component = f"{cls.COLORS['BOLD']}{cls.COLORS['BRIGHT_BLUE']}{component_display:12}{cls.COLORS['RESET']}"
        # Phase in bright magenta
        colored_phase = f"{cls.COLORS['BOLD']}{cls.COLORS['BRIGHT_MAGENTA']}{phase_display:20}{cls.COLORS['RESET']}"
        # Message with appropriate color
        colored_message = f"{level_color}{message}{cls.COLORS['RESET']}"
        
        parts = [
            f"[{timestamp}]",
            f"[{colored_level}]",  # Colored level
            f"[{colored_component}]",  # Colored component
            f"[{colored_phase}]",  # Colored phase
            f"[{file_info:40}]",  # File:Line:Function
            "|",
            colored_message
        ]
        
        return " ".join(parts) + "\n"
    
    @classmethod
    def setup_logging(cls, level="INFO", log_file=None):
        """
        Setup loguru with enhanced configuration

        Args:
            level: Logging level (DEBUG, INFO, WARNING, ERROR)
            log_file: Optional file path for log output
        """
        # Remove default handler
        logger.remove()

        # Add console handler with custom format
        logger.add(
            sys.stderr,
            format=cls.format_record,
            level=level,
            colorize=True,  # Enable color support
            backtrace=False,  # Disable full tracebacks
            diagnose=False,  # Disable diagnostic info
            enqueue=True,  # Thread-safe logging
        )
        
        # Add file handler if specified
        if log_file:
            logger.add(
                log_file,
                format=cls.format_record,
                level="DEBUG",  # Always log everything to file
                rotation="100 MB",
                retention="7 days",
                compression="zip",
                enqueue=True,
            )
        
        logger.info("Logging system initialized", extra={
            'phase': 'setup',
            'agent': 'system'
        })


class PhaseLogger:
    """
    Context manager for logging phases with clear boundaries
    
    Usage:
        async with PhaseLogger("data_collection", "Fetching candles"):
            # Your code here
            pass
    """
    
    def __init__(self, phase: str, description: str, agent: str = 'system'):
        self.phase = phase
        self.description = description
        self.agent = agent
        self.start_time = None
        self.phase_token = None
        self.agent_token = None
    
    async def __aenter__(self):
        self.start_time = datetime.now()
        
        # Set context
        self.phase_token = current_phase.set(self.phase)
        self.agent_token = current_agent.set(self.agent)
        
        # Log phase start
        phase_name = LoggingConfig.PHASES.get(self.phase, self.phase.upper())
        logger.info(
            f"{'=' * 80}",
            extra={'phase': self.phase, 'agent': self.agent}
        )
        logger.info(
            f"▶ PHASE START: {phase_name} - {self.description}",
            extra={'phase': self.phase, 'agent': self.agent}
        )
        logger.info(
            f"{'=' * 80}",
            extra={'phase': self.phase, 'agent': self.agent}
        )
        
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        duration = (datetime.now() - self.start_time).total_seconds()
        
        # Reset context
        if self.phase_token:
            current_phase.reset(self.phase_token)
        if self.agent_token:
            current_agent.reset(self.agent_token)
        
        # Log phase end
        phase_name = LoggingConfig.PHASES.get(self.phase, self.phase.upper())
        
        if exc_type is None:
            logger.info(
                f"✓ PHASE COMPLETE: {phase_name} ({duration:.2f}s)",
                extra={'phase': self.phase, 'agent': self.agent}
            )
        else:
            logger.error(
                f"✗ PHASE FAILED: {phase_name} ({duration:.2f}s) - {exc_val}",
                extra={'phase': self.phase, 'agent': self.agent}
            )
        
        logger.info(
            f"{'=' * 80}\n",
            extra={'phase': self.phase, 'agent': self.agent}
        )
        
        return False  # Don't suppress exceptions


class StepLogger:
    """
    Logger for individual steps within a phase
    
    Usage:
        step = StepLogger("1.1", "Connecting to exchange")
        step.start()
        # Your code
        step.complete(success=True, details="Connected to Binance")
    """
    
    def __init__(self, step_number: str, description: str, phase: str = None, agent: str = None):
        self.step_number = step_number
        self.description = description
        self.phase = phase or current_phase.get('general')
        self.agent = agent or current_agent.get('system')
        self.start_time = None
    
    def start(self):
        """Log step start"""
        self.start_time = datetime.now()
        logger.info(
            f"  ▸ Step {self.step_number}: {self.description}",
            extra={'phase': self.phase, 'agent': self.agent}
        )
    
    def progress(self, message: str):
        """Log progress within step"""
        logger.debug(
            f"    • {message}",
            extra={'phase': self.phase, 'agent': self.agent}
        )
    
    def complete(self, success: bool = True, details: str = None, metrics: dict = None):
        """Log step completion"""
        duration = (datetime.now() - self.start_time).total_seconds()
        
        status = "✓" if success else "✗"
        level = "info" if success else "warning"
        
        message_parts = [f"  {status} Step {self.step_number} complete ({duration:.2f}s)"]
        
        if details:
            message_parts.append(f"- {details}")
        
        # Prepare extra dict with safe types (convert metrics to strings to avoid JSON serialization issues)
        extra_dict = {'phase': self.phase, 'agent': self.agent}
        if metrics:
            # Convert all metric values to strings to ensure JSON serialization compatibility
            metrics_str = ", ".join(f"{k}={str(v)}" for k, v in metrics.items())
            message_parts.append(f"[{metrics_str}]")
            # Also add serializable metrics to extra
            extra_dict['metrics'] = {k: str(v) for k, v in metrics.items()}
        
        getattr(logger, level)(
            " ".join(message_parts),
            extra=extra_dict
        )


class MetricsLogger:
    """
    Logger for performance metrics and statistics
    """
    
    @staticmethod
    def log_metrics(title: str, metrics: dict, phase: str = None, agent: str = None):
        """
        Log metrics in a formatted table
        
        Args:
            title: Metrics section title
            metrics: Dictionary of metric_name -> value
            phase: Current phase
            agent: Current agent
        """
        phase = phase or current_phase.get('general')
        agent = agent or current_agent.get('system')
        
        logger.info(
            f"\n  📊 {title}",
            extra={'phase': phase, 'agent': agent}
        )
        
        # Find longest key for alignment
        max_key_length = max(len(str(k)) for k in metrics.keys()) if metrics else 0
        
        for key, value in metrics.items():
            # Format value based on type
            if isinstance(value, float):
                if value < 1:
                    formatted_value = f"{value:.4f}"
                else:
                    formatted_value = f"{value:.2f}"
            else:
                formatted_value = str(value)
            
            logger.info(
                f"    {key:<{max_key_length}} : {formatted_value}",
                extra={'phase': phase, 'agent': agent}
            )


# Convenience functions for common logging patterns

def log_phase_start(phase: str, description: str, agent: str = 'system'):
    """Log the start of a major phase"""
    phase_name = LoggingConfig.PHASES.get(phase, phase.upper())
    logger.info(
        f"\n{'=' * 80}\n"
        f"▶ STARTING: {phase_name} - {description}\n"
        f"{'=' * 80}",
        extra={'phase': phase, 'agent': agent}
    )


def log_phase_complete(phase: str, duration: float, agent: str = 'system', metrics: dict = None):
    """Log the completion of a major phase"""
    phase_name = LoggingConfig.PHASES.get(phase, phase.upper())
    
    message = f"✓ COMPLETED: {phase_name} ({duration:.2f}s)"
    
    if metrics:
        metrics_str = ", ".join(f"{k}={v}" for k, v in metrics.items())
        message += f" [{metrics_str}]"
    
    logger.info(
        message + f"\n{'=' * 80}\n",
        extra={'phase': phase, 'agent': agent}
    )


def log_error(message: str, exception: Exception = None, phase: str = None, agent: str = None):
    """Log an error with optional exception details"""
    phase = phase or current_phase.get('general')
    agent = agent or current_agent.get('system')
    
    logger.error(
        f"✗ ERROR: {message}",
        extra={'phase': phase, 'agent': agent}
    )
    
    if exception:
        logger.exception(
            f"Exception details: {str(exception)}",
            extra={'phase': phase, 'agent': agent}
        )


def log_warning(message: str, phase: str = None, agent: str = None):
    """Log a warning"""
    phase = phase or current_phase.get('general')
    agent = agent or current_agent.get('system')
    
    logger.warning(
        f"⚠ WARNING: {message}",
        extra={'phase': phase, 'agent': agent}
    )


def log_success(message: str, phase: str = None, agent: str = None):
    """Log a success message"""
    phase = phase or current_phase.get('general')
    agent = agent or current_agent.get('system')
    
    logger.info(
        f"✓ SUCCESS: {message}",
        extra={'phase': phase, 'agent': agent}
    )


# Example usage in your code:
"""
# In test_realtime_btc_analysis.py

from src.utils.enhanced_logging import (
    LoggingConfig, PhaseLogger, StepLogger, MetricsLogger,
    log_phase_start, log_phase_complete, log_error
)

# Setup logging at start
LoggingConfig.setup_logging(
    level="INFO",
    log_file="logs/trading_system.log"
)

# Use PhaseLogger for major phases
async def run_analysis():
    async with PhaseLogger("analysis", "Running market analysis", agent="analysis_agent"):
        # Your analysis code
        
        step = StepLogger("3.1", "Preprocessing data", agent="analysis_agent")
        step.start()
        # ... preprocessing code ...
        step.complete(success=True, details="Calculated 15 indicators")
        
        step = StepLogger("3.2", "LLM analysis", agent="analysis_agent")
        step.start()
        # ... LLM call ...
        step.complete(success=True, metrics={'tokens': 16000, 'time': 26.79})

# Log metrics
MetricsLogger.log_metrics(
    "Performance Summary",
    {
        'Total Time': 27.81,
        'Opportunities Found': 2,
        'Confidence': 0.50
    },
    phase='analysis',
    agent='analysis_agent'
)
"""