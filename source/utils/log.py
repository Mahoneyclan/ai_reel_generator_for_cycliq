# source/utils/log.py
"""
Logging setup for ride-scoped log files.

Loggers are created at import time without handlers.
File handlers are added dynamically when reconfigure_loggers() is called
after a project folder is selected.

This prevents unwanted log files in the project root at startup
and eliminates terminal spam.
"""

import logging
from pathlib import Path
from typing import Optional

# Module-level registry to track configured loggers
_configured_loggers = set()


def setup_logger(name: str, level: int = logging.DEBUG) -> logging.Logger:
    """
    Create or retrieve a logger without console handlers.
    
    File handlers are added later by reconfigure_loggers() after project selection.
    GUI handlers are attached separately via gui_log_handler.
    
    Args:
        name: Logger name (e.g., "steps.extract")
        level: Logging level (default: DEBUG)
    
    Returns:
        Configured logger instance
    """
    logger = logging.getLogger(name)
    logger.setLevel(level)
    logger.propagate = False  # Prevent duplicate logs to root logger
    
    return logger


def reconfigure_loggers() -> None:
    """
    Reconfigure all active loggers to write to project log directory.
    
    This is called after CFG.RIDE_FOLDER is updated to create log files in the
    selected project folder, not in the project root.
    
    Process:
    1. Remove all existing file handlers from all loggers
    2. Add new file handlers pointing to current project's log directory
    3. Preserve any GUI/stream handlers that were added separately
    
    Existing log files are preserved (append mode) rather than overwritten.
    """
    from ..io_paths import logs_dir, _mk
    
    log_dir = _mk(logs_dir())
    
    # Get all active loggers
    logger_names = list(logging.Logger.manager.loggerDict.keys())
    
    # Also include root logger
    loggers_to_configure = [logging.getLogger(name) for name in logger_names]
    loggers_to_configure.append(logging.getLogger())
    
    for logger in loggers_to_configure:
        # Remove ONLY file handlers, preserve GUI/stream handlers
        handlers_to_remove = [
            h for h in logger.handlers 
            if isinstance(h, logging.FileHandler)
        ]
        
        for handler in handlers_to_remove:
            handler.close()
            logger.removeHandler(handler)
        
        # Only add file handler if this logger is actually used
        if logger.name and not logger.name.startswith('matplotlib'):
            # Create sanitized filename from logger name
            log_filename = logger.name.replace('.', '_') + ".log.txt"
            log_file = log_dir / log_filename
            
            # Create file handler
            try:
                fh = logging.FileHandler(log_file, mode="a", encoding="utf-8")
                fh.setLevel(logging.DEBUG)
                
                # Detailed format for file logs
                formatter = logging.Formatter(
                    "%(asctime)s | %(name)s | %(levelname)-8s | %(message)s",
                    datefmt="%Y-%m-%d %H:%M:%S"
                )
                fh.setFormatter(formatter)
                
                logger.addHandler(fh)
                _configured_loggers.add(logger.name)
                
            except Exception as e:
                # If file handler creation fails, continue without it
                print(f"Warning: Could not create log file handler for {logger.name}: {e}")


def get_configured_loggers() -> set:
    """Return set of logger names that have been configured with file handlers."""
    return _configured_loggers.copy()


def clear_logger_configuration():
    """
    Remove all file handlers from all loggers.
    Used for cleanup or when switching projects.
    """
    logger_names = list(logging.Logger.manager.loggerDict.keys())
    loggers_to_clear = [logging.getLogger(name) for name in logger_names]
    loggers_to_clear.append(logging.getLogger())
    
    for logger in loggers_to_clear:
        handlers_to_remove = [
            h for h in logger.handlers 
            if isinstance(h, logging.FileHandler)
        ]
        
        for handler in handlers_to_remove:
            handler.close()
            logger.removeHandler(handler)
    
    _configured_loggers.clear()


def setup_console_logger(name: str, level: int = logging.INFO) -> logging.Logger:
    """
    Create a logger WITH console output.
    
    Use this for standalone scripts that need terminal output.
    GUI application should NOT use this.
    
    Args:
        name: Logger name
        level: Console output level (default: INFO)
    
    Returns:
        Logger with console handler attached
    """
    logger = setup_logger(name, level)
    
    # Check if console handler already exists
    has_console = any(
        isinstance(h, logging.StreamHandler) and not isinstance(h, logging.FileHandler)
        for h in logger.handlers
    )
    
    if not has_console:
        console = logging.StreamHandler()
        console.setLevel(level)
        formatter = logging.Formatter(
            "[%(levelname)s] %(name)s: %(message)s"
        )
        console.setFormatter(formatter)
        logger.addHandler(console)
    
    return logger