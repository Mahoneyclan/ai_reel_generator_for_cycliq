# source/steps/build_helpers/minimap_prerenderer.py
"""
Minimap pre-rendering for clips.
Generates all minimap overlays before video encoding begins.
"""

from __future__ import annotations
from pathlib import Path
from typing import List, Dict

from ...utils.log import setup_logger
from ...utils.map_overlay import render_overlay_minimap
from ...utils.gpx import GpxPoint
from ...io_paths import _mk
from ...utils.progress_reporter import progress_iter

log = setup_logger("steps.build_helpers.minimap_prerenderer")


class MinimapPrerenderer:
    """Pre-renders minimaps for all selected clips."""
    
    def __init__(self, output_dir: Path, gpx_points: List[GpxPoint]):
        """
        Args:
            output_dir: Directory to save minimap images
            gpx_points: GPS trackpoints for map rendering
        """
        self.output_dir = _mk(output_dir)
        self.gpx_points = gpx_points
    
    def prerender_all(self, rows: List[Dict]) -> Dict[int, Path]:
        """
        Pre-render all minimaps for selected clips.
        
        Args:
            rows: List of clip metadata dicts from select.csv
            
        Returns:
            Dict mapping clip_idx → minimap_path
        """
        if not self.gpx_points:
            log.warning("[minimap] No GPX data available, skipping minimap rendering")
            return {}
        
        log.info(f"[minimap] Pre-rendering {len(rows)} minimaps...")
        minimap_paths: Dict[int, Path] = {}
        
        for idx, row in enumerate(progress_iter(rows, desc="Rendering minimaps", unit="map"), start=1):
            try:
                minimap_path = self._render_single(row, idx)
                if minimap_path:
                    minimap_paths[idx] = minimap_path
            except Exception as e:
                log.warning(f"[minimap] Failed to render minimap {idx}: {e}")
        
        log.info(f"[minimap] Successfully rendered {len(minimap_paths)} minimaps")
        return minimap_paths
    
    def _render_single(self, row: Dict, clip_idx: int) -> Path | None:
        """
        Render single minimap for a clip.
        
        Args:
            row: Clip metadata
            clip_idx: Clip index number
            
        Returns:
            Path to rendered minimap PNG, or None if failed
        """
        gpx_epoch = row.get("gpx_epoch")
        if not gpx_epoch:
            log.debug(f"[minimap] Clip {clip_idx} has no GPX timestamp")
            return None
        
        try:
            epoch = float(gpx_epoch)
            img = render_overlay_minimap(self.gpx_points, epoch)
            
            minimap_path = self.output_dir / f"minimap_{clip_idx:04d}.png"
            img.save(minimap_path)
            
            return minimap_path
            
        except Exception as e:
            log.warning(f"[minimap] Render failed for clip {clip_idx}: {e}")
            return None