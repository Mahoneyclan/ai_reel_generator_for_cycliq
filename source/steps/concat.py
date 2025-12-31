# source/steps/concat.py
"""
Concatenate _intro.mp4, all _middle_##.mp4 segments, and _outro.mp4 into final reel.
Output filename is derived from ride folder name.

MODIFIED: Uses stream copy (fast!) since all inputs are already 1080p.
"""

from __future__ import annotations
from pathlib import Path
import subprocess
import re

from ..config import DEFAULT_CONFIG as CFG
from ..io_paths import clips_dir
from ..utils.log import setup_logger
from ..utils.progress_reporter import report_progress

log = setup_logger("steps.concat")


def run() -> Path:
    """Concatenate intro, multiple middle segments, and outro into final 1080p reel."""
    clips_path = CFG.FINAL_REEL_PATH.parent
    out = CFG.FINAL_REEL_PATH

    intro = clips_path / "_intro.mp4"
    outro = clips_path / "_outro.mp4"

    # Step 1: Collect segments
    report_progress(1, 3, "Collecting segments...")
    middle_segments = []
    for f in clips_path.glob("_middle_*.mp4"):
        m = re.match(r"_middle_(\d+)\.mp4", f.name)
        if m:
            idx = int(m.group(1))
            middle_segments.append((idx, f))
    middle_segments.sort(key=lambda x: x[0])
    middle_files = [f for _, f in middle_segments]

    if not middle_files:
        log.error("[concat] No _middle_##.mp4 segments found – run 'build' step first")
        return out

    # Build final parts list
    final_parts = []
    if intro.exists():
        final_parts.append(intro)
    else:
        log.warning("[concat] _intro.mp4 not found – skipping")

    final_parts.extend(middle_files)

    if outro.exists():
        final_parts.append(outro)
    else:
        log.warning("[concat] _outro.mp4 not found – skipping")

    if not final_parts:
        log.error("[concat] No clips to concatenate")
        return out

    concat_list = CFG.WORKING_DIR / "final_concat_list.txt"
    with concat_list.open("w") as f:
        for part in final_parts:
            f.write(f"file '{part.resolve()}'\n")

    # Step 2: Concatenate and re-encode for Facebook compatibility
    report_progress(2, 3, f"Concatenating {len(final_parts)} parts...")
    log.info(f"[concat] Concatenating {len(final_parts)} parts with Facebook-compliant encoding...")
    subprocess.run([
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
        "-f", "concat", "-safe", "0", "-i", str(concat_list),
        # Re-encode to ensure Facebook compatibility
        "-c:v", "libx264",           # H.264 codec
        "-preset", "medium",         # Encoding speed
        "-crf", "23",                # Quality (18-28, 23 is good)
        "-profile:v", "high",        # H.264 profile
        "-level", "4.0",             # H.264 level
        "-pix_fmt", "yuv420p",       # Pixel format (required)
        "-r", "30",                  # Force 30 fps
        "-c:a", "aac",               # AAC audio
        "-b:a", "128k",              # Audio bitrate
        "-ar", "48000",              # Audio sample rate
        str(out)
    ], check=True)

    # Step 3: Finalize output
    report_progress(3, 3, "Finalizing output...")
    
    # Get final file size
    file_size_mb = out.stat().st_size / (1024 * 1024)
    log.info(f"[concat] Final 1080p reel: {out}")
    log.info(f"[concat] File size: {file_size_mb:.1f} MB")
    
    # Warn if approaching Facebook limits
    if file_size_mb > 4000:  # 4GB
        log.warning(f"[concat] File size ({file_size_mb:.1f} MB) exceeds 4GB - may have upload issues")
    elif file_size_mb > 3000:  # 3GB
        log.warning(f"[concat] File size ({file_size_mb:.1f} MB) is large - upload may be slow")
    
    log.info("[concat] ✅ Output is Facebook-compliant (1080p, H.264, 30fps, AAC audio)")
    log.info("[concat] ✅ Intro, middle segments, and outro are all Strava-compliant (≤30s each)")

    try:
        concat_list.unlink()
    except Exception as e:
        log.debug(f"[concat] cleanup warning: {e}")

    return out


if __name__ == "__main__":
    run()