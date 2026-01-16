# source/steps/build_helpers/minimap_prerenderer.py
"""
Minimap pre-rendering for clips.
Generates all minimap overlays before video encoding begins.
Uses parallel processing for faster rendering.
"""

from __future__ import annotations
from concurrent.futures import ThreadPoolExecutor, as_completed
from os import cpu_count
from pathlib import Path
from typing import List, Dict

from ...utils.log import setup_logger
from ...utils.map_overlay import render_overlay_minimap
from ...utils.gpx import GpxPoint
from ...io_paths import _mk
from ...utils.progress_reporter import report_progress

log = setup_logger("steps.build_helpers.minimap_prerenderer")


class MinimapPrerenderer:
    """Pre-renders minimaps for all selected clips."""

    def __init__(self, output_dir: Path, gpx_points: List[GpxPoint]):
        """
        Args:
            output_dir: Directory to save minimap images
            gpx_points: GPS trackpoints for map rendering
        """
        from ...config import DEFAULT_CONFIG as CFG

        self.output_dir = _mk(output_dir)
        self.gpx_points = gpx_points

        # Calculate minimap size constraints to maximize available space
        # Layout (top-right corner, top to bottom):
        #   - top margin
        #   - minimap
        #   - gap
        #   - elevation plot
        #   - gap
        #   - PIP video
        #   - bottom margin
        # Use MAP_SPLASH_SIZE as reference for output video dimensions
        video_width, video_height = CFG.MAP_SPLASH_SIZE
        pip_width = int(video_width * CFG.PIP_SCALE_RATIO)
        pip_height = int(video_height * CFG.PIP_SCALE_RATIO)
        elev_height = int(pip_width * 0.25)  # Elevation is 25% of pip width
        top_margin = CFG.MINIMAP_MARGIN
        bottom_margin = CFG.PIP_MARGIN
        gap_minimap_elev = 10  # Gap between minimap and elevation
        gap_elev_pip = 10  # Gap between elevation and PIP

        self.max_width = pip_width  # Same as PIP width

        # Max height: total available vertical space minus all other elements
        available_height = (video_height - top_margin - bottom_margin
                           - pip_height - elev_height
                           - gap_minimap_elev - gap_elev_pip)
        self.max_height = max(available_height, 200)  # Minimum 200px

        log.info(f"[minimap] Video: {video_width}x{video_height}, PIP: {pip_width}x{pip_height}, max minimap: {self.max_width}x{self.max_height}px")
    
    def prerender_all(self, rows: List[Dict]) -> Dict[int, Path]:
        """
        Pre-render all minimaps for selected clips using parallel processing.

        Args:
            rows: List of clip metadata dicts from select.csv

        Returns:
            Dict mapping clip_idx → minimap_path
        """
        if not self.gpx_points:
            log.warning("[minimap] No GPX data available, skipping minimap rendering")
            return {}

        num_workers = min(cpu_count() or 4, 8)
        log.info(f"[minimap] Pre-rendering {len(rows)} minimaps with {num_workers} workers...")
        minimap_paths: Dict[int, Path] = {}

        with ThreadPoolExecutor(max_workers=num_workers) as executor:
            # Submit all tasks
            futures = {
                executor.submit(self._render_single, row, idx): idx
                for idx, row in enumerate(rows, start=1)
            }

            # Collect results as they complete
            completed = 0
            for future in as_completed(futures):
                idx = futures[future]
                completed += 1
                try:
                    minimap_path = future.result()
                    if minimap_path:
                        minimap_paths[idx] = minimap_path
                except Exception as e:
                    log.warning(f"[minimap] Failed to render minimap {idx}: {e}")

                # Progress update
                if completed % 10 == 0 or completed == len(rows):
                    report_progress(completed, len(rows), f"Rendered {completed}/{len(rows)} minimaps")

        log.info(f"[minimap] Successfully rendered {len(minimap_paths)} minimaps")
        return minimap_paths
    
    def _render_single(self, row: Dict, clip_idx: int) -> Path | None:
        """
        Render single minimap for a clip.

        Args:
            row: Clip metadata (from select.csv)
            clip_idx: Clip index number

        Returns:
            Path to rendered minimap PNG, or None if failed
        """
        # Use GPX epoch as the authoritative ride timeline
        gpx_epoch = row.get("gpx_epoch")
        if not gpx_epoch:
            log.debug(f"[minimap] Clip {clip_idx} has no GPX timestamp")
            return None

        try:
            epoch = float(gpx_epoch)
            img = render_overlay_minimap(
                self.gpx_points,
                epoch,
                size=(self.max_width, self.max_height)
            )

            minimap_path = self.output_dir / f"minimap_{clip_idx:04d}.png"
            img.save(minimap_path)

            return minimap_path

        except Exception as e:
            log.warning(f"[minimap] Render failed for clip {clip_idx}: {e}")
            return None
    
