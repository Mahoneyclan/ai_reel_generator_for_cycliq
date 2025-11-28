# source/gui/preferences_window.py
"""
Native macOS preferences dialog for streaming pipeline.
Scene scoring removed (requires JPGs). M1 controls added.
Now includes YOLO detection classes selection.
"""

from __future__ import annotations
from typing import Dict, Any
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QTabWidget, QWidget, QFormLayout,
    QLineEdit, QSpinBox, QDoubleSpinBox, QCheckBox,
    QPushButton, QHBoxLayout, QLabel, QSizePolicy, QScrollArea,
    QGridLayout, QGroupBox
)

from ..config import DEFAULT_CONFIG as CFG


FIELD_MIN_WIDTH = 220  # baseline width for all input widgets


def _fix_size(widget):
    """Apply consistent sizing policy to all input widgets."""
    widget.setMinimumWidth(FIELD_MIN_WIDTH)
    widget.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
    return widget


class PreferencesWindow(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Preferences")
        self.setMinimumSize(700, 600)
        self.setModal(True)

        self.overrides: Dict[str, Any] = {}
        self.class_checkboxes: Dict[str, QCheckBox] = {}

        layout = QVBoxLayout(self)

        self.tabs = QTabWidget()
        layout.addWidget(self.tabs)

        # Tabs with form layouts
        self.core_tab, self.core_form = self._make_tab("Core")
        self.video_tab, self.video_form = self._make_tab("Video")
        self.detect_tab, self.detect_form = self._make_tab("Detection")
        self.yolo_tab = self._make_yolo_tab("YOLO Classes")
        self.m1_tab, self.m1_form = self._make_tab("M1 Performance")

        # Buttons
        btn_layout = QHBoxLayout()
        save_btn = QPushButton("Save")
        save_btn.clicked.connect(self.accept)
        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        btn_layout.addWidget(cancel_btn)
        btn_layout.addWidget(save_btn)
        layout.addLayout(btn_layout)

        # Populate tabs
        self._create_core_settings()
        self._create_video_settings()
        self._create_detection_settings()
        self._create_m1_settings()
        self.load_current_values()

        # Global polish: label alignment and growth
        for form in (self.core_form, self.video_form, self.detect_form, self.m1_form):
            form.setLabelAlignment(Qt.AlignRight | Qt.AlignVCenter)
            form.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow)
            form.setSpacing(8)

    def _make_tab(self, name: str):
        """Create a tab with a form layout and add it to the tab widget."""
        tab = QWidget()
        form = QFormLayout(tab)
        self.tabs.addTab(tab, name)
        return tab, form

    def _make_yolo_tab(self, name: str) -> QWidget:
        """Create YOLO detection classes tab."""
        tab = QWidget()
        self.tabs.addTab(tab, name)
        
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(20, 20, 20, 20)
        
        # Description
        description = QLabel(
            "Select which object classes YOLO should detect in your video frames.\n"
            "By default, only 'bicycle' is selected for cycling videos."
        )
        description.setWordWrap(True)
        description.setStyleSheet("font-size: 12px; color: #666; padding: 10px;")
        layout.addWidget(description)
        
        # Quick selection buttons
        quick_select_layout = QHBoxLayout()
        
        btn_select_all = QPushButton("Select All")
        btn_select_all.clicked.connect(self._select_all_classes)
        btn_select_all.setStyleSheet("""
            QPushButton {
                background-color: #FFFFFF;
                color: #333333;
                padding: 6px 12px;
                border: 2px solid #DDDDDD;
                border-radius: 4px;
                font-weight: 600;
            }
            QPushButton:hover {
                background-color: #F8F9FA;
                border-color: #007AFF;
            }
        """)
        
        btn_select_none = QPushButton("Select None")
        btn_select_none.clicked.connect(self._select_no_classes)
        btn_select_none.setStyleSheet("""
            QPushButton {
                background-color: #FFFFFF;
                color: #333333;
                padding: 6px 12px;
                border: 2px solid #DDDDDD;
                border-radius: 4px;
                font-weight: 600;
            }
            QPushButton:hover {
                background-color: #F8F9FA;
                border-color: #FF3B30;
            }
        """)
        
        btn_reset_default = QPushButton("Reset to Default (Bicycle)")
        btn_reset_default.clicked.connect(self._reset_to_default)
        btn_reset_default.setStyleSheet("""
            QPushButton {
                background-color: #F0F9F4;
                color: #2D7A4F;
                padding: 6px 12px;
                border: 2px solid #6EBF8B;
                border-radius: 4px;
                font-weight: 600;
            }
            QPushButton:hover {
                background-color: #E5F4EC;
                border-color: #5CAF7B;
            }
        """)
        
        quick_select_layout.addWidget(btn_select_all)
        quick_select_layout.addWidget(btn_select_none)
        quick_select_layout.addWidget(btn_reset_default)
        quick_select_layout.addStretch()
        
        layout.addLayout(quick_select_layout)
        
        # Group box for checkboxes
        group_box = QGroupBox("Detection Classes")
        group_box.setStyleSheet("""
            QGroupBox {
                font-size: 13px;
                font-weight: bold;
                border: 2px solid #DDD;
                border-radius: 5px;
                margin-top: 10px;
                padding-top: 15px;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 5px;
            }
        """)
        
        # Container for checkboxes - 2 columns
        checkbox_layout = QGridLayout()
        checkbox_layout.setSpacing(15)
        checkbox_layout.setContentsMargins(20, 20, 20, 20)
        
        # Create checkboxes for cycling-relevant YOLO classes
        all_classes = list(CFG.YOLO_CLASS_MAP.keys())
        columns = 2
        
        for idx, class_name in enumerate(all_classes):
            row = idx // columns
            col = idx % columns
            
            checkbox = QCheckBox(class_name.title())
            checkbox.setStyleSheet("font-size: 13px;")
            self.class_checkboxes[class_name] = checkbox
            
            checkbox_layout.addWidget(checkbox, row, col)
        
        group_box.setLayout(checkbox_layout)
        layout.addWidget(group_box)
        
        # Selected count label
        self.selected_count_label = QLabel("Selected: 0 classes")
        self.selected_count_label.setStyleSheet(
            "font-size: 12px; font-weight: 600; color: #2D7A4F; padding: 10px;"
        )
        layout.addWidget(self.selected_count_label)
        
        # Add stretch to push everything to the top
        layout.addStretch()
        
        # Connect all checkboxes to update count
        for checkbox in self.class_checkboxes.values():
            checkbox.stateChanged.connect(self._update_selected_count)
        
        return tab

    # --- Helper methods for adding fields ---
    def _add_line_edit(self, form, label, attr, value):
        widget = _fix_size(QLineEdit(str(value)))
        form.addRow(label, widget)
        self.overrides[attr] = widget

    def _add_spinbox(self, form, label, attr, value, min_val, max_val):
        widget = _fix_size(QSpinBox())
        widget.setRange(min_val, max_val)
        widget.setValue(value)
        form.addRow(label, widget)
        self.overrides[attr] = widget

    def _add_doublespinbox(self, form, label, attr, value, min_val, max_val, step):
        widget = _fix_size(QDoubleSpinBox())
        widget.setRange(min_val, max_val)
        widget.setSingleStep(step)
        widget.setValue(value)
        form.addRow(label, widget)
        self.overrides[attr] = widget

    def _add_checkbox(self, form, label, attr, value):
        widget = _fix_size(QCheckBox())
        widget.setChecked(value)
        form.addRow(label, widget)
        self.overrides[attr] = widget

    # --- Settings population ---
    def _create_core_settings(self):
        self._add_doublespinbox(self.core_form, "Extract FPS", "EXTRACT_FPS", CFG.EXTRACT_FPS, 0.5, 10.0, 0.5)
        self._add_doublespinbox(self.core_form, "Target Duration (s)", "HIGHLIGHT_TARGET_DURATION_S", CFG.HIGHLIGHT_TARGET_DURATION_S, 30, 600, 30)
        self._add_doublespinbox(self.core_form, "Clip Pre-Roll (s)", "CLIP_PRE_ROLL_S", CFG.CLIP_PRE_ROLL_S, 0, 2, 0.1)
        self._add_doublespinbox(self.core_form, "Clip Duration (s)", "CLIP_OUT_LEN_S", CFG.CLIP_OUT_LEN_S, 1, 10, 0.1)
        self._add_doublespinbox(self.core_form, "Min Gap Between Clips (s)", "MIN_GAP_BETWEEN_CLIPS", CFG.MIN_GAP_BETWEEN_CLIPS, 30, 300, 10)
        self._add_doublespinbox(self.core_form, "Scene Comparison Window (s)", "SCENE_COMPARISON_WINDOW_S", CFG.SCENE_COMPARISON_WINDOW_S, 1.0, 15.0, 0.5)
        self._add_doublespinbox(self.core_form, "Start Zone Duration (s)", "START_ZONE_DURATION_S", CFG.START_ZONE_DURATION_S, 0, 1800, 60)
        self._add_doublespinbox(self.core_form, "Max Start Zone Fraction", "MAX_START_ZONE_FRAC", CFG.MAX_START_ZONE_FRAC, 0, 1, 0.05)
        self._add_doublespinbox(self.core_form, "End Zone Duration (s)", "END_ZONE_DURATION_S", CFG.END_ZONE_DURATION_S, 0, 1800, 60)
        self._add_doublespinbox(self.core_form, "Max End Zone Fraction", "MAX_END_ZONE_FRAC", CFG.MAX_END_ZONE_FRAC, 0, 1, 0.05)

    def _create_video_settings(self):
        self._add_line_edit(self.video_form, "Video Codec", "VIDEO_CODEC", CFG.VIDEO_CODEC)
        self._add_line_edit(self.video_form, "Bitrate", "BITRATE", CFG.BITRATE)
        self._add_line_edit(self.video_form, "Max Rate", "MAXRATE", CFG.MAXRATE)
        self._add_line_edit(self.video_form, "Buffer Size", "BUFSIZE", CFG.BUFSIZE)
        self._add_doublespinbox(self.video_form, "Music Volume", "MUSIC_VOLUME", CFG.MUSIC_VOLUME, 0, 1, 0.1)
        self._add_doublespinbox(self.video_form, "Raw Audio Volume", "RAW_AUDIO_VOLUME", CFG.RAW_AUDIO_VOLUME, 0, 1, 0.1)
        self._add_doublespinbox(self.video_form, "PiP Scale Ratio", "PIP_SCALE_RATIO", CFG.PIP_SCALE_RATIO, 0, 1, 0.05)
        self._add_spinbox(self.video_form, "PiP Margin", "PIP_MARGIN", CFG.PIP_MARGIN, 0, 100)
        self._add_doublespinbox(self.video_form, "Minimap Scale Ratio", "MINIMAP_SCALE_RATIO", CFG.MINIMAP_SCALE_RATIO, 0, 1, 0.05)
        self._add_spinbox(self.video_form, "Minimap Margin", "MINIMAP_MARGIN", CFG.MINIMAP_MARGIN, 0, 100)

    def _create_detection_settings(self):
        self._add_doublespinbox(self.detect_form, "Min Detect Score", "MIN_DETECT_SCORE", CFG.MIN_DETECT_SCORE, 0, 1, 0.05)
        self._add_doublespinbox(self.detect_form, "Min Speed Penalty", "MIN_SPEED_PENALTY", CFG.MIN_SPEED_PENALTY, 0, 20, 1)
        self._add_doublespinbox(self.detect_form, "Start Zone Penalty", "START_ZONE_PENALTY", CFG.START_ZONE_PENALTY, 0, 1, 0.05)
        self._add_doublespinbox(self.detect_form, "End Zone Penalty", "END_ZONE_PENALTY", CFG.END_ZONE_PENALTY, 0, 1, 0.05)
        self._add_doublespinbox(self.detect_form, "GPX Tolerance (s)", "GPX_TOLERANCE", CFG.GPX_TOLERANCE, 0, 10, 0.5)
        self._add_doublespinbox(self.detect_form, "Partner Time Tolerance (s)", "PARTNER_TIME_TOLERANCE_S", CFG.PARTNER_TIME_TOLERANCE_S, 0, 10, 0.5)
        self._add_doublespinbox(self.detect_form, "YOLO Min Confidence", "YOLO_MIN_CONFIDENCE", CFG.YOLO_MIN_CONFIDENCE, 0, 1, 0.05)
        self._add_spinbox(self.detect_form, "YOLO Image Size", "YOLO_IMAGE_SIZE", CFG.YOLO_IMAGE_SIZE, 320, 1280)

    def _create_m1_settings(self):
        note = QLabel("M1-specific settings for hardware acceleration")
        note.setStyleSheet("font-style: italic; color: #666;")
        self.m1_form.addRow(note)

        self._add_checkbox(self.m1_form, "Use M1 GPU (MPS)", "USE_MPS", CFG.USE_MPS)
        self._add_spinbox(self.m1_form, "YOLO Batch Size (RAM limit)", "YOLO_BATCH_SIZE", CFG.YOLO_BATCH_SIZE, 1, 16)
        self._add_line_edit(self.m1_form, "FFmpeg HW Accel", "FFMPEG_HWACCEL", CFG.FFMPEG_HWACCEL)

    # --- YOLO classes methods ---
    def _select_all_classes(self):
        """Select all detection classes."""
        for checkbox in self.class_checkboxes.values():
            checkbox.setChecked(True)

    def _select_no_classes(self):
        """Deselect all detection classes."""
        for checkbox in self.class_checkboxes.values():
            checkbox.setChecked(False)

    def _reset_to_default(self):
        """Reset to default selection (bicycle only)."""
        for class_name, checkbox in self.class_checkboxes.items():
            checkbox.setChecked(class_name == "bicycle")

    def _update_selected_count(self):
        """Update the label showing how many classes are selected."""
        count = sum(1 for cb in self.class_checkboxes.values() if cb.isChecked())
        self.selected_count_label.setText(f"Selected: {count} class{'es' if count != 1 else ''}")

    # --- Value loading and overrides ---
    def load_current_values(self):
        """Load values from DEFAULT_CONFIG into widgets."""
        cfg = CFG
        
        # Load standard config values
        for attr, widget in self.overrides.items():
            val = getattr(cfg, attr, None)
            if val is None:
                continue
            if isinstance(widget, QLineEdit):
                widget.setText(str(val))
            elif isinstance(widget, QSpinBox):
                widget.setValue(int(val))
            elif isinstance(widget, QDoubleSpinBox):
                widget.setValue(float(val))
            elif isinstance(widget, QCheckBox):
                widget.setChecked(bool(val))
        
        # Load YOLO detection classes
        current_ids = getattr(cfg, 'YOLO_DETECT_CLASSES', [1])
        for class_name, class_id in CFG.YOLO_CLASS_MAP.items():
            if class_name in self.class_checkboxes:
                self.class_checkboxes[class_name].setChecked(class_id in current_ids)
        
        self._update_selected_count()

    def get_overrides(self) -> Dict[str, Any]:
        """Collect all overrides from UI widgets."""
        overrides: Dict[str, Any] = {}
        
        # Collect standard overrides
        for attr, widget in self.overrides.items():
            if isinstance(widget, QLineEdit):
                text = widget.text().strip()
                current = getattr(CFG, attr, None)
                if isinstance(current, Path):
                    overrides[attr] = Path(text)
                else:
                    overrides[attr] = text
            elif isinstance(widget, QSpinBox):
                overrides[attr] = widget.value()
            elif isinstance(widget, QDoubleSpinBox):
                overrides[attr] = widget.value()
            elif isinstance(widget, QCheckBox):
                overrides[attr] = widget.isChecked()
        
        # Collect YOLO detection class IDs
        selected_ids = [
            CFG.YOLO_CLASS_MAP[class_name]
            for class_name, checkbox in self.class_checkboxes.items()
            if checkbox.isChecked()
        ]
        overrides['YOLO_DETECT_CLASSES'] = selected_ids
        
        return overrides