# source/steps/extract.py
"""
Extract frame metadata from MP4s without writing JPGs.

ALIGNED SAMPLING:
- All cameras sample at times on a global grid (multiples of sample_interval
  from global_session_start_epoch)
- This ensures frames from different cameras at the same real-world moment
  have IDENTICAL abs_time_epoch values
- Enables exact moment_id matching without tolerance-based heuristics
"""

from __future__ import annotations
import csv
import json
import math
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import List, Dict, Optional, Tuple

from ..config import DEFAULT_CONFIG as CFG
from ..io_paths import extract_path, flatten_path, camera_offsets_path, _mk
from ..utils.log import setup_logger
from ..utils.progress_reporter import progress_iter, report_progress
from ..utils.video_utils import (
    probe_video_metadata,
    fix_cycliq_utc_bug,
    infer_recording_start,
    parse_camera_and_clip
)

log = setup_logger("steps.extract")


def _load_camera_offsets() -> Dict[str, float]:
    """
    Load camera alignment offsets from JSON file.
    Falls back to config defaults if file doesn't exist.
    
    Returns:
        Dict mapping camera names to offset seconds
    """
    offsets_file = camera_offsets_path()
    
    if offsets_file.exists():
        try:
            with offsets_file.open() as f:
                offsets = json.load(f)
            log.info(f"[extract] Loaded camera offsets from {offsets_file.name}")
            for camera, offset in offsets.items():
                log.debug(f"[extract]   {camera}: {offset:.3f}s")
            return offsets
        except Exception as e:
            log.warning(f"[extract] Failed to load {offsets_file.name}: {e}")
            log.warning(f"[extract] Falling back to config defaults")
    
    # Fall back to config
    log.info("[extract] Using camera offsets from config (no JSON file found)")
    return CFG.CAMERA_TIME_OFFSETS.copy()


def _get_gpx_start_epoch() -> float:
    """
    Load GPX ride start time for filtering.
    
    Returns:
        GPX start time as epoch seconds, or 0.0 if unavailable
    """
    flatten_csv = flatten_path()
    
    if not flatten_csv.exists():
        log.warning("[extract] No flatten.csv - will extract all frames (no GPX filtering)")
        return 0.0
    
    try:
        with flatten_csv.open() as f:
            reader = csv.DictReader(f)
            first_row = next(reader, None)
            
            if first_row and "gpx_epoch" in first_row and first_row["gpx_epoch"]:
                gpx_start = float(first_row["gpx_epoch"])
                log.info(f"[extract] GPX ride starts at epoch {gpx_start:.3f}")
                return gpx_start
    except Exception as e:
        log.warning(f"[extract] Could not read GPX start time: {e}")
    
    return 0.0


def _compute_session_time_bounds(
    videos: List[Path],
    camera_offsets: Dict[str, float],
) -> Tuple[float, Dict[str, Tuple[float, float]]]:
    """
    Compute:
      - global_session_start_epoch: earliest aligned start across all cameras
      - per-camera (overlap_start_epoch, overlap_end_epoch) in REAL time

    Time model:
      real_start_utc  = creation_utc - duration
      aligned_start_utc = real_start_utc + camera_offset_s

    Overlap is defined in REAL time:
      real_end_utc    = real_start_utc + duration
      overlap_start   = max(real_start_utc for all cameras)
      overlap_end     = min(real_end_utc for all cameras)
    """
    if not videos:
        return 0.0, {}

    # First pass: collect real and aligned ranges per camera
    per_camera_real: Dict[str, List[Tuple[float, float]]] = {}
    per_camera_aligned_starts: Dict[str, List[float]] = {}

    for video_path in videos:
        try:
            # Use utils function with include_fps=True to get all 3 values
            raw_dt, duration_s, fps = probe_video_metadata(video_path, include_fps=True)
        except Exception as e:
            log.warning(f"[extract] Skipping {video_path.name} for time bounds: {e}")
            continue

        # Fix UTC bug using utils function
        creation_local = fix_cycliq_utc_bug(
            raw_dt,
            CFG.CAMERA_CREATION_TIME_TZ,
            CFG.CAMERA_CREATION_TIME_IS_LOCAL_WRONG_Z
        )
        creation_utc = creation_local.astimezone(timezone.utc)

        # Infer recording start using utils function with video_path
        real_start_utc = infer_recording_start(creation_utc, duration_s, video_path=video_path)
        real_end_utc = real_start_utc + timedelta(seconds=duration_s)

        # Parse camera name using utils function
        camera_name, _, _ = parse_camera_and_clip(video_path)
        camera_offset_s = camera_offsets.get(camera_name, 0.0)

        aligned_start_utc = real_start_utc - timedelta(seconds=camera_offset_s)

        real_start_epoch = real_start_utc.timestamp()
        real_end_epoch = real_end_utc.timestamp()
        aligned_start_epoch = aligned_start_utc.timestamp()

        per_camera_real.setdefault(camera_name, []).append(
            (real_start_epoch, real_end_epoch)
        )
        per_camera_aligned_starts.setdefault(camera_name, []).append(
            aligned_start_epoch
        )

    if not per_camera_real:
        return 0.0, {}

    # Global session start: earliest aligned start across all cameras
    global_session_start_epoch = min(
        start for starts in per_camera_aligned_starts.values() for start in starts
    )

    # Compute global REAL overlap window
    all_real_starts = [s for ranges in per_camera_real.values() for (s, _e) in ranges]
    all_real_ends = [e for ranges in per_camera_real.values() for (_s, e) in ranges]

    overlap_start_epoch = max(all_real_starts)
    overlap_end_epoch = min(all_real_ends)

    if overlap_end_epoch <= overlap_start_epoch:
        log.warning(
            "[extract] No temporal overlap between cameras "
            f"(overlap_start={overlap_start_epoch}, overlap_end={overlap_end_epoch})"
        )
        # Fallback: no overlap; use individual camera coverage
        per_camera_overlap = {
            cam: (min(r[0] for r in ranges), max(r[1] for r in ranges))
            for cam, ranges in per_camera_real.items()
        }
        return global_session_start_epoch, per_camera_overlap

    # Per-camera REAL overlap (intersection of each camera's real coverage with global overlap)
    per_camera_overlap: Dict[str, Tuple[float, float]] = {}
    for cam, ranges in per_camera_real.items():
        cam_starts = []
        cam_ends = []
        for (s, e) in ranges:
            s_i = max(s, overlap_start_epoch)
            e_i = min(e, overlap_end_epoch)
            if e_i > s_i:
                cam_starts.append(s_i)
                cam_ends.append(e_i)
        if cam_starts and cam_ends:
            per_camera_overlap[cam] = (min(cam_starts), max(cam_ends))
        else:
            per_camera_overlap[cam] = (overlap_start_epoch, overlap_start_epoch)

    log.info(
        f"[extract] Global session start epoch (aligned): {global_session_start_epoch:.3f} "
        f"| REAL overlap window: {overlap_start_epoch:.3f}–{overlap_end_epoch:.3f}"
    )
    for cam, (s, e) in per_camera_overlap.items():
        log.info(
            f"[extract]   {cam}: REAL overlap {s:.3f}–{e:.3f} ({e - s:.1f}s)"
        )

    return global_session_start_epoch, per_camera_overlap


def _extract_video_metadata(
    video_path: Path,
    sampling_interval_s: int,
    camera_offsets: Dict[str, float],
    gpx_start_epoch: float,
    global_session_start_epoch: float,
    _camera_overlap_bounds: Tuple[float, float],
) -> List[Dict[str, str]]:
    """
    Generate frame metadata for one video clip with ALIGNED sampling.

    Aligned Sampling Model:
        All cameras sample at times that fall on a global grid defined by
        global_session_start_epoch and sampling_interval_s. This ensures
        frames from different cameras at the same real-world moment have
        IDENTICAL abs_time_epoch values, enabling exact moment_id matching.

        Global grid: global_session_start + N * sampling_interval (for N = 0, 1, 2...)

        For each camera:
            time_since_global_start = real_start_epoch - global_session_start_epoch
            first_sec_raw = next grid point >= time_since_global_start
            Sample at: first_sec_raw, first_sec_raw + interval, ...

    Time fields:
        abs_time_epoch    = real_start_epoch + sec_raw (always on global grid)
        session_ts_s      = abs_time_epoch - global_session_start_epoch
    """

    # Parse camera name using utils function
    camera_name, clip_num, clip_id = parse_camera_and_clip(video_path)

    # Probe metadata using utils function with include_fps=True
    try:
        raw_dt, duration_s, video_fps = probe_video_metadata(video_path, include_fps=True)
    except Exception as e:
        try:
            file_size = video_path.stat().st_size
            size_mb = file_size / (1024 * 1024)
            log.error(
                f"[extract] Metadata probe failed: "
                f"video={video_path.name} ({size_mb:.1f}MB), "
                f"error={type(e).__name__}: {e}"
            )
        except OSError:
            log.error(
                f"[extract] Metadata probe failed: video={video_path.name}, "
                f"error={type(e).__name__}: {e}"
            )
        return []

    # Fix Cycliq UTC bug using utils function
    creation_local = fix_cycliq_utc_bug(
        raw_dt,
        CFG.CAMERA_CREATION_TIME_TZ,
        CFG.CAMERA_CREATION_TIME_IS_LOCAL_WRONG_Z
    )
    creation_utc = creation_local.astimezone(timezone.utc)

    # Real-world start time (Cycliq creation_time = END of clip)
    # Using utils function with video_path for camera offset detection
    real_start_utc = infer_recording_start(creation_utc, duration_s, video_path=video_path)
    real_start_epoch = real_start_utc.timestamp()

    # Camera-to-camera offset (relative to baseline camera)
    camera_offset_s = float(camera_offsets.get(camera_name, 0.0))

    duration_int = int(duration_s)
    effective_fps = 1.0 / float(sampling_interval_s)

    # =========================================================================
    # ALIGNED SAMPLING: Compute first_sec_raw so samples fall on global grid
    # =========================================================================
    # Time from global session start to this clip's start
    time_since_global_start = real_start_epoch - global_session_start_epoch

    # Find first sampling point that falls on the global grid
    # Grid points are at: 0, interval, 2*interval, 3*interval, ... from global start
    # We need the first grid point >= time_since_global_start
    remainder = time_since_global_start % sampling_interval_s
    if remainder < 0.001:  # Effectively zero (floating point tolerance)
        first_sec_raw = 0
    else:
        first_sec_raw = int(sampling_interval_s - remainder)

    # Ensure first_sec_raw doesn't exceed clip duration
    if first_sec_raw >= duration_int:
        log.warning(
            f"[extract] {video_path.name}: first aligned sample ({first_sec_raw}s) "
            f"exceeds duration ({duration_int}s) - no samples from this clip"
        )
        return []

    log.info(
        f"[extract] {video_path.name} | duration={duration_s:.1f}s | "
        f"fps={video_fps:.2f} | offset={camera_offset_s:.3f}s | "
        f"first_sec={first_sec_raw}s | real_start={real_start_utc.isoformat()}"
    )

    rows: List[Dict[str, str]] = []

    # Sampling loop with aligned start (samples fall on global grid)
    for sec_raw in range(first_sec_raw, duration_int, sampling_interval_s):
        # 1. Raw timeline → frame number, filename, index
        frame_number = int(sec_raw * video_fps)
        index = f"{camera_name}_{clip_id}_{sec_raw:06d}"

        # 2. Real-world timestamp for this frame (now aligned to global grid)
        abs_time_epoch = real_start_epoch + float(sec_raw)
        abs_time_iso = datetime.fromtimestamp(abs_time_epoch, tz=timezone.utc).isoformat()

        session_ts_aligned = abs_time_epoch - global_session_start_epoch

        # Filter frames before GPX start
        if gpx_start_epoch > 0 and abs_time_epoch < gpx_start_epoch:
            continue

        rows.append({
            "index": index,
            "camera": camera_name,
            "clip_num": str(clip_num),
            "frame_number": str(frame_number),
            "video_path": str(video_path),
            "frame_interval": str(sampling_interval_s),
            "fps": f"{effective_fps:.3f}",

            "session_ts_s": f"{session_ts_aligned:.3f}",
            "abs_time_iso": abs_time_iso,
            "abs_time_epoch": f"{abs_time_epoch:.3f}",

            "camera_offset_s": f"{camera_offset_s:.3f}",
            "path": f"{camera_name}/{clip_id}_{sec_raw:06d}.jpg",
            "source": video_path.name,
            "raw_creation_time": creation_local.isoformat(),
            "duration_s": f"{duration_s:.3f}",

            "adjusted_start_time": real_start_utc.isoformat().replace("+00:00", "Z"),
        })

    log.info(f"[extract] Generated {len(rows)} aligned frames from {video_path.name}")
    return rows


def _write_metadata_csv(output_path: Path, all_rows: List[Dict[str, str]]):
    """
    Write frame metadata to CSV using the minimal, correct schema.

    Removes deprecated or misleading time fields and ensures downstream
    steps receive only the fields required for:
        - analyze.py
        - select.py
        - manual_selection_window.py
        - build.py
    """

    # Minimal schema for extract → analyze → select → build
    FIELDNAMES = [
        "index",
        "camera",
        "clip_num",
        "frame_number",
        "video_path",

        # Time model (clean)
        "abs_time_epoch",
        "abs_time_iso",
        "session_ts_s",
        "adjusted_start_time",

        # Camera alignment (debug)
        "camera_offset_s",

        # Clip metadata
        "duration_s",
        "source",

        # UI / analysis
        "fps",
    ]

    # If no rows, write empty CSV with header
    if not all_rows:
        log.warning("[extract] No frames to write - creating empty CSV")
        with output_path.open("w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
            writer.writeheader()
        return

    # Filter rows to minimal schema
    cleaned_rows = []
    for row in all_rows:
        cleaned = {k: row.get(k, "") for k in FIELDNAMES}
        cleaned_rows.append(cleaned)

    # Write cleaned rows
    with output_path.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
        writer.writeheader()
        writer.writerows(cleaned_rows)

    log.info(f"[extract] Wrote {len(cleaned_rows)} frame metadata rows to {output_path.name}")


def run() -> Path:
    """
    Main extract pipeline: generate frame metadata with proper alignment.
    
    Process:
        1. Load camera offsets from align step (if USE_CAMERA_OFFSETS=True)
        2. Load GPX start time for filtering
        3. For each video clip:
           a. Fix UTC bug
           b. Infer recording start
           c. Use natural timestamps (don't shift by offset)
           d. Filter edge case frames that fall outside overlap window
           e. Generate frame metadata
           f. Filter frames before GPX start
        4. Write metadata CSV
    
    Returns:
        Path to extract.csv output file
    """
    log.info("=" * 70)
    log.info("EXTRACT: Frame Metadata Generation with Alignment")
    log.info("=" * 70)
    
    # =========================================================================
    # Setup
    # =========================================================================
    report_progress(1, 5, "Initializing extraction...")
    
    output_csv = _mk(extract_path())
    videos = sorted(CFG.INPUT_VIDEOS_DIR.glob("*_*.MP4"))
    
    if not videos:
        log.warning(f"[extract] No videos found in {CFG.INPUT_VIDEOS_DIR}")
        _write_metadata_csv(output_csv, [])
        return output_csv
    
    log.info(f"[extract] Found {len(videos)} video clips")
    
    # =========================================================================
    # Load alignment data
    # =========================================================================
    if CFG.USE_CAMERA_OFFSETS:
        report_progress(2, 5, "Loading camera offsets...")
        camera_offsets = _load_camera_offsets()
    else:
        report_progress(2, 5, "Camera offsets disabled - using natural timestamps")
        log.info("[extract] USE_CAMERA_OFFSETS=False - all offsets set to 0")
        camera_offsets = {}

    # Compute global session start and per-camera REAL overlap bounds
    global_session_start_epoch, per_camera_overlap = _compute_session_time_bounds(
        videos,
        camera_offsets,
    )
    
    gpx_start_epoch = _get_gpx_start_epoch()
    sampling_interval_s = int(CFG.EXTRACT_INTERVAL_SECONDS)
    effective_fps = 1.0 / float(sampling_interval_s)
    
    log.info(f"[extract] Sampling interval: {sampling_interval_s}s (~{effective_fps:.3f} FPS)")
    
    if gpx_start_epoch > 0:
        gpx_start_dt = datetime.fromtimestamp(gpx_start_epoch, tz=timezone.utc)
        log.info(f"[extract] GPX filtering enabled: frames before {gpx_start_dt.isoformat()} will be excluded")
    else:
        log.info("[extract] No GPX filtering - all frames will be extracted")
    
    # =========================================================================
    # Process videos
    # =========================================================================
    report_progress(3, 5, f"Processing {len(videos)} videos...")
    
    all_rows: List[Dict[str, str]] = []
    
    for video_idx, video_path in enumerate(progress_iter(
        videos,
        desc="Extracting metadata",
        unit="video"
    ), start=1):
        
        report_progress(
            3 + (video_idx - 1) / len(videos),
            5,
            f"Processing {video_path.name} ({video_idx}/{len(videos)})"
        )
        
        try:
            camera_name, _clip_num, _clip_id = parse_camera_and_clip(video_path)
            overlap_bounds = per_camera_overlap.get(
                camera_name,
                (global_session_start_epoch, float("inf")),
            )

            rows = _extract_video_metadata(
                video_path,
                sampling_interval_s,
                camera_offsets,
                gpx_start_epoch,
                global_session_start_epoch,
                overlap_bounds,
            )

            all_rows.extend(rows)
            
        except Exception as e:
            log.error(
                f"[extract] Video processing failed: "
                f"video={video_path.name}, camera={camera_name}, "
                f"error={type(e).__name__}: {e}"
            )
            continue
    
    # =========================================================================
    # Write output
    # =========================================================================
    report_progress(4, 5, "Writing metadata CSV...")
    
    if all_rows:
        # Sort chronologically
        all_rows.sort(key=lambda r: float(r["abs_time_epoch"]))
        
        log.info("")
        log.info("=" * 70)
        log.info(f"[extract] ✓ Generated {len(all_rows)} frame metadata entries")
        
        # Log statistics
        cameras = set(r["camera"] for r in all_rows)
        for camera in sorted(cameras):
            cam_rows = [r for r in all_rows if r["camera"] == camera]
            log.info(f"[extract]   {camera}: {len(cam_rows)} frames")
        
        # Log time range
        first_time = all_rows[0]["abs_time_iso"]
        last_time = all_rows[-1]["abs_time_iso"]
        log.info(f"[extract] Time range: {first_time} to {last_time}")
        
    else:
        log.warning("[extract] ⚠️ No frames generated (possibly all before GPX start)")
    
    _write_metadata_csv(output_csv, all_rows)
    
    report_progress(5, 5, "Extraction complete")
    
    log.info("=" * 70)
    
    return output_csv


