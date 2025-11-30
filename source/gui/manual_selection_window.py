# source/gui/manual_selection_window.py
"""
Manual review dialog for clip selection.
Displays PAIRED clips with reciprocal pairing support.
- Each moment shows 2 widgets: Fly12Sport primary + Fly6Pro primary
- Clicking either widget selects that camera angle as the primary
- Auto-deselects the reciprocal pair
"""

import csv
from pathlib import Path
from typing import List, Dict, Optional

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
    """Manual review dialog with reciprocal pairing support."""

    def __init__(self, project_dir: Path, parent=None):
        super().__init__(parent)
        self.project_dir = project_dir
        self.candidates: List[Dict[str, str]] = []
        self.extract_dir = frames_dir()
        _mk(self.extract_dir)
        self.selected_count = 0
        self.target_clips = int(CFG.HIGHLIGHT_TARGET_DURATION_S // CFG.CLIP_OUT_LEN_S)

        # Map index → row for fast lookup
        self.index_to_row: Dict[str, Dict] = {}
        
        # Map index → widget for reciprocal updates
        self.index_to_widget: Dict[str, QWidget] = {}

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

        # Title
        title = QLabel("Review & Refine Clip Selection")
        title.setStyleSheet(
            "font-size: 22px; font-weight: 600; color: #1a1a1a; margin-bottom: 5px;"
        )
        layout.addWidget(title, alignment=Qt.AlignCenter)

        # Status label
        self.status_label = QLabel("Loading candidate clips...")
        self.status_label.setStyleSheet(
            "font-size: 13px; color: #666; margin-bottom: 10px;"
        )
        layout.addWidget(self.status_label, alignment=Qt.AlignCenter)

        # Counter
        self.counter_label = QLabel(f"Selected: {self.selected_count} clips")
        self.counter_label.setStyleSheet(
            "font-size: 16px; font-weight: 600; color: #2D7A4F; "
            "padding: 10px 20px; background-color: #F0F9F4; "
            "border: 2px solid #6EBF8B; border-radius: 6px; margin-bottom: 10px;"
        )
        self.counter_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.counter_label)

        # Scroll area
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

        # Instructions
        instructions = QLabel(
            "💡 Click any pair to select that camera angle. Selected pairs show with green borders.\n"
            "Reciprocal pairs (same moment, different camera) are automatically managed."
        )
        instructions.setStyleSheet(
            "color: #666; font-size: 12px; font-style: italic; padding: 10px;"
        )
        instructions.setAlignment(Qt.AlignCenter)
        instructions.setWordWrap(True)
        layout.addWidget(instructions)

        # Button bar
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

    def _load_candidates(self):
        """Load candidates from select.csv and build index."""
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
            self.candidates = rows
            
            # Build index lookup
            for row in rows:
                self.index_to_row[row["index"]] = row
            
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
        """Populate grid with one widget per row in select.csv, showing index + partner_index frames."""
        if self.grid_layout.count() > 0:
            return

        # Sort rows by time for stable order
        rows = sorted(self.candidates, key=lambda r: float(r.get("abs_time_epoch", 0) or 0.0))

        widget_idx = 0
        for row in rows:
            try:
                widget = self._create_frame_widget(row)
                self.grid_layout.addWidget(widget, widget_idx // 2, widget_idx % 2)

                # Map this row’s index to its widget
                self.index_to_widget[row["index"]] = widget

                widget_idx += 1
            except Exception as e:
                self.log(f"Failed to create widget for {row.get('index')}: {e}", "error")

        # Update counter based on row-level recommended
        self.selected_count = sum(1 for r in self.candidates if r.get("recommended", "false") == "true")
        self.counter_label.setText(f"Selected: {self.selected_count} clips")
        self.ok_btn.setText(f"Use {self.selected_count} Clips & Continue")



    def _create_frame_widget(self, row: Dict) -> QWidget:
        """Create widget showing primary frame with partner (if available)."""
        container = QFrame()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(8)

        # Store reference for toggle handler
        container.row_data = row

        # Get partner info
        partner_index = row.get("partner_index", "")
        partner_row = self.index_to_row.get(partner_index) if partner_index else None

        # Frames container
        frames_container = QWidget()
        frames_layout = QHBoxLayout(frames_container)
        frames_layout.setContentsMargins(0, 0, 0, 0)
        frames_layout.setSpacing(8)

        # LEFT: Primary frame
        primary_frame = self._create_single_frame(
            row["index"], 
            f"Primary ({row.get('camera', 'Unknown')})"
        )
        frames_layout.addWidget(primary_frame)

        # RIGHT: Partner frame (if exists)
        if partner_row:
            partner_frame = self._create_single_frame(
                partner_row["index"],
                f"Partner ({partner_row.get('camera', 'Unknown')})"
            )
            frames_layout.addWidget(partner_frame)
        else:
            # Show placeholder for unpaired
            placeholder = QLabel("⚠️ No Partner\nCamera")
            placeholder.setAlignment(Qt.AlignCenter)
            placeholder.setMinimumSize(340, 240)
            placeholder.setStyleSheet(
                "color: #999; background-color: #f0f0f0; "
                "border: 2px dashed #ddd; border-radius: 4px;"
            )
            frames_layout.addWidget(placeholder)

        layout.addWidget(frames_container)

        # Metadata
        time_str = row.get('adjusted_start_time') or row.get('abs_time_iso', 'N/A')
        if time_str != 'N/A' and 'T' in time_str:
            try:
                from datetime import datetime
                dt = datetime.fromisoformat(time_str.replace('Z', '+00:00'))
                time_str = dt.astimezone().strftime('%Y-%m-%d %H:%M:%S')
            except Exception:
                pass

        metadata_lines = [f"Time: {time_str}"]
        
        # Primary camera info
        metadata_lines.append(
            f"Primary: {row.get('speed_kmh', 'N/A')} km/h | "
            f"Detection: {row.get('detect_score', 'N/A')} | "
            f"Scene: {row.get('scene_boost', 'N/A')}"
        )
        
        # Partner camera info (if exists)
        if partner_row:
            metadata_lines.append(
                f"Partner: {partner_row.get('speed_kmh', 'N/A')} km/h | "
                f"Detection: {partner_row.get('detect_score', 'N/A')} | "
                f"Scene: {partner_row.get('scene_boost', 'N/A')}"
            )

        metadata = QLabel("\n".join(metadata_lines))
        metadata.setAlignment(Qt.AlignCenter)
        metadata.setStyleSheet("font-size: 10px; color: #666;")
        metadata.setWordWrap(True)
        layout.addWidget(metadata)

        # Style and click handler
        self._apply_style(container, row)
        container.mousePressEvent = self._make_toggle_handler(container)
        
        return container

    def _create_single_frame(self, idx: str, label_text: str) -> QWidget:
        """Create single frame image widget."""
        frame_widget = QWidget()
        frame_layout = QVBoxLayout(frame_widget)
        frame_layout.setContentsMargins(0, 0, 0, 0)
        frame_layout.setSpacing(4)

        # Label
        label = QLabel(label_text)
        label.setAlignment(Qt.AlignCenter)
        label.setStyleSheet("font-weight: bold; font-size: 11px;")
        frame_layout.addWidget(label)

        # Image
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
                fallback = QLabel(f"[Error loading image]")
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

    def _apply_style(self, widget: QWidget, row: Dict):
        """Apply style based on selection state."""
        is_selected = row.get("recommended", "false") == "true"
        
        widget.setStyleSheet(f"""
            QFrame {{
                background-color: {'#E8F5E9' if is_selected else '#FAFAFA'};
                border: {'3' if is_selected else '2'}px solid {'#4CAF50' if is_selected else '#DDDDDD'};
                border-radius: 8px;
            }}
        """)

    def _make_toggle_handler(self, widget: QWidget):
        """Create toggle handler with reciprocal pair logic."""
        def handler(event):
            row = widget.row_data
            current_index = row["index"]
            partner_index = row.get("partner_index", "")
            
            # Get current state
            is_currently_selected = row.get("recommended", "false") == "true"
            
            if is_currently_selected:
                # Deselect this frame
                row["recommended"] = "false"
                self._apply_style(widget, row)
            else:
                # Select this frame
                row["recommended"] = "true"
                self._apply_style(widget, row)
                
                # RECIPROCAL LOGIC: If partner exists and is also selected, deselect it
                if partner_index:
                    partner_row = self.index_to_row.get(partner_index)
                    if partner_row and partner_row.get("recommended", "false") == "true":
                        # Partner is the reciprocal pair - deselect it
                        partner_row["recommended"] = "false"
                        
                        # Update partner widget if it exists
                        partner_widget = self.index_to_widget.get(partner_index)
                        if partner_widget:
                            self._apply_style(partner_widget, partner_row)
                            self.log(
                                f"Auto-deselected reciprocal: {partner_row.get('camera')} "
                                f"(selected {row.get('camera')} instead)",
                                "info"
                            )
            
            # Update counter
            self.selected_count = sum(
                1 for c in self.candidates 
                if c.get("recommended", "false") == "true"
            )
            self.counter_label.setText(f"✓ Selected: {self.selected_count} clips")
            self.ok_btn.setText(f"✓ Use {self.selected_count} Clips & Continue")
        
        return handler

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