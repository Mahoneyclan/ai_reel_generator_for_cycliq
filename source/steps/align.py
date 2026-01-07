# source/steps/align.py
"""
Camera alignment diagnostics.

Logs timing information about cameras and GPX for debugging.
Does NOT produce any output files - extract.py handles alignment
by anchoring all sampling to the GPX timeline.
"""

from __future__ import annotations
import csv
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Tuple, List, Optional

from ..config import DEFAULT_CONFIG as CFG
from ..io_paths import flatten_path
from ..utils.log import setup_logger
from ..utils.progress_reporter import report_progress
from ..utils.video_utils import (
    probe_video_metadata,
    fix_cycliq_utc_bug,
    infer_recording_start,
    extract_camera_name
)

log = setup_logger("steps.align")

# Sanity threshold for detecting potential issues
SANITY_THRESHOLD_S = 3600.0  # 1 hour - warn if camera starts are this far apart


def _get_gpx_start_time() -> Optional[datetime]:
    """
    Load GPX start time from flatten.csv.
    
    Returns:
        GPX start datetime in UTC, or None if unavailable
    """
    flatten_csv = flatten_path()
    
    if not flatten_csv.exists():
        log.warning("[align] flatten.csv not found - GPX checks will be skipped")
        return None
    
    try:
        with flatten_csv.open() as f:
            reader = csv.DictReader(f)
            first_row = next(reader, None)
            
            if not first_row:
                log.warning("[align] flatten.csv is empty")
                return None
            
            gpx_epoch_str = first_row.get("gpx_epoch", "")
            if not gpx_epoch_str:
                log.warning("[align] flatten.csv missing gpx_epoch column")
                return None
            
            gpx_epoch = float(gpx_epoch_str)
            return datetime.fromtimestamp(gpx_epoch, tz=timezone.utc)
            
    except Exception as e:
        log.warning(f"[align] Failed to read GPX start time: {e}")
        return None


def _probe_camera_with_fallback(
    camera_name: str,
    video_files: List[Path]
) -> Tuple[Optional[datetime], Optional[str]]:
    """
    Probe camera's first usable clip to determine recording start time.
    Falls back to subsequent clips if first clip fails to probe.
    
    Args:
        camera_name: Camera identifier
        video_files: List of video files for this camera (sorted)
        
    Returns:
        Tuple of (recording_start_utc, source_filename) or (None, None) if all fail
    """
    for video_file in video_files:
        try:
            # Extract metadata
            raw_dt, duration_s = probe_video_metadata(video_file)
            
            # Fix UTC bug
            creation_local = fix_cycliq_utc_bug(
                raw_dt,
                CFG.CAMERA_CREATION_TIME_TZ,
                CFG.CAMERA_CREATION_TIME_IS_LOCAL_WRONG_Z
            )
            creation_utc = creation_local.astimezone(timezone.utc)
            
            # Infer recording start (now with video_path for offset detection)
            recording_start_utc = infer_recording_start(
                creation_utc,
                duration_s,
                video_path=video_file
            )
            
            log.debug(
                f"[align] {camera_name}: Probed {video_file.name} → "
                f"start_utc={recording_start_utc.isoformat()}"
            )
            
            return recording_start_utc, video_file.name
            
        except Exception as e:
            log.warning(f"[align] Probe failed for {video_file.name}: {e}")
            continue
    
    # All probes failed
    log.error(f"[align] All probe attempts failed for {camera_name}")
    return None, None


def run() -> None:
    """
    Log camera timing diagnostics.

    This step is informational only - it logs:
    - Recording start times for each camera
    - Time differences between cameras
    - How cameras relate to GPX timeline

    Alignment is handled by extract.py using GPX-anchored sampling grid.
    """
    log.info("=" * 70)
    log.info("CAMERA ALIGNMENT DIAGNOSTICS")
    log.info("=" * 70)

    report_progress(1, 4, "Scanning video files...")

    videos = sorted(CFG.INPUT_VIDEOS_DIR.glob("*_*.MP4"))
    if not videos:
        log.warning(f"[align] No videos found in {CFG.INPUT_VIDEOS_DIR}")
        return

    # Group videos by camera
    videos_by_camera: Dict[str, List[Path]] = {}
    for video in videos:
        camera_name = extract_camera_name(video)
        videos_by_camera.setdefault(camera_name, []).append(video)

    log.info(f"[align] Found {len(videos)} videos from {len(videos_by_camera)} cameras")
    for cam, files in videos_by_camera.items():
        log.info(f"[align]   - {cam}: {len(files)} clips")

    # ────────────────────────────────────────────────────────────
    # Probe camera start times
    # ────────────────────────────────────────────────────────────
    report_progress(2, 4, "Probing camera start times...")

    recording_starts: Dict[str, Tuple[datetime, str]] = {}

    for camera_name, video_files in videos_by_camera.items():
        start_time, source_file = _probe_camera_with_fallback(camera_name, video_files)
        if start_time is None:
            log.error(f"[align] Failed to determine start time for {camera_name}")
            continue
        recording_starts[camera_name] = (start_time, source_file)
        log.info(
            f"[align] ✓ {camera_name:15s} starts at {start_time.isoformat()} "
            f"(from {source_file})"
        )

    if not recording_starts:
        log.error("[align] No cameras could be probed successfully")
        return

    # ────────────────────────────────────────────────────────────
    # Log time differences between cameras
    # ────────────────────────────────────────────────────────────
    report_progress(3, 4, "Computing camera time differences...")

    earliest_start = min(start for (start, _src) in recording_starts.values())
    baseline_camera = [
        cam for cam, (start, _src) in recording_starts.items()
        if start == earliest_start
    ][0]

    log.info(f"[align] Baseline camera (earliest): {baseline_camera}")

    for camera_name, (start_time, _) in recording_starts.items():
        offset_s = (start_time - earliest_start).total_seconds()
        if camera_name == baseline_camera:
            log.info(f"[align] {camera_name:15s}: 0.000s (baseline)")
        else:
            log.info(
                f"[align] {camera_name:15s}: {offset_s:+7.3f}s "
                f"(starts {abs(offset_s):.3f}s after baseline)"
            )

    # ────────────────────────────────────────────────────────────
    # GPX sanity checks
    # ────────────────────────────────────────────────────────────
    report_progress(4, 4, "GPX sanity checks...")
    gpx_start = _get_gpx_start_time()
    if gpx_start is not None:
        log.info("")
        log.info("GPX Timing:")
        log.info("-" * 70)
        log.info(f"[align] GPX start time: {gpx_start.isoformat()}")
        for camera_name, (camera_start, _src) in recording_starts.items():
            delta_vs_gpx = (camera_start - gpx_start).total_seconds()
            status = (
                "✓ aligned" if abs(delta_vs_gpx) < 1.0
                else f"starts {delta_vs_gpx:.1f}s "
                     f"{'after' if delta_vs_gpx > 0 else 'before'} GPX"
            )
            log.info(
                f"[align] {camera_name:15s} vs GPX: {delta_vs_gpx:+8.3f}s ({status})"
            )
    else:
        log.info("[align] No GPX data available - skipping GPX checks")

    log.info("=" * 70)


