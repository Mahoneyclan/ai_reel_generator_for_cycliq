# source/gui/main_window.py
# Updated to properly wire preferences window

from datetime import datetime
from pathlib import Path

from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QListWidget, QListWidgetItem, QSplitter, QTextEdit, QProgressBar,
    QFileDialog, QMessageBox
)
from PySide6.QtCore import Qt

from source.config import DEFAULT_CONFIG as CFG
from source.core.pipeline_executor import PipelineExecutor
from source.gui.import_window import ImportRideWindow
from source.gui.preferences_window import PreferencesWindow  # Import PreferencesWindow
from source.utils.log import reconfigure_loggers
from source.gui.analysis_dialog import AnalysisDialog


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Velo Highlights AI")
        self.resize(1200, 800)

        self.current_project = None
        self.progress_bar = None
        self.log_view = None
        self.completed_steps = set()

        # Executor handles pipeline orchestration
        self.executor = PipelineExecutor(
            on_step_started=self.on_step_started,
            on_step_progress=self.on_step_progress,
            on_step_completed=self.on_step_completed,
            on_error=self.on_error
        )

        self._setup_ui()
        self.refresh_projects()

    def _setup_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QHBoxLayout(central)

        # Left panel: project list
        left_panel = QWidget()
        left_layout = QVBoxLayout(left_panel)
        left_layout.setContentsMargins(0, 0, 0, 0)

        left_label = QLabel("Ride Projects")
        left_label.setStyleSheet("font-size: 16px; font-weight: bold; padding: 10px;")
        left_layout.addWidget(left_label)

        self.project_list = QListWidget()
        self.project_list.itemClicked.connect(self.on_project_selected)
        self.project_list.itemDoubleClicked.connect(self.load_selected_project)
        left_layout.addWidget(self.project_list)

        # Bottom action buttons
        action_panel = QWidget()
        action_layout = QHBoxLayout(action_panel)
        action_layout.setContentsMargins(10, 10, 10, 10)
        action_layout.setSpacing(10)

        self.btn_create_project = QPushButton("➕ Create New Project")
        self.btn_create_project.clicked.connect(self.new_project)

        self.btn_import_clips = QPushButton("📹 Import Clips")
        self.btn_import_clips.clicked.connect(self.open_import_clips)

        self.btn_analyze_selection = QPushButton("📊 Analyze Selection")
        self.btn_analyze_selection.clicked.connect(self.open_analysis)
        self.btn_analyze_selection.setToolTip(
            "Analyze why clips were selected or rejected\n"
            "Shows detection scores, bottlenecks, and recommendations"
        )

        self.btn_preferences = QPushButton("⚙️ Preferences")
        self.btn_preferences.clicked.connect(self.open_preferences)

        action_layout.addWidget(self.btn_import_clips)
        action_layout.addWidget(self.btn_create_project)
        action_layout.addWidget(self.btn_analyze_selection)
        action_layout.addWidget(self.btn_preferences)
        left_layout.addWidget(action_panel)
        # Right panel: pipeline steps
        right_panel = QWidget()
        right_layout = QVBoxLayout(right_panel)

        self.project_name_label = QLabel("No project loaded")
        self.project_name_label.setStyleSheet("font-size: 18px; font-weight: bold;")
        right_layout.addWidget(self.project_name_label)

        self.project_info_label = QLabel("")
        right_layout.addWidget(self.project_info_label)

        steps_label = QLabel("Pipeline Steps")
        steps_label.setStyleSheet("font-size: 14px; font-weight: bold; margin-top: 10px;")
        right_layout.addWidget(steps_label)

        # Step buttons
        self.btn_prepare = self._create_step_button(
            "1️⃣ Prepare Data",
            "Validate inputs, parse GPX, and align camera timestamps\nRuns: Preflight → Flatten → Align",
            lambda: self.run_step_group("prepare")
        )
        right_layout.addWidget(self.btn_prepare)

        self.btn_analyze = self._create_step_button(
            "2️⃣ Analyze Frames",
            "Extract frame metadata and detect bikes with AI\nRuns: Extract → Analyze",
            lambda: self.run_step_group("analyze")
        )
        right_layout.addWidget(self.btn_analyze)

        self.btn_select = self._create_step_button(
            "3️⃣ Select Clips",
            "AI recommends clips, then you review and finalize selection\nOpens manual review interface",
            self.run_select_with_review
        )
        right_layout.addWidget(self.btn_select)

        self.btn_finalize = self._create_step_button(
            "4️⃣ Build Final Video",
            "Render clips with overlays, create intro/outro, and assemble final video\nRuns: Build → Splash → Concat",
            lambda: self.run_step_group("finalize")
        )
        right_layout.addWidget(self.btn_finalize)

        right_layout.addStretch()

        # Progress bar
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        right_layout.addWidget(self.progress_bar)

        # Activity log
        log_label = QLabel("Activity Log")
        log_label.setStyleSheet("font-size: 14px; font-weight: bold; margin-top: 10px;")
        right_layout.addWidget(log_label)

        self.log_view = QTextEdit()
        self.log_view.setReadOnly(True)
        right_layout.addWidget(self.log_view)

        # Splitter
        splitter = QSplitter(Qt.Horizontal)
        splitter.addWidget(left_panel)
        splitter.addWidget(right_panel)
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 2)
        main_layout.addWidget(splitter)

        # Status bar
        self.statusBar().showMessage("Ready")

        self._update_step_buttons()

    def _create_step_button(self, text, tooltip, callback):
        btn = QPushButton(text)
        btn.clicked.connect(callback)
        btn.setMinimumHeight(60)
        btn.setToolTip(tooltip)
        btn.setStyleSheet("""
            QPushButton {
                background-color: #007AFF;
                color: white;
                font-size: 16px;
                font-weight: bold;
                border-radius: 8px;
                text-align: left;
                padding-left: 20px;
            }
            QPushButton:hover {
                background-color: #0051D5;
            }
            QPushButton:disabled {
                background-color: #CCCCCC;
                color: #888888;
            }
        """)
        return btn

    def refresh_projects(self):
        self.project_list.clear()
        projects_root = CFG.PROJECTS_ROOT
        if not projects_root.exists():
            self.log("Projects folder not found", "error")
            return

        for folder in projects_root.iterdir():
            if folder.is_dir():
                item = QListWidgetItem(folder.name)
                item.setData(Qt.UserRole, str(folder))
                self.project_list.addItem(item)

        count = self.project_list.count()
        self.log(f"Found {count} project(s)", "success")
        self.statusBar().showMessage(f"Loaded {count} projects")

    def on_project_selected(self, item):
        project_path = Path(item.data(Qt.UserRole))
        self.project_name_label.setText(project_path.name)
        self.project_info_label.setText(str(project_path))
        self.current_project = project_path

        CFG.RIDE_FOLDER = project_path.name

        symlink_path = project_path / "source_videos"
        if symlink_path.exists() and symlink_path.is_symlink():
            CFG.INPUT_BASE_DIR = project_path
            CFG.SOURCE_FOLDER = "source_videos"
            actual_target = symlink_path.resolve()
            self.log(f"Using project-local symlink: {symlink_path} → {actual_target}", "info")
        elif (project_path / "source_path.txt").exists():
            source_meta = project_path / "source_path.txt"
            source_path = Path(source_meta.read_text().strip())
            CFG.INPUT_BASE_DIR = source_path.parent
            CFG.SOURCE_FOLDER = source_path.name
            self.log(f"Using imported source: {source_path}", "info")
        else:
            CFG.SOURCE_FOLDER = project_path.name
            self.log("Using project folder as source", "info")

        reconfigure_loggers()
        self._update_step_buttons()

    def load_selected_project(self, item):
        self.on_project_selected(item)

    def new_project(self):
        source_folder = QFileDialog.getExistingDirectory(
            self,
            "Select Source Folder with Video Files"
        )
        if not source_folder:
            return

        source_path = Path(source_folder)
        video_extensions = {'.mp4', '.mov', '.avi', '.mkv', '.m4v'}
        video_files = [
            f for f in source_path.iterdir()
            if f.is_file() and f.suffix.lower() in video_extensions
        ]

        if not video_files:
            self.log("Error: No video files found in source folder", "error")
            return

        gpx_files = list(source_path.glob("*.gpx"))
        if not gpx_files:
            self.log("Warning: No GPX file found in source folder", "warning")

        project_name = source_path.name
        project_folder = CFG.PROJECTS_ROOT / project_name

        try:
            # Create project structure
            project_folder.mkdir(parents=True, exist_ok=True)
            for sub in ["logs", "working", "clips", "frames",
                        "splash_assets", "minimaps", "gauges"]:
                (project_folder / sub).mkdir(exist_ok=True)

            # Create symlink to source videos
            video_link = project_folder / "source_videos"
            if not video_link.exists():
                video_link.symlink_to(source_path)
                self.log(f"Created symlink to source videos: {video_link}", "success")

            # Add metadata file linking to source
            metadata_file = project_folder / "source_path.txt"
            metadata_file.write_text(str(source_path))

            self.log(f"Created project: {project_folder}", "success")
            self.log(f"Linked {len(video_files)} video file(s) from source", "info")

            # Add to project list
            item = QListWidgetItem(project_name)
            item.setData(Qt.UserRole, str(project_folder))
            self.project_list.addItem(item)

            # Select it as the current project
            self.project_list.setCurrentItem(item)
            self.on_project_selected(item)

            self.log(f"Project created: {project_name}", "success")
            self.statusBar().showMessage(f"Project created: {project_name}")

        except Exception as e:
            self.log(f"Error creating project: {str(e)}", "error")
            self.statusBar().showMessage("Failed to create project")

    def open_import_clips(self):
        """Open the ImportRideWindow dialog for importing new ride footage."""
        dlg = ImportRideWindow(self)
        dlg.exec()

    def open_preferences(self):
        """Open preferences window and apply changes if saved."""
        if not self.current_project:
            QMessageBox.warning(
                self,
                "No Project Selected",
                "Please select or create a project before opening preferences."
            )
            return

        # Create preferences dialog
        prefs_dialog = PreferencesWindow(self)
        
        # Show dialog and wait for user action
        result = prefs_dialog.exec()
        
        # If user clicked Save (accepted)
        if result == PreferencesWindow.Accepted:
            overrides = prefs_dialog.get_overrides()
            
            # Apply overrides to config
            changes_applied = []
            for key, value in overrides.items():
                if hasattr(CFG, key):
                    old_value = getattr(CFG, key)
                    setattr(CFG, key, value)
                    
                    # Log significant changes
                    if old_value != value:
                        changes_applied.append(f"{key}: {old_value} → {value}")
            
            if changes_applied:
                self.log("✓ Preferences updated:", "success")
                for change in changes_applied[:5]:  # Show first 5 changes
                    self.log(f"  • {change}", "info")
                if len(changes_applied) > 5:
                    self.log(f"  ... and {len(changes_applied) - 5} more changes", "info")
                
                # Reconfigure loggers if log level changed
                if any("LOG_LEVEL" in change for change in changes_applied):
                    reconfigure_loggers()
                
                self.statusBar().showMessage(f"Applied {len(changes_applied)} preference changes")
            else:
                self.log("No changes made to preferences", "info")
                self.statusBar().showMessage("Preferences unchanged")
        else:
            # User clicked Cancel
            self.log("Preferences changes cancelled", "info")
            self.statusBar().showMessage("Preferences not changed")

    def open_analysis(self):
        """Open selection analysis dialog."""
        if not self.current_project:
            QMessageBox.warning(
                self,
                "No Project Selected",
                "Please select or create a project before analyzing selection."
            )
            return
        
        # Check if analyze step has been run
        from source.io_paths import enrich_path
        if not enrich_path().exists():
            QMessageBox.warning(
                self,
                "No Analysis Data",
                "Please run the 'Analyze Frames' step first.\n\n"
                "The analysis tool needs enriched.csv to identify bottlenecks."
            )
            return
        
        # Open analysis dialog
        try:
            dialog = AnalysisDialog(self.current_project, self)
            dialog.exec()
        except Exception as e:
            self.log(f"Failed to open analysis: {e}", "error")
            QMessageBox.critical(
                self,
                "Analysis Error",
                f"Failed to run analysis:\n\n{str(e)}"
            )

    def run_step_group(self, group_name: str):
        """Run a pipeline action via executor."""
        if not self.current_project:
            return
        try:
            if group_name == "prepare":
                self.executor.prepare()
            elif group_name == "analyze":
                self.executor.analyze()
            elif group_name == "finalize":
                self.executor.build()
        except Exception as e:
            self.on_error(group_name, str(e))

    def run_select_with_review(self):
        """Run select step (AI + manual review)."""
        if not self.current_project:
            return
        try:
            self.executor.select(self.current_project)
        except Exception as e:
            self.on_error("select", str(e))

    # --- Progressive feedback handlers ---
    def on_step_started(self, step_name: str):
        self.log(f"▶ Starting {step_name}...", "info")
        self.statusBar().showMessage(f"Running: {step_name}")
        self.progress_bar.setVisible(True)
        self.progress_bar.setValue(0)

    def on_step_progress(self, step_name: str, progress: int, status: str):
        self.progress_bar.setVisible(True)
        self.progress_bar.setValue(progress)
        self.statusBar().showMessage(f"{step_name}: {status}")

    def on_step_completed(self, step_name: str, result):
        self.log(f"✓ {step_name} completed", "success")
        self.statusBar().showMessage(f"Completed: {step_name}")
        self.completed_steps.add(step_name)
        self._update_step_buttons()
        current = self.progress_bar.value()
        self.progress_bar.setValue(min(current + 10, 100))

    def on_error(self, step_name: str, error_message: str):
        self.progress_bar.setVisible(False)
        self.statusBar().showMessage("Pipeline failed")
        self.log(f"✗ {step_name} failed: {error_message}", "error")

    def _update_step_buttons(self):
        if not self.current_project:
            self.btn_prepare.setEnabled(False)
            self.btn_analyze.setEnabled(False)
            self.btn_select.setEnabled(False)
            self.btn_finalize.setEnabled(False)
            return

        from source.io_paths import camera_offsets_path, enrich_path, select_path
        prepare_done = camera_offsets_path().exists()
        self.btn_analyze.setEnabled(prepare_done)

        analyze_done = enrich_path().exists()
        self.btn_select.setEnabled(analyze_done)

        select_done = select_path().exists()
        self.btn_finalize.setEnabled(select_done)

        self.btn_prepare.setEnabled(True)

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

    def closeEvent(self, event):
        event.accept()