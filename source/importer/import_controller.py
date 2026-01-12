"""
Unified GPX import controller:
- Ensures GPX files are saved to CFG.GPX_FILE (project working directory)
- Provides consistent naming, logging, and error handling
- Abstracts provider-specific download calls via 'downloader' callable
"""

from __future__ import annotations
from pathlib import Path
from typing import Callable, Optional

# Use central config for GPX file location
try:
    from source.config import DEFAULT_CONFIG as CFG
except ImportError:
    CFG = None


class ImportController:
    def __init__(self, log_callback: Optional[Callable[[str, str], None]] = None):
        self._log_cb = log_callback or (lambda msg, level="info": None)

    def _log(self, msg: str, level: str = "info") -> None:
        self._log_cb(msg, level)

    def default_output_path(self, provider: str, activity_id: object) -> Path:
        """
        Return the project-scoped GPX path (working directory).
        Falls back to ~/Downloads if config unavailable.
        """
        if CFG is not None and CFG.RIDE_FOLDER:
            gpx_path = CFG.GPX_FILE
            gpx_path.parent.mkdir(parents=True, exist_ok=True)
            return gpx_path
        # Fallback for when no project is selected
        fallback = Path.home() / "Downloads" / "ride.gpx"
        fallback.parent.mkdir(parents=True, exist_ok=True)
        return fallback

    def download_gpx(
        self,
        provider: str,
        activity_id: object,
        downloader: Callable[[Path], bool]
    ) -> Optional[str]:
        """
        Orchestrate GPX download and placement.

        Args:
            provider: 'garmin' or 'strava'
            activity_id: provider-specific activity identifier
            downloader: callable that accepts Path and returns bool success

        Returns:
            Saved path as str if success, else None.
        """
        out_path = self.default_output_path(provider, activity_id)

        self._log(f"Starting GPX download: provider={provider} id={activity_id} -> {out_path}")
        try:
            ok = downloader(out_path)
            if not ok:
                self._log("Download failed", level="error")
                return None

            if not out_path.exists() or out_path.stat().st_size == 0:
                self._log("Downloaded file missing or empty", level="error")
                return None

            self._log(f"GPX saved successfully: {out_path}")
            return str(out_path)
        except Exception as e:
            self._log(f"Exception during download: {e}", level="error")
            return None
