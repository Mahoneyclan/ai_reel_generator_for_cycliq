# source/gui/gui_helpers/project_list_panel.py
"""
Project list panel widget.
Displays available projects and handles selection.
"""

from pathlib import Path
from typing import List, Tuple

from PySide6.QtWidgets import QWidget, QVBoxLayout, QLabel, QListWidget, QListWidgetItem
from PySide6.QtCore import Qt, Signal


class ProjectListPanel(QWidget):
    """Panel displaying list of available projects."""
    
    project_selected = Signal(Path)  # Emitted when project is clicked
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self._setup_ui()
    
    def _setup_ui(self):
        """Setup panel UI."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        
        # Header
        header = QLabel("Ride Projects")
        header.setStyleSheet("font-size: 16px; font-weight: bold; padding: 10px;")
        layout.addWidget(header)
        
        # Project list
        self.project_list = QListWidget()
        self.project_list.itemClicked.connect(self._on_item_clicked)
        layout.addWidget(self.project_list)
    
    def set_projects(self, projects: List[Tuple[str, Path]]):
        """
        Populate project list.
        
        Args:
            projects: List of (name, path) tuples
        """
        self.project_list.clear()
        
        for name, path in projects:
            item = QListWidgetItem(name)
            item.setData(Qt.UserRole, str(path))
            self.project_list.addItem(item)
    
    def select_project(self, project_path: Path):
        """
        Programmatically select a project.
        
        Args:
            project_path: Path to project to select
        """
        for i in range(self.project_list.count()):
            item = self.project_list.item(i)
            if Path(item.data(Qt.UserRole)) == project_path:
                self.project_list.setCurrentItem(item)
                self._on_item_clicked(item)
                break
    
    def _on_item_clicked(self, item: QListWidgetItem):
        """Handle project selection."""
        project_path = Path(item.data(Qt.UserRole))
        self.project_selected.emit(project_path)