# source/gui/gui_helpers/activity_log_panel.py
"""
Activity log panel widget.
Displays colored log messages with timestamps.
"""

from datetime import datetime
from PySide6.QtWidgets import QWidget, QVBoxLayout, QLabel, QTextEdit


class ActivityLogPanel(QWidget):
    """Panel displaying activity log with colored messages."""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self._setup_ui()
    
    def _setup_ui(self):
        """Setup panel UI."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        
        # Header
        header = QLabel("Activity Log")
        header.setStyleSheet("font-size: 14px; font-weight: bold;")
        layout.addWidget(header)
        
        # Log view
        self.log_view = QTextEdit()
        self.log_view.setReadOnly(True)
        self.log_view.setMinimumHeight(120)
        self.log_view.setStyleSheet("""
            QTextEdit {
                background-color: #FAFAFA;
                border: 1px solid #DDDDDD;
                border-radius: 4px;
                padding: 8px;
                font-family: 'Menlo', 'SF Mono', 'Monaco', 'Courier New';
                font-size: 11px;
            }
        """)
        layout.addWidget(self.log_view)
    
    def log(self, message: str, level: str = "info"):
        """
        Add colored log message.
        
        Args:
            message: Log message text
            level: Log level (info, error, warning, success)
        """
        color_map = {
            "info": "#000000",
            "error": "#FF0000",
            "warning": "#FF9500",
            "success": "#00C853"
        }
        
        color = color_map.get(level, "#000000")
        timestamp = datetime.now().strftime("%H:%M:%S")
        
        self.log_view.append(
            f'<span style="color: #888">[{timestamp}]</span> '
            f'<span style="color: {color}">{message}</span>'
        )
        self.log_view.ensureCursorVisible()
    
    def clear(self):
        """Clear all log messages."""
        self.log_view.clear()