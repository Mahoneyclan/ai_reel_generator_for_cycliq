# source/gui/gui_helpers/action_button_panel.py
"""
Top action bar panel with project-independent actions.
MIGRATED from action_button_panel.py - kept only non-project buttons.

Buttons that DON'T require a project:
- Import Raw Video
- Create Ride Project
- Add Music
- Preferences

Moved to pipeline_steps_panel.py:
- Get GPX (project-specific)
- Analyze Selection (project-specific)
- View Log (project-specific)
"""

from PySide6.QtWidgets import QWidget, QHBoxLayout, QLabel, QPushButton, QFrame
from PySide6.QtCore import Signal


class ActionButtonPanel(QFrame):
    """
    Top action bar with project-independent actions only.
    These work WITHOUT a project selected.
    """
    
    # Project-independent signals (from old action_button_panel.py)
    import_clicked = Signal()
    create_clicked = Signal()
    music_clicked = Signal()
    prefs_clicked = Signal()
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self._setup_ui()
    
    def _setup_ui(self):
        """Setup panel UI."""
        self.setStyleSheet("""
            QFrame {
                background-color: #F5F5F5;
                border-bottom: 1px solid #DDDDDD;
            }
        """)
        
        layout = QHBoxLayout(self)
        layout.setContentsMargins(15, 10, 15, 10)
        layout.setSpacing(10)
        
        # Title
        title = QLabel("Actions")
        title.setStyleSheet("font-size: 13px; font-weight: 600; color: #666;")
        layout.addWidget(title)
        
        layout.addSpacing(10)
        
        # Project-independent action buttons (always enabled)
        import_btn = self._create_button(
            "📥 Import Raw Video", 
            "Import video clips from cameras"
        )
        import_btn.clicked.connect(self.import_clicked.emit)
        layout.addWidget(import_btn)
        
        create_btn = self._create_button(
            "➕ Create Ride Project", 
            "Create a new ride project from source folder"
        )
        create_btn.clicked.connect(self.create_clicked.emit)
        layout.addWidget(create_btn)
        
        music_btn = self._create_button(
            "🎵 Add Music", 
            "Add background music tracks"
        )
        music_btn.clicked.connect(self.music_clicked.emit)
        layout.addWidget(music_btn)
        
        prefs_btn = self._create_button(
            "⚙️ Preferences", 
            "Configure pipeline settings"
        )
        prefs_btn.clicked.connect(self.prefs_clicked.emit)
        layout.addWidget(prefs_btn)
        
        layout.addStretch()
    
    def _create_button(self, text: str, tooltip: str) -> QPushButton:
        """Create styled action button."""
        btn = QPushButton(text)
        btn.setToolTip(tooltip)
        btn.setStyleSheet("""
            QPushButton {
                background-color: #FFFFFF;
                color: #333333;
                padding: 8px 16px;
                font-size: 13px;
                font-weight: 600;
                border: 2px solid #DDDDDD;
                border-radius: 4px;
            }
            QPushButton:hover {
                background-color: #F8F9FA;
                border-color: #007AFF;
            }
        """)
        return btn