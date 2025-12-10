"""
Unified GPX import controller:
- Ensures GPX files are saved to CFG.INPUT_DIR
- Provides consistent naming, logging, and error handling
- Abstracts provider-specific download calls via 'downloader' callable
"""

from __future__ import annotations
from pathlib import Path
from typing import Callable, Optional

# Use your central config for input/log directories if available.
try:
    from source.config import CFG
    INPUT_DIR = Path(CFG.INPUT_DIR)
except Exception:
    INPUT_DIR = Path.home() / "Downloads"

INPUT_DIR.mkdir(parents=True, exist_ok=True)


class ImportController:
    def __init__(self, log_callback: Optional[Callable[[str, str], None]] = None):
        self._log_cb = log_callback or (lambda msg, level="info": None)

    def _log(self, msg: str, level: str = "info") -> None:
        self._log_cb(msg, level)

    def default_output_path(self, provider: str, activity_id: object) -> Path:
        """
        Always return the fixed filename 'ride.gpx' in the input directory.
        """
        return INPUT_DIR / "ride.gpx"

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
