# source/gui/manual_selection_window.py

import csv
import logging
from pathlib import Path
from typing import List, Dict, Optional
from datetime import datetime 
from zoneinfo import ZoneInfo

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QScrollArea, QWidget, QGridLayout, QMessageBox, QFrame
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap, QPainter

from source.config import DEFAULT_CONFIG as CFG
from source.io_paths import select_path, frames_dir, _mk
from source.utils.log import setup_logger
from source.models import get_registry

log = setup_logger("gui.manual_selection_window")


class ManualSelectionWindow(QDialog):
    """
    Manual selection window with PiP layout for moment-based dual perspectives.

    Assumptions:
        - select.csv contains two rows per candidate moment_id:
            * One for Fly12Sport
            * One for Fly6Pro
        - Each row has:
            * index, camera, abs_time_epoch, recommended, ...
        - Frames are extracted as {index}_Primary.jpg in frames_dir().
    """

    def __init__(self, project_dir: Path, parent=None):
        super().__init__(parent)
        self.project_dir = project_dir

        # Each moment entry:
        # {
        #   "moment_id": int,
        #   "epoch": float,
        #   "rows": [fly12_row, fly6_row]  (order stable, but we treat them by camera)
        # }
        self.moments: List[Dict] = []

        self.extract_dir = frames_dir()
        _mk(self.extract_dir)

        self.selected_count = 0
        self.target_clips = int(CFG.HIGHLIGHT_TARGET_DURATION_S // CFG.CLIP_OUT_LEN_S)

        self.setWindowTitle("Review & Refine Clip Selection")
        self.resize(1400, 900)
        self.setModal(True)

        self._setup_ui()
        self._load_moments()
        self._populate_grid()

    # --------------------------------------------------
    # Logging helpers
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
    # Dialog lifecycle
    # --------------------------------------------------

    def accept(self):
        try:
            self.save_selection()
            self.log("Manual selection persisted via accept()", "success")
        except Exception as e:
            self.log(f"Error saving selection on accept: {e}", "error")
            QMessageBox.critical(self, "Save Error", f"Failed to save selection: {e}")
            return
        super().accept()

    # --------------------------------------------------
    # UI setup
    # --------------------------------------------------

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(15)

        # Title
        title = QLabel("Review & Refine Clip Selection")
        title.setStyleSheet(
            "font-size: 22px; font-weight: 600; color: #1a1a1a; margin-bottom: 5px;"
        )
        title.setAlignment(Qt.AlignCenter)
        layout.addWidget(title)

        self.status_label = QLabel("Loading candidate clips...")
        self.status_label.setStyleSheet("font-size: 13px; color: #666; margin-bottom: 10px;")
        layout.addWidget(self.status_label, alignment=Qt.AlignCenter)

        self.counter_label = QLabel(f"Selected: {self.selected_count} clips")
        self.counter_label.setStyleSheet(
            "font-size: 16px; font-weight: 600; color: #2D7A4F; "
            "padding: 10px 20px; background-color: #F0F9F4; "
            "border: 2px solid #6EBF8B; border-radius: 6px; margin-bottom: 10px;"
        )
        self.counter_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.counter_label)

        # Scrollable grid of moments
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet(
            "QScrollArea { border: 1px solid #E5E5E5; background: #FAFAFA; border-radius: 4px; }"
        )

        self.grid_widget = QWidget()
        self.grid_layout = QGridLayout(self.grid_widget)
        self.grid_layout.setSpacing(20)
        self.grid_layout.setContentsMargins(10, 10, 10, 10)

        scroll.setWidget(self.grid_widget)
        layout.addWidget(scroll)

        instructions = QLabel(
            "Click a perspective card to select/deselect that camera angle.\n"
            "Both views are shown: primary (main) with opposite camera as PiP.\n"
            "Only one perspective per moment can be selected (or none)."
        )
        instructions.setStyleSheet(
            "color: #666; font-size: 12px; font-style: italic; padding: 10px;"
        )
        instructions.setAlignment(Qt.AlignCenter)
        instructions.setWordWrap(True)
        layout.addWidget(instructions)

        # Buttons
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(12)

        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        cancel_btn.setStyleSheet(
            """
            QPushButton {
                background-color: #FFFFFF;
                color: #333333;
                padding: 10px 20px;
                font-size: 13px;
                font-weight: 600;
                border: 2px solid #DDDDDD;
                border-radius: 6px;
            }
            QPushButton:hover {
                background-color: #F8F9FA;
                border-color: #CCCCCC;
            }
        """
        )

        self.ok_btn = QPushButton(f"Use {self.selected_count} Clips & Continue")
        self.ok_btn.clicked.connect(lambda: self.accept())
        self.ok_btn.setStyleSheet(
            """
            QPushButton {
                background-color: #2D7A4F;
                color: white;
                padding: 10px 20px;
                font-size: 13px;
                font-weight: 600;
                border: 2px solid #2D7A4F;
                border-radius: 6px;
            }
            QPushButton:hover {
                background-color: #246840;
                border-color: #246840;
            }
        """
        )

        btn_layout.addWidget(cancel_btn)
        btn_layout.addWidget(self.ok_btn)
        layout.addLayout(btn_layout)

    # --------------------------------------------------
    # Load moments from select.csv (moment-based)
    # --------------------------------------------------

    def _load_moments(self):
        select_csv = select_path()
        if not select_csv.exists():
            QMessageBox.critical(self, "Error", "No selection data. Run steps first.")
            self.reject()
            return

        try:
            with select_csv.open() as f:
                rows = list(csv.DictReader(f))
            if not rows:
                QMessageBox.critical(self, "Error", "Selection list is empty.")
                self.reject()
                return

            self.log(f"Loaded {len(rows)} rows from select.csv", "info")

            # Group by moment_id
            by_moment: Dict[str, List[Dict]] = {}
            for r in rows:
                mid = r.get("moment_id")
                if mid in (None, ""):
                    self.log(f"Row {r.get('index', '?')} missing moment_id", "warning")
                    continue
                by_moment.setdefault(str(mid), []).append(r)

            moments: List[Dict] = []
            dropped = 0

            registry = get_registry()
            for mid, group in by_moment.items():
                # Expect one Fly12 and one Fly6 row
                fly12_row: Optional[Dict] = None
                fly6_row: Optional[Dict] = None

                for r in group:
                    cam = r.get("camera", "")
                    if registry.is_front_camera(cam):
                        fly12_row = r
                    elif registry.is_rear_camera(cam):
                        fly6_row = r

                if not fly12_row or not fly6_row:
                    dropped += 1
                    continue

                # Use aligned world time
                epoch = min(
                    float(fly12_row.get("abs_time_epoch", 0) or 0.0),
                    float(fly6_row.get("abs_time_epoch", 0) or 0.0),
                )

                moments.append(
                    {
                        "moment_id": int(mid),
                        "epoch": epoch,
                        "rows": [fly12_row, fly6_row],
                    }
                )

            # Sort moments by aligned world time
            moments.sort(key=lambda m: m["epoch"])
            self.moments = moments

            # Count pre-selected (moments with at least one recommended row)
            self.selected_count = sum(
                1 for m in self.moments if any(r.get("recommended") == "true" for r in m["rows"])
            )

            total = len(self.moments)

            self.log(
                f"Created {total} moments from {len(rows)} rows, "
                f"dropped {dropped} moments with missing perspectives, "
                f"{self.selected_count} pre-selected",
                "success",
            )

            self.counter_label.setText(f"Selected: {self.selected_count} / {total} clips")
            self.ok_btn.setText(f"Use {self.selected_count} Clips & Continue")
            self.status_label.setText(
                f"Showing {total} moments (2 perspectives each)  •  "
                f"Pre-selected: {self.selected_count} / {self.target_clips} target"
            )

            if total == 0:
                QMessageBox.critical(
                    self,
                    "No Moments",
                    f"Could not create any moments from {len(rows)} rows.\n\n"
                    f"Check that moment_id values are present in select.csv",
                )
                self.reject()

        except Exception as e:
            self.log(f"Error: {e}", "error")
            import traceback

            self.log(traceback.format_exc(), "error")
            QMessageBox.critical(self, "Error", str(e))
            self.reject()

    # --------------------------------------------------
    # Grid population
    # --------------------------------------------------

    def _populate_grid(self):
        while self.grid_layout.count():
            item = self.grid_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        # 2 columns layout: both perspectives of same moment side-by-side
        for row_idx, moment in enumerate(self.moments):
            try:
                # Perspective A: Fly12 main / Fly6 PiP  (primary_idx = 0)
                card1 = self._create_perspective_card(moment, primary_idx=0)
                # Perspective B: Fly6 main / Fly12 PiP  (primary_idx = 1)
                card2 = self._create_perspective_card(moment, primary_idx=1)

                self.grid_layout.addWidget(card1, row_idx, 0)
                self.grid_layout.addWidget(card2, row_idx, 1)

            except Exception as e:
                self.log(f"Failed to create widget for moment {row_idx}: {e}", "error")

    # --------------------------------------------------
    # Card creation & PiP
    # --------------------------------------------------

    def _create_perspective_card(self, moment: Dict, primary_idx: int) -> QWidget:
        """
        Create a perspective card with PiP layout.

        primary_idx = 0 → primary = rows[0] (Fly12), partner = rows[1] (Fly6)
        primary_idx = 1 → primary = rows[1] (Fly6), partner = rows[0] (Fly12)
        """
        container = QFrame()
        container.setFrameShape(QFrame.Box)
        layout = QVBoxLayout(container)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(8)

        # Store moment data on container for click handling
        container.moment_data = moment
        container.primary_idx = primary_idx

        primary_row = moment["rows"][primary_idx]
        partner_row = moment["rows"][1 - primary_idx]

        # Create PiP composite image
        pip_widget = self._create_pip_widget(primary_row, partner_row)
        layout.addWidget(pip_widget)

        # Metadata
        camera_label = primary_row.get("camera", "Camera") 
        file_name = primary_row.get("path", "").split("/")[-1] 
        frame_num = primary_row.get("frame_number", "—")

        camera_label = primary_row.get("camera", "Camera")

        metadata_lines = [
            f"Camera: {camera_label} | File {file_name} | Frame {frame_num}",
            self._fmt_meta(primary_row),
        ]

        metadata = QLabel("\n".join(metadata_lines))
        metadata.setAlignment(Qt.AlignCenter)
        metadata.setStyleSheet("font-size: 11px; color: #666;")
        metadata.setWordWrap(True)
        layout.addWidget(metadata)

        # Click handler
        container.mousePressEvent = lambda e: self._on_perspective_selected(container)

        # Apply selection styling based on primary_row.recommended
        self._apply_perspective_style(container, primary_row)

        return container

    def _create_pip_widget(self, primary_row: Dict, partner_row: Dict) -> QLabel:
        """Create a QLabel with PiP composite image."""
        label = QLabel()
        label.setAlignment(Qt.AlignCenter)

        primary_idx = primary_row.get("index", "")
        partner_idx = partner_row.get("index", "")

        primary_path = self.extract_dir / f"{primary_idx}_Primary.jpg"
        partner_path = self.extract_dir / f"{partner_idx}_Primary.jpg"

        if not primary_path.exists():
            label.setText(f"[Missing: {primary_path.name}]")
            label.setStyleSheet("color: #999; background-color: #f0f0f0;")
            label.setMinimumSize(640, 360)
            return label

        composite = self._create_pip_composite(primary_path, partner_path)
        if composite:
            label.setPixmap(composite)
        else:
            label.setText("[Error creating PiP]")
            label.setMinimumSize(640, 360)

        return label

    def _create_pip_composite(self, primary_path: Path, partner_path: Path) -> Optional[QPixmap]:
        """Create PiP composite from two images."""
        primary = QPixmap(str(primary_path))
        if primary.isNull():
            return None

        display_width = 640
        display_height = 360
        primary = primary.scaled(
            display_width,
            display_height,
            Qt.KeepAspectRatio,
            Qt.SmoothTransformation,
        )

        if partner_path.exists():
            partner = QPixmap(str(partner_path))
            if not partner.isNull():
                pip_scale = 0.30
                pip_margin = 15
                pip_width = int(display_width * pip_scale)
                pip_height = int(pip_width * 9 / 16)

                partner = partner.scaled(
                    pip_width,
                    pip_height,
                    Qt.KeepAspectRatio,
                    Qt.SmoothTransformation,
                )

                painter = QPainter(primary)
                pip_x = display_width - pip_width - pip_margin
                pip_y = display_height - pip_height - pip_margin

                painter.setOpacity(0.95)
                painter.drawPixmap(pip_x, pip_y, partner)
                painter.end()

        return primary

    # --------------------------------------------------
    # Styling & selection logic
    # --------------------------------------------------

    def _fmt_meta(self, r: Dict) -> str:
        """Format metadata for a given row."""
        parts = []
        if r.get("speed_kmh"):
            parts.append(f"Speed {r['speed_kmh']} km/h")
        if r.get("detect_score"):
            parts.append(f"Detection {r['detect_score']}")
        if r.get("scene_boost"):
            parts.append(f"Scene {r['scene_boost']}")
        return " | ".join(parts) if parts else "—"

    def _apply_perspective_style(self, container: QFrame, row: Dict):
        """Apply styling based on selection state."""
        is_selected = row.get("recommended") == "true"
        container.setStyleSheet(
            f"""
            QFrame {{
                background-color: {'#E8F5E9' if is_selected else '#FAFAFA'};
                border: {'3' if is_selected else '2'}px solid {'#4CAF50' if is_selected else '#DDDDDD'};
                border-radius: 8px;
            }}
            QFrame:hover {{
                border-color: {'#2E7D32' if is_selected else '#999999'};
                background-color: {'#C8E6C9' if is_selected else '#F5F5F5'};
            }}
        """
        )

    def _on_perspective_selected(self, container: QFrame):
        """
        Handle perspective card selection.

        Rules:
            - At most 1 selected per moment.
            - Clicking selected → deselect (0 selected).
            - Clicking unselected → select this, deselect the other.
        """
        moment = container.moment_data
        primary_idx = container.primary_idx

        selected_row = moment["rows"][primary_idx]
        other_row = moment["rows"][1 - primary_idx]

        currently_selected = selected_row.get("recommended") == "true"

        if currently_selected:
            # Clicking selected → deselect
            selected_row["recommended"] = "false"
        else:
            # Clicking unselected → select this, deselect other
            selected_row["recommended"] = "true"
            other_row["recommended"] = "false"

        # Update all cards for this moment
        for i in range(self.grid_layout.count()):
            widget = self.grid_layout.itemAt(i).widget()
            if isinstance(widget, QFrame) and hasattr(widget, "moment_data"):
                if widget.moment_data is moment:
                    row_idx = widget.primary_idx
                    self._apply_perspective_style(widget, moment["rows"][row_idx])

        # Update counter - count moments with at least 1 selected perspective
        self.selected_count = sum(
            1 for m in self.moments if any(r.get("recommended") == "true" for r in m["rows"])
        )
        self.counter_label.setText(f"✓ Selected: {self.selected_count} clips")
        self.ok_btn.setText(f"✓ Use {self.selected_count} Clips & Continue")

    # --------------------------------------------------
    # Save selection back to CSV
    # --------------------------------------------------

    def save_selection(self):
        """Save selection back to select.csv."""
        csv_path = select_path()
        all_rows: List[Dict] = []
        for moment in self.moments:
            all_rows.extend(moment["rows"])

        if not all_rows:
            with csv_path.open("w", newline="") as f:
                csv.writer(f).writerow(["index"])
            self.log("[manual] No candidates to save; wrote minimal header", "warning")
            return

        all_rows.sort(key=lambda r: float(r.get("abs_time_epoch", 0) or 0.0))
        selected_count = sum(1 for r in all_rows if r.get("recommended") == "true")
        message = f"[manual] Saving {len(all_rows)} rows ({selected_count} recommended)"
        self.log(message, "info")

        try:
            fieldnames = list(all_rows[0].keys())
            with csv_path.open("w", newline="") as f:
                writer = csv.DictWriter(f, fieldnames=fieldnames)
                writer.writeheader()
                writer.writerows(all_rows)
            self.log(f"[manual] Selection confirmed: {selected_count} clips selected", "success")
        except Exception as e:
            self.log(f"[manual] FAILED to write {csv_path}: {e}", "error")
            raise
