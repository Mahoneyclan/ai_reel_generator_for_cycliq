# source/steps/analyze_helpers/__init__.py
"""
Frame analysis components for the analyze pipeline step.

This package contains focused modules for different analysis tasks:
- object_detector: YOLO-based bicycle detection
- scene_detector: Temporal scene change detection
- gps_enricher: GPX telemetry matching
- score_calculator: Composite score computation
"""

from .object_detector import ObjectDetector, cleanup_model
from .scene_detector import SceneDetector
from .gps_enricher import GPSEnricher
from .score_calculator import ScoreCalculator

__all__ = [
    "ObjectDetector",
    "SceneDetector",
    "GPSEnricher",
    "ScoreCalculator",
    "cleanup_model",
]
