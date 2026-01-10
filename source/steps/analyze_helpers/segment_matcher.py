# source/steps/analyze_helpers/segment_matcher.py
"""
Match frame timestamps to Strava segment efforts for PR boost scoring.
"""

from __future__ import annotations
import json
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

from ...io_paths import segments_path
from ...utils.log import setup_logger

log = setup_logger("steps.analyze_helpers.segment_matcher")


class SegmentMatcher:
    """
    Matches frame timestamps to Strava segment efforts.

    Provides a score boost for frames that occur during PR efforts.
    """

    def __init__(self):
        self.segments: List[Dict] = []
        self._load_segments()

    def _load_segments(self) -> None:
        """Load segment efforts from segments.json if it exists."""
        seg_file = segments_path()
        if not seg_file.exists():
            log.debug("[segment_matcher] No segments.json found")
            return

        try:
            with open(seg_file) as f:
                self.segments = json.load(f)

            # Parse start times to epoch for fast matching
            for seg in self.segments:
                start_str = seg.get("start_time", "")
                if start_str:
                    try:
                        dt = datetime.fromisoformat(start_str.replace("Z", "+00:00"))
                        seg["start_epoch"] = dt.timestamp()
                        seg["end_epoch"] = seg["start_epoch"] + seg.get("elapsed_time", 0)
                    except (ValueError, TypeError):
                        seg["start_epoch"] = 0
                        seg["end_epoch"] = 0

            log.info(f"[segment_matcher] Loaded {len(self.segments)} PR segment(s)")

        except Exception as e:
            log.warning(f"[segment_matcher] Failed to load segments: {e}")
            self.segments = []

    def get_segment_boost(self, frame_epoch: float) -> float:
        """
        Get score boost for a frame based on segment efforts.

        Args:
            frame_epoch: Frame timestamp as Unix epoch

        Returns:
            Boost value: 1.0 for PR, 0.7 for top 3, 0.0 otherwise
        """
        if not self.segments:
            return 0.0

        for seg in self.segments:
            start = seg.get("start_epoch", 0)
            end = seg.get("end_epoch", 0)

            if start <= frame_epoch <= end:
                pr_rank = seg.get("pr_rank")
                if pr_rank == 1:
                    return 1.0  # Personal record!
                elif pr_rank in [2, 3]:
                    return 0.7  # Top 3 effort
                else:
                    return 0.3  # Any tracked segment

        return 0.0

    def get_segment_name(self, frame_epoch: float) -> Optional[str]:
        """
        Get the segment name if frame is during an effort.

        Args:
            frame_epoch: Frame timestamp as Unix epoch

        Returns:
            Segment name or None
        """
        if not self.segments:
            return None

        for seg in self.segments:
            start = seg.get("start_epoch", 0)
            end = seg.get("end_epoch", 0)

            if start <= frame_epoch <= end:
                return seg.get("name")

        return None

    def get_segment_info(self, frame_epoch: float) -> Optional[Dict]:
        """
        Get full segment info if frame is during an effort.

        Args:
            frame_epoch: Frame timestamp as Unix epoch

        Returns:
            Dict with segment details or None:
            - name: Segment name
            - distance: Distance in meters
            - average_grade: Grade percentage
            - pr_rank: 1 for PR, 2-3 for top efforts
        """
        if not self.segments:
            return None

        for seg in self.segments:
            start = seg.get("start_epoch", 0)
            end = seg.get("end_epoch", 0)

            if start <= frame_epoch <= end:
                return {
                    "name": seg.get("name", ""),
                    "distance": seg.get("distance", 0),
                    "average_grade": seg.get("average_grade", 0),
                    "pr_rank": seg.get("pr_rank", 0),
                    "elapsed_time": seg.get("elapsed_time", 0),
                }

        return None

    def get_stats(self) -> Dict:
        """Return segment matching statistics."""
        return {
            "segments_loaded": len(self.segments),
            "pr_count": sum(1 for s in self.segments if s.get("pr_rank") == 1),
        }
