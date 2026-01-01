# source/steps/select.py
"""
Clip selection step - MOMENT-BASED APPROACH

Works with per-frame data from enriched.csv.
Each moment_id = 1 real-world moment with 2 perspectives (both cameras).
Only one perspective per moment can be recommended.

Pipeline:

1. Load enriched.csv rows (already analyzed and scored).
2. Group rows by moment_id into canonical moments (Fly12/Fly6).
3. For each moment, compute:
   - score_fly12, score_fly6
   - best_score = max(score_fly12, score_fly6)
   - scene_boost_max = max(scene_boosts)
4. Build a candidate pool:
   - Compute target_clips from HIGHLIGHT_TARGET_DURATION_S / CLIP_OUT_LEN_S
   - pool_size = target_clips * CANDIDATE_FRACTION
   - Group moments by clip_num and select top K per clip,
     where K is proportional: ceil(pool_size / num_clips).
5. Apply gap filtering over the candidate pool using moment_epoch and scene_boost_max.
6. For each accepted moment, choose the best perspective (higher score_weighted).
7. Emit select.csv with two rows per candidate-pool moment, at most one recommended="true".
8. Extract JPGs for all candidate-pool rows for manual review.
"""

from __future__ import annotations
from typing import List, Dict, Tuple
from pathlib import Path
import csv
import math

from ..io_paths import enrich_path, select_path, frames_dir, _mk
from ..utils.log import setup_logger
from ..utils.common import safe_float as _sf, read_csv as _load_csv
from ..config import DEFAULT_CONFIG as CFG

log = setup_logger("steps.select")


def _write_csv(path: Path, rows: List[Dict]):
    if not rows:
        return
    with path.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
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


# -----------------------------
# Moment-centric helpers
# -----------------------------

def _group_rows_by_moment(rows: List[Dict]) -> List[Dict]:
    """
    Group enriched rows into canonical moments by moment_id.

    Each moment dict contains:
        {
            "moment_id": int,
            "moment_epoch": float,
            "fly12": Dict,
            "fly6": Dict,
            "clip_num": int,
            "score_fly12": float,
            "score_fly6": float,
            "best_score": float,
            "scene_boost_max": float,
        }

    Moments missing one perspective are dropped.
    """
    by_moment: Dict[str, List[Dict]] = {}
    for r in rows:
        mid = r.get("moment_id")
        if mid is None or mid == "":
            continue
        by_moment.setdefault(str(mid), []).append(r)

    moments: List[Dict] = []
    dropped = 0

    for mid, group in by_moment.items():
        # Expect at most one row per camera per moment
        fly12_row = None
        fly6_row = None
        for r in group:
            cam = r.get("camera", "")
            if cam == "Fly12Sport":
                fly12_row = r
            elif cam == "Fly6Pro":
                fly6_row = r

        if not fly12_row or not fly6_row:
            dropped += 1
            continue

        # Use the earlier abs_time_epoch as canonical moment_epoch
        t12 = _sf(fly12_row.get("abs_time_epoch"))
        t6 = _sf(fly6_row.get("abs_time_epoch"))
        moment_epoch = min(t12, t6)

        # clip_num: we trust they are aligned; fall back sensibly if not
        try:
            clip_num_12 = int(fly12_row.get("clip_num", "0"))
        except Exception:
            clip_num_12 = 0
        try:
            clip_num_6 = int(fly6_row.get("clip_num", "0"))
        except Exception:
            clip_num_6 = 0
        clip_num = clip_num_12 if clip_num_12 == clip_num_6 else min(clip_num_12, clip_num_6)

        score_fly12 = _sf(fly12_row.get("score_weighted"))
        score_fly6 = _sf(fly6_row.get("score_weighted"))
        best_score = max(score_fly12, score_fly6)

        scene12 = _sf(fly12_row.get("scene_boost"))
        scene6 = _sf(fly6_row.get("scene_boost"))
        scene_boost_max = max(scene12, scene6)

        moments.append({
            "moment_id": int(mid),
            "moment_epoch": moment_epoch,
            "fly12": fly12_row,
            "fly6": fly6_row,
            "clip_num": clip_num,
            "score_fly12": score_fly12,
            "score_fly6": score_fly6,
            "best_score": best_score,
            "scene_boost_max": scene_boost_max,
        })

    moments.sort(key=lambda m: m["moment_epoch"])

    log.info("")
    log.info("=" * 60)
    log.info("MOMENT BUILDING")
    log.info("=" * 60)
    log.info(f"Total enriched rows: {len(rows)}")
    log.info(f"Moments built: {len(moments)}")
    log.info(f"Moments dropped (missing perspective): {dropped}")
    return moments


def _build_candidate_pool(moments: List[Dict], target_clips: int) -> List[Dict]:
    """
    Build candidate pool per raw clip, proportional to number of clips.

    Steps:
        1. Compute pool_size = target_clips * CANDIDATE_FRACTION.
        2. Group moments by clip_num.
        3. For each clip, take top K moments by best_score, where:
               K = ceil(pool_size / number_of_clips)
        4. Combine all clip winners into a pool.
        5. If pool is larger than pool_size, trim globally by best_score.
    """
    if not moments or target_clips <= 0:
        return []

    pool_size = max(1, int(target_clips * CFG.CANDIDATE_FRACTION))

    # Group moments by clip_num
    by_clip: Dict[int, List[Dict]] = {}
    for m in moments:
        by_clip.setdefault(m["clip_num"], []).append(m)

    num_clips = len(by_clip)
    if num_clips == 0:
        return []

    k_per_clip = max(1, int(math.ceil(pool_size / float(num_clips))))

    log.info("")
    log.info("=" * 60)
    log.info("CANDIDATE POOL SELECTION (PER CLIP)")
    log.info("=" * 60)
    log.info(f"Target clips: {target_clips}")
    log.info(f"Candidate fraction: {CFG.CANDIDATE_FRACTION:.2f}x")
    log.info(f"Desired pool_size: {pool_size} moments")
    log.info(f"Number of clips: {num_clips}")
    log.info(f"Moments per clip (K_per_clip): {k_per_clip}")

    pool: List[Dict] = []
    for clip_num, clip_moments in sorted(by_clip.items()):
        clip_moments_sorted = sorted(clip_moments, key=lambda m: m["best_score"], reverse=True)
        selected_for_clip = clip_moments_sorted[:k_per_clip]
        pool.extend(selected_for_clip)

        scores = [m["best_score"] for m in selected_for_clip]
        if scores:
            log.info(
                f"  Clip {clip_num:04d}: selected {len(selected_for_clip)} "
                f"moments (best={max(scores):.3f}, worst={min(scores):.3f})"
            )
        else:
            log.info(f"  Clip {clip_num:04d}: no moments selected")

    # If pool is larger than requested pool_size, trim globally by best_score
    if len(pool) > pool_size:
        pool_sorted = sorted(pool, key=lambda m: m["best_score"], reverse=True)
        cutoff_score = pool_sorted[pool_size - 1]["best_score"]
        pool = [m for m in pool_sorted if m["best_score"] >= cutoff_score]
        log.info(
            f"Trimmed pool from {len(pool_sorted)} to {len(pool)} using cutoff score {cutoff_score:.3f}"
        )
    else:
        cutoff_score = min((m["best_score"] for m in pool), default=0.0)

    log.info(f"Final candidate pool size: {len(pool)} moments")
    log.info(f"Candidate pool cutoff score: {cutoff_score:.3f}")
    return sorted(pool, key=lambda m: m["best_score"], reverse=True)


def _apply_gap_filter(moments: List[Dict], target_clips: int) -> List[Dict]:
    """
    Apply gap filtering to moments based on moment_epoch and scene_boost_max.

    Uses similar logic to the previous pair-based implementation, but operates
    at the moment level instead of pair level.
    """
    log.info("")
    log.info("=" * 60)
    log.info("GAP FILTERING (MOMENT LEVEL)")
    log.info("=" * 60)
    log.info(f"Target: {target_clips} moments")
    log.info(f"Min gap: {CFG.MIN_GAP_BETWEEN_CLIPS}s")
    log.info(f"Scene thresholds: High={CFG.SCENE_HIGH_THRESHOLD}, Major={CFG.SCENE_MAJOR_THRESHOLD}")
    log.info("")

    accepted: List[Dict] = []
    used_windows = set()
    last_time = None

    for i, m in enumerate(moments):
        t = int(m["moment_epoch"])
        time_iso = (
            m["fly12"].get("abs_time_iso", "")
            or m["fly6"].get("abs_time_iso", "")
        )[:19]
        idx1 = m["fly12"]["index"]
        idx2 = m["fly6"]["index"]

        scene_boost = m["scene_boost_max"]

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

        time_since_last = (t - last_time) if last_time is not None else float("inf")

        if window not in used_windows:
            accepted.append(m)
            for offset in range(-1, 2):
                used_windows.add(window + offset)

            log.info(f"✓ ACCEPT [{len(accepted)}/{target_clips}] @ {time_iso}")
            log.info(f"    {idx1} ↔ {idx2}")
            log.info(
                f"    Best score: {m['best_score']:.3f} | Scene: {scene_boost:.3f} ({gap_reason})"
            )
            log.info(f"    Gap: {effective_gap}s | Since last: {time_since_last:.0f}s")
            log.info("")

            last_time = t
        else:
            log.info(f"✗ REJECT [{i+1}] @ {time_iso}")
            log.info(f"    {idx1} ↔ {idx2}")
            log.info(
                f"    Best score: {m['best_score']:.3f} | Scene: {scene_boost:.3f}"
            )
            log.info(
                f"    Reason: Too close to accepted moment (window {window} in use); "
                f"time since last: {time_since_last:.0f}s < {effective_gap}s required"
            )
            log.info("")

        if len(accepted) >= target_clips:
            remaining = len(moments) - i - 1
            if remaining > 0:
                log.info(f"Target reached. Skipping {remaining} remaining moments.")
            break

    return accepted


# -----------------------------
# Main entrypoint
# -----------------------------

def run() -> Path:
    """Main selection step: moment-based selection."""
    log.info("=" * 60)
    log.info("SELECT STEP: Moment-based selection")
    log.info("=" * 60)

    enriched = _load_csv(enrich_path())
    if not enriched:
        log.warning("No enriched frames found.")
        return select_path()

    # Ensure chronological ordering for logs / duration reporting
    enriched.sort(key=lambda r: _sf(r.get("abs_time_epoch")))

    # DO NOT recompute moment_id here.
    # analyze.py already assigns correct moment_id using abs_time_epoch.
    log.info(f"Loaded {len(enriched)} enriched frames")
    log.info("Using moment_id from analyze.py (abs_time_epoch-based)")

    first_time = _sf(enriched[0].get("abs_time_epoch"))
    last_time = _sf(enriched[-1].get("abs_time_epoch"))
    duration_s = max(0.0, last_time - first_time)
    duration_h = duration_s / 3600.0
    log.info(f"Total footage duration: {duration_h:.1f} hours ({duration_s:.0f} seconds)")

    # Build canonical moments from enriched rows
    moments = _group_rows_by_moment(enriched)
    if not moments:
        log.error("No valid moments found (missing paired perspectives).")
        return select_path()

    # Selection targets
    target_clips = int(CFG.HIGHLIGHT_TARGET_DURATION_S // CFG.CLIP_OUT_LEN_S)
    if target_clips <= 0:
        log.warning("Non-positive target_clips; nothing to select.")
        return select_path()

    # Candidate pool per clip, proportional
    candidate_moments = _build_candidate_pool(moments, target_clips)
    if not candidate_moments:
        log.error("No candidate moments could be built.")
        return select_path()

    # Log top scoring candidate moments
    log.info("")
    log.info("=" * 60)
    log.info("TOP SCORING CANDIDATE MOMENTS")
    log.info("=" * 60)
    for i, m in enumerate(candidate_moments[:20], 1):
        t_iso = (
            m["fly12"].get("abs_time_iso", "")
            or m["fly6"].get("abs_time_iso", "")
        )[:19]
        log.info(f"{i:2d}. Score {m['best_score']:.3f} @ {t_iso}")
        log.info(f"    {m['fly12']['index']} ↔ {m['fly6']['index']}")
        log.info(
            f"    Fly12: {m['score_fly12']:.3f} | Fly6: {m['score_fly6']:.3f} | "
            f"Scene: {m['scene_boost_max']:.3f}"
        )

    # Gap filtering on candidate pool
    recommended_moments = _apply_gap_filter(candidate_moments, target_clips)

    log.info("")
    log.info("=" * 60)
    log.info("PERSPECTIVE SELECTION PER MOMENT")
    log.info("=" * 60)
    log.info("Choosing best perspective for each recommended moment...")

    recommended_indices = set()
    for m in recommended_moments:
        score12 = m["score_fly12"]
        score6 = m["score_fly6"]

        if score12 >= score6:
            chosen = m["fly12"]
            other = m["fly6"]
            chosen_score = score12
            other_score = score6
        else:
            chosen = m["fly6"]
            other = m["fly12"]
            chosen_score = score6
            other_score = score12

        recommended_indices.add(chosen["index"])

        time_iso = (chosen.get("abs_time_iso", "") or other.get("abs_time_iso", ""))[:19]
        log.info(f"✓ {time_iso}: {chosen['index']} (score {chosen_score:.3f})")
        log.info(
            f"  Chosen: {chosen.get('camera')} - score={chosen_score:.3f} | "
            f"Other: {other.get('camera')} - score={other_score:.3f}"
        )

    # Build output rows: all rows from candidate pool, with recommended flags
    output_rows: List[Dict] = []
    for m in candidate_moments:
        for row in (m["fly12"], m["fly6"]):
            row = dict(row)  # avoid mutating original enriched row list
            row["recommended"] = "true" if row["index"] in recommended_indices else "false"
            output_rows.append(row)

    # Sort by aligned world time
    output_rows.sort(key=lambda r: _sf(r.get("abs_time_epoch")))

    # Write select.csv with all fields present in enriched rows
    _write_csv(select_path(), output_rows)

    log.info("")
    log.info("=" * 60)
    log.info("SELECT COMPLETE")
    log.info("=" * 60)
    log.info(f"Total frames analyzed: {len(enriched)}")
    log.info(f"Moments built: {len(moments)}")
    log.info(f"Candidate pool: {len(candidate_moments)} moments ({len(candidate_moments) * 2} rows)")
    log.info(f"Recommended: {len(recommended_moments)} moments ({len(recommended_indices)} clips)")
    log.info(f"Target: {target_clips}")
    if target_clips > 0:
        log.info(f"Pool ratio: {len(candidate_moments) / target_clips:.1f}x")
    log.info("=" * 60)

    extract_frame_images(output_rows)
    log.info("Ready for manual review")

    return select_path()

