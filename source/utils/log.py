# source/utils/log.py
"""
Logging setup for ride-scoped log files.

Loggers are created WITHOUT console handlers at import time.
File handlers are only added when reconfigure_loggers() is called,
which happens after a project folder is selected.

This prevents unwanted log files in the project root at startup
and eliminates terminal spam.
"""

import logging
from ..io_paths import logs_dir, _mk

def setup_logger(name: str) -> logging.Logger:
    """Create or retrieve a logger with no console handler.
    
    File handlers are added later by reconfigure_loggers() after project selection.
    GUI handlers are attached separately via gui_log_handler.
    """
    logger = logging.getLogger(name)
    
    if logger.handlers:
        return logger
    
    logger.setLevel(logging.DEBUG)
    # Do NOT add a StreamHandler — prevents terminal output
    return logger


def reconfigure_loggers() -> None:
    """Reconfigure all active loggers to add file handlers after project selection.
    
    This is called after CFG.RIDE_FOLDER is updated to create log files in the
    selected project folder, not in the project root.
    
    Existing log files are preserved (append mode) rather than overwritten.
    """
    log_dir = _mk(logs_dir())
    
    for logger_name in logging.Logger.manager.loggerDict:
        logger = logging.getLogger(logger_name)
        
        # Remove existing file handlers
        for handler in logger.handlers[:]:
            if isinstance(handler, logging.FileHandler):
                logger.removeHandler(handler)
        
        # Add new file handler pointing to the project's log directory
        log_file = log_dir / f"{logger_name.replace('.', '_')}.log.txt"
        fh = logging.FileHandler(log_file, mode="a")
        fh.setLevel(logging.DEBUG)
        formatter = logging.Formatter(
            "%(asctime)s | %(name)s | %(levelname)s | %(message)s",
            datefmt="%H:%M:%S"
        )
        fh.setFormatter(formatter)
        logger.addHandler(fh)
