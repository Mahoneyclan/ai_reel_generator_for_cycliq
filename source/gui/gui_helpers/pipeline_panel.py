# source/gui/gui_helpers/pipeline_panel.py
"""
Pipeline steps panel widget.
Displays project info and pipeline step buttons.
"""

from PySide6.QtWidgets import QWidget, QVBoxLayout, QLabel, QPushButton
from PySide6.QtCore import Signal


class PipelinePanel(QWidget):
    """Panel displaying pipeline steps and project info."""
    
    prepare_clicked = Signal()
    analyze_clicked = Signal()
    select_clicked = Signal()
    finalize_clicked = Signal()
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self._setup_ui()
    
    def _setup_ui(self):
        """Setup panel UI."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(12)
        
        # Project info
        self.project_name_label = QLabel("No project loaded")
        self.project_name_label.setStyleSheet(
            "font-size: 18px; font-weight: bold; color: #1a1a1a;"
        )
        layout.addWidget(self.project_name_label)
        
        self.project_info_label = QLabel()
        self.project_info_label.setStyleSheet("font-size: 12px; color: #666;")
        layout.addWidget(self.project_info_label)
        
        # Pipeline steps header
        steps_label = QLabel("Pipeline Steps")
        steps_label.setStyleSheet(
            "font-size: 14px; font-weight: 600; color: #666; "
            "padding: 10px 0 5px 0;"
        )
        layout.addWidget(steps_label)
        
        # Step buttons
        self.btn_prepare = self._create_button(
            "Prepare",
            "Validate inputs, parse GPX, and align camera timestamps",
            self.prepare_clicked
        )
        layout.addWidget(self.btn_prepare)
        
        self.btn_analyze = self._create_button(
            "Analyze",
            "Extract frame metadata and detect bikes with AI",
            self.analyze_clicked
        )
        layout.addWidget(self.btn_analyze)
        
        self.btn_select = self._create_button(
            "Select",
            "AI recommends clips, then you review and finalize selection",
            self.select_clicked
        )
        layout.addWidget(self.btn_select)
        
        self.btn_finalize = self._create_button(
            "Build",
            "Render clips with overlays, create intro/outro, and assemble final video",
            self.finalize_clicked
        )
        layout.addWidget(self.btn_finalize)
        
        layout.addStretch()
    
    def _create_button(self, text: str, tooltip: str, signal: Signal) -> QPushButton:
        """Create a pipeline step button."""
        btn = QPushButton(text)
        btn.clicked.connect(signal.emit)
        btn.setMinimumHeight(50)
        btn.setToolTip(tooltip)
        btn.setProperty("original_text", text)
        btn.setStyleSheet(self._get_default_style())
        return btn
    
    def set_project_info(self, name: str, path: str):
        """Update project information display."""
        self.project_name_label.setText(name)
        self.project_info_label.setText(path)
    
    def update_button_states(
        self,
        prepare_enabled: bool = False,
        prepare_done: bool = False,
        analyze_enabled: bool = False,
        analyze_done: bool = False,
        select_enabled: bool = False,
        select_done: bool = False,
        finalize_enabled: bool = False,
        finalize_done: bool = False
    ):
        """Update button enabled states and completion indicators."""
        self._update_button(self.btn_prepare, prepare_enabled, prepare_done)
        self._update_button(self.btn_analyze, analyze_enabled, analyze_done)
        self._update_button(self.btn_select, select_enabled, select_done)
        self._update_button(self.btn_finalize, finalize_enabled, finalize_done)
    
    def disable_all(self):
        """Disable all pipeline buttons."""
        for btn in [self.btn_prepare, self.btn_analyze, self.btn_select, self.btn_finalize]:
            btn.setEnabled(False)
            btn.setStyleSheet(self._get_default_style())
    
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
        """Get default button stylesheet."""
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
        """Get completed button stylesheet."""
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