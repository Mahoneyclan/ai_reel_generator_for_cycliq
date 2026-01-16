# source/utils/selection_analyzer.py
"""
Selection analysis and reporting for enriched/select outputs.
Summarizes detection, scene, speed, and selection outcomes.
"""

from __future__ import annotations
from collections import Counter
from pathlib import Path
from typing import Dict, List

from ..config import DEFAULT_CONFIG as CFG
from ..io_paths import enrich_path, select_path
from .log import setup_logger
from .common import safe_float as _sf, read_csv as _load_csv
from ..steps.enrich_helpers.score_calculator import ScoreCalculator

log = setup_logger("utils.selection_analyzer")


def analyze_selection() -> str:
    enriched = _load_csv(enrich_path())
    selected = _load_csv(select_path())

    total = len(enriched)
    object_detected = sum(1 for r in enriched if r.get("object_detected") == "true")
    
    # Check camera pairing - frames are "paired" if their moment_id appears across multiple cameras
    moment_camera_sets = {}  # {moment_id: set of cameras}
    for r in enriched:
        moment_id = r.get("moment_id")
        camera = r.get("camera")
        if moment_id and camera:
            if moment_id not in moment_camera_sets:
                moment_camera_sets[moment_id] = set()
            moment_camera_sets[moment_id].add(camera)
    
    # Count frames where the moment_id has multiple cameras
    paired_ok = sum(
        1 for r in enriched 
        if r.get("moment_id") in moment_camera_sets 
        and len(moment_camera_sets[r.get("moment_id")]) >= 2
    )
    
    gps_matched = sum(1 for r in enriched if r.get("gpx_missing") == "false")

    # Count frames that pass both object detection AND camera pairing filters
    pass_filters = sum(
        1 for r in enriched
        if r.get("object_detected") == "true"
        and r.get("moment_id") in moment_camera_sets
        and len(moment_camera_sets[r.get("moment_id")]) >= 2
    )

    # Detection score distribution
    detect_scores = [_sf(r.get("detect_score")) for r in enriched]
    above_threshold = sum(1 for s in detect_scores if s >= _sf(CFG.YOLO_MIN_CONFIDENCE))
    max_detect = max(detect_scores) if detect_scores else 0.0
    avg_detect = (sum(detect_scores) / len(detect_scores)) if detect_scores else 0.0

    # Scene change distribution
    scene_scores = [_sf(r.get("scene_boost")) for r in enriched]
    avg_scene = (sum(scene_scores) / len(scene_scores)) if scene_scores else 0.0
    max_scene = max(scene_scores) if scene_scores else 0.0

    # Speed distribution
    speeds = [_sf(r.get("speed_kmh")) for r in enriched]
    avg_speed = (sum(speeds) / len(speeds)) if speeds else 0.0
    max_speed = max(speeds) if speeds else 0.0

    # Candidate pool
    target_clips = int((CFG.HIGHLIGHT_TARGET_DURATION_M * 60) // CFG.CLIP_OUT_LEN_S)
    preselected = sum(1 for r in selected if r.get("recommended") == "true")

    # Per-class breakdown - FIXED to handle semicolon delimiters and invalid data
    class_counts = Counter()
    for r in enriched:
        classes_str = r.get("detected_classes") or ""
        # Handle both comma and semicolon delimiters
        if ";" in classes_str:
            classes = classes_str.split(";")
        else:
            classes = classes_str.split(",")
        for c in classes:
            c = c.strip()  # Remove whitespace
            if c and c.isdigit():  # Only count valid numeric class IDs
                class_counts[c] += 1

    def _bar(n: int, scale: int = 40) -> str:
        blocks = max(0, int(round((n / max(1, total)) * scale)))
        return "█" * blocks

    # Score stats
    calc = ScoreCalculator()
    stats = calc.get_stats(enriched)

    lines: List[str] = []
    lines.append("=" * 70)
    lines.append("CLIP SELECTION ANALYSIS REPORT")
    lines.append("=" * 70)
    lines.append("")
    lines.append("📊 FRAME ANALYSIS")
    lines.append("-" * 70)
    lines.append(f"Total frames extracted:     {total}")
    lines.append(f"Objects detected:           {object_detected} ({(object_detected/total*100):.1f}%)")
    lines.append(f"Camera paired:              {paired_ok} ({(paired_ok/total*100):.1f}%)")
    lines.append(f"GPS matched:                {gps_matched} ({(gps_matched/total*100):.1f}%)")
    lines.append(f"Pass object+pair filters:   {pass_filters} ({(pass_filters/total*100):.1f}%)")
    lines.append("")
    lines.append("🔍 YOLO CLASS BREAKDOWN")
    lines.append("-" * 70)
    if class_counts:
        name_map = {v: k for k, v in CFG.YOLO_CLASS_MAP.items()}
        for cls_id, cnt in sorted(class_counts.items(), key=lambda kv: int(kv[0])):
            name = name_map.get(int(cls_id), f"Class {cls_id}")
            lines.append(f"  {name} (Class {cls_id}): {cnt} frames {_bar(cnt)}")
    else:
        lines.append("  No classes detected at configured thresholds")
    lines.append("")
    lines.append("🎯 DETECTION SCORES")
    lines.append("-" * 70)
    lines.append(f"Average:  {avg_detect:.3f}")
    lines.append(f"Maximum:  {max_detect:.3f}")
    lines.append(f"Above threshold ({CFG.YOLO_MIN_CONFIDENCE:.2f}): {above_threshold} frames")
    lines.append("")
    lines.append("🎬 SCENE CHANGE SCORES")
    lines.append("-" * 70)
    lines.append(f"Average:  {avg_scene:.3f}")
    lines.append(f"Maximum:  {max_scene:.3f}")
    lines.append("")
    lines.append("🚴 SPEED DISTRIBUTION")
    lines.append("-" * 70)
    lines.append(f"Average:  {avg_speed:.1f} km/h")
    lines.append(f"Maximum:  {max_speed:.1f} km/h")
    lines.append("")
    lines.append("✂️  SELECTION RESULTS")
    lines.append("-" * 70)
    lines.append(f"Target clips:          {target_clips}")
    lines.append(f"Pre-selected:          {preselected}")
    lines.append("")
    lines.append("📈 SCORE STATS")
    lines.append("-" * 70)
    if stats:
        lines.append(f"Composite avg: {stats['composite_avg']}")
        lines.append(f"Composite max: {stats['composite_max']}")
        lines.append(f"Weighted avg:  {stats['weighted_avg']}")
        lines.append(f"Weighted max:  {stats['weighted_max']}")
    lines.append("")
    return "\n".join(lines)