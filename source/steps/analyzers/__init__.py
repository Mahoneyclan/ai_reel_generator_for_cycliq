# source/steps/analyzers/__init__.py
"""
Frame analysis components for the analyze pipeline step.

This package contains focused modules for different analysis tasks:
- bike_detector: YOLO-based bicycle detection
- scene_detector: Temporal scene change detection
- gps_enricher: GPX telemetry matching
- partner_matcher: Dual-camera frame pairing
- score_calculator: Composite score computation
"""

from .bike_detector import BikeDetector, cleanup_model
from .scene_detector import SceneDetector
from .gps_enricher import GPSEnricher
from .partner_matcher import PartnerMatcher
from .score_calculator import ScoreCalculator

__all__ = [
    "BikeDetector",
    "SceneDetector",
    "GPSEnricher",
    "PartnerMatcher",
    "ScoreCalculator",
    "cleanup_model",
]