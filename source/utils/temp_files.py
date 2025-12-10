# source/utils/temp_files.py
"""
Centralized temporary file tracking and cleanup.

Single source of truth for all temporary files created during pipeline execution.
Thread-safe implementation with automatic deduplication.
"""

from pathlib import Path
from typing import Set, List
import threading
from ..utils.log import setup_logger

log = setup_logger("utils.temp_files")

# Thread-safe temporary file registry
_temp_files_lock = threading.Lock()
_temp_files: Set[Path] = set()


def register_temp_file(path: Path) -> None:
    """
    Register a temporary file or directory for cleanup.
    
    Thread-safe with automatic deduplication.
    
    Args:
        path: Path to temporary file or directory
    """
    if not isinstance(path, Path):
        path = Path(path)
    
    with _temp_files_lock:
        _temp_files.add(path.resolve())
        log.debug(f"Registered temp: {path.name}")


def register_temp_files(paths: List[Path]) -> None:
    """
    Register multiple temporary files at once.
    
    Args:
        paths: List of paths to register
    """
    if not paths:
        return
    
    with _temp_files_lock:
        for path in paths:
            if not isinstance(path, Path):
                path = Path(path)
            _temp_files.add(path.resolve())
        
        log.debug(f"Registered {len(paths)} temp files")


def unregister_temp_file(path: Path) -> None:
    """
    Remove a file from the temp registry without deleting it.
    
    Use this if you want to keep a "temp" file.
    
    Args:
        path: Path to unregister
    """
    if not isinstance(path, Path):
        path = Path(path)
    
    with _temp_files_lock:
        _temp_files.discard(path.resolve())


def cleanup_temp_files(force: bool = False) -> int:
    """
    Delete all registered temporary files and directories.
    
    Args:
        force: If True, ignore errors and continue cleanup
    
    Returns:
        Number of items successfully removed
    """
    removed_count = 0
    failed_items = []
    
    with _temp_files_lock:
        items_to_remove = list(_temp_files)
        _temp_files.clear()
    
    for temp_item in items_to_remove:
        try:
            if not temp_item.exists():
                continue
            
            if temp_item.is_dir():
                import shutil
                shutil.rmtree(temp_item)
                log.debug(f"Removed temp directory: {temp_item.name}")
            else:
                temp_item.unlink()
                log.debug(f"Removed temp file: {temp_item.name}")
            
            removed_count += 1
            
        except Exception as e:
            error_msg = f"Failed to remove {temp_item.name}: {e}"
            
            if force:
                log.warning(error_msg)
                failed_items.append(str(temp_item))
            else:
                log.error(error_msg)
                # Re-register failed items for retry
                with _temp_files_lock:
                    _temp_files.add(temp_item)
                raise
    
    if removed_count > 0:
        log.info(f"Cleaned up {removed_count} temporary items")
    
    if failed_items:
        log.warning(f"Failed to remove {len(failed_items)} items: {', '.join(failed_items)}")
    
    return removed_count


def get_temp_file_count() -> int:
    """
    Get count of registered temporary files.
    
    Returns:
        Number of files/directories registered for cleanup
    """
    with _temp_files_lock:
        return len(_temp_files)


def list_temp_files() -> List[Path]:
    """
    Get list of all registered temporary files.
    
    Returns:
        Copy of temp file registry
    """
    with _temp_files_lock:
        return list(_temp_files)


def clear_temp_registry() -> None:
    """
    Clear the temp file registry WITHOUT deleting files.
    
    Use this if you want to abandon tracking without cleanup.
    Rarely needed - prefer cleanup_temp_files() instead.
    """
    with _temp_files_lock:
        count = len(_temp_files)
        _temp_files.clear()
    
    if count > 0:
        log.warning(f"Cleared {count} temp files from registry without deletion")


class TempFileContext:
    """
    Context manager for automatic temp file cleanup.
    
    Usage:
        with TempFileContext() as tmp:
            tmp.add(some_temp_file)
            # ... do work ...
        # Files automatically cleaned up on exit
    """
    
    def __init__(self):
        self.local_files: Set[Path] = set()
    
    def add(self, path: Path) -> None:
        """Register a file in this context."""
        if not isinstance(path, Path):
            path = Path(path)
        self.local_files.add(path.resolve())
        register_temp_file(path)
    
    def __enter__(self):
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        # Clean up files registered in this context
        removed = 0
        for path in self.local_files:
            try:
                if path.exists():
                    if path.is_dir():
                        import shutil
                        shutil.rmtree(path)
                    else:
                        path.unlink()
                    removed += 1
            except Exception as e:
                log.warning(f"Context cleanup failed for {path.name}: {e}")
        
        if removed > 0:
            log.debug(f"Context cleaned up {removed} temp files")
        
        # Don't suppress exceptions
        return False