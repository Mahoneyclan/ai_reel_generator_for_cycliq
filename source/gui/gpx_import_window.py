# source/gui/gpx_import_window.py
"""
GPX Import Window (refactored): a slim tabbed container delegating
to provider-specific panels for Garmin and Strava.

- Keeps public signals and external interface clean.
- All provider-specific logic lives in helper panels.
"""

from __future__ import annotations
from PySide6.QtWidgets import QDialog, QVBoxLayout, QTabWidget
from PySide6.QtCore import Signal

from source.gui.gui_helpers.garmin_import_panel import GarminImportPanel
from source.gui.gui_helpers.strava_import_panel import StravaImportPanel


class GPXImportWindow(QDialog):
    """
    Main import window with Garmin and Strava tabs.
    Emits signals for status and import-complete events.
    """
    importCompleted = Signal(str)  # Emits saved GPX path
    statusChanged = Signal(str)    # Emits status messages

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Import GPX")
        self.setMinimumSize(900, 600)

        layout = QVBoxLayout(self)
        self.tabs = QTabWidget()
        layout.addWidget(self.tabs)

        # Panels
        self.garmin_panel = GarminImportPanel()
        self.strava_panel = StravaImportPanel()

        # Wire child signals to window signals
        self.garmin_panel.importCompleted.connect(self.importCompleted.emit)
        self.strava_panel.importCompleted.connect(self.importCompleted.emit)

        self.garmin_panel.statusChanged.connect(self.statusChanged.emit)
        self.strava_panel.statusChanged.connect(self.statusChanged.emit)

        self.tabs.addTab(self.garmin_panel, "Garmin Connect")
        self.tabs.addTab(self.strava_panel, "Strava")
