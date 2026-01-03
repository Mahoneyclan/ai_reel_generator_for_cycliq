# source/steps/analyze.py
"""
Frame analysis orchestrator.
Coordinates object detection, scene detection, GPS enrichment, and scoring.

This is a thin orchestration layer - actual analysis logic is in analyze_helpers/ submodules.
"""

from __future__ import annotations
import csv
from pathlib import Path
from typing import Dict, List
from source.utils.progress_reporter import progress_iter

from ..config import DEFAULT_CONFIG as CFG
from ..io_paths import extract_path, enrich_path, _mk
from ..utils.video_utils import VideoCache
from ..utils.log import setup_logger

# Import analysis components
from .analyze_helpers import (
    ObjectDetector,
    SceneDetector,
    GPSEnricher,
    ScoreCalculator,
    cleanup_model,
)

log = setup_logger("steps.analyze")


def _assign_moment_ids(rows: List[Dict]) -> List[Dict]:
    """
    Assign moment_id based solely on abs_time_epoch, using a fixed global
    reference (epoch=0) so that camera start-time differences do not shift
    bucket boundaries.

    moment_id = floor(abs_time_epoch / sample_interval)
    """

    if not rows:
        return rows

    sample_interval = float(CFG.EXTRACT_INTERVAL_SECONDS)
    if sample_interval <= 0:
        sample_interval = 1.0

    for row in rows:
        try:
            epoch = float(row.get("abs_time_epoch", 0) or 0.0)
        except Exception:
            epoch = 0.0

        # Use global epoch reference (0), not first_epoch
        mid = int(epoch // sample_interval)

        row["moment_id"] = str(mid)

    return rows



class FrameAnalyzer:
    """
    Combined frame analyzer using modular components.
    Extracts frames once and runs all analysis passes.

    Optimized:
    - Uses VideoCache to keep videos open while processing consecutive frames
    - Uses batch YOLO inference for 2-3x GPU speedup
    """

    # Default batch size for YOLO inference
    DEFAULT_BATCH_SIZE = 8

    def __init__(self, scene_comparison_window_s: float = 5.0, batch_size: int = None):
        """
        Initialize all analysis components.

        Args:
            scene_comparison_window_s: Time window for scene change detection
            batch_size: Number of frames to batch for YOLO inference (default: 8)
        """
        self.object_detector = ObjectDetector()
        self.scene_detector = SceneDetector(
            comparison_window_s=scene_comparison_window_s,
            fps=1.0 / float(CFG.EXTRACT_INTERVAL_SECONDS),
        )
        self.gps_enricher = GPSEnricher()
        self.score_calculator = ScoreCalculator()

        # Video cache for efficient frame extraction
        self.video_cache = VideoCache()

        # Batch size for YOLO inference
        self.batch_size = batch_size or self.DEFAULT_BATCH_SIZE

        self.frames_processed = 0

    def analyze_frame(self, video_path: Path, frame_number: int, camera: str) -> Dict[str, object]:
        """
        Analyze single frame: detection + scene scoring.

        Uses VideoCache for efficient extraction when processing
        consecutive frames from the same video file.

        Args:
            video_path: Path to source video file
            frame_number: Frame index to extract
            camera: Camera identifier

        Returns:
            Dict with detection and scene analysis results
        """
        # Extract frame using cache (reuses open video for consecutive frames)
        frame = self.video_cache.extract_frame(video_path, frame_number)
        if frame is None:
            return self._empty_result()

        # Run detection and scene analysis on same frame
        detect_result = self.object_detector.detect(frame)
        scene_score = self.scene_detector.compute_scene_score(frame, camera)

        self.frames_processed += 1

        return {
            **detect_result,
            "scene_boost": scene_score,
        }

    def analyze_batch(self, batch_info: List[Dict]) -> List[Dict[str, object]]:
        """
        Analyze a batch of frames with batched YOLO inference.

        Extracts all frames, runs batch YOLO detection, then runs
        scene detection per-frame (scene detection needs sequential processing).

        Args:
            batch_info: List of dicts with 'video_path', 'frame_number', 'camera'

        Returns:
            List of analysis result dicts matching input order
        """
        if not batch_info:
            return []

        # Extract all frames in batch
        frames = []
        for info in batch_info:
            frame = self.video_cache.extract_frame(
                Path(info['video_path']),
                int(info['frame_number'])
            )
            frames.append(frame)

        # Batch YOLO detection
        detect_results = self.object_detector.detect_batch(frames)

        # Scene detection per-frame (needs sequential per-camera processing)
        results = []
        for i, (info, frame, detect_result) in enumerate(zip(batch_info, frames, detect_results)):
            if frame is not None:
                scene_score = self.scene_detector.compute_scene_score(frame, info['camera'])
            else:
                scene_score = 0.0

            self.frames_processed += 1

            results.append({
                **detect_result,
                "scene_boost": scene_score,
            })

        return results

    def enrich_frame(self, row: Dict) -> Dict:
        """Add GPX telemetry to frame metadata."""
        return self.gps_enricher.enrich(row)

    def normalize_and_score(self, rows: List[Dict]) -> List[Dict]:
        """Normalize scene scores and compute composite scores."""
        rows = self.score_calculator.normalize_scene_scores(rows)
        return self.score_calculator.compute_scores(rows)

    def _empty_result(self) -> Dict[str, object]:
        """Return empty analysis result."""
        return {
            "detect_score": 0.0,
            "num_detections": 0,
            "bbox_area": 0.0,
            "detected_classes": [],
            "scene_boost": 0.0,
        }

    def get_stats(self) -> Dict:
        """Aggregate statistics from all components."""
        return {
            "frames_processed": self.frames_processed,
            **self.object_detector.get_stats(),
            **self.scene_detector.get_stats(),
            **self.gps_enricher.get_stats(),
        }

    def cleanup(self):
        """Clean up all components."""
        self.video_cache.close()  # Close cached video and log stats
        self.scene_detector.cleanup()
        log.info(f"[analyze] Processed {self.frames_processed} frames")


def run() -> Path:
    """
    Main analyze pipeline orchestrator.

    Steps:
        1. Load frame metadata from extract.csv
        2. Sort by camera + timestamp for scene continuity
        3. Analyze each frame (object detection + scene change)
        4. Enrich with GPX telemetry
        5. Compute composite scores
        6. Write enriched.csv

    Returns:
        Path to enriched.csv output file
    """
    extract_csv = extract_path()
    out_csv = _mk(enrich_path())

    # Validate input
    if not extract_csv.exists():
        log.error("[analyze] extract.csv missing - run extract step first")
        return out_csv

    # Load frame metadata
    try:
        log.info("[analyze] Loading extract.csv...")
        with extract_csv.open() as f:
            rows = list(csv.DictReader(f))
        log.info(f"[analyze] Loaded {len(rows)} frame metadata rows")
    except Exception as e:
        log.error(f"[analyze] Failed to load extract.csv: {e}")
        return out_csv

    if not rows:
        log.warning("[analyze] No frames to analyze")
        return out_csv

    # Sort for scene continuity (same camera frames should be sequential)
    log.info("[analyze] Sorting frames by camera and timestamp...")
    rows.sort(key=lambda r: (r.get("camera", ""), float(r.get("abs_time_epoch", 0) or 0.0)))

    # Initialize analyzer with batch size from config
    batch_size = CFG.YOLO_BATCH_SIZE
    analyzer = FrameAnalyzer(
        scene_comparison_window_s=CFG.SCENE_COMPARISON_WINDOW_S,
        batch_size=batch_size
    )
    enriched_rows: List[Dict] = []

    log.info(f"[analyze] Scene detection: comparing frames {CFG.SCENE_COMPARISON_WINDOW_S}s apart")
    log.info(f"[analyze] Using batch size {batch_size} for YOLO inference")

    try:
        # Process frames in batches for GPU efficiency
        total_frames = len(rows)
        processed = 0

        for batch_start in range(0, total_frames, batch_size):
            batch_end = min(batch_start + batch_size, total_frames)
            batch_rows = rows[batch_start:batch_end]

            # Prepare batch info for analyzer
            batch_info = [
                {
                    'video_path': r["video_path"],
                    'frame_number': r["frame_number"],
                    'camera': r["camera"]
                }
                for r in batch_rows
            ]

            # Batch analyze (YOLO batched, scene detection per-frame)
            batch_results = analyzer.analyze_batch(batch_info)

            # Merge results with original rows
            for r, analysis in zip(batch_rows, batch_results):
                enriched = {**r, **analysis}

                # Add detection flag
                detect_ok = float(enriched.get("detect_score", 0) or 0.0) >= CFG.MIN_DETECT_SCORE
                enriched["object_detected"] = "true" if detect_ok else "false"

                # Persist class IDs for reporting/audit
                if isinstance(enriched.get("detected_classes"), list):
                    enriched["detected_classes"] = ";".join(
                        str(c) for c in sorted(enriched["detected_classes"])
                    )

                # Enrich with GPX telemetry
                enriched = analyzer.enrich_frame(enriched)

                enriched_rows.append(enriched)

            processed += len(batch_rows)
            log.info(f"[analyze] Processed {processed}/{total_frames} frames ({processed*100//total_frames}%)")

        # Normalize scene scores and compute final scores
        enriched_rows = analyzer.normalize_and_score(enriched_rows)

        # Log summary statistics
        stats = analyzer.get_stats()
        detection_frames = sum(1 for r in enriched_rows if r.get("object_detected") == "true")

        log.info(
            f"[analyze] Complete: {len(enriched_rows)} frames; "
            f"detections: {detection_frames}; "
            f"GPS: {stats.get('gps_matches', 0)}"
        )
        log.info(f"[analyze] Scene detection stats: {stats}")

    finally:
        # Always cleanup, even on error
        analyzer.cleanup()
        cleanup_model()

    # Sort chronologically for output
    enriched_rows.sort(key=lambda r: float(r.get("abs_time_epoch", 0) or 0.0))

    # Assign moment_ids to group paired frames
    log.info("[analyze] Assigning moment IDs to paired frames...")
    enriched_rows = _assign_moment_ids(enriched_rows)
    paired_moments = sum(1 for r in enriched_rows if r.get("moment_id"))
    log.info(f"[analyze] Assigned moment IDs: {paired_moments} frames in {paired_moments // 2} moments")

    # Write enriched CSV
    if enriched_rows:
        # Use all keys present in rows (now includes moment_id)
        fieldnames = sorted({k for row in enriched_rows for k in row.keys()})
        with out_csv.open("w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(enriched_rows)
        log.info(f"[analyze] Wrote {len(enriched_rows)} enriched frames → {out_csv}")

    return out_csv


