# source/steps/__init__.py

"""Steps package - pipeline stages."""

from . import flatten, extract, enrich, select, build, splash, concat

from enum import Enum

class PipelineStep(Enum):
    """Enumeration of all pipeline steps in execution order."""
    FLATTEN   = "flatten"
    EXTRACT   = "extract"
    ENRICH    = "enrich"
    SELECT    = "select"
    BUILD     = "build"
    SPLASH    = "splash"
    CONCAT    = "concat"

__all__ = [
    "flatten",
    "extract",
    "enrich",
    "select",
    "build",
    "splash",
    "concat",
]