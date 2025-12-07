# source/strava/__init__.py
"""
Strava integration package for GPX import.
Implements OAuth 2.0 with PKCE for secure authentication.
"""

from .strava_client import StravaClient
from .strava_auth import StravaAuth
from .strava_config import StravaConfig

__all__ = [
    "StravaClient",
    "StravaAuth", 
    "StravaConfig",
]