# source/steps/align.py
"""
Camera alignment step with three explicit stages:

Stage 1: UTC Bug Correction
    - Fix Cycliq's "local time with fake Z" metadata bug
    - Pure metadata correction, independent of GPX
    
Stage 2: Camera-to-Camera Alignment
    - Compute recording start differences between cameras
    - Store offsets relative to earliest camera (baseline)
    - These offsets go into camera_offsets.json
    
Stage 3: GPX Sanity Checks
    - Log how cameras relate to GPX timeline
    - Informational only, does not affect alignment
"""

from __future__ import annotations
import json
import csv
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Tuple, List, Optional

from ..config import DEFAULT_CONFIG as CFG
from ..io_paths import flatten_path, camera_offsets_path, _mk
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


def run() -> Dict[str, float]:
    """
    Main alignment pipeline with three explicit stages.
    
    Returns:
        Dict mapping camera names to their offsets (in seconds)
    """
    log.info("=" * 70)
    log.info("CAMERA ALIGNMENT - THREE STAGE CORRECTION")
    log.info("=" * 70)
    log.info(f"[align] USE_CAMERA_OFFSETS={CFG.USE_CAMERA_OFFSETS}")
    
    # =========================================================================
    # STAGE 0: Preparation
    # =========================================================================
    report_progress(1, 6, "Scanning video files...")
    
    videos = sorted(CFG.INPUT_VIDEOS_DIR.glob("*_*.MP4"))
    
    if not videos:
        log.warning(f"[align] No videos found in {CFG.INPUT_VIDEOS_DIR}")
        log.warning("[align] Searched for pattern: *_*.MP4")
        
        # Write empty offsets file
        empty_offsets = {cam: 0.0 for cam in CFG.CAMERA_WEIGHTS.keys()}
        if CFG.USE_CAMERA_OFFSETS:
            offsets_file = _mk(camera_offsets_path())
            with offsets_file.open("w") as f:
                json.dump(empty_offsets, f, indent=2, sort_keys=True)
            log.info(f"[align] Wrote empty offsets file: {offsets_file}")
        else:
            log.info("[align] USE_CAMERA_OFFSETS is False – not writing camera_offsets.json")

        return empty_offsets
    
    # Group videos by camera
    videos_by_camera: Dict[str, List[Path]] = {}
    for video in videos:
        camera_name = extract_camera_name(video)
        videos_by_camera.setdefault(camera_name, []).append(video)
    
    log.info(f"[align] Found {len(videos)} videos from {len(videos_by_camera)} cameras")
    for cam, files in videos_by_camera.items():
        log.info(f"[align]   - {cam}: {len(files)} clips")
    
    # =========================================================================
    # STAGE 1: UTC Bug Fix + Recording Start Inference
    # =========================================================================
    report_progress(2, 6, "Computing corrected recording start times...")
    
    log.info("")
    log.info("STAGE 1: UTC Bug Correction + Recording Start Inference")
    log.info("-" * 70)
    
    recording_starts: Dict[str, Tuple[datetime, str]] = {}
    
    for camera_name, video_files in videos_by_camera.items():
        start_time, source_file = _probe_camera_with_fallback(camera_name, video_files)
        
        if start_time is None:
            log.error(f"[align] Failed to determine start time for {camera_name}")
            log.error(f"[align] This camera will use offset 0.0 by default")
            # Use epoch as placeholder
            recording_starts[camera_name] = (datetime.fromtimestamp(0, tz=timezone.utc), "FAILED")
        else:
            recording_starts[camera_name] = (start_time, source_file)
            log.info(
                f"[align] ✓ {camera_name:15s} starts at {start_time.isoformat()} "
                f"(from {source_file})"
            )
    
    if not recording_starts:
        log.error("[align] No cameras could be probed successfully")
        return {}
    
    # =========================================================================
    # STAGE 2: Camera-to-Camera Alignment
    # =========================================================================
    report_progress(3, 6, "Computing camera-to-camera offsets...")
    
    log.info("")
    log.info("STAGE 2: Camera-to-Camera Alignment")
    log.info("-" * 70)
    
    # Find earliest camera (baseline)
    earliest_start = min(start_time for start_time, _ in recording_starts.values())
    baseline_camera = [
        cam for cam, (start, _) in recording_starts.items()
        if start == earliest_start
    ][0]
    
    log.info(f"[align] Baseline camera (earliest): {baseline_camera}")
    log.info(f"[align] Baseline start time: {earliest_start.isoformat()}")
    log.info("")
    
    # Compute offsets relative to baseline
    camera_offsets: Dict[str, float] = {}
    
    for camera_name, (start_time, source_file) in recording_starts.items():
        # How many seconds AFTER baseline this camera started
        offset_s = (start_time - earliest_start).total_seconds()
        camera_offsets[camera_name] = round(offset_s, 3)
        
        if camera_name == baseline_camera:
            log.info(f"[align] {camera_name:15s}: 0.000s (baseline)")
        else:
            log.info(
                f"[align] {camera_name:15s}: +{offset_s:7.3f}s "
                f"(starts {abs(offset_s):.3f}s {'after' if offset_s > 0 else 'before'} baseline)"
            )
        
        # Sanity check
        if abs(offset_s) > SANITY_THRESHOLD_S:
            log.warning(
                f"[align] ⚠️ WARNING: {camera_name} offset is very large ({offset_s:.1f}s)"
            )
            log.warning(
                f"[align]           This might indicate a problem with timestamps"
            )
    
    # =========================================================================
    # STAGE 3: GPX Sanity Checks (Optional)
    # =========================================================================
    report_progress(4, 6, "Performing GPX sanity checks...")
    
    gpx_start = _get_gpx_start_time()
    
    if gpx_start is not None:
        log.info("")
        log.info("STAGE 3: GPX Sanity Checks")
        log.info("-" * 70)
        log.info(f"[align] GPX start time: {gpx_start.isoformat()}")
        log.info("")
        
        for camera_name, (camera_start, _) in recording_starts.items():
            delta_vs_gpx = (camera_start - gpx_start).total_seconds()
            
            if abs(delta_vs_gpx) < 1.0:
                status = "✓ aligned"
            elif delta_vs_gpx > 0:
                status = f"starts {delta_vs_gpx:.1f}s after GPX"
            else:
                status = f"starts {abs(delta_vs_gpx):.1f}s before GPX"
            
            log.info(f"[align] {camera_name:15s} vs GPX: {delta_vs_gpx:+8.3f}s ({status})")
            
            # Additional warning for concerning offsets
            if abs(delta_vs_gpx) > SANITY_THRESHOLD_S:
                log.warning(
                    f"[align] ⚠️ {camera_name} is very far from GPX start "
                    f"({abs(delta_vs_gpx):.0f}s)"
                )
    else:
        log.info("")
        log.info("STAGE 3: GPX Sanity Checks")
        log.info("-" * 70)
        log.info("[align] No GPX data available - skipping sanity checks")
    
    # =========================================================================
    # Persist & Apply Offsets
    # =========================================================================
    report_progress(5, 6, "Saving camera offsets...")
    
    if CFG.USE_CAMERA_OFFSETS:
        offsets_file = _mk(camera_offsets_path())
        with offsets_file.open("w") as f:
            json.dump(camera_offsets, f, indent=2, sort_keys=True)

        log.info("")
        log.info("=" * 70)
        log.info(f"[align] ✓ Offsets saved to: {offsets_file}")
        log.info("=" * 70)

        # Auto-apply to config for this pipeline run
        CFG.CAMERA_TIME_OFFSETS.update(camera_offsets)
        log.info("[align] Offsets applied to config for current pipeline run")
    else:
        log.info("[align] USE_CAMERA_OFFSETS is False – skipping write/apply of camera offsets")
    
    report_progress(6, 6, "Alignment complete")
    
    return camera_offsets


