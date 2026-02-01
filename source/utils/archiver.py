# source/utils/archiver.py
"""
Project archiver utility.

Moves projects between storage locations:
- AData (high-speed SSD, 1TB) - working environment
- GDrive (slower HDD, 4TB) - archive storage

Handles both project folder and linked raw source files.
"""

from __future__ import annotations
import shutil
from pathlib import Path
from typing import Callable, Optional, Tuple

from ..utils.log import setup_logger

log = setup_logger("utils.archiver")

# Storage locations
STORAGE_LOCATIONS = {
    "AData": {
        "projects": Path("/Volumes/AData/Fly_Projects"),
        "raw": Path("/Volumes/AData/Fly_Raw"),
        "description": "High-speed SSD (1TB) - Working",
    },
    "GDrive": {
        "projects": Path("/Volumes/GDrive/Fly_Projects"),
        "raw": Path("/Volumes/GDrive/Fly_Raw"),
        "description": "Archive HDD (4TB) - Storage",
    },
}


def get_available_locations() -> list[str]:
    """Return list of available (mounted) storage locations."""
    available = []
    for name, paths in STORAGE_LOCATIONS.items():
        if paths["projects"].parent.exists():
            available.append(name)
    return available


def get_project_location(project_path: Path) -> Optional[str]:
    """Determine which storage location a project is in."""
    for name, paths in STORAGE_LOCATIONS.items():
        if str(project_path).startswith(str(paths["projects"])):
            return name
    return None


def get_raw_source_path(project_path: Path) -> Optional[Path]:
    """Get the raw source path for a project (following symlink)."""
    symlink_path = project_path / "source_videos"
    if symlink_path.exists() and symlink_path.is_symlink():
        return symlink_path.resolve()

    # Try source_path.txt
    source_meta = project_path / "source_path.txt"
    if source_meta.exists():
        return Path(source_meta.read_text().strip())

    return None


def calculate_archive_size(project_path: Path) -> Tuple[int, int]:
    """
    Calculate total size to archive.

    Returns:
        Tuple of (project_size_bytes, raw_size_bytes)
    """
    project_size = 0
    raw_size = 0

    # Project folder size
    if project_path.exists():
        for f in project_path.rglob("*"):
            if f.is_file() and not f.is_symlink():
                project_size += f.stat().st_size

    # Raw source size
    raw_path = get_raw_source_path(project_path)
    if raw_path and raw_path.exists():
        for f in raw_path.rglob("*"):
            if f.is_file():
                raw_size += f.stat().st_size

    return project_size, raw_size


def archive_project(
    project_path: Path,
    destination: str,
    progress_callback: Optional[Callable[[str, int], None]] = None,
    include_raw: bool = True,
) -> Tuple[bool, str]:
    """
    Archive a project to the specified destination.

    Args:
        project_path: Path to project folder
        destination: Destination storage name (e.g., "GDrive")
        progress_callback: Optional callback(message, percent)
        include_raw: Whether to also move raw source files

    Returns:
        Tuple of (success, message)
    """
    if destination not in STORAGE_LOCATIONS:
        return False, f"Unknown destination: {destination}"

    dest_paths = STORAGE_LOCATIONS[destination]

    # Check destination is available
    if not dest_paths["projects"].parent.exists():
        return False, f"Destination not mounted: {destination}"

    # Ensure destination directories exist
    dest_paths["projects"].mkdir(parents=True, exist_ok=True)
    if include_raw:
        dest_paths["raw"].mkdir(parents=True, exist_ok=True)

    project_name = project_path.name
    dest_project_path = dest_paths["projects"] / project_name

    # Check if already exists at destination
    if dest_project_path.exists():
        return False, f"Project already exists at destination: {dest_project_path}"

    try:
        # Get raw source info before moving project
        raw_source_path = get_raw_source_path(project_path) if include_raw else None
        raw_name = raw_source_path.name if raw_source_path else None
        dest_raw_path = dest_paths["raw"] / raw_name if raw_name else None

        # Check raw destination
        if dest_raw_path and dest_raw_path.exists():
            return False, f"Raw folder already exists at destination: {dest_raw_path}"

        # Calculate sizes for progress
        project_size, raw_size = calculate_archive_size(project_path)
        total_size = project_size + (raw_size if include_raw else 0)

        if progress_callback:
            progress_callback("Starting archive...", 0)

        # Move raw files first (if included)
        if include_raw and raw_source_path and raw_source_path.exists():
            if progress_callback:
                progress_callback(f"Moving raw files: {raw_name}...", 10)

            log.info(f"Moving raw: {raw_source_path} -> {dest_raw_path}")
            shutil.move(str(raw_source_path), str(dest_raw_path))

            if progress_callback:
                progress_callback("Raw files moved", 50)

        # Update symlink in project to point to new raw location
        symlink_path = project_path / "source_videos"
        if symlink_path.is_symlink() and dest_raw_path:
            symlink_path.unlink()
            symlink_path.symlink_to(dest_raw_path)
            log.info(f"Updated symlink to: {dest_raw_path}")

        # Update source_path.txt
        source_meta = project_path / "source_path.txt"
        if source_meta.exists() and dest_raw_path:
            source_meta.write_text(str(dest_raw_path))
            log.info(f"Updated source_path.txt")

        # Move project folder
        if progress_callback:
            progress_callback(f"Moving project: {project_name}...", 60)

        log.info(f"Moving project: {project_path} -> {dest_project_path}")
        shutil.move(str(project_path), str(dest_project_path))

        if progress_callback:
            progress_callback("Archive complete!", 100)

        log.info(f"Archive complete: {project_name} -> {destination}")
        return True, f"Archived to {destination}: {dest_project_path}"

    except Exception as e:
        log.error(f"Archive failed: {e}")
        return False, f"Archive failed: {str(e)}"


def restore_project(
    project_name: str,
    source: str,
    progress_callback: Optional[Callable[[str, int], None]] = None,
    include_raw: bool = True,
) -> Tuple[bool, str]:
    """
    Restore a project from archive back to working storage.

    This is the reverse of archive_project - moves from GDrive to AData.
    """
    # Determine destination (opposite of source)
    if source == "GDrive":
        destination = "AData"
    elif source == "AData":
        destination = "GDrive"
    else:
        return False, f"Unknown source: {source}"

    source_paths = STORAGE_LOCATIONS[source]
    project_path = source_paths["projects"] / project_name

    if not project_path.exists():
        return False, f"Project not found: {project_path}"

    return archive_project(project_path, destination, progress_callback, include_raw)
