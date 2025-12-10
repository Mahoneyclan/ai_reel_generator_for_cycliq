"""
Strava import panel:
- OAuth connect flow
- List activities with date
- Download GPX to CFG.INPUT_DIR as 'ride.gpx'
"""

from __future__ import annotations
from PySide6.QtWidgets import QWidget, QVBoxLayout, QPushButton, QLabel, QMessageBox
from PySide6.QtCore import Signal

from source.gui.gui_helpers.activity_list_panel import ActivityListPanel
from source.strava.strava_client import StravaClient
from source.importer.import_controller import ImportController


class StravaImportPanel(QWidget):
    importCompleted = Signal(str)  # Emits saved GPX path
    statusChanged = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.client = StravaClient(log_callback=self._log)
        self.importer = ImportController(log_callback=self._log)

        layout = QVBoxLayout(self)

        # Connect button (OAuth)
        self.connect_btn = QPushButton("Connect to Strava")
        self.connect_btn.clicked.connect(self._connect)
        layout.addWidget(self.connect_btn)

        # Status
        self.status_label = QLabel("Not connected")
        layout.addWidget(self.status_label)

        # Activities list
        self.activities_panel = ActivityListPanel()
        self.activities_panel.set_header("Strava activities")
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
        ok = self.client.connect()  # use StravaClient’s connect
        if ok:
            self._log("✓ Strava connected")
            self._load_activities()
        else:
            self._log("❌ Strava connection failed")

    def _load_activities(self) -> None:
        activities = self.client.get_recent_activities(limit=50)
        self.activities_panel.populate(
            activities=activities,
            summary_fn=self._format_summary,
            id_key="id",
        )
        self.download_btn.setEnabled(bool(activities))

    def _format_summary(self, act: dict) -> str:
        # Include date from start_date_local
        date_str = act.get("start_date_local", "")[:10]
        name = act.get("name", "Activity")
        km = (act.get("distance", 0) or 0) / 1000.0
        dur = int(act.get("moving_time", 0))
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

        saved_path = self.importer.download_gpx(
            provider="strava",
            activity_id=act_id,
            downloader=lambda out_path: self.client.download_gpx(act_id, out_path),
        )
        if saved_path:
            self._log(f"GPX saved: {saved_path}")
            self.importCompleted.emit(saved_path)
            self.window().accept()  # ✅ auto-close after success
        else:
            QMessageBox.warning(self, "Download failed", "Could not download GPX.")
