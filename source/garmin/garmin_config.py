# source/garmin/garmin_config.py
"""
FIXED: Garmin Connect configuration and credentials management.
Simplified to work with garminconnect library's internal session handling.
"""

from __future__ import annotations
import json
from pathlib import Path
from typing import Optional

from ..utils.log import setup_logger
from .garmin_credentials import get_credentials

log = setup_logger("garmin.config")

email, _ = get_credentials()
log.info(f"[garmin_config] Active Garmin account: {email}")

class GarminConfig:
    """Manages Garmin Connect credentials and minimal session tracking."""

    def __init__(self):
        self.config_dir = Path.home() / ".velo_films"
        self.session_file = self.config_dir / "garmin_session.json"
        self._ensure_config_dir()

    def _ensure_config_dir(self):
        self.config_dir.mkdir(parents=True, exist_ok=True)
        log.debug(f"[garmin_config] Session storage: {self.session_file}")

    def save_session(self, email: str, session_data: dict):
        """
        Save minimal session info to disk.
        Note: garminconnect library manages its own session internally.
        We just track the last successful login.
        """
        try:
            data = {
                "email": email,
                "session_data": session_data,
                "last_login": str(Path(__file__).stat().st_mtime)  # timestamp
            }
            with self.session_file.open("w") as f:
                json.dump(data, f, indent=2)
            self.session_file.chmod(0o600)
            log.info(f"[garmin_config] Saved session marker for {email}")
        except Exception as e:
            log.error(f"[garmin_config] Failed to save session: {e}")

    def load_session(self) -> Optional[tuple[str, dict]]:
        """
        Load session info from disk.
        Returns (email, session_data) or None.
        """
        if not self.session_file.exists():
            log.debug("[garmin_config] No saved session found")
            return None
        
        try:
            with self.session_file.open() as f:
                data = json.load(f)
            
            email = data.get("email")
            session_data = data.get("session_data", {})
            
            if not email:
                log.warning("[garmin_config] Invalid session file")
                return None
            
            log.debug(f"[garmin_config] Loaded session for {email}")
            return email, session_data
            
        except Exception as e:
            log.error(f"[garmin_config] Failed to load session: {e}")
            return None

    def clear_session(self):
        """Delete saved session (logout)."""
        if self.session_file.exists():
            try:
                self.session_file.unlink()
                log.info("[garmin_config] Cleared saved session")
            except Exception as e:
                log.error(f"[garmin_config] Failed to clear session: {e}")