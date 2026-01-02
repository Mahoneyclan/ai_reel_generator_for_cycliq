# source/models/time_model.py
"""
TimeModel: Encapsulates frame/moment timing with derived calculations.

Centralizes the complex time conversions scattered across:
- extract.py (abs_time_epoch, adjusted_start_time generation)
- clip_renderer.py (t_start computation)
- analyze.py (moment_id assignment)
- build.py (moment-based grouping)

Time Model:
    abs_time_epoch      = World-aligned timestamp (aligned to global grid)
    adjusted_start_time = Real start time of source video clip (UTC)
    clip_start_epoch    = adjusted_start_time as epoch seconds
    offset_in_clip      = abs_time_epoch - clip_start_epoch
    moment_id           = floor(abs_time_epoch / sample_interval)
    t_start             = max(0, offset_in_clip - pre_roll)
"""

from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime
from typing import Dict, Optional

from ..utils.common import parse_iso_time, safe_float
from ..utils.log import setup_logger

log = setup_logger("models.time_model")


@dataclass
class TimeModel:
    """
    Encapsulates frame/moment timing with derived calculations.

    Attributes:
        abs_time_epoch: World-aligned timestamp (seconds since Unix epoch).
                       Aligned to global sampling grid for camera pairing.
        adjusted_start_time: Video clip start time (UTC datetime).
                            Derived from creation_time - duration.
        duration_s: Video clip duration in seconds.
        sample_interval: Sampling interval for moment_id bucketing (default 5.0s).
    """

    abs_time_epoch: float
    adjusted_start_time: datetime
    duration_s: float
    sample_interval: float = 5.0

    # -------------------------------------------------------------------------
    # Factory Methods
    # -------------------------------------------------------------------------

    @classmethod
    def from_row(
        cls,
        row: Dict,
        sample_interval: Optional[float] = None,
    ) -> Optional["TimeModel"]:
        """
        Construct TimeModel from a CSV row dictionary.

        Expected row keys:
            - abs_time_epoch: float or string (required)
            - adjusted_start_time: ISO timestamp string (required)
            - duration_s: float or string (required)

        Args:
            row: Dictionary from CSV with time fields
            sample_interval: Override default sample interval (5.0s)

        Returns:
            TimeModel instance, or None if parsing fails
        """
        try:
            abs_epoch = safe_float(row.get("abs_time_epoch"))
            if abs_epoch == 0.0:
                log.debug("[TimeModel] abs_time_epoch is zero or missing")
                return None

            start_iso = row.get("adjusted_start_time")
            if not start_iso:
                log.debug("[TimeModel] adjusted_start_time is missing")
                return None

            adjusted_start = parse_iso_time(start_iso)
            if adjusted_start is None:
                log.debug(f"[TimeModel] Could not parse adjusted_start_time: {start_iso}")
                return None

            duration = safe_float(row.get("duration_s"))

            interval = sample_interval if sample_interval is not None else 5.0

            return cls(
                abs_time_epoch=abs_epoch,
                adjusted_start_time=adjusted_start,
                duration_s=duration,
                sample_interval=interval,
            )

        except Exception as e:
            log.debug(f"[TimeModel] Failed to create from row: {e}")
            return None

    # -------------------------------------------------------------------------
    # Derived Properties
    # -------------------------------------------------------------------------

    @property
    def moment_id(self) -> int:
        """
        Compute moment bucket for camera pairing.

        Frames from different cameras at the same real-world moment
        will have identical moment_ids when using aligned sampling.

        Returns:
            Integer bucket ID: floor(abs_time_epoch / sample_interval)
        """
        return int(self.abs_time_epoch // self.sample_interval)

    @property
    def clip_start_epoch(self) -> float:
        """
        Clip start as epoch seconds.

        Returns:
            adjusted_start_time converted to Unix timestamp
        """
        return self.adjusted_start_time.timestamp()

    @property
    def offset_in_clip(self) -> float:
        """
        Position of this moment within the source video.

        Returns:
            Seconds from clip start to this moment (can be negative if misaligned)
        """
        return self.abs_time_epoch - self.clip_start_epoch

    @property
    def abs_time_iso(self) -> str:
        """
        ISO format string for abs_time_epoch.

        Returns:
            ISO 8601 timestamp with Z suffix
        """
        from datetime import timezone
        dt = datetime.fromtimestamp(self.abs_time_epoch, tz=timezone.utc)
        return dt.isoformat().replace("+00:00", "Z")

    # -------------------------------------------------------------------------
    # Computed Methods
    # -------------------------------------------------------------------------

    def t_start(self, pre_roll: float = 0.0) -> float:
        """
        Compute FFmpeg seek position with optional pre-roll.

        Args:
            pre_roll: Seconds to start before the moment (default 0.0)

        Returns:
            Seek position in seconds, clamped to >= 0
        """
        return max(0.0, self.offset_in_clip - pre_roll)

    def is_valid_seek(self) -> bool:
        """
        Check if offset is within clip bounds.

        Returns:
            True if 0 <= offset_in_clip < duration_s
        """
        return 0 <= self.offset_in_clip < self.duration_s

    def is_valid_seek_with_duration(self, clip_duration: float) -> bool:
        """
        Check if seek + clip_duration fits within source video.

        Args:
            clip_duration: Duration of output clip in seconds

        Returns:
            True if the full clip can be extracted
        """
        return (
            0 <= self.offset_in_clip
            and self.offset_in_clip + clip_duration <= self.duration_s
        )

    # -------------------------------------------------------------------------
    # String Representation
    # -------------------------------------------------------------------------

    def __repr__(self) -> str:
        return (
            f"TimeModel(epoch={self.abs_time_epoch:.3f}, "
            f"moment_id={self.moment_id}, "
            f"offset={self.offset_in_clip:.3f}s)"
        )
