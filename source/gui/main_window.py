# source/gui/main_window.py
"""
Main application window - UI orchestration only.
Business logic delegated to controller modules.
"""

from datetime import datetime
from pathlib import Path

from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QListWidget, QListWidgetItem, QSplitter, QFileDialog, QMessageBox
)
from PySide6.QtCore import Qt

from ..config import DEFAULT_CONFIG as CFG
from .import_window import ImportRideWindow
from .preferences_window import PreferencesWindow
from .analysis_dialog import AnalysisDialog

# Import controllers
from .controllers import ProjectController, PipelineController, UIBuilder

from ..io_paths import enrich_path


class MainWindow(QMainWindow):
    """Main application window with clean separation of concerns."""
    
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Velo Highlights AI")
        self.resize(1200, 800)
        
        # Initialize controllers
        self.project_controller = ProjectController(log_callback=self.log)
        self.pipeline_controller = PipelineController(
            on_step_started=self.on_step_started,
            on_step_progress=self.on_step_progress,
            on_step_completed=self.on_step_completed,
            on_error=self.on_error
        )
        self.ui_builder = UIBuilder()
        
        # UI components (will be initialized in _setup_ui)
        self.progress_bar = None
        self.log_view = None
        self.project_list = None
        self.project_name_label = None
        self.project_info_label = None
        
        # Step buttons
        self.btn_prepare = None
        self.btn_analyze = None
        self.btn_select = None
        self.btn_finalize = None
        
        self._setup_ui()
        self._refresh_projects()
    
    def _setup_ui(self):
        """Set up the main UI layout."""
        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QHBoxLayout(central)
        
        # Create left and right panels
        left_panel = self._create_left_panel()
        right_panel = self._create_right_panel()
        
        # Add to splitter
        splitter = QSplitter(Qt.Horizontal)
        splitter.addWidget(left_panel)
        splitter.addWidget(right_panel)
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 2)
        main_layout.addWidget(splitter)
        
        # Status bar
        self.statusBar().showMessage("Ready")
    
    def _create_left_panel(self) -> QWidget:
        """Create left panel with project list and action buttons."""
        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(0, 0, 0, 0)
        
        # Header
        header = self.ui_builder.create_section_label("Ride Projects")
        layout.addWidget(header)
        
        # Project list
        self.project_list = QListWidget()
        self.project_list.itemClicked.connect(self._on_project_clicked)
        self.project_list.itemDoubleClicked.connect(self._on_project_double_clicked)
        layout.addWidget(self.project_list)
        
        # Action buttons
        action_panel = self._create_action_buttons()
        layout.addWidget(action_panel)
        
        return panel
    
    def _create_action_buttons(self) -> QWidget:
        """Create bottom action button panel."""
        panel = QWidget()
        layout = QHBoxLayout(panel)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(10)
        
        btn_import = self.ui_builder.create_action_button(
            "📹 Import Clips",
            "Import new ride footage from cameras"
        )
        btn_import.clicked.connect(self._open_import_clips)
        
        btn_create = self.ui_builder.create_action_button(
            "➕ Create New Project",
            "Create project from a folder with video files"
        )
        btn_create.clicked.connect(self._create_new_project)
        
        btn_analyze = self.ui_builder.create_action_button(
            "📊 Analyze Selection",
            "Analyze why clips were selected or rejected"
        )
        btn_analyze.clicked.connect(self._open_analysis)
        
        btn_prefs = self.ui_builder.create_action_button(
            "⚙️ Preferences",
            "Configure pipeline settings"
        )
        btn_prefs.clicked.connect(self._open_preferences)
        
        layout.addWidget(btn_import)
        layout.addWidget(btn_create)
        layout.addWidget(btn_analyze)
        layout.addWidget(btn_prefs)
        
        return panel
    
    def _create_right_panel(self) -> QWidget:
        """Create right panel with pipeline steps and log."""
        panel = QWidget()
        layout = QVBoxLayout(panel)
        
        # Project info
        self.project_name_label = QLabel("No project loaded")
        self.project_name_label.setStyleSheet("font-size: 18px; font-weight: bold;")
        layout.addWidget(self.project_name_label)
        
        self.project_info_label = self.ui_builder.create_info_label()
        layout.addWidget(self.project_info_label)
        
        # Pipeline steps
        steps_label = self.ui_builder.create_section_label("Pipeline Steps", 14)
        layout.addWidget(steps_label)
        
        # Step buttons
        self.btn_prepare = self.ui_builder.create_step_button(
            "1️⃣ Prepare Data",
            "Validate inputs, parse GPX, and align camera timestamps\nRuns: Preflight → Flatten → Align",
            lambda: self._run_step_group("prepare")
        )
        layout.addWidget(self.btn_prepare)
        
        self.btn_analyze = self.ui_builder.create_step_button(
            "2️⃣ Analyze Frames",
            "Extract frame metadata and detect bikes with AI\nRuns: Extract → Analyze",
            lambda: self._run_step_group("analyze")
        )
        layout.addWidget(self.btn_analyze)
        
        self.btn_select = self.ui_builder.create_step_button(
            "3️⃣ Select Clips",
            "AI recommends clips, then you review and finalize selection\nOpens manual review interface",
            self._run_select_with_review
        )
        layout.addWidget(self.btn_select)
        
        self.btn_finalize = self.ui_builder.create_step_button(
            "4️⃣ Build Final Video",
            "Render clips with overlays, create intro/outro, and assemble final video\nRuns: Build → Splash → Concat",
            lambda: self._run_step_group("finalize")
        )
        layout.addWidget(self.btn_finalize)
        
        layout.addStretch()
        
        # Progress bar
        self.progress_bar = self.ui_builder.create_progress_bar()
        layout.addWidget(self.progress_bar)
        
        # Log view
        log_label = self.ui_builder.create_section_label("Activity Log", 14)
        layout.addWidget(log_label)
        
        self.log_view = self.ui_builder.create_log_view()
        layout.addWidget(self.log_view)
        
        return panel
    
    # --- Project Management ---
    
    def _refresh_projects(self):
        """Refresh project list from disk."""
        self.project_list.clear()
        projects = self.project_controller.get_all_projects()
        
        for name, path in projects:
            item = QListWidgetItem(name)
            item.setData(Qt.UserRole, str(path))
            self.project_list.addItem(item)
        
        count = len(projects)
        self.log(f"Found {count} project(s)", "success")
        self.statusBar().showMessage(f"Loaded {count} projects")
    
    def _on_project_clicked(self, item):
        """Handle project selection from list."""
        project_path = Path(item.data(Qt.UserRole))
        
        # Select project via controller
        if self.project_controller.select_project(project_path):
            self.pipeline_controller.set_current_project(project_path)
            
            # Update UI
            self.project_name_label.setText(project_path.name)
            self.project_info_label.setText(str(project_path))
            
            # Update button states
            self._update_step_buttons()
    
    def _on_project_double_clicked(self, item):
        """Handle project double-click (same as single click for now)."""
        self._on_project_clicked(item)
    
    def _create_new_project(self):
        """Create a new project from source folder."""
        source_folder = QFileDialog.getExistingDirectory(
            self,
            "Select Source Folder with Video Files"
        )
        if not source_folder:
            return
        
        # Create project via controller
        project_path = self.project_controller.create_project(Path(source_folder))
        
        if project_path:
            # Add to list and select
            item = QListWidgetItem(project_path.name)
            item.setData(Qt.UserRole, str(project_path))
            self.project_list.addItem(item)
            self.project_list.setCurrentItem(item)
            self._on_project_clicked(item)
            
            self.statusBar().showMessage(f"Project created: {project_path.name}")
        else:
            self.statusBar().showMessage("Failed to create project")
    
    # --- Pipeline Execution ---
    
    def _run_step_group(self, group_name: str):
        """Run a pipeline step group."""
        if not self.project_controller.current_project:
            return
        
        try:
            if group_name == "prepare":
                self.pipeline_controller.run_prepare()
            elif group_name == "analyze":
                self.pipeline_controller.run_analyze()
            elif group_name == "finalize":
                self.pipeline_controller.run_finalize()
        except Exception as e:
            self.on_error(group_name, str(e))
    
    def _run_select_with_review(self):
        """Run select step with manual review dialog."""
        if not self.project_controller.current_project:
            return
        
        try:
            self.pipeline_controller.run_select()
        except Exception as e:
            self.on_error("select", str(e))
    
    def _update_step_buttons(self):
        """Update step button enabled/disabled state based on pipeline progress."""
        if not self.project_controller.current_project:
            self.btn_prepare.setEnabled(False)
            self.btn_analyze.setEnabled(False)
            self.btn_select.setEnabled(False)
            self.btn_finalize.setEnabled(False)
            return
        
        # Enable buttons based on completion status
        self.btn_prepare.setEnabled(True)
        self.btn_analyze.setEnabled(self.pipeline_controller.can_run_analyze())
        self.btn_select.setEnabled(self.pipeline_controller.can_run_select())
        self.btn_finalize.setEnabled(self.pipeline_controller.can_run_finalize())
    
    # --- Pipeline Callbacks ---
    
    def on_step_started(self, step_name: str):
        """Callback when pipeline step starts."""
        self.log(f"▶ Starting {step_name}...", "info")
        self.statusBar().showMessage(f"Running: {step_name}")
        self.progress_bar.setVisible(True)
        self.progress_bar.setValue(0)
    
    def on_step_progress(self, step_name: str, progress: int, status: str):
        """Callback for pipeline step progress updates."""
        self.progress_bar.setVisible(True)
        self.progress_bar.setValue(progress)
        self.statusBar().showMessage(f"{step_name}: {status}")
    
    def on_step_completed(self, step_name: str, result):
        """Callback when pipeline step completes."""
        self.log(f"✓ {step_name} completed", "success")
        self.statusBar().showMessage(f"Completed: {step_name}")
        self._update_step_buttons()
        current = self.progress_bar.value()
        self.progress_bar.setValue(min(current + 10, 100))
    
    def on_error(self, step_name: str, error_message: str):
        """Callback when pipeline step fails."""
        self.progress_bar.setVisible(False)
        self.statusBar().showMessage("Pipeline failed")
        self.log(f"✗ {step_name} failed: {error_message}", "error")
    
    # --- Dialogs ---
    
    def _open_import_clips(self):
        """Open import clips dialog."""
        dlg = ImportRideWindow(self)
        dlg.exec()
    
    def _open_preferences(self):
        """Open preferences dialog."""
        if not self.project_controller.current_project:
            QMessageBox.warning(
                self,
                "No Project Selected",
                "Please select or create a project before opening preferences."
            )
            return
        
        from ..utils.log import reconfigure_loggers
        
        prefs_dialog = PreferencesWindow(self)
        result = prefs_dialog.exec()
        
        if result == PreferencesWindow.Accepted:
            overrides = prefs_dialog.get_overrides()
            
            # Apply overrides to config
            changes_applied = []
            for key, value in overrides.items():
                if hasattr(CFG, key):
                    old_value = getattr(CFG, key)
                    setattr(CFG, key, value)
                    
                    if old_value != value:
                        changes_applied.append(f"{key}: {old_value} → {value}")
            
            if changes_applied:
                self.log("✓ Preferences updated:", "success")
                for change in changes_applied[:5]:
                    self.log(f"  • {change}", "info")
                if len(changes_applied) > 5:
                    self.log(f"  ... and {len(changes_applied) - 5} more changes", "info")
                
                if any("LOG_LEVEL" in change for change in changes_applied):
                    reconfigure_loggers()
                
                self.statusBar().showMessage(f"Applied {len(changes_applied)} preference changes")
            else:
                self.log("No changes made to preferences", "info")
        else:
            self.log("Preferences changes cancelled", "info")
    
    def _open_analysis(self):
        """Open selection analysis dialog."""
        if not self.project_controller.current_project:
            QMessageBox.warning(
                self,
                "No Project Selected",
                "Please select or create a project before analyzing selection."
            )
            return
        
        if not enrich_path().exists():
            QMessageBox.warning(
                self,
                "No Analysis Data",
                "Please run the 'Analyze Frames' step first.\n\n"
                "The analysis tool needs enriched.csv to identify bottlenecks."
            )
            return
        
        try:
            dialog = AnalysisDialog(self.project_controller.current_project, self)
            dialog.exec()
        except Exception as e:
            self.log(f"Failed to open analysis: {e}", "error")
            QMessageBox.critical(
                self,
                "Analysis Error",
                f"Failed to run analysis:\n\n{str(e)}"
            )
    
    # --- Logging ---
    
    def log(self, message: str, level: str = "info"):
        """Add colored log message to log view."""
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
    
    def closeEvent(self, event):
        """Handle window close event."""
        event.accept()