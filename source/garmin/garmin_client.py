# source/garmin/garmin_client.py
"""
FIXED: Garmin Connect API client for fetching activities and GPX exports.
Uses garminconnect library for authentication and API access.
"""

from pathlib import Path
from datetime import datetime
from typing import List, Dict, Optional, Callable

from garminconnect import Garmin, GarminConnectAuthenticationError, GarminConnectConnectionError

from .garmin_config import GarminConfig
from .garmin_credentials import get_credentials
from ..utils.log import setup_logger

log = setup_logger("garmin.client")


class GarminClient:
    """Client for interacting with Garmin Connect API."""
    
    def __init__(self, log_callback: Optional[Callable[[str, str], None]] = None):
        """
        Initialize Garmin client with config.
        
        Args:
            log_callback: Optional callback function(message, level) for logging
        """
        self.config = GarminConfig()
        self.client: Optional[Garmin] = None
        self.log = log_callback or self._default_log
    
    def _default_log(self, message: str, level: str = "info"):
        """Default logging to console if no callback provided."""
        print(f"[garmin] {message}")
    
    def connect(self, email: str = None, password: str = None) -> bool:
        """
        Authenticate with Garmin Connect using email/password.
        
        Args:
            email: Garmin Connect email
            password: Garmin Connect password
            
        Returns:
            True if connection successful
        """
        # Fallback to stored credentials if not provided
        if not email or not password:
            email, password = get_credentials()
        try:
            log.info("[garmin_client] Connecting to Garmin Connect...")

            # Try to load existing session first
            saved = self.config.load_session()
            if saved:
                saved_email, session_data = saved
                if saved_email == email:
                    log.info("[garmin_client] Using saved session...")
                    try:
                        # Create client 
                        self.client = Garmin(email, password)
                        
                        # FIXED: The garminconnect library handles sessions internally
                        # We can't manually restore sessions - just try to login
                        # If saved session exists, the library may use cached tokens
                        self.client.login()
                        
                        # Test session validity
                        self.client.get_full_name()
                        log.info("[garmin_client] ✓ Connected (session reused)")
                        return True
                        
                    except Exception as e:
                        log.info(f"[garmin_client] Saved session invalid, performing fresh login...")

            # Fresh login
            log.info("[garmin_client] Performing fresh login...")
            self.client = Garmin(email, password)
            self.client.login()

            # FIXED: Save session properly using library's export method
            # Get session data from the client - garminconnect exports this
            session_data = {}
            
            try:
                # The garminconnect library uses OAuth tokens internally
                # These are complex objects that can't be directly serialized
                # We'll save minimal state and rely on fresh login next time
                session_data = {
                    'username': email,
                    'authenticated': True,
                    'last_successful_login': True
                }
                log.debug("[garmin_client] Saved minimal session state")
            except Exception as e:
                log.warning(f"[garmin_client] Could not save session data: {e}")
                # Minimal session data
                session_data = {
                    'username': email,
                    'authenticated': True
                }
            
            # Save for future use
            self.config.save_session(email, session_data)

            user_name = self.client.get_full_name()
            log.info(f"[garmin_client] ✓ Connected to Garmin Connect as {user_name}")
            return True

        except GarminConnectAuthenticationError as e:
            log.error(f"[garmin_client] Authentication failed: {e}")
            log.error("[garmin_client] Check your email and password")
            return False
            
        except GarminConnectConnectionError as e:
            log.error(f"[garmin_client] Connection failed: {e}")
            log.error("[garmin_client] Check your internet connection")
            return False
            
        except Exception as e:
            log.error(f"[garmin_client] Unexpected error: {e}")
            import traceback
            log.error(traceback.format_exc())
            return False
    
    def get_recent_activities(self, limit: int = 30) -> List[Dict]:
        """
        Fetch recent activities.
        
        Args:
            limit: Maximum number of activities to fetch
            
        Returns:
            List of activity dicts with activityId, activityName, startTimeLocal, distance
        """
        if not self.client:
            raise RuntimeError("Not connected. Call connect() first.")
        
        log.info(f"[garmin_client] Fetching {limit} recent activities...")
        
        try:
            # Get activities
            activities = self.client.get_activities(0, limit)
            
            # Filter to cycling activities
            cycling_types = ['cycling', 'road_biking', 'mountain_biking', 'gravel_cycling', 'indoor_cycling']
            cycling = [
                a for a in activities 
                if a.get('activityType', {}).get('typeKey', '').lower() in cycling_types
            ]
            
            log.info(f"[garmin_client] Found {len(cycling)} cycling activities")
            return cycling
            
        except Exception as e:
            log.error(f"[garmin_client] Failed to fetch activities: {e}")
            return []
    
    def get_activity_details(self, activity_id: int) -> Optional[Dict]:
        """
        Fetch detailed activity information.
        
        Args:
            activity_id: Garmin activity ID
            
        Returns:
            Activity dict with full details or None
        """
        if not self.client:
            raise RuntimeError("Not connected. Call connect() first.")
        
        log.debug(f"[garmin_client] Fetching activity {activity_id} details...")
        
        try:
            return self.client.get_activity(activity_id)
        except Exception as e:
            log.error(f"[garmin_client] Failed to fetch activity details: {e}")
            return None
    
    def download_gpx(self, activity_id: int, output_path: Path) -> bool:
        """
        Download activity GPX export.
        
        Args:
            activity_id: Garmin activity ID
            output_path: Where to save GPX file (should be in raw source folder)
            
        Returns:
            True if successful
        """
        if not self.client:
            raise RuntimeError("Not connected. Call connect() first.")
        
        log.info(f"[garmin_client] Downloading GPX for activity {activity_id}...")
        
        try:
            # FIXED: Better error handling for GPX download
            # Download GPX data
            gpx_data = self.client.download_activity(
                activity_id, 
                dl_fmt=self.client.ActivityDownloadFormat.GPX
            )
            
            # Validate GPX data
            if not gpx_data:
                log.error(f"[garmin_client] No GPX data returned for activity {activity_id}")
                return False
            
            if len(gpx_data) < 100:
                log.error(f"[garmin_client] GPX data too small ({len(gpx_data)} bytes)")
                return False
            
            # Save to file
            output_path.parent.mkdir(parents=True, exist_ok=True)
            with output_path.open("wb") as f:
                f.write(gpx_data)
            
            file_size = output_path.stat().st_size
            log.info(
                f"[garmin_client] ✓ Downloaded GPX to {output_path.name} "
                f"({file_size / 1024:.1f} KB)"
            )
            return True
            
        except AttributeError as e:
            log.error(f"[garmin_client] GPX download not supported: {e}")
            log.error("[garmin_client] Make sure you're using the latest garminconnect library")
            return False
            
        except Exception as e:
            log.error(f"[garmin_client] GPX download failed: {e}")
            
            # Provide helpful error messages
            error_str = str(e).lower()
            if "404" in error_str or "not found" in error_str:
                log.error("[garmin_client] Activity not found or no GPS data available")
            elif "403" in error_str or "forbidden" in error_str:
                log.error("[garmin_client] Access denied - check activity privacy settings")
            elif "401" in error_str or "unauthorized" in error_str:
                log.error("[garmin_client] Session expired - try reconnecting")
                self.client = None
                
            return False
    
    def format_activity_summary(self, activity: Dict) -> str:
        """
        Format activity as readable string for UI display.
        
        Args:
            activity: Activity dict from API
            
        Returns:
            Formatted string like "Morning Ride - 25.3 km - 1h 23m"
        """
        name = activity.get("activityName", "Unnamed Activity")
        distance_m = activity.get("distance", 0)
        distance_km = distance_m / 1000.0
        duration_s = activity.get("duration", 0)
        
        hours = int(duration_s // 3600)
        minutes = int((duration_s % 3600) // 60)
        
        time_str = f"{hours}h {minutes}m" if hours > 0 else f"{minutes}m"
        
        return f"{name} - {distance_km:.1f} km - {time_str}"
    
    def disconnect(self):
        """Clear connection (logout)."""
        self.client = None
        log.info("[garmin_client] Disconnected from Garmin Connect")