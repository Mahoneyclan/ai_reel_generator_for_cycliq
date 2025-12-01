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
    """
    filtered: List[Dict] = []
    used_windows = set()

    HIGH_SCENE_THRESHOLD = 0.50
    MAJOR_SCENE_THRESHOLD = 0.70

    for c in candidates:
        t = int(_sf(c.get("abs_time_epoch")))
        scene_boost = _sf(c.get("scene_boost", 0))

        if scene_boost >= MAJOR_SCENE_THRESHOLD:
            effective_gap = max(1, min_gap_s // 2)
        elif scene_boost >= HIGH_SCENE_THRESHOLD:
            effective_gap = max(1, int(min_gap_s * 0.75))
        else:
            effective_gap = max(1, min_gap_s)

        window = t // effective_gap

        if window not in used_windows:
            filtered.append(c)
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

            output_path = frames_path / f"{idx}_Primary.jpg"
            if output_path.exists():
                continue

            video_path = CFG.INPUT_VIDEOS_DIR / source_file
            if not video_path.exists():
                log.warning(f"[select] Video not found: {source_file}")
                continue

            frame_num = int(frame_number)
            timestamp = frame_num / 30.0

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
                log.warning(f"[select] FFmpeg error for {idx}: {result.stderr.decode()}")
                continue

            extraction_count += 1

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
    slot_len = max(1, int(CFG.CLIP_OUT_LEN_S))
    return t // slot_len


def _clean_internal_fields(row: Dict) -> Dict:
    """Remove internal fields that shouldn't be written to CSV."""
    return {k: v for k, v in row.items() if not k.startswith('_')}


def run() -> Path:
    """Select top candidates, apply gap filter, expand to reciprocal pairs, and output."""
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
    log.info("SELECT STEP: Rank by score, Timeslot gap filter, Expand to reciprocal pairs")
    log.info("=" * 60)

    index_all: Dict[str, Dict] = {r.get("index", ""): r for r in rows if r.get("index")}

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

    valid.sort(key=lambda r: _sf(r.get("score_weighted")), reverse=True)

    if CFG.SCENE_PRIORITY_MODE:
        for r in valid:
            scene_boost = _sf(r.get("scene_boost"))
            current_score = _sf(r.get("score_weighted"))
            if scene_boost >= CFG.SCENE_MAJOR_THRESHOLD:
                r["score_weighted"] = f"{current_score * 1.3:.3f}"
            elif scene_boost >= CFG.SCENE_HIGH_THRESHOLD:
                r["score_weighted"] = f"{current_score * 1.15:.3f}"
        valid.sort(key=lambda r: _sf(r.get("score_weighted")), reverse=True)

    timeslot_map: Dict[int, List[Dict]] = {}
    for r in valid:
        slot = _timeslot_key(r.get("abs_time_epoch"))
        timeslot_map.setdefault(slot, []).append(r)

    representatives: List[Dict] = []
    for slot, rows_in_slot in timeslot_map.items():
        best = max(rows_in_slot, key=lambda r: _sf(r.get("score_weighted")))
        best["_slot_key"] = slot
        representatives.append(best)

    target_clips = int(CFG.HIGHLIGHT_TARGET_DURATION_S // CFG.CLIP_OUT_LEN_S)
    pool_slots = min(len(representatives), int(target_clips * CFG.CANDIDATE_FRACTION))
    reps_pool = representatives[:pool_slots]

    preselected_reps = apply_gap_filter(reps_pool, CFG.MIN_GAP_BETWEEN_CLIPS, target_clips)

    final_pool: List[Dict] = []
    for rep in preselected_reps:
        slot = rep["_slot_key"]
        rows_in_slot = timeslot_map.get(slot, [])
        partner_idx = rep.get("partner_index", "")
        partner_row = None

        if partner_idx:
            for r in rows_in_slot:
                epoch_diff = abs(_sf(r.get("abs_time_epoch")) - _sf(rep.get("abs_time_epoch")))
                if r.get("index") == partner_idx and epoch_diff <= CFG.PARTNER_TIME_TOLERANCE_S:
                    partner_row = r
                    break
            if partner_row is None:
                candidate = index_all.get(partner_idx)
                if candidate:
                    epoch_diff = abs(_sf(candidate.get("abs_time_epoch")) - _sf(rep.get("abs_time_epoch")))
                    if epoch_diff <= CFG.PARTNER_TIME_TOLERANCE_S:
                        partner_row = candidate

        # Mark recommendation flags: representative TRUE, partner FALSE
        rep["recommended"] = "true"
        final_pool.append(rep)

        if partner_row:
            partner_copy = dict(partner_row)
            partner_copy["recommended"] = "false"
            final_pool.append(partner_copy)
        else:
            log.warning(
                f"[select] Missing partner row for representative {rep.get('index')} "
                f"(expected partner {partner_idx})"
            )

    # Chronological ordering for GUI
    final_pool.sort(key=lambda r: _sf(r.get("abs_time_epoch")))

    # Remove internal fields before writing to CSV
    final_pool_cleaned = [_clean_internal_fields(row) for row in final_pool]

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
