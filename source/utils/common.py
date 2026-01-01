# source/utils/common.py
"""
Common utility functions used across the codebase.
Consolidates duplicated helper functions for consistency.
"""

from __future__ import annotations
import csv
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from .log import setup_logger

log = setup_logger("utils.common")


# =============================================================================
# Safe Type Conversions
# =============================================================================

def safe_float(value: Any, default: float = 0.0) -> float:
    """
    Safely convert a value to float with a default fallback.

    Handles None, empty strings, and invalid values gracefully.

    Args:
        value: Value to convert (string, number, None, etc.)
        default: Default value if conversion fails

    Returns:
        Float value or default

    Examples:
        >>> safe_float("3.14")
        3.14
        >>> safe_float("", 0.0)
        0.0
        >>> safe_float(None, -1.0)
        -1.0
        >>> safe_float("invalid", 0.0)
        0.0
    """
    if value in ("", None):
        return default
    try:
        return float(value)
    except (ValueError, TypeError):
        return default


def safe_int(value: Any, default: int = 0) -> int:
    """
    Safely convert a value to int with a default fallback.

    Args:
        value: Value to convert
        default: Default value if conversion fails

    Returns:
        Int value or default
    """
    if value in ("", None):
        return default
    try:
        return int(value)
    except (ValueError, TypeError):
        return default


# =============================================================================
# ISO Time Parsing
# =============================================================================

def parse_iso_time(time_str: str) -> Optional[datetime]:
    """
    Parse an ISO format time string, handling various Z suffix formats.

    Cycliq cameras and other sources use inconsistent formats:
    - "2025-12-28T05:04:51.000000Z" (Z suffix)
    - "2025-12-28T05:04:51+00:00" (explicit UTC offset)
    - "2025-12-28T05:04:51" (no timezone)

    Args:
        time_str: ISO format datetime string

    Returns:
        datetime object in UTC, or None if parsing fails

    Examples:
        >>> parse_iso_time("2025-12-28T05:04:51Z")
        datetime(2025, 12, 28, 5, 4, 51, tzinfo=timezone.utc)
    """
    if not time_str:
        return None

    try:
        # Handle Z suffix (replace with +00:00 for fromisoformat)
        if time_str.endswith("Z"):
            time_str = time_str[:-1] + "+00:00"

        dt = datetime.fromisoformat(time_str)

        # If no timezone info, assume UTC
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)

        return dt.astimezone(timezone.utc)

    except (ValueError, TypeError) as e:
        log.debug(f"[common] Could not parse ISO time '{time_str}': {e}")
        return None


# =============================================================================
# CSV Utilities
# =============================================================================

def read_csv(path: Path) -> List[Dict[str, str]]:
    """
    Read a CSV file and return a list of dictionaries.

    Args:
        path: Path to CSV file

    Returns:
        List of row dictionaries, empty list if file doesn't exist or is empty

    Example:
        >>> rows = read_csv(Path("data.csv"))
        >>> for row in rows:
        ...     print(row["column_name"])
    """
    if not path.exists():
        log.debug(f"[common] CSV file not found: {path}")
        return []

    try:
        with path.open(encoding="utf-8") as f:
            return list(csv.DictReader(f))
    except Exception as e:
        log.warning(f"[common] Failed to read CSV {path}: {e}")
        return []


def write_csv(path: Path, rows: List[Dict[str, str]], fieldnames: Optional[List[str]] = None) -> bool:
    """
    Write a list of dictionaries to a CSV file.

    Args:
        path: Output path for CSV file
        rows: List of row dictionaries to write
        fieldnames: Optional explicit field order. If None, uses keys from first row.

    Returns:
        True if successful, False otherwise

    Example:
        >>> rows = [{"name": "Alice", "age": "30"}, {"name": "Bob", "age": "25"}]
        >>> write_csv(Path("output.csv"), rows)
        True
    """
    if not rows:
        log.debug(f"[common] No rows to write to {path}")
        return False

    try:
        # Ensure parent directory exists
        path.parent.mkdir(parents=True, exist_ok=True)

        # Determine fieldnames
        if fieldnames is None:
            fieldnames = list(rows[0].keys())

        with path.open("w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)

        return True

    except Exception as e:
        log.error(f"[common] Failed to write CSV {path}: {e}")
        return False
