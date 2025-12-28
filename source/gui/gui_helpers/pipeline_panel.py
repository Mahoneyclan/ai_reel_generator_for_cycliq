# source/gui/gui_helpers/pipeline_panel.py
"""
Pipeline steps panel with project-specific workflow.
MIGRATED from pipeline_panel.py + project-specific buttons from action_button_panel.py

Pipeline workflow: Get GPX → Prepare → Analyze → Select → Build
Special tools: Analyze Selection, View Log

Signal naming clarification:
- analyze_clicked = Run the Analyze pipeline step
- analyze_selection_clicked = Open selection analysis tool (was "analyze" in old action_button_panel)
"""

from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QFrame
from PySide6.QtCore import Signal


class PipelinePanel(QWidget):
    """
    Panel displaying pipeline steps and project info.
    All features require a project to be selected.
    """

    # Pipeline step signals (from old pipeline_panel.py)
    gpx_clicked = Signal()          # NEW: Moved from action_button_panel
    prepare_clicked = Signal()
    analyze_clicked = Signal()      # Runs analyze step (NOT selection analysis)
    select_clicked = Signal()
    build_clicked = Signal()        # Renamed from finalize_clicked
    
    # Special tool signals (from old action_button_panel.py)
    analyze_selection_clicked = Signal()  # Renamed from analyze_clicked in action_button_panel
    view_log_clicked = Signal()           # Renamed from log_clicked in action_button_panel

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

        # Pipeline step buttons
        # NEW: Get GPX as first step (moved from action_button_panel)
        self.btn_gpx = self._create_button(
            "Get GPX", 
            "Import GPS data from Strava or Garmin Connect",
            self.gpx_clicked
        )
        layout.addWidget(self.btn_gpx)

        self.btn_prepare = self._create_button(
            "Prepare & Extract",
            "Validate inputs, align camera timestamps, and extract frame metadata",
            self.prepare_clicked
        )
        layout.addWidget(self.btn_prepare)

        self.btn_analyze = self._create_button(
            "Analyze",
            "Detect bikes with AI and score clips",
            self.analyze_clicked
        )
        layout.addWidget(self.btn_analyze)

        self.btn_select = self._create_button(
            "Select", 
            "AI recommends clips, then you review and finalize selection",
            self.select_clicked
        )
        layout.addWidget(self.btn_select)

        # Renamed from "Finalize" to "Build" for clarity
        self.btn_build = self._create_button(
            "Build", 
            "Render clips with overlays, create intro/outro, and assemble final video",
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

        # Renamed from "analyze_clicked" to "analyze_selection_clicked" to avoid conflict
        self.analyze_selection_btn = self._create_special_button(
            "📊 Analyze Selection",
            "Analyze selection pipeline and identify bottlenecks"
        )
        self.analyze_selection_btn.clicked.connect(self.analyze_selection_clicked.emit)
        special_layout.addWidget(self.analyze_selection_btn)

        # Renamed from "log_clicked" to "view_log_clicked" for clarity
        self.view_log_btn = self._create_special_button(
            "📄 View Log",
            "View detailed log files for this project"
        )
        self.view_log_btn.clicked.connect(self.view_log_clicked.emit)
        special_layout.addWidget(self.view_log_btn)

        layout.addLayout(special_layout)

        layout.addStretch()

        # Store button references for state management
        self.pipeline_buttons = {
            "gpx": self.btn_gpx,
            "prepare": self.btn_prepare,
            "analyze": self.btn_analyze,
            "select": self.btn_select,
            "build": self.btn_build
        }
        
        self.special_buttons = [self.analyze_selection_btn, self.view_log_btn]

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
        analyze_enabled: bool = False,
        analyze_done: bool = False,
        select_enabled: bool = False,
        select_done: bool = False,
        build_enabled: bool = False,
        build_done: bool = False
    ):
        """Update button states based on pipeline progress."""
        self._update_button(self.btn_gpx, gpx_enabled, gpx_done)
        self._update_button(self.btn_prepare, prepare_enabled, prepare_done)
        self._update_button(self.btn_analyze, analyze_enabled, analyze_done)
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