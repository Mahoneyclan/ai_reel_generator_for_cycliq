# source/utils/video_utils.py
"""
Centralized video file handling with guaranteed cleanup.
Prevents memory leaks from unreleased VideoCapture objects.
"""

from __future__ import annotations
import cv2
import numpy as np
import json
import subprocess
from pathlib import Path
from contextlib import contextmanager
from datetime import datetime, timedelta
from typing import Optional, Tuple

from .log import setup_logger

log = setup_logger("utils.video")


# ============================================================================
# Video Capture Utilities
# ============================================================================

@contextmanager
def open_video(video_path: Path):
    """
    Context manager for safe video file handling.
    Guarantees release even on exception.
    
    Usage:
        with open_video(path) as cap:
            ret, frame = cap.read()
    
    Args:
        video_path: Path to video file
        
    Yields:
        cv2.VideoCapture object
        
    Raises:
        IOError: If video cannot be opened
    """
    cap = None
    try:
        cap = cv2.VideoCapture(str(video_path))
        if not cap.isOpened():
            raise IOError(f"Cannot open video: {video_path}")
        yield cap
    finally:
        if cap is not None:
            cap.release()
            log.debug(f"Released video: {video_path.name}")


def extract_frame_safe(video_path: Path, frame_number: int) -> Optional[np.ndarray]:
    """
    Extract single frame with guaranteed cleanup.
    
    Args:
        video_path: Path to video file
        frame_number: Zero-based frame index
        
    Returns:
        RGB numpy array (H, W, 3) or None if extraction fails
    """
    try:
        with open_video(video_path) as cap:
            # Validate frame number
            total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
            if frame_number >= total_frames:
                log.warning(
                    f"Frame {frame_number} >= total {total_frames} in {video_path.name}"
                )
                return None
            
            # Seek and extract
            cap.set(cv2.CAP_PROP_POS_FRAMES, frame_number)
            ret, frame = cap.read()
            
            if not ret:
                log.warning(f"Failed to read frame {frame_number} from {video_path.name}")
                return None
            
            # Convert BGR to RGB
            return cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            
    except Exception as e:
        log.error(f"Frame extraction failed for {video_path.name}: {e}")
        return None


# ============================================================================
# Video Metadata Utilities (shared by align.py and extract.py)
# ============================================================================

def probe_video_metadata(video_path: Path, include_fps: bool = False) -> Tuple:
    """
    Extract creation_time, duration, and optionally FPS from video metadata.
    
    Args:
        video_path: Path to MP4 file
        include_fps: If True, also return FPS as third element
        
    Returns:
        Tuple of (raw_creation_datetime, duration_seconds) or
        (raw_creation_datetime, duration_seconds, fps) if include_fps=True
        
    Raises:
        RuntimeError: If metadata cannot be extracted
    """
    try:
        out = subprocess.check_output([
            "ffprobe", "-v", "quiet", "-print_format", "json",
            "-show_entries", "format=duration:format_tags=creation_time",
            "-show_streams", "-select_streams", "v:0",
            str(video_path)
        ], stderr=subprocess.DEVNULL)
        
        meta = json.loads(out)
        
        # Extract creation time from format or stream tags
        tags_format = meta.get("format", {}).get("tags", {}) or {}
        tags_stream = meta["streams"][0].get("tags", {}) or {}
        
        creation_time_str = (
            tags_stream.get("creation_time") or
            tags_format.get("creation_time")
        )
        
        if not creation_time_str:
            raise RuntimeError("No creation_time in metadata")
        
        # Parse ISO format, handle both with and without 'Z' suffix
        raw_dt = datetime.fromisoformat(creation_time_str.rstrip("Z"))
        
        # Extract duration
        duration_s = float(meta["format"]["duration"])
        
        if include_fps:
            # Extract FPS
            fps_str = meta["streams"][0].get("r_frame_rate", "30/1")
            num, denom = fps_str.split("/")
            fps = float(num) / float(denom)
            return raw_dt, duration_s, fps
        else:
            return raw_dt, duration_s
        
    except subprocess.CalledProcessError as e:
        raise RuntimeError(f"ffprobe failed: {e}")
    except (KeyError, ValueError, json.JSONDecodeError) as e:
        raise RuntimeError(f"Invalid metadata format: {e}")


def fix_cycliq_utc_bug(raw_dt: datetime, camera_tz, is_local_wrong_z: bool) -> datetime:
    """
    Fix Cycliq's UTC bug.
    
    Cycliq cameras store local time but mark it with 'Z' (UTC indicator).
    This function corrects the timezone interpretation.
    
    Args:
        raw_dt: Raw datetime from video metadata
        camera_tz: Correct timezone for the camera
        is_local_wrong_z: If True, raw time is local with wrong Z marker
        
    Returns:
        Corrected datetime in proper timezone
    """
    if is_local_wrong_z:
        # Raw time is actually local time, not UTC - reinterpret with correct timezone
        creation_local = raw_dt.replace(tzinfo=camera_tz)
    else:
        # Raw time is genuinely UTC, convert to local
        creation_local = raw_dt.astimezone(camera_tz)
    
    return creation_local


def parse_camera_and_clip(video_path: Path) -> Tuple[str, int, str]:
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


def extract_camera_name(video_path: Path) -> str:
    """
    Extract camera identifier from video filename.
    
    Expected format: CameraName_NNNN.MP4
    
    Args:
        video_path: Path to video file
        
    Returns:
        Camera name (everything before the last underscore)
    """
    camera_name, _, _ = parse_camera_and_clip(video_path)
    return camera_name


def detect_camera_creation_time_offset(video_path: Path) -> float:
    """
    Detect how many seconds the creation_time is offset from actual end time.
    
    Different Cycliq camera models have different behaviors:
    - Fly12Sport: creation_time = end of recording + 2 seconds
    - Fly6Pro: creation_time = exact end of recording
    
    This offset must be added to duration before subtracting from creation_time
    to get the correct recording start time.
    
    Args:
        video_path: Path to video file
        
    Returns:
        Offset in seconds to add to duration
    """
    camera_name = extract_camera_name(video_path)
    
    # Known offsets for Cycliq cameras (empirically determined)
    known_offsets = {
        "Fly12Sport": 3.0,  # creation_time is end + 2s
        "Fly6Pro": 0.0,     # creation_time is exactly at end
    }
    
    offset = known_offsets.get(camera_name, 0.0)
    
    if offset > 0:
        log.debug(
            f"[video_utils] {camera_name} has {offset}s creation_time offset"
        )
    
    return offset


def infer_recording_start(
    creation_time_utc: datetime,
    duration_s: float,
    video_path: Optional[Path] = None
) -> datetime:
    """
    Infer recording start time from creation time and duration.
    
    Camera metadata contains end time (or near-end), not start time.
    Different camera models have different creation_time behaviors.
    
    Args:
        creation_time_utc: Corrected creation time in UTC
        duration_s: Video duration in seconds
        video_path: Path to video file (for auto-detecting camera offset)
        
    Returns:
        Inferred recording start time in UTC
    """
    offset = 0.0
    if video_path:
        offset = detect_camera_creation_time_offset(video_path)
    
    return creation_time_utc - timedelta(seconds=duration_s + offset)