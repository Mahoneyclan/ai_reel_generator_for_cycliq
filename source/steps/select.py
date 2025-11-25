# source/steps/select.py
"""
Select step:
- Loads enriched.csv (authoritative dataset from Analyze)
- Filters to valid frames (paired_ok, bike_detected, optional GPS)
- Ranks by score_weighted
- Builds a pool capped at 2× target clips
- Marks top target clips as recommended = "true", enforcing min_gap_between_clips
- Writes select.csv including full enriched fields + recommended
- Extracts frame images for all candidates to frames directory
- Ensures output is chronological for GUI consumption
"""

from __future__ import annotations
import csv
import subprocess
from pathlib import Path
from typing import List, Dict
from tqdm import tqdm

from ..config import DEFAULT_CONFIG as CFG
from ..io_paths import enrich_path, select_path, frames_dir, _mk
from ..utils.log import setup_logger

log = setup_logger("steps.select")


def _sf(v, d=0.0) -> float:
    """Safe float conversion."""
    try:
        return float(v) if v not in ("", None) else d
    except Exception:
        return d


def apply_gap_filter(candidates: List[Dict], min_gap_s: int, target_clips: int) -> List[Dict]:
    """
    Select top clips with adaptive spacing based on scene boost.
    High scene-change clips get priority and can be closer together.
    """
    filtered: List[Dict] = []
    used_windows = set()
    
    # Define scene boost thresholds for adaptive gaps
    HIGH_SCENE_THRESHOLD = 0.50  # "Significant" scene change
    MAJOR_SCENE_THRESHOLD = 0.70  # "Major" scene change
    
    for c in candidates:
        t = int(_sf(c.get("abs_time_epoch")))
        scene_boost = _sf(c.get("scene_boost", 0))
        
        # Adaptive gap based on scene quality
        if scene_boost >= MAJOR_SCENE_THRESHOLD:
            # Major scene changes: allow 30s gaps (very close)
            effective_gap = min_gap_s // 2
        elif scene_boost >= HIGH_SCENE_THRESHOLD:
            # Significant scene changes: allow 45s gaps (closer)
            effective_gap = int(min_gap_s * 0.75)
        else:
            # Normal clips: use full gap
            effective_gap = min_gap_s
        
        window = t // effective_gap
        
        if window not in used_windows:
            filtered.append(c)
            # Mark adjacent windows as used to maintain minimum spacing
            for offset in range(-1, 2):  # Block ±1 window
                used_windows.add(window + offset)
        
        if len(filtered) >= target_clips:
            break
    
    return filtered


def extract_frames_for_candidates(pool: List[Dict]) -> None:
    """Extract frame images for all candidate clips to frames directory."""
    if not pool:
        return
    
    log.info(f"[select] Extracting {len(pool)} frame images for manual review...")
    frames_path = _mk(frames_dir())
    
    extraction_count = 0
    
    for candidate in tqdm(pool, desc="[select] Extracting frames", unit="frame", ncols=80):
        try:
            idx = candidate.get("index", "")
            source_file = candidate.get("source", "")
            frame_number = candidate.get("frame_number", "")
            
            if not idx or not source_file or not frame_number:
                log.warning(f"[select] Missing data for candidate: {idx}")
                continue
            
            # Primary frame output path
            output_path = frames_path / f"{idx}_Primary.jpg"
            
            # Skip if already exists
            if output_path.exists():
                continue
            
            video_path = CFG.INPUT_VIDEOS_DIR / source_file
            
            if not video_path.exists():
                log.warning(f"[select] Video not found: {source_file}")
                continue
            
            # Calculate timestamp from frame number (assuming 30fps)
            frame_num = int(frame_number)
            timestamp = frame_num / 30.0
            
            # Extract primary frame using ffmpeg
            cmd = [
                "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
                "-ss", f"{timestamp:.3f}",
                "-i", str(video_path),
                "-frames:v", "1",
                "-q:v", "2",  # High quality JPEG
                str(output_path)
            ]
            
            result = subprocess.run(cmd, capture_output=True)
            if result.returncode != 0:
                log.warning(f"[select] FFmpeg error for {idx}: {result.stderr.decode()}")
                continue
            
            extraction_count += 1
            
            # Extract partner frame if available
            partner_source = candidate.get("partner_source", "")
            partner_frame = candidate.get("partner_frame_number", "")
            
            if partner_source and partner_frame:
                partner_video = CFG.INPUT_VIDEOS_DIR / partner_source
                partner_output = frames_path / f"{idx}_Partner.jpg"
                
                if partner_video.exists() and not partner_output.exists():
                    partner_timestamp = int(partner_frame) / 30.0
                    cmd = [
                        "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
                        "-ss", f"{partner_timestamp:.3f}",
                        "-i", str(partner_video),
                        "-frames:v", "1",
                        "-q:v", "2",
                        str(partner_output)
                    ]
                    subprocess.run(cmd, capture_output=True)
        
        except Exception as e:
            log.warning(f"[select] Failed to extract frame {idx}: {e}")
    
    log.info(f"[select] Extracted {extraction_count} new frame images to {frames_path}")


def run() -> Path:
    """Select top candidates, preselect recommendations, extract frames, and output a 2× pool."""
    src = enrich_path()
    dst = _mk(select_path())

    if not src.exists():
        with dst.open("w", newline="") as f:
            csv.writer(f).writerow(["index"])
        log.error("[select] ❌ enriched.csv missing")
        return dst

    with src.open() as f:
        rows = list(csv.DictReader(f))

    if not rows:
        with dst.open("w", newline="") as f:
            csv.writer(f).writerow(["index"])
        log.error("[select] ❌ enriched.csv is empty")
        return dst

    log.info("=" * 60)
    log.info(f"SELECT STEP: Rank, Pool ({CFG.CANDIDATE_FRACTION}×), Preselect w/ gap filter")
    log.info("=" * 60)

    # Filter validity (paired_ok + bike_detected); GPS requirement optional
    valid: List[Dict] = []
    for r in rows:
        if r.get("paired_ok") != "true":
            continue
        if r.get("bike_detected") != "true":
            continue
        if CFG.REQUIRE_GPS_FOR_SELECTION and r.get("gpx_missing") == "true":
            continue
        valid.append(r)

    if not valid:
        with dst.open("w", newline="") as f:
            csv.writer(f).writerow(["index"])
        log.error("[select] ❌ No valid frames after filtering")
        return dst

    # Sort by ranking signal (descending)
    valid.sort(key=lambda r: _sf(r.get("score_weighted")), reverse=True)

    # Boost high scene-change clips in ranking
    if CFG.SCENE_PRIORITY_MODE:
        for r in valid:
            scene_boost = _sf(r.get("scene_boost"))
            current_score = _sf(r.get("score_weighted"))
            
            # Apply scene priority multiplier
            if scene_boost >= CFG.SCENE_MAJOR_THRESHOLD:
                r["score_weighted"] = f"{current_score * 1.3:.3f}"  # 30% boost
            elif scene_boost >= CFG.SCENE_HIGH_THRESHOLD:
                r["score_weighted"] = f"{current_score * 1.15:.3f}"  # 15% boost
        
        # Re-sort after boosting
        valid.sort(key=lambda r: _sf(r.get("score_weighted")), reverse=True)


    # Targets
    target_clips = int(CFG.HIGHLIGHT_TARGET_DURATION_S // CFG.CLIP_OUT_LEN_S)
    pool_size = min(len(valid), int(target_clips * CFG.CANDIDATE_FRACTION))

    pool = valid[:pool_size]

    # Apply min gap filter to preselection
    preselected = apply_gap_filter(pool, CFG.MIN_GAP_BETWEEN_CLIPS, target_clips)

    # Mark recommendations
    pre_ids = {r["index"] for r in preselected}
    for r in pool:
        r["recommended"] = "true" if r["index"] in pre_ids else "false"

    # Chronological ordering for GUI (after recommendation marking)
    pool.sort(key=lambda r: _sf(r.get("abs_time_epoch")))

    # Write full rows (retain all fields for downstream consumers)
    with dst.open("w", newline="") as f:
        fieldnames = list(pool[0].keys())
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(pool)

    rec_count = sum(1 for r in pool if r.get("recommended") == "true")
    log.info("=" * 60)
    log.info(f"SELECT COMPLETE | Pool: {len(pool)} | Preselected: {rec_count} (gap‑filtered)")
    log.info("=" * 60)
    
    # Extract frames for all candidates in the pool
    extract_frames_for_candidates(pool)
    
    log.info("Ready for manual review")

    return dst


if __name__ == "__main__":
    run()