# source/gui/gui_helpers/dialog_manager.py
"""
Dialog management helper.
Centralizes all dialog creation and display logic.
"""

from pathlib import Path
from PySide6.QtWidgets import QFileDialog, QMessageBox


class DialogManager:
    """Manages all dialogs for main window."""
    
    def __init__(self, parent):
        """
        Args:
            parent: Parent widget (main window)
        """
        self.parent = parent
    
    def select_source_folder(self) -> Path | None:
        """
        Show folder selection dialog.
        
        Returns:
            Selected folder path or None
        """
        folder = QFileDialog.getExistingDirectory(
            self.parent,
            "Select Source Folder with Video Files"
        )
        return Path(folder) if folder else None
    
    def show_import(self):
        """Show GPX import dialog."""
        from ..gpx_import_window import GPXImportWindow
        dialog = GPXImportWindow(parent=self.parent)
        dialog.exec()
    
    def show_analysis(self):
        """Show selection analysis dialog."""
        from ..analysis_dialog import AnalysisDialog
        from ...io_paths import enrich_path
        
        # Validate prerequisites
        if not hasattr(self.parent, 'project_controller') or not self.parent.project_controller.current_project:
            self.show_no_project_warning()
            return
        
        if not enrich_path().exists():
            QMessageBox.warning(
                self.parent,
                "No Analysis Data",
                "Please run the 'Enrich' step first.\n\n"
                "The analysis tool needs enriched.csv to identify bottlenecks."
            )
            return
        
        try:
            dialog = AnalysisDialog(self.parent.project_controller.current_project, self.parent)
            dialog.exec()
        except Exception as e:
            QMessageBox.critical(
                self.parent,
                "Analysis Error",
                f"Failed to run analysis:\n\n{str(e)}"
            )
    
    def show_log(self):
        """Show log viewer window."""
        from ..view_log_window import ViewLogWindow
        
        if not hasattr(self.parent, 'project_controller') or not self.parent.project_controller.current_project:
            self.show_no_project_warning()
            return
        
        try:
            dialog = ViewLogWindow(self.parent.project_controller.current_project, self.parent)
            dialog.exec()
        except Exception as e:
            QMessageBox.critical(
                self.parent,
                "Log Viewer Error",
                f"Failed to open log viewer:\n\n{str(e)}"
            )
    
    def show_preferences(self):
        """Show preferences dialog."""
        from ..preferences_window import PreferencesWindow
        from ...utils.log import reconfigure_loggers
        from ...config import DEFAULT_CONFIG as CFG
        
        dialog = PreferencesWindow(self.parent)
        result = dialog.exec()
        
        if result == PreferencesWindow.Accepted:
            overrides = dialog.get_overrides()
            
            # Apply overrides to config
            changes_applied = []
            for key, value in overrides.items():
                if hasattr(CFG, key):
                    old_value = getattr(CFG, key)
                    setattr(CFG, key, value)
                    
                    if old_value != value:
                        changes_applied.append(f"{key}: {old_value} → {value}")
            
            if changes_applied:
                if hasattr(self.parent, 'log_panel'):
                    self.parent.log_panel.log("✓ Preferences updated:", "success")
                    for change in changes_applied[:5]:
                        self.parent.log_panel.log(f"  • {change}", "info")
                    if len(changes_applied) > 5:
                        self.parent.log_panel.log(f"  ... and {len(changes_applied) - 5} more changes", "info")
                
                if any("LOG_LEVEL" in change for change in changes_applied):
                    reconfigure_loggers()
                
                self.parent.statusBar().showMessage(f"Applied {len(changes_applied)} preference changes")

    def show_general_settings(self):
        """Show standalone General Settings dialog and apply changes."""
        from ..general_settings_window import GeneralSettingsWindow
        from ...utils.log import reconfigure_loggers
        from ...config import DEFAULT_CONFIG as CFG

        dialog = GeneralSettingsWindow(self.parent)
        result = dialog.exec()

        if result == GeneralSettingsWindow.Accepted:
            overrides = dialog._collect_overrides()

            changes_applied = []
            for key, value in overrides.items():
                if hasattr(CFG, key):
                    old_value = getattr(CFG, key)
                    setattr(CFG, key, value)
                    if old_value != value:
                        changes_applied.append(f"{key}: {old_value} → {value}")

            if changes_applied:
                if hasattr(self.parent, 'log_panel'):
                    self.parent.log_panel.log("✓ General settings updated:", "success")
                    for change in changes_applied[:5]:
                        self.parent.log_panel.log(f"  • {change}", "info")
                if any("LOG_LEVEL" in change for change in changes_applied):
                    reconfigure_loggers()
                self.parent.statusBar().showMessage(f"Applied {len(changes_applied)} general setting changes")
    
    def show_no_project_warning(self):
        """Show warning that no project is selected."""
        QMessageBox.warning(
            self.parent,
            "No Project Selected",
            "Please select or create a project first."
        )
    
    def offer_open_video(self, video_path: Path):
        """
        Offer to open final video after build completion.
        
        Args:
            video_path: Path to final video file
        """
        reply = QMessageBox.question(
            self.parent,
            "Build Complete! 🎉",
            f"Your highlight reel has been created successfully!\n\n"
            f"Location: {video_path}\n\n"
            f"Would you like to open the video now?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.Yes
        )
        
        if reply == QMessageBox.Yes:
            self._open_video_file(video_path)
    
    def _open_video_file(self, video_path: Path):
        """Open video file in default system player."""
        import subprocess
        import sys
        
        try:
            if sys.platform == 'darwin':  # macOS
                subprocess.run(['open', str(video_path)], check=True)
            elif sys.platform == 'win32':  # Windows
                subprocess.run(['start', str(video_path)], shell=True, check=True)
            else:  # Linux
                subprocess.run(['xdg-open', str(video_path)], check=True)
            
            if hasattr(self.parent, 'log_panel'):
                self.parent.log_panel.log(f"Opened video: {video_path.name}", "success")
        
        except Exception as e:
            QMessageBox.warning(
                self.parent,
                "Cannot Open Video",
                f"Could not open video automatically.\n\n"
                f"Please open manually:\n{video_path}"
            )