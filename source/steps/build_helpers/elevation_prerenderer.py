# source/steps/build_helpers/elevation_prerenderer.py
"""
Pre-render elevation profile plots for all clips.
"""

from __future__ import annotations
from pathlib import Path
from typing import Dict, List

from ...utils.log import setup_logger
from ...utils.elevation_plot import load_elevation_data, render_elevation_plot
from ...io_paths import flatten_path, _mk
from ...config import DEFAULT_CONFIG as CFG

log = setup_logger("steps.build_helpers.elevation_prerenderer")


class ElevationPrerenderer:
    """Pre-renders elevation plots for all selected clips."""

    def __init__(self, output_dir: Path):
        """
        Args:
            output_dir: Directory to save elevation plot images
        """
        self.output_dir = _mk(output_dir)
        self.elevation_data = load_elevation_data(flatten_path())

        # Width matches minimap (video_width * MINIMAP_SIZE_RATIO)
        video_width = 1920  # Standard Cycliq video width
        self.width = int(video_width * CFG.MINIMAP_SIZE_RATIO)
        # Height is ~25% of width for a wide strip
        self.height = max(80, int(self.width * 0.25))

    def prerender_all(self, rows: List[Dict]) -> Dict[int, Path]:
        """
        Pre-render elevation plots for all clips.

        Args:
            rows: List of clip metadata dicts from select.csv

        Returns:
            Dict mapping clip_idx → elevation_plot_path
        """
        if not self.elevation_data:
            log.warning("[elev] No elevation data available, skipping plots")
            return {}

        log.info(f"[elev] Pre-rendering {len(rows)} elevation plots ({self.width}x{self.height}px)...")
        paths: Dict[int, Path] = {}

        for idx, row in enumerate(rows, start=1):
            try:
                # Use gpx_epoch if available, fallback to abs_time_epoch
                epoch_str = row.get("gpx_epoch") or row.get("abs_time_epoch") or "0"
                epoch = float(epoch_str)

                if epoch > 0:
                    out_path = self.output_dir / f"elev_{idx:04d}.png"
                    render_elevation_plot(
                        self.elevation_data, epoch, out_path,
                        self.width, self.height
                    )
                    paths[idx] = out_path
            except Exception as e:
                log.warning(f"[elev] Failed to render plot for clip {idx}: {e}")

        log.info(f"[elev] Successfully rendered {len(paths)} elevation plots")
        return paths
