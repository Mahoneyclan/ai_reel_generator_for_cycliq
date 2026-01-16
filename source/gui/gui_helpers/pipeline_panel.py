# source/gui/gui_helpers/pipeline_panel.py
"""
Pipeline steps panel with project-specific workflow.
MIGRATED from pipeline_panel.py + project-specific buttons from action_button_panel.py

Pipeline workflow:
- Get GPX
- Extract
- Enrich (detection, scoring, telemetry)
- Select
- Build

Special tools:
- Project Summary
- View Log

Signal naming clarification:
- enrich_clicked = Run the Enrich pipeline step
- project_summary_clicked = Open project summary report
"""

from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QFrame
from PySide6.QtCore import Signal


class PipelinePanel(QWidget):
    """
    Panel displaying pipeline steps and project info.
    All features require a project to be selected.
    """

    # Pipeline step signals (from old pipeline_panel.py)
    gpx_clicked = Signal()          # Get GPX
    prepare_clicked = Signal()      # Extract
    enrich_clicked = Signal()       # Runs enrich step (detection, scoring)
    select_clicked = Signal()
    build_clicked = Signal()        # Renamed from finalize_clicked

    # Project tool signals
    project_summary_clicked = Signal()
    view_log_clicked = Signal()
    project_settings_clicked = Signal()  # Project-specific settings (audio, pipeline params)
    camera_calibration_clicked = Signal()  # Camera offset calibration tool

    def __init__(self, parent=None):
        super().__init__(parent)
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(12)

        # Project info header (from old pipeline_panel.py)
        self.project_name_label = QLabel("No project loaded")
        self.project_name_label.setStyleSheet("font-size: 18px; font-weight: bold; color: #1a1a1a;")
        layout.addWidget(self.project_name_label)

        self.project_info_label = QLabel()
        self.project_info_label.setStyleSheet("font-size: 12px; color: #666;")
        layout.addWidget(self.project_info_label)

        # Separator
        layout.addWidget(self._create_separator())

        # Pipeline steps header
        steps_label = QLabel("Pipeline Steps")
        steps_label.setStyleSheet("font-size: 14px; font-weight: 600; color: #666; padding: 10px 0 5px 0;")
        layout.addWidget(steps_label)

        # ---------------------------------------------------------------------
        # Pipeline step buttons (with explicit dependencies and outputs)
        # ---------------------------------------------------------------------

        # Get GPX: download/import GPX and create flatten.csv
        self.btn_gpx = self._create_button(
            "Get GPX",
            "Download or import GPX (Strava/Garmin) and generate flatten.csv.\n"
            "Required before extraction.\n"
            "Produces: ride.gpx, flatten.csv",
            self.gpx_clicked
        )
        layout.addWidget(self.btn_gpx)

        # Extract: generate frame metadata using GPX-anchored grid
        self.btn_prepare = self._create_button(
            "Extract",
            "Generate frame metadata using GPX-anchored sampling grid.\n"
            "Requires: flatten.csv\n"
            "Produces: extract.csv",
            self.prepare_clicked
        )
        layout.addWidget(self.btn_prepare)

        # Enrich: detection, scene, telemetry, partner matching
        self.btn_enrich = self._create_button(
            "Enrich",
            "Run object detection, scene detection, telemetry enrichment, and partner matching.\n"
            "Requires: extract.csv\n"
            "Produces: enriched.csv",
            self.enrich_clicked
        )
        layout.addWidget(self.btn_enrich)

        # Select: candidate pool + gap filtering + recommended clips
        self.btn_select = self._create_button(
            "Select",
            "AI recommends clips based on scores and scene changes.\n"
            "Requires: enriched.csv\n"
            "Produces: select.csv",
            self.select_clicked
        )
        layout.addWidget(self.btn_select)

        # Build: render clips, intro/outro, final reel
        self.btn_build = self._create_button(
            "Build",
            "Render highlight clips with overlays, create intro/outro, and assemble the final video.\n"
            "Requires: select.csv\n"
            "Produces: clips/, minimaps/, gauges/, _middle_XX.mp4, _intro.mp4, _outro.mp4, final reel",
            self.build_clicked
        )
        layout.addWidget(self.btn_build)

        # Separator
        layout.addWidget(self._create_separator())

        # Special project tools (moved from action_button_panel.py)
        special_label = QLabel("Project Tools")
        special_label.setStyleSheet("font-size: 14px; font-weight: 600; color: #666; padding: 10px 0 5px 0;")
        layout.addWidget(special_label)

        special_layout = QHBoxLayout()
        special_layout.setSpacing(10)

        # Project summary
        self.project_summary_btn = self._create_special_button(
            "📊 Summary",
            "View project summary with detection stats, selection metrics, and pipeline diagnostics"
        )
        self.project_summary_btn.clicked.connect(self.project_summary_clicked.emit)
        special_layout.addWidget(self.project_summary_btn)

        # View log
        self.view_log_btn = self._create_special_button(
            "📄 View Log",
            "View detailed log files for this project"
        )
        self.view_log_btn.clicked.connect(self.view_log_clicked.emit)
        special_layout.addWidget(self.view_log_btn)

        # Project preferences
        self.project_settings_btn = self._create_special_button(
            "Preferences",
            "Project-specific preferences (audio track, pipeline parameters)"
        )
        self.project_settings_btn.clicked.connect(self.project_settings_clicked.emit)
        special_layout.addWidget(self.project_settings_btn)

        # Camera calibration (same row)
        self.camera_calibration_btn = self._create_special_button(
            "Calibrate",
            "Compare burnt-in timestamps with calculated times to calibrate camera timing offsets.\n"
            "Use this to verify/adjust KNOWN_OFFSETS based on actual video footage."
        )
        self.camera_calibration_btn.clicked.connect(self.camera_calibration_clicked.emit)
        special_layout.addWidget(self.camera_calibration_btn)

        layout.addLayout(special_layout)

        layout.addStretch()

        # Store button references for state management
        self.pipeline_buttons = {
            "gpx": self.btn_gpx,
            "prepare": self.btn_prepare,
            "enrich": self.btn_enrich,
            "select": self.btn_select,
            "build": self.btn_build
        }

        self.special_buttons = [self.project_summary_btn, self.view_log_btn, self.project_settings_btn, self.camera_calibration_btn]

    def _create_separator(self) -> QFrame:
        """Create horizontal separator."""
        separator = QFrame()
        separator.setFrameShape(QFrame.HLine)
        separator.setStyleSheet("background-color: #DDDDDD;")
        return separator

    def _create_button(self, text: str, tooltip: str, signal: Signal) -> QPushButton:
        """Create pipeline step button."""
        btn = QPushButton(text)
        btn.clicked.connect(signal.emit)
        btn.setMinimumHeight(60)
        btn.setMinimumWidth(240)
        btn.setToolTip(tooltip)
        btn.setProperty("original_text", text)
        btn.setStyleSheet(self._get_default_style())
        return btn

    def _create_special_button(self, text: str, tooltip: str) -> QPushButton:
        """Create special project tool button."""
        btn = QPushButton(text)
        btn.setToolTip(tooltip)
        btn.setStyleSheet("""
            QPushButton {
                background-color: #F0F9F4;
                color: #2D7A4F;
                padding: 10px 16px;
                font-size: 13px;
                font-weight: 600;
                border: 2px solid #6EBF8B;
                border-radius: 4px;
            }
            QPushButton:hover {
                background-color: #E5F4EC;
                border-color: #5CAF7B;
            }
            QPushButton:disabled {
                background-color: #F5F5F5;
                color: #AAAAAA;
                border-color: #E5E5E5;
            }
        """)
        return btn

    # -------------------------------------------------------------------------
    # Public API
    # -------------------------------------------------------------------------

    def set_project_info(self, name: str, path: str):
        """Update project info display."""
        self.project_name_label.setText(name)
        self.project_info_label.setText(path)

    def enable_all_buttons(self, enabled: bool):
        """Enable/disable all project-specific buttons."""
        for btn in self.pipeline_buttons.values():
            btn.setEnabled(enabled)

        for btn in self.special_buttons:
            btn.setEnabled(enabled)

    def update_button_states(
        self,
        gpx_enabled: bool = False,
        gpx_done: bool = False,
        prepare_enabled: bool = False,
        prepare_done: bool = False,
        enrich_enabled: bool = False,
        enrich_done: bool = False,
        select_enabled: bool = False,
        select_done: bool = False,
        build_enabled: bool = False,
        build_done: bool = False
    ):
        """
        Update button states based on pipeline progress and dependencies.

        The convention is:
            - *_enabled controls whether the user can click the button
            - *_done toggles the visual "completed" state
        """
        self._update_button(self.btn_gpx, gpx_enabled, gpx_done)
        self._update_button(self.btn_prepare, prepare_enabled, prepare_done)
        self._update_button(self.btn_enrich, enrich_enabled, enrich_done)
        self._update_button(self.btn_select, select_enabled, select_done)
        self._update_button(self.btn_build, build_enabled, build_done)

    def set_button_in_progress(self, button_name: str):
        """Set button to in-progress state."""
        button = self.pipeline_buttons.get(button_name)
        if button:
            original_text = button.property("original_text")
            button.setText(f"⏳  {original_text}")
            button.setStyleSheet("""
                QPushButton {
                    background-color: #E3F2FD;
                    color: #1976D2;
                    font-size: 16px;
                    font-weight: 600;
                    border: 2px solid #2196F3;
                    border-radius: 8px;
                    text-align: left;
                    padding-left: 15px;
                }
            """)

    # -------------------------------------------------------------------------
    # Internal helpers
    # -------------------------------------------------------------------------

    def _update_button(self, button: QPushButton, enabled: bool, done: bool):
        """Update single button state."""
        button.setEnabled(enabled)
        original_text = button.property("original_text")
        if done:
            button.setText(f"✓  {original_text}")
            button.setStyleSheet(self._get_completed_style())
        else:
            button.setText(original_text)
            button.setStyleSheet(self._get_default_style())

    def _get_default_style(self) -> str:
        """Default button style."""
        return """
            QPushButton {
                background-color: #FFFFFF;
                color: #333333;
                font-size: 16px;
                font-weight: 600;
                border: 2px solid #DDDDDD;
                border-radius: 8px;
                text-align: left;
                padding-left: 15px;
            }
            QPushButton:hover {
                background-color: #F8F9FA;
                border-color: #007AFF;
            }
            QPushButton:disabled {
                background-color: #F5F5F5;
                color: #AAAAAA;
                border-color: #E5E5E5;
            }
        """

    def _get_completed_style(self) -> str:
        """Completed button style."""
        return """
            QPushButton {
                background-color: #F0F9F4;
                color: #2D7A4F;
                font-size: 16px;
                font-weight: 600;
                border: 2px solid #6EBF8B;
                border-radius: 8px;
                text-align: left;
                padding-left: 15px;
            }
            QPushButton:hover {
                background-color: #E5F4EC;
                border-color: #5CAF7B;
            }
            QPushButton:disabled {
                background-color: #F5F5F5;
                color: #AAAAAA;
                border-color: #DDDDDD;
            }
        """
