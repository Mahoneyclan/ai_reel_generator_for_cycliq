# source/gui/manual_selection_window.py
"""
Manual review dialog for clip selection.
Displays PAIRED clips (primary + partner side-by-side) instead of individual frames.
"""

import csv
from pathlib import Path
from typing import List, Dict

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QScrollArea, QWidget, QGridLayout, QMessageBox, QFrame
)
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QPixmap

from source.config import DEFAULT_CONFIG as CFG
from source.io_paths import select_path, frames_dir, _mk
from source.utils.log import setup_logger

log = setup_logger("gui.manual_selection_window")


class ManualSelectionWindow(QDialog):
    """
    Manual review dialog for paired clip selection.
    - Shows primary + partner frames side-by-side
    - Groups clips by their pair relationship
    - Highlights AI recommendations
    - Allows toggling entire pairs
    """

    def __init__(self, project_dir: Path, parent=None):
        super().__init__(parent)
        self.project_dir = project_dir
        self.candidates: List[Dict[str, str]] = []
        self.extract_dir = frames_dir()
        _mk(self.extract_dir)
        self.selected_count = 0
        self.target_clips = int(CFG.HIGHLIGHT_TARGET_DURATION_S // CFG.CLIP_OUT_LEN_S)

        self.setWindowTitle("Review & Refine Clip Selection")
        self.resize(1600, 900)
        self.setModal(True)

        self._setup_ui()
        self._load_candidates()

    def log(self, message: str, level: str = "info"):
        """Proxy logs to parent window if available, else print."""
        if self.parent() and hasattr(self.parent(), 'log'):
            self.parent().log(message, level)
        else:
            print(f"[ManualSelectionWindow] {level.upper()}: {message}")

    def accept(self):
        """Override QDialog.accept to guarantee persistence of manual selection."""
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

        title = QLabel("Review & Refine Clip Selection")
        title.setStyleSheet("font-size: 22px; font-weight: bold; margin-bottom: 10px;")
        layout.addWidget(title, alignment=Qt.AlignCenter)

        self.status_label = QLabel("Loading candidate clips...")
        self.status_label.setStyleSheet("font-size: 14px; color: #666; margin-bottom: 15px;")
        layout.addWidget(self.status_label, alignment=Qt.AlignCenter)

        self.counter_label = QLabel(f"✓ Selected: {self.selected_count} clips")
        self.counter_label.setStyleSheet(
            "font-size: 18px; font-weight: bold; padding: 12px; "
            "background-color: #E3F2FD; border-radius: 6px; margin-bottom: 15px;"
        )
        self.counter_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.counter_label)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("QScrollArea { border: none; background: #F5F5F5; }")

        self.grid_widget = QWidget()
        self.grid_layout = QGridLayout(self.grid_widget)
        self.grid_layout.setSpacing(15)
        self.grid_layout.setContentsMargins(10, 10, 10, 10)

        scroll.setWidget(self.grid_widget)
        layout.addWidget(scroll)

        instructions = QLabel(
            "💡 Click any pair to toggle selection. Blue-highlighted pairs are AI recommendations.\n"
            "Primary (front) and partner (rear) cameras are shown side-by-side for each moment."
        )
        instructions.setStyleSheet("color: #666; font-style: italic; padding: 10px;")
        instructions.setAlignment(Qt.AlignCenter)
        instructions.setWordWrap(True)
        layout.addWidget(instructions)

        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(15)

        cancel_btn = QPushButton("Cancel & Stop Pipeline")
        cancel_btn.clicked.connect(self.reject)
        cancel_btn.setStyleSheet("padding: 12px 24px; font-size: 14px;")

        self.ok_btn = QPushButton(f"✓ Use {self.selected_count} Clips & Continue")
        self.ok_btn.clicked.connect(lambda: self.accept())
        self.ok_btn.setStyleSheet("""
            QPushButton {
                background-color: #007AFF;
                color: white;
                padding: 12px 24px;
                font-size: 14px;
                font-weight: bold;
                border-radius: 6px;
            }
            QPushButton:hover {
                background-color: #0051D5;
            }
        """)

        btn_layout.addWidget(cancel_btn)
        btn_layout.addWidget(self.ok_btn)
        layout.addLayout(btn_layout)

    def _apply_gap_recommendations(self, rows: List[Dict[str, str]]) -> List[Dict[str, str]]:
        """Ensure recommended clips comply with minimum gap spacing."""
        last_time = None
        min_gap_s = int(getattr(CFG, "MIN_GAP_BETWEEN_CLIPS", 90))
        for row in rows:
            ts = float(row.get("abs_time_epoch", 0) or 0.0)
            if row.get("recommended", "false") == "true":
                if last_time is None or (ts - last_time) >= min_gap_s:
                    last_time = ts
                else:
                    row["recommended"] = "false"
        return rows

    def _load_candidates(self):
        """Load candidates directly from select.csv."""
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

            rows.sort(key=lambda r: float(r.get("abs_time_epoch", 0) or 0.0))
            rows = self._apply_gap_recommendations(rows)

            self.candidates = rows
            self.selected_count = sum(1 for c in self.candidates if c.get("recommended", "false") == "true")

            self.counter_label.setText(f"✓ Selected: {self.selected_count} clips")
            self.ok_btn.setText(f"✓ Use {self.selected_count} Clips & Continue")

            status_text = (
                f"AI provided {len(self.candidates)} candidate clips | "
                f"Pre-selected: {self.selected_count}/{self.target_clips} target"
            )
            self.status_label.setText(status_text)

        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to load candidates: {e}")
            self.log(f"CSV load error: {e}", "error")
            self.reject()

    def showEvent(self, event):
        super().showEvent(event)
        QTimer.singleShot(100, self._populate_grid)

    def _populate_grid(self):
        """Populate grid with paired clip tiles (primary + partner side-by-side)."""
        if self.grid_layout.count() > 0:
            return

        # Display 2 pairs per row (2 columns, each containing a pair)
        pairs_per_row = 2

        for idx, candidate in enumerate(self.candidates):
            row = idx // pairs_per_row
            col = idx % pairs_per_row

            # Create pair container
            pair_widget = self._create_pair_widget(candidate)
            
            self.grid_layout.addWidget(pair_widget, row, col)

    def _create_pair_widget(self, candidate: Dict) -> QWidget:
        """Create a widget displaying primary + partner frames side-by-side."""
        pair_container = QFrame()
        pair_container.setFrameShape(QFrame.Box)
        pair_layout = QVBoxLayout(pair_container)
        pair_layout.setContentsMargins(8, 8, 8, 8)
        pair_layout.setSpacing(8)

        # Frames container (horizontal layout for side-by-side)
        frames_container = QWidget()
        frames_layout = QHBoxLayout(frames_container)
        frames_layout.setContentsMargins(0, 0, 0, 0)
        frames_layout.setSpacing(8)

        idx = candidate.get('index', '')
        
        # Primary frame (left)
        primary_frame = self._create_frame_widget(idx, "Primary", candidate)
        frames_layout.addWidget(primary_frame)

        # Partner frame (right)
        partner_frame = self._create_frame_widget(idx, "Partner", candidate)
        frames_layout.addWidget(partner_frame)

        pair_layout.addWidget(frames_container)

        # Metadata footer - use best available time field from CSV
        # Priority: adjusted_start_time (local) > abs_time_iso (UTC)
        time_str = candidate.get('adjusted_start_time') or candidate.get('abs_time_iso', 'N/A')
        if time_str != 'N/A' and 'T' in time_str:
            try:
                from datetime import datetime
                # Parse ISO format and convert to local time if needed
                dt = datetime.fromisoformat(time_str.replace('Z', '+00:00'))
                time_str = dt.astimezone().strftime('%Y-%m-%d %H:%M:%S')
            except Exception:
                pass  # Keep original if parsing fails
        
        metadata = QLabel(
            f"Time: {time_str}\n"
            f"Speed: {candidate.get('speed_kmh', 'N/A')} km/h | "
            f"Detection: {candidate.get('detect_score', 'N/A')}"
        )
        metadata.setAlignment(Qt.AlignCenter)
        metadata.setStyleSheet("font-size: 10px; color: #666;")
        pair_layout.addWidget(metadata)

        # Style based on selection state
        self._apply_pair_style(pair_container, candidate)

        # Make entire pair clickable
        pair_container.mousePressEvent = self._make_pair_toggle_handler(candidate, pair_container)

        return pair_container

    def _create_frame_widget(self, idx: str, frame_type: str, candidate: Dict) -> QWidget:
        """Create widget for a single frame (Primary or Partner)."""
        frame_widget = QWidget()
        frame_layout = QVBoxLayout(frame_widget)
        frame_layout.setContentsMargins(0, 0, 0, 0)
        frame_layout.setSpacing(4)

        # Camera label
        camera = candidate.get('camera', 'Unknown') if frame_type == "Primary" else candidate.get('partner_camera', 'Unknown')
        label = QLabel(f"{frame_type} ({camera})")
        label.setAlignment(Qt.AlignCenter)
        label.setStyleSheet("font-weight: bold; font-size: 11px;")
        frame_layout.addWidget(label)

        # Frame image
        frame_path = self.extract_dir / f"{idx}_{frame_type}.jpg"
        
        if frame_path.exists():
            pixmap = QPixmap(str(frame_path))
            if not pixmap.isNull():
                # Scale to reasonable thumbnail size
                pixmap = pixmap.scaled(340, 240, Qt.KeepAspectRatio, Qt.SmoothTransformation)
                image_label = QLabel()
                image_label.setPixmap(pixmap)
                image_label.setAlignment(Qt.AlignCenter)
                frame_layout.addWidget(image_label)
            else:
                fallback = QLabel(f"[{frame_type} load error]")
                fallback.setAlignment(Qt.AlignCenter)
                fallback.setMinimumSize(340, 240)
                frame_layout.addWidget(fallback)
        else:
            fallback = QLabel(f"[No {frame_type.lower()} camera]" if frame_type == "Partner" else f"[No image]")
            fallback.setAlignment(Qt.AlignCenter)
            fallback.setMinimumSize(340, 240)
            fallback.setStyleSheet("color: #999; background-color: #f0f0f0;")
            frame_layout.addWidget(fallback)

        return frame_widget

    def _apply_pair_style(self, widget: QWidget, candidate: Dict):
        """Apply visual styling based on selection state."""
        is_selected = candidate.get("recommended", "false") == "true"
        
        if is_selected:
            widget.setStyleSheet("""
                QFrame {
                    background-color: #BBDEFB;
                    border: 3px solid #1976D2;
                    border-radius: 8px;
                }
            """)
        else:
            widget.setStyleSheet("""
                QFrame {
                    background-color: #FAFAFA;
                    border: 2px solid #DDDDDD;
                    border-radius: 8px;
                }
            """)

    def _make_pair_toggle_handler(self, candidate: Dict, widget: QWidget):
        """Create click handler for toggling pair selection."""
        def handler(event):
            currently_selected = candidate.get("recommended", "false") == "true"
            new_selected = not currently_selected
            candidate["recommended"] = "true" if new_selected else "false"

            # Update visual styling
            self._apply_pair_style(widget, candidate)

            # Update counters
            if new_selected:
                self.selected_count += 1
            else:
                self.selected_count -= 1

            self.counter_label.setText(f"✓ Selected: {self.selected_count} clips")
            self.ok_btn.setText(f"✓ Use {self.selected_count} Clips & Continue")

        return handler

    def get_selected_indices(self) -> List[str]:
        """Return indices marked as selected."""
        return [c["index"] for c in self.candidates if c.get("recommended", "false") == "true"]

    def save_selection(self):
        """Save final selection to select.csv, preserving schema."""
        csv_path = select_path()

        if not self.candidates:
            with csv_path.open('w', newline='') as f:
                csv.writer(f).writerow(["index"])
            self.log("[manual] No candidates to save; wrote minimal header", "warning")
            return

        rows = sorted(self.candidates, key=lambda r: float(r.get("abs_time_epoch", 0) or 0.0))
        selected_count = sum(1 for r in rows if r.get("recommended", "false") == "true")

        message = f"[manual] Saving {len(rows)} candidates ({selected_count} recommended)"
        self.log(message, "info")
        log.info(message)

        try:
            fieldnames = list(rows[0].keys())
            with csv_path.open('w', newline='') as f:
                writer = csv.DictWriter(f, fieldnames=fieldnames)
                writer.writeheader()
                writer.writerows(rows)

            confirm_msg = f"[manual] Selection confirmed: {selected_count} clips selected"
            self.log(confirm_msg, "info")
            log.info(confirm_msg)

            success_msg = f"[manual] Successfully wrote {csv_path}"
            self.log(success_msg, "success")
            log.info(success_msg)

        except Exception as e:
            error_msg = f"[manual] FAILED to write {csv_path}: {e}"
            self.log(error_msg, "error")
            log.error(error_msg)
            raise