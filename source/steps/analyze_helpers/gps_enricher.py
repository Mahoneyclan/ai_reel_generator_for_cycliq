# source/steps/analyze_helpers/gps_enricher.py
"""
GPX telemetry enrichment for frame metadata.
Uses flatten.csv as authoritative source for HR, cadence, speed, gradient, elevation.
"""

from __future__ import annotations
import csv
from typing import Dict, List
from bisect import bisect_left

from ...config import DEFAULT_CONFIG as CFG
from ...io_paths import flatten_path
from ...utils.log import setup_logger

log = setup_logger("steps.analyze_helpers.gps_enricher")


class GPSEnricher:
    """Enriches frame metadata using flatten.csv timeline."""

    def __init__(self):
        self.points = self._load_flatten_points()
        self.epochs = [p["gpx_epoch"] for p in self.points]
        self.matches = 0
        self.misses = 0

    def _load_flatten_points(self) -> List[Dict]:
        """Load flatten.csv and parse telemetry rows."""
        fp = flatten_path()
        if not fp.exists():
            log.warning("[gps_enricher] flatten.csv missing; telemetry will be empty")
            return []

        points = []
        skipped = 0
        try:
            with fp.open() as f:
                reader = csv.DictReader(f)
                for row_idx, r in enumerate(reader):
                    try:
                        epoch = float(r.get("gpx_epoch") or 0.0)
                        points.append({
                            "gpx_epoch": epoch,
                            "gpx_time_utc": r.get("gpx_time_utc", ""),
                            "lat": r.get("lat", ""),
                            "lon": r.get("lon", ""),
                            "elevation": r.get("elevation", ""),
                            "hr_bpm": r.get("hr_bpm", ""),
                            "cadence_rpm": r.get("cadence_rpm", ""),
                            "speed_kmh": r.get("speed_kmh", ""),
                            "gradient_pct": r.get("gradient_pct", "")
                        })
                    except (ValueError, TypeError) as e:
                        skipped += 1
                        if skipped <= 3:  # Log first few, then suppress
                            log.debug(
                                f"[gps_enricher] Skipping row {row_idx}: "
                                f"gpx_epoch={r.get('gpx_epoch')!r}, error={e}"
                            )
                        continue
            if skipped > 0:
                log.warning(f"[gps_enricher] Skipped {skipped} malformed rows in flatten.csv")
            log.info(f"[gps_enricher] Loaded {len(points)} telemetry points from flatten.csv")
        except Exception as e:
            log.error(f"[gps_enricher] Failed to read flatten.csv: {e}")
        return sorted(points, key=lambda p: p["gpx_epoch"])

    def enrich(self, row: Dict) -> Dict:
        """
        Attach telemetry fields to a frame row using abs_time_epoch.

        The new time model guarantees:
            - abs_time_epoch is the authoritative world-aligned timestamp
            - flatten.csv provides gpx_epoch at 1 Hz
            - We match the nearest GPX epoch within GPX_TOLERANCE
        """

        try:
            epoch = float(row.get("abs_time_epoch", 0.0) or 0.0)
        except (ValueError, TypeError):
            log.debug(
                f"[gps_enricher] Invalid abs_time_epoch: {row.get('abs_time_epoch')!r}, "
                f"frame={row.get('index', '?')}"
            )
            epoch = 0.0

        if not self.points:
            # No GPX data available
            row["gpx_missing"] = "true"
            for k in [
                "gpx_dt_s", "gpx_epoch", "gpx_time_utc", "lat", "lon",
                "elevation", "hr_bpm", "cadence_rpm", "speed_kmh", "gradient_pct"
            ]:
                row[k] = ""
            return row

        # Binary search for nearest GPX point
        idx = bisect_left(self.epochs, epoch)

        best = None
        best_dt = float("inf")

        for offset in (-1, 0, 1):
            i = idx + offset
            if 0 <= i < len(self.points):
                pt = self.points[i]
                dt = abs(pt["gpx_epoch"] - epoch)
                if dt <= CFG.GPX_TOLERANCE and dt < best_dt:
                    best = pt
                    best_dt = dt

        if best:
            self.matches += 1
            row["gpx_missing"] = "false"
            row["gpx_dt_s"] = f"{best_dt:.3f}"
            row["gpx_epoch"] = f"{best['gpx_epoch']:.3f}"
            row["gpx_time_utc"] = best["gpx_time_utc"]
            row["lat"] = best["lat"]
            row["lon"] = best["lon"]
            row["elevation"] = best["elevation"]
            row["hr_bpm"] = best["hr_bpm"]
            row["cadence_rpm"] = best["cadence_rpm"]
            row["speed_kmh"] = best["speed_kmh"]
            row["gradient_pct"] = best["gradient_pct"]
        else:
            self.misses += 1
            row["gpx_missing"] = "true"
            for k in [
                "gpx_dt_s", "gpx_epoch", "gpx_time_utc", "lat", "lon",
                "elevation", "hr_bpm", "cadence_rpm", "speed_kmh", "gradient_pct"
            ]:
                row[k] = ""

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
