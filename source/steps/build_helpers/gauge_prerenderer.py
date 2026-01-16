# source/steps/build_helpers/gauge_prerenderer.py
"""
Pre-render composite gauge overlays for all clips.
Combines all enabled gauges into a single PNG matching PIP size.
"""

from __future__ import annotations
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Dict, List
from PIL import Image

from ...config import DEFAULT_CONFIG as CFG
from ...utils.log import setup_logger
from ...utils.hardware import get_worker_count
from ...utils.draw_gauge import (
    draw_speed_gauge,
    draw_cadence_gauge,
    draw_hr_gauge,
    draw_elev_gauge,
    draw_gradient_gauge,
)
from ...utils.gauge_overlay import compute_gauge_maxes
from ...io_paths import _mk, select_path
from ...utils.progress_reporter import report_progress

log = setup_logger("steps.build_helpers.gauge_prerenderer")


class GaugePrerenderer:
    """Pre-renders composite gauge overlays for all selected clips."""

    def __init__(self, output_dir: Path):
        """
        Args:
            output_dir: Directory to save composite gauge images
        """
        self.output_dir = _mk(output_dir)
        self.gauge_maxes = compute_gauge_maxes(select_path())

        # Composite canvas size (matches PIP)
        self.width, self.height = CFG.GAUGE_COMPOSITE_SIZE
        self.layout = CFG.GAUGE_LAYOUT
        self.enabled = CFG.ENABLED_GAUGES

    def prerender_all(self, rows: List[Dict]) -> Dict[int, Path]:
        """
        Pre-render composite gauge images for all clips using parallel processing.

        Args:
            rows: List of clip metadata dicts from select.csv

        Returns:
            Dict mapping clip_idx -> composite_gauge_path
        """
        num_workers = get_worker_count('io')
        log.info(
            f"[gauge] Pre-rendering {len(rows)} composite gauges "
            f"({self.width}x{self.height}px, layout={self.layout}) "
            f"with {num_workers} workers..."
        )
        paths: Dict[int, Path] = {}

        with ThreadPoolExecutor(max_workers=num_workers) as executor:
            futures = {
                executor.submit(self._render_single, row, idx): idx
                for idx, row in enumerate(rows, start=1)
            }

            completed = 0
            for future in as_completed(futures, timeout=300):  # 5 min timeout
                idx = futures[future]
                completed += 1
                try:
                    result = future.result(timeout=30)  # 30s per gauge
                    if result:
                        paths[idx] = result
                except TimeoutError:
                    log.warning(f"[gauge] Timeout rendering composite for clip {idx}")
                except Exception as e:
                    log.warning(f"[gauge] Failed to render composite for clip {idx}: {e}")

                if completed % 10 == 0 or completed == len(rows):
                    report_progress(
                        completed, len(rows),
                        f"Rendered {completed}/{len(rows)} gauge composites"
                    )

        log.info(f"[gauge] Successfully rendered {len(paths)} composite gauges")
        return paths

    def _render_single(self, row: Dict, idx: int) -> Path | None:
        """Render single composite gauge for a clip."""
        # Create transparent canvas
        canvas = Image.new("RGBA", (self.width, self.height), (0, 0, 0, 0))

        # Extract telemetry values
        telemetry = {
            "speed": float(row.get("speed_kmh") or 0.0),
            "cadence": float(row.get("cadence_rpm") or 0.0),
            "hr": float(row.get("hr_bpm") or 0.0),
            "elev": float(row.get("elevation") or 0.0),
            "gradient": float(row.get("gradient_pct") or 0.0),
        }

        # Get positions for current layout
        positions = self._calculate_positions()

        # Draw each enabled gauge
        for gauge_type in self.enabled:
            if gauge_type not in positions:
                continue

            x, y, size = positions[gauge_type]
            value = telemetry.get(gauge_type, 0.0)
            max_val = self.gauge_maxes.get(gauge_type, 100.0)

            # Create gauge image
            gauge_img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
            rect = (0, 0, size, size)

            if gauge_type == "speed":
                draw_speed_gauge(gauge_img, rect, value, max_val)
            elif gauge_type == "cadence":
                draw_cadence_gauge(gauge_img, rect, value, max_val)
            elif gauge_type == "hr":
                draw_hr_gauge(gauge_img, rect, value, max_val)
            elif gauge_type == "elev":
                draw_elev_gauge(gauge_img, rect, value, max_val)
            elif gauge_type == "gradient":
                min_val = -self.gauge_maxes.get("gradient", 10.0)
                draw_gradient_gauge(gauge_img, rect, value, min_val, max_val)

            # Paste onto canvas
            canvas.paste(gauge_img, (x, y), gauge_img)

        out_path = self.output_dir / f"gauge_composite_{idx:04d}.png"
        canvas.save(out_path)
        return out_path

    def _calculate_positions(self) -> Dict[str, tuple[int, int, int]]:
        """
        Calculate gauge positions based on layout mode.

        Returns:
            Dict mapping gauge_type -> (x, y, size)
        """
        w, h = self.width, self.height
        speed_size = min(CFG.SPEED_GAUGE_SIZE, h - 20)  # Fit within height
        small_size = min(CFG.SMALL_GAUGE_SIZE, (h - 20) // 2)

        if self.layout == "strip":
            # Horizontal strip: all gauges in a row, equal sizes
            gauge_size = min(w // 5 - 10, h - 20)
            spacing = (w - gauge_size * 5) // 6
            return {
                "hr": (spacing, (h - gauge_size) // 2, gauge_size),
                "cadence": (spacing * 2 + gauge_size, (h - gauge_size) // 2, gauge_size),
                "speed": (spacing * 3 + gauge_size * 2, (h - gauge_size) // 2, gauge_size),
                "elev": (spacing * 4 + gauge_size * 3, (h - gauge_size) // 2, gauge_size),
                "gradient": (spacing * 5 + gauge_size * 4, (h - gauge_size) // 2, gauge_size),
            }

        # Default: cluster layout
        # Speed gauge centered at bottom, small gauges in corners
        speed_x = (w - speed_size) // 2
        speed_y = h - speed_size - 10

        # Small gauges positioned around speed
        margin = 5
        return {
            "speed": (speed_x, speed_y, speed_size),
            "hr": (margin, margin, small_size),  # Top-left
            "cadence": (w - small_size - margin, margin, small_size),  # Top-right
            "elev": (margin, h - small_size - margin, small_size),  # Bottom-left
            "gradient": (w - small_size - margin, h - small_size - margin, small_size),  # Bottom-right
        }
