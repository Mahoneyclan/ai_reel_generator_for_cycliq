# source/gui/camera_offset_window.py
"""
Camera Offset Calibration Window for adjusting KNOWN_OFFSETS.

Allows visual comparison of:
- Burnt-in timestamp (visible in first frame)
- Raw metadata creation_time
- Calculated recording start time

Users can adjust per-camera offsets and save to config.
"""

from __future__ import annotations
import csv
import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QScrollArea, QWidget, QGridLayout, QMessageBox, QFrame,
    QDoubleSpinBox, QGroupBox, QSplitter, QComboBox
)
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QPixmap

from source.config import DEFAULT_CONFIG as CFG
from source.io_paths import flatten_path, _mk
from source.utils.log import setup_logger
from source.utils.video_utils import (
    probe_video_metadata,
    fix_cycliq_utc_bug,
    extract_frame_safe,
)
from source.models import get_registry, reset_registry

log = setup_logger("gui.camera_offset_window")


class CameraOffsetWindow(QDialog):
    """
    Camera Offset Calibration Window.

    Shows first frame from each video clip grouped by camera,
    with metadata comparison and offset adjustment controls.
    """

    offsets_changed = Signal(dict)  # Emits new offsets when saved

    def __init__(self, project_dir: Path, parent=None):
        super().__init__(parent)
        self.project_dir = project_dir
        self.thumbnail_dir = _mk(CFG.CALIBRATION_FRAMES_DIR)

        # Current offset values - load from project_config.json if exists, else from default config
        self.offsets: Dict[str, float] = self._load_saved_offsets()

        # Current timezone - load from project_config.json if exists
        self.current_timezone: str = self._load_saved_timezone()

        # Clip data grouped by camera
        self.clips_by_camera: Dict[str, List[Dict]] = {}

        # UI references for updating
        self.time_labels: Dict[str, List[QLabel]] = {}  # camera -> [labels]
        self.spinboxes: Dict[str, QDoubleSpinBox] = {}
        self.timezone_combo: QComboBox = None

        self.setWindowTitle("Camera Offset Calibration")
        self.resize(1400, 900)
        self.setModal(True)

        self._setup_ui()
        self._load_clips()

    # --------------------------------------------------
    # Logging helper
    # --------------------------------------------------

    def log(self, message: str, level: str = "info"):
        """Route messages to parent GUI log panel or fallback to file logger."""
        if self.parent() and hasattr(self.parent(), "log"):
            self.parent().log(message, level)
        else:
            level_map = {
                "debug": logging.DEBUG,
                "info": logging.INFO,
                "warning": logging.WARNING,
                "error": logging.ERROR,
                "success": logging.INFO,
            }
            log.log(level_map.get(level, logging.INFO), message)

    # --------------------------------------------------
    # UI setup
    # --------------------------------------------------

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(5, 5, 5, 5)
        layout.setSpacing(4)

        # Timezone selector at top
        tz_layout = QHBoxLayout()
        tz_layout.setSpacing(8)
        tz_label = QLabel("Ride Timezone:")
        tz_label.setStyleSheet("font-weight: 600; font-size: 12px;")

        self.timezone_combo = QComboBox()
        self.timezone_combo.setFixedWidth(200)
        self._populate_timezone_options()
        self.timezone_combo.currentTextChanged.connect(self._on_timezone_changed)

        tz_help = QLabel("(Where the ride took place)")
        tz_help.setStyleSheet("color: #666; font-size: 11px;")

        tz_layout.addWidget(tz_label)
        tz_layout.addWidget(self.timezone_combo)
        tz_layout.addWidget(tz_help)
        tz_layout.addStretch()
        layout.addLayout(tz_layout)

        # Splitter for two camera columns (no header - title is in window titlebar)
        splitter = QSplitter(Qt.Horizontal)

        # Left column: Fly12Sport (front)
        self.front_scroll = self._create_camera_column("Fly12Sport", "Front Camera")
        splitter.addWidget(self.front_scroll)

        # Right column: Fly6Pro (rear)
        self.rear_scroll = self._create_camera_column("Fly6Pro", "Rear Camera")
        splitter.addWidget(self.rear_scroll)

        splitter.setSizes([690, 690])
        layout.addWidget(splitter)

        # Buttons (compact footer)
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(8)
        btn_layout.setContentsMargins(0, 4, 0, 0)

        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        cancel_btn.setStyleSheet(self._button_style(primary=False))

        self.save_btn = QPushButton("Save Offsets")
        self.save_btn.clicked.connect(self._save_offsets)
        self.save_btn.setStyleSheet(self._button_style(primary=True))

        btn_layout.addWidget(cancel_btn)
        btn_layout.addStretch()
        btn_layout.addWidget(self.save_btn)
        layout.addLayout(btn_layout)

    def _create_camera_column(self, camera_name: str, display_name: str) -> QGroupBox:
        """Create a scrollable column for one camera type."""
        group = QGroupBox(display_name)
        group.setStyleSheet("""
            QGroupBox {
                font-size: 14px;
                font-weight: 600;
                border: 1px solid #ddd;
                border-radius: 4px;
                margin-top: 8px;
                padding: 2px;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 8px;
                padding: 0 3px;
            }
        """)

        outer_layout = QVBoxLayout(group)
        outer_layout.setContentsMargins(4, 4, 4, 4)
        outer_layout.setSpacing(4)

        # Offset control for this camera (compact)
        offset_layout = QHBoxLayout()
        offset_layout.setSpacing(6)
        offset_label = QLabel(f"Offset:")
        offset_label.setStyleSheet("font-weight: 600; font-size: 12px;")

        spinbox = QDoubleSpinBox()
        spinbox.setRange(-10.0, 10.0)
        spinbox.setSingleStep(0.5)
        spinbox.setDecimals(1)
        spinbox.setValue(self.offsets.get(camera_name, 0.0))
        spinbox.setStyleSheet("padding: 3px; font-size: 12px;")
        spinbox.setFixedWidth(70)
        spinbox.valueChanged.connect(lambda v, c=camera_name: self._on_offset_changed(c, v))

        self.spinboxes[camera_name] = spinbox

        sec_label = QLabel("sec")
        sec_label.setStyleSheet("color: #666; font-size: 11px;")

        offset_layout.addWidget(offset_label)
        offset_layout.addWidget(spinbox)
        offset_layout.addWidget(sec_label)
        offset_layout.addStretch()
        outer_layout.addLayout(offset_layout)

        # Scrollable clip grid
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet(
            "QScrollArea { border: none; background: #FAFAFA; }"
        )

        grid_widget = QWidget()
        grid_layout = QVBoxLayout(grid_widget)
        grid_layout.setSpacing(8)
        grid_layout.setContentsMargins(2, 2, 2, 2)

        # Store reference for populating later
        setattr(self, f"{camera_name}_grid", grid_layout)

        scroll.setWidget(grid_widget)
        outer_layout.addWidget(scroll)

        return group

    def _button_style(self, primary: bool) -> str:
        """Generate button stylesheet."""
        if primary:
            return """
                QPushButton {
                    background-color: #2D7A4F;
                    color: white;
                    padding: 6px 14px;
                    font-size: 12px;
                    font-weight: 600;
                    border: 1px solid #2D7A4F;
                    border-radius: 4px;
                }
                QPushButton:hover {
                    background-color: #246840;
                    border-color: #246840;
                }
            """
        else:
            return """
                QPushButton {
                    background-color: #FFFFFF;
                    color: #333333;
                    padding: 6px 14px;
                    font-size: 12px;
                    font-weight: 600;
                    border: 1px solid #DDDDDD;
                    border-radius: 4px;
                }
                QPushButton:hover {
                    background-color: #F8F9FA;
                    border-color: #CCCCCC;
                }
            """

    # --------------------------------------------------
    # Data loading
    # --------------------------------------------------

    def _load_clips(self):
        """Scan input video directory and group clips by camera."""
        input_dir = CFG.INPUT_VIDEOS_DIR

        if not input_dir.exists():
            QMessageBox.warning(
                self, "No Input Directory",
                f"Input directory not found:\n{input_dir}\n\n"
                "Please ensure a project is loaded with video files."
            )
            return

        # Find all MP4 files
        video_files = list(input_dir.glob("**/*.MP4")) + list(input_dir.glob("**/*.mp4"))

        if not video_files:
            QMessageBox.warning(
                self, "No Videos",
                f"No video files found in:\n{input_dir}"
            )
            return

        # Group by camera (detected from path)
        self.clips_by_camera = {}
        for video_path in video_files:
            # Detect camera from path (parent folder name usually contains camera name)
            camera = self._detect_camera_from_path(video_path)

            # Get video metadata
            try:
                # probe_video_metadata returns (creation_datetime, duration_seconds)
                creation_dt, duration_s = probe_video_metadata(video_path)

                clip_data = {
                    "source": video_path.name,
                    "full_path": str(video_path),
                    "camera": camera,
                    "duration_s": duration_s,
                    "creation_time": creation_dt.isoformat() if creation_dt else "",
                }

                if camera not in self.clips_by_camera:
                    self.clips_by_camera[camera] = []
                self.clips_by_camera[camera].append(clip_data)

            except Exception as e:
                log.warning(f"Failed to probe {video_path.name}: {e}")

        total_clips = sum(len(clips) for clips in self.clips_by_camera.values())
        self.log(f"Found {total_clips} video clips from {len(self.clips_by_camera)} cameras", "info")

        # Populate UI
        self._populate_camera_grids()

    def _detect_camera_from_path(self, video_path: Path) -> str:
        """Detect camera name from video file path."""
        from source.models import get_registry

        registry = get_registry()
        path_str = str(video_path).lower()

        # Check path components for camera names
        for part in video_path.parts:
            normalized = registry.normalize(part)
            if normalized in registry.get_all_cameras():
                return normalized

        # Fallback: check if any known camera name is in the path
        if "fly12" in path_str:
            return "Fly12Sport"
        if "fly6" in path_str:
            return "Fly6Pro"

        return "Unknown"

    def _populate_camera_grids(self):
        """Populate grid for each camera."""
        for camera_name in ["Fly12Sport", "Fly6Pro"]:
            grid = getattr(self, f"{camera_name}_grid", None)
            if not grid:
                continue

            # Clear existing
            while grid.count():
                item = grid.takeAt(0)
                if item.widget():
                    item.widget().deleteLater()

            clips = self.clips_by_camera.get(camera_name, [])

            # Sort by filename (ascending order)
            clips = sorted(clips, key=lambda c: c.get("source", ""))

            if not clips:
                empty_label = QLabel(f"No {camera_name} clips found")
                empty_label.setStyleSheet("color: #999; font-style: italic; padding: 20px;")
                empty_label.setAlignment(Qt.AlignCenter)
                grid.addWidget(empty_label)
                continue

            # Initialize time labels list for this camera
            self.time_labels[camera_name] = []

            # Show first 10 clips (or all if fewer)
            for idx, clip in enumerate(clips[:10]):
                card = self._create_clip_card(clip, camera_name, idx)
                grid.addWidget(card)

            grid.addStretch()

    def _create_clip_card(self, clip: Dict, camera_name: str, idx: int) -> QFrame:
        """Create a card showing clip thumbnail and time metadata."""
        card = QFrame()
        card.setFrameShape(QFrame.Box)
        card.setStyleSheet("""
            QFrame {
                background-color: white;
                border: 1px solid #ddd;
                border-radius: 4px;
                padding: 4px;
            }
        """)

        layout = QVBoxLayout(card)
        layout.setSpacing(3)
        layout.setContentsMargins(3, 3, 3, 3)

        # Thumbnail - full frame to show burnt-in timestamps at bottom
        thumbnail_label = QLabel()
        thumbnail_label.setMinimumSize(520, 293)
        thumbnail_label.setMaximumHeight(390)
        thumbnail_label.setStyleSheet("background-color: #f0f0f0; border-radius: 4px;")
        thumbnail_label.setScaledContents(True)  # Fill label, show full frame

        # Extract and display thumbnail
        self._load_thumbnail(clip, thumbnail_label)
        layout.addWidget(thumbnail_label)

        # Compact metadata (below thumbnail)
        source = clip.get("source", "Unknown")
        duration_s = float(clip.get("duration_s", 0))
        full_path = clip.get("full_path")
        video_path = Path(full_path) if full_path else CFG.INPUT_VIDEOS_DIR / source
        codec_name = self._get_video_codec(video_path) if video_path.exists() else "Unknown"
        creation_time_str = clip.get("creation_time", "")
        calc_start = self._calculate_start_time(clip, camera_name)

        # File and codec on one line
        is_hevc = 'hevc' in codec_name.lower() or '265' in codec_name
        codec_color = '#c75000' if is_hevc else '#666'
        info_label = QLabel(f"<b>{source}</b> | {duration_s:.0f}s | <span style='color:{codec_color}'>{codec_name}</span>")
        info_label.setStyleSheet("font-size: 10px;")
        layout.addWidget(info_label)

        # Calculated start (the important one)
        calc_label = QLabel(f"<b>Start:</b> {calc_start}")
        calc_label.setStyleSheet("font-size: 11px; color: #2D7A4F; font-weight: 600;")
        calc_label.setProperty("clip_data", clip)
        layout.addWidget(calc_label)

        # Store reference for updating
        self.time_labels[camera_name].append(calc_label)

        return card

    def _load_thumbnail(self, clip: Dict, label: QLabel):
        """Load first frame thumbnail for a clip - full frame including bottom timestamps."""
        # Use full_path if available, otherwise construct from source
        full_path = clip.get("full_path")
        if full_path:
            video_path = Path(full_path)
        else:
            source = clip.get("source", "")
            video_path = CFG.INPUT_VIDEOS_DIR / source

        if not video_path.exists():
            label.setText(f"[Video not found]")
            return

        source = video_path.name  # For thumbnail naming

        # Check for cached thumbnail - use high resolution for readable timestamps
        thumb_name = f"{Path(source).stem}_cal.png"
        thumb_path = self.thumbnail_dir / thumb_name

        if not thumb_path.exists():
            # Extract first frame - save at high resolution (PNG for lossless quality)
            try:
                frame = extract_frame_safe(video_path, 0)
                if frame is not None:
                    from PIL import Image
                    img = Image.fromarray(frame)
                    # Scale to 1280px width for clear timestamp readability
                    w, h = img.size
                    new_w = 1280
                    new_h = int(h * new_w / w)
                    img = img.resize((new_w, new_h), Image.Resampling.LANCZOS)
                    img.save(thumb_path)  # PNG = lossless
            except Exception as e:
                log.warning(f"Failed to extract thumbnail from {source}: {e}")
                label.setText(f"[Thumbnail error]")
                return

        # Load thumbnail - setScaledContents will stretch to fill label
        if thumb_path.exists():
            pixmap = QPixmap(str(thumb_path))
            if not pixmap.isNull():
                label.setPixmap(pixmap)
            else:
                label.setText("[Load error]")
        else:
            label.setText("[No thumbnail]")

    def _calculate_start_time(self, clip: Dict, camera_name: str) -> str:
        """Calculate recording start time with current offset and timezone."""
        creation_time_str = clip.get("creation_time", "")
        duration_s = float(clip.get("duration_s", 0))

        if not creation_time_str:
            return "N/A"

        try:
            # Parse creation time
            creation_dt = datetime.fromisoformat(creation_time_str.replace("Z", "+00:00"))

            # Apply Cycliq UTC bug fix using the SELECTED timezone (not CFG default)
            if CFG.CAMERA_CREATION_TIME_IS_LOCAL_WRONG_Z:
                selected_tz = self._parse_timezone_string(self.current_timezone)
                if selected_tz:
                    creation_dt = fix_cycliq_utc_bug(
                        creation_dt,
                        selected_tz,
                        CFG.CAMERA_CREATION_TIME_IS_LOCAL_WRONG_Z
                    )
                else:
                    # Fallback to config default
                    creation_dt = fix_cycliq_utc_bug(
                        creation_dt,
                        CFG.CAMERA_CREATION_TIME_TZ,
                        CFG.CAMERA_CREATION_TIME_IS_LOCAL_WRONG_Z
                    )

            # Get current offset for this camera
            offset = self.offsets.get(camera_name, 0.0)

            # Calculate start: creation_time - duration - offset
            start_dt = creation_dt - timedelta(seconds=duration_s + offset)

            return start_dt.strftime("%Y-%m-%d %H:%M:%S")

        except Exception as e:
            log.warning(f"Failed to calculate start time: {e}")
            return "Error"

    def _parse_timezone_string(self, tz_str: str):
        """Parse timezone string like 'UTC+10:30' to timezone object."""
        import re

        if not tz_str:
            return None

        # Parse UTC offset format: "UTC+10:30", "UTC+10", "UTC-5", etc.
        pattern = r'^UTC([+-])(\d{1,2})(?::(\d{2}))?$'
        match = re.match(pattern, tz_str.strip())

        if match:
            sign = match.group(1)
            hours = int(match.group(2))
            minutes = int(match.group(3) or 0)

            total_minutes = hours * 60 + minutes
            if sign == '-':
                total_minutes = -total_minutes

            return timezone(timedelta(minutes=total_minutes))

        return None

    def _get_video_codec(self, video_path: Path) -> str:
        """Get video codec name from file metadata."""
        import subprocess
        import json

        try:
            out = subprocess.check_output([
                "ffprobe", "-v", "quiet", "-print_format", "json",
                "-show_streams", "-select_streams", "v:0",
                str(video_path)
            ], timeout=10)

            data = json.loads(out.decode())
            streams = data.get("streams", [])
            if streams:
                codec = streams[0].get("codec_name", "")
                if codec:
                    # Map common codec names to friendly names
                    codec_map = {
                        "h264": "H.264 (AVC)",
                        "hevc": "H.265 (HEVC)",
                        "h265": "H.265 (HEVC)",
                    }
                    return codec_map.get(codec.lower(), codec)
            return "Unknown"
        except Exception as e:
            log.debug(f"Failed to get codec for {video_path.name}: {e}")
            return "Unknown"

    # --------------------------------------------------
    # Offset adjustment
    # --------------------------------------------------

    def _on_offset_changed(self, camera_name: str, value: float):
        """Handle offset spinbox value change."""
        self.offsets[camera_name] = value

        # Update all time labels for this camera
        for label in self.time_labels.get(camera_name, []):
            clip = label.property("clip_data")
            if clip:
                new_time = self._calculate_start_time(clip, camera_name)
                label.setText(f"<b>Calculated start:</b> {new_time}")

    # --------------------------------------------------
    # Save functionality
    # --------------------------------------------------

    def _load_saved_offsets(self) -> Dict[str, float]:
        """Load offsets from project config if exists, else from default config."""
        import json

        # Project-specific config
        config_path = self.project_dir / "project_config.json"

        if config_path.exists():
            try:
                with config_path.open() as f:
                    data = json.load(f)
                    if "KNOWN_OFFSETS" in data:
                        log.info(f"Loaded project offsets from {config_path}: {data['KNOWN_OFFSETS']}")
                        return dict(data["KNOWN_OFFSETS"])
            except Exception as e:
                log.warning(f"Failed to load project_config.json: {e}")

        # Fall back to default config
        return dict(CFG.KNOWN_OFFSETS)

    def _load_saved_timezone(self) -> str:
        """Load timezone from project config if exists, else from default config."""
        import json

        # Project-specific config
        config_path = self.project_dir / "project_config.json"

        if config_path.exists():
            try:
                with config_path.open() as f:
                    data = json.load(f)
                    if "CAMERA_TIMEZONE" in data:
                        tz = data["CAMERA_TIMEZONE"]
                        log.info(f"Loaded project timezone from {config_path}: {tz}")
                        return tz
            except Exception as e:
                log.warning(f"Failed to load timezone from project_config.json: {e}")

        # Fall back to default config timezone
        # Convert the timezone object to a string representation
        tz = CFG.CAMERA_CREATION_TIME_TZ
        offset = tz.utcoffset(None)
        if offset:
            total_seconds = int(offset.total_seconds())
            hours, remainder = divmod(abs(total_seconds), 3600)
            minutes = remainder // 60
            sign = '+' if total_seconds >= 0 else '-'
            if minutes:
                return f"UTC{sign}{hours}:{minutes:02d}"
            else:
                return f"UTC{sign}{hours}"
        return "UTC+10"

    def _populate_timezone_options(self):
        """Populate timezone combo with common Australian timezones."""
        timezones = [
            ("UTC+10:30 - Adelaide (ACDT)", "UTC+10:30"),
            ("UTC+10 - Brisbane/Sydney (AEST)", "UTC+10"),
            ("UTC+11 - Sydney DST (AEDT)", "UTC+11"),
            ("UTC+9:30 - Adelaide Std (ACST)", "UTC+9:30"),
            ("UTC+8 - Perth (AWST)", "UTC+8"),
            ("UTC+0 - UTC/GMT", "UTC+0"),
        ]

        for label, value in timezones:
            self.timezone_combo.addItem(label, value)

        # Select current timezone
        for i in range(self.timezone_combo.count()):
            if self.timezone_combo.itemData(i) == self.current_timezone:
                self.timezone_combo.setCurrentIndex(i)
                break

    def _on_timezone_changed(self, text: str):
        """Handle timezone combo change."""
        new_tz = self.timezone_combo.currentData()
        if new_tz:
            self.current_timezone = new_tz
            # Refresh all calculated times
            self._refresh_all_time_labels()

    def _refresh_all_time_labels(self):
        """Refresh all time labels with current timezone."""
        for camera_name, labels in self.time_labels.items():
            for label in labels:
                clip = label.property("clip_data")
                if clip:
                    new_time = self._calculate_start_time(clip, camera_name)
                    label.setText(f"<b>Start:</b> {new_time}")

    def _save_offsets(self):
        """Save offsets and timezone to config."""
        try:
            # Build overrides dict
            overrides = {
                "KNOWN_OFFSETS": self.offsets,
                "CAMERA_TIMEZONE": self.current_timezone,
            }

            # Save to project_config.json
            self._save_config_overrides(overrides)

            # Also update the live CFG so it takes effect immediately
            CFG.KNOWN_OFFSETS = dict(self.offsets)

            # Update timezone in CFG
            selected_tz = self._parse_timezone_string(self.current_timezone)
            if selected_tz:
                CFG.CAMERA_CREATION_TIME_TZ = selected_tz

            # Reset camera registry to pick up new values
            reset_registry()

            self.log(f"Saved camera offsets: {self.offsets}", "success")
            self.log(f"Saved timezone: {self.current_timezone}", "success")
            self.offsets_changed.emit(self.offsets)

            QMessageBox.information(
                self, "Saved",
                f"Camera calibration saved:\n\n"
                f"Timezone: {self.current_timezone}\n"
                f"Fly12Sport offset: {self.offsets.get('Fly12Sport', 0.0):.1f}s\n"
                f"Fly6Pro offset: {self.offsets.get('Fly6Pro', 0.0):.1f}s\n\n"
                "Re-run Extract step to apply changes."
            )

            self.accept()

        except Exception as e:
            log.error(f"Failed to save settings: {e}")
            QMessageBox.critical(self, "Error", f"Failed to save settings: {e}")

    def _save_config_overrides(self, overrides: Dict):
        """Save config overrides to project config file."""
        import json

        # Project-specific config
        config_path = self.project_dir / "project_config.json"

        # Load existing config
        existing = {}
        if config_path.exists():
            try:
                with config_path.open() as f:
                    existing = json.load(f)
            except Exception:
                pass

        # Merge overrides
        existing.update(overrides)

        # Save
        with config_path.open("w") as f:
            json.dump(existing, f, indent=2)

        log.info(f"Saved project config to {config_path}")
