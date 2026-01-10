# source/gui/controllers/ui_builder.py
"""
UI component builder.
Creates styled buttons, layouts, and widgets.
"""

from PySide6.QtWidgets import QPushButton, QLabel, QTextEdit, QProgressBar
from typing import Callable


class UIBuilder:
    """Factory for creating styled UI components."""
    
    @staticmethod
    def create_step_button(text: str, tooltip: str, callback: Callable) -> QPushButton:
        """
        Create a styled pipeline step button.
        
        Args:
            text: Button label
            tooltip: Tooltip text
            callback: Click handler function
            
        Returns:
            Configured QPushButton
        """
        btn = QPushButton(text)
        btn.clicked.connect(callback)
        btn.setMinimumHeight(60)
        btn.setToolTip(tooltip)
        btn.setStyleSheet("""
            QPushButton {
                background-color: #007AFF;
                color: white;
                font-size: 16px;
                font-weight: bold;
                border-radius: 8px;
                text-align: left;
                padding-left: 20px;
            }
            QPushButton:hover {
                background-color: #0051D5;
            }
            QPushButton:disabled {
                background-color: #CCCCCC;
                color: #888888;
            }
        """)
        return btn
    
    @staticmethod
    def create_action_button(text: str, tooltip: str = "") -> QPushButton:
        """
        Create a styled action button (smaller, bottom panel style).
        
        Args:
            text: Button label
            tooltip: Optional tooltip text
            
        Returns:
            Configured QPushButton
        """
        btn = QPushButton(text)
        if tooltip:
            btn.setToolTip(tooltip)
        btn.setStyleSheet("""
            QPushButton {
                padding: 8px 16px;
                font-size: 13px;
                border-radius: 4px;
                background-color: #F0F0F0;
            }
            QPushButton:hover {
                background-color: #E0E0E0;
            }
        """)
        return btn
    
    @staticmethod
    def create_section_label(text: str, font_size: int = 16, bold: bool = True) -> QLabel:
        """
        Create a styled section header label.
        
        Args:
            text: Label text
            font_size: Font size in pixels
            bold: Whether to use bold font
            
        Returns:
            Configured QLabel
        """
        label = QLabel(text)
        style = f"font-size: {font_size}px;"
        if bold:
            style += " font-weight: bold;"
        style += " padding: 10px;"
        label.setStyleSheet(style)
        return label
    
    @staticmethod
    def create_info_label(text: str = "") -> QLabel:
        """
        Create an info label (secondary text style).
        
        Args:
            text: Initial text
            
        Returns:
            Configured QLabel
        """
        label = QLabel(text)
        label.setStyleSheet("color: #666; font-size: 12px;")
        return label
    
    @staticmethod
    def create_log_view() -> QTextEdit:
        """
        Create a read-only log viewer.
        
        Returns:
            Configured QTextEdit
        """
        log_view = QTextEdit()
        log_view.setReadOnly(True)
        log_view.setStyleSheet("""
            QTextEdit {
                background-color: #FAFAFA;
                border: 1px solid #DDDDDD;
                border-radius: 4px;
                padding: 8px;
                font-family: 'Menlo', 'SF Mono', 'Monaco', 'Courier New';
                font-size: 11px;
            }
        """)
        return log_view
    
    @staticmethod
    def create_progress_bar() -> QProgressBar:
        """
        Create a styled progress bar.
        
        Returns:
            Configured QProgressBar
        """
        progress = QProgressBar()
        progress.setStyleSheet("""
            QProgressBar {
                border: 1px solid #DDDDDD;
                border-radius: 4px;
                text-align: center;
                height: 24px;
            }
            QProgressBar::chunk {
                background-color: #007AFF;
                border-radius: 3px;
            }
        """)
        progress.setVisible(False)
        return progress