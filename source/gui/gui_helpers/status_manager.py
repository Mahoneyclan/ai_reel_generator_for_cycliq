# source/gui/gui_helpers/status_manager.py
"""
Status bar and logging manager.
Handles status bar updates and log message routing.
"""

from PySide6.QtWidgets import QMainWindow


class StatusManager:
    """Manages status bar and logging for main window."""
    
    def __init__(self, main_window: QMainWindow):
        """
        Args:
            main_window: Parent main window with statusBar()
        """
        self.main_window = main_window
        self.log_callback = None
    
    def set_log_callback(self, callback):
        """Set callback for log messages."""
        self.log_callback = callback
    
    def show_ready(self):
        """Show ready status."""
        self.main_window.statusBar().showMessage("Ready")
    
    def show_running(self, step_name: str):
        """Show step running status."""
        self.main_window.statusBar().showMessage(f"Running: {step_name}")
    
    def show_progress(self, step_name: str, current: int, total: int):
        """Show progress status."""
        if total > 0:
            pct = int((current / total) * 100)
            status = f"{step_name}: {current}/{total} ({pct}%)"
            self.main_window.statusBar().showMessage(status)
    
    def show_error(self, step_name: str):
        """Show error status."""
        self.main_window.statusBar().showMessage(f"Error: {step_name} failed")
    
    def log(self, message: str, level: str = "info"):
        """
        Log message to activity log.
        
        Args:
            message: Log message text
            level: Log level (info, error, warning, success)
        """
        if self.log_callback:
            self.log_callback(message, level)