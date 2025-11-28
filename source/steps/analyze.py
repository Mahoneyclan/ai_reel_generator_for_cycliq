# source/steps/analyze.py
"""
Frame analysis orchestrator.
Coordinates bike detection, scene detection, GPS enrichment, partner matching, and scoring.

This is a thin orchestration layer - actual analysis logic is in analyzers/ submodules.
"""

from __future__ import annotations
import csv
from pathlib import Path
from typing import Dict, List
from source.utils.progress_reporter import progress_iter

from ..config import DEFAULT_CONFIG as CFG
from ..io_paths import extract_path, enrich_path, _mk
from ..utils.video_utils import extract_frame_safe
from ..utils.log import setup_logger

# Import analysis components
from .analyzers import (
    BikeDetector,
    SceneDetector,
    GPSEnricher,
    PartnerMatcher,
    ScoreCalculator,
    cleanup_model
)

log = setup_logger("steps.analyze")


class FrameAnalyzer:
    """
    Combined frame analyzer using modular components.
    Extracts frames once and runs all analysis passes.
    """
    
    def __init__(self, scene_comparison_window_s: float = 5.0):
        """
        Initialize all analysis components.
        
        Args:
            scene_comparison_window_s: Time window for scene change detection
        """
        self.bike_detector = BikeDetector()
        self.scene_detector = SceneDetector(
            comparison_window_s=scene_comparison_window_s,
            fps=CFG.EXTRACT_FPS
        )
        self.gps_enricher = GPSEnricher()
        self.partner_matcher = PartnerMatcher()
        self.score_calculator = ScoreCalculator()
        
        self.frames_processed = 0
    
    def analyze_frame(self, video_path: Path, frame_number: int, camera: str) -> Dict[str, float]:
        """
        Analyze single frame: detection + scene scoring.
        
        Args:
            video_path: Path to source video file
            frame_number: Frame index to extract
            camera: Camera identifier
            
        Returns:
            Dict with detection and scene analysis results
        """
        # Extract frame once from video stream
        frame = extract_frame_safe(video_path, frame_number)
        if frame is None:
            return self._empty_result()
        
        # Run detection and scene analysis on same frame
        detect_result = self.bike_detector.detect(frame)
        scene_score = self.scene_detector.compute_scene_score(frame, camera)
        
        self.frames_processed += 1
        
        return {
            **detect_result,
            "scene_boost": scene_score
        }
    
    def enrich_frame(self, row: Dict) -> Dict:
        """Add GPX telemetry to frame metadata."""
        return self.gps_enricher.enrich(row)
    
    def find_partner(self, row: Dict, all_frames: List[Dict]) -> Dict:
        """Find partner camera frame."""
        return self.partner_matcher.find_partner(row, all_frames)
    
    def normalize_and_score(self, rows: List[Dict]) -> List[Dict]:
        """Normalize scene scores and compute composite scores."""
        rows = self.score_calculator.normalize_scene_scores(rows)
        return self.score_calculator.compute_scores(rows)
    
    def _empty_result(self) -> Dict[str, float]:
        """Return empty analysis result."""
        return {
            "detect_score": 0.0,
            "num_detections": 0,
            "bbox_area": 0.0,
            "scene_boost": 0.0
        }
    
    def get_stats(self) -> Dict:
        """Aggregate statistics from all components."""
        return {
            "frames_processed": self.frames_processed,
            **self.bike_detector.get_stats(),
            **self.scene_detector.get_stats(),
            **self.gps_enricher.get_stats(),
            **self.partner_matcher.get_stats(),
        }
    
    def cleanup(self):
        """Clean up all components."""
        self.scene_detector.cleanup()
        log.info(f"[analyze] Processed {self.frames_processed} frames")


def run() -> Path:
    """
    Main analyze pipeline orchestrator.
    
    Steps:
        1. Load frame metadata from extract.csv
        2. Sort by camera + timestamp for scene continuity
        3. Analyze each frame (detect bikes + scene change)
        4. Enrich with GPX telemetry
        5. Match partner camera frames
        6. Compute composite scores
        7. Write enriched.csv
        
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
    
    # Initialize analyzer
    analyzer = FrameAnalyzer(scene_comparison_window_s=CFG.SCENE_COMPARISON_WINDOW_S)
    enriched_rows: List[Dict] = []
    
    log.info(f"[analyze] Scene detection: comparing frames {CFG.SCENE_COMPARISON_WINDOW_S}s apart")
    
    try:
        # Process all frames
        pbar = progress_iter(rows, desc="[analyze] Processing frames", unit="frame")
        for idx, r in enumerate(pbar):
            progress_pct = int((idx / len(rows)) * 100)
            #pbar.set_postfix_str(f"{idx}/{len(rows)} ({progress_pct}%)")
            
            # Extract frame info
            video_path = Path(r["video_path"])
            frame_number = int(r["frame_number"])
            camera = r["camera"]
            
            # Analyze frame (detection + scene)
            analysis = analyzer.analyze_frame(video_path, frame_number, camera)
            
            # Find partner camera frame
            partner_data = analyzer.find_partner(r, rows)
            
            # Merge all metadata
            enriched = {**r, **analysis, **partner_data}
            
            # Add validity flags
            detect_ok = float(enriched.get("detect_score", 0) or 0.0) >= CFG.MIN_DETECT_SCORE
            paired_ok = bool(enriched.get("partner_index"))
            enriched["bike_detected"] = "true" if detect_ok else "false"
            enriched["paired_ok"] = "true" if paired_ok else "false"
            
            # Enrich with GPX telemetry
            enriched = analyzer.enrich_frame(enriched)
            
            enriched_rows.append(enriched)
        
        # Normalize scene scores and compute final scores
        enriched_rows = analyzer.normalize_and_score(enriched_rows)
        
        # Log summary statistics
        stats = analyzer.get_stats()
        detection_frames = sum(1 for r in enriched_rows if r.get("bike_detected") == "true")
        
        log.info(
            f"[analyze] Complete: {len(enriched_rows)} frames; "
            f"detections: {detection_frames}; "
            f"partners: {stats.get('partner_matches', 0)}; "
            f"GPS: {stats.get('gps_matches', 0)}"
        )
        log.info(f"[analyze] Scene detection stats: {stats}")
        
    finally:
        # Always cleanup, even on error
        analyzer.cleanup()
        cleanup_model()
    
    # Sort chronologically for output
    enriched_rows.sort(key=lambda r: float(r.get("abs_time_epoch", 0) or 0.0))
    
    # Write enriched CSV
    if enriched_rows:
        fieldnames = sorted({k for row in enriched_rows for k in row.keys()})
        with out_csv.open("w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(enriched_rows)
        log.info(f"[analyze] Wrote {len(enriched_rows)} enriched frames → {out_csv}")
    
    return out_csv


if __name__ == "__main__":
    run()