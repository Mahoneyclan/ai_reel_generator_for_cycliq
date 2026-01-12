# source/io_paths.py
"""
Centralized path helpers for ride-scoped artifacts.
Layout:
    {Ride}/
        {Ride}.mp4
        logs/
        working/   (CSVs + JSON only)
        clips/
        frames/
        splash_assets/
        minimaps/
        gauges/
        elevation/
"""

from pathlib import Path
from .config import DEFAULT_CONFIG as CFG

def _mk(path: Path) -> Path:
    """Ensure the path exists (directory or parent for file)."""
    if path.suffix:
        path.parent.mkdir(parents=True, exist_ok=True)
    else:
        path.mkdir(parents=True, exist_ok=True)
    return path


# --- Working CSVs / JSON / GPX (in project folder) ---
def gpx_path() -> Path: return CFG.GPX_FILE
def flatten_path() -> Path: return CFG.WORKING_DIR / "flatten.csv"
def extract_path() -> Path: return CFG.WORKING_DIR / "extract.csv"
def enrich_path() -> Path: return CFG.WORKING_DIR / "enriched.csv"
def select_path() -> Path: return CFG.WORKING_DIR / "select.csv"
def segments_path() -> Path: return CFG.WORKING_DIR / "segments.json"

# --- Clips / frames / splash assets (in project folder) ---
def clips_dir() -> Path: return CFG.CLIPS_DIR
def frames_dir() -> Path: return CFG.FRAMES_DIR
def splash_assets_dir() -> Path: return CFG.SPLASH_ASSETS_DIR

# --- Overlays (in project folder) ---
def minimap_dir() -> Path: return CFG.MINIMAP_DIR
def gauge_dir() -> Path: return CFG.GAUGE_DIR
def elevation_dir() -> Path: return CFG.ELEVATION_DIR

# --- Logs (in project folder) ---
def logs_dir() -> Path: return CFG.LOG_DIR