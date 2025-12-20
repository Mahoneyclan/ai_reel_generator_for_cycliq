# source/gui/preferences_window.py
"""
Native macOS preferences dialog for streaming pipeline.
Scene scoring removed (requires JPGs). M1 controls added.
Now includes YOLO detection classes selection, score weights, and persistent storage.
"""

from __future__ import annotations
from typing import Dict, Any
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QTabWidget, QWidget, QFormLayout,
    QLineEdit, QSpinBox, QDoubleSpinBox, QCheckBox,
    QPushButton, QHBoxLayout, QLabel, QSizePolicy, QGridLayout,
    QGroupBox, QFileDialog, QMessageBox
)

from ..utils.persistent_config import save_persistent_config, load_persistent_config, clear_persistent_config
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
        self.score_tab, self.score_form = self._make_tab("Score Weights")
        self.paths_tab, self.paths_form = self._make_tab("Paths")
        self.yolo_tab = self._make_yolo_tab("Detection Classes")
        self.detect_tab, self.detect_form = self._make_tab("Detection Settings")
        self.video_tab, self.video_form = self._make_tab("Video Settings")
        self.m1_tab, self.m1_form = self._make_tab("M1 Performance")

        # Populate tabs
        self._create_core_settings()
        self._create_score_settings()
        self._create_paths_settings()
        self._create_detection_settings()
        self._create_m1_settings()
        self._create_video_settings()

        self.load_current_values()

        # Buttons
        btn_layout = QHBoxLayout()
        save_btn = QPushButton("Save")
        save_btn.clicked.connect(self.accept)
        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        btn_layout.addWidget(cancel_btn)
        btn_layout.addWidget(save_btn)
        layout.addLayout(btn_layout)

        # Global polish: label alignment and growth
        for form in (
            self.core_form, self.video_form, self.detect_form,
            self.m1_form, self.paths_form, self.score_form
        ):
            form.setLabelAlignment(Qt.AlignRight | Qt.AlignVCenter)
            form.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow)
            form.setSpacing(8)

    def _make_tab(self, name: str):
        tab = QWidget()
        form = QFormLayout(tab)
        self.tabs.addTab(tab, name)
        return tab, form

    def _make_yolo_tab(self, name: str) -> QWidget:
        tab = QWidget()
        self.tabs.addTab(tab, name)
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(20, 20, 20, 20)

        description = QLabel(
            "Select which object classes YOLO should detect in your video frames.\n"
            "By default, only 'bicycle' is selected for cycling videos."
        )
        description.setWordWrap(True)
        description.setStyleSheet("font-size: 12px; color: #666; padding: 10px;")
        layout.addWidget(description)

        quick_select_layout = QHBoxLayout()
        btn_select_all = QPushButton("Select All")
        btn_select_all.clicked.connect(self._select_all_classes)
        btn_select_none = QPushButton("Select None")
        btn_select_none.clicked.connect(self._select_no_classes)
        btn_reset_default = QPushButton("Reset to Default (Bicycle)")
        btn_reset_default.clicked.connect(self._reset_to_default)
        quick_select_layout.addWidget(btn_select_all)
        quick_select_layout.addWidget(btn_select_none)
        quick_select_layout.addWidget(btn_reset_default)
        quick_select_layout.addStretch()
        layout.addLayout(quick_select_layout)

        group_box = QGroupBox("Detection Classes")
        checkbox_layout = QGridLayout()
        all_classes = list(CFG.YOLO_CLASS_MAP.keys())
        for idx, class_name in enumerate(all_classes):
            row = idx // 2
            col = idx % 2
            checkbox = QCheckBox(class_name.title())
            self.class_checkboxes[class_name] = checkbox
            checkbox_layout.addWidget(checkbox, row, col)
        group_box.setLayout(checkbox_layout)
        layout.addWidget(group_box)

        self.selected_count_label = QLabel("Selected: 0 classes")
        self.selected_count_label.setStyleSheet("font-size: 12px; font-weight: 600; color: #2D7A4F; padding: 10px;")
        layout.addWidget(self.selected_count_label)
        layout.addStretch()

        for checkbox in self.class_checkboxes.values():
            checkbox.stateChanged.connect(self._update_selected_count)

        return tab

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

    def _create_core_settings(self):
        # Sampling interval in seconds (time-based sampling, replaces Extract FPS)
        self._add_spinbox(
            self.core_form,
            "Sampling Interval (s)",
            "EXTRACT_INTERVAL_SECONDS",
            int(CFG.EXTRACT_INTERVAL_SECONDS),
            1,
            60,
        )
        self._add_doublespinbox(
            self.core_form,
            "Target Duration (s)",
            "HIGHLIGHT_TARGET_DURATION_S",
            CFG.HIGHLIGHT_TARGET_DURATION_S,
            30,
            600,
            30
        )
        self._add_doublespinbox(
            self.core_form,
            "Clip Pre-Roll (s)",
            "CLIP_PRE_ROLL_S",
            CFG.CLIP_PRE_ROLL_S,
            0,
            2,
            0.1
        )
        self._add_doublespinbox(
            self.core_form,
            "Clip Duration (s)",
            "CLIP_OUT_LEN_S",
            CFG.CLIP_OUT_LEN_S,
            1,
            10,
            0.1
        )
        self._add_doublespinbox(
            self.core_form,
            "Min Gap Between Clips (s)",
            "MIN_GAP_BETWEEN_CLIPS",
            CFG.MIN_GAP_BETWEEN_CLIPS,
            30,
            300,
            10
        )
        self._add_doublespinbox(
            self.core_form,
            "Scene Comparison Window (s)",
            "SCENE_COMPARISON_WINDOW_S",
            CFG.SCENE_COMPARISON_WINDOW_S,
            1.0,
            15.0,
            0.5
        )
        self._add_doublespinbox(
            self.core_form,
            "Start Zone Duration (s)",
            "START_ZONE_DURATION_S",
            CFG.START_ZONE_DURATION_S,
            0,
            1800,
            60
        )
        self._add_doublespinbox(
            self.core_form,
            "Max Start Zone Fraction",
            "MAX_START_ZONE_FRAC",
            CFG.MAX_START_ZONE_FRAC,
            0,
            1,
            0.05
        )
        self._add_doublespinbox(
            self.core_form,
            "End Zone Duration (s)",
            "END_ZONE_DURATION_S",
            CFG.END_ZONE_DURATION_S,
            0,
            1800,
            60
        )
        self._add_doublespinbox(
            self.core_form,
            "Max End Zone Fraction",
            "MAX_END_ZONE_FRAC",
            CFG.MAX_END_ZONE_FRAC,
            0,
            1,
            0.05
        )

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

    def _create_score_settings(self):
        """Create score weights settings tab."""
        description = QLabel(
            "Adjust relative weights used in scoring clips.\n"
            "Values should sum to ~1.0 for balanced scoring."
        )
        description.setWordWrap(True)
        description.setStyleSheet("font-size: 12px; color: #666; padding: 10px;")
        self.score_form.addRow(description)

        for key, val in CFG.SCORE_WEIGHTS.items():
            widget = _fix_size(QDoubleSpinBox())
            widget.setRange(0.0, 1.0)
            widget.setSingleStep(0.05)
            widget.setValue(val)
            self.score_form.addRow(key.replace("_", " ").title(), widget)
            self.overrides[f"SCORE_WEIGHTS.{key}"] = widget

    def _create_paths_settings(self):
        description = QLabel(
            "Configure where projects and source videos are stored.\n"
            "These settings persist across sessions."
        )
        description.setWordWrap(True)
        description.setStyleSheet("font-size: 12px; color: #666; padding: 10px;")
        self.paths_form.addRow(description)

        # Projects Root Path
        projects_layout = QHBoxLayout()
        self.projects_root_edit = QLineEdit(str(CFG.PROJECTS_ROOT))
        self.projects_root_edit.setMinimumWidth(400)
        self.projects_root_edit.setReadOnly(True)
        projects_browse_btn = QPushButton("Browse...")
        projects_browse_btn.clicked.connect(self._browse_projects_root)
        projects_layout.addWidget(self.projects_root_edit)
        projects_layout.addWidget(projects_browse_btn)
        self.paths_form.addRow("Projects Output Folder:", projects_layout)

        # Input Base Dir Path
        input_layout = QHBoxLayout()
        self.input_base_edit = QLineEdit(str(CFG.INPUT_BASE_DIR))
        self.input_base_edit.setMinimumWidth(400)
        self.input_base_edit.setReadOnly(True)
        input_browse_btn = QPushButton("Browse...")
        input_browse_btn.clicked.connect(self._browse_input_base)
        input_layout.addWidget(self.input_base_edit)
        input_layout.addWidget(input_browse_btn)
        self.paths_form.addRow("Source Videos Folder:", input_layout)

        help_text = QLabel(
            "<b>Projects Output:</b> Where all generated content is stored<br>"
            "<b>Source Videos:</b> Where your raw MP4 and GPX files are located"
        )
        help_text.setWordWrap(True)
        help_text.setStyleSheet("font-size: 11px; color: #888; padding: 10px;")
        self.paths_form.addRow(help_text)

        reset_layout = QHBoxLayout()
        reset_btn = QPushButton("Reset All Preferences to Defaults")
        reset_btn.clicked.connect(self._reset_all_preferences)
        reset_layout.addStretch()
        reset_layout.addWidget(reset_btn)
        reset_layout.addStretch()
        self.paths_form.addRow("", reset_layout)

    def _browse_projects_root(self):
        current = self.projects_root_edit.text()
        folder = QFileDialog.getExistingDirectory(self, "Select Projects Output Folder", current)
        if folder:
            self.projects_root_edit.setText(folder)

    def _browse_input_base(self):
        current = self.input_base_edit.text()
        folder = QFileDialog.getExistingDirectory(self, "Select Source Videos Folder", current)
        if folder:
            self.input_base_edit.setText(folder)

    def _reset_all_preferences(self):
        reply = QMessageBox.question(
            self,
            "Reset All Preferences",
            "This will reset ALL preferences to their default values.\n\n"
            "This action cannot be undone. Continue?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )
        if reply == QMessageBox.Yes:
            clear_persistent_config()
            QMessageBox.information(
                self,
                "Preferences Reset",
                "All preferences have been reset to defaults.\n\n"
                "Please restart the application for changes to take effect."
            )
            self.reject()

    # --- YOLO helper methods (restored) ---
    def _select_all_classes(self):
        for checkbox in self.class_checkboxes.values():
            checkbox.setChecked(True)

    def _select_no_classes(self):
        for checkbox in self.class_checkboxes.values():
            checkbox.setChecked(False)

    def _reset_to_default(self):
        for class_name, checkbox in self.class_checkboxes.items():
            checkbox.setChecked(class_name == "bicycle")

    def _update_selected_count(self):
        count = sum(1 for cb in self.class_checkboxes.values() if cb.isChecked())
        self.selected_count_label.setText(f"Selected: {count} class{'es' if count != 1 else ''}")

    def load_current_values(self):
        cfg = CFG
        for attr, widget in self.overrides.items():
            if attr.startswith("SCORE_WEIGHTS."):
                key = attr.split(".", 1)[1]
                val = CFG.SCORE_WEIGHTS.get(key, 0.0)
                widget.setValue(float(val))
                continue

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

        current_ids = getattr(cfg, 'YOLO_DETECT_CLASSES', [1])
        for class_name, class_id in CFG.YOLO_CLASS_MAP.items():
            if class_name in self.class_checkboxes:
                self.class_checkboxes[class_name].setChecked(class_id in current_ids)
        self._update_selected_count()

    def get_overrides(self) -> Dict[str, Any]:
        overrides: Dict[str, Any] = {}
        for attr, widget in self.overrides.items():
            if isinstance(widget, QLineEdit):
                overrides[attr] = widget.text().strip()
            elif isinstance(widget, QSpinBox):
                overrides[attr] = widget.value()
            elif isinstance(widget, QDoubleSpinBox):
                overrides[attr] = widget.value()
            elif isinstance(widget, QCheckBox):
                overrides[attr] = widget.isChecked()

        selected_ids = [
            CFG.YOLO_CLASS_MAP[class_name]
            for class_name, checkbox in self.class_checkboxes.items()
            if checkbox.isChecked()
        ]
        overrides['YOLO_DETECT_CLASSES'] = selected_ids

        # Only persist the two root paths
        overrides['PROJECTS_ROOT'] = Path(self.projects_root_edit.text())
        overrides['INPUT_BASE_DIR'] = Path(self.input_base_edit.text())

        # Collect score weights
        score_weights = {}
        for attr, widget in self.overrides.items():
            if attr.startswith("SCORE_WEIGHTS."):
                key = attr.split(".", 1)[1]
                score_weights[key] = widget.value()
        overrides['SCORE_WEIGHTS'] = score_weights

        save_persistent_config(overrides)
        return overrides
