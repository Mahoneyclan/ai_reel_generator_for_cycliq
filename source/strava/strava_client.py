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
        Download activity GPS data as GPX file.

        Uses streams API to construct GPX (more reliable than export_gpx endpoint).

        Args:
            activity_id: Strava activity ID
            output_path: Where to save GPX file

        Returns:
            True if successful
        """
        if not self._access_token:
            raise RuntimeError("Not connected. Call connect() first.")

        log.info(f"[strava_client] Downloading GPS data for activity {activity_id}...")

        try:
            # Get activity details for metadata
            details = self.get_activity_details(activity_id)
            if not details:
                log.error(f"[strava_client] Could not fetch activity details")
                return False

            # Get streams (GPS data)
            streams = self._get_activity_streams(activity_id)
            if not streams:
                log.error(f"[strava_client] No GPS streams available for activity {activity_id}")
                return False

            # Build GPX from streams
            gpx_content = self._build_gpx_from_streams(details, streams)
            if not gpx_content:
                log.error(f"[strava_client] Failed to build GPX from streams")
                return False

            # Save GPX file
            output_path.parent.mkdir(parents=True, exist_ok=True)
            with output_path.open("w") as f:
                f.write(gpx_content)

            file_size = output_path.stat().st_size
            log.info(
                f"[strava_client] ✓ Downloaded GPX to {output_path.name} "
                f"({file_size / 1024:.1f} KB)"
            )
            return True

        except Exception as e:
            log.error(f"[strava_client] GPX download failed: {e}")
            return False

    def _get_activity_streams(self, activity_id: int) -> Optional[Dict]:
        """
        Fetch activity streams (GPS, altitude, time, heartrate, etc.)

        Args:
            activity_id: Strava activity ID

        Returns:
            Dict of stream data or None
        """
        try:
            response = requests.get(
                f"{self.config.API_BASE_URL}/activities/{activity_id}/streams",
                headers={"Authorization": f"Bearer {self._access_token}"},
                params={
                    "keys": "time,latlng,altitude,heartrate,cadence",
                    "key_by_type": "true"
                }
            )

            if response.status_code == 404:
                log.warning(f"[strava_client] No streams available for activity {activity_id}")
                return None

            response.raise_for_status()
            return response.json()

        except requests.RequestException as e:
            log.error(f"[strava_client] Failed to fetch streams: {e}")
            return None

    def _build_gpx_from_streams(self, activity: Dict, streams: Dict) -> Optional[str]:
        """
        Build GPX XML from Strava streams data.

        Args:
            activity: Activity details dict
            streams: Streams data dict

        Returns:
            GPX XML string or None
        """
        latlng = streams.get("latlng", {}).get("data", [])
        altitude = streams.get("altitude", {}).get("data", [])
        time_data = streams.get("time", {}).get("data", [])
        heartrate = streams.get("heartrate", {}).get("data", [])
        cadence = streams.get("cadence", {}).get("data", [])

        if not latlng:
            log.warning("[strava_client] No latlng data in streams")
            return None

        # Parse activity start time
        start_time_str = activity.get("start_date", "")
        try:
            start_time = datetime.fromisoformat(start_time_str.replace("Z", "+00:00"))
        except (ValueError, TypeError):
            start_time = datetime.now(timezone.utc)

        activity_name = activity.get("name", "Strava Activity")

        # Build GPX XML
        gpx_lines = [
            '<?xml version="1.0" encoding="UTF-8"?>',
            '<gpx version="1.1" creator="Velo Highlights AI (Strava Import)"',
            '     xmlns="http://www.topografix.com/GPX/1/1"',
            '     xmlns:gpxtpx="http://www.garmin.com/xmlschemas/TrackPointExtension/v1">',
            '  <metadata>',
            f'    <name>{activity_name}</name>',
            f'    <time>{start_time.isoformat()}</time>',
            '  </metadata>',
            '  <trk>',
            f'    <name>{activity_name}</name>',
            '    <trkseg>',
        ]

        for i, (lat, lon) in enumerate(latlng):
            # Calculate timestamp
            if i < len(time_data):
                from datetime import timedelta
                point_time = start_time + timedelta(seconds=time_data[i])
            else:
                point_time = start_time

            ele = altitude[i] if i < len(altitude) else 0

            gpx_lines.append(f'      <trkpt lat="{lat}" lon="{lon}">')
            gpx_lines.append(f'        <ele>{ele}</ele>')
            gpx_lines.append(f'        <time>{point_time.isoformat()}</time>')

            # Add extensions for HR/cadence if available
            has_hr = i < len(heartrate) and heartrate[i]
            has_cad = i < len(cadence) and cadence[i]
            if has_hr or has_cad:
                gpx_lines.append('        <extensions>')
                gpx_lines.append('          <gpxtpx:TrackPointExtension>')
                if has_hr:
                    gpx_lines.append(f'            <gpxtpx:hr>{heartrate[i]}</gpxtpx:hr>')
                if has_cad:
                    gpx_lines.append(f'            <gpxtpx:cad>{cadence[i]}</gpxtpx:cad>')
                gpx_lines.append('          </gpxtpx:TrackPointExtension>')
                gpx_lines.append('        </extensions>')

            gpx_lines.append('      </trkpt>')

        gpx_lines.extend([
            '    </trkseg>',
            '  </trk>',
            '</gpx>'
        ])

        log.info(f"[strava_client] Built GPX with {len(latlng)} trackpoints")
        return '\n'.join(gpx_lines)
    
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
        Includes date, name, distance, and duration.
        """
        name = activity.get("name", "Unnamed Activity")
        distance_km = activity.get("distance", 0) / 1000.0
        moving_time_s = activity.get("moving_time", 0)

        hours = moving_time_s // 3600
        minutes = (moving_time_s % 3600) // 60
        time_str = f"{hours}h {minutes}m" if hours > 0 else f"{minutes}m"

        # Include date from start_date_local
        date_str = activity.get("start_date_local", "")[:10]

        return f"{date_str} | {name} - {distance_km:.1f} km - {time_str}"

    
    def get_segment_efforts(self, activity_id: int) -> List[Dict]:
        """
        Extract PR segment efforts from activity details.

        Args:
            activity_id: Strava activity ID

        Returns:
            List of segment effort dicts with timing and PR info
        """
        details = self.get_activity_details(activity_id)
        if not details:
            return []

        efforts = details.get("segment_efforts", [])
        if not efforts:
            log.info(f"[strava_client] No segment efforts in activity {activity_id}")
            return []

        # Extract relevant fields for PR efforts
        pr_efforts = []
        for effort in efforts:
            pr_rank = effort.get("pr_rank")

            # Only include if it's a PR (rank 1) or top 3
            if pr_rank is not None and pr_rank <= 3:
                segment = effort.get("segment", {})
                pr_efforts.append({
                    "name": effort.get("name", "Unknown Segment"),
                    "start_time": effort.get("start_date"),
                    "elapsed_time": effort.get("elapsed_time", 0),
                    "pr_rank": pr_rank,
                    "kom_rank": effort.get("kom_rank"),
                    "distance": effort.get("distance", 0),
                    "climb_category": segment.get("climb_category", 5),
                    "average_grade": segment.get("average_grade", 0),
                })

        log.info(
            f"[strava_client] Found {len(pr_efforts)} PR/top-3 efforts "
            f"out of {len(efforts)} total segments"
        )
        return pr_efforts

    def disconnect(self):
        """Clear authentication (logout)."""
        self._access_token = None
        log.info("[strava_client] Disconnected from Strava")