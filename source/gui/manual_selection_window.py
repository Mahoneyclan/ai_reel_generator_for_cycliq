# source/gui/manual_selection_window.py

import csv
from pathlib import Path
from typing import List, Dict
from collections import defaultdict

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QScrollArea, QWidget, QGridLayout, QMessageBox, QFrame
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap

from source.config import DEFAULT_CONFIG as CFG
from source.io_paths import select_path, frames_dir, _mk
from source.utils.log import setup_logger

log = setup_logger("gui.manual_selection_window")


class ManualSelectionWindow(QDialog):
    def __init__(self, project_dir: Path, parent=None):
        super().__init__(parent)
        self.project_dir = project_dir
        self.moments: List[Dict] = []
        self.extract_dir = frames_dir()
        _mk(self.extract_dir)
        self.selected_count = 0
        self.target_clips = int(CFG.HIGHLIGHT_TARGET_DURATION_S // CFG.CLIP_OUT_LEN_S)

        self.setWindowTitle("Review & Refine Clip Selection")
        self.resize(1600, 900)
        self.setModal(True)

        self._setup_ui()
        self._load_moments()
        self._populate_grid()

    def log(self, message: str, level: str = "info"):
        if self.parent() and hasattr(self.parent(), 'log'):
            self.parent().log(message, level)
        else:
            print(f"[ManualSelectionWindow] {level.upper()}: {message}")

    def accept(self):
        try:
            self.save_selection()
            self.log("Manual selection persisted via accept()", "success")
        except Exception as e:
            self.log(f"Error saving selection on accept: {e}", "error")
            QMessageBox.critical(self, "Save Error", f"Failed to save selection: {e}")
            return
        super().accept()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(15)

        title = QLabel("Review & Refine Clip Selection")
        title.setStyleSheet("font-size: 22px; font-weight: 600; color: #1a1a1a; margin-bottom: 5px;")
        layout.addWidget(title, alignment=Qt.AlignCenter)

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

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("QScrollArea { border: 1px solid #E5E5E5; background: #FAFAFA; border-radius: 4px; }")

        self.grid_widget = QWidget()
        self.grid_layout = QGridLayout(self.grid_widget)
        self.grid_layout.setSpacing(15)
        self.grid_layout.setContentsMargins(10, 10, 10, 10)

        scroll.setWidget(self.grid_widget)
        layout.addWidget(scroll)

        instructions = QLabel(
            "💡 Click a perspective to select its pair of frames.\n"
            "Only one perspective per moment can be selected.\n"
            "Click again to deselect."
        )
        instructions.setStyleSheet("color: #666; font-size: 12px; font-style: italic; padding: 10px;")
        instructions.setAlignment(Qt.AlignCenter)
        instructions.setWordWrap(True)
        layout.addWidget(instructions)

        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(12)

        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)

        self.ok_btn = QPushButton(f"Use {self.selected_count} Clips & Continue")
        self.ok_btn.clicked.connect(lambda: self.accept())

        btn_layout.addWidget(cancel_btn)
        btn_layout.addWidget(self.ok_btn)
        layout.addLayout(btn_layout)

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

            # Sort rows by epoch for pairing
            rows_sorted = sorted(rows, key=lambda r: float(r.get("abs_time_epoch", 0) or 0.0))
            self.moments = []
            used = set()

            for i, row in enumerate(rows_sorted):
                if i in used:
                    continue
                epoch = float(row.get("abs_time_epoch", 0) or 0.0)
                pair = [row]

                # look ahead for partner within tolerance
                for j in range(i + 1, len(rows_sorted)):
                    other = rows_sorted[j]
                    other_epoch = float(other.get("abs_time_epoch", 0) or 0.0)
                    if abs(other_epoch - epoch) <= CFG.PARTNER_TIME_TOLERANCE_S:
                        pair.append(other)
                        used.add(j)
                        break

                if len(pair) == 2:
                    row1, row2 = pair
                    moment = {
                        "epoch": epoch,
                        "row1": row1,
                        "row2": row2,
                        "rows": pair,
                    }
                    self.moments.append(moment)
                else:
                    self.log(f"Skipping epoch {epoch}: expected 2 rows, found {len(pair)}", "warning")

            self.selected_count = sum(
                1 for m in self.moments if any(r.get("recommended") == "true" for r in m["rows"])
            )
            self.counter_label.setText(f"Selected: {self.selected_count} clips")
            self.ok_btn.setText(f"Use {self.selected_count} Clips & Continue")
            self.status_label.setText(
                f"Found {len(self.moments)} moments  •  Pre-selected: {self.selected_count} / {self.target_clips} target"
            )
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to load candidates: {e}")
            self.log(f"CSV load error: {e}", "error")
            self.reject()


    def _populate_grid(self):
        while self.grid_layout.count():
            item = self.grid_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        for row_idx, moment in enumerate(self.moments):
            try:
                widget = self._create_moment_widget(moment, row_idx)
                self.grid_layout.addWidget(widget, row_idx, 0)
            except Exception as e:
                self.log(f"Failed to create widget for moment {row_idx}: {e}", "error")

    def _create_moment_widget(self, moment: Dict, moment_idx: int) -> QWidget:
        container = QFrame()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(8)

        container.moment_data = moment
        container.moment_idx = moment_idx
        moment["widget"] = container

        row1 = moment["row1"]
        row2 = moment["row2"]

        frames_container = QWidget()
        frames_layout = QHBoxLayout(frames_container)
        frames_layout.setContentsMargins(0, 0, 0, 0)
        frames_layout.setSpacing(8)

        persp1 = self._create_perspective_widget(row1, row1.get("camera", "Cam1"), moment)
        frames_layout.addWidget(persp1)

        persp2 = self._create_perspective_widget(row2, row2.get("camera", "Cam2"), moment)
        frames_layout.addWidget(persp2)

        layout.addWidget(frames_container)

        time_str = row1.get('abs_time_iso') or row1.get('adjusted_start_time') or 'N/A'
        metadata_lines = [f"Time: {time_str}"]

        def _fmt_meta(r: Dict, label: str) -> str:
            parts = []
            if r.get('speed_kmh'): parts.append(f"Speed {r['speed_kmh']} km/h")
            if r.get('detect_score'): parts.append(f"Detection {r['detect_score']}")
            if r.get('scene_boost'): parts.append(f"Scene {r['scene_boost']}")
            return f"{label}: " + (" | ".join(parts) if parts else "—")

        metadata_lines.append(_fmt_meta(row1, row1.get("camera", "Cam1")))
        metadata_lines.append(_fmt_meta(row2, row2.get("camera", "Cam2")))

        metadata = QLabel("\n".join(metadata_lines))
        metadata.setAlignment(Qt.AlignCenter)
        metadata.setStyleSheet("font-size: 10px; color: #666;")
        metadata.setWordWrap(True)
        layout.addWidget(metadata)

        return container

    def _create_perspective_widget(self, row: Dict, label: str, moment: Dict) -> QWidget:
        container = QFrame()
        container.row_data = row
        container.moment_data = moment

        layout = QHBoxLayout(container)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(4)

        index = row.get("index", "")
        partner_index = row.get("partner_index", "")

        primary_frame = self._create_single_frame(f"{index}_Primary", f"{label} (Primary)", index)
        partner_frame = self._create_single_frame(f"{index}_Partner", f"{label} (Partner)", partner_index)

        layout.addWidget(primary_frame)
        layout.addWidget(partner_frame)

        container.mousePressEvent = lambda e: self._on_perspective_selected(container)

        self._apply_perspective_style(container, row)
        return container

    def _create_single_frame(self, filename: str, label_text: str, title_text: str) -> QWidget:
        frame_widget = QWidget()
        frame_layout = QVBoxLayout(frame_widget)
        frame_layout.setContentsMargins(0, 0, 0, 0)
        frame_layout.setSpacing(4)

        label = QLabel(label_text)
        label.setAlignment(Qt.AlignCenter)
        label.setStyleSheet("font-weight: bold; font-size: 11px;")
        frame_layout.addWidget(label)

        title = QLabel(title_text)
        title.setAlignment(Qt.AlignCenter)
        title.setStyleSheet("font-size: 10px; color: #444;")
        frame_layout.addWidget(title)

        frame_path = self.extract_dir / f"{filename}.jpg"
        if frame_path.exists():
            pixmap = QPixmap(str(frame_path))
            if not pixmap.isNull():
                pixmap = pixmap.scaled(340, 240, Qt.KeepAspectRatio, Qt.SmoothTransformation)
                image_label = QLabel()
                image_label.setPixmap(pixmap)
                image_label.setAlignment(Qt.AlignCenter)
                frame_layout.addWidget(image_label)
            else:
                fallback = QLabel("[Error loading image]")
                fallback.setAlignment(Qt.AlignCenter)
                fallback.setMinimumSize(340, 240)
                frame_layout.addWidget(fallback)
        else:
            fallback = QLabel(f"[Missing: {frame_path.name}]")
            fallback.setAlignment(Qt.AlignCenter)
            fallback.setMinimumSize(340, 240)
            fallback.setStyleSheet("color: #999; background-color: #f0f0f0;")
            frame_layout.addWidget(fallback)

        return frame_widget

    def _apply_perspective_style(self, container: QFrame, row: Dict):
        is_selected = row.get("recommended") == "true"
        container.setStyleSheet(f"""
            QFrame {{
                background-color: {'#E8F5E9' if is_selected else '#FAFAFA'};
                border: {'3' if is_selected else '2'}px solid {'#4CAF50' if is_selected else '#DDDDDD'};
                border-radius: 6px;
            }}
        """)

    def _on_perspective_selected(self, persp_container: QFrame):
        moment = persp_container.moment_data
        row = persp_container.row_data

        currently_selected = row.get("recommended") == "true"
        if currently_selected:
            row["recommended"] = "false"
        else:
            # Select this perspective, deselect the other
            row["recommended"] = "true"
            other = moment["row1"] if row is moment["row2"] else moment["row2"]
            other["recommended"] = "false"

        # Refresh styles for both perspectives in this moment
        parent_frames = persp_container.parent()
        if parent_frames is not None:
            for i in range(parent_frames.layout().count()):
                w = parent_frames.layout().itemAt(i).widget()
                if isinstance(w, QFrame) and hasattr(w, "row_data"):
                    self._apply_perspective_style(w, w.row_data)

        # Update counter: number of moments with one perspective selected
        self.selected_count = sum(
            1 for m in self.moments
            if any(r.get("recommended") == "true" for r in m["rows"])
        )
        self.counter_label.setText(f"✓ Selected: {self.selected_count} clips")
        self.ok_btn.setText(f"✓ Use {self.selected_count} Clips & Continue")

    def save_selection(self):
        csv_path = select_path()
        all_rows = []
        for moment in self.moments:
            all_rows.extend(moment["rows"])
        if not all_rows:
            with csv_path.open('w', newline='') as f:
                csv.writer(f).writerow(["index"])
            self.log("[manual] No candidates to save; wrote minimal header", "warning")
            return
        all_rows.sort(key=lambda r: float(r.get("abs_time_epoch", 0) or 0.0))
        selected_count = sum(1 for r in all_rows if r.get("recommended") == "true")
        message = f"[manual] Saving {len(all_rows)} rows ({selected_count} recommended)"
        self.log(message, "info")
        log.info(message)
        try:
            fieldnames = list(all_rows[0].keys())
            with csv_path.open('w', newline='') as f:
                writer = csv.DictWriter(f, fieldnames=fieldnames)
                writer.writeheader()
                writer.writerows(all_rows)
            self.log(f"[manual] Selection confirmed: {selected_count} clips selected", "info")
            log.info(f"[manual] Successfully wrote {csv_path}")
        except Exception as e:
            self.log(f"[manual] FAILED to write {csv_path}: {e}", "error")
            log.error(f"[manual] FAILED to write {csv_path}: {e}")
            raise
