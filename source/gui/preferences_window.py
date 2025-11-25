# source/gui/preferences_window.py
"""
Native macOS preferences dialog for streaming pipeline.
Scene scoring removed (requires JPGs). M1 controls added.
"""

from __future__ import annotations
from typing import Dict, Any
from pathlib import Path

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QTabWidget, QWidget, QFormLayout,
    QLineEdit, QSpinBox, QDoubleSpinBox, QCheckBox,
    QPushButton, QHBoxLayout, QLabel
)

from ..config import DEFAULT_CONFIG as CFG

class PreferencesWindow(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Preferences")
        self.setMinimumSize(600, 500)
        self.setModal(True)

        self.overrides: Dict[str, Any] = {}
        
        layout = QVBoxLayout(self)
        
        self.tabs = QTabWidget()
        layout.addWidget(self.tabs)

        self.core_tab = QWidget()
        self.core_form = QFormLayout(self.core_tab)
        self.tabs.addTab(self.core_tab, "Core")

        self.video_tab = QWidget()
        self.video_form = QFormLayout(self.video_tab)
        self.tabs.addTab(self.video_tab, "Video")

        self.detect_tab = QWidget()
        self.detect_form = QFormLayout(self.detect_tab)
        self.tabs.addTab(self.detect_tab, "Detection")
        
        self.m1_tab = QWidget()
        self.m1_form = QFormLayout(self.m1_tab)
        self.tabs.addTab(self.m1_tab, "M1 Performance")

        btn_layout = QHBoxLayout()
        save_btn = QPushButton("Save")
        save_btn.clicked.connect(self.accept)
        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        btn_layout.addWidget(cancel_btn)
        btn_layout.addWidget(save_btn)
        layout.addLayout(btn_layout)

        self._create_core_settings()
        self._create_video_settings()
        self._create_detection_settings()
        self._create_m1_settings()
        self.load_current_values()

    def _add_line_edit(self, form, label, attr, value):
        widget = QLineEdit(value)
        form.addRow(label, widget)
        self.overrides[attr] = widget

    def _add_spinbox(self, form, label, attr, value, min_val, max_val):
        widget = QSpinBox()
        widget.setRange(min_val, max_val)
        widget.setValue(value)
        form.addRow(label, widget)
        self.overrides[attr] = widget

    def _add_doublespinbox(self, form, label, attr, value, min_val, max_val, step):
        widget = QDoubleSpinBox()
        widget.setRange(min_val, max_val)
        widget.setSingleStep(step)
        widget.setValue(value)
        form.addRow(label, widget)
        self.overrides[attr] = widget

    def _add_checkbox(self, form, label, attr, value):
        widget = QCheckBox()
        widget.setChecked(value)
        form.addRow(label, widget)
        self.overrides[attr] = widget

    def _create_core_settings(self):
        self._add_doublespinbox(self.core_form, "Extract FPS", "EXTRACT_FPS", CFG.EXTRACT_FPS, 0.5, 10.0, 0.5)
        self._add_doublespinbox(self.core_form, "Target Duration (s)", "HIGHLIGHT_TARGET_DURATION_S", CFG.HIGHLIGHT_TARGET_DURATION_S, 30, 600, 30)
        self._add_doublespinbox(self.core_form, "Clip Pre-Roll (s)", "CLIP_PRE_ROLL_S", CFG.CLIP_PRE_ROLL_S, 0, 2, 0.1)
        self._add_doublespinbox(self.core_form, "Clip Duration (s)", "CLIP_OUT_LEN_S", CFG.CLIP_OUT_LEN_S, 1, 10, 0.1)
        self._add_doublespinbox(self.core_form, "Min Gap Between Clips (s)", "MIN_GAP_BETWEEN_CLIPS", CFG.MIN_GAP_BETWEEN_CLIPS, 30, 300, 10)

    def _create_video_settings(self):
        self._add_line_edit(self.video_form, "Video Codec", "VIDEO_CODEC", CFG.VIDEO_CODEC)
        self._add_line_edit(self.video_form, "Bitrate", "BITRATE", CFG.BITRATE)
        self._add_line_edit(self.video_form, "Max Rate", "MAXRATE", CFG.MAXRATE)
        self._add_line_edit(self.video_form, "Buffer Size", "BUFSIZE", CFG.BUFSIZE)
        self._add_doublespinbox(self.video_form, "Musuc Volume", "MUSIC_VOLUME", CFG.MUSIC_VOLUME, 0, 1, 0.1)
        self._add_doublespinbox(self.video_form, "Raw Audio Volume", "RAW_AUDIO_VOLUME", CFG.RAW_AUDIO_VOLUME, 0, 1, 0.1)
        self._add_doublespinbox(self.video_form, "PiP Scale Ratio", "PIP_SCALE_RATIO", CFG.PIP_SCALE_RATIO, 0, 1, 0.05)
        self._add_spinbox(self.video_form, "PiP Margin", "PIP_MARGIN", CFG.PIP_MARGIN, 0, 100)
        self._add_doublespinbox(self.video_form, "Minimap Scale Ratio", "MINIMAP_SCALE_RATIO", CFG.MINIMAP_SCALE_RATIO, 0, 1, 0.05)
        self._add_spinbox(self.video_form, "Minimap Margin", "MINIMAP_MARGIN", CFG.MINIMAP_MARGIN, 0, 100)

    def _create_detection_settings(self):
        self._add_spinbox(self.detect_form, "YOLO Image Size", "YOLO_IMAGE_SIZE", CFG.YOLO_IMAGE_SIZE, 320, 1280)
        self._add_doublespinbox(self.detect_form, "YOLO Min Confidence", "YOLO_MIN_CONFIDENCE", CFG.YOLO_MIN_CONFIDENCE, 0, 1, 0.05)
        self._add_doublespinbox(self.detect_form, "Min Detect Score", "MIN_DETECT_SCORE", CFG.MIN_DETECT_SCORE, 0, 1, 0.05)
        self._add_doublespinbox(self.detect_form, "Min Speed Penalty", "MIN_SPEED_PENALTY", CFG.MIN_SPEED_PENALTY, 0, 20, 1)
        self._add_doublespinbox(self.detect_form, "Start Zone Duration (s)", "START_ZONE_DURATION_S", CFG.START_ZONE_DURATION_S, 0, 1800, 60)
        self._add_doublespinbox(self.detect_form, "Start Zone Penalty", "START_ZONE_PENALTY", CFG.START_ZONE_PENALTY, 0, 1, 0.05)
        self._add_doublespinbox(self.detect_form, "Max Start Zone Fraction", "MAX_START_ZONE_FRAC", CFG.MAX_START_ZONE_FRAC, 0, 1, 0.05)
        self._add_doublespinbox(self.detect_form, "End Zone Duration (s)", "END_ZONE_DURATION_S", CFG.END_ZONE_DURATION_S, 0, 1800, 60)
        self._add_doublespinbox(self.detect_form, "End Zone Penalty", "END_ZONE_PENALTY", CFG.END_ZONE_PENALTY, 0, 1, 0.05)
        self._add_doublespinbox(self.detect_form, "Max End Zone Fraction", "MAX_END_ZONE_FRAC", CFG.MAX_END_ZONE_FRAC, 0, 1, 0.05)
        self._add_doublespinbox(self.detect_form, "GPX Tolerance (s)", "GPX_TOLERANCE", CFG.GPX_TOLERANCE, 0, 10, 0.5)
        self._add_doublespinbox(self.detect_form, "Partner Time Tolerance (s)", "PARTNER_TIME_TOLERANCE_S", CFG.PARTNER_TIME_TOLERANCE_S, 0, 10, 0.5)

    def _create_m1_settings(self):
        note = QLabel("M1-specific settings for hardware acceleration")
        note.setStyleSheet("font-style: italic; color: #666;")
        self.m1_form.addRow(note)
        
        self._add_checkbox(self.m1_form, "Use M1 GPU (MPS)", "USE_MPS", CFG.USE_MPS)
        self._add_spinbox(self.m1_form, "YOLO Batch Size (RAM limit)", "YOLO_BATCH_SIZE", CFG.YOLO_BATCH_SIZE, 1, 16)
        self._add_line_edit(self.m1_form, "FFmpeg HW Accel", "FFMPEG_HWACCEL", CFG.FFMPEG_HWACCEL)

    def load_current_values(self):
        """Load values from DEFAULT_CONFIG."""
        cfg = CFG
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

    def get_overrides(self) -> Dict[str, Any]:
        """Collect all overrides from UI widgets."""
        overrides: Dict[str, Any] = {}
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
        return overrides

