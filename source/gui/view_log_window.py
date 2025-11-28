# source/gui/view_log_window.py
"""
View Log Window - displays logs for selected ride project.
UPDATED: Clean, understated visual theme.
"""

from pathlib import Path
from datetime import datetime

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QListWidget, QListWidgetItem, QSplitter, QTextEdit, QWidget
)
from PySide6.QtCore import Qt


class ViewLogWindow(QDialog):
    """Window to view log files for a ride project with clean styling."""
    
    def __init__(self, project_dir: Path, parent=None):
        super().__init__(parent)
        self.project_dir = project_dir
        self.logs_dir = project_dir / "logs"
        
        self.setWindowTitle(f"View Logs - {project_dir.name}")
        self.setMinimumSize(900, 600)
        self.resize(1100, 700)
        self.setModal(False)
        
        self._setup_ui()
        self._load_log_files()
    
    def _setup_ui(self):
        """Set up the UI - clean two-panel layout."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        
        # Main splitter
        splitter = QSplitter(Qt.Horizontal)
        splitter.setHandleWidth(1)
        splitter.setStyleSheet("QSplitter::handle { background-color: #E5E5E5; }")
        
        # Left panel
        left_panel = self._create_left_panel()
        splitter.addWidget(left_panel)
        
        # Right panel
        right_panel = self._create_right_panel()
        splitter.addWidget(right_panel)
        
        # Set sizes (25% left, 75% right)
        splitter.setStretchFactor(0, 25)
        splitter.setStretchFactor(1, 75)
        
        layout.addWidget(splitter)
    
    def _create_left_panel(self) -> QWidget:
        """Create left panel with log file list."""
        panel = QWidget()
        panel.setStyleSheet("background-color: #FAFAFA;")
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)
        
        # Header with refresh button
        header_layout = QHBoxLayout()
        header = QLabel("Available Logs")
        header.setStyleSheet(
            "font-size: 13px; font-weight: 600; color: #333; padding: 2px;"
        )
        header_layout.addWidget(header)
        header_layout.addStretch()
        
        # Refresh button
        self.refresh_btn = QPushButton("🔄")
        self.refresh_btn.clicked.connect(self._load_log_files)
        self.refresh_btn.setFixedSize(28, 28)
        self.refresh_btn.setStyleSheet("""
            QPushButton {
                padding: 2px;
                font-size: 12px;
                border: 2px solid #E5E5E5;
                border-radius: 4px;
                background-color: #FFFFFF;
            }
            QPushButton:hover {
                background-color: #F8F9FA;
                border-color: #CCCCCC;
            }
        """)
        header_layout.addWidget(self.refresh_btn)
        
        layout.addLayout(header_layout)
        
        # Log list
        self.log_list = QListWidget()
        self.log_list.itemClicked.connect(self._on_log_selected)
        self.log_list.setStyleSheet("""
            QListWidget {
                border: 1px solid #E5E5E5;
                background-color: #FFFFFF;
                font-size: 11px;
                outline: none;
                border-radius: 4px;
            }
            QListWidget::item {
                padding: 8px;
                border-bottom: 1px solid #F5F5F5;
            }
            QListWidget::item:selected {
                background-color: #F0F9F4;
                color: #2D7A4F;
                border-left: 3px solid #6EBF8B;
            }
            QListWidget::item:hover:!selected {
                background-color: #F8F9FA;
            }
        """)
        layout.addWidget(self.log_list)
        
        return panel
    
    def _create_right_panel(self) -> QWidget:
        """Create right panel with log content."""
        panel = QWidget()
        panel.setStyleSheet("background-color: #FFFFFF;")
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)
        
        # Header with close button
        header_layout = QHBoxLayout()
        self.content_label = QLabel("Select a log file to view")
        self.content_label.setStyleSheet(
            "font-size: 13px; font-weight: 600; color: #333; padding: 2px;"
        )
        header_layout.addWidget(self.content_label)
        header_layout.addStretch()
        
        # Close button
        close_btn = QPushButton("Close")
        close_btn.clicked.connect(self.accept)
        close_btn.setStyleSheet("""
            QPushButton {
                padding: 6px 16px;
                font-size: 12px;
                font-weight: 600;
                border: 2px solid #E5E5E5;
                border-radius: 4px;
                background-color: #FFFFFF;
                color: #333333;
            }
            QPushButton:hover {
                background-color: #F8F9FA;
                border-color: #CCCCCC;
            }
        """)
        header_layout.addWidget(close_btn)
        
        layout.addLayout(header_layout)
        
        # Log content
        self.log_content = QTextEdit()
        self.log_content.setReadOnly(True)
        self.log_content.setStyleSheet("""
            QTextEdit {
                background-color: #FAFAFA;
                border: 1px solid #E5E5E5;
                border-radius: 4px;
                font-family: 'Monaco', 'Menlo', 'Courier New', monospace;
                font-size: 10px;
                line-height: 1.5;
                padding: 8px;
            }
        """)
        layout.addWidget(self.log_content)
        
        return panel

    def _load_log_files(self):
        """Load list of log files from logs directory."""
        self.log_list.clear()
        self.log_content.clear()
        self.content_label.setText("Select a log file to view")
        
        if not self.logs_dir.exists():
            item = QListWidgetItem("⚠️  No logs directory")
            item.setFlags(Qt.ItemIsEnabled)
            self.log_list.addItem(item)
            return
        
        # Get all .txt log files
        log_files = sorted(self.logs_dir.glob("*.txt"))
        
        if not log_files:
            item = QListWidgetItem("📝 No log files found")
            item.setFlags(Qt.ItemIsEnabled)
            self.log_list.addItem(item)
            return
        
        # Add log files to list
        for log_file in log_files:
            try:
                stat = log_file.stat()
                size_kb = stat.st_size / 1024
                mod_time = datetime.fromtimestamp(stat.st_mtime)
                
                # Clean display
                display_name = f"📄 {log_file.name}"
                subtitle = f"    {size_kb:.1f} KB • {mod_time.strftime('%Y-%m-%d %H:%M')}"
                
                item = QListWidgetItem(f"{display_name}\n{subtitle}")
                item.setData(Qt.UserRole, str(log_file))
                self.log_list.addItem(item)
                
            except Exception:
                item = QListWidgetItem(f"⚠️  {log_file.name}")
                item.setFlags(Qt.ItemIsEnabled)
                self.log_list.addItem(item)
    
    def _on_log_selected(self, item: QListWidgetItem):
        """Load and display selected log file."""
        log_path_str = item.data(Qt.UserRole)
        if not log_path_str:
            return
        
        log_path = Path(log_path_str)
        
        try:
            self.content_label.setText(f"Log: {log_path.name}")
            
            with log_path.open('r', encoding='utf-8', errors='replace') as f:
                content = f.read()
            
            formatted = self._format_log_content(content)
            self.log_content.setHtml(formatted)
            
            # Scroll to bottom
            self.log_content.verticalScrollBar().setValue(
                self.log_content.verticalScrollBar().maximum()
            )
            
        except Exception as e:
            self.log_content.setPlainText(f"Error reading log:\n{str(e)}")
    
    def _format_log_content(self, content: str) -> str:
        """Format log content with subtle color coding."""
        lines = content.split('\n')
        formatted = []
        
        for line in lines:
            # Determine color based on log level - understated palette
            if '| ERROR |' in line or '| CRITICAL |' in line:
                color = '#D32F2F'
            elif '| WARNING |' in line:
                color = '#F57C00'
            elif '| INFO |' in line:
                color = '#333333'
            elif '| DEBUG |' in line:
                color = '#999999'
            else:
                color = '#666666'
            
            # Escape HTML
            escaped = (line
                .replace('&', '&amp;')
                .replace('<', '&lt;')
                .replace('>', '&gt;')
                .replace(' ', '&nbsp;')
            )
            
            formatted.append(
                f'<div style="color: {color}; font-family: Monaco, monospace; font-size: 10px;">{escaped}</div>'
            )
        
        return ''.join(formatted)