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
- Extracts frame images for all candidates to frames directory using actual video metadata
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
from ..utils.temp_files import register_temp_file

log = setup_logger("steps.select")


def _sf(v, d=0.0) -> float:
    """Safe float conversion with default."""
    try:
        return float(v) if v not in ("", None) else d
    except Exception:
        return d


def apply_gap_filter(candidates: List[Dict], min_gap_s: int, target_clips: int) -> List[Dict]:
    """
    Select top clips with adaptive spacing based on scene boost.
    High scene-change clips get priority and can be closer together.
    
    Args:
        candidates: List of candidate clip dictionaries
        min_gap_s: Minimum gap between clips in seconds
        target_clips: Target number of clips to select
    
    Returns:
        Filtered list of selected clips
    """
    filtered: List[Dict] = []
    used_windows = set()
    
    # Scene change thresholds from config
    HIGH_SCENE_THRESHOLD = getattr(CFG, 'SCENE_HIGH_THRESHOLD', 0.50)
    MAJOR_SCENE_THRESHOLD = getattr(CFG, 'SCENE_MAJOR_THRESHOLD', 0.70)
    
    for c in candidates:
        t = int(_sf(c.get("abs_time_epoch")))
        scene_boost = _sf(c.get("scene_boost", 0))
        
        # Adaptive gap based on scene significance
        if scene_boost >= MAJOR_SCENE_THRESHOLD:
            effective_gap = max(1, min_gap_s // 2)
        elif scene_boost >= HIGH_SCENE_THRESHOLD:
            effective_gap = max(1, int(min_gap_s * 0.75))
        else:
            effective_gap = max(1, min_gap_s)
        
        window = t // effective_gap
        
        if window not in used_windows:
            filtered.append(c)
            # Block adjacent windows
            for offset in range(-1, 2):
                used_windows.add(window + offset)
        
        if len(filtered) >= target_clips:
            break
    
    return filtered


def extract_frames_for_candidates(pool: List[Dict]) -> None:
    """
    Extract frame images for all candidate clips to frames directory.
    Uses accurate timing from CSV metadata instead of hardcoded FPS.
    
    Args:
        pool: List of candidate clip dictionaries with video metadata
    """
    if not pool:
        return
    
    log.info(f"Extracting {len(pool)} frame images for manual review...")
    frames_path = _mk(frames_dir())
    extraction_count = 0
    
    for candidate in progress_iter(pool, desc="[select] Extracting frames", unit="frame"):
        try:
            idx = candidate.get("index", "")
            source_file = candidate.get("source", "")
            
            # Use accurate frame timing from metadata
            session_ts_s = candidate.get("session_ts_s", "")
            
            if not idx or not source_file or not session_ts_s:
                log.warning(f"Missing metadata for candidate: {idx}")
                continue
            
            # Skip if already extracted
            output_path = frames_path / f"{idx}_Primary.jpg"
            if output_path.exists():
                continue
            
            video_path = CFG.INPUT_VIDEOS_DIR / source_file
            if not video_path.exists():
                log.warning(f"Video not found: {source_file}")
                continue
            
            # Use session timestamp from CSV (accurate)
            timestamp = float(session_ts_s)
            
            # Extract primary frame
            cmd = [
                "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
                "-ss", f"{timestamp:.3f}",
                "-i", str(video_path),
                "-frames:v", "1",
                "-q:v", "2",
                str(output_path)
            ]
            
            result = subprocess.run(cmd, capture_output=True)
            if result.returncode != 0:
                log.warning(f"FFmpeg error for {idx}: {result.stderr.decode()}")
                continue
            
            extraction_count += 1
            
            # Extract partner frame if available
            partner_source = candidate.get("partner_source", "")
            partner_video_path = candidate.get("partner_video_path", "")
            
            if partner_source and partner_video_path:
                partner_video = Path(partner_video_path)
                partner_output = frames_path / f"{idx}_Partner.jpg"
                
                if partner_video.exists() and not partner_output.exists():
                    # Use partner's session timestamp
                    # Look up partner's metadata from enriched data if available
                    # For now, use same timestamp (cameras are synchronized)
                    partner_cmd = [
                        "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
                        "-ss", f"{timestamp:.3f}",
                        "-i", str(partner_video),
                        "-frames:v", "1",
                        "-q:v", "2",
                        str(partner_output)
                    ]
                    subprocess.run(partner_cmd, capture_output=True)
        
        except Exception as e:
            log.warning(f"Failed to extract frame {idx}: {e}")
    
    log.info(f"Extracted {extraction_count} new frame images to {frames_path}")


def _timeslot_key(abs_time_epoch: str) -> int:
    """
    Bucket absolute time into timeslots aligned to CLIP_OUT_LEN_S.
    
    Args:
        abs_time_epoch: Timestamp string from CSV
    
    Returns:
        Integer timeslot bucket
    """
    t = int(_sf(abs_time_epoch))
    slot_len = max(1, int(CFG.CLIP_OUT_LEN_S))
    return t // slot_len


def _clean_internal_fields(row: Dict) -> Dict:
    """
    Remove internal fields that shouldn't be written to CSV.
    
    Args:
        row: Dictionary with potential internal fields
    
    Returns:
        Cleaned dictionary
    """
    return {k: v for k, v in row.items() if not k.startswith('_')}


def run() -> Path:
    """
    Main selection pipeline.
    
    Process:
    1. Load enriched.csv
    2. Filter to valid frames (detection + pairing)
    3. Apply scene boost if enabled
    4. Group by timeslot and select best per slot
    5. Apply gap filtering
    6. Expand to reciprocal pairs
    7. Extract frame images
    8. Write select.csv
    
    Returns:
        Path to select.csv output file
    """
    src = enrich_path()
    dst = _mk(select_path())
    
    # Validate input
    if not src.exists():
        with dst.open("w", newline="") as f:
            csv.writer(f).writerow(["index"])
        log.error("[select] ❌ enriched.csv missing")
        return dst
    
    # Load enriched data
    try:
        with src.open() as f:
            rows = list(csv.DictReader(f))
    except Exception as e:
        log.error(f"[select] Failed to load enriched.csv: {e}")
        with dst.open("w", newline="") as f:
            csv.writer(f).writerow(["index"])
        return dst
    
    if not rows:
        with dst.open("w", newline="") as f:
            csv.writer(f).writerow(["index"])
        log.error("[select] ❌ enriched.csv is empty")
        return dst
    
    log.info("=" * 60)
    log.info("SELECT STEP: Rank by score, Timeslot gap filter, Expand to reciprocal pairs")
    log.info("=" * 60)
    
    # Build index for partner lookup
    index_all: Dict[str, Dict] = {r.get("index", ""): r for r in rows if r.get("index")}
    
    # Filter to valid frames
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
    
    # Sort by weighted score
    valid.sort(key=lambda r: _sf(r.get("score_weighted")), reverse=True)
    
    # Apply scene boost if enabled
    if CFG.SCENE_PRIORITY_MODE:
        HIGH_THRESHOLD = getattr(CFG, 'SCENE_HIGH_THRESHOLD', 0.50)
        MAJOR_THRESHOLD = getattr(CFG, 'SCENE_MAJOR_THRESHOLD', 0.70)
        
        for r in valid:
            scene_boost = _sf(r.get("scene_boost"))
            current_score = _sf(r.get("score_weighted"))
            
            if scene_boost >= MAJOR_THRESHOLD:
                r["score_weighted"] = f"{current_score * 1.3:.3f}"
            elif scene_boost >= HIGH_THRESHOLD:
                r["score_weighted"] = f"{current_score * 1.15:.3f}"
        
        # Re-sort after boost
        valid.sort(key=lambda r: _sf(r.get("score_weighted")), reverse=True)
    
    # Group by timeslot
    timeslot_map: Dict[int, List[Dict]] = {}
    for r in valid:
        slot = _timeslot_key(r.get("abs_time_epoch"))
        timeslot_map.setdefault(slot, []).append(r)
    
    # Select best representative per timeslot
    representatives: List[Dict] = []
    for slot, rows_in_slot in timeslot_map.items():
        best = max(rows_in_slot, key=lambda r: _sf(r.get("score_weighted")))
        best["_slot_key"] = slot
        representatives.append(best)
    
    # Calculate candidate pool size
    target_clips = int(CFG.HIGHLIGHT_TARGET_DURATION_S // CFG.CLIP_OUT_LEN_S)
    candidate_fraction = getattr(CFG, 'CANDIDATE_FRACTION', 2.0)
    pool_slots = min(len(representatives), int(target_clips * candidate_fraction))
    reps_pool = representatives[:pool_slots]
    
    # Apply gap filtering
    preselected_reps = apply_gap_filter(reps_pool, CFG.MIN_GAP_BETWEEN_CLIPS, target_clips)
    
    # Expand to reciprocal pairs
    final_pool: List[Dict] = []
    for rep in preselected_reps:
        slot = rep["_slot_key"]
        rows_in_slot = timeslot_map.get(slot, [])
        partner_idx = rep.get("partner_index", "")
        partner_row = None
        
        # Find partner in same timeslot
        if partner_idx:
            for r in rows_in_slot:
                epoch_diff = abs(_sf(r.get("abs_time_epoch")) - _sf(rep.get("abs_time_epoch")))
                if r.get("index") == partner_idx and epoch_diff <= CFG.PARTNER_TIME_TOLERANCE_S:
                    partner_row = r
                    break
            
            # Fall back to index lookup if not in slot
            if partner_row is None:
                candidate = index_all.get(partner_idx)
                if candidate:
                    epoch_diff = abs(_sf(candidate.get("abs_time_epoch")) - _sf(rep.get("abs_time_epoch")))
                    if epoch_diff <= CFG.PARTNER_TIME_TOLERANCE_S:
                        partner_row = candidate
        
        # Add representative (pre-selected)
        rep["recommended"] = "true"
        final_pool.append(rep)
        
        # Add partner (not pre-selected)
        if partner_row:
            partner_copy = dict(partner_row)
            partner_copy["recommended"] = "false"
            final_pool.append(partner_copy)
        else:
            log.warning(
                f"[select] Missing partner row for representative {rep.get('index')} "
                f"(expected partner {partner_idx})"
            )
    
    # Sort chronologically for GUI
    final_pool.sort(key=lambda r: _sf(r.get("abs_time_epoch")))
    
    # Clean internal fields
    final_pool_cleaned = [_clean_internal_fields(row) for row in final_pool]
    
    # Write select.csv
    if final_pool_cleaned:
        fieldnames = sorted({k for row in final_pool_cleaned for k in row.keys()})
        with dst.open("w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(final_pool_cleaned)
    
    rec_count = sum(1 for r in final_pool if r.get("recommended") == "true")
    log.info("=" * 60)
    log.info(
        f"SELECT COMPLETE | Moments: {len(preselected_reps)} | "
        f"Pool rows: {len(final_pool)} | Preselected: {rec_count} (gap‑filtered)"
    )
    log.info("=" * 60)
    
    # Extract frames for all candidates
    extract_frames_for_candidates(final_pool)
    log.info("Ready for manual review")
    
    return dst


if __name__ == "__main__":
    run()