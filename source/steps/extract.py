# source/steps/extract.py
"""
Extract frame metadata from MP4s without writing JPGs.
Applies camera offsets and GPX timeline filtering.
"""

from __future__ import annotations
import csv
import json
import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import List, Dict

from ..config import DEFAULT_CONFIG as CFG
from ..io_paths import extract_path, flatten_path, camera_offsets_path, _mk
from ..utils.log import setup_logger
from ..utils.progress_reporter import progress_iter, report_progress

log = setup_logger("steps.extract")
FFMPEG_COMMON = ["-hide_banner", "-loglevel", "error", "-y", "-nostdin"]

def _probe_meta(video_path: Path) -> tuple[datetime, float, float]:
    """Extract creation_time, duration, and FPS from video."""
    out = subprocess.check_output([
        "ffprobe", "-v", "quiet", "-print_format", "json",
        "-show_entries", "format=duration:format_tags=creation_time",
        "-show_streams", "-select_streams", "v:0",
        str(video_path)
    ])
    meta = json.loads(out)
    tags = meta.get("format", {}).get("tags", {}) or {}
    ct = tags.get("creation_time")
    if not ct:
        raise RuntimeError(f"No creation_time in {video_path.name}")
    raw_dt = datetime.fromisoformat(ct.rstrip("Z"))
    duration_s = float(meta["format"]["duration"])
    fps_str = meta["streams"][0].get("r_frame_rate", "30/1")
    fps = float(fps_str.split("/")[0]) / float(fps_str.split("/")[1])
    return raw_dt, duration_s, fps

def _get_camera_offset(camera: str) -> float:
    """Get time offset for camera from camera_offsets.json (if exists) or config."""
    offsets_file = camera_offsets_path()
    if offsets_file.exists():
        try:
            with offsets_file.open() as f:
                offsets = json.load(f)
                if camera in offsets:
                    log.debug(f"[extract] Using offset {offsets[camera]:.3f}s for {camera} from {offsets_file.name}")
                    return float(offsets[camera])
        except Exception as e:
            log.warning(f"[extract] Failed to load camera offsets from JSON: {e}")
    
    return CFG.CAMERA_TIME_OFFSETS.get(camera, 0.0)

def _derive_camera_and_clip(vp: Path) -> tuple[str, int, str]:
    """Parse camera name and clip number from filename."""
    parts = vp.stem.split("_")
    camera = "_".join(parts[:-1]) if len(parts) > 1 else parts[0]
    try:
        clip_num = int(parts[-1])
    except Exception:
        clip_num = 0
    clip_id = f"{clip_num:04d}"
    return camera, clip_num, clip_id

def _get_gpx_start_epoch() -> float:
    """Load GPX start epoch for filtering; returns 0 if unavailable."""
    gp = flatten_path()
    if not gp.exists():
        log.warning("[extract] No GPX data available, will extract all frames")
        return 0.0
    
    try:
        with gp.open() as f:
            reader = csv.DictReader(f)
            first = next(reader, None)
            if first and "gpx_epoch" in first and first["gpx_epoch"]:
                return float(first["gpx_epoch"])
    except Exception as e:
        log.warning(f"[extract] Could not read GPX start: {e}")
    
    return 0.0

def _extract_single_video(vp: Path, target_fps: float, gpx_start_epoch: float) -> List[Dict[str, str]]:
    """Generate frame metadata for one video without extracting images, with live progress reporting."""
    camera, clip_num, clip_id = _derive_camera_and_clip(vp)
    raw_dt, duration_s, video_fps = _probe_meta(vp)

    # Apply timezone and camera offset corrections
    if CFG.CAMERA_CREATION_TIME_IS_LOCAL_WRONG_Z:
        creation_local = raw_dt.replace(tzinfo=CFG.CAMERA_CREATION_TIME_TZ)
    else:
        creation_local = raw_dt.astimezone(CFG.CAMERA_CREATION_TIME_TZ)

    adjusted_local = creation_local - timedelta(seconds=duration_s)
    camera_offset_s = _get_camera_offset(camera)
    adjusted_local_corrected = adjusted_local - timedelta(seconds=camera_offset_s)
    adjusted_utc = adjusted_local_corrected.astimezone(timezone.utc)

    log.info(
        f"[extract] {vp.name} | duration={duration_s:.1f}s | fps={video_fps:.2f} | "
        f"offset={camera_offset_s:.3f}s | start_utc={adjusted_utc.isoformat()}"
    )

    if duration_s <= 0:
        return []

    # Calculate frame sampling interval
    frame_interval = max(1, int(video_fps / target_fps))
    target_frame_duration = 1.0 / target_fps

    # Estimate total frames for progress reporting
    total_frames = int(duration_s / target_frame_duration)

    rows: List[Dict[str, str]] = []
    frame_idx = 0

    # Wrap iteration with progress_iter for GUI progress bar
    for frame_idx in progress_iter(range(0, total_frames, frame_interval),
                                   desc=f"Extract {vp.name}", unit="frame"):
        session_ts_s = frame_idx * target_frame_duration
        abs_dt_utc = adjusted_utc + timedelta(seconds=session_ts_s)
        abs_epoch = abs_dt_utc.timestamp()

        # Skip frames before GPX start time
        if gpx_start_epoch > 0 and abs_epoch < gpx_start_epoch:
            continue

        virtual_frame_num = frame_idx
        index = f"{camera}_{clip_id}_{virtual_frame_num:06d}"

        rows.append({
            "index": index,
            "camera": camera,
            "clip_num": str(clip_num),
            "frame_number": str(frame_idx),
            "video_path": str(vp),
            "frame_interval": str(frame_interval),
            "fps": f"{target_fps:.3f}",
            "session_ts_s": f"{session_ts_s:.3f}",
            "abs_time_iso": abs_dt_utc.isoformat(),
            "abs_time_epoch": f"{abs_epoch:.3f}",
            "camera_offset_s": f"{camera_offset_s:.3f}",
            "path": f"{camera}/{clip_id}_{virtual_frame_num:06d}.jpg",
            "source": vp.name,
            "raw_creation_time": creation_local.isoformat(),
            "duration_s": f"{duration_s:.3f}",
            "adjusted_start_time": adjusted_local.isoformat(),
        })

        # Optional: debug log every N frames
        if frame_idx % 500 == 0:
            log.debug(f"[extract] {vp.name}: processed frame {frame_idx}/{total_frames}")

    log.info(f"[extract] Finished extracting {len(rows)} frames from {vp.name}")
    return rows

def run() -> Path:
    """Generate frame metadata CSV without writing any image files."""
    out_csv = _mk(extract_path())
    videos = sorted(CFG.INPUT_VIDEOS_DIR.glob("*_*.MP4"))
    
    if not videos:
        log.warning("[extract] No videos found")
        with out_csv.open("w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=[
                "index", "camera", "clip_num", "frame_number", "video_path", "frame_interval",
                "fps", "session_ts_s", "abs_time_iso", "abs_time_epoch", "camera_offset_s",
                "path", "source", "raw_creation_time", "duration_s", "adjusted_start_time"
            ])
            writer.writeheader()
        return out_csv
    
    target_fps = CFG.EXTRACT_FPS
    gpx_start_epoch = _get_gpx_start_epoch()
    
    log.info(f"[extract] Processing {len(videos)} videos at {target_fps:.1f} FPS (streaming mode)")
    
    # Process videos with progress reporting
    all_rows: List[Dict[str, str]] = []
    for vp in progress_iter(videos, desc="Extracting metadata", unit="video"):
        try:
            rows = _extract_single_video(vp, target_fps, gpx_start_epoch)
            all_rows.extend(rows)
        except Exception as e:
            log.error(f"[extract] Failed {vp.name}: {e}")
    
    # Write metadata CSV
    report_progress(1, 1, "Writing metadata CSV...")
    
    if all_rows:
        with out_csv.open("w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=list(all_rows[0].keys()))
            writer.writeheader()
            writer.writerows(all_rows)
        log.info(f"[extract] Wrote {len(all_rows)} frame metadata rows")
    else:
        log.warning("[extract] No frames matched GPX timeline")
        with out_csv.open("w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=[
                "index", "camera", "clip_num", "frame_number", "video_path", "frame_interval",
                "fps", "session_ts_s", "abs_time_iso", "abs_time_epoch", "camera_offset_s",
                "path", "source", "raw_creation_time", "duration_s", "adjusted_start_time"
            ])
            writer.writeheader()
    
    return out_csv

if __name__ == "__main__":
    run()