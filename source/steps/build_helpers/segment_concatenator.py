# source/steps/build_helpers/cleanup.py
"""
Cleanup utilities for temporary build files.
"""

from pathlib import Path
from ...utils.log import setup_logger

log = setup_logger("steps.build_helpers.cleanup")

# Track temporary files created during build
_temp_files: list[Path] = []


def register_temp_file(path: Path):
    """Register a file for cleanup."""
    _temp_files.append(path)


def cleanup_temp_files():
    """Remove all registered temporary files."""
    if not _temp_files:
        return
    
    removed = 0
    for temp_file in _temp_files:
        try:
            if temp_file.exists():
                temp_file.unlink()
                removed += 1
        except Exception as e:
            log.debug(f"[cleanup] Could not remove {temp_file.name}: {e}")
    
    if removed > 0:
        log.debug(f"[cleanup] Removed {removed} temporary files")
    
    _temp_files.clear()