# source/steps/analyzers/scene_detector.py
"""
Scene change detection using temporal frame differencing.
Identifies interesting visual transitions (action, camera movement, new scenes).
"""

from __future__ import annotations
import numpy as np
import cv2
from typing import Dict
from collections import deque

from ...config import DEFAULT_CONFIG as CFG
from ...utils.log import setup_logger

log = setup_logger("steps.analyzers.scene_detector")


class SceneDetector:
    """
    Scene change detector with temporal window.
    Compares frames across a time window (e.g., 5-10 seconds) instead of just adjacent frames.
    Better for detecting significant scene changes vs. gradual camera movement.
    """
    
    def __init__(self, comparison_window_s: float = 5.0, fps: float = 1.0):
        """
        Args:
            comparison_window_s: How many seconds back to compare (default 5s)
            fps: Frame rate of extracted frames (default 1.0 from EXTRACT_FPS)
        """
        self.comparison_window_s = comparison_window_s
        self.fps = fps
        self.max_frames_to_keep = max(1, int(comparison_window_s * fps))
        
        # Store frame history per camera (circular buffer)
        self.frame_history: Dict[str, deque] = {}
        self.frame_counts: Dict[str, int] = {}
        self.scene_scores: Dict[str, list] = {}
    
    def compute_scene_score(self, frame: np.ndarray, camera: str) -> float:
        """
        Compute scene change score by comparing current frame to frame from N seconds ago.
        
        Args:
            frame: RGB numpy array (H, W, 3)
            camera: Camera identifier for per-camera history tracking
        
        Returns:
            0.0 = no change (static scene)
            1.0 = complete scene change (new environment/action)
        """
        if frame is None:
            return 0.0
        
        # Convert to grayscale thumbnail for efficient comparison
        gray = cv2.cvtColor(frame, cv2.COLOR_RGB2GRAY)
        thumbnail = cv2.resize(gray, (64, 64), interpolation=cv2.INTER_AREA)
        
        # Initialize history for this camera
        if camera not in self.frame_history:
            self.frame_history[camera] = deque(maxlen=self.max_frames_to_keep)
            self.frame_counts[camera] = 0
            self.scene_scores[camera] = []
        
        history = self.frame_history[camera]
        
        # First frame - baseline
        if len(history) == 0:
            history.append(thumbnail)
            self.frame_counts[camera] += 1
            return 0.0
        
        # Compare to oldest available frame (N seconds ago)
        comparison_frame = history[0]
        
        # Compute pixel-level difference
        diff = np.mean(np.abs(comparison_frame.astype(np.float32) - thumbnail.astype(np.float32)))
        score = float(diff / 255.0)
        
        # Add current frame to history (will auto-evict oldest when full)
        history.append(thumbnail)
        self.frame_counts[camera] += 1
        self.scene_scores[camera].append(score)
        
        # Log significant changes
        if score > 0.4:  # Lowered threshold since comparing across longer time
            log.debug(
                f"[scene_detector] High change: {camera} frame {self.frame_counts[camera]}, "
                f"score={score:.3f} (comparing to {len(history)} frames / "
                f"{len(history) / self.fps:.1f}s ago)"
            )
        
        return score
    
    def get_stats(self) -> Dict:
        """Return processing statistics."""
        stats = {
            "cameras_processed": len(self.frame_history),
            "frame_counts": dict(self.frame_counts),
            "comparison_window_s": self.comparison_window_s,
        }
        
        # Add score statistics per camera
        for camera, scores in self.scene_scores.items():
            if scores:
                stats[f"{camera}_mean_scene"] = f"{np.mean(scores):.3f}"
                stats[f"{camera}_max_scene"] = f"{np.max(scores):.3f}"
                stats[f"{camera}_median_scene"] = f"{np.median(scores):.3f}"
                
                # Count high-change frames (adjusted threshold for longer window)
                high_change_count = sum(1 for s in scores if s > 0.3)
                stats[f"{camera}_high_changes"] = high_change_count
                stats[f"{camera}_high_change_pct"] = f"{(high_change_count / len(scores) * 100):.1f}%"
        
        return stats
    
    def cleanup(self):
        """Release cached data."""
        self.frame_history.clear()
        self.frame_counts.clear()
        self.scene_scores.clear()