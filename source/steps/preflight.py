# source/steps/preflight.py
"""
Pre-flight check: validate inputs before running pipeline.
Simplified to rely on config path resolution instead of redundant checks.
"""

from __future__ import annotations
from pathlib import Path
from ..config import DEFAULT_CONFIG as CFG
from ..utils.log import setup_logger
from ..utils.progress_reporter import report_progress

log = setup_logger("steps.preflight")


def check_gpx() -> bool:
    """
    Check if GPX file exists in source directory.
    
    Returns:
        True if GPX file found, False otherwise (with appropriate warnings)
    """
    log.info("[preflight] Checking GPS data...")
    
    # Check configured GPX file
    gpx_file = CFG.INPUT_GPX_FILE
    if gpx_file.exists():
        size = gpx_file.stat().st_size
        log.info(f"[preflight] ✓ Found {gpx_file.name} ({size / 1024:.1f} KB)")
        return True
    
    # Check for any GPX in source directory
    gpx_files = list(CFG.INPUT_DIR.glob("*.gpx"))
    if gpx_files:
        log.info(f"[preflight] ✓ Found {len(gpx_files)} GPX file(s):")
        for gf in gpx_files:
            log.info(f"[preflight]     • {gf.name}")
        return True
    
    log.warning("[preflight] ⚠️  No GPX files found in source")
    log.warning("[preflight] Pipeline will run without GPS data")
    return False


def check_videos() -> bool:
    """
    Check if video files exist in INPUT_VIDEOS_DIR.
    
    Uses config's INPUT_VIDEOS_DIR which already handles symlink resolution.
    No redundant path checking needed.
    
    Returns:
        True if videos found, False otherwise
    """
    log.info("[preflight] Checking video files...")
    
    # Use config's resolved path (handles symlinks automatically)
    videos = list(CFG.INPUT_VIDEOS_DIR.glob("*_*.MP4"))
    
    if not videos:
        log.error("[preflight] ❌ No videos found matching pattern '*_*.MP4'")
        log.error(f"[preflight] Searched in: {CFG.INPUT_VIDEOS_DIR}")
        log.error(f"[preflight] Source folder: {CFG.INPUT_DIR}")
        log.error(f"[preflight] Project folder: {CFG.PROJECT_DIR}")
        return False
    
    # Group by camera for summary
    by_cam = {}
    for v in videos:
        parts = v.stem.split("_")
        cam = "_".join(parts[:-1]) if len(parts) > 1 else parts[0]
        by_cam.setdefault(cam, []).append(v)
    
    log.info(f"[preflight] ✓ Found {len(videos)} video files:")
    for cam, files in sorted(by_cam.items()):
        log.info(f"[preflight]     • {cam}: {len(files)} clips")
    
    return True


def check_assets() -> bool:
    """
    Check if required assets exist for splash/intro/outro.
    
    Returns:
        True if all assets found, False with warnings if any missing
    """
    log.info("[preflight] Checking assets...")
    
    required = {
        "Logo": CFG.PROJECT_ROOT / "assets" / "velo_films.png",
        "Intro music": CFG.INTRO_MUSIC,
        "Outro music": CFG.OUTRO_MUSIC,
    }
    
    all_ok = True
    for name, path in required.items():
        if path.exists():
            log.info(f"[preflight] ✓ {name}: {path.name}")
        else:
            log.warning(f"[preflight] ⚠️  {name} missing: {path}")
            all_ok = False
    
    if not all_ok:
        log.warning("[preflight] Some assets missing (splash/music will be affected)")
    
    return all_ok


def run() -> bool:
    """
    Run all pre-flight checks with GUI progress reporting.
    
    Returns:
        True if critical checks pass, False otherwise
    """
    log.info(f"[preflight] Starting pre-flight checks for: {CFG.RIDE_FOLDER}")
    log.info(f"[preflight] Input directory: {CFG.INPUT_DIR}")
    log.info(f"[preflight] Project directory: {CFG.PROJECT_DIR}")
    
    report_progress(1, 3, "Checking video files...")
    videos_ok = check_videos()
    
    report_progress(2, 3, "Checking GPS data...")
    gps_ok = check_gpx()
    
    report_progress(3, 3, "Checking assets...")
    assets_ok = check_assets()
    
    # Summary
    checks = {
        "Videos": videos_ok,
        "GPS data": gps_ok,
        "Assets": assets_ok,
    }
    
    log.info("\n[preflight] ╔═══════════════════════════════════════╗")
    log.info("[preflight] ║  Pre-flight Check Summary            ║")
    log.info("[preflight] ╚═══════════════════════════════════════╝")
    for name, passed in checks.items():
        status = "✓ PASS" if passed else "✗ FAIL"
        log.info(f"[preflight]   {status:8s} {name}")
    
    # Only videos are critical
    critical_failed = not checks["Videos"]
    
    if critical_failed:
        log.error("[preflight] ╔═══════════════════════════════════════╗")
        log.error("[preflight] ║  CRITICAL: Cannot proceed             ║")
        log.error("[preflight] ╚═══════════════════════════════════════╝")
        log.error("[preflight] ❌ No videos found")
        log.error("[preflight] Add video files to:")
        log.error(f"[preflight]   {CFG.INPUT_DIR}")
        return False
    
    if not checks["GPS data"]:
        log.warning("[preflight] ╔═══════════════════════════════════════╗")
        log.warning("[preflight] ║  WARNING: No GPS data                 ║")
        log.warning("[preflight] ╚═══════════════════════════════════════╝")
        log.warning("[preflight] ⚠️  Pipeline will run with limited features")
        log.warning("[preflight] Use 'Get GPX' to import from Strava/Garmin")
    
    log.info("[preflight] ╔═══════════════════════════════════════╗")
    log.info("[preflight] ║  ✓ Ready to proceed                   ║")
    log.info("[preflight] ╚═══════════════════════════════════════╝")
    return True


if __name__ == "__main__":
    import sys
    sys.exit(0 if run() else 1)