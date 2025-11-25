# source/utils/log.py
"""
Logging setup for ride-scoped log files.

Loggers are created WITHOUT file handlers at import time.
File handlers are only added when reconfigure_loggers() is called,
which happens after a project folder is selected.

This prevents unwanted log files in the project root at startup.
"""

import logging
from ..io_paths import logs_dir, _mk

def setup_logger(name: str) -> logging.Logger:
    """Create or retrieve a logger with ONLY console handler (no file handler).
    
    File handlers are added later by reconfigure_loggers() after project selection.
    This prevents creating log files in the project root at startup.
    """
    logger = logging.getLogger(name)
    
    # Only add handlers if this logger doesn't have any yet
    if logger.handlers:
        return logger
    
    logger.setLevel(logging.DEBUG)
    
    # Only add console handler at startup (no file handler)
    # File handler will be added by reconfigure_loggers() after project selection
    sh = logging.StreamHandler()
    sh.setLevel(logging.INFO)
    formatter = logging.Formatter(
        "%(asctime)s | %(name)s | %(levelname)s | %(message)s",
        datefmt="%H:%M:%S"
    )
    sh.setFormatter(formatter)
    logger.addHandler(sh)

    return logger


def reconfigure_loggers() -> None:
    """Reconfigure all active loggers to add file handlers after project selection.
    
    This is called after CFG.RIDE_FOLDER is updated to create log files in the
    selected project folder, not in the project root.
    
    Existing log files are preserved (append mode) rather than overwritten.
    """
    log_dir = _mk(logs_dir())
    
    # Reconfigure all existing loggers to add file handlers
    for logger_name in logging.Logger.manager.loggerDict:
        logger = logging.getLogger(logger_name)
        
        # Remove existing file handlers
        for handler in logger.handlers[:]:
            if isinstance(handler, logging.FileHandler):
                logger.removeHandler(handler)
        
        # Add new file handler pointing to the project's log directory
        log_file = log_dir / f"{logger_name.replace('.', '_')}.log.txt"
        # Use append mode ("a") to preserve existing logs instead of overwriting
        fh = logging.FileHandler(log_file, mode="a")
        fh.setLevel(logging.DEBUG)
        formatter = logging.Formatter(
            "%(asctime)s | %(name)s | %(levelname)s | %(message)s",
            datefmt="%H:%M:%S"
        )
        fh.setFormatter(formatter)
        logger.addHandler(fh)