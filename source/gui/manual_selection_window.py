# source/gui/manual_selection_window.py
"""
Manual review dialog for clip selection.
Displays PAIRED clips (primary + partner side-by-side) instead of individual frames.
UPDATED: Clean, understated visual theme.
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
    Clean, understated visual design.
    """

    def __init__(self, project_dir: Path, parent=None):
        super().__init__(parent)
        self.project_dir = project_dir
        self.candidates: List[Dict[str, str]] = []
        self.extract_dir = frames_dir()
        _mk(self.extract_dir)
        self.selected_count = 0
        self.target_clips = int(CFG.HIGHLIGHT_TARGET_DURATION_S // CFG.CLIP_OUT_LEN_S)

        self.timestamp_widget_map = {} 
        self.timestamp_widgets = {}

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
        layout.setSpacing(15)

        # Title - clean typography
        title = QLabel("Review & Refine Clip Selection")
        title.setStyleSheet(
            "font-size: 22px; font-weight: 600; color: #1a1a1a; margin-bottom: 5px;"
        )
        layout.addWidget(title, alignment=Qt.AlignCenter)

        # Status label - understated
        self.status_label = QLabel("Loading candidate clips...")
        self.status_label.setStyleSheet(
            "font-size: 13px; color: #666; margin-bottom: 10px;"
        )
        layout.addWidget(self.status_label, alignment=Qt.AlignCenter)

        # Counter - subtle highlight
        self.counter_label = QLabel(f"Selected: {self.selected_count} clips")
        self.counter_label.setStyleSheet(
            "font-size: 16px; font-weight: 600; color: #2D7A4F; "
            "padding: 10px 20px; background-color: #F0F9F4; "
            "border: 2px solid #6EBF8B; border-radius: 6px; margin-bottom: 10px;"
        )
        self.counter_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.counter_label)

        # Scroll area - clean border
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("""
            QScrollArea {
                border: 1px solid #E5E5E5;
                background: #FAFAFA;
                border-radius: 4px;
            }
        """)

        self.grid_widget = QWidget()
        self.grid_layout = QGridLayout(self.grid_widget)
        self.grid_layout.setSpacing(15)
        self.grid_layout.setContentsMargins(10, 10, 10, 10)

        scroll.setWidget(self.grid_widget)
        layout.addWidget(scroll)

        # Instructions - subtle info
        instructions = QLabel(
            "💡 Click any pair to toggle selection. Selected pairs show with green borders."
        )
        instructions.setStyleSheet(
            "color: #666; font-size: 12px; font-style: italic; padding: 10px;"
        )
        instructions.setAlignment(Qt.AlignCenter)
        instructions.setWordWrap(True)
        layout.addWidget(instructions)

        # Button bar - clean styling
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(12)

        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        cancel_btn.setStyleSheet("""
            QPushButton {
                background-color: #FFFFFF;
                color: #333333;
                padding: 10px 24px;
                font-size: 14px;
                font-weight: 600;
                border: 2px solid #DDDDDD;
                border-radius: 6px;
            }
            QPushButton:hover {
                background-color: #F8F9FA;
                border-color: #CCCCCC;
            }
        """)

        self.ok_btn = QPushButton(f"Use {self.selected_count} Clips & Continue")
        self.ok_btn.clicked.connect(lambda: self.accept())
        self.ok_btn.setStyleSheet("""
            QPushButton {
                background-color: #2D7A4F;
                color: white;
                padding: 10px 24px;
                font-size: 14px;
                font-weight: 600;
                border: 2px solid #2D7A4F;
                border-radius: 6px;
            }
            QPushButton:hover {
                background-color: #246840;
                border-color: #246840;
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

            self.counter_label.setText(f"Selected: {self.selected_count} clips")
            self.ok_btn.setText(f"Use {self.selected_count} Clips & Continue")

            status_text = (
                f"Found {len(self.candidates)} candidate clips  •  "
                f"Pre-selected: {self.selected_count} / {self.target_clips} target"
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
        """Populate grid with exactly 2 widgets per reciprocal pair."""
        if self.grid_layout.count() > 0:
            return

        from collections import defaultdict
        
        timestamp_groups = defaultdict(list)
        for candidate in self.candidates:
            ts = candidate.get('abs_time_epoch', '0')
            timestamp_groups[ts].append(candidate)
        
        self.timestamp_widgets = {}
        
        widget_idx = 0
        for ts, rows in timestamp_groups.items():
            if len(rows) == 2:  # Reciprocal pair found
                fly12_row = next((r for r in rows if r.get('camera') == 'Fly12Sport'), None)
                fly6_row = next((r for r in rows if r.get('camera') == 'Fly6Pro'), None)
                
                if fly12_row and fly6_row:
                    # Widget 1: Fly12Sport on LEFT, Fly6Pro on RIGHT
                    widget1 = self._create_pair_widget(fly12_row, fly6_row, ts, 0)
                    self.grid_layout.addWidget(widget1, widget_idx // 2, 0)
                    
                    # Widget 2: Fly6Pro on LEFT, Fly12Sport on RIGHT
                    widget2 = self._create_pair_widget(fly6_row, fly12_row, ts, 1)
                    self.grid_layout.addWidget(widget2, widget_idx // 2, 1)
                    
                    # Store for cross-reference
                    self.timestamp_widgets[ts] = [widget1, widget2]
                    widget_idx += 2

    def _create_pair_widget(self, primary_row: Dict, secondary_row: Dict, ts: str, position: int) -> QWidget:
        """Create widget showing primary_row's camera on left, secondary_row's on right."""
        pair_container = QFrame()
        pair_container.timestamp = ts
        pair_container.position = position
        pair_layout = QVBoxLayout(pair_container)
        pair_layout.setContentsMargins(8, 8, 8, 8)
        pair_layout.setSpacing(8)

        # Store references for toggle handler
        pair_container.primary_row = primary_row
        pair_container.secondary_row = secondary_row

        # Frames container
        frames_container = QWidget()
        frames_layout = QHBoxLayout(frames_container)
        frames_layout.setContentsMargins(0, 0, 0, 0)
        frames_layout.setSpacing(8)

        # LEFT: Primary camera frame
        primary_idx = primary_row['index']
        primary_frame = self._create_frame_widget(primary_idx, "Primary", primary_row)
        frames_layout.addWidget(primary_frame)

        # RIGHT: Partner camera frame (load from secondary row)
        secondary_idx = secondary_row['index']
        partner_frame = self._create_frame_widget(secondary_idx, "Partner", secondary_row)
        frames_layout.addWidget(partner_frame)

        pair_layout.addWidget(frames_container)

        # FIXED: Define time_str before using it
        time_str = primary_row.get('adjusted_start_time') or primary_row.get('abs_time_iso', 'N/A')
        if time_str != 'N/A' and 'T' in time_str:
            try:
                from datetime import datetime
                dt = datetime.fromisoformat(time_str.replace('Z', '+00:00'))
                time_str = dt.astimezone().strftime('%Y-%m-%d %H:%M:%S')
            except Exception:
                pass

        # Metadata - now time_str is defined
        metadata = QLabel(
            f"Time: {time_str}\n"
            f"Front: {primary_row.get('speed_kmh', 'N/A')} km/h | "
            f"Detection: {primary_row.get('detect_score', 'N/A')} | "
            f"Area: {primary_row.get('bbox_area', 'N/A')}\n"
            f"Rear: {secondary_row.get('speed_kmh', 'N/A')} km/h | "
            f"Detection: {secondary_row.get('detect_score', 'N/A')} | "
            f"Area: {secondary_row.get('bbox_area', 'N/A')}"
        )
        metadata.setAlignment(Qt.AlignCenter)
        metadata.setStyleSheet("font-size: 10px; color: #666;")
        metadata.setWordWrap(True)
        pair_layout.addWidget(metadata)

        # Style and click handler
        self._apply_pair_style(pair_container, primary_row)
        pair_container.mousePressEvent = self._make_pair_toggle_handler(pair_container)
        
        return pair_container


    def _create_frame_widget(self, idx: str, frame_type: str, candidate: Dict) -> QWidget:
        """Create single frame widget - always loads the PRIMARY frame for that camera."""
        frame_widget = QWidget()
        frame_layout = QVBoxLayout(frame_widget)
        frame_layout.setContentsMargins(0, 0, 0, 0)
        frame_layout.setSpacing(4)

        # Camera label
        camera = candidate.get('camera', 'Unknown')
        label = QLabel(f"{frame_type} ({camera})")
        label.setAlignment(Qt.AlignCenter)
        label.setStyleSheet("font-weight: bold; font-size: 11px;")
        frame_layout.addWidget(label)

        # FIXED: Always load the PRIMARY frame for this camera
        frame_path = self.extract_dir / f"{idx}_Primary.jpg"
        
        if frame_path.exists():
            pixmap = QPixmap(str(frame_path))
            if not pixmap.isNull():
                pixmap = pixmap.scaled(340, 240, Qt.KeepAspectRatio, Qt.SmoothTransformation)
                image_label = QLabel()
                image_label.setPixmap(pixmap)
                image_label.setAlignment(Qt.AlignCenter)
                frame_layout.addWidget(image_label)
            else:
                fallback = QLabel(f"[Error loading {Path(idx).name}]")
                fallback.setAlignment(Qt.AlignCenter)
                fallback.setMinimumSize(340, 240)
                frame_layout.addWidget(fallback)
        else:
            # Show which frame is missing for debugging
            fallback = QLabel(f"[Missing: {Path(idx).name}]")
            fallback.setAlignment(Qt.AlignCenter)
            fallback.setMinimumSize(340, 240)
            fallback.setStyleSheet("color: #999; background-color: #f0f0f0;")
            frame_layout.addWidget(fallback)

        return frame_widget


    def _apply_pair_style(self, widget: QWidget, primary_row: Dict):
        """Apply style based on whether THIS WIDGET'S PRIMARY row is selected."""
        is_selected = primary_row.get("recommended", "false") == "true"
        
        widget.setStyleSheet(f"""
            QFrame {{
                background-color: {'#BBDEFB' if is_selected else '#FAFAFA'};
                border: {'3' if is_selected else '2'}px solid {'#1976D2' if is_selected else '#DDDDDD'};
                border-radius: 8px;
            }}
        """)

    def _make_pair_toggle_handler(self, widget: QWidget):
        """Toggle selection - properly identifies the clicked widget."""
        def handler(event):
            ts = widget.timestamp
            
            # Get both widgets for this timestamp
            if ts not in self.timestamp_widgets:
                return
            
            widgets = self.timestamp_widgets[ts]
            
            # CORRECT: Identify which widget was ACTUALLY clicked
            # widget is the one that received the click event
            clicked_widget = widget
            other_widget = widgets[0] if widget is widgets[1] else widgets[1]
            
            # Toggle logic
            if clicked_widget.primary_row["recommended"] == "true":
                # Deselect - remove recommendation from both rows
                clicked_widget.primary_row["recommended"] = "false"
                other_widget.primary_row["recommended"] = "false"
            else:
                # Select clicked widget - ONLY its primary row gets recommended
                clicked_widget.primary_row["recommended"] = "true"
                other_widget.primary_row["recommended"] = "false"
            
            # Update BOTH widget styles
            self._apply_pair_style(widgets[0], widgets[0].primary_row)
            self._apply_pair_style(widgets[1], widgets[1].primary_row)
            
            # Update counter (unique timestamps with any selection)
            self.selected_count = sum(
                1 for w1, w2 in self.timestamp_widgets.values()
                if w1.primary_row["recommended"] == "true" or w2.primary_row["recommended"] == "true"
            )
            self.counter_label.setText(f"✓ Selected: {self.selected_count} clips")
            self.ok_btn.setText(f"✓ Use {self.selected_count} Clips & Continue")
        
        return handler
 
    def get_selected_indices(self) -> List[str]:
        """Return ONE index per selected moment (preferring Fly12Sport)."""
        selected_indices = []
        
        for ts, (w1, w2) in self.timestamp_widgets.items():
            if w1.primary_row["recommended"] == "true":
                # Widget 1 stores Fly12Sport in primary_row
                selected_indices.append(w1.primary_row["index"])
            elif w2.primary_row["recommended"] == "true":
                # Widget 2 stores Fly6Pro in primary_row - but we want Fly12Sport
                # Fly12Sport is in w2.secondary_row
                selected_indices.append(w2.secondary_row["index"])
        
        return sorted(selected_indices)
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