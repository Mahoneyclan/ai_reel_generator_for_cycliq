# source/gui/general_settings_window.py
"""
General settings dialog: Paths, M1 Performance, Video Settings.
Separated from the ride-specific `PreferencesWindow`.
Organized as 3 tabs: Paths, Video Settings, M1 Settings.
"""

from __future__ import annotations
from typing import Dict, Any
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QTabWidget, QWidget, QFormLayout, QLineEdit, QSpinBox, QDoubleSpinBox,
    QCheckBox, QPushButton, QHBoxLayout, QLabel, QSizePolicy, QFileDialog, QMessageBox
)

from ..utils.persistent_config import save_persistent_config, load_persistent_config, clear_persistent_config
from ..config import DEFAULT_CONFIG as CFG

FIELD_MIN_WIDTH = 220

def _fix_size(widget):
    widget.setMinimumWidth(FIELD_MIN_WIDTH)
    widget.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
    return widget


class GeneralSettingsWindow(QDialog):
    """Dialog for program-wide (general) settings.

    Contains:
    - Paths: Projects output, Source videos
    - Video Settings: codec, bitrate, buffers, volumes, PiP/minimap
    - M1 Settings: USE_MPS, YOLO_BATCH_SIZE, FFMPEG_HWACCEL
    - Camera Offsets: creation_time offsets per camera model
    - Detection: YOLO confidence, image size, min detect score
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("General Settings")
        self.setMinimumSize(700, 500)
        self.setModal(True)

        self.overrides: Dict[str, Any] = {}
        self.known_offsets_spinboxes: Dict[str, QDoubleSpinBox] = {}

        layout = QVBoxLayout(self)

        # Create tabbed interface
        self.tabs = QTabWidget()
        layout.addWidget(self.tabs)

        # Create tabs
        self.paths_tab, self.paths_form = self._make_tab("Paths")
        self.video_tab, self.video_form = self._make_tab("Video Settings")
        self.m1_tab, self.m1_form = self._make_tab("M1 Settings")
        self.camera_tab, self.camera_form = self._make_tab("Camera Offsets")
        self.detect_tab, self.detect_form = self._make_tab("Detection")

        # Populate tabs
        self._create_paths_section()
        self._create_video_section()
        self._create_m1_section()
        self._create_camera_offsets_section()
        self._create_detection_section()

        # Buttons
        btn_layout = QHBoxLayout()
        save_btn = QPushButton("Save")
        save_btn.clicked.connect(self._on_save)
        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        btn_layout.addStretch()
        btn_layout.addWidget(cancel_btn)
        btn_layout.addWidget(save_btn)
        layout.addLayout(btn_layout)

        # Load values
        self.load_current_values()

        # Styling
        for form in (self.paths_form, self.video_form, self.m1_form, self.camera_form, self.detect_form):
            form.setLabelAlignment(Qt.AlignRight | Qt.AlignVCenter)
            form.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow)
            form.setSpacing(8)

        # Tooltips for general settings
        self.GENERAL_TOOLTIPS = {
            'PROJECTS_ROOT': 'Folder where generated projects and working files are stored.',
            'INPUT_BASE_DIR': 'Base folder containing raw source videos used for imports.',
            'VIDEO_CODEC': 'FFmpeg codec used for final MP4 encoding (e.g. libx264).',
            'BITRATE': 'Target video bitrate for output (e.g. 8M).',
            'MAXRATE': 'Maximum video bitrate for encoding.',
            'BUFSIZE': 'FFmpeg buffer size for rate control.',
            'MUSIC_VOLUME': 'Background music volume in final video (0.0-1.0).',
            'RAW_AUDIO_VOLUME': 'Original ride audio volume in final video (0.0-1.0).',
            'USE_MPS': 'Enable Apple MPS (GPU) acceleration where available.',
            'YOLO_BATCH_SIZE': 'YOLO inference batch size (higher = more RAM).',
            'FFMPEG_HWACCEL': 'Hardware acceleration option for FFmpeg.',
        }

    def _make_tab(self, name: str):
        """Create a new tab with form layout."""
        tab = QWidget()
        form = QFormLayout(tab)
        self.tabs.addTab(tab, name)
        return tab, form

    # --- Sections ---
    def _create_paths_section(self):
        title = QLabel("Paths")
        title.setStyleSheet("font-weight: 700; margin-bottom: 6px;")
        self.paths_form.addRow(title)

        projects_layout = QHBoxLayout()
        self.projects_root_edit = _fix_size(QLineEdit(str(CFG.PROJECTS_ROOT)))
        self.projects_root_edit.setReadOnly(True)
        projects_browse_btn = QPushButton("Browse...")
        projects_browse_btn.clicked.connect(self._browse_projects_root)
        projects_layout.addWidget(self.projects_root_edit)
        projects_layout.addWidget(projects_browse_btn)
        self.paths_form.addRow("Projects Output Folder:", projects_layout)
        try:
            self.projects_root_edit.setToolTip(self.GENERAL_TOOLTIPS.get('PROJECTS_ROOT',''))
        except Exception:
            pass

        input_layout = QHBoxLayout()
        self.input_base_edit = _fix_size(QLineEdit(str(CFG.INPUT_BASE_DIR)))
        self.input_base_edit.setReadOnly(True)
        input_browse_btn = QPushButton("Browse...")
        input_browse_btn.clicked.connect(self._browse_input_base)
        input_layout.addWidget(self.input_base_edit)
        input_layout.addWidget(input_browse_btn)
        self.paths_form.addRow("Source Videos Folder:", input_layout)
        try:
            self.input_base_edit.setToolTip(self.GENERAL_TOOLTIPS.get('INPUT_BASE_DIR',''))
        except Exception:
            pass

        help_text = QLabel(
            "<b>Projects Output:</b> Where generated content is stored<br>"
            "<b>Source Videos:</b> Where raw MP4 and GPX files are located"
        )
        help_text.setWordWrap(True)
        help_text.setStyleSheet("font-size: 11px; color: #888; padding: 6px 0;")
        self.paths_form.addRow(help_text)

    def _create_video_section(self):
        title = QLabel("Video Settings")
        title.setStyleSheet("font-weight: 700; margin: 12px 0 6px 0;")
        self.video_form.addRow(title)

        self.video_codec = _fix_size(QLineEdit(str(CFG.VIDEO_CODEC)))
        self.video_form.addRow("Video Codec", self.video_codec)
        try:
            self.video_codec.setToolTip(self.GENERAL_TOOLTIPS.get('VIDEO_CODEC',''))
        except Exception:
            pass
        self.video_bitrate = _fix_size(QLineEdit(str(CFG.BITRATE)))
        self.video_form.addRow("Bitrate", self.video_bitrate)
        try:
            self.video_bitrate.setToolTip(self.GENERAL_TOOLTIPS.get('BITRATE',''))
        except Exception:
            pass
        self.video_maxrate = _fix_size(QLineEdit(str(CFG.MAXRATE)))
        self.video_form.addRow("Max Rate", self.video_maxrate)
        try:
            self.video_maxrate.setToolTip(self.GENERAL_TOOLTIPS.get('MAXRATE',''))
        except Exception:
            pass
        self.video_bufsize = _fix_size(QLineEdit(str(CFG.BUFSIZE)))
        self.video_form.addRow("Buffer Size", self.video_bufsize)
        try:
            self.video_bufsize.setToolTip(self.GENERAL_TOOLTIPS.get('BUFSIZE',''))
        except Exception:
            pass

        self.music_volume = _fix_size(QDoubleSpinBox())
        self.music_volume.setRange(0.0, 1.0)
        self.music_volume.setSingleStep(0.05)
        self.music_volume.setValue(CFG.MUSIC_VOLUME)
        self.video_form.addRow("Music Volume", self.music_volume)
        try:
            self.music_volume.setToolTip(self.GENERAL_TOOLTIPS.get('MUSIC_VOLUME',''))
        except Exception:
            pass

        self.raw_audio_volume = _fix_size(QDoubleSpinBox())
        self.raw_audio_volume.setRange(0.0, 1.0)
        self.raw_audio_volume.setSingleStep(0.05)
        self.raw_audio_volume.setValue(CFG.RAW_AUDIO_VOLUME)
        self.video_form.addRow("Raw Audio Volume", self.raw_audio_volume)
        try:
            self.raw_audio_volume.setToolTip(self.GENERAL_TOOLTIPS.get('RAW_AUDIO_VOLUME',''))
        except Exception:
            pass

        self.pip_scale = _fix_size(QDoubleSpinBox())
        self.pip_scale.setRange(0.0, 1.0)
        self.pip_scale.setSingleStep(0.05)
        self.pip_scale.setValue(CFG.PIP_SCALE_RATIO)
        self.video_form.addRow("PiP Scale Ratio", self.pip_scale)

        self.pip_margin = _fix_size(QSpinBox())
        self.pip_margin.setRange(0, 200)
        self.pip_margin.setValue(CFG.PIP_MARGIN)
        self.video_form.addRow("PiP Margin", self.pip_margin)

        self.minimap_scale = _fix_size(QDoubleSpinBox())
        self.minimap_scale.setRange(0.0, 1.0)
        self.minimap_scale.setSingleStep(0.05)
        self.minimap_scale.setValue(CFG.MINIMAP_SCALE_RATIO)
        self.video_form.addRow("Minimap Scale Ratio", self.minimap_scale)

        self.minimap_margin = _fix_size(QSpinBox())
        self.minimap_margin.setRange(0, 200)
        self.minimap_margin.setValue(CFG.MINIMAP_MARGIN)
        self.video_form.addRow("Minimap Margin", self.minimap_margin)

    def _create_m1_section(self):
        title = QLabel("M1 Performance")
        title.setStyleSheet("font-weight: 700; margin: 12px 0 6px 0;")
        self.m1_form.addRow(title)

        self.use_mps = _fix_size(QCheckBox())
        self.use_mps.setChecked(CFG.USE_MPS)
        self.m1_form.addRow("Use M1 GPU (MPS)", self.use_mps)
        try:
            self.use_mps.setToolTip(self.GENERAL_TOOLTIPS.get('USE_MPS',''))
        except Exception:
            pass

        self.yolo_batch = _fix_size(QSpinBox())
        self.yolo_batch.setRange(1, 32)
        self.yolo_batch.setValue(CFG.YOLO_BATCH_SIZE)
        self.m1_form.addRow("YOLO Batch Size (RAM limit)", self.yolo_batch)
        try:
            self.yolo_batch.setToolTip(self.GENERAL_TOOLTIPS.get('YOLO_BATCH_SIZE',''))
        except Exception:
            pass

        self.ffmpeg_hw = _fix_size(QLineEdit(str(CFG.FFMPEG_HWACCEL)))
        self.m1_form.addRow("FFmpeg HW Accel", self.ffmpeg_hw)
        try:
            self.ffmpeg_hw.setToolTip(self.GENERAL_TOOLTIPS.get('FFMPEG_HWACCEL',''))
        except Exception:
            pass

    def _create_camera_offsets_section(self):
        """Camera creation_time offset settings."""
        title = QLabel("Camera & GPX Alignment")
        title.setStyleSheet("font-weight: 700; margin-bottom: 6px;")
        self.camera_form.addRow(title)

        description = QLabel(
            "Seconds added to video duration when calculating recording start time.\n"
            "Different cameras record creation_time at different points relative to recording end."
        )
        description.setWordWrap(True)
        description.setStyleSheet("font-size: 11px; color: #666; padding: 2px 0 10px 0;")
        self.camera_form.addRow(description)

        # Create spinbox for each known camera
        for camera_name, offset_val in CFG.KNOWN_OFFSETS.items():
            widget = _fix_size(QDoubleSpinBox())
            widget.setRange(-10.0, 10.0)
            widget.setSingleStep(0.5)
            widget.setDecimals(1)
            widget.setValue(float(offset_val))
            widget.setToolTip(f"Creation time offset for {camera_name} camera (seconds)")
            self.camera_form.addRow(f"{camera_name} Offset (s):", widget)
            self.known_offsets_spinboxes[camera_name] = widget

        # GPX tolerance
        self.gpx_tolerance = _fix_size(QDoubleSpinBox())
        self.gpx_tolerance.setRange(0, 10)
        self.gpx_tolerance.setSingleStep(0.5)
        self.gpx_tolerance.setValue(CFG.GPX_TOLERANCE)
        self.gpx_tolerance.setToolTip("Allowed time tolerance (seconds) when aligning GPX timestamps to video frames.")
        self.camera_form.addRow("GPX Tolerance (s):", self.gpx_tolerance)

    def _create_detection_section(self):
        """Detection and sampling settings."""
        title = QLabel("Detection & Sampling")
        title.setStyleSheet("font-weight: 700; margin-bottom: 6px;")
        self.detect_form.addRow(title)

        self.extract_interval = _fix_size(QSpinBox())
        self.extract_interval.setRange(1, 60)
        self.extract_interval.setValue(CFG.EXTRACT_INTERVAL_SECONDS)
        self.extract_interval.setToolTip("Interval in seconds between sampled frames for analysis.")
        self.detect_form.addRow("Sampling Interval (s):", self.extract_interval)

        self.yolo_min_conf = _fix_size(QDoubleSpinBox())
        self.yolo_min_conf.setRange(0, 1)
        self.yolo_min_conf.setSingleStep(0.05)
        self.yolo_min_conf.setValue(CFG.YOLO_MIN_CONFIDENCE)
        self.yolo_min_conf.setToolTip("YOLO minimum confidence threshold for detections.")
        self.detect_form.addRow("YOLO Min Confidence:", self.yolo_min_conf)

        self.yolo_image_size = _fix_size(QSpinBox())
        self.yolo_image_size.setRange(320, 1280)
        self.yolo_image_size.setValue(CFG.YOLO_IMAGE_SIZE)
        self.yolo_image_size.setToolTip("Image size for YOLO inference (larger = slower but more accurate).")
        self.detect_form.addRow("YOLO Image Size:", self.yolo_image_size)

    # --- Browse helpers ---
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

    # --- Load & Save ---
    def load_current_values(self):
        # Reload config to get fresh values (not stale module-level CFG)
        from ..config import reload_config, DEFAULT_CONFIG
        reload_config()
        cfg = DEFAULT_CONFIG
        self.projects_root_edit.setText(str(cfg.PROJECTS_ROOT))
        # If INPUT_BASE_DIR points at the project folder itself (its name == SOURCE_FOLDER),
        # prefer showing the parent directory as the raw videos base.
        display_base = cfg.INPUT_BASE_DIR
        try:
            if cfg.SOURCE_FOLDER and Path(cfg.INPUT_BASE_DIR).name == cfg.SOURCE_FOLDER:
                display_base = Path(cfg.INPUT_BASE_DIR).parent
        except Exception:
            display_base = cfg.INPUT_BASE_DIR

        self.input_base_edit.setText(str(display_base))

        self.video_codec.setText(str(cfg.VIDEO_CODEC))
        self.video_bitrate.setText(str(cfg.BITRATE))
        self.video_maxrate.setText(str(cfg.MAXRATE))
        self.video_bufsize.setText(str(cfg.BUFSIZE))

        self.music_volume.setValue(float(cfg.MUSIC_VOLUME))
        self.raw_audio_volume.setValue(float(cfg.RAW_AUDIO_VOLUME))
        self.pip_scale.setValue(float(cfg.PIP_SCALE_RATIO))
        self.pip_margin.setValue(int(cfg.PIP_MARGIN))
        self.minimap_scale.setValue(float(cfg.MINIMAP_SCALE_RATIO))
        self.minimap_margin.setValue(int(cfg.MINIMAP_MARGIN))

        self.use_mps.setChecked(bool(cfg.USE_MPS))
        self.yolo_batch.setValue(int(cfg.YOLO_BATCH_SIZE))
        self.ffmpeg_hw.setText(str(cfg.FFMPEG_HWACCEL))

        # Camera offsets
        current_offsets = getattr(cfg, 'KNOWN_OFFSETS', {})
        for camera_name, spinbox in self.known_offsets_spinboxes.items():
            spinbox.setValue(current_offsets.get(camera_name, 0.0))

        # Detection settings
        self.extract_interval.setValue(int(cfg.EXTRACT_INTERVAL_SECONDS))
        self.gpx_tolerance.setValue(float(cfg.GPX_TOLERANCE))
        self.yolo_min_conf.setValue(float(cfg.YOLO_MIN_CONFIDENCE))
        self.yolo_image_size.setValue(int(cfg.YOLO_IMAGE_SIZE))

    def _collect_overrides(self) -> Dict[str, Any]:
        overrides: Dict[str, Any] = {}
        overrides['PROJECTS_ROOT'] = Path(self.projects_root_edit.text())
        overrides['INPUT_BASE_DIR'] = Path(self.input_base_edit.text())

        overrides['VIDEO_CODEC'] = self.video_codec.text().strip()
        overrides['BITRATE'] = self.video_bitrate.text().strip()
        overrides['MAXRATE'] = self.video_maxrate.text().strip()
        overrides['BUFSIZE'] = self.video_bufsize.text().strip()
        overrides['MUSIC_VOLUME'] = float(self.music_volume.value())
        overrides['RAW_AUDIO_VOLUME'] = float(self.raw_audio_volume.value())
        overrides['PIP_SCALE_RATIO'] = float(self.pip_scale.value())
        overrides['PIP_MARGIN'] = int(self.pip_margin.value())
        overrides['MINIMAP_SCALE_RATIO'] = float(self.minimap_scale.value())
        overrides['MINIMAP_MARGIN'] = int(self.minimap_margin.value())

        overrides['USE_MPS'] = bool(self.use_mps.isChecked())
        overrides['YOLO_BATCH_SIZE'] = int(self.yolo_batch.value())
        overrides['FFMPEG_HWACCEL'] = self.ffmpeg_hw.text().strip()

        # Camera offsets
        known_offsets = {camera_name: spinbox.value() for camera_name, spinbox in self.known_offsets_spinboxes.items()}
        overrides['KNOWN_OFFSETS'] = known_offsets

        # Detection settings
        overrides['EXTRACT_INTERVAL_SECONDS'] = int(self.extract_interval.value())
        overrides['GPX_TOLERANCE'] = float(self.gpx_tolerance.value())
        overrides['YOLO_MIN_CONFIDENCE'] = float(self.yolo_min_conf.value())
        overrides['YOLO_IMAGE_SIZE'] = int(self.yolo_image_size.value())

        return overrides

    def _on_save(self):
        overrides = self._collect_overrides()
        save_persistent_config(overrides)

        # Reload config so changes take effect immediately without restart
        from ..utils.persistent_config import reload_all_config
        reload_all_config()

        QMessageBox.information(self, "Saved", "General settings saved.")
        self.accept()

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
