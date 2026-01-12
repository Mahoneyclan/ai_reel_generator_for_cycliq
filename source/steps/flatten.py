# source/steps/flatten.py
"""
Parse GPX → resample to 1 Hz timeline with speed/gradient.
Merged: flatten + enrich (always run together).
"""

from __future__ import annotations
import csv
import gpxpy
from datetime import timezone

from ..config import DEFAULT_CONFIG as CFG
from ..utils.gpx import _haversine_m
from ..io_paths import flatten_path, _mk
from ..utils.log import setup_logger
from ..utils.progress_reporter import report_progress

log = setup_logger("steps.flatten")
RESAMPLE_INTERVAL_S = 1.0

def run():
    """Parse GPX with safe failure handling and auto-detection."""
    out = _mk(flatten_path())
    
    def _write_empty_csv():
        with out.open("w", newline="") as f:
            csv.writer(f).writerow([
                "gpx_epoch", "gpx_time_utc", "lat", "lon", "elevation",
                "hr_bpm", "cadence_rpm", "speed_kmh", "gradient_pct"
            ])
        return out
    
    # Step 1: Locate GPX file (project working directory, fallback to raw input)
    report_progress(1, 5, "Locating GPX file...")
    gpx_fp = CFG.GPX_FILE  # Project working directory

    if not gpx_fp.exists():
        log.info(f"[flatten] GPX not in working dir, checking raw input...")
        # Fallback: check raw input folder (legacy location)
        legacy_gpx = CFG.INPUT_GPX_FILE
        if legacy_gpx.exists():
            gpx_fp = legacy_gpx
            log.info(f"[flatten] ✓ Found GPX in raw input: {gpx_fp.name}")
        else:
            # Auto-detect any .gpx in working dir or input dir
            gpx_files = list(CFG.WORKING_DIR.glob("*.gpx")) + list(CFG.INPUT_DIR.glob("*.gpx"))

            if not gpx_files:
                log.error(f"[flatten] ❌ No GPX files found in working or input directories")
                log.error("[flatten] Pipeline will continue but all steps requiring GPS will be skipped")
                return _write_empty_csv()

            gpx_fp = gpx_files[0]
            log.info(f"[flatten] ✓ Auto-detected GPX file: {gpx_fp.name}")
    
    # Validate file
    try:
        file_size = gpx_fp.stat().st_size
        if file_size == 0:
            log.error(f"[flatten] ❌ GPX file is empty: {gpx_fp.name}")
            return _write_empty_csv()
        
        if file_size < 100:
            log.warning(f"[flatten] ⚠️  GPX file is very small ({file_size} bytes), may be corrupt")
    except Exception as e:
        log.error(f"[flatten] ❌ Cannot read GPX file: {e}")
        return _write_empty_csv()
    
    # Step 2: Parse GPX
    report_progress(2, 5, f"Parsing GPX ({file_size / 1024:.1f} KB)...")
    log.info(f"[flatten] Parsing {gpx_fp.name} ({file_size / 1024:.1f} KB)")
    
    try:
        with gpx_fp.open() as f:
            gpx = gpxpy.parse(f)
    except Exception as e:
        log.error(f"[flatten] ❌ Failed to parse GPX file: {e}")
        return _write_empty_csv()

    # Extract trackpoints
    pts = [p for trk in gpx.tracks for seg in trk.segments for p in seg.points if p.time]
    
    if not pts:
        log.error("[flatten] ❌ GPX file contains no trackpoints with timestamps")
        return _write_empty_csv()

    pts.sort(key=lambda p: p.time.timestamp())
    log.info(f"[flatten] ✓ Parsed {len(pts)} trackpoints")
    
    # Step 3: Resample to 1 Hz
    report_progress(3, 5, f"Resampling {len(pts)} points to 1 Hz...")
    
    rows = []
    t = pts[0].time.timestamp()
    end = pts[-1].time.timestamp()
    gi = 0

    while t <= end:
        # Find nearest point
        while gi + 1 < len(pts) and pts[gi+1].time.timestamp() <= t:
            gi += 1
        cand = [pts[gi]] + ([pts[gi+1]] if gi+1 < len(pts) else [])
        best = min(cand, key=lambda p: abs(p.time.timestamp() - t))

        # Extract extensions (HR, cadence)
        hr = cad = None
        if best.extensions:
            for ext in best.extensions:
                for c in ext:
                    tag = (c.tag or "").lower()
                    if "hr" in tag and c.text:
                        try:
                            hr = int(c.text)
                        except (ValueError, TypeError):
                            log.debug(f"[flatten] Could not parse HR value: {c.text!r}")
                    if "cad" in tag and c.text:
                        try:
                            cad = int(c.text)
                        except (ValueError, TypeError):
                            log.debug(f"[flatten] Could not parse cadence value: {c.text!r}")

        corrected_epoch = best.time.timestamp() + CFG.GPX_TIME_OFFSET_S

        rows.append({
            "gpx_epoch": f"{corrected_epoch:.3f}",
            "gpx_time_utc": best.time.astimezone(timezone.utc).isoformat(),
            "lat": f"{best.latitude:.6f}",
            "lon": f"{best.longitude:.6f}",
            "elevation": f"{best.elevation:.1f}" if best.elevation else "",
            "hr_bpm": f"{hr}" if hr else "",
            "cadence_rpm": f"{cad}" if cad else "",
            "speed_kmh": "",
            "gradient_pct": "",
        })
        t += RESAMPLE_INTERVAL_S

    # Step 4: Compute speed and gradient
    report_progress(4, 5, f"Computing speed and gradient for {len(rows)} points...")
    
    for i, r in enumerate(rows):
        if i == 0:
            continue
        
        # Report sub-progress for long computations
        if i % 500 == 0:
            report_progress(4, 5, f"Computing metrics: {i}/{len(rows)} points")

        try:
            p = rows[i-1]
            lat1, lon1 = float(p["lat"]), float(p["lon"])
            lat2, lon2 = float(r["lat"]), float(r["lon"])
            dt = float(r["gpx_epoch"]) - float(p["gpx_epoch"])

            if dt <= 0:
                continue

            d_m = _haversine_m(lat1, lon1, lat2, lon2)
            r["speed_kmh"] = f"{(d_m/dt)*3.6:.1f}"

            if r.get("elevation") and p.get("elevation") and d_m > 0:
                grad = ((float(r["elevation"]) - float(p["elevation"])) / d_m) * 100
                r["gradient_pct"] = f"{grad:.1f}"
        except Exception:
            pass

    # Step 5: Write output
    report_progress(5, 5, "Writing flattened CSV...")
    
    with out.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)

    log.info(f"[flatten] ✓ Wrote {len(rows)} resampled points to {out}")
    return out

