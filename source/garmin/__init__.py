# source/garmin/__init__.py
"""
Garmin Connect integration package for GPX import.
Uses garminconnect library for authentication and data access.
"""

from .garmin_client import GarminClient
from .garmin_config import GarminConfig

__all__ = [
    "GarminClient",
    "GarminConfig",
]