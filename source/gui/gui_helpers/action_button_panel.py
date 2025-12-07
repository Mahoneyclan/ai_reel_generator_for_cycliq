# source/gui/gui_helpers/action_button_panel.py
"""
Action button panel widget.
Horizontal bar with utility action buttons.
"""

from PySide6.QtWidgets import QWidget, QHBoxLayout, QPushButton
from PySide6.QtCore import Signal


class ActionButtonPanel(QWidget):
    """Panel with action buttons spanning full width."""
    
    import_clicked = Signal()
    gpx_clicked = Signal()
    create_clicked = Signal()
    analyze_clicked = Signal()
    log_clicked = Signal()
    music_clicked = Signal()
    prefs_clicked = Signal()
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self._setup_ui()
    
    def _setup_ui(self):
        """Setup panel UI."""
        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(8)
        
        # Create action buttons
        buttons = [
            ("Import Clips", self.import_clicked),
            ("Get GPX", self.gpx_clicked),
            ("Create New Project", self.create_clicked),
            ("Analyze Selection", self.analyze_clicked),
            ("View Log", self.log_clicked),
            ("Add Music", self.music_clicked),
            ("Preferences", self.prefs_clicked),
        ]
        
        for text, signal in buttons:
            btn = self._create_button(text)
            btn.clicked.connect(signal.emit)
            layout.addWidget(btn)
    
    def _create_button(self, text: str) -> QPushButton:
        """Create an action button."""
        btn = QPushButton(text)
        btn.setStyleSheet("""
            QPushButton {
                background-color: #F5F5F5;
                color: #333333;
                padding: 8px 12px;
                font-size: 12px;
                border: 1px solid #DDDDDD;
                border-radius: 4px;
            }
            QPushButton:hover {
                background-color: #E8E8E8;
            }
            QPushButton:pressed {
                background-color: #DDDDDD;
            }
        """)
        return btn