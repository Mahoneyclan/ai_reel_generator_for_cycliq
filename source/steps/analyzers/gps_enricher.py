# source/steps/analyzers/gps_enricher.py
"""
GPX telemetry enrichment for frame metadata.
Matches frames to GPS trackpoints and adds speed, elevation, HR, cadence, gradient.
"""

from __future__ import annotations
from typing import Dict

from ...config import DEFAULT_CONFIG as CFG
from ...utils.gpx import GPXIndex, load_gpx
from ...utils.log import setup_logger

log = setup_logger("steps.analyzers.gps_enricher")


class GPSEnricher:
    """Enriches frame metadata with GPX telemetry data."""
    
    def __init__(self):
        self.gpx_index = self._load_gpx_index()
        self.matches = 0
        self.misses = 0
    
    def _load_gpx_index(self) -> GPXIndex:
        """Load GPX data and build index for fast lookups."""
        try:
            gpx_path = CFG.INPUT_GPX_FILE
            if not gpx_path.exists():
                log.warning("[gps_enricher] No GPX file found, skipping GPS enrichment")
                return GPXIndex([])
            
            points = load_gpx(str(gpx_path))
            if not points:
                log.warning("[gps_enricher] GPX file loaded but contains no points")
                return GPXIndex([])
            
            log.info(f"[gps_enricher] Loaded {len(points)} GPX points")
            return GPXIndex(points)
            
        except Exception as e:
            log.error(f"[gps_enricher] Failed to load GPX: {e}")
            return GPXIndex([])
    
    def enrich(self, row: Dict) -> Dict:
        """
        Add GPX telemetry to frame metadata.
        
        Args:
            row: Frame metadata dict with abs_time_epoch
            
        Returns:
            Updated row with GPX fields added
        """
        epoch = float(row.get("abs_time_epoch", 0))
        pt = self.gpx_index.find_within_tolerance(epoch, CFG.GPX_TOLERANCE)
        
        if pt:
            self.matches += 1
            row["gpx_missing"] = "false"
            row["gpx_dt_s"] = f"{abs(pt.timestamp_epoch - epoch):.3f}"
            row["gpx_epoch"] = f"{pt.timestamp_epoch:.3f}"
            row["gpx_time_utc"] = pt.when.isoformat()
            row["lat"] = f"{pt.lat:.6f}"
            row["lon"] = f"{pt.lon:.6f}"
            row["elevation"] = f"{pt.ele:.1f}"
            row["hr_bpm"] = str(pt.hr) if pt.hr else ""
            row["cadence_rpm"] = str(pt.cadence) if pt.cadence else ""
            row["speed_kmh"] = f"{pt.speed_kmh:.1f}" if pt.speed_kmh else ""
            row["gradient_pct"] = f"{pt.gradient:.1f}" if pt.gradient else ""
        else:
            self.misses += 1
            row["gpx_missing"] = "true"
            for key in ["gpx_dt_s", "gpx_epoch", "gpx_time_utc", "lat", "lon", 
                        "elevation", "hr_bpm", "cadence_rpm", "speed_kmh", "gradient_pct"]:
                row[key] = ""
        
        return row
    
    def get_stats(self) -> Dict:
        """Return enrichment statistics."""
        total = self.matches + self.misses
        match_pct = (self.matches / total * 100) if total > 0 else 0
        
        return {
            "gps_matches": self.matches,
            "gps_misses": self.misses,
            "gps_match_pct": f"{match_pct:.1f}%"
        }