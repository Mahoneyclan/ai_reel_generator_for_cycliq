# source/gui/create_project_dialog.py
"""
Create Project dialog with timezone selection.

Captures ride metadata at project creation time:
- Source folder (videos location)
- Timezone (where the ride took place)
"""

from pathlib import Path
from typing import Optional, Tuple

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QFormLayout,
    QLabel, QPushButton, QComboBox, QLineEdit, QFileDialog
)
from PySide6.QtCore import Qt

from ..config import DEFAULT_CONFIG as CFG


class CreateProjectDialog(QDialog):
    """Dialog for creating a new project with timezone selection."""

    # Common timezones for Australian cycling
    TIMEZONES = [
        ("UTC+10:30 - Adelaide (ACDT)", "UTC+10:30"),
        ("UTC+10 - Brisbane/Sydney (AEST)", "UTC+10"),
        ("UTC+11 - Sydney DST (AEDT)", "UTC+11"),
        ("UTC+9:30 - Adelaide Std (ACST)", "UTC+9:30"),
        ("UTC+8 - Perth (AWST)", "UTC+8"),
        ("UTC+12 - New Zealand (NZST)", "UTC+12"),
        ("UTC+13 - New Zealand DST (NZDT)", "UTC+13"),
        ("UTC+0 - UTC/GMT", "UTC+0"),
        ("UTC-5 - US Eastern (EST)", "UTC-5"),
        ("UTC-8 - US Pacific (PST)", "UTC-8"),
    ]

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Create New Project")
        self.setMinimumWidth(500)
        self.setModal(True)

        self.selected_folder: Optional[Path] = None
        self.selected_timezone: str = "UTC+10"  # Default

        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(15)

        # Title
        title = QLabel("Create New Project")
        title.setStyleSheet(
            "font-size: 18px; font-weight: 600; color: #1a1a1a; margin-bottom: 5px;"
        )
        layout.addWidget(title)

        # Description
        desc = QLabel(
            "Select the folder containing your ride videos and set the timezone "
            "where the ride took place. This ensures accurate time alignment between "
            "video and GPS data."
        )
        desc.setWordWrap(True)
        desc.setStyleSheet("color: #666; font-size: 12px; margin-bottom: 10px;")
        layout.addWidget(desc)

        # Form
        form = QFormLayout()
        form.setSpacing(12)
        form.setLabelAlignment(Qt.AlignRight | Qt.AlignVCenter)

        # Source folder
        folder_layout = QHBoxLayout()
        self.folder_edit = QLineEdit()
        self.folder_edit.setReadOnly(True)
        self.folder_edit.setPlaceholderText("Select folder with video files...")
        self.folder_edit.setStyleSheet("""
            QLineEdit {
                padding: 8px;
                border: 2px solid #E5E5E5;
                border-radius: 4px;
                background-color: #FAFAFA;
            }
        """)

        browse_btn = QPushButton("Browse...")
        browse_btn.clicked.connect(self._browse_folder)
        browse_btn.setStyleSheet("""
            QPushButton {
                padding: 8px 16px;
                border: 2px solid #E5E5E5;
                border-radius: 4px;
                background-color: #FFFFFF;
            }
            QPushButton:hover {
                background-color: #F5F5F5;
                border-color: #CCCCCC;
            }
        """)

        folder_layout.addWidget(self.folder_edit, 1)
        folder_layout.addWidget(browse_btn)

        folder_label = QLabel("Source Folder:")
        folder_label.setStyleSheet("font-weight: 600;")
        form.addRow(folder_label, folder_layout)

        # Timezone
        self.timezone_combo = QComboBox()
        self.timezone_combo.setStyleSheet("""
            QComboBox {
                padding: 8px;
                border: 2px solid #E5E5E5;
                border-radius: 4px;
                background-color: #FFFFFF;
            }
            QComboBox:focus {
                border-color: #007AFF;
            }
        """)

        for label, value in self.TIMEZONES:
            self.timezone_combo.addItem(label, value)

        # Default to Brisbane/Sydney (UTC+10) - most common
        self.timezone_combo.setCurrentIndex(1)

        tz_label = QLabel("Ride Timezone:")
        tz_label.setStyleSheet("font-weight: 600;")
        form.addRow(tz_label, self.timezone_combo)

        # Timezone help text
        tz_help = QLabel(
            "The timezone where you recorded the ride. This corrects the camera's "
            "timestamp metadata for accurate GPS alignment."
        )
        tz_help.setWordWrap(True)
        tz_help.setStyleSheet("color: #888; font-size: 11px; margin-left: 5px;")
        form.addRow("", tz_help)

        layout.addLayout(form)

        # Folder info (shown after selection)
        self.folder_info = QLabel("")
        self.folder_info.setStyleSheet("color: #666; font-size: 11px; margin-top: 5px;")
        self.folder_info.setWordWrap(True)
        layout.addWidget(self.folder_info)

        layout.addStretch()

        # Buttons
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(12)

        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        cancel_btn.setStyleSheet("""
            QPushButton {
                background-color: #FFFFFF;
                color: #333333;
                padding: 10px 24px;
                font-size: 13px;
                font-weight: 600;
                border: 2px solid #DDDDDD;
                border-radius: 6px;
            }
            QPushButton:hover {
                background-color: #F8F9FA;
                border-color: #CCCCCC;
            }
        """)

        self.create_btn = QPushButton("Create Project")
        self.create_btn.clicked.connect(self._on_create)
        self.create_btn.setEnabled(False)
        self.create_btn.setStyleSheet("""
            QPushButton {
                background-color: #2D7A4F;
                color: white;
                padding: 10px 24px;
                font-size: 13px;
                font-weight: 600;
                border: 2px solid #2D7A4F;
                border-radius: 6px;
            }
            QPushButton:hover {
                background-color: #246840;
                border-color: #246840;
            }
            QPushButton:disabled {
                background-color: #E5E5E5;
                color: #AAAAAA;
                border-color: #E5E5E5;
            }
        """)

        btn_layout.addStretch()
        btn_layout.addWidget(cancel_btn)
        btn_layout.addWidget(self.create_btn)
        layout.addLayout(btn_layout)

    def _browse_folder(self):
        """Open folder selection dialog."""
        start_dir = str(CFG.INPUT_BASE_DIR) if CFG.INPUT_BASE_DIR.exists() else ""
        folder = QFileDialog.getExistingDirectory(
            self,
            "Select Folder with Video Files",
            start_dir
        )

        if folder:
            self.selected_folder = Path(folder)
            self.folder_edit.setText(folder)
            self._update_folder_info()
            self.create_btn.setEnabled(True)

    def _update_folder_info(self):
        """Show info about selected folder."""
        if not self.selected_folder or not self.selected_folder.exists():
            self.folder_info.setText("")
            return

        # Count video files
        video_extensions = {'.mp4', '.mov', '.avi', '.mkv', '.m4v'}
        video_files = [
            f for f in self.selected_folder.iterdir()
            if f.is_file() and f.suffix.lower() in video_extensions
        ]

        # Check for GPX
        gpx_files = list(self.selected_folder.glob("*.gpx"))

        info_parts = [f"Found {len(video_files)} video file(s)"]
        if gpx_files:
            info_parts.append(f"{len(gpx_files)} GPX file(s)")
        else:
            info_parts.append("no GPX file (can import later)")

        self.folder_info.setText(" • ".join(info_parts))

        # Warn if no videos
        if not video_files:
            self.folder_info.setStyleSheet("color: #D32F2F; font-size: 11px;")
            self.folder_info.setText("Warning: No video files found in this folder")
        else:
            self.folder_info.setStyleSheet("color: #2D7A4F; font-size: 11px;")

    def _on_create(self):
        """Handle create button click."""
        self.selected_timezone = self.timezone_combo.currentData()
        self.accept()

    def get_result(self) -> Tuple[Optional[Path], str]:
        """
        Get dialog result.

        Returns:
            Tuple of (source_folder, timezone) or (None, "") if cancelled
        """
        if self.result() == QDialog.Accepted and self.selected_folder:
            return (self.selected_folder, self.selected_timezone)
        return (None, "")
