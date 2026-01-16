# source/steps/enrich_helpers/__init__.py
"""
Frame enrichment components for the enrich pipeline step.

This package contains focused modules for different analysis tasks:
- object_detector: YOLO-based bicycle detection
- scene_detector: Temporal scene change detection
- gps_enricher: GPX telemetry matching
- segment_matcher: Strava segment effort matching for PR boost
- score_calculator: Composite score computation
"""

from .object_detector import ObjectDetector, cleanup_model
from .scene_detector import SceneDetector
from .gps_enricher import GPSEnricher
from .segment_matcher import SegmentMatcher
from .score_calculator import ScoreCalculator

__all__ = [
    "ObjectDetector",
    "SceneDetector",
    "GPSEnricher",
    "SegmentMatcher",
    "ScoreCalculator",
    "cleanup_model",
]
