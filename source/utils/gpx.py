# source/utils/gpx.py
"""
Lightweight GPX loader + derived stats for ride banner.
Returns list[GpxPoint] and helpers; robust for missing extensions.
Includes GPXIndex for fast O(log n) timestamp lookups via binary search.
"""

from __future__ import annotations
from dataclasses import dataclass
from typing import List, Optional
from datetime import datetime, timezone
from bisect import bisect_left
import math
import xml.etree.ElementTree as ET

@dataclass
class GpxPoint:
    """Single GPS trackpoint with telemetry."""
    lat: float
    lon: float
    ele: float
    when: datetime
    t_s: float
    timestamp_epoch: float
    hr: Optional[int] = None
    cadence: Optional[int] = None
    speed_kmh: Optional[float] = None
    gradient: Optional[float] = None

class GPXIndex:
    """Fast O(log n) timestamp lookup using binary search."""

    def __init__(self, points: List[GpxPoint]):
        if not points:
            self.points = []
            self.epochs = []
            return

        # Sort by timestamp and extract epochs for binary search
        self.points = sorted(points, key=lambda p: p.timestamp_epoch)
        self.epochs = [p.timestamp_epoch for p in self.points]

    def find_nearest(self, target_epoch: float) -> Optional[GpxPoint]:
        """Find GPX point closest to target timestamp in O(log n) time."""
        if not self.points:
            return None

        if len(self.points) == 1:
            return self.points[0]

        # Binary search for insertion point
        idx = bisect_left(self.epochs, target_epoch)

        # Handle edge cases
        if idx == 0:
            return self.points[0]
        if idx == len(self.points):
            return self.points[-1]

        # Compare distances to before/after points
        before = self.points[idx - 1]
        after = self.points[idx]

        dist_before = abs(target_epoch - before.timestamp_epoch)
        dist_after = abs(target_epoch - after.timestamp_epoch)

        return before if dist_before < dist_after else after

    def find_within_tolerance(self, target_epoch: float, tolerance: float) -> Optional[GpxPoint]:
        """Find nearest point within tolerance, or None if too far."""
        nearest = self.find_nearest(target_epoch)
        if nearest is None:
            return None

        distance = abs(target_epoch - nearest.timestamp_epoch)
        return nearest if distance <= tolerance else None

    def __len__(self):
        return len(self.points)

    def __getitem__(self, idx):
        return self.points[idx]

def _haversine_m(lat1, lon1, lat2, lon2):
    """Compute distance in meters between two lat/lon points."""
    R = 6371000.0
    a1, b1 = math.radians(lat1), math.radians(lon1)
    a2, b2 = math.radians(lat2), math.radians(lon2)
    dA = a2 - a1
    dB = b2 - b1
    h = math.sin(dA/2)**2 + math.cos(a1)*math.cos(a2)*math.sin(dB/2)**2
    return 2 * R * math.asin(math.sqrt(h))

def load_gpx(path: str) -> List[GpxPoint]:
    """Parse GPX file and return list of trackpoints."""
    root = ET.parse(path).getroot()
    ns = {"ns": root.tag.split('}')[0].strip('{')}
    pts = []
    
    for trkpt in root.findall(".//ns:trkpt", ns):
        lat = float(trkpt.attrib["lat"])
        lon = float(trkpt.attrib["lon"])
        ele = float(trkpt.findtext("ns:ele", "0.0", ns))
        t = trkpt.findtext("ns:time", namespaces=ns)
        if not t:
            continue
        when = datetime.fromisoformat(t.replace("Z", "+00:00")).astimezone(timezone.utc)
        
        hr = cad = None
        for ext in trkpt.findall("ns:extensions/ns:*", ns):
            tag = ext.tag.lower()
            try:
                if "hr" in tag:
                    hr = int(ext.text)
                elif "cad" in tag or "cadence" in tag:
                    cad = int(ext.text)
            except:
                pass
        
        pts.append(GpxPoint(lat, lon, ele, when, 0.0, when.timestamp(), hr, cad))
    
    if not pts:
        return []
    
    t0 = pts[0].when
    for i, p in enumerate(pts):
        p.t_s = (p.when - t0).total_seconds()
        if i > 0:
            q = pts[i-1]
            dt = (p.when - q.when).total_seconds()
            if dt > 0:
                d = _haversine_m(q.lat, q.lon, p.lat, p.lon)
                if d > 0:
                    p.speed_kmh = (d / dt) * 3.6
                    p.gradient = max(-25, min(25, ((p.ele - q.ele) / d) * 100))
    
    return pts

def compute_stats(points: List[GpxPoint]) -> dict:
    """Compute ride statistics from GPX points."""
    if not points:
        return {}
    
    dist = 0.0
    climb = 0.0
    hrs = []
    cads = []
    
    for i in range(1, len(points)):
        p, q = points[i-1], points[i]
        d = _haversine_m(p.lat, p.lon, q.lat, q.lon)
        dist += d
        gain = q.ele - p.ele
        if gain > 0:
            climb += gain
        if q.hr is not None:
            hrs.append(q.hr)
        if q.cadence is not None:
            cads.append(q.cadence)
    
    dur = (points[-1].when - points[0].when).total_seconds()
    km = dist / 1000.0
    avg = (km / (dur / 3600.0)) if dur > 0 else 0.0
    
    return {
        "duration_s": dur,
        "distance_m": dist,
        "distance_km": km,
        "avg_speed": avg,
        "avg_hr": (sum(hrs) / len(hrs)) if hrs else None,
        "avg_cadence": (sum(cads) / len(cads)) if cads else None,
        "total_climb_m": climb
    }

def compute_telemetry(pt: GpxPoint) -> dict:
    """Extract telemetry dict from a GpxPoint."""
    return {
        "speed_kmh": pt.speed_kmh or 0.0,
        "hr_bpm": pt.hr or 0.0,
        "cadence_rpm": pt.cadence or 0.0,
        "gradient_pct": pt.gradient or 0.0,
    }