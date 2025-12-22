# source/steps/build.py
"""
Render highlight clips with overlays (PiP, minimap, gauges).
Produces individual clips and concatenates them into _middle_##.mp4 segments with music.

Moment-based version:
- Uses moment_id and recommended flag to determine main vs PiP camera.
- Always renders PiP: main = recommended row, PiP = other camera in same moment.
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
    cleanup_temp_files,
)

log = setup_logger("steps.build")


def _load_recommended_moments() -> List[Dict]:
    """
    Load recommended moments from select.csv and build main+PiP pairs.

    Returns:
        List of dicts:
            {
                "moment_id": int,
                "main": <row with recommended=true>,
                "pip":  <other row in same moment>,
            }
    """
    select_csv = select_path()

    if not select_csv.exists():
        log.warning("[build] select.csv missing")
        return []

    try:
        with select_csv.open() as f:
            rows = list(csv.DictReader(f))
    except Exception as e:
        log.error(f"[build] Failed to load select.csv: {e}")
        return []

    if not rows:
        log.warning("[build] select.csv is empty")
        return []

    # Group rows by moment_id
    by_moment: Dict[str, List[Dict]] = {}
    for r in rows:
        mid = r.get("moment_id")
        if mid in (None, ""):
            log.debug(f"[build] Row {r.get('index', '?')} missing moment_id; skipping")
            continue
        by_moment.setdefault(str(mid), []).append(r)

    moments: List[Dict] = []
    dropped = 0

    for mid, group in by_moment.items():
        # Expect exactly two cameras per moment
        if len(group) < 2:
            dropped += 1
            continue

        # Identify main (recommended) and pip (other camera)
        main_row = None
        pip_row = None

        for r in group:
            if str(r.get("recommended", "false")).lower() == "true":
                main_row = r

        if main_row is None:
            # No recommended row in this moment → not part of final reel
            continue

        # PiP row = any other row in same moment
        candidates = [r for r in group if r is not main_row]
        if not candidates:
            dropped += 1
            continue

        pip_row = candidates[0]

        try:
            moment_id_int = int(mid)
        except Exception:
            moment_id_int = -1

        moments.append(
            {
                "moment_id": moment_id_int,
                "main": main_row,
                "pip": pip_row,
            }
        )

    if not moments:
        log.warning("[build] No recommended moments with both perspectives available")
        return []

    # Sort by time for stable build order
    moments.sort(
        key=lambda m: float(m["main"].get("abs_time_epoch", m["pip"].get("abs_time_epoch", 0)) or 0.0)
    )

    log.info(
        f"[build] Loaded {len(moments)} recommended moments "
        f"(dropped {dropped} incomplete moments)"
    )
    return moments


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
        1. Load recommended moments from select.csv (main+PiP per moment).
        2. Pre-render all minimaps (using main rows).
        3. Setup gauge renderer with computed maxes (from select.csv).
        4. Render individual clips with overlays (main + PiP + HUD + minimap).
        5. Concatenate clips into ~30s segments.
        6. Add music to each segment.

    Returns:
        Path to clips directory
    """
    # Setup output directories
    out_dir = _mk(clips_dir())
    minimap_path = _mk(minimap_dir())
    gauge_path = _mk(gauge_dir())

    # Load data (moment-based)
    recommended_moments = _load_recommended_moments()
    if not recommended_moments:
        log.error("[build] No moments to build")
        return out_dir

    gpx_points = _load_gpx_points()

    # Step 1: Pre-render minimaps (one per clip, using main rows)
    log.info("[build] Pre-rendering minimaps...")
    minimap_prerenderer = MinimapPrerenderer(minimap_path, gpx_points)
    main_rows_for_minimap = [m["main"] for m in recommended_moments]
    minimap_paths = minimap_prerenderer.prerender_all(main_rows_for_minimap)

    # Step 2: Setup gauge renderer
    log.info("[build] Computing gauge maxes...")
    gauge_renderer = GaugeRenderer(gauge_path, select_path())

    # Step 3: Render individual clips
    log.info(f"[build] Rendering {len(recommended_moments)} clips with overlays (main+PiP)...")
    clip_renderer = ClipRenderer(out_dir)
    individual_clips: List[Path] = []

    for idx, moment in enumerate(
        progress_iter(recommended_moments, desc="Encoding clips", unit="clip"), start=1
    ):
        main_row = moment["main"]
        pip_row = moment["pip"]

        try:
            # Get pre-rendered minimap (if available)
            minimap_path_for_clip = minimap_paths.get(idx)

            # Render clip with all overlays
            clip_path = clip_renderer.render_clip(
                main_row=main_row,
                pip_row=pip_row,
                clip_idx=idx,
                minimap_path=minimap_path_for_clip,
                gauge_renderer=gauge_renderer,
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
        working_dir=CFG.WORKING_DIR,
    )

    segment_paths = segment_concatenator.concatenate_into_segments(
        clips=individual_clips,
        music_path=CFG.MUSIC_DIR,  # Pass music directory
        music_volume=CFG.MUSIC_VOLUME,
        raw_audio_volume=CFG.RAW_AUDIO_VOLUME,
    )

    if segment_paths:
        log.info(f"[build] Created {len(segment_paths)} segment(s)")
        for seg_path in segment_paths:
            log.info(f"[build]   → {seg_path.name}")
    else:
        log.warning("[build] No segments created")

    # Step 5: Cleanup temp files
    cleanup_temp_files()

    log.info(
        f"[build] Build complete: {len(individual_clips)} clips → {len(segment_paths)} segments"
    )
    return out_dir


if __name__ == "__main__":
    run()
