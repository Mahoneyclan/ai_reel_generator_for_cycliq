"""
Garmin import panel:
- Email/password credentials
- Connect to Garmin
- List cycling activities with date
- Download GPX to CFG.INPUT_DIR as 'ride.gpx'
- Immediately run flatten step after successful download
"""

from __future__ import annotations
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QFormLayout, QLineEdit, QPushButton, QLabel, QMessageBox
)
from PySide6.QtCore import Signal

from source.gui.gui_helpers.activity_list_panel import ActivityListPanel
from source.garmin.garmin_client import GarminClient
from source.garmin.garmin_credentials import get_credentials, set_credentials
from source.importer.import_controller import ImportController
from source.steps.flatten import run as run_flatten
from source.config import DEFAULT_CONFIG as CFG


class GarminImportPanel(QWidget):
    importCompleted = Signal(str)  # Emits saved GPX path
    statusChanged = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.client = GarminClient(log_callback=self._log)
        self.importer = ImportController(log_callback=self._log)

        layout = QVBoxLayout(self)

        # Credentials form
        form = QFormLayout()
        self.email_edit = QLineEdit()
        self.password_edit = QLineEdit()
        self.password_edit.setEchoMode(QLineEdit.Password)

        email, pwd = get_credentials()
        if email:
            self.email_edit.setText(email)
        if pwd:
            self.password_edit.setText(pwd)

        form.addRow("Email", self.email_edit)
        form.addRow("Password", self.password_edit)
        layout.addLayout(form)

        # Connect button
        self.connect_btn = QPushButton("Connect to Garmin")
        self.connect_btn.clicked.connect(self._connect)
        layout.addWidget(self.connect_btn)

        # Status
        self.status_label = QLabel("Not connected")
        layout.addWidget(self.status_label)

        # Activities list
        self.activities_panel = ActivityListPanel()
        self.activities_panel.set_header("Garmin activities")
        layout.addWidget(self.activities_panel)

        # Download button
        self.download_btn = QPushButton("Download selected GPX")
        self.download_btn.setEnabled(False)
        self.download_btn.clicked.connect(self._download_selected)
        layout.addWidget(self.download_btn)

        # Enable download when an activity is selected
        self.activities_panel.selectionChanged.connect(self._on_selection_changed)

    def _log(self, msg: str, level: str = "info") -> None:
        self.status_label.setText(msg)
        self.statusChanged.emit(msg)

    def _connect(self) -> None:
        email = self.email_edit.text().strip()
        password = self.password_edit.text().strip()
        if not email or not password:
            QMessageBox.warning(self, "Missing credentials", "Please enter email and password.")
            return

        set_credentials(email, password)
        ok = self.client.connect(email, password)
        if ok:
            self._log("✓ Garmin connected")
            self._load_activities()
        else:
            self._log("✘ Garmin connection failed")

    def _load_activities(self) -> None:
        activities = self.client.get_recent_activities(limit=50)
        self.activities_panel.populate(
            activities=activities,
            summary_fn=self._format_summary,
            id_key="activityId",
        )
        self.download_btn.setEnabled(bool(activities))

    def _format_summary(self, act: dict) -> str:
        # Include date from startTimeLocal
        date_str = act.get("startTimeLocal", "")[:10]
        name = act.get("activityName", "Activity")
        km = (act.get("distance", 0) or 0) / 1000.0
        dur = int(act.get("duration", 0))
        hrs, mins = divmod(dur // 60, 60)
        time_str = f"{hrs}h {mins}m" if hrs > 0 else f"{mins}m"
        return f"{date_str} | {name} — {km:.1f} km — {time_str}"

    def _on_selection_changed(self, activity_id: object) -> None:
        self.download_btn.setEnabled(activity_id is not None)

    def _download_selected(self) -> None:
        act_id = self.activities_panel.current_activity_id()
        if act_id is None:
            QMessageBox.warning(self, "No selection", "Please select an activity.")
            return

        # Save to project working directory
        out_path = CFG.GPX_FILE
        out_path.parent.mkdir(parents=True, exist_ok=True)
        ok = self.client.download_gpx(act_id, out_path)

        if ok:
            self._log(f"GPX saved: {out_path}")
            # Immediately flatten
            try:
                flatten_out = run_flatten()
                self._log(f"✓ Flatten complete → {flatten_out}")
            except Exception as e:
                self._log(f"Flatten failed: {e}", level="error")
                QMessageBox.warning(self, "Flatten failed", f"Could not process GPX:\n\n{e}")
                return

            # Emit completion and auto-close
            self.importCompleted.emit(str(out_path))
            self.window().accept()
        else:
            QMessageBox.warning(self, "Download failed", "Could not download GPX.")
