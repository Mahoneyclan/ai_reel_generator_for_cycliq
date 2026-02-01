# source/gui/archive_dialog.py
"""
Archive Project Dialog.

Allows user to move projects between storage locations.
"""

from __future__ import annotations
from pathlib import Path
from typing import Optional

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QComboBox, QProgressBar, QGroupBox, QCheckBox, QMessageBox
)
from PySide6.QtCore import Qt, QThread, Signal

from ..utils.archiver import (
    STORAGE_LOCATIONS,
    get_available_locations,
    get_project_location,
    get_raw_source_path,
    calculate_archive_size,
    archive_project,
)
from ..utils.log import setup_logger

log = setup_logger("gui.archive_dialog")


def format_size(size_bytes: int) -> str:
    """Format bytes as human-readable size."""
    if size_bytes < 1024:
        return f"{size_bytes} B"
    elif size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.1f} KB"
    elif size_bytes < 1024 * 1024 * 1024:
        return f"{size_bytes / (1024 * 1024):.1f} MB"
    else:
        return f"{size_bytes / (1024 * 1024 * 1024):.2f} GB"


class ArchiveWorker(QThread):
    """Background thread for archive operation."""

    progress = Signal(str, int)  # message, percent
    finished = Signal(bool, str)  # success, message

    def __init__(
        self,
        project_path: Path,
        destination: str,
        include_raw: bool,
        parent=None
    ):
        super().__init__(parent)
        self.project_path = project_path
        self.destination = destination
        self.include_raw = include_raw

    def run(self):
        success, message = archive_project(
            self.project_path,
            self.destination,
            progress_callback=self._on_progress,
            include_raw=self.include_raw,
        )
        self.finished.emit(success, message)

    def _on_progress(self, message: str, percent: int):
        self.progress.emit(message, percent)


class ArchiveDialog(QDialog):
    """Dialog for archiving projects between storage locations."""

    # Emitted when archive completes successfully
    archive_completed = Signal(str)  # new project path

    def __init__(self, project_path: Path, parent=None):
        super().__init__(parent)
        self.project_path = project_path
        self.worker: Optional[ArchiveWorker] = None

        self.setWindowTitle("Archive Project")
        self.setMinimumWidth(500)
        self.setModal(True)

        self._setup_ui()
        self._load_project_info()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(15)

        # Project info
        info_group = QGroupBox("Project Information")
        info_layout = QVBoxLayout(info_group)

        self.project_name_label = QLabel()
        self.project_name_label.setStyleSheet("font-weight: bold; font-size: 14px;")
        info_layout.addWidget(self.project_name_label)

        self.current_location_label = QLabel()
        info_layout.addWidget(self.current_location_label)

        self.raw_source_label = QLabel()
        self.raw_source_label.setWordWrap(True)
        info_layout.addWidget(self.raw_source_label)

        self.size_label = QLabel()
        info_layout.addWidget(self.size_label)

        layout.addWidget(info_group)

        # Destination selection
        dest_group = QGroupBox("Destination")
        dest_layout = QVBoxLayout(dest_group)

        dest_row = QHBoxLayout()
        dest_row.addWidget(QLabel("Move to:"))

        self.dest_combo = QComboBox()
        self.dest_combo.setMinimumWidth(200)
        dest_row.addWidget(self.dest_combo)
        dest_row.addStretch()

        dest_layout.addLayout(dest_row)

        self.dest_info_label = QLabel()
        self.dest_info_label.setStyleSheet("color: #666; font-size: 11px;")
        dest_layout.addWidget(self.dest_info_label)

        self.dest_combo.currentTextChanged.connect(self._on_dest_changed)

        layout.addWidget(dest_group)

        # Options
        options_group = QGroupBox("Options")
        options_layout = QVBoxLayout(options_group)

        self.include_raw_checkbox = QCheckBox("Include raw source files")
        self.include_raw_checkbox.setChecked(True)
        self.include_raw_checkbox.setToolTip(
            "Also move the original video files from the source folder"
        )
        options_layout.addWidget(self.include_raw_checkbox)

        layout.addWidget(options_group)

        # Progress
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        layout.addWidget(self.progress_bar)

        self.status_label = QLabel()
        self.status_label.setStyleSheet("color: #666;")
        self.status_label.setVisible(False)
        layout.addWidget(self.status_label)

        # Buttons
        btn_layout = QHBoxLayout()

        self.cancel_btn = QPushButton("Cancel")
        self.cancel_btn.clicked.connect(self.reject)

        self.archive_btn = QPushButton("Archive")
        self.archive_btn.setStyleSheet("""
            QPushButton {
                background-color: #007AFF;
                color: white;
                padding: 8px 20px;
                font-weight: bold;
                border: none;
                border-radius: 4px;
            }
            QPushButton:hover {
                background-color: #0056b3;
            }
            QPushButton:disabled {
                background-color: #ccc;
            }
        """)
        self.archive_btn.clicked.connect(self._start_archive)

        btn_layout.addWidget(self.cancel_btn)
        btn_layout.addStretch()
        btn_layout.addWidget(self.archive_btn)

        layout.addLayout(btn_layout)

    def _load_project_info(self):
        """Load and display project information."""
        project_name = self.project_path.name
        self.project_name_label.setText(project_name)

        # Current location
        current_loc = get_project_location(self.project_path)
        if current_loc:
            loc_info = STORAGE_LOCATIONS[current_loc]
            self.current_location_label.setText(
                f"Current location: {current_loc} ({loc_info['description']})"
            )
        else:
            self.current_location_label.setText(f"Current location: {self.project_path.parent}")

        # Raw source
        raw_path = get_raw_source_path(self.project_path)
        if raw_path:
            self.raw_source_label.setText(f"Raw source: {raw_path}")
        else:
            self.raw_source_label.setText("Raw source: (not linked)")
            self.include_raw_checkbox.setChecked(False)
            self.include_raw_checkbox.setEnabled(False)

        # Calculate sizes
        project_size, raw_size = calculate_archive_size(self.project_path)
        total_size = project_size + raw_size
        self.size_label.setText(
            f"Size: Project {format_size(project_size)} + Raw {format_size(raw_size)} = {format_size(total_size)}"
        )

        # Populate destinations (exclude current location)
        available = get_available_locations()
        for loc in available:
            if loc != current_loc:
                self.dest_combo.addItem(loc, loc)

        if self.dest_combo.count() == 0:
            self.archive_btn.setEnabled(False)
            self.dest_info_label.setText("No other storage locations available")

    def _on_dest_changed(self, dest_name: str):
        """Update destination info when selection changes."""
        if dest_name in STORAGE_LOCATIONS:
            info = STORAGE_LOCATIONS[dest_name]
            self.dest_info_label.setText(
                f"{info['description']}\n"
                f"Projects: {info['projects']}\n"
                f"Raw: {info['raw']}"
            )

    def _start_archive(self):
        """Start the archive operation."""
        destination = self.dest_combo.currentData()
        if not destination:
            return

        # Confirm
        include_raw = self.include_raw_checkbox.isChecked()
        raw_msg = " and raw source files" if include_raw else ""

        reply = QMessageBox.question(
            self,
            "Confirm Archive",
            f"Move project '{self.project_path.name}'{raw_msg} to {destination}?\n\n"
            "This operation may take several minutes for large projects.",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.Yes
        )

        if reply != QMessageBox.Yes:
            return

        # Disable UI
        self.archive_btn.setEnabled(False)
        self.cancel_btn.setEnabled(False)
        self.dest_combo.setEnabled(False)
        self.include_raw_checkbox.setEnabled(False)

        # Show progress
        self.progress_bar.setVisible(True)
        self.progress_bar.setValue(0)
        self.status_label.setVisible(True)
        self.status_label.setText("Starting archive...")

        # Start worker
        self.worker = ArchiveWorker(
            self.project_path,
            destination,
            include_raw,
            parent=self
        )
        self.worker.progress.connect(self._on_progress)
        self.worker.finished.connect(self._on_finished)
        self.worker.start()

    def _on_progress(self, message: str, percent: int):
        """Handle progress updates."""
        self.progress_bar.setValue(percent)
        self.status_label.setText(message)

    def _on_finished(self, success: bool, message: str):
        """Handle archive completion."""
        self.worker = None

        if success:
            self.status_label.setText("Archive complete!")
            self.status_label.setStyleSheet("color: #28a745; font-weight: bold;")

            # Get new path
            dest = self.dest_combo.currentData()
            new_path = STORAGE_LOCATIONS[dest]["projects"] / self.project_path.name

            QMessageBox.information(
                self,
                "Archive Complete",
                f"Project archived successfully!\n\nNew location: {new_path}"
            )

            self.archive_completed.emit(str(new_path))
            self.accept()
        else:
            self.status_label.setText(f"Error: {message}")
            self.status_label.setStyleSheet("color: #dc3545;")

            QMessageBox.critical(self, "Archive Failed", message)

            # Re-enable UI
            self.archive_btn.setEnabled(True)
            self.cancel_btn.setEnabled(True)
            self.dest_combo.setEnabled(True)
            self.include_raw_checkbox.setEnabled(True)
