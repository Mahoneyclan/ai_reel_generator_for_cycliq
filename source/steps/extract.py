# source/steps/extract.py
"""
Extract frame metadata from MP4s without writing JPGs.

FIXED: Camera offset handling
- Uses natural timestamps (doesn't shift start times)
- Filters edge case frames that have no partner camera
- Allows proper moment bucketing by abs_time_epoch
"""

from __future__ import annotations
import csv
import json
import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import List, Dict, Optional, Tuple

from ..config import DEFAULT_CONFIG as CFG
from ..io_paths import extract_path, flatten_path, camera_offsets_path, _mk
from ..utils.log import setup_logger
from ..utils.progress_reporter import progress_iter, report_progress

log = setup_logger("steps.extract")

# FFmpeg constants
FFMPEG_COMMON = ["-hide_banner", "-loglevel", "error", "-y", "-nostdin"]


def _probe_video_metadata(video_path: Path) -> Tuple[datetime, float, float]:
    """
    Extract creation_time, duration, and FPS from video.
    
    Args:
        video_path: Path to MP4 file
        
    Returns:
        Tuple of (raw_creation_datetime, duration_seconds, fps)
        
    Raises:
        RuntimeError: If metadata extraction fails
    """
    try:
        out = subprocess.check_output([
            "ffprobe", "-v", "quiet", "-print_format", "json",
            "-show_entries", "format=duration:format_tags=creation_time",
            "-show_streams", "-select_streams", "v:0",
            str(video_path)
        ], stderr=subprocess.DEVNULL)
        
        meta = json.loads(out)
        
        # Extract creation time
        tags = meta.get("format", {}).get("tags", {}) or {}
        creation_time_str = tags.get("creation_time")
        if not creation_time_str:
            raise RuntimeError("No creation_time in metadata")
        
        raw_dt = datetime.fromisoformat(creation_time_str.rstrip("Z"))
        
        # Extract duration
        duration_s = float(meta["format"]["duration"])
        
        # Extract FPS
        fps_str = meta["streams"][0].get("r_frame_rate", "30/1")
        num, denom = fps_str.split("/")
        fps = float(num) / float(denom)
        
        return raw_dt, duration_s, fps
        
    except subprocess.CalledProcessError as e:
        raise RuntimeError(f"ffprobe failed: {e}")
    except (KeyError, ValueError, json.JSONDecodeError) as e:
        raise RuntimeError(f"Invalid metadata: {e}")


def _fix_utc_bug(raw_dt: datetime) -> datetime:
    """
    Stage 1: Fix Cycliq's UTC bug.
    
    Camera stores local time but marks it with 'Z' (UTC indicator).
    
    Args:
        raw_dt: Raw datetime from video metadata
        
    Returns:
        Corrected datetime with proper timezone
    """
    if CFG.CAMERA_CREATION_TIME_IS_LOCAL_WRONG_Z:
        # Raw time is local, not UTC - reinterpret
        creation_local = raw_dt.replace(tzinfo=CFG.CAMERA_CREATION_TIME_TZ)
    else:
        # Raw time is genuinely UTC
        creation_local = raw_dt.astimezone(CFG.CAMERA_CREATION_TIME_TZ)
    
    return creation_local


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


def _parse_camera_and_clip(video_path: Path) -> Tuple[str, int, str]:
    """
    Parse camera name and clip number from video filename.
    
    Expected format: CameraName_NNNN.MP4
    
    Args:
        video_path: Path to video file
        
    Returns:
        Tuple of (camera_name, clip_number, clip_id_padded)
    """
    stem = video_path.stem
    parts = stem.split("_")
    
    # Camera name is everything except last part
    camera_name = "_".join(parts[:-1]) if len(parts) > 1 else parts[0]
    
    # Clip number is last part
    try:
        clip_num = int(parts[-1])
    except (ValueError, IndexError):
        clip_num = 0
    
    # Zero-padded clip ID
    clip_id = f"{clip_num:04d}"
    
    return camera_name, clip_num, clip_id


def _extract_video_metadata(
    video_path: Path,
    sampling_interval_s: int,
    camera_offsets: Dict[str, float],
    gpx_start_epoch: float
) -> List[Dict[str, str]]:
    """
    Generate frame metadata for one video clip.
    
    FIXED: Uses natural timestamps and filters edge case frames.
    
    Args:
        video_path: Path to video file
        sampling_interval_s: Seconds between sampled frames
        camera_offsets: Camera alignment offsets
        gpx_start_epoch: GPX start time for filtering
        
    Returns:
        List of frame metadata dicts
    """
    # Parse filename
    camera_name, clip_num, clip_id = _parse_camera_and_clip(video_path)
    
    # Probe video
    try:
        raw_dt, duration_s, video_fps = _probe_video_metadata(video_path)
    except Exception as e:
        log.error(f"[extract] Failed to probe {video_path.name}: {e}")
        return []
    
    # =========================================================================
    # TIMESTAMP CORRECTION
    # =========================================================================
    
    # Stage 1: Fix UTC bug
    creation_local = _fix_utc_bug(raw_dt)
    creation_utc = creation_local.astimezone(timezone.utc)
    
    # Stage 2: Infer recording start (end - duration = start)
    clip_start_utc = creation_utc - timedelta(seconds=duration_s)
    
    # Stage 3: Apply camera offset to create unified real-world timeline
    # ✅ FIX: Offset is subtracted (earlier offset = camera started later, so shift backward)
    camera_offset_s = camera_offsets.get(camera_name, 0.0)
    aligned_start_utc = clip_start_utc - timedelta(seconds=camera_offset_s)
    
    # =========================================================================
    # Calculate absolute time overlap window
    # =========================================================================
    
    # Calculate when ALL cameras can record together (overlap window)
    # Overlap starts when LAST camera starts (max offset)
    # Overlap ends when FIRST camera ends (baseline + duration)
    
    if camera_offsets:
        min_offset = min(camera_offsets.values())  # Baseline (earliest start)
        max_offset = max(camera_offsets.values())  # Latest start
        
        # For THIS camera, calculate its absolute timeline
        this_start_abs = camera_offset_s  # Relative to baseline
        this_end_abs = camera_offset_s + duration_s
        
        # Overlap window in absolute timeline
        overlap_start_abs = max_offset  # When all cameras have started
        overlap_end_abs = min_offset + duration_s  # When first camera ends
        
        # Convert to session_ts_s for THIS camera
        # Only keep frames where: overlap_start_abs <= (this_start_abs + sec) <= overlap_end_abs
        min_sec = max(0, int(overlap_start_abs - this_start_abs))
        max_sec = min(int(duration_s), int(overlap_end_abs - this_start_abs))
    else:
        # No offsets, use all frames
        min_sec = 0
        max_sec = int(duration_s)
    
    # =========================================================================
    # Log clip info with overlap window details
    # =========================================================================
    
    frames_skipped_start = min_sec // sampling_interval_s
    frames_skipped_end = (int(duration_s) - max_sec) // sampling_interval_s
    frames_kept = (max_sec - min_sec) // sampling_interval_s
    
    log.info(
        f"[extract] {video_path.name} | "
        f"duration={duration_s:.1f}s | fps={video_fps:.2f} | "
        f"offset={camera_offset_s:.3f}s | "
        f"keep=[{min_sec}s-{max_sec}s] ({frames_kept} frames) | "
        f"skip_start={frames_skipped_start} skip_end={frames_skipped_end}"
    )
    
    if duration_s <= 0:
        log.warning(f"[extract] {video_path.name} has zero duration - skipping")
        return []
    
    if max_sec <= min_sec:
        overlap_duration = max_sec - min_sec
        log.warning(
            f"[extract] {video_path.name} has no overlap with other cameras "
            f"(offset={camera_offset_s:.1f}s creates gap)"
        )
        return []
    
    # =========================================================================
    # Generate frame metadata with edge case filtering
    # =========================================================================
    rows: List[Dict[str, str]] = []
    effective_fps = 1.0 / float(sampling_interval_s)
    
    for sec in range(0, int(duration_s), sampling_interval_s):
        # ✅ EDGE CASE FILTER: Skip frames outside overlap window
        if sec < min_sec or sec >= max_sec:
            continue
        
        # Compute absolute time for this frame (using NATURAL timeline)
        frame_time_utc = aligned_start_utc + timedelta(seconds=sec)
        frame_epoch = frame_time_utc.timestamp()
        
        # Filter: Skip frames before GPX starts
        if gpx_start_epoch > 0 and frame_epoch < gpx_start_epoch:
            continue
        
        # Compute frame number in original video
        frame_number = int(sec * video_fps)
        
        # Generate unique index
        index = f"{camera_name}_{clip_id}_{sec:06d}"
        
        # Build metadata row
        rows.append({
            "index": index,
            "camera": camera_name,
            "clip_num": str(clip_num),
            "frame_number": str(frame_number),
            "video_path": str(video_path),
            "frame_interval": str(sampling_interval_s),
            "fps": f"{effective_fps:.3f}",
            "session_ts_s": f"{sec:.3f}",
            "abs_time_iso": frame_time_utc.isoformat(),
            "abs_time_epoch": f"{frame_epoch:.3f}",
            "camera_offset_s": f"{camera_offset_s:.3f}",
            "path": f"{camera_name}/{clip_id}_{sec:06d}.jpg",
            "source": video_path.name,
            "raw_creation_time": creation_local.isoformat(),
            "duration_s": f"{duration_s:.3f}",
            "adjusted_start_time": clip_start_utc.isoformat(),
        })
    
    log.info(
        f"[extract] Generated {len(rows)} frames from {video_path.name} "
        f"(skipped {frames_skipped_start} at start, {frames_skipped_end} at end due to camera overlap)"
    )
    return rows


def _write_metadata_csv(output_path: Path, all_rows: List[Dict[str, str]]):
    """
    Write frame metadata to CSV.
    
    Args:
        output_path: Path to output CSV file
        all_rows: List of frame metadata dicts
    """
    if not all_rows:
        # Write empty CSV with headers
        log.warning("[extract] No frames to write - creating empty CSV")
        with output_path.open("w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=[
                "index", "camera", "clip_num", "frame_number", "video_path",
                "frame_interval", "fps", "session_ts_s", "abs_time_iso",
                "abs_time_epoch", "camera_offset_s", "path", "source",
                "raw_creation_time", "duration_s", "adjusted_start_time"
            ])
            writer.writeheader()
        return
    
    # Write rows
    with output_path.open("w", newline="") as f:
        fieldnames = list(all_rows[0].keys())
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(all_rows)
    
    log.info(f"[extract] Wrote {len(all_rows)} frame metadata rows to {output_path.name}")


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
            rows = _extract_video_metadata(
                video_path,
                sampling_interval_s,
                camera_offsets,
                gpx_start_epoch
            )
            all_rows.extend(rows)
            
        except Exception as e:
            log.error(f"[extract] Failed to process {video_path.name}: {e}")
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


if __name__ == "__main__":
    run()