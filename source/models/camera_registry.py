# source/models/camera_registry.py
"""
CameraRegistry: Centralized camera name validation and property lookup.

Consolidates scattered camera-related logic:
- Camera name validation and normalization
- Alias handling (Fly12S → Fly12Sport)
- KNOWN_OFFSETS lookup (creation_time bias per camera)
- CAMERA_WEIGHTS lookup (scoring weights)
- CAMERA_TIME_OFFSETS lookup (alignment offsets)

Usage:
    from source.models import CameraRegistry

    registry = CameraRegistry()

    # Validate and normalize camera name
    camera = registry.normalize("Fly12S")  # Returns "Fly12Sport"

    # Get camera properties
    offset = registry.get_known_offset("Fly12Sport")  # Returns 2.0
    weight = registry.get_weight("Fly6Pro")  # Returns 1.0
"""

from __future__ import annotations
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, Optional, Set

from ..utils.log import setup_logger

log = setup_logger("models.camera_registry")


class CameraType(Enum):
    """Known Cycliq camera types."""
    FLY12_SPORT = "Fly12Sport"
    FLY6_PRO = "Fly6Pro"

    @classmethod
    def values(cls) -> Set[str]:
        """Return set of all camera name strings."""
        return {c.value for c in cls}


# Alias mappings for camera names (e.g., SD card labels → canonical names)
_CAMERA_ALIASES: Dict[str, str] = {
    "Fly12S": "Fly12Sport",
    "FLY12SPORT": "Fly12Sport",
    "fly12sport": "Fly12Sport",
    "FLY6PRO": "Fly6Pro",
    "fly6pro": "Fly6Pro",
    "Fly6": "Fly6Pro",
}


@dataclass
class CameraRegistry:
    """
    Centralized registry for camera names and properties.

    Provides validation, normalization, and property lookups for known cameras.
    Falls back to config values for properties not explicitly set.
    """

    # Known creation_time offsets per camera (seconds)
    # Cycliq cameras record creation_time at different points relative to recording end
    known_offsets: Dict[str, float] = field(default_factory=dict)

    # Scoring weights per camera
    camera_weights: Dict[str, float] = field(default_factory=dict)

    # Camera-to-camera alignment offsets (computed by align.py)
    time_offsets: Dict[str, float] = field(default_factory=dict)

    def __post_init__(self):
        """Initialize with config defaults if not provided."""
        # Lazy import to avoid circular dependency
        from ..config import DEFAULT_CONFIG as CFG

        if not self.known_offsets:
            self.known_offsets = dict(CFG.KNOWN_OFFSETS)

        if not self.camera_weights:
            self.camera_weights = dict(CFG.CAMERA_WEIGHTS)

        if not self.time_offsets:
            self.time_offsets = dict(CFG.CAMERA_TIME_OFFSETS)

    # -------------------------------------------------------------------------
    # Validation & Normalization
    # -------------------------------------------------------------------------

    def is_valid(self, camera_name: str) -> bool:
        """
        Check if camera name is valid (known or alias).

        Args:
            camera_name: Camera name to validate

        Returns:
            True if camera is recognized
        """
        normalized = self.normalize(camera_name)
        return normalized in CameraType.values()

    def normalize(self, camera_name: str) -> str:
        """
        Normalize camera name to canonical form.

        Handles aliases like "Fly12S" → "Fly12Sport".
        Returns original if not an alias and already valid.

        Args:
            camera_name: Camera name or alias

        Returns:
            Canonical camera name
        """
        if not camera_name:
            return camera_name

        # Check alias mapping first
        if camera_name in _CAMERA_ALIASES:
            return _CAMERA_ALIASES[camera_name]

        # Already canonical?
        if camera_name in CameraType.values():
            return camera_name

        # Try case-insensitive match
        lower = camera_name.lower()
        for alias, canonical in _CAMERA_ALIASES.items():
            if alias.lower() == lower:
                return canonical

        # Unknown camera - return as-is
        log.debug(f"[CameraRegistry] Unknown camera name: {camera_name}")
        return camera_name

    def get_all_cameras(self) -> Set[str]:
        """Return set of all known canonical camera names."""
        return CameraType.values()

    # -------------------------------------------------------------------------
    # Property Lookups
    # -------------------------------------------------------------------------

    def get_known_offset(self, camera_name: str, default: float = 0.0) -> float:
        """
        Get creation_time offset for a camera.

        This offset accounts for camera-specific bias in creation_time metadata.
        E.g., Fly12Sport records creation_time as end + 2 seconds.

        Args:
            camera_name: Camera name (will be normalized)
            default: Default value if camera not found

        Returns:
            Offset in seconds
        """
        normalized = self.normalize(camera_name)
        return self.known_offsets.get(normalized, default)

    def get_weight(self, camera_name: str, default: float = 1.0) -> float:
        """
        Get scoring weight for a camera.

        Used in score_calculator.py to weight camera contributions.

        Args:
            camera_name: Camera name (will be normalized)
            default: Default weight if camera not found

        Returns:
            Weight multiplier (typically 1.0)
        """
        normalized = self.normalize(camera_name)
        return self.camera_weights.get(normalized, default)

    def get_time_offset(self, camera_name: str, default: float = 0.0) -> float:
        """
        Get camera-to-camera alignment offset.

        Computed by align.py based on actual recording start times.

        Args:
            camera_name: Camera name (will be normalized)
            default: Default offset if camera not found

        Returns:
            Offset in seconds relative to baseline camera
        """
        normalized = self.normalize(camera_name)
        return self.time_offsets.get(normalized, default)

    def set_time_offset(self, camera_name: str, offset: float) -> None:
        """
        Set camera-to-camera alignment offset.

        Called by align.py after computing offsets from video metadata.

        Args:
            camera_name: Camera name (will be normalized)
            offset: Offset in seconds
        """
        normalized = self.normalize(camera_name)
        self.time_offsets[normalized] = offset

    # -------------------------------------------------------------------------
    # Camera Identification
    # -------------------------------------------------------------------------

    def is_front_camera(self, camera_name: str) -> bool:
        """Check if camera is front-facing (Fly12Sport)."""
        return self.normalize(camera_name) == CameraType.FLY12_SPORT.value

    def is_rear_camera(self, camera_name: str) -> bool:
        """Check if camera is rear-facing (Fly6Pro)."""
        return self.normalize(camera_name) == CameraType.FLY6_PRO.value

    def get_display_name(self, camera_name: str) -> str:
        """
        Get human-readable display name for camera.

        Args:
            camera_name: Camera name

        Returns:
            Display name (e.g., "Front" or "Rear")
        """
        normalized = self.normalize(camera_name)
        if normalized == CameraType.FLY12_SPORT.value:
            return "Front"
        elif normalized == CameraType.FLY6_PRO.value:
            return "Rear"
        return normalized

    # -------------------------------------------------------------------------
    # String Representation
    # -------------------------------------------------------------------------

    def __repr__(self) -> str:
        return (
            f"CameraRegistry(cameras={list(CameraType.values())}, "
            f"offsets={self.known_offsets})"
        )


# Module-level singleton for convenience
_default_registry: Optional[CameraRegistry] = None


def get_registry() -> CameraRegistry:
    """Get the default CameraRegistry singleton."""
    global _default_registry
    if _default_registry is None:
        _default_registry = CameraRegistry()
    return _default_registry
