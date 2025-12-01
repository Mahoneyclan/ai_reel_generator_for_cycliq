# source/gui/main_window.py
"""
Main application window - UI orchestration only.
Business logic delegated to helper modules.
"""

from pathlib import Path
from PySide6.QtWidgets import QMainWindow, QWidget, QVBoxLayout, QSplitter
from PySide6.QtCore import Qt

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

from ..config import DEFAULT_CONFIG as CFG


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
        
        # Will be connected after UI setup
        self.log_panel = None
        
        # Initialize controllers
        self.project_controller = ProjectController(
            log_callback=self.status_manager.log
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
        """Set up the main UI layout."""
        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QVBoxLayout(central)
        
        # Create panels
        self.project_panel = ProjectListPanel()
        self.pipeline_panel = PipelinePanel()
        self.action_panel = ActionButtonPanel()
        self.log_panel = ActivityLogPanel()
        
        # Top section with splitter
        splitter = QSplitter(Qt.Horizontal)
        splitter.addWidget(self.project_panel)
        splitter.addWidget(self.pipeline_panel)
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 2)
        
        main_layout.addWidget(splitter)
        main_layout.addWidget(self.action_panel)
        main_layout.addWidget(self.log_panel)
        
        # Connect status manager to log panel
        self.status_manager.set_log_callback(self.log_panel.log)
        
        # Status bar
        self.status_manager.show_ready()
    
    def _connect_signals(self):
        """Connect all UI signals to handlers."""
        # Project panel
        self.project_panel.project_selected.connect(self._on_project_selected)
        
        # Pipeline panel
        self.pipeline_panel.prepare_clicked.connect(self._run_prepare)
        self.pipeline_panel.analyze_clicked.connect(self._run_analyze)
        self.pipeline_panel.select_clicked.connect(self._run_select)
        self.pipeline_panel.finalize_clicked.connect(self._run_finalize)
        
        # Action panel
        self.action_panel.import_clicked.connect(self.dialog_manager.show_import)
        self.action_panel.strava_clicked.connect(self._show_strava_placeholder)
        self.action_panel.create_clicked.connect(self._create_project)
        self.action_panel.analyze_clicked.connect(self.dialog_manager.show_analysis)
        self.action_panel.log_clicked.connect(self.dialog_manager.show_log)
        self.action_panel.music_clicked.connect(self._show_music_placeholder)
        self.action_panel.prefs_clicked.connect(self._show_preferences)
    
    def _refresh_projects(self):
        """Refresh project list from disk."""
        projects = self.project_controller.get_all_projects()
        self.project_panel.set_projects(projects)
        self.status_manager.log(f"Found {len(projects)} project(s)", "success")
    
    def _on_project_selected(self, project_path: Path):
        """Handle project selection."""
        if self.project_controller.select_project(project_path):
            self.pipeline_controller.set_current_project(project_path)
            self.pipeline_panel.set_project_info(
                name=project_path.name,
                path=str(project_path)
            )
            self._update_pipeline_buttons()
    
    def _create_project(self):
        """Create new project from source folder."""
        source_folder = self.dialog_manager.select_source_folder()
        if not source_folder:
            return
        
        project_path = self.project_controller.create_project(source_folder)
        if project_path:
            self._refresh_projects()
            self.project_panel.select_project(project_path)
    
    # --- Pipeline Execution ---
    
    def _run_prepare(self):
        """Run preparation pipeline."""
        try:
            self.pipeline_controller.run_prepare()
        except Exception as e:
            self._on_error("prepare", str(e))
    
    def _run_analyze(self):
        """Run analysis pipeline."""
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
    
    def _run_finalize(self):
        """Run finalization pipeline."""
        try:
            self.pipeline_controller.run_finalize()
        except Exception as e:
            self._on_error("finalize", str(e))
    
    # --- Pipeline Callbacks ---
    
    def _on_step_started(self, step_name: str):
        """Handle step start."""
        self.status_manager.show_running(step_name)
        self.log_panel.log(f"▶ Starting {step_name}...", "info")
    
    def _on_step_progress(self, step_name: str, current: int, total: int):
        """Handle step progress."""
        self.status_manager.show_progress(step_name, current, total)
    
    def _on_step_completed(self, step_name: str, result):
        """Handle step completion."""
        self.step_tracker.mark_completed(step_name)
        self.log_panel.log(f"✓ {step_name} completed", "success")
        self._update_pipeline_buttons()
        
        # Handle special completions
        if step_name == "concat":
            self._on_build_completed()
    
    def _on_error(self, step_name: str, error_message: str):
        """Handle step error."""
        self.status_manager.show_error(step_name)
        self.log_panel.log(f"✗ {step_name} failed: {error_message}", "error")
    
    def _on_build_completed(self):
        """Handle build completion with video offer."""
        if not self.project_controller.current_project:
            return
        
        final_video = self.project_controller.current_project / f"{self.project_controller.current_project.name}.mp4"
        if final_video.exists():
            self.dialog_manager.offer_open_video(final_video)
    
    # --- UI Updates ---
    
    def _update_pipeline_buttons(self):
        """Update pipeline button states and completion indicators."""
        if not self.project_controller.current_project:
            self.pipeline_panel.disable_all()
            return
        
        # Update button states
        prepare_done = self.pipeline_controller.can_run_analyze()
        analyze_done = self.pipeline_controller.can_run_select()
        select_done = self.pipeline_controller.can_run_finalize()
        
        self.pipeline_panel.update_button_states(
            prepare_enabled=True,
            prepare_done=prepare_done,
            analyze_enabled=prepare_done,
            analyze_done=analyze_done,
            select_enabled=analyze_done,
            select_done=select_done,
            finalize_enabled=select_done,
            finalize_done=self._check_finalize_done()
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
    
    def _show_strava_placeholder(self):
        """Show Strava placeholder message."""
        self.log_panel.log("Strava GPX import coming soon", "info")
    
    def _show_music_placeholder(self):
        """Show music management placeholder."""
        self.log_panel.log("Music management coming soon", "info")