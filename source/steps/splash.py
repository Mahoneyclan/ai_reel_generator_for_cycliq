# source/steps/splash.py
"""
Splash step orchestrator: produces _intro.mp4 and _outro.mp4.
Delegates to specialized builders for sequence generation.

REFACTORED: Now ~100 lines, down from 563 lines.
"""

from __future__ import annotations
import csv
from pathlib import Path
from typing import Tuple, List

from ..config import DEFAULT_CONFIG as CFG
from ..io_paths import select_path, frames_dir, splash_assets_dir, _mk
from ..utils.log import setup_logger
from .splash_builders import (
    CollageBuilder,
    IntroBuilder,
    OutroBuilder
)

log = setup_logger("steps.splash")

# Canvas constants
OUT_W, OUT_H = 2560, 1440
BANNER_HEIGHT = 220

# Track temp files for cleanup
_temp_files: List[Path] = []


def _collect_frame_images() -> List[Path]:
    """
    Collect frame images for recommended clips.
    Returns list of frame paths (Primary + Partner) sorted chronologically.
    """
    select_csv = select_path()
    if not select_csv.exists():
        log.warning("[splash] select.csv not found, falling back to all frames")
        return sorted(frames_dir().glob("*.jpg"))
    
    try:
        with select_csv.open() as f:
            rows = list(csv.DictReader(f))
    except Exception as e:
        log.error(f"[splash] Failed to read select.csv: {e}")
        return []
    
    # Filter recommended clips
    recommended = [r for r in rows if r.get("recommended") == "true"]
    if not recommended:
        log.warning("[splash] No recommended clips in select.csv")
        return []
    
    # Collect Primary + Partner frames
    frame_pairs = []
    partner_count = 0
    
    for row in recommended:
        idx = row["index"]
        epoch = float(row.get("abs_time_epoch", 0) or 0.0)
        
        # Primary frame
        primary = frames_dir() / f"{idx}_Primary.jpg"
        if primary.exists():
            frame_pairs.append((epoch, primary))
        else:
            log.warning(f"[splash] Primary frame missing: {primary}")
        
        # Partner frame
        partner = frames_dir() / f"{idx}_Partner.jpg"
        if partner.exists():
            frame_pairs.append((epoch, partner))
            partner_count += 1
    
    # Sort chronologically
    frame_pairs.sort(key=lambda x: x[0])
    frames = [path for _, path in frame_pairs]
    
    log.info(
        f"[splash] Collected {len(frames)} frames "
        f"({len(frames) - partner_count} primary + {partner_count} partner)"
    )
    return frames


def run() -> Tuple[Path, Path]:
    """
    Generate both _intro.mp4 and _outro.mp4 in PROJECT_DIR.
    
    Returns:
        Tuple of (intro_path, outro_path)
    """
    global _temp_files
    _temp_files = []
    
    # Collect frame images
    frames = _collect_frame_images()
    if not frames:
        log.error("[splash] No frames available for splash generation")
        return CFG.PROJECT_DIR / "_intro.mp4", CFG.PROJECT_DIR / "_outro.mp4"
    
    # Calculate grid layout
    builder = CollageBuilder(OUT_W, OUT_H - BANNER_HEIGHT)
    grid_info = builder.calculate_grid(len(frames))
    
    # Setup
    assets_dir = _mk(splash_assets_dir())
    intro_path = CFG.PROJECT_DIR / "_intro.mp4"
    outro_path = CFG.PROJECT_DIR / "_outro.mp4"
    
    # Build sequences
    try:
        # Outro first (simpler, validates frame collection)
        outro_builder = OutroBuilder(assets_dir, _temp_files)
        outro_builder.build_outro(frames, outro_path)
        
        # Intro (complex with animation)
        intro_builder = IntroBuilder(assets_dir, _temp_files)
        intro_builder.build_intro(frames, grid_info, intro_path)
        
    finally:
        # Cleanup temp files
        _cleanup_temp_files()
    
    return intro_path, outro_path


def _cleanup_temp_files():
    """Remove temporary files and directories."""
    for temp_item in _temp_files:
        if not temp_item.exists():
            continue
        
        try:
            if temp_item.is_dir():
                import shutil
                shutil.rmtree(temp_item)
                log.debug(f"[splash] Cleaned up directory: {temp_item.name}")
            else:
                temp_item.unlink()
                log.debug(f"[splash] Cleaned up file: {temp_item.name}")
        except Exception as e:
            log.warning(f"[splash] Could not delete {temp_item.name}: {e}")


if __name__ == "__main__":
    run()