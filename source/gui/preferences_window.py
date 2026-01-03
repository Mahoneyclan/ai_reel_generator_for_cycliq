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
    QGroupBox, QComboBox
)

from ..utils.persistent_config import save_persistent_config
from ..config import DEFAULT_CONFIG as CFG, DEFAULT_YOLO_CLASS_WEIGHTS


FIELD_MIN_WIDTH = 220  # baseline width for all input widgets


def _fix_size(widget):
    """Apply consistent sizing policy to all input widgets."""
    widget.setMinimumWidth(FIELD_MIN_WIDTH)
    widget.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
    return widget


class PreferencesWindow(QDialog):
    # Tooltips describing effect of changing each preference key
    PREFERENCE_TOOLTIPS = {
        'KNOWN_OFFSETS': 'Seconds to add to video duration when calculating recording start time. '
                         'Different cameras record creation_time at different points relative to recording end.',
        'MIN_DETECT_SCORE': 'Minimum detection score required to consider an object detection valid.',
        'GPX_TOLERANCE': 'Allowed time tolerance (seconds) when aligning GPX timestamps to video frames.',
        'EXTRACT_INTERVAL_SECONDS': 'Interval in seconds between sampled frames used for analysis.'
    }
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Preferences")
        self.setMinimumSize(700, 600)
        self.setModal(True)

        self.overrides: Dict[str, Any] = {}
        self.class_checkboxes: Dict[str, QCheckBox] = {}
        self.class_weights_spinboxes: Dict[str, QDoubleSpinBox] = {}

        layout = QVBoxLayout(self)

        self.tabs = QTabWidget()
        layout.addWidget(self.tabs)

        # Tabs with form layouts (project-specific settings only)
        self.core_tab, self.core_form = self._make_tab("Core")
        self.score_tab, self.score_form = self._make_tab("Score Weights")
        self.yolo_tab = self._make_yolo_tab("Detection Classes")
        self.audio_tab, self.audio_form = self._make_tab("Audio")

        # Populate tabs
        self._create_core_settings()
        self._create_score_settings()
        self._create_audio_settings()

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
        for form in (self.audio_form, self.core_form, self.score_form):
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
            "Select which object classes to detect and adjust their scoring weights.\n"
            "Higher weights make a class more likely to be selected for a highlight clip."
        )
        description.setWordWrap(True)
        description.setStyleSheet("font-size: 12px; color: #666; padding: 10px;")
        layout.addWidget(description)

        quick_select_layout = QHBoxLayout()
        btn_select_all = QPushButton("Select All")
        btn_select_all.clicked.connect(self._select_all_classes)
        btn_select_none = QPushButton("Select None")
        btn_select_none.clicked.connect(self._select_no_classes)
        btn_reset_default = QPushButton("Reset to Default")
        btn_reset_default.clicked.connect(self._reset_to_default)
        quick_select_layout.addWidget(btn_select_all)
        quick_select_layout.addWidget(btn_select_none)
        quick_select_layout.addWidget(btn_reset_default)
        quick_select_layout.addStretch()
        layout.addLayout(quick_select_layout)

        group_box = QGroupBox("Detection Classes and Weights")
        grid_layout = QGridLayout()
        grid_layout.setColumnStretch(0, 1) # Class name
        grid_layout.setColumnStretch(1, 0) # Enabled
        grid_layout.setColumnStretch(2, 0) # Weight

        # Header
        grid_layout.addWidget(QLabel("<b>Class</b>"), 0, 0)
        grid_layout.addWidget(QLabel("<b>Enabled</b>"), 0, 1, Qt.AlignCenter)
        grid_layout.addWidget(QLabel("<b>Weight</b>"), 0, 2, Qt.AlignCenter)

        all_classes = sorted(list(CFG.YOLO_CLASS_MAP.keys()))
        for idx, class_name in enumerate(all_classes):
            row = idx + 1
            
            # Class Name Label
            label = QLabel(class_name.title())
            
            # Enabled CheckBox
            checkbox = QCheckBox()
            checkbox.stateChanged.connect(self._update_selected_count)
            self.class_checkboxes[class_name] = checkbox
            
            # Weight SpinBox
            spinbox = QDoubleSpinBox()
            spinbox.setRange(0.0, 10.0)
            spinbox.setSingleStep(0.5)
            spinbox.setDecimals(1)
            self.class_weights_spinboxes[class_name] = spinbox

            grid_layout.addWidget(label, row, 0)
            grid_layout.addWidget(checkbox, row, 1, Qt.AlignCenter)
            grid_layout.addWidget(spinbox, row, 2)

        group_box.setLayout(grid_layout)
        layout.addWidget(group_box)

        self.selected_count_label = QLabel("Selected: 0 classes")
        self.selected_count_label.setStyleSheet("font-size: 12px; font-weight: 600; color: #2D7A4F; padding: 10px;")
        layout.addWidget(self.selected_count_label)
        layout.addStretch()

        return tab

    def _add_spinbox(self, form, label, attr, value, min_val, max_val):
        widget = _fix_size(QSpinBox())
        widget.setRange(min_val, max_val)
        widget.setValue(value)
        tip = self.PREFERENCE_TOOLTIPS.get(attr, '')
        if tip:
            widget.setToolTip(tip)
        form.addRow(label, widget)
        self.overrides[attr] = widget

    def _add_doublespinbox(self, form, label, attr, value, min_val, max_val, step):
        widget = _fix_size(QDoubleSpinBox())
        widget.setRange(min_val, max_val)
        widget.setSingleStep(step)
        widget.setValue(value)
        tip = self.PREFERENCE_TOOLTIPS.get(attr, '')
        if tip:
            widget.setToolTip(tip)
        form.addRow(label, widget)
        self.overrides[attr] = widget

    def _create_audio_settings(self):
        """Create audio/music selection UI."""
        title = QLabel("Background Music")
        title.setStyleSheet("font-weight: 700; margin-bottom: 6px;")
        self.audio_form.addRow(title)

        description = QLabel(
            "Select a music track for the highlight reel.\n"
            "Tracks are loaded from the assets/music folder."
        )
        description.setWordWrap(True)
        description.setStyleSheet("font-size: 11px; color: #666; padding: 2px 0 10px 0;")
        self.audio_form.addRow(description)

        # Music track combo box
        self.music_combo = _fix_size(QComboBox())
        self.music_combo.setToolTip("Select a music track or use random selection")
        self._populate_music_tracks()
        self.audio_form.addRow("Music Track:", self.music_combo)

        # Refresh button
        refresh_btn = QPushButton("🔄 Refresh")
        refresh_btn.setToolTip("Reload music tracks from assets/music folder")
        refresh_btn.clicked.connect(self._populate_music_tracks)
        self.audio_form.addRow("", refresh_btn)

    def _populate_music_tracks(self):
        """Populate combo box with available music tracks."""
        self.music_combo.clear()
        self.music_combo.addItem("🎲 Random", "")  # Empty string = random

        music_dir = CFG.PROJECT_ROOT / "assets" / "music"
        if music_dir.exists():
            extensions = [".mp3", ".wav", ".m4a", ".aac", ".flac"]
            tracks = []
            for ext in extensions:
                tracks.extend(music_dir.glob(f"*{ext}"))
                tracks.extend(music_dir.glob(f"*{ext.upper()}"))
            tracks = sorted(set(tracks))

            for track in tracks:
                self.music_combo.addItem(f"🎵 {track.stem}", str(track))

    def _create_core_settings(self):
        self._add_spinbox(self.core_form, "Sampling Interval (s)", "EXTRACT_INTERVAL_SECONDS", int(CFG.EXTRACT_INTERVAL_SECONDS), 1, 60)
        self._add_doublespinbox(self.core_form, "Target Duration (s)", "HIGHLIGHT_TARGET_DURATION_S", CFG.HIGHLIGHT_TARGET_DURATION_S, 30, 600, 30)
        self._add_doublespinbox(self.core_form, "Clip Pre-Roll (s)", "CLIP_PRE_ROLL_S", CFG.CLIP_PRE_ROLL_S, 0, 2, 0.1)
        self._add_doublespinbox(self.core_form, "Clip Duration (s)", "CLIP_OUT_LEN_S", CFG.CLIP_OUT_LEN_S, 1, 10, 0.1)
        self._add_doublespinbox(self.core_form, "Min Gap Between Clips (s)", "MIN_GAP_BETWEEN_CLIPS", CFG.MIN_GAP_BETWEEN_CLIPS, 30, 300, 10)
        self._add_doublespinbox(self.core_form, "Scene Comparison Window (s)", "SCENE_COMPARISON_WINDOW_S", CFG.SCENE_COMPARISON_WINDOW_S, 1.0, 15.0, 0.5)
        self._add_doublespinbox(self.core_form, "Start Zone Duration (s)", "START_ZONE_DURATION_S", CFG.START_ZONE_DURATION_S, 0, 1800, 60)
        self._add_doublespinbox(self.core_form, "Max Start Zone Fraction", "MAX_START_ZONE_FRAC", CFG.MAX_START_ZONE_FRAC, 0, 1, 0.05)
        self._add_doublespinbox(self.core_form, "End Zone Duration (s)", "END_ZONE_DURATION_S", CFG.END_ZONE_DURATION_S, 0, 1800, 60)
        self._add_doublespinbox(self.core_form, "Max End Zone Fraction", "MAX_END_ZONE_FRAC", CFG.MAX_END_ZONE_FRAC, 0, 1, 0.05)
        self._add_doublespinbox(self.core_form, "GPX Tolerance (s)", "GPX_TOLERANCE", CFG.GPX_TOLERANCE, 0, 10, 0.5)

    def _create_score_settings(self):
        description = QLabel("Adjust relative weights used in scoring clips.\nValues should sum to ~1.0 for balanced scoring.")
        description.setWordWrap(True)
        description.setStyleSheet("font-size: 12px; color: #666; padding: 10px;")
        self.score_form.addRow(description)
        for key, val in CFG.SCORE_WEIGHTS.items():
            widget = _fix_size(QDoubleSpinBox())
            widget.setRange(0.0, 1.0)
            widget.setSingleStep(0.05)
            widget.setValue(val)
            widget.valueChanged.connect(self._update_score_total)
            self.score_form.addRow(key.replace("_", " ").title(), widget)
            self.overrides[f"SCORE_WEIGHTS.{key}"] = widget
        self.score_total_label = QLabel("")
        self.score_total_label.setStyleSheet("font-weight: 700; padding-top: 8px;")
        self.score_form.addRow("Total:", self.score_total_label)
        self._update_score_total()

    def _select_all_classes(self):
        for checkbox in self.class_checkboxes.values():
            checkbox.setChecked(True)

    def _select_no_classes(self):
        for checkbox in self.class_checkboxes.values():
            checkbox.setChecked(False)

    def _reset_to_default(self):
        default_classes = ["bicycle"]
        for class_name, checkbox in self.class_checkboxes.items():
            checkbox.setChecked(class_name in default_classes)
        
        for class_name, spinbox in self.class_weights_spinboxes.items():
            spinbox.setValue(DEFAULT_YOLO_CLASS_WEIGHTS.get(class_name, 1.0))

    def _update_selected_count(self):
        count = sum(1 for cb in self.class_checkboxes.values() if cb.isChecked())
        self.selected_count_label.setText(f"Selected: {count} class{'es' if count != 1 else ''}")

    def _update_score_total(self):
        total = 0.0
        for attr, widget in self.overrides.items():
            if attr.startswith("SCORE_WEIGHTS."):
                try:
                    total += float(widget.value())
                except (ValueError, AttributeError):
                    # Widget may not have value() or value may not be numeric
                    pass
        pct = total * 100.0
        text = f"{pct:.1f}%"
        if abs(total - 1.0) <= 0.01:
            css = "color: #1E8E3E; font-weight: 700;"
        else:
            css = "color: #C62828; font-weight: 700;"
        if hasattr(self, 'score_total_label'):
            self.score_total_label.setText(text)
            self.score_total_label.setStyleSheet(css)

    def load_current_values(self):
        cfg = CFG
        for attr, widget in self.overrides.items():
            if attr.startswith("SCORE_WEIGHTS."):
                key = attr.split(".", 1)[1]
                val = CFG.SCORE_WEIGHTS.get(key, 0.0)
                widget.setValue(float(val))
                continue
            val = getattr(cfg, attr, None)
            if val is None: continue
            if isinstance(widget, QLineEdit): widget.setText(str(val))
            elif isinstance(widget, QSpinBox): widget.setValue(int(val))
            elif isinstance(widget, QDoubleSpinBox): widget.setValue(float(val))
            elif isinstance(widget, QCheckBox): widget.setChecked(bool(val))

        current_ids = getattr(cfg, 'YOLO_DETECT_CLASSES', [1])
        for class_name, class_id in CFG.YOLO_CLASS_MAP.items():
            if class_name in self.class_checkboxes:
                self.class_checkboxes[class_name].setChecked(class_id in current_ids)
        
        current_weights = getattr(cfg, 'YOLO_CLASS_WEIGHTS', {})
        for class_name, spinbox in self.class_weights_spinboxes.items():
            spinbox.setValue(current_weights.get(class_name, 1.0))

        # Load selected music track
        selected_track = getattr(cfg, 'SELECTED_MUSIC_TRACK', "")
        if selected_track:
            # Find the track in combo box
            for i in range(self.music_combo.count()):
                if self.music_combo.itemData(i) == selected_track:
                    self.music_combo.setCurrentIndex(i)
                    break

        self._update_selected_count()

    def get_overrides(self) -> Dict[str, Any]:
        overrides: Dict[str, Any] = {}
        for attr, widget in self.overrides.items():
            if isinstance(widget, QLineEdit): overrides[attr] = widget.text().strip()
            elif isinstance(widget, QSpinBox): overrides[attr] = widget.value()
            elif isinstance(widget, QDoubleSpinBox): overrides[attr] = widget.value()
            elif isinstance(widget, QCheckBox): overrides[attr] = widget.isChecked()

        selected_ids = [CFG.YOLO_CLASS_MAP[class_name] for class_name, checkbox in self.class_checkboxes.items() if checkbox.isChecked()]
        overrides['YOLO_DETECT_CLASSES'] = selected_ids

        yolo_weights = {class_name: spinbox.value() for class_name, spinbox in self.class_weights_spinboxes.items()}
        overrides['YOLO_CLASS_WEIGHTS'] = yolo_weights

        # Music track selection (empty string = random)
        selected_track = self.music_combo.currentData()
        overrides['SELECTED_MUSIC_TRACK'] = selected_track if selected_track else ""

        overrides['PROJECTS_ROOT'] = Path(getattr(CFG, 'PROJECTS_ROOT', CFG.PROJECTS_ROOT))
        overrides['INPUT_BASE_DIR'] = Path(getattr(CFG, 'INPUT_BASE_DIR', CFG.INPUT_BASE_DIR))

        score_weights = {}
        for attr, widget in self.overrides.items():
            if attr.startswith("SCORE_WEIGHTS."):
                key = attr.split(".", 1)[1]
                score_weights[key] = widget.value()
        overrides['SCORE_WEIGHTS'] = score_weights

        save_persistent_config(overrides)
        return overrides
