# source/utils/gui_log_handler.py
"""
Custom logging handler that routes log messages to GUI activity log.
"""

import logging
from typing import Optional, Callable


class GUILogHandler(logging.Handler):
    """
    Logging handler that forwards messages to GUI activity log.
    Thread-safe for use with background pipeline execution.
    """
    
    def __init__(self, callback: Callable[[str, str], None]):
        """
        Args:
            callback: Function(message, level) to display log in GUI
                     level is one of: "info", "warning", "error", "success", "debug"
        """
        super().__init__()
        self.callback = callback
    
    def emit(self, record: logging.LogRecord):
        """Process a log record and send to GUI."""
        try:
            msg = self.format(record)
            
            # Map log levels to GUI display levels
            level_map = {
                logging.DEBUG: "debug",
                logging.INFO: "info",
                logging.WARNING: "warning",
                logging.ERROR: "error",
                logging.CRITICAL: "error"
            }
            
            gui_level = level_map.get(record.levelno, "info")
            
            # Check for success indicator in message
            if any(indicator in msg.lower() for indicator in ["✓", "complete", "success", "finished"]):
                gui_level = "success"
            
            # Send to GUI
            self.callback(msg, gui_level)
            
        except Exception:
            self.handleError(record)


# Global GUI handler registry
_gui_handler: Optional[GUILogHandler] = None


def attach_gui_handler(callback: Callable[[str, str], None]):
    """
    Attach GUI handler to all loggers.
    Call this when GUI starts up.
    
    Args:
        callback: Function to display log messages in GUI
    """
    global _gui_handler
    
    # Remove old handler if exists
    if _gui_handler:
        detach_gui_handler()
    
    # Create new handler
    _gui_handler = GUILogHandler(callback)
    _gui_handler.setLevel(logging.DEBUG)
    
    formatter = logging.Formatter(
        "%(message)s"  # GUI adds timestamp, so just send message
    )
    _gui_handler.setFormatter(formatter)
    
    # Attach to root logger (catches all loggers)
    root_logger = logging.getLogger()
    root_logger.addHandler(_gui_handler)
    
    # Also attach to main app loggers
    for logger_name in ["steps", "gui", "utils", "core"]:
        logger = logging.getLogger(logger_name)
        if _gui_handler not in logger.handlers:
            logger.addHandler(_gui_handler)


def detach_gui_handler():
    """Remove GUI handler from all loggers."""
    global _gui_handler
    
    if _gui_handler:
        root_logger = logging.getLogger()
        if _gui_handler in root_logger.handlers:
            root_logger.removeHandler(_gui_handler)
        
        _gui_handler = None