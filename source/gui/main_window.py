# source/gui/main_window.py
"""
Main application window - UI orchestration only.
Business logic delegated to helper modules.

MUSIC NOTE: Music stored in PROJECT_ROOT/assets/music/
Intro/outro audio stored separately in assets/
"""

from pathlib import Path
from PySide6.QtWidgets import QMainWindow, QWidget, QVBoxLayout, QSplitter, QProgressBar
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QDesktopServices
from PySide6.QtCore import QUrl

from .gui_helpers import (
    ProjectListPanel,
    PipelinePanel,
    ActionButtonPanel,
    ActivityLogPanel,
    StatusManager,
    DialogManager,
    StepStatusTracker
)
from .controllers import ProjectController, PipelineController

# Progress bar styles (avoid duplication)
_PROGRESS_STYLE_NORMAL = """
    QProgressBar {
        border: 2px solid #DDDDDD;
        border-radius: 6px;
        text-align: center;
        height: 28px;
        background-color: #F5F5F5;
        font-size: 12px;
        font-weight: 600;
        color: #333333;
        margin: 0px 10px 10px 10px;
    }
    QProgressBar::chunk {
        background-color: qlineargradient(
            x1:0, y1:0, x2:1, y2:0,
            stop:0 #007AFF, stop:1 #00C7FF
        );
        border-radius: 4px;
    }
"""

_PROGRESS_STYLE_ERROR = """
    QProgressBar {
        border: 2px solid #FF3B30;
        border-radius: 6px;
        text-align: center;
        height: 28px;
        background-color: #FFF0F0;
        font-size: 12px;
        font-weight: 600;
        color: #FF3B30;
        margin: 0px 10px 10px 10px;
    }
    QProgressBar::chunk {
        background-color: #FF3B30;
        border-radius: 4px;
    }
"""
from .gpx_import_window import GPXImportWindow

from ..config import DEFAULT_CONFIG as CFG
from ..io_paths import flatten_path, extract_path, enrich_path, select_path
from ..utils.log import setup_logger
from ..utils.map_overlay import clear_map_caches
from ..utils.temp_files import cleanup_temp_files

log = setup_logger("gui.main_window")


class MainWindow(QMainWindow):
    """Main application window with clean separation of concerns."""

    def __init__(self):
        super().__init__()
        self.setWindowTitle("Velo Highlights AI")
        self.resize(1200, 800)

        # Initialize managers
        self.status_manager = StatusManager(self)
        self.dialog_manager = DialogManager(self)
        self.step_tracker = StepStatusTracker()

        # Progress tracking
        self.log_panel = None
        self.progress_bar = None
        self._progress_hide_timer = None

        # Initialize controllers
        self.project_controller = ProjectController(
            log_callback=self._log_to_panel
        )
        self.pipeline_controller = PipelineController(
            on_step_started=self._on_step_started,
            on_step_progress=self._on_step_progress,
            on_step_completed=self._on_step_completed,
            on_error=self._on_error
        )

        # Setup UI
        self._setup_ui()
        self._connect_signals()
        self._refresh_projects()

    def _setup_ui(self):
        """Set up the main UI layout with correct ordering."""
        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QVBoxLayout(central)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # 1. ACTION BAR AT TOP (project-independent actions)
        self.action_panel = ActionButtonPanel()
        main_layout.addWidget(self.action_panel)

        # 2. PROJECT/PIPELINE SPLITTER (main workspace)
        splitter = QSplitter(Qt.Horizontal)

        self.project_panel = ProjectListPanel()
        self.pipeline_panel = PipelinePanel()

        splitter.addWidget(self.project_panel)
        splitter.addWidget(self.pipeline_panel)
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 2)

        main_layout.addWidget(splitter)

        # 3. PROGRESS BAR (below workspace, above log)
        self.progress_bar = QProgressBar()
        self.progress_bar.setStyleSheet(_PROGRESS_STYLE_NORMAL)
        self.progress_bar.setMinimum(0)
        self.progress_bar.setMaximum(100)
        self.progress_bar.setValue(0)
        self.progress_bar.setVisible(False)
        main_layout.addWidget(self.progress_bar)

        # 4. ACTIVITY LOG AT BOTTOM
        self.log_panel = ActivityLogPanel()
        main_layout.addWidget(self.log_panel)

        # Connect status manager to log panel
        self.status_manager.set_log_callback(self.log_panel.log)

        # Status bar
        self.status_manager.show_ready()

    def _connect_signals(self):
        """Connect all UI signals to handlers."""
        # Project panel
        self.project_panel.project_selected.connect(self._on_project_selected)

        # Action panel (top bar - project-independent)
        self.action_panel.import_clicked.connect(self._show_import_raw_video)
        self.action_panel.create_clicked.connect(self._create_project)
        self.action_panel.music_clicked.connect(self._open_music_folder)
        self.action_panel.prefs_clicked.connect(self._show_preferences)
        self.action_panel.general_clicked.connect(self._show_general_settings)

        # Pipeline panel (project-specific workflow)
        self.pipeline_panel.gpx_clicked.connect(self._show_gpx_import)
        self.pipeline_panel.prepare_clicked.connect(self._run_prepare)
        self.pipeline_panel.analyze_clicked.connect(self._run_analyze)
        self.pipeline_panel.select_clicked.connect(self._run_select)
        self.pipeline_panel.build_clicked.connect(self._run_build)

        # Special project tools
        self.pipeline_panel.analyze_selection_clicked.connect(self.dialog_manager.show_analysis)
        self.pipeline_panel.view_log_clicked.connect(self.dialog_manager.show_log)

    def _log_to_panel(self, message: str, level: str = "info"):
        """Route project controller logs to activity panel."""
        if self.log_panel:
            self.log_panel.log(message, level)

    def _refresh_projects(self):
        """Refresh project list from disk."""
        projects = self.project_controller.get_all_projects()
        self.project_panel.set_projects(projects)
        self.log_panel.log(f"Found {len(projects)} project(s)", "success")

    def _on_project_selected(self, project_path: Path):
        """Handle project selection."""
        if self.project_controller.select_project(project_path):
            self.pipeline_controller.set_current_project(project_path)
            self.pipeline_panel.set_project_info(
                name=project_path.name,
                path=str(project_path)
            )
            self._update_pipeline_buttons()
            self.log_panel.log(f"Selected project: {project_path.name}", "success")

            # Clear caches when switching projects
            clear_map_caches()

    def _create_project(self):
        """Create new project from source folder."""
        source_folder = self.dialog_manager.select_source_folder()
        if not source_folder:
            return

        project_path = self.project_controller.create_project(source_folder)
        if project_path:
            self._refresh_projects()
            self.project_panel.select_project(project_path)

    def closeEvent(self, event):
        """Handle application close - cleanup resources."""
        try:
            # Cleanup temporary files
            cleanup_temp_files(force=True)

            # Clear caches
            clear_map_caches()

            log.info("Application closed cleanly")
        except Exception as e:
            log.warning(f"Cleanup warning on close: {e}")

        event.accept()

    # --- Pipeline Execution ---

    def _run_prepare(self):
        """Run preparation pipeline (align and extract)."""
        try:
            self.pipeline_controller.run_prepare()
        except Exception as e:
            self._on_error("prepare", str(e))

    def _run_analyze(self):
        """Run analysis pipeline (enrichment and scoring)."""
        try:
            self.pipeline_controller.run_analyze()
        except Exception as e:
            self._on_error("analyze", str(e))

    def _run_select(self):
        """Run selection with manual review."""
        try:
            self.pipeline_controller.run_select()
        except Exception as e:
            self._on_error("select", str(e))

    def _run_build(self):
        """Run finalization pipeline."""
        try:
            self.pipeline_controller.run_build()
        except Exception as e:
            self._on_error("build", str(e))

    # --- Pipeline Callbacks ---

    def _on_step_started(self, step_name: str):
        """Handle step start."""
        self.status_manager.show_running(step_name)
        self.log_panel.log(f"▶ Starting {step_name}...", "info")

        # Cancel any pending hide timer
        if self._progress_hide_timer:
            self._progress_hide_timer.stop()
            self._progress_hide_timer = None

        # Show and reset progress bar
        self.progress_bar.setValue(0)
        self.progress_bar.setFormat(f"{step_name}: Starting...")
        self.progress_bar.setVisible(True)

        # Update button to show in-progress state
        self._update_button_in_progress(step_name)

    def _on_step_progress(self, step_name: str, current: int, total: int, message: str):
        """Handle step progress updates. Status bar stays at 'Running: XXX'."""
        # Update progress bar only (status bar keeps "Running: XXX" from _on_step_started)
        if total > 0:
            pct = int((current / total) * 100)
            self.progress_bar.setValue(pct)
            self.progress_bar.setFormat(f"{step_name}: {message}")

    def _on_step_completed(self, step_name: str, result):
        """Handle step completion."""
        self.step_tracker.mark_completed(step_name)
        self.log_panel.log(f"✓ {step_name} completed", "success")

        # Update progress bar to show completion
        self.progress_bar.setValue(100)
        self.progress_bar.setFormat(f"{step_name}: Complete ✓")

        # Hide progress bar after 1.5 seconds
        self._progress_hide_timer = QTimer()
        self._progress_hide_timer.setSingleShot(True)
        self._progress_hide_timer.timeout.connect(lambda: self.progress_bar.setVisible(False))
        self._progress_hide_timer.start(1500)

        # Update UI
        self._update_pipeline_buttons()
        self.status_manager.show_ready()

        # Handle special completions
        if step_name == "concat":
            self._on_build_completed()

    def _on_error(self, step_name: str, error_message: str):
        """Handle step error."""
        self.status_manager.show_error(step_name)
        self.log_panel.log(f"✗ {step_name} failed: {error_message}", "error")

        # Update progress bar to show error
        self.progress_bar.setStyleSheet(_PROGRESS_STYLE_ERROR)
        self.progress_bar.setFormat(f"{step_name}: Failed ✗")

        # Hide after 3 seconds and restore style
        self._progress_hide_timer = QTimer()
        self._progress_hide_timer.setSingleShot(True)
        self._progress_hide_timer.timeout.connect(self._restore_progress_bar_style)
        self._progress_hide_timer.start(3000)

    def _restore_progress_bar_style(self):
        """Restore normal progress bar style and hide."""
        self.progress_bar.setStyleSheet(_PROGRESS_STYLE_NORMAL)
        self.progress_bar.setVisible(False)

    def _on_build_completed(self):
        """Handle build completion with video offer."""
        if not self.project_controller.current_project:
            return

        final_video = self.project_controller.current_project / f"{self.project_controller.current_project.name}.mp4"
        if final_video.exists():
            self.dialog_manager.offer_open_video(final_video)

    # --- UI Updates ---

    def _update_button_in_progress(self, step_name: str):
        """Update button to show in-progress state."""
        step_button_map = {
            "flatten": self.pipeline_panel.btn_gpx,
            "align": self.pipeline_panel.btn_prepare,
            "extract": self.pipeline_panel.btn_prepare,
            "analyze": self.pipeline_panel.btn_analyze,
            "select": self.pipeline_panel.btn_select,
            "build": self.pipeline_panel.btn_build,
            "splash": self.pipeline_panel.btn_build,
            "concat": self.pipeline_panel.btn_build,
        }

        button = step_button_map.get(step_name)
        if button:
            original_text = button.property("original_text")
            button.setText(f"⟳  {original_text}")
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

    def _update_pipeline_buttons(self):
        """
        Update pipeline button states and completion indicators
        based on the presence of key artifacts.

        Mapping:
            Get GPX & Flatten → flatten.csv
            Align & Extract    → extract.csv
            Analyze            → enriched.csv
            Select             → select.csv
            Build              → final reel
        """
        if not self.project_controller.current_project:
            self.pipeline_panel.enable_all_buttons(False)
            return

        # Artifact existence
        gpx_done = flatten_path().exists()
        prepare_done = extract_path().exists()
        analyze_done = enrich_path().exists()
        select_done = select_path().exists()
        build_done = self._check_finalize_done()

        # Enablement follows dependency chain:
        # - Align & Extract requires flatten.csv
        # - Analyze requires extract.csv
        # - Select requires enriched.csv
        # - Build requires select.csv
        self.pipeline_panel.update_button_states(
            gpx_enabled=True,
            gpx_done=gpx_done,

            prepare_enabled=gpx_done,
            prepare_done=prepare_done,

            analyze_enabled=prepare_done,
            analyze_done=analyze_done,

            select_enabled=analyze_done,
            select_done=select_done,

            build_enabled=select_done,
            build_done=build_done
        )

    def _check_finalize_done(self) -> bool:
        """Check if finalize step is complete."""
        if not self.project_controller.current_project:
            return False
        final_video = self.project_controller.current_project / f"{self.project_controller.current_project.name}.mp4"
        return final_video.exists()

    # --- Dialogs ---

    def _show_preferences(self):
        """Show preferences dialog."""
        if not self.project_controller.current_project:
            self.dialog_manager.show_no_project_warning()
            return

        self.dialog_manager.show_preferences()

    def _show_general_settings(self):
        """Show general settings dialog (no project required)."""
        # General settings are program-wide and should be accessible without a project
        self.dialog_manager.show_general_settings()

    def _show_import_raw_video(self):
        """Show raw video import dialog from cameras."""
        from .import_window import ImportRideWindow

        dialog = ImportRideWindow(self)
        result = dialog.exec()

        if result == ImportRideWindow.Accepted:
            self.log_panel.log("✓ Video import completed", "success")
            self._refresh_projects()

    def _show_gpx_import(self):
        """Show GPX import (Get GPX & Flatten)."""
        if not self.project_controller.current_project:
            self.dialog_manager.show_no_project_warning()
            return
        try:
            dialog = GPXImportWindow(parent=self)
            dialog.importCompleted.connect(
                lambda p: self.log_panel.log(f"GPX import complete: {p}", "success")
            )
            dialog.statusChanged.connect(
                lambda s: self.log_panel.log(s, "info")
            )
            dialog.exec()

            # After import, flatten step should have run; re-evaluate buttons
            self._update_pipeline_buttons()
        except Exception as e:
            from PySide6.QtWidgets import QMessageBox
            QMessageBox.critical(self, "GPS Import Error", f"Failed to open GPS import:\n\n{str(e)}")

    def _open_music_folder(self):
        """
        Open the music folder (assets/music) in the system file browser.
        Creates the folder if it doesn't exist.
        
        Music for middle segments: PROJECT_ROOT/assets/music/
        Intro/outro audio: stored separately in assets/
        """
        try:
            # Music directory: PROJECT_ROOT/assets/music/
            music_dir = CFG.PROJECT_ROOT / "assets" / "music"
            
            # Create directory if it doesn't exist
            music_dir.mkdir(parents=True, exist_ok=True)
            
            # Open in system file browser
            url = QUrl.fromLocalFile(str(music_dir))
            if QDesktopServices.openUrl(url):
                self.log_panel.log(f"Opened music folder: {music_dir}", "success")
                self.log_panel.log("💡 Add full-length music files here (MP3, WAV, M4A, etc.)", "info")
                self.log_panel.log("   Music plays continuously across all middle segments", "info")
            else:
                # Fallback: show path in log
                self.log_panel.log(f"Music folder: {music_dir}", "info")
                self.log_panel.log("💡 Add full-length music files to this directory", "info")
                
        except Exception as e:
            log.error(f"Failed to open music folder: {e}")
            self.log_panel.log(f"Error opening music folder: {e}", "error")
            # Still show the path even if we can't open it
            music_dir = CFG.PROJECT_ROOT / "assets" / "music"
            self.log_panel.log(f"Music folder location: {music_dir}", "info")