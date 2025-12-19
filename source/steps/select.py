# source/steps/select.py
"""
Clip selection step - PAIR-BASED APPROACH
Works with pre-paired data from enriched.csv.
Each pair = 1 moment with 2 perspectives (both cameras).
Only one perspective per moment can be recommended.
"""

from __future__ import annotations
from typing import List, Dict, Tuple
from pathlib import Path
import csv

from ..io_paths import enrich_path, select_path, frames_dir, _mk
from ..utils.log import setup_logger
from .analyze_helpers.score_calculator import ScoreCalculator
from ..config import DEFAULT_CONFIG as CFG

log = setup_logger("steps.select")


def _sf(v, d=0.0) -> float:
    """Safe float conversion with default."""
    try:
        return float(v) if v not in ("", None) else d
    except Exception:
        return d


def build_pairs(rows: List[Dict]) -> List[Tuple[Dict, Dict]]:
    """
    Build pairs from enriched rows using partner_index relationships.
    Returns list of (row1, row2) tuples representing moments.
    """
    index_map = {r["index"]: r for r in rows}
    pairs = []
    seen = set()
    
    for row in rows:
        idx = row["index"]
        if idx in seen:
            continue
        
        partner_idx = row.get("partner_index", "")
        if not partner_idx or partner_idx not in index_map:
            log.warning(f"Row {idx} has invalid partner_index: {partner_idx}")
            continue
        
        partner = index_map[partner_idx]
        
        # Verify reciprocal relationship
        if partner.get("partner_index") != idx:
            log.warning(f"Non-reciprocal pair: {idx} -> {partner_idx}")
            continue
        
        # Verify different cameras
        if row.get("camera") == partner.get("camera"):
            log.warning(f"Same camera pair: {idx}")
            continue
        
        seen.add(idx)
        seen.add(partner_idx)
        pairs.append((row, partner))
    
    log.info(f"Built {len(pairs)} valid pairs from {len(rows)} rows ({len(seen)} paired, {len(rows)-len(seen)} unpaired)")
    return pairs


def score_pair(pair: Tuple[Dict, Dict]) -> float:
    """Score a pair by taking the maximum score of the two perspectives."""
    score1 = _sf(pair[0].get("score_weighted"))
    score2 = _sf(pair[1].get("score_weighted"))
    return max(score1, score2)


def apply_gap_filter(pairs: List[Tuple[Dict, Dict]], target_clips: int) -> List[Tuple[Dict, Dict]]:
    """
    Select top pairs with adaptive spacing based on scene_boost.
    """
    filtered = []
    used_windows = set()

    for pair in pairs:
        t = int(_sf(pair[0].get("abs_time_epoch")))
        scene_boost = max(_sf(pair[0].get("scene_boost", 0)), _sf(pair[1].get("scene_boost", 0)))

        effective_gap = CFG.MIN_GAP_BETWEEN_CLIPS
        if scene_boost >= CFG.SCENE_MAJOR_THRESHOLD:
            effective_gap *= CFG.SCENE_MAJOR_GAP_MULTIPLIER
        elif scene_boost >= CFG.SCENE_HIGH_THRESHOLD:
            effective_gap *= CFG.SCENE_HIGH_GAP_MULTIPLIER

        effective_gap = max(1, int(effective_gap))
        window = t // effective_gap

        if window not in used_windows:
            filtered.append(pair)
            for offset in range(-1, 2):
                used_windows.add(window + offset)

        if len(filtered) >= target_clips:
            break

    return filtered


def _load_csv(path: Path) -> List[Dict]:
    if not path.exists():
        return []
    with path.open() as f:
        return list(csv.DictReader(f))


def _write_csv(path: Path, rows: List[Dict]):
    if not rows:
        return
    with path.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=rows[0].keys())
        writer.writeheader()
        writer.writerows(rows)


def extract_frame_images(rows: List[Dict]) -> int:
    """Extract frame images from videos for manual review."""
    from ..io_paths import frames_dir, _mk
    import cv2
    
    frames_dir_path = _mk(frames_dir())
    extracted_count = 0
    
    log.info(f"Extracting {len(rows)} frame images for manual review...")
    
    for row in rows:
        index = row["index"]
        video_path = Path(row["video_path"])
        frame_number = int(float(row["frame_number"]))
        
        primary_out = frames_dir_path / f"{index}_Primary.jpg"
        if primary_out.exists():
            continue
        
        try:
            cap = cv2.VideoCapture(str(video_path))
            cap.set(cv2.CAP_PROP_POS_FRAMES, frame_number)
            ret, frame = cap.read()
            cap.release()
            
            if ret and frame is not None:
                cv2.imwrite(str(primary_out), frame)
                extracted_count += 1
            else:
                log.warning(f"Failed to extract frame {frame_number} from {video_path.name}")
        except Exception as e:
            log.error(f"Error extracting {index}: {e}")
    
    log.info(f"Extracted {extracted_count} new frame images to {frames_dir_path}")
    return extracted_count


def run() -> Path:
    """Main selection step: work with pairs from the start."""
    log.info("=" * 60)
    log.info("SELECT STEP: Pair-based selection")
    log.info("=" * 60)
    
    enriched = _load_csv(enrich_path())
    if not enriched:
        log.warning("No enriched frames found.")
        return select_path()

    calc = ScoreCalculator()
    scored = calc.compute_scores(enriched)
    all_pairs = build_pairs(scored)
    
    if not all_pairs:
        log.error("No valid pairs found in enriched data")
        return select_path()
    
    pairs_with_scores = [(pair, score_pair(pair)) for pair in all_pairs]
    pairs_sorted = sorted(pairs_with_scores, key=lambda x: x[1], reverse=True)
    
    target_clips = int(CFG.HIGHLIGHT_TARGET_DURATION_S // CFG.CLIP_OUT_LEN_S)
    pool_size = int(target_clips * CFG.CANDIDATE_FRACTION)
    
    log.info(f"Target clips: {target_clips}")
    log.info(f"Candidate pool size: {pool_size} moments (×2 = {pool_size*2} rows)")
    
    candidate_pairs = [pair for pair, score in pairs_sorted[:pool_size]]
    recommended_pairs = apply_gap_filter(candidate_pairs, target_clips)
    log.info(f"Gap-filtered to {len(recommended_pairs)} recommended moments")
    
    # Only one perspective per recommended moment
    recommended_indices = set()
    for pair in recommended_pairs:
        score1 = _sf(pair[0].get("score_weighted"))
        score2 = _sf(pair[1].get("score_weighted"))
        chosen = pair[0] if score1 >= score2 else pair[1]
        recommended_indices.add(chosen["index"])
    
    output_rows = []
    for pair in candidate_pairs:
        for row in pair:
            row["recommended"] = "true" if row["index"] in recommended_indices else "false"
            output_rows.append(row)
    
    output_rows.sort(key=lambda r: _sf(r.get("abs_time_epoch")))
    _write_csv(select_path(), output_rows)
    
    log.info("=" * 60)
    log.info("SELECT COMPLETE")
    log.info(f"Pool: {len(candidate_pairs)} moments ({len(output_rows)} rows)")
    log.info(f"Recommended: {len(recommended_pairs)} moments")
    log.info(f"Target: {target_clips}")
    log.info(f"Pool ratio: {len(candidate_pairs)/target_clips:.1f}x")
    log.info("=" * 60)
    
    extract_frame_images(output_rows)
    log.info("Ready for manual review")

    return select_path()
