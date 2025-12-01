# source/steps/align.py
"""
Core alignment step: compute CAMERA_TIME_OFFSETS vs corrected GPX anchor.
Persists offsets to working/camera_offsets.json and auto-applies to CFG.
"""

from __future__ import annotations
import json
import csv
import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, Tuple, List

from ..config import DEFAULT_CONFIG as CFG
from ..io_paths import flatten_path, camera_offsets_path, _mk
from ..utils.log import setup_logger
from ..utils.progress_reporter import progress_iter, report_progress

log = setup_logger("steps.align")
SANITY_THRESHOLD_S = 3600.0  # 1 hour

def _probe_meta(video_path: Path) -> Tuple[datetime, float]:
    """Extract creation_time and duration from video metadata."""
    out = subprocess.check_output([
        "ffprobe", "-v", "quiet", "-print_format", "json",
        "-show_entries", "format=duration:format_tags=creation_time",
        str(video_path)
    ])
    meta = json.loads(out)
    tags = meta.get("format", {}).get("tags", {}) or {}
    ct = tags.get("creation_time")
    if not ct:
        raise RuntimeError(f"No creation_time in {video_path.name}")
    raw_dt = datetime.fromisoformat(ct.replace("Z", "+00:00"))
    duration_s = float(meta["format"]["duration"])
    return raw_dt, duration_s

def _adjust_start_local(raw_dt: datetime, duration_s: float) -> datetime:
    """Compute actual video start time (adjust for Cycliq timezone bug)."""
    if CFG.CAMERA_CREATION_TIME_IS_LOCAL_WRONG_Z:
        creation_local = raw_dt.replace(tzinfo=CFG.CAMERA_CREATION_TIME_TZ)
    else:
        creation_local = raw_dt.astimezone(CFG.CAMERA_CREATION_TIME_TZ)
    return creation_local - timedelta(seconds=duration_s)

def _get_corrected_gpx_start() -> datetime | None:
    """Get first GPX timestamp from flatten.csv, return None if unavailable."""
    gp = flatten_path()
    if not gp.exists():
        log.warning("[align] flatten.csv not found; run flatten step first")
        return None
    
    try:
        with gp.open() as f:
            reader = csv.DictReader(f)
            first = next(reader, None)
            if not first:
                log.warning("[align] flatten.csv is empty")
                return None
            if "gpx_epoch" not in first:
                log.warning("[align] flatten.csv missing gpx_epoch column")
                return None
            if not first["gpx_epoch"]:
                log.warning("[align] flatten.csv has no GPX data (empty epoch)")
                return None
            return datetime.fromtimestamp(float(first["gpx_epoch"]), tz=timezone.utc)
    except Exception as e:
        log.warning(f"[align] Failed to read GPX start time: {e}")
        return None

def _derive_camera_name(vp: Path) -> str:
    """Extract camera name from video filename."""
    parts = vp.stem.split("_")
    return "_".join(parts[:-1]) if len(parts) > 1 else parts[0]

def run() -> Dict[str, float]:
    """Compute camera time offsets and auto-apply."""
    report_progress(1, 4, "Loading GPX reference time...")
    
    gpx_start = _get_corrected_gpx_start()
    
    if gpx_start is None:
        log.warning("[align] ⚠️  No GPX data available")
        log.warning("[align] Skipping camera alignment (no GPS to align to)")
        log.warning("[align] Camera offsets will remain at 0.0s")
        
        normalized = {cam: 0.0 for cam in CFG.CAMERA_WEIGHTS.keys()}
        
        sidecar = _mk(camera_offsets_path())
        with sidecar.open("w") as f:
            json.dump(normalized, f, indent=2, sort_keys=True)
        
        return normalized
    
    log.info(f"[align] GPX start (corrected) = {gpx_start.isoformat()}")

    report_progress(2, 4, "Scanning video files...")
    videos = sorted(CFG.INPUT_VIDEOS_DIR.glob("*_*.MP4"))

    if not videos:
        log.warning("[align] ❌ No videos found matching pattern '*_*.MP4'")
        log.warning(f"[align] Searched in: {CFG.INPUT_VIDEOS_DIR}")
        return {}

    by_cam: Dict[str, List[Path]] = {}
    for v in videos:
        cam = _derive_camera_name(v)
        by_cam.setdefault(cam, []).append(v)

    report_progress(3, 4, f"Computing offsets for {len(by_cam)} cameras...")
    
    offsets_vs_gpx: Dict[str, float] = {}
    
    for cam_idx, (cam, files) in enumerate(by_cam.items(), start=1):
        # Sub-progress reporting
        report_progress(3, 4, f"Analyzing camera {cam_idx}/{len(by_cam)}: {cam}")
        
        candidates: List[Tuple[str, float]] = []
        for f in files:
            try:
                raw_dt, dur = _probe_meta(f)
                start_local = _adjust_start_local(raw_dt, dur)
                start_utc = start_local.astimezone(timezone.utc)
                offset_s = start_utc.timestamp() - gpx_start.timestamp()
                candidates.append((f.name, offset_s))
            except Exception as e:
                log.warning(f"[align] Probe failed {f.name}: {e}")

        if not candidates:
            continue

        best_file, best_offset = min(candidates, key=lambda c: abs(c[1]))
        if abs(best_offset) > SANITY_THRESHOLD_S:
            log.warning(f"[align] {cam} offset vs GPX is large ({best_offset:.1f}s)")

        log.info(f"[align] {cam}: {best_offset:.3f}s vs GPX (from {best_file})")
        offsets_vs_gpx[cam] = best_offset

    if not offsets_vs_gpx:
        return {}

    # Normalize offsets
    report_progress(4, 4, "Normalizing and saving offsets...")
    
    min_offset = min(offsets_vs_gpx.values())
    normalized = {cam: round(off - min_offset, 3) for cam, off in offsets_vs_gpx.items()}

    # Persist to JSON
    sidecar = _mk(camera_offsets_path())
    with sidecar.open("w") as f:
        json.dump(normalized, f, indent=2, sort_keys=True)

    log.info(f"[align] Offsets saved to {sidecar}")

    # Auto-apply to config
    CFG.CAMERA_TIME_OFFSETS.update(normalized)
    log.info("[align] Offsets applied to config for this run")

    return normalized

if __name__ == "__main__":
    run()