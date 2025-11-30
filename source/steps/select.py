# source/steps/select.py
"""
Select step:
- Loads enriched.csv (authoritative dataset from Analyze)
- Filters to valid frames (paired_ok, bike_detected, optional GPS)
- Ranks by score_weighted
- Applies gap spacing at the timeslot (moment) level
- Expands selected moments to ALWAYS include both reciprocal clips
- Builds a pool capped at 2× target moments (pairs), with one side marked recommended="true"
- Writes select.csv including full enriched fields + recommended
- Extracts frame images for all candidates to frames directory
- Ensures output is chronological for GUI consumption
"""

from __future__ import annotations
import csv
import subprocess
from pathlib import Path
from typing import List, Dict
from source.utils.progress_reporter import progress_iter

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

    Note: This function expects "representative" rows (one per moment/timeslot),
    each with 'abs_time_epoch' and 'scene_boost' fields present.
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
            # Major scene changes: allow closer spacing
            effective_gap = max(1, min_gap_s // 2)
        elif scene_boost >= HIGH_SCENE_THRESHOLD:
            # Significant scene changes: allow moderately closer spacing
            effective_gap = max(1, int(min_gap_s * 0.75))
        else:
            # Normal clips: use full gap
            effective_gap = max(1, min_gap_s)
        
        window = t // effective_gap
        
        if window not in used_windows:
            filtered.append(c)
            # Block ±1 window to maintain minimum spacing around each selection
            for offset in range(-1, 2):
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
    
    for candidate in progress_iter(pool, desc="[select] Extracting frames", unit="frame"):
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


def _timeslot_key(abs_time_epoch: str) -> int:
    """Bucket absolute time into timeslots aligned to CLIP_OUT_LEN_S."""
    t = int(_sf(abs_time_epoch))
    # Avoid division by zero; CLIP_OUT_LEN_S is config-defined > 0 in normal operation
    slot_len = max(1, int(CFG.CLIP_OUT_LEN_S))
    return t // slot_len


def run() -> Path:
    """Select top candidates, apply timeslot gap filter, expand to reciprocal pairs, and output."""
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
    log.info(f"SELECT STEP: Rank by score, Timeslot gap filter, Expand to reciprocal pairs")
    log.info("=" * 60)

    # Build an index over all enriched rows (authoritative)
    index_all: Dict[str, Dict] = {r.get("index", ""): r for r in rows if r.get("index")}

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

    # Optional scene priority boost, then re-sort
    if CFG.SCENE_PRIORITY_MODE:
        for r in valid:
            scene_boost = _sf(r.get("scene_boost"))
            current_score = _sf(r.get("score_weighted"))
            if scene_boost >= CFG.SCENE_MAJOR_THRESHOLD:
                r["score_weighted"] = f"{current_score * 1.3:.3f}"  # 30% boost
            elif scene_boost >= CFG.SCENE_HIGH_THRESHOLD:
                r["score_weighted"] = f"{current_score * 1.15:.3f}"  # 15% boost
        valid.sort(key=lambda r: _sf(r.get("score_weighted")), reverse=True)

    # Group valid rows into timeslots, pick representative (best score) per slot
    timeslot_map: Dict[int, List[Dict]] = {}
    for r in valid:
        slot = _timeslot_key(r.get("abs_time_epoch"))
        timeslot_map.setdefault(slot, []).append(r)

    representatives: List[Dict] = []
    for slot, rows_in_slot in timeslot_map.items():
        # Pick the highest 'score_weighted' row as the representative of the moment
        best = max(rows_in_slot, key=lambda r: _sf(r.get("score_weighted")))
        # Attach slot for later expansion
        best["_slot_key"] = slot
        representatives.append(best)

    # Determine pool size based on timeslot representatives
    target_clips = int(CFG.HIGHLIGHT_TARGET_DURATION_S // CFG.CLIP_OUT_LEN_S)
    pool_slots = min(len(representatives), int(target_clips * CFG.CANDIDATE_FRACTION))

    # Take top representatives into the candidate pool (pre-gap-filter)
    reps_pool = representatives[:pool_slots]

    # Apply min gap filter across timeslot representatives
    preselected_reps = apply_gap_filter(reps_pool, CFG.MIN_GAP_BETWEEN_CLIPS, target_clips)

    # Expand each selected representative into BOTH reciprocal rows
    final_pool: List[Dict] = []
    for rep in preselected_reps:
        slot = rep["_slot_key"]
        rows_in_slot = timeslot_map.get(slot, [])
        partner_idx = rep.get("partner_index", "")
        partner_row = None

        # Prefer partner from the same timeslot group if present
        if partner_idx:
            for r in rows_in_slot:
                if r.get("index") == partner_idx:
                    partner_row = r
                    break

            # Fallback to authoritative full index (enriched) if needed
            if partner_row is None:
                partner_row = index_all.get(partner_idx)

        # Mark recommendation flags: representative TRUE, partner FALSE
        rep["recommended"] = "true"
        final_pool.append(rep)

        if partner_row:
            # Ensure partner row has consistent types/fields; copy to avoid mutating index_all
            partner_copy = dict(partner_row)
            partner_copy["recommended"] = "false"
            final_pool.append(partner_copy)
        else:
            log.warning(f"[select] Missing partner row for representative {rep.get('index')} -> {partner_idx}")

    # Chronological ordering for GUI (after recommendation marking)
    final_pool.sort(key=lambda r: _sf(r.get("abs_time_epoch")))

    # Write full rows (retain all fields for downstream consumers)
    with dst.open("w", newline="") as f:
        fieldnames = list(final_pool[0].keys())
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(final_pool)

    # Count recommended (one per selected moment)
    rec_count = sum(1 for r in final_pool if r.get("recommended") == "true")
    log.info("=" * 60)
    log.info(f"SELECT COMPLETE | Moments: {len(preselected_reps)} | Pool rows: {len(final_pool)} | Preselected: {rec_count} (gap‑filtered)")
    log.info("=" * 60)
    
    # Extract frames for all candidates in the pool
    extract_frames_for_candidates(final_pool)
    
    log.info("Ready for manual review")

    return dst


if __name__ == "__main__":
    run()
