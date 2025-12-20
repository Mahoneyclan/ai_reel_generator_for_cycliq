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


def build_pairs(rows: List[Dict]) -> Tuple[List[Tuple[Dict, Dict]], Dict[str, str]]:
    """
    Build pairs from enriched rows using partner_index relationships.
    Returns (pairs, rejection_reasons).
    """
    index_map = {r["index"]: r for r in rows}
    pairs = []
    seen = set()
    rejections = {}
    
    log.info("")
    log.info("=" * 60)
    log.info("PAIR BUILDING")
    log.info("=" * 60)
    
    for row in rows:
        idx = row["index"]
        if idx in seen:
            continue
        
        partner_idx = row.get("partner_index", "")
        if not partner_idx:
            rejections[idx] = "No partner_index"
            continue
            
        if partner_idx not in index_map:
            rejections[idx] = f"Partner not found: {partner_idx}"
            continue
        
        partner = index_map[partner_idx]
        
        # Verify reciprocal relationship
        if partner.get("partner_index") != idx:
            rejections[idx] = f"Non-reciprocal: {idx} -> {partner_idx} -> {partner.get('partner_index')}"
            continue
        
        # Verify different cameras
        if row.get("camera") == partner.get("camera"):
            rejections[idx] = f"Same camera: {row.get('camera')}"
            continue
        
        seen.add(idx)
        seen.add(partner_idx)
        pairs.append((row, partner))
        
        # Log successful pair
        time1 = row.get("abs_time_iso", "")[:19] if row.get("abs_time_iso") else "?"
        time2 = partner.get("abs_time_iso", "")[:19] if partner.get("abs_time_iso") else "?"
        log.info(f"✓ Pair: {idx} ({row.get('camera')}) ↔ {partner_idx} ({partner.get('camera')}) @ {time1}")
    
    # Log rejection summary
    log.info("")
    log.info(f"Pair Building Summary:")
    log.info(f"  Valid pairs: {len(pairs)}")
    log.info(f"  Paired rows: {len(seen)}")
    log.info(f"  Unpaired rows: {len(rows) - len(seen)}")
    
    if rejections:
        log.info("")
        log.info(f"Rejection reasons ({len(rejections)} frames):")
        rejection_counts = {}
        for reason in rejections.values():
            rejection_counts[reason] = rejection_counts.get(reason, 0) + 1
        for reason, count in sorted(rejection_counts.items(), key=lambda x: -x[1]):
            log.info(f"  • {reason}: {count} frames")
    
    return pairs, rejections


def score_pair(pair: Tuple[Dict, Dict]) -> Tuple[float, Dict]:
    """
    Score a pair by taking the maximum score of the two perspectives.
    Returns (score, details_dict).
    """
    score1 = _sf(pair[0].get("score_weighted"))
    score2 = _sf(pair[1].get("score_weighted"))
    
    details = {
        'cam1': pair[0].get('camera'),
        'score1': score1,
        'composite1': _sf(pair[0].get('score_composite')),
        'detections1': int(_sf(pair[0].get('num_detections'))),
        'speed1': _sf(pair[0].get('speed_kmh')),
        'scene1': _sf(pair[0].get('scene_boost')),
        'cam2': pair[1].get('camera'),
        'score2': score2,
        'composite2': _sf(pair[1].get('score_composite')),
        'detections2': int(_sf(pair[1].get('num_detections'))),
        'speed2': _sf(pair[1].get('speed_kmh')),
        'scene2': _sf(pair[1].get('scene_boost')),
        'max_score': max(score1, score2)
    }
    
    return max(score1, score2), details


def apply_gap_filter(pairs_with_details: List[Tuple[Tuple[Dict, Dict], float, Dict]], 
                     target_clips: int) -> List[Tuple[Dict, Dict]]:
    """
    Select top pairs with adaptive spacing based on scene_boost.
    Returns list of accepted pairs and logs rejections.
    """
    log.info("")
    log.info("=" * 60)
    log.info("GAP FILTERING")
    log.info("=" * 60)
    log.info(f"Target: {target_clips} moments")
    log.info(f"Min gap: {CFG.MIN_GAP_BETWEEN_CLIPS}s")
    log.info(f"Scene thresholds: High={CFG.SCENE_HIGH_THRESHOLD}, Major={CFG.SCENE_MAJOR_THRESHOLD}")
    log.info("")
    
    filtered = []
    used_windows = set()
    last_time = None
    
    for i, (pair, score, details) in enumerate(pairs_with_details):
        t = int(_sf(pair[0].get("abs_time_epoch")))
        time_iso = pair[0].get("abs_time_iso", "")[:19] if pair[0].get("abs_time_iso") else "?"
        idx1 = pair[0]["index"]
        idx2 = pair[1]["index"]
        
        scene_boost = max(_sf(pair[0].get("scene_boost", 0)), _sf(pair[1].get("scene_boost", 0)))
        
        effective_gap = CFG.MIN_GAP_BETWEEN_CLIPS
        gap_reason = "normal"
        if scene_boost >= CFG.SCENE_MAJOR_THRESHOLD:
            effective_gap *= CFG.SCENE_MAJOR_GAP_MULTIPLIER
            gap_reason = "major scene"
        elif scene_boost >= CFG.SCENE_HIGH_THRESHOLD:
            effective_gap *= CFG.SCENE_HIGH_GAP_MULTIPLIER
            gap_reason = "high scene"
        
        effective_gap = max(1, int(effective_gap))
        window = t // effective_gap
        
        # Calculate time since last accepted moment
        time_since_last = (t - last_time) if last_time else float('inf')
        
        if window not in used_windows:
            filtered.append(pair)
            for offset in range(-1, 2):
                used_windows.add(window + offset)
            
            log.info(f"✓ ACCEPT [{len(filtered)}/{target_clips}] @ {time_iso}")
            log.info(f"    {idx1} ↔ {idx2}")
            log.info(f"    Score: {score:.2f} | Scene: {scene_boost:.1f} ({gap_reason})")
            log.info(f"    Gap: {effective_gap}s | Since last: {time_since_last:.0f}s")
            log.info(f"    {details['cam1']}: score={details['score1']:.2f} det={details['detections1']} speed={details['speed1']:.1f}km/h")
            log.info(f"    {details['cam2']}: score={details['score2']:.2f} det={details['detections2']} speed={details['speed2']:.1f}km/h")
            log.info("")
            
            last_time = t
        else:
            log.info(f"✗ REJECT [{i+1}] @ {time_iso}")
            log.info(f"    {idx1} ↔ {idx2}")
            log.info(f"    Score: {score:.2f} | Scene: {scene_boost:.1f}")
            log.info(f"    Reason: Too close to accepted moment (window {window} in use)")
            log.info(f"    Time since last: {time_since_last:.0f}s < {effective_gap}s required")
            log.info("")
        
        if len(filtered) >= target_clips:
            remaining = len(pairs_with_details) - i - 1
            if remaining > 0:
                log.info(f"Target reached. Skipping {remaining} remaining pairs.")
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
    
    log.info(f"Loaded {len(enriched)} enriched frames")
    log.info(f"Time range: {enriched[0].get('abs_time_iso', '?')[:19]} to {enriched[-1].get('abs_time_iso', '?')[:19]}")
    
    # Calculate total footage duration
    first_time = _sf(enriched[0].get('abs_time_epoch'))
    last_time = _sf(enriched[-1].get('abs_time_epoch'))
    duration_s = last_time - first_time
    duration_h = duration_s / 3600
    log.info(f"Total footage duration: {duration_h:.1f} hours ({duration_s:.0f} seconds)")
    
    calc = ScoreCalculator()
    scored = calc.compute_scores(enriched)
    all_pairs, rejections = build_pairs(scored)
    
    if not all_pairs:
        log.error("No valid pairs found in enriched data")
        return select_path()
    
    # Score all pairs with details
    log.info("")
    log.info("=" * 60)
    log.info("SCORING PAIRS")
    log.info("=" * 60)
    
    pairs_with_scores = []
    for pair in all_pairs:
        score, details = score_pair(pair)
        pairs_with_scores.append((pair, score, details))
    
    pairs_sorted = sorted(pairs_with_scores, key=lambda x: x[1], reverse=True)
    
    # Log top 20 scoring pairs
    log.info("Top 20 scoring pairs:")
    for i, (pair, score, details) in enumerate(pairs_sorted[:20], 1):
        time_iso = pair[0].get("abs_time_iso", "")[:19]
        log.info(f"{i:2d}. Score {score:.2f} @ {time_iso}")
        log.info(f"    {pair[0]['index']} ↔ {pair[1]['index']}")
        log.info(f"    {details['cam1']}: {details['score1']:.2f} | {details['cam2']}: {details['score2']:.2f}")
    
    # Log score distribution
    all_scores = [score for _, score, _ in pairs_sorted]
    log.info("")
    log.info("Score distribution:")
    log.info(f"  Max: {max(all_scores):.2f}")
    log.info(f"  75th percentile: {sorted(all_scores)[int(len(all_scores)*0.75)]:.2f}")
    log.info(f"  Median: {sorted(all_scores)[len(all_scores)//2]:.2f}")
    log.info(f"  25th percentile: {sorted(all_scores)[int(len(all_scores)*0.25)]:.2f}")
    log.info(f"  Min: {min(all_scores):.2f}")
    
    target_clips = int(CFG.HIGHLIGHT_TARGET_DURATION_S // CFG.CLIP_OUT_LEN_S)
    pool_size = int(target_clips * CFG.CANDIDATE_FRACTION)
    
    log.info("")
    log.info("=" * 60)
    log.info("CANDIDATE POOL SELECTION")
    log.info("=" * 60)
    log.info(f"Target clips: {target_clips}")
    log.info(f"Pool multiplier: {CFG.CANDIDATE_FRACTION}x")
    log.info(f"Candidate pool size: {pool_size} moments (×2 = {pool_size*2} rows)")
    
    candidate_pairs = pairs_sorted[:pool_size]
    cutoff_score = candidate_pairs[-1][1] if candidate_pairs else 0
    log.info(f"Pool cutoff score: {cutoff_score:.2f}")
    
    # Apply gap filtering
    recommended_pairs = apply_gap_filter(candidate_pairs, target_clips)
    
    log.info("")
    log.info("=" * 60)
    log.info("PERSPECTIVE SELECTION")
    log.info("=" * 60)
    log.info("Choosing best perspective from each recommended pair...")
    
    # Only one perspective per recommended moment
    recommended_indices = set()
    for pair in recommended_pairs:
        score1 = _sf(pair[0].get("score_weighted"))
        score2 = _sf(pair[1].get("score_weighted"))
        chosen = pair[0] if score1 >= score2 else pair[1]
        other = pair[1] if score1 >= score2 else pair[0]
        
        recommended_indices.add(chosen["index"])
        
        time_iso = chosen.get("abs_time_iso", "")[:19]
        log.info(f"✓ {time_iso}: {chosen['index']} (score {score1 if score1 >= score2 else score2:.2f})")
        log.info(f"  Chosen: {chosen.get('camera')} - score={score1 if score1 >= score2 else score2:.2f}")
        log.info(f"  Other:  {other.get('camera')} - score={score2 if score1 >= score2 else score1:.2f}")
    
    output_rows = []
    for pair, _, _ in candidate_pairs:
        for row in pair:
            row["recommended"] = "true" if row["index"] in recommended_indices else "false"
            output_rows.append(row)
    
    output_rows.sort(key=lambda r: _sf(r.get("abs_time_epoch")))
    _write_csv(select_path(), output_rows)
    
    log.info("")
    log.info("=" * 60)
    log.info("SELECT COMPLETE")
    log.info("=" * 60)
    log.info(f"Total frames analyzed: {len(enriched)}")
    log.info(f"Valid pairs: {len(all_pairs)}")
    log.info(f"Candidate pool: {len(candidate_pairs)} moments ({len(candidate_pairs)*2} rows)")
    log.info(f"Recommended: {len(recommended_pairs)} moments ({len(recommended_indices)} clips)")
    log.info(f"Target: {target_clips}")
    log.info(f"Pool ratio: {len(candidate_pairs)/target_clips:.1f}x")
    log.info("=" * 60)
    
    extract_frame_images(output_rows)
    log.info("Ready for manual review")

    return select_path()