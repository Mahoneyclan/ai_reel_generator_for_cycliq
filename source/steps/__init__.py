# source/steps/__init__.py

"""Steps package - pipeline stages.

UPDATED: Replaced detect + enrich with combined analyze step.
"""
from . import preflight, flatten, align, extract, analyze, select, build, splash, concat

from enum import Enum

class PipelineStep(Enum):
    """Enumeration of all pipeline steps in execution order."""
    PREFLIGHT = "preflight"
    FLATTEN   = "flatten"
    ALIGN     = "align"
    EXTRACT   = "extract"
    ANALYZE   = "analyze"  # UPDATED: Replaces DETECT and ENRICH
    SELECT    = "select"
    BUILD     = "build"
    SPLASH    = "splash"
    CONCAT    = "concat"

__all__ = [
    "preflight",
    "flatten",
    "align",
    "extract",
    "analyze",
    "select",
    "build",
    "splash",
    "concat",
]