# source/utils/video_utils.py
"""
Centralized video file handling with guaranteed cleanup.
Prevents memory leaks from unreleased VideoCapture objects.
"""

from __future__ import annotations
import cv2
import numpy as np
from pathlib import Path
from contextlib import contextmanager
from typing import Optional, Tuple

from .log import setup_logger

log = setup_logger("utils.video")


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

