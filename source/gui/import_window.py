# source/gui/import_window.py
"""
Import dialog for copying video clips from cameras.
UPDATED: Clean, understated visual theme.
"""

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QFormLayout, QLineEdit, QCheckBox,
    QPushButton, QHBoxLayout, QDateEdit, QTextEdit, QLabel
)
from PySide6.QtCore import QDate
from datetime import datetime

from source.gui.import_thread import ImportThread


class ImportRideWindow(QDialog):
    """A dialog for importing new ride footage with clean styling."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Import New Ride")
        self.setMinimumSize(600, 450)
        self.setModal(True)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(15)

        # Title
        title = QLabel("Import New Ride")
        title.setStyleSheet(
            "font-size: 20px; font-weight: 600; color: #1a1a1a; margin-bottom: 10px;"
        )
        layout.addWidget(title)

        # Form for import settings
        form_layout = QFormLayout()
        form_layout.setSpacing(12)
        form_layout.setContentsMargins(0, 0, 0, 0)

        # Camera selection
        self.cam_fly12s = QCheckBox("Fly12S")
        self.cam_fly12s.setChecked(True)
        self.cam_fly12s.setStyleSheet("font-size: 13px;")
        
        self.cam_fly6pro = QCheckBox("Fly6Pro")
        self.cam_fly6pro.setChecked(True)
        self.cam_fly6pro.setStyleSheet("font-size: 13px;")
        
        cam_layout = QHBoxLayout()
        cam_layout.addWidget(self.cam_fly12s)
        cam_layout.addWidget(self.cam_fly6pro)
        cam_layout.addStretch()
        
        cam_label = QLabel("Cameras:")
        cam_label.setStyleSheet("font-weight: 600; color: #333;")
        form_layout.addRow(cam_label, cam_layout)

        # Ride Date
        self.ride_date = QDateEdit(QDate.currentDate())
        self.ride_date.setCalendarPopup(True)
        self.ride_date.setDisplayFormat("yyyy-MM-dd")
        self.ride_date.setStyleSheet("""
            QDateEdit {
                padding: 6px;
                border: 2px solid #E5E5E5;
                border-radius: 4px;
                background-color: #FFFFFF;
            }
            QDateEdit:focus {
                border-color: #007AFF;
            }
        """)
        
        date_label = QLabel("Ride Date:")
        date_label.setStyleSheet("font-weight: 600; color: #333;")
        form_layout.addRow(date_label, self.ride_date)

        # Ride Name
        self.ride_name = QLineEdit()
        self.ride_name.setPlaceholderText("e.g., Morning Loop")
        self.ride_name.setStyleSheet("""
            QLineEdit {
                padding: 6px;
                border: 2px solid #E5E5E5;
                border-radius: 4px;
                background-color: #FFFFFF;
            }
            QLineEdit:focus {
                border-color: #007AFF;
            }
        """)
        
        name_label = QLabel("Ride Name:")
        name_label.setStyleSheet("font-weight: 600; color: #333;")
        form_layout.addRow(name_label, self.ride_name)

        layout.addLayout(form_layout)

        # Log view section
        log_label = QLabel("Import Log")
        log_label.setStyleSheet(
            "font-size: 14px; font-weight: 600; color: #333; margin-top: 10px;"
        )
        layout.addWidget(log_label)
        
        self.log_view = QTextEdit()
        self.log_view.setReadOnly(True)
        self.log_view.setStyleSheet("""
            QTextEdit {
                background-color: #FAFAFA;
                border: 1px solid #E5E5E5;
                border-radius: 4px;
                padding: 8px;
                font-family: 'Monaco', 'Courier New', monospace;
                font-size: 11px;
            }
        """)
        layout.addWidget(self.log_view)

        # Buttons - clean styling
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(12)
        
        self.cancel_btn = QPushButton("Cancel")
        self.cancel_btn.clicked.connect(self.reject)
        self.cancel_btn.setStyleSheet("""
            QPushButton {
                background-color: #FFFFFF;
                color: #333333;
                padding: 8px 20px;
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
        
        self.import_btn = QPushButton("Import")
        self.import_btn.clicked.connect(self.start_import)
        self.import_btn.setStyleSheet("""
            QPushButton {
                background-color: #2D7A4F;
                color: white;
                padding: 8px 20px;
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
                background-color: #F5F5F5;
                color: #AAAAAA;
                border-color: #E5E5E5;
            }
        """)
        
        btn_layout.addStretch()
        btn_layout.addWidget(self.cancel_btn)
        btn_layout.addWidget(self.import_btn)
        layout.addLayout(btn_layout)

    def start_import(self):
        self.log("Starting import process...")
        self.import_btn.setEnabled(False)
        self.cancel_btn.setText("Close")

        cameras = []
        if self.cam_fly12s.isChecked():
            cameras.append("Fly12S")
        if self.cam_fly6pro.isChecked():
            cameras.append("Fly6Pro")
            
        ride_date = self.ride_date.date().toString("yyyy-MM-dd")
        ride_name = self.ride_name.text().strip()

        if not ride_name:
            self.log("Ride Name is required.", "error")
            self.import_btn.setEnabled(True)
            return
        
        if not cameras:
            self.log("At least one camera must be selected.", "error")
            self.import_btn.setEnabled(True)
            return

        # Run the import in a separate thread
        self.thread = ImportThread(cameras, ride_date, ride_name)
        self.thread.log_message.connect(self.log)
        self.thread.import_finished.connect(self.on_import_finished)
        self.thread.error_occurred.connect(self.on_import_error)
        self.thread.start()

    def on_import_finished(self):
        self.log("Import process finished.", "success")
        self.import_btn.setEnabled(True)

    def on_import_error(self, error_message):
        self.log(f"Error during import: {error_message}", "error")
        self.import_btn.setEnabled(True)

    def log(self, message: str, level: str = "info"):
        """Add colored log message to log view."""
        color_map = {
            "info": "#333333",
            "error": "#D32F2F",
            "warning": "#F57C00",
            "success": "#2D7A4F"
        }
        color = color_map.get(level, "#333333")
        timestamp = datetime.now().strftime("%H:%M:%S")
        self.log_view.append(
            f'<span style="color: #888">[{timestamp}]</span> '
            f'<span style="color: {color}">{message}</span>'
        )
        self.log_view.ensureCursorVisible()