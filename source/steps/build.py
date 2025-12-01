# source/steps/build.py
"""
Render highlight clips with overlays (PiP, minimap, gauges).
Produces individual clips and concatenates them into _middle_##.mp4 segments with music.

REFACTORED: Now uses helper modules for clean separation of concerns.
"""

from __future__ import annotations
import csv
from pathlib import Path
from typing import List, Dict

from ..config import DEFAULT_CONFIG as CFG
from ..io_paths import select_path, clips_dir, minimap_dir, gauge_dir, _mk
from ..utils.log import setup_logger
from ..utils.gpx import load_gpx
from ..utils.progress_reporter import progress_iter

# Import build helpers
from .build_helpers import (
    MinimapPrerenderer,
    GaugeRenderer,
    ClipRenderer,
    SegmentConcatenator,
    cleanup_temp_files
)

log = setup_logger("steps.build")


def _load_recommended_clips() -> List[Dict]:
    """Load recommended clips from select.csv."""
    select_csv = select_path()
    
    if not select_csv.exists():
        log.warning("[build] select.csv missing")
        return []
    
    try:
        with select_csv.open() as f:
            rows = list(csv.DictReader(f))
        
        # Filter only recommended clips
        recommended = [r for r in rows if r.get("recommended", "false").lower() == "true"]
        
        if not recommended:
            log.warning("[build] No recommended clips in select.csv")
            return []
        
        log.info(f"[build] Loaded {len(recommended)} recommended clips")
        return recommended
        
    except Exception as e:
        log.error(f"[build] Failed to load select.csv: {e}")
        return []


def _load_gpx_points():
    """Load GPX points with safe failure handling."""
    try:
        gpx_points = load_gpx(str(CFG.INPUT_GPX_FILE))
        log.info(f"[build] Loaded {len(gpx_points)} GPX points")
        return gpx_points
    except Exception as e:
        log.warning(f"[build] No GPX data for minimaps: {e}")
        return []


def run() -> Path:
    """
    Main build pipeline: render clips → concatenate segments → add music.
    
    Pipeline:
        1. Load recommended clips from select.csv
        2. Pre-render all minimaps
        3. Setup gauge renderer with computed maxes
        4. Render individual clips with overlays
        5. Concatenate clips into ~30s segments
        6. Add music to each segment
        
    Returns:
        Path to clips directory
    """
    # Setup output directories
    out_dir = _mk(clips_dir())
    minimap_path = _mk(minimap_dir())
    gauge_path = _mk(gauge_dir())
    
    # Load data
    recommended_clips = _load_recommended_clips()
    if not recommended_clips:
        log.error("[build] No clips to build")
        return out_dir
    
    gpx_points = _load_gpx_points()
    
    # Step 1: Pre-render minimaps
    log.info("[build] Pre-rendering minimaps...")
    minimap_prerenderer = MinimapPrerenderer(minimap_path, gpx_points)
    minimap_paths = minimap_prerenderer.prerender_all(recommended_clips)
    
    # Step 2: Setup gauge renderer
    log.info("[build] Computing gauge maxes...")
    gauge_renderer = GaugeRenderer(gauge_path, select_path())
    
    # Step 3: Render individual clips
    log.info(f"[build] Rendering {len(recommended_clips)} clips with overlays...")
    clip_renderer = ClipRenderer(out_dir)
    individual_clips: List[Path] = []
    
    for idx, clip_row in enumerate(progress_iter(
        recommended_clips, 
        desc="Encoding clips", 
        unit="clip"
    ), start=1):
        try:
            # Get pre-rendered minimap (if available)
            minimap_path_for_clip = minimap_paths.get(idx)
            
            # Render clip with all overlays
            clip_path = clip_renderer.render_clip(
                row=clip_row,
                clip_idx=idx,
                minimap_path=minimap_path_for_clip,
                gauge_renderer=gauge_renderer
            )
            
            if clip_path:
                individual_clips.append(clip_path)
            else:
                log.warning(f"[build] Clip {idx} failed to render")
                
        except Exception as e:
            log.error(f"[build] Failed to render clip {idx}: {e}", exc_info=True)
    
    if not individual_clips:
        log.error("[build] No clips were successfully rendered")
        return out_dir
    
    log.info(f"[build] Successfully rendered {len(individual_clips)} clips")
    
    # Step 4: Concatenate into segments with music
    log.info("[build] Concatenating clips into segments...")
    segment_concatenator = SegmentConcatenator(
        project_dir=CFG.FINAL_REEL_PATH.parent,
        working_dir=CFG.WORKING_DIR
    )
    
    segment_paths = segment_concatenator.concatenate_into_segments(
        clips=individual_clips,
        music_path=CFG.MUSIC_DIR,  # Pass music directory
        music_volume=CFG.MUSIC_VOLUME,
        raw_audio_volume=CFG.RAW_AUDIO_VOLUME
    )
    
    if segment_paths:
        log.info(f"[build] Created {len(segment_paths)} segment(s)")
        for seg_path in segment_paths:
            log.info(f"[build]   → {seg_path.name}")
    else:
        log.warning("[build] No segments created")
    
    # Step 5: Cleanup temp files
    cleanup_temp_files()
    
    log.info(f"[build] Build complete: {len(individual_clips)} clips → {len(segment_paths)} segments")
    return out_dir


if __name__ == "__main__":
    run()