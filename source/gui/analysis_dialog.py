# source/gui/analysis_dialog.py
"""
Dialog window to display selection analysis results.
"""

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QTextEdit, QPushButton, QHBoxLayout, QLabel
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QFont

from pathlib import Path
from ..utils.selection_analyzer import SelectionAnalyzer, format_analysis_report


class AnalysisDialog(QDialog):
    """Dialog to display selection pipeline analysis."""
    
    def __init__(self, project_dir: Path, parent=None):
        super().__init__(parent)
        self.project_dir = project_dir
        
        self.setWindowTitle("Selection Pipeline Analysis")
        self.setMinimumSize(900, 700)
        self.setModal(True)
        
        self._setup_ui()
        self._run_analysis()
    
    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        
        # Title
        title = QLabel("Selection Pipeline Analysis")
        title.setStyleSheet("font-size: 18px; font-weight: bold; margin-bottom: 10px;")
        title.setAlignment(Qt.AlignCenter)
        layout.addWidget(title)
        
        # Info label
        info = QLabel(
            "Analyzing enriched.csv and select.csv to identify bottlenecks\n"
            "and provide recommendations for better clip selection."
        )
        info.setStyleSheet("color: #666; font-style: italic; margin-bottom: 10px;")
        info.setAlignment(Qt.AlignCenter)
        layout.addWidget(info)
        
        # Text display
        self.text_view = QTextEdit()
        self.text_view.setReadOnly(True)
        self.text_view.setLineWrapMode(QTextEdit.NoWrap)
        
        # Use monospace font for better alignment
        font = QFont("Monaco")
        if not font.exactMatch():
            font = QFont("Courier")
        font.setPointSize(11)
        self.text_view.setFont(font)
        
        layout.addWidget(self.text_view)
        
        # Buttons
        btn_layout = QHBoxLayout()
        
        self.refresh_btn = QPushButton("🔄 Refresh Analysis")
        self.refresh_btn.clicked.connect(self._run_analysis)
        self.refresh_btn.setStyleSheet("padding: 8px 16px; font-size: 13px;")
        
        self.close_btn = QPushButton("Close")
        self.close_btn.clicked.connect(self.accept)
        self.close_btn.setStyleSheet("padding: 8px 16px; font-size: 13px;")
        
        btn_layout.addWidget(self.refresh_btn)
        btn_layout.addStretch()
        btn_layout.addWidget(self.close_btn)
        
        layout.addLayout(btn_layout)
    
    def _run_analysis(self):
        """Run the analysis and display results."""
        self.text_view.setPlainText("Running analysis...")
        self.text_view.repaint()  # Force immediate update
        
        try:
            analyzer = SelectionAnalyzer(self.project_dir)
            results = analyzer.analyze()
            report = format_analysis_report(results)
            self.text_view.setPlainText(report)
            
        except Exception as e:
            self.text_view.setPlainText(
                f"❌ Analysis failed:\n\n{str(e)}\n\n"
                f"Make sure you have run the Analyze step first."
            )