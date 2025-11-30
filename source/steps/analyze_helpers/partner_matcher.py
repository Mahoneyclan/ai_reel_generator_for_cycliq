# source/steps/analyze_helpers/partner_matcher.py
"""
Partner camera matching for dual-camera setups.
Finds closest-in-time opposite camera frame for PiP video creation.
"""

from __future__ import annotations
from pathlib import Path
from typing import Dict, List

from ...config import DEFAULT_CONFIG as CFG
from ...utils.log import setup_logger

log = setup_logger("steps.analyze_helpers.partner_matcher")


class PartnerMatcher:
    """Matches frames between front and rear cameras."""
    
    def __init__(self):
        self.matches = 0
        self.misses = 0
    
    def find_partner(self, frame_row: Dict, all_frames: List[Dict]) -> Dict:
        """
        Find closest-in-time opposite camera frame within tolerance.
        
        Args:
            frame_row: Current frame metadata
            all_frames: List of all frame metadata (pre-sorted by camera+time)
            
        Returns:
            Dict with partner frame info (or empty fields if no match)
        """
        camera = frame_row.get("camera", "")
        if not camera:
            return self._empty_partner(camera)
        
        # Determine opposite camera
        other_camera = "Fly6Pro" if camera == "Fly12Sport" else "Fly12Sport"
        other_frames = [f for f in all_frames if f.get("camera") == other_camera]
        
        if not other_frames:
            self.misses += 1
            return self._empty_partner(other_camera)
        
        # Find closest frame within tolerance
        target_time = float(frame_row.get("abs_time_epoch", 0) or 0.0)
        best_frame, best_diff = None, float("inf")
        
        for f in other_frames:
            f_time = float(f.get("abs_time_epoch", 0) or 0.0)
            dt = abs(f_time - target_time)
            if dt <= CFG.PARTNER_TIME_TOLERANCE_S and dt < best_diff:
                best_frame, best_diff = f, dt
        
        if best_frame:
            self.matches += 1
            partner_video_path = best_frame.get("video_path", "")
            partner_source = Path(partner_video_path).name if partner_video_path else ""
            
            return {
                "partner_video_path": partner_video_path,
                "partner_frame_number": best_frame.get("frame_number", ""),
                "partner_index": best_frame.get("index", ""),
                "partner_camera": other_camera,
                "partner_abs_time_diff": f"{best_diff:.3f}",
                "partner_source": partner_source,
            }
        
        self.misses += 1
        return self._empty_partner(other_camera)
    
    def _empty_partner(self, camera: str = "") -> Dict:
        """Return empty partner metadata."""
        return {
            "partner_video_path": "",
            "partner_frame_number": "",
            "partner_index": "",
            "partner_camera": camera,
            "partner_abs_time_diff": "",
            "partner_source": "",
        }
    
    def get_stats(self) -> Dict:
        """Return matching statistics."""
        total = self.matches + self.misses
        match_pct = (self.matches / total * 100) if total > 0 else 0
        
        return {
            "partner_matches": self.matches,
            "partner_misses": self.misses,
            "partner_match_pct": f"{match_pct:.1f}%"
        }