# source/gui/gui_helpers/action_button_panel.py
"""
Top action bar panel with project-independent actions.

Buttons that DON'T require a project:
- Import Raw Video
- Create Ride Project
- Add Music
- Settings (global app config)

Project-specific buttons are in pipeline_panel.py:
- Pipeline steps (GPX, Extract, Enrich, Select, Build)
- Project Tools (Summary, View Log, Preferences, Calibrate)
"""

from PySide6.QtWidgets import QWidget, QHBoxLayout, QLabel, QPushButton, QFrame
from PySide6.QtCore import Signal


class ActionButtonPanel(QFrame):
    """
    Top action bar with project-independent actions only.
    These work WITHOUT a project selected.
    """
    
    # Project-independent signals
    import_clicked = Signal()
    create_clicked = Signal()
    archive_clicked = Signal()  # Archive project to storage
    music_clicked = Signal()
    settings_clicked = Signal()  # Global app settings
    
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

        self.archive_btn = self._create_button(
            "📦 Archive Project",
            "Move project to archive storage"
        )
        self.archive_btn.clicked.connect(self.archive_clicked.emit)
        self.archive_btn.setEnabled(False)  # Requires project selection
        layout.addWidget(self.archive_btn)

        music_btn = self._create_button(
            "🎵 Add Music",
            "Add background music tracks"
        )
        music_btn.clicked.connect(self.music_clicked.emit)
        layout.addWidget(music_btn)

        settings_btn = self._create_button(
            "⚙️ Settings",
            "Global app settings (paths, video, M1)"
        )
        settings_btn.clicked.connect(self.settings_clicked.emit)
        layout.addWidget(settings_btn)
        
        layout.addStretch()
    
    def set_archive_enabled(self, enabled: bool):
        """Enable/disable archive button based on project selection."""
        self.archive_btn.setEnabled(enabled)

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