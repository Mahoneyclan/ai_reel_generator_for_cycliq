# source/utils/gauge_overlay.py
"""
Gauge overlay generation for HUD.
Creates PNG gauge images for speed, cadence, heart rate, elevation, gradient.
"""

from __future__ import annotations
import csv
from pathlib import Path
from typing import Dict, List
from PIL import Image

from ..config import DEFAULT_CONFIG as CFG
from .draw_gauge import (
    draw_speed_gauge,
    draw_cadence_gauge,
    draw_hr_gauge,
    draw_elev_gauge,
    draw_gradient_gauge,
)

# Exposed sizes for layout math in build.py
SPEED_GAUGE_SIZE = 240
SMALL_GAUGE_SIZE = 120

def compute_gauge_maxes(csv_path: Path) -> Dict[str, float]:
    """Compute maximum values for gauge scaling from CSV data."""
    maxes = {"speed": 0.0, "cadence": 0.0, "hr": 0.0, "elev": 0.0, "gradient": 0.0}
    
    try:
        with csv_path.open() as f:
            for r in csv.DictReader(f):
                try:
                    s = float(r.get("speed_kmh") or 0.0)
                    c = float(r.get("cadence_rpm") or 0.0)
                    h = float(r.get("hr_bpm") or 0.0)
                    e = float(r.get("elevation") or 0.0)
                    g = float(r.get("gradient_pct") or 0.0)
                except Exception:
                    continue
                
                if s > maxes["speed"]:
                    maxes["speed"] = s
                if c > maxes["cadence"]:
                    maxes["cadence"] = c
                if h > maxes["hr"]:
                    maxes["hr"] = h
                if e > maxes["elev"]:
                    maxes["elev"] = e
                if abs(g) > maxes["gradient"]:
                    maxes["gradient"] = abs(g)

        import math
        def round_up(x: float, step: float) -> float:
            if x <= 0:
                return step
            return math.ceil(x / step) * step

        maxes["speed"] = round_up(maxes["speed"], 10.0)
        maxes["cadence"] = round_up(maxes["cadence"], 10.0)
        maxes["hr"] = round_up(maxes["hr"], 10.0)
        maxes["elev"] = round_up(maxes["elev"], 50.0)
        maxes["gradient"] = round_up(maxes["gradient"], 2.0)

    except Exception:
        # Fallback defaults
        maxes = {"speed": 60.0, "cadence": 120.0, "hr": 190.0, "elev": 300.0, "gradient": 15.0}

    # Apply config caps
    capped = {}
    capped["speed"] = min(maxes["speed"], CFG.GAUGE_MAXES.get("speed", maxes["speed"]))
    capped["cadence"] = min(maxes["cadence"], CFG.GAUGE_MAXES.get("cadence", maxes["cadence"]))
    capped["hr"] = min(maxes["hr"], CFG.GAUGE_MAXES.get("hr", maxes["hr"]))
    capped["elev"] = min(maxes["elev"], CFG.GAUGE_MAXES.get("elev", maxes["elev"]))
    capped["gradient"] = min(maxes["gradient"], CFG.GAUGE_MAXES.get("gradient_max", maxes["gradient"]))
    
    return capped

def create_all_gauge_images(
    telemetry: Dict[str, List[float]],
    gauge_maxes: Dict[str, float],
    base_dir: Path,
    clip_idx: int,
) -> Dict[str, Path]:
    """
    Create gauge images for all telemetry types and return dict of paths.
    base_dir is a per-clip folder under GAUGE_DIR, created by build.py.
    """
    out: Dict[str, Path] = {}
    base_dir.mkdir(parents=True, exist_ok=True)

    for gtype, values in telemetry.items():
        if not values:
            continue
        val = float(values[0] or 0.0)
        max_val = gauge_maxes.get(gtype, None)

        if gtype == "speed":
            size = SPEED_GAUGE_SIZE
            img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
            draw_speed_gauge(img, (0, 0, size, size), val, float(max_val or 60))
        elif gtype == "cadence":
            size = SMALL_GAUGE_SIZE
            img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
            draw_cadence_gauge(img, (0, 0, size, size), val, float(max_val or 120))
        elif gtype == "hr":
            size = SMALL_GAUGE_SIZE
            img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
            draw_hr_gauge(img, (0, 0, size, size), val, float(max_val or 180))
        elif gtype == "elev":
            size = SMALL_GAUGE_SIZE
            img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
            draw_elev_gauge(img, (0, 0, size, size), val, float(max_val or 1000))
        elif gtype == "gradient":
            size = SMALL_GAUGE_SIZE
            img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
            draw_gradient_gauge(img, (0, 0, size, size), val,
                                -float(max_val or 10), float(max_val or 10))
        else:
            continue

        fp = base_dir / f"gauge_{gtype}.png"
        img.save(fp)
        out[gtype] = fp

    return out