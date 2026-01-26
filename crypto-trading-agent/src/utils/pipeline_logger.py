"""
Pipeline-specific logging utilities with file/line/method tracking
Extends enhanced_logging with detailed trace information
"""

import inspect
from loguru import logger
from pathlib import Path
from typing import Optional, Dict, Any
from .enhanced_logging import current_phase, current_agent


def get_caller_info() -> Dict[str, str]:
    """
    Get detailed information about the calling function
    
    Returns:
        Dict with file, line, function, and class information
    """
    frame = inspect.currentframe().f_back.f_back
    info = inspect.getframeinfo(frame)
    
    # Get function name
    func_name = frame.f_code.co_name
    
    # Try to get class name if it's a method
    class_name = None
    if 'self' in frame.f_locals:
        class_name = frame.f_locals['self'].__class__.__name__
    
    # Get relative file path
    file_path = Path(info.filename)
    try:
        # Try to get relative path from project root
        relative_path = file_path.relative_to(Path.cwd())
    except ValueError:
        # If not in project, use last 2 parts
        relative_path = Path(*file_path.parts[-2:])
    
    return {
        'file': str(relative_path),
        'line': info.lineno,
        'function': func_name,
        'class': class_name,
        'method': f"{class_name}.{func_name}" if class_name else func_name
    }


class PipelineLogger:
    """
    Enhanced logger that includes file/line/method information
    """
    
    @staticmethod
    def _log(level: str, message: str, **kwargs):
        """Internal log method with caller info"""
        caller = get_caller_info()
        
        # Build location string
        if caller['class']:
            location = f"{caller['file']}:{caller['line']} [{caller['class']}.{caller['function']}]"
        else:
            location = f"{caller['file']}:{caller['line']} [{caller['function']}]"
        
        # Get extra context
        extra = kwargs.pop('extra', {})
        phase = kwargs.pop('phase', None) or extra.get('phase', current_phase.get('general'))
        agent = kwargs.pop('agent', None) or extra.get('agent', current_agent.get('system'))
        
        # Safely convert message to string (handle long exception messages)
        try:
            message_str = str(message)
        except Exception:
            message_str = repr(message)
        
        # Merge location into extra
        extra.update({
            'phase': phase,
            'agent': agent,
            'location': location,
            **caller
        })
        
        # Enhanced message with location
        # Escape curly braces to prevent loguru from interpreting them as formatting
        enhanced_message = f"{message_str} [{location}]".replace("{", "{{").replace("}", "}}")
        
        # Log with proper level
        log_func = getattr(logger, level)
        log_func(enhanced_message, extra=extra, **kwargs)
    
    @staticmethod
    def debug(message: str, **kwargs):
        """Log debug message with caller info"""
        PipelineLogger._log('debug', message, **kwargs)
    
    @staticmethod
    def info(message: str, **kwargs):
        """Log info message with caller info"""
        PipelineLogger._log('info', message, **kwargs)
    
    @staticmethod
    def success(message: str, **kwargs):
        """Log success message with caller info"""
        PipelineLogger._log('success', message, **kwargs)
    
    @staticmethod
    def warning(message: str, **kwargs):
        """Log warning message with caller info"""
        PipelineLogger._log('warning', message, **kwargs)
    
    @staticmethod
    def error(message: str, exception: Optional[Exception] = None, **kwargs):
        """Log error message with caller info and optional exception"""
        PipelineLogger._log('error', message, **kwargs)
        
        if exception:
            # Use logger.exception to get full traceback with file/line info
            # Handle exception repr safely (e.g., KeyError includes extra quotes)
            try:
                exc_str = str(exception)
            except Exception:
                exc_str = repr(exception)
            
            logger.exception(
                f"Exception details: {exc_str}",
                extra={
                    **kwargs.get('extra', {}),
                    'caller_info': get_caller_info()
                }
            )
    
    @staticmethod
    def phase_marker(phase_name: str, action: str = "ENTER", **kwargs):
        """
        Log phase markers for pipeline tracking
        
        Args:
            phase_name: Name of the phase
            action: ENTER, EXIT, or STEP
            **kwargs: Additional context
        """
        caller = get_caller_info()
        extra = kwargs.get('extra', {})
        extra['location'] = f"{caller['file']}:{caller['line']}"
        
        markers = {
            'ENTER': '▶',
            'EXIT': '◀',
            'STEP': '▸'
        }
        marker = markers.get(action, '•')
        
        logger.info(
            f"{marker} {action}: {phase_name} [{caller['file']}:{caller['line']}]",
            extra=extra
        )
    
    @staticmethod
    def method_entry(method_name: str = None, **kwargs):
        """Log method entry with params"""
        caller = get_caller_info()
        method = method_name or caller['method']
        
        logger.debug(
            f"→ Entering {method} [{caller['file']}:{caller['line']}]",
            extra=kwargs.get('extra', {})
        )
    
    @staticmethod
    def method_exit(method_name: str = None, result: Any = None, **kwargs):
        """Log method exit with result"""
        caller = get_caller_info()
        method = method_name or caller['method']
        
        msg = f"← Exiting {method}"
        if result is not None:
            msg += f" | Result: {result}"
        msg += f" [{caller['file']}:{caller['line']}]"
        
        logger.debug(msg, extra=kwargs.get('extra', {}))
