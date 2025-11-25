# source/core/models/__init__.py
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from datetime import datetime

@dataclass
class Project:
    name: str
    path: Path
    video_count: int = 0
    gpx_count: int = 0
    last_modified: datetime = datetime.min

__all__ = ["Project"]
