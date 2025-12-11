# source/gui/manual_selection_window.py

import csv
import logging
from pathlib import Path
from typing import List, Dict

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QScrollArea, QWidget, QGridLayout, QMessageBox, QFrame
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap, QPainter

from source.config import DEFAULT_CONFIG as CFG
from source.io_paths import select_path, frames_dir, _mk
from source.utils.log import setup_logger

log = setup_logger("gui.manual_selection_window")


class ManualSelectionWindow(QDialog):
    """Manual selection window with PiP layout for reciprocal pairs."""
    
    def __init__(self, project_dir: Path, parent=None):
        super().__init__(parent)
        self.project_dir = project_dir
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

    def log(self, message: str, level: str = "info"):
        """Route messages to parent GUI log panel or fallback to file logger."""
        if self.parent() and hasattr(self.parent(), 'log'):
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

        # Title
        title = QLabel("Review & Refine Clip Selection")
        title.setStyleSheet("font-size: 22px; font-weight: 600; color: #1a1a1a; margin-bottom: 5px;")
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

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("QScrollArea { border: 1px solid #E5E5E5; background: #FAFAFA; border-radius: 4px; }")

        self.grid_widget = QWidget()
        self.grid_layout = QGridLayout(self.grid_widget)
        self.grid_layout.setSpacing(20)
        self.grid_layout.setContentsMargins(10, 10, 10, 10)

        scroll.setWidget(self.grid_widget)
        layout.addWidget(scroll)

        instructions = QLabel(
            "💡 Click a perspective card to select/deselect that camera angle.\n"
            "Both views shown: primary (main) with partner (PiP overlay).\n"
            "Only one perspective per moment can be selected."
        )
        instructions.setStyleSheet("color: #666; font-size: 12px; font-style: italic; padding: 10px;")
        instructions.setAlignment(Qt.AlignCenter)
        instructions.setWordWrap(True)
        layout.addWidget(instructions)

        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(12)

        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        cancel_btn.setStyleSheet("""
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
        """)

        self.ok_btn = QPushButton(f"Use {self.selected_count} Clips & Continue")
        self.ok_btn.clicked.connect(lambda: self.accept())
        self.ok_btn.setStyleSheet("""
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
        """)

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

            self.log(f"Loaded {len(rows)} rows from select.csv", "info")
            
            # Build index for partner lookups
            index_map = {r.get("index", ""): r for r in rows if r.get("index")}
            self.log(f"Built index with {len(index_map)} entries", "debug")
            
            # Group by exact epoch - use partner_index for precise pairing
            from collections import defaultdict
            timeslot_groups = defaultdict(list)
            
            # First pass: group by partner relationships
            paired_indices = set()
            moments_by_index = {}
            
            for row in rows:
                idx = row.get("index", "")
                partner_idx = row.get("partner_index", "")
                
                # Skip if already paired
                if idx in paired_indices:
                    continue
                
                # Find partner
                partner_row = index_map.get(partner_idx) if partner_idx else None
                
                if partner_row and partner_idx not in paired_indices:
                    # Valid pair found
                    paired_indices.add(idx)
                    paired_indices.add(partner_idx)
                    
                    # Create moment (use epoch from first row)
                    epoch = float(row.get("abs_time_epoch", 0) or 0.0)
                    moment_key = f"{idx}_{partner_idx}"
                    moments_by_index[moment_key] = (epoch, row, partner_row)
            
            self.log(f"Found {len(moments_by_index)} valid pairs from {len(rows)} rows", "info")
            self.log(f"Paired {len(paired_indices)} indices, unpaired: {len(rows) - len(paired_indices)}", "debug")
            
            # Build moments from paired data, sorted by time
            self.moments = []
            
            for moment_key, (epoch, row1, row2) in sorted(moments_by_index.items(), key=lambda x: x[1][0]):
                # Verify cameras are different
                cam1 = row1.get("camera", "")
                cam2 = row2.get("camera", "")
                
                if cam1 == cam2:
                    self.log(f"Skipping same-camera pair: {cam1}", "warning")
                    continue
                
                # Create moment - include ALL pairs, not just recommended
                moment = {
                    "epoch": epoch,
                    "row1": row1,
                    "row2": row2,
                    "rows": [row1, row2],
                }
                self.moments.append(moment)
                
                # Log details including recommendation status
                rec1 = row1.get("recommended", "false")
                rec2 = row2.get("recommended", "false")
                time_diff = abs(float(row1.get("abs_time_epoch", 0)) - float(row2.get("abs_time_epoch", 0)))
                
                self.log(
                    f"Moment {len(self.moments)}: {cam1} ↔ {cam2} "
                    f"(Δt={time_diff:.3f}s, rec: {rec1}/{rec2})",
                    "debug"
                )

            # Count how many are pre-selected by AI
            self.selected_count = sum(
                1 for m in self.moments if any(r.get("recommended") == "true" for r in m["rows"])
            )
            
            total_moments = len(self.moments)
            self.log(
                f"Created {total_moments} moments total, "
                f"{self.selected_count} pre-selected by AI ({self.selected_count/total_moments*100:.1f}%)", 
                "success"
            )
            
            self.counter_label.setText(f"Selected: {self.selected_count} / {total_moments} clips")
            self.ok_btn.setText(f"Use {self.selected_count} Clips & Continue")
            self.status_label.setText(
                f"Showing {total_moments} moments (candidate pool)  •  "
                f"Pre-selected: {self.selected_count} / {self.target_clips} target  •  "
                f"Pool ratio: {total_moments/self.target_clips:.1f}x"
            )
            
            if len(self.moments) == 0:
                QMessageBox.warning(
                    self, 
                    "No Paired Moments", 
                    f"No valid camera pairs found from {len(rows)} rows.\n\n"
                    "Check that:\n"
                    "• Both cameras recorded simultaneously\n"
                    "• Rows are properly paired in select.csv\n"
                    "• Camera time alignment is correct"
                )
                self.reject()
                
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to load candidates: {e}")
            self.log(f"CSV load error: {e}", "error")
            import traceback
            self.log(traceback.format_exc(), "error")
            self.reject()

    def _populate_grid(self):
        while self.grid_layout.count():
            item = self.grid_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        # 2 columns layout: both perspectives of same moment side-by-side
        for row_idx, moment in enumerate(self.moments):
            try:
                # Create both perspective cards for this moment
                card1 = self._create_perspective_card(moment, 0)  # row1 as primary
                card2 = self._create_perspective_card(moment, 1)  # row2 as primary
                
                # Place both perspectives side-by-side in same row
                self.grid_layout.addWidget(card1, row_idx, 0)
                self.grid_layout.addWidget(card2, row_idx, 1)
                
            except Exception as e:
                self.log(f"Failed to create widget for moment {row_idx}: {e}", "error")

    def _create_perspective_card(self, moment: Dict, primary_idx: int) -> QWidget:
        """Create a perspective card with PiP layout."""
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
        time_str = primary_row.get('abs_time_iso') or primary_row.get('adjusted_start_time') or 'N/A'
        camera_label = primary_row.get("camera", "Camera")
        
        metadata_lines = [
            f"Time: {time_str}",
            f"Primary: {camera_label}",
            self._fmt_meta(primary_row),
        ]
        
        metadata = QLabel("\n".join(metadata_lines))
        metadata.setAlignment(Qt.AlignCenter)
        metadata.setStyleSheet("font-size: 11px; color: #666;")
        metadata.setWordWrap(True)
        layout.addWidget(metadata)

        # Click handler
        container.mousePressEvent = lambda e: self._on_perspective_selected(container)

        # Apply selection styling
        self._apply_perspective_style(container, primary_row)
        
        return container

    def _create_pip_widget(self, primary_row: Dict, partner_row: Dict) -> QLabel:
        """Create a QLabel with PiP composite image."""
        label = QLabel()
        label.setAlignment(Qt.AlignCenter)
        
        # Load images
        primary_idx = primary_row.get("index", "")
        partner_idx = partner_row.get("index", "")
        
        primary_path = self.extract_dir / f"{primary_idx}_Primary.jpg"
        partner_path = self.extract_dir / f"{partner_idx}_Primary.jpg"
        
        if not primary_path.exists():
            label.setText(f"[Missing: {primary_path.name}]")
            label.setStyleSheet("color: #999; background-color: #f0f0f0;")
            label.setMinimumSize(640, 360)
            return label
        
        # Create composite
        composite = self._create_pip_composite(primary_path, partner_path)
        if composite:
            label.setPixmap(composite)
        else:
            label.setText("[Error creating PiP]")
            label.setMinimumSize(640, 360)
        
        return label

    def _create_pip_composite(self, primary_path: Path, partner_path: Path) -> QPixmap:
        """Create PiP composite from two images."""
        # Load primary
        primary = QPixmap(str(primary_path))
        if primary.isNull():
            return None
        
        # Scale to display size (16:9 aspect ratio)
        display_width = 640
        display_height = 360
        primary = primary.scaled(
            display_width, display_height,
            Qt.KeepAspectRatio,
            Qt.SmoothTransformation
        )
        
        # Load partner if available
        if partner_path.exists():
            partner = QPixmap(str(partner_path))
            if not partner.isNull():
                # PiP sizing (30% of primary width)
                pip_scale = 0.30
                pip_margin = 15
                pip_width = int(display_width * pip_scale)
                pip_height = int(pip_width * 9 / 16)  # Maintain 16:9
                
                partner = partner.scaled(
                    pip_width, pip_height,
                    Qt.KeepAspectRatio,
                    Qt.SmoothTransformation
                )
                
                # Composite: overlay partner on bottom-right of primary
                painter = QPainter(primary)
                pip_x = display_width - pip_width - pip_margin
                pip_y = display_height - pip_height - pip_margin
                
                # Draw semi-transparent background for PiP
                painter.setOpacity(0.95)
                painter.drawPixmap(pip_x, pip_y, partner)
                painter.end()
        
        return primary

    def _fmt_meta(self, r: Dict) -> str:
        """Format metadata for a given row."""
        parts = []
        if r.get('speed_kmh'):
            parts.append(f"Speed {r['speed_kmh']} km/h")
        if r.get('detect_score'):
            parts.append(f"Detection {r['detect_score']}")
        if r.get('scene_boost'):
            parts.append(f"Scene {r['scene_boost']}")
        return " | ".join(parts) if parts else "—"

    def _apply_perspective_style(self, container: QFrame, row: Dict):
        """Apply styling based on selection state."""
        is_selected = row.get("recommended") == "true"
        container.setStyleSheet(f"""
            QFrame {{
                background-color: {'#E8F5E9' if is_selected else '#FAFAFA'};
                border: {'3' if is_selected else '2'}px solid {'#4CAF50' if is_selected else '#DDDDDD'};
                border-radius: 8px;
            }}
            QFrame:hover {{
                border-color: {'#2E7D32' if is_selected else '#999999'};
                background-color: {'#C8E6C9' if is_selected else '#F5F5F5'};
            }}
        """)

    def _on_perspective_selected(self, container: QFrame):
        """Handle perspective card selection."""
        moment = container.moment_data
        primary_idx = container.primary_idx
        
        selected_row = moment["rows"][primary_idx]
        other_row = moment["rows"][1 - primary_idx]
        
        # Toggle selection
        currently_selected = selected_row.get("recommended") == "true"
        
        if currently_selected:
            # Deselect this perspective
            selected_row["recommended"] = "false"
        else:
            # Select this perspective, deselect other
            selected_row["recommended"] = "true"
            other_row["recommended"] = "false"

        # Update all cards for this moment
        for i in range(self.grid_layout.count()):
            widget = self.grid_layout.itemAt(i).widget()
            if isinstance(widget, QFrame) and hasattr(widget, "moment_data"):
                if widget.moment_data == moment:
                    row_idx = widget.primary_idx
                    self._apply_perspective_style(widget, moment["rows"][row_idx])

        # Update counter
        self.selected_count = sum(
            1 for m in self.moments
            if any(r.get("recommended") == "true" for r in m["rows"])
        )
        self.counter_label.setText(f"✓ Selected: {self.selected_count} clips")
        self.ok_btn.setText(f"✓ Use {self.selected_count} Clips & Continue")

    def save_selection(self):
        """Save selection back to CSV."""
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

        try:
            fieldnames = list(all_rows[0].keys())
            with csv_path.open('w', newline='') as f:
                writer = csv.DictWriter(f, fieldnames=fieldnames)
                writer.writeheader()
                writer.writerows(all_rows)
            self.log(f"[manual] Selection confirmed: {selected_count} clips selected", "success")
        except Exception as e:
            self.log(f"[manual] FAILED to write {csv_path}: {e}", "error")
            raise