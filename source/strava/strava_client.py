# source/strava/strava_client.py
from __future__ import annotations

"""
Strava API client for fetching activities and GPX exports.
"""

import requests
from pathlib import Path
from datetime import datetime, timezone
from typing import List, Dict, Optional, Callable

from .strava_config import StravaConfig
from .strava_auth import StravaAuth
from ..utils.log import setup_logger

log = setup_logger("strava.client")

class StravaClient:
    """Client for interacting with Strava API v3."""
    
    def __init__(self, log_callback: Optional[Callable[[str, str], None]] = None):
        """
        Initialize Strava client with config and auth.
        
        Args:
            log_callback: Optional callback function(message, level) for logging
        """
        self.config = StravaConfig()
        self.auth = StravaAuth(self.config, log_callback)
        self._access_token: Optional[str] = None
        self.log = log_callback or self._default_log
    
    def _default_log(self, message: str, level: str = "info"):
        """Default logging to console if no callback provided."""
        print(f"[strava] {message}")
    
    def connect(self) -> bool:
        """
        Authenticate with Strava and prepare for API calls.
        
        Returns:
            True if connection successful
        """
        if not self.config.is_configured():
            log.error(
                "[strava_client] Strava app not configured. "
                "Set CLIENT_ID and CLIENT_SECRET in strava_config.py"
            )
            return False
        
        # Run auth flow
        if not self.auth.authenticate():
            return False
        
        # Load access token
        tokens = self.config.load_tokens()
        if not tokens:
            log.error("[strava_client] No valid tokens after authentication")
            return False
        
        self._access_token = tokens["access_token"]
        log.info("[strava_client] ✓ Connected to Strava")
        return True
    
    def get_recent_activities(self, limit: int = 30) -> List[Dict]:
        """
        Fetch recent activities.
        
        Args:
            limit: Maximum number of activities to fetch
            
        Returns:
            List of activity dicts with id, name, start_date, type, distance
        """
        if not self._access_token:
            raise RuntimeError("Not connected. Call connect() first.")
        
        log.info(f"[strava_client] Fetching {limit} recent activities...")
        
        try:
            response = requests.get(
                f"{self.config.API_BASE_URL}/athlete/activities",
                headers={"Authorization": f"Bearer {self._access_token}"},
                params={"per_page": limit, "page": 1}
            )
            
            response.raise_for_status()
            activities = response.json()
            
            log.info(f"[strava_client] Found {len(activities)} activities")
            return activities
            
        except requests.RequestException as e:
            log.error(f"[strava_client] Failed to fetch activities: {e}")
            return []
    
    def get_activity_details(self, activity_id: int) -> Optional[Dict]:
        """
        Fetch detailed activity information.
        
        Args:
            activity_id: Strava activity ID
            
        Returns:
            Activity dict with full details or None
        """
        if not self._access_token:
            raise RuntimeError("Not connected. Call connect() first.")
        
        log.debug(f"[strava_client] Fetching activity {activity_id} details...")
        
        try:
            response = requests.get(
                f"{self.config.API_BASE_URL}/activities/{activity_id}",
                headers={"Authorization": f"Bearer {self._access_token}"}
            )
            
            response.raise_for_status()
            return response.json()
            
        except requests.RequestException as e:
            log.error(f"[strava_client] Failed to fetch activity details: {e}")
            return None
    
    def download_gpx(self, activity_id: int, output_path: Path) -> bool:
        """
        Download activity GPX export.
        
        Args:
            activity_id: Strava activity ID
            output_path: Where to save GPX file
            
        Returns:
            True if successful
        """
        if not self._access_token:
            raise RuntimeError("Not connected. Call connect() first.")
        
        log.info(f"[strava_client] Downloading GPX for activity {activity_id}...")
        
        try:
            # First, get activity details to check for GPS data and privacy settings
            details = self.get_activity_details(activity_id)
            
            # Request GPX export
            response = requests.get(
                f"{self.config.API_BASE_URL}/activities/{activity_id}/export_gpx",
                headers={"Authorization": f"Bearer {self._access_token}"},
                stream=True
            )
            
            # Handle 404 - check why GPS export failed
            if response.status_code == 404:
                # Diagnose the specific reason
                if details:
                    has_latlng = bool(details.get("start_latlng"))
                    map_visibility = details.get("visibility", "unknown")
                    activity_type = details.get("type", "unknown")
                    
                    if not has_latlng:
                        log.warning(
                            f"[strava_client] Activity {activity_id} has no GPS data. "
                            f"Type: {activity_type} (likely virtual ride or manual entry)"
                        )
                    else:
                        log.error(
                            f"[strava_client] Activity {activity_id} has GPS data but export is blocked.\n"
                            f"   Map visibility: {map_visibility}\n"
                            f"   Possible reasons:\n"
                            f"   • Privacy zones are hiding the route\n"
                            f"   • Map visibility is set to 'Only You' or 'Followers Only'\n"
                            f"   • Your app doesn't have permission to access detailed GPS data\n\n"
                            f"   Solutions:\n"
                            f"   1. Go to https://www.strava.com/activities/{activity_id}\n"
                            f"   2. Click the pencil icon to edit\n"
                            f"   3. Change 'Map Visibility' to 'Everyone'\n"
                            f"   4. Temporarily disable privacy zones in Settings > Privacy\n"
                            f"   5. Re-authorize this app at https://www.strava.com/settings/apps"
                        )
                else:
                    log.warning(
                        f"[strava_client] Cannot export GPX for activity {activity_id}. "
                        "Unable to determine the reason - check activity details on Strava."
                    )
                return False
            
            response.raise_for_status()
            
            # Save GPX file
            output_path.parent.mkdir(parents=True, exist_ok=True)
            with output_path.open("wb") as f:
                for chunk in response.iter_content(chunk_size=8192):
                    f.write(chunk)
            
            file_size = output_path.stat().st_size
            log.info(
                f"[strava_client] ✓ Downloaded GPX to {output_path.name} "
                f"({file_size / 1024:.1f} KB)"
            )
            return True
            
        except requests.RequestException as e:
            log.error(f"[strava_client] GPX download failed: {e}")
            return False
    
    def search_activities_by_date(
        self,
        start_date: datetime,
        end_date: Optional[datetime] = None
    ) -> List[Dict]:
        """
        Search for activities within date range.
        
        Args:
            start_date: Start of date range (inclusive)
            end_date: End of date range (inclusive), defaults to start_date
            
        Returns:
            List of matching activities
        """
        if not end_date:
            # Default to same day
            end_date = start_date.replace(hour=23, minute=59, second=59)
        
        # Convert to Unix timestamps
        after = int(start_date.timestamp())
        before = int(end_date.timestamp())
        
        log.info(
            f"[strava_client] Searching activities between "
            f"{start_date.date()} and {end_date.date()}..."
        )
        
        try:
            response = requests.get(
                f"{self.config.API_BASE_URL}/athlete/activities",
                headers={"Authorization": f"Bearer {self._access_token}"},
                params={
                    "after": after,
                    "before": before,
                    "per_page": 50,
                    "page": 1
                }
            )
            
            response.raise_for_status()
            activities = response.json()
            
            # Filter to only cycling activities
            cycling = [a for a in activities if a.get("type") in ["Ride", "VirtualRide"]]
            
            log.info(f"[strava_client] Found {len(cycling)} cycling activities in range")
            return cycling
            
        except requests.RequestException as e:
            log.error(f"[strava_client] Activity search failed: {e}")
            return []
    
    def format_activity_summary(self, activity: Dict) -> str:
        """
        Format activity as readable string for UI display.
        
        Args:
            activity: Activity dict from API
            
        Returns:
            Formatted string like "Morning Ride - 25.3 km - 1h 23m"
        """
        name = activity.get("name", "Unnamed Activity")
        distance_km = activity.get("distance", 0) / 1000.0
        moving_time_s = activity.get("moving_time", 0)
        
        hours = moving_time_s // 3600
        minutes = (moving_time_s % 3600) // 60
        
        time_str = f"{hours}h {minutes}m" if hours > 0 else f"{minutes}m"
        
        return f"{name} - {distance_km:.1f} km - {time_str}"
    
    def disconnect(self):
        """Clear authentication (logout)."""
        self._access_token = None
        log.info("[strava_client] Disconnected from Strava")