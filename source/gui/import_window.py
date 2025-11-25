# source/gui/import_window.py

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QFormLayout, QLineEdit, QCheckBox,
    QPushButton, QHBoxLayout, QDateEdit, QTextEdit, QLabel
)
from PySide6.QtCore import QDate
from datetime import datetime

from source.gui.import_thread import ImportThread


class ImportRideWindow(QDialog):
    """A dialog for importing new ride footage."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Import New Ride")
        self.setMinimumSize(600, 400)
        self.setModal(True)

        layout = QVBoxLayout(self)

        # Form for import settings
        form_layout = QFormLayout()

        # Camera selection
        self.cam_fly12s = QCheckBox("Fly12S")
        self.cam_fly12s.setChecked(True)
        self.cam_fly6pro = QCheckBox("Fly6Pro")
        self.cam_fly6pro.setChecked(True)
        
        cam_layout = QHBoxLayout()
        cam_layout.addWidget(self.cam_fly12s)
        cam_layout.addWidget(self.cam_fly6pro)
        form_layout.addRow("Cameras:", cam_layout)

        # Ride Date
        self.ride_date = QDateEdit(QDate.currentDate())
        self.ride_date.setCalendarPopup(True)
        self.ride_date.setDisplayFormat("yyyy-MM-dd")
        form_layout.addRow("Ride Date:", self.ride_date)

        # Ride Name
        self.ride_name = QLineEdit()
        self.ride_name.setPlaceholderText("e.g., Morning Loop")
        form_layout.addRow("Ride Name:", self.ride_name)

        layout.addLayout(form_layout)

        # Log view
        log_label = QLabel("Import Log")
        log_label.setStyleSheet("font-size: 14px; font-weight: bold; margin-top: 10px;")
        layout.addWidget(log_label)
        
        self.log_view = QTextEdit()
        self.log_view.setReadOnly(True)
        layout.addWidget(self.log_view)

        # Buttons
        btn_layout = QHBoxLayout()
        self.import_btn = QPushButton("Import")
        self.import_btn.clicked.connect(self.start_import)
        self.cancel_btn = QPushButton("Cancel")
        self.cancel_btn.clicked.connect(self.reject)
        
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
