# source/steps/analyze.py
"""
Combined frame analysis with scene change detection.
Scene scores are used as a key ranking signal for clip selection.
"""

from __future__ import annotations
import csv
import numpy as np
import cv2
from pathlib import Path
from typing import Dict, List, Tuple
from collections import deque
from collections import defaultdict
from tqdm import tqdm

_torch_imported = False
_torch = None

def _get_torch():
    global _torch_imported, _torch
    if not _torch_imported:
        import torch as _torch_module
        _torch = _torch_module
        _torch_imported = True
    return _torch

from source.config import DEFAULT_CONFIG as CFG
from source.io_paths import extract_path, enrich_path, _mk
from source.utils.video_utils import extract_frame_safe
from source.utils.log import setup_logger
from source.utils.gpx import GPXIndex, load_gpx

log = setup_logger("steps.analyze")

_model_instance = None

def _get_model():
    """Load YOLO model once, reuse across frames."""
    global _model_instance
    if _model_instance is None:
        from ultralytics import YOLO
        torch = _get_torch()
        device = 'mps' if CFG.USE_MPS and torch.backends.mps.is_available() else 'cpu'
        log.info(f"[analyze] Loading YOLOv8n on {device}...")
        _model_instance = YOLO('yolov8n.pt').to(device)
    return _model_instance

def cleanup_model():
    """Release YOLO model and GPU/MPS memory."""
    global _model_instance
    if _model_instance is not None:
        try:
            del _model_instance
            _model_instance = None
            log.debug("[analyze] Released YOLO model")
        except Exception as e:
            log.warning(f"[analyze] Model cleanup warning: {e}")

    torch = _get_torch()
    if CFG.USE_MPS and torch.backends.mps.is_available():
        try:
            torch.mps.empty_cache()
            log.debug("[analyze] Cleared MPS cache")
        except Exception as e:
            log.warning(f"[analyze] MPS cache clear warning: {e}")

    import gc
    gc.collect()

def _load_gpx_index() -> GPXIndex:
    """Load GPX data and build index for fast lookups."""
    try:
        gpx_path = CFG.INPUT_GPX_FILE
        if not gpx_path.exists():
            log.warning("[analyze] No GPX file found, skipping GPS enrichment")
            return GPXIndex([])
        points = load_gpx(str(gpx_path))
        if not points:
            log.warning("[analyze] GPX file loaded but contains no points")
            return GPXIndex([])
        log.info(f"[analyze] Loaded {len(points)} GPX points")
        return GPXIndex(points)
    except Exception as e:
        log.error(f"[analyze] Failed to load GPX: {e}")
        return GPXIndex([])

def _enrich_with_gpx(row: Dict, gpx_index: GPXIndex) -> Dict:
    """Add GPX telemetry to frame metadata."""
    epoch = float(row.get("abs_time_epoch", 0))
    pt = gpx_index.find_within_tolerance(epoch, CFG.GPX_TOLERANCE)

    if pt:
        row["gpx_missing"] = "false"
        row["gpx_dt_s"] = f"{abs(pt.timestamp_epoch - epoch):.3f}"
        row["gpx_epoch"] = f"{pt.timestamp_epoch:.3f}"
        row["gpx_time_utc"] = pt.when.isoformat()
        row["lat"] = f"{pt.lat:.6f}"
        row["lon"] = f"{pt.lon:.6f}"
        row["elevation"] = f"{pt.ele:.1f}"
        row["hr_bpm"] = str(pt.hr) if pt.hr else ""
        row["cadence_rpm"] = str(pt.cadence) if pt.cadence else ""
        row["speed_kmh"] = f"{pt.speed_kmh:.1f}" if pt.speed_kmh else ""
        row["gradient_pct"] = f"{pt.gradient:.1f}" if pt.gradient else ""
    else:
        row["gpx_missing"] = "true"
        for key in ["gpx_dt_s", "gpx_epoch", "gpx_time_utc", "lat", "lon", 
                    "elevation", "hr_bpm", "cadence_rpm", "speed_kmh", "gradient_pct"]:
            row[key] = ""
    return row

def _normalize_scene_scores(rows: List[Dict]) -> List[Dict]:
    """
    Normalize scene_boost to 0-1 range.
    High scene scores indicate interesting visual changes (action, transitions).
    """
    if not rows or CFG.SCORE_WEIGHTS.get("scene_boost", 0) == 0:
        return rows
    
    scores = [float(r.get("scene_boost", 0) or 0.0) for r in rows]
    max_score = max(scores) if scores else 1.0
    
    if max_score > 1e-6:
        for r in rows:
            current = float(r.get("scene_boost", 0) or 0.0)
            r["scene_boost"] = f"{(current / max_score):.3f}"
    
    # Log distribution for debugging
    if scores:
        sorted_scores = sorted(scores, reverse=True)
        log.info(f"[analyze] Scene scores - Top: {sorted_scores[0]:.3f}, "
                f"Median: {sorted_scores[len(sorted_scores)//2]:.3f}, "
                f"Min: {sorted_scores[-1]:.3f}")
    
    return rows

def _sf(v, d=0.0) -> float:
    """Safe float conversion."""
    try:
        return float(v) if v not in ("", None) else d
    except Exception:
        return d

def _camera_weight(cam: str) -> float:
    """Get camera weight from config."""
    return CFG.CAMERA_WEIGHTS.get(cam, 1.0)

def _compute_scores(rows: List[Dict]) -> List[Dict]:
    """
    Compute composite and weighted scores for all frames.
    Scene boost is a key component - high scene change = interesting moment.
    """
    W = CFG.SCORE_WEIGHTS
    out = []
    
    for r in rows:
        detect = _sf(r.get("detect_score"))
        scene_boost = _sf(r.get("scene_boost"))
        speed = _sf(r.get("speed_kmh"))
        grad_norm = abs(_sf(r.get("gradient_pct"))) / 8.0
        bbox_norm = _sf(r.get("bbox_area")) / 400_000.0

        # Speed normalization
        if speed < CFG.MIN_SPEED_PENALTY:
            speed_norm = (speed / 60.0) * 0.3
        elif speed > 15:
            speed_norm = (speed / 60.0) * 1.2
        else:
            speed_norm = speed / 60.0

        # Composite score with scene boost
        score = (
            W["detect_score"] * detect +
            W["scene_boost"]  * scene_boost +  # 🎬 Scene changes boost ranking
            W["speed_kmh"]    * speed_norm +
            W["gradient"]     * grad_norm +
            W["bbox_area"]    * bbox_norm
        )

        w = _camera_weight(r.get("camera", ""))
        r2 = dict(r)
        r2["score_composite"] = f"{score:.3f}"
        r2["score_weighted"] = f"{(score * w):.3f}"
        out.append(r2)
    
    return out

class SceneDetector:
    """
    Scene change detector with temporal window.
    Compares frames across a time window (e.g., 5-10 seconds) instead of just adjacent frames.
    Better for detecting significant scene changes vs. gradual camera movement.
    """
    
    def __init__(self, comparison_window_s: float = 5.0, fps: float = 1.0):
        """
        Args:
            comparison_window_s: How many seconds back to compare (default 5s)
            fps: Frame rate of extracted frames (default 1.0 from EXTRACT_FPS)
        """
        self.comparison_window_s = comparison_window_s
        self.fps = fps
        self.max_frames_to_keep = max(1, int(comparison_window_s * fps))
        
        # Store frame history per camera (circular buffer)
        self.frame_history: Dict[str, deque] = {}
        self.frame_counts: Dict[str, int] = {}
        self.scene_scores: Dict[str, list] = {}
        
    def compute_scene_score(self, frame: np.ndarray, camera: str) -> float:
        """
        Compute scene change score by comparing current frame to frame from N seconds ago.
        
        Returns:
            0.0 = no change (static scene)
            1.0 = complete scene change (new environment/action)
        """
        if frame is None:
            return 0.0
        
        # Convert to grayscale thumbnail for efficient comparison
        gray = cv2.cvtColor(frame, cv2.COLOR_RGB2GRAY)
        thumbnail = cv2.resize(gray, (64, 64), interpolation=cv2.INTER_AREA)
        
        # Initialize history for this camera
        if camera not in self.frame_history:
            self.frame_history[camera] = deque(maxlen=self.max_frames_to_keep)
            self.frame_counts[camera] = 0
            self.scene_scores[camera] = []
        
        history = self.frame_history[camera]
        
        # First frame - baseline
        if len(history) == 0:
            history.append(thumbnail)
            self.frame_counts[camera] += 1
            return 0.0
        
        # Not enough history yet - compare to oldest available frame
        comparison_frame = history[0]  # Oldest frame in buffer
        
        # Compute pixel-level difference
        diff = np.mean(np.abs(comparison_frame.astype(np.float32) - thumbnail.astype(np.float32)))
        score = float(diff / 255.0)
        
        # Add current frame to history (will auto-evict oldest when full)
        history.append(thumbnail)
        self.frame_counts[camera] += 1
        self.scene_scores[camera].append(score)
        
        # Log significant changes
        if score > 0.4:  # Lowered threshold since we're comparing across longer time
            from source.utils.log import setup_logger
            log = setup_logger("steps.analyze")
            log.debug(
                f"[scene] High change detected: {camera} frame {self.frame_counts[camera]}, "
                f"score={score:.3f} (comparing to {len(history)} frames / "
                f"{len(history) / self.fps:.1f}s ago)"
            )
        
        return score
    
    def get_stats(self) -> Dict:
        """Return processing statistics."""
        stats = {
            "cameras_processed": len(self.frame_history),
            "frame_counts": dict(self.frame_counts),
            "comparison_window_s": self.comparison_window_s,
        }
        
        # Add score statistics per camera
        for camera, scores in self.scene_scores.items():
            if scores:
                stats[f"{camera}_mean_scene"] = f"{np.mean(scores):.3f}"
                stats[f"{camera}_max_scene"] = f"{np.max(scores):.3f}"
                stats[f"{camera}_median_scene"] = f"{np.median(scores):.3f}"
                # Count high-change frames (adjusted threshold for longer window)
                high_change_count = sum(1 for s in scores if s > 0.3)
                stats[f"{camera}_high_changes"] = high_change_count
                stats[f"{camera}_high_change_pct"] = f"{(high_change_count / len(scores) * 100):.1f}%"
        
        return stats
    
    def cleanup(self):
        """Release cached data."""
        self.frame_history.clear()
        self.frame_counts.clear()
        self.scene_scores.clear()

class FrameAnalyzer:
    """Frame analysis: detection + scene scoring in one pass."""
    
    def __init__(self, scene_comparison_window_s: float = 5.0):
        self.model = _get_model()
        # Use configurable comparison window (default 5 seconds)
        from source.config import DEFAULT_CONFIG as CFG
        self.scene_detector = SceneDetector(
            comparison_window_s=scene_comparison_window_s,
            fps=CFG.EXTRACT_FPS
        )
        self.frames_processed = 0

    def analyze_frame(self, video_path: Path, frame_number: int, camera: str) -> Dict[str, float]:
        """
        Single frame extraction, dual analysis (detection + scene).
        Scene score identifies interesting moments for selection.
        """
        # Stream frame from MP4
        frame = extract_frame_safe(video_path, frame_number)
        if frame is None:
            return self._empty_result()

        # YOLO bike detection
        detect_result = self._detect_objects(frame)
        
        # Scene change detection (reuses extracted frame)
        scene_score = self.scene_detector.compute_scene_score(frame, camera)

        self.frames_processed += 1
        
        return {
            **detect_result,
            "scene_boost": scene_score
        }

    def _detect_objects(self, frame: np.ndarray) -> Dict[str, float]:
        """Run YOLO detection on frame."""
        try:
            results = self.model.predict(
                source=frame,
                imgsz=CFG.YOLO_IMAGE_SIZE,
                conf=CFG.YOLO_MIN_CONFIDENCE,
                verbose=False,
                stream=False
            )
            max_conf, max_area, count = 0.0, 0.0, 0
            for r in results:
                if r.boxes is None:
                    continue
                for b in r.boxes:
                    cls = int(b.cls[0])
                    if cls not in CFG.YOLO_DETECT_CLASSES:
                        continue
                    conf = float(b.conf[0])
                    x1, y1, x2, y2 = b.xyxy[0].tolist()
                    area = max(0.0, (x2 - x1) * (y2 - y1))
                    max_conf = max(max_conf, conf)
                    max_area = max(max_area, area)
                    count += 1
            return {
                "detect_score": round(max_conf, 3),
                "num_detections": count,
                "bbox_area": round(max_area, 1)
            }
        except Exception as e:
            log.error(f"[analyze] Detection failed: {e}")
            return {"detect_score": 0.0, "num_detections": 0, "bbox_area": 0.0}

    def _empty_result(self) -> Dict[str, float]:
        return {
            "detect_score": 0.0,
            "num_detections": 0,
            "bbox_area": 0.0,
            "scene_boost": 0.0
        }

    def cleanup(self):
        """Clean up and log statistics."""
        stats = self.scene_detector.get_stats()
        log.info(f"[analyze] Scene detection stats: {stats}")
        
        self.scene_detector.cleanup()
        log.debug(f"[analyze] Processed {self.frames_processed} frames")

def _find_partner_for_frame(frame_row: Dict, all_frames: List[Dict]) -> Dict:
    """Find closest-in-time opposite camera frame within tolerance."""
    camera = frame_row.get("camera", "")
    if not camera:
        return {
            "partner_video_path": "",
            "partner_frame_number": "",
            "partner_index": "",
            "partner_camera": "",
            "partner_abs_time_diff": "",
            "partner_source": "",
        }

    other_camera = "Fly6Pro" if camera == "Fly12Sport" else "Fly12Sport"
    other_frames = [f for f in all_frames if f.get("camera") == other_camera]
    if not other_frames:
        return {
            "partner_video_path": "",
            "partner_frame_number": "",
            "partner_index": "",
            "partner_camera": other_camera,
            "partner_abs_time_diff": "",
            "partner_source": "",
        }

    target_time = float(frame_row.get("abs_time_epoch", 0) or 0.0)
    best_frame, best_diff = None, float("inf")

    for f in other_frames:
        f_time = float(f.get("abs_time_epoch", 0) or 0.0)
        dt = abs(f_time - target_time)
        if dt <= CFG.PARTNER_TIME_TOLERANCE_S and dt < best_diff:
            best_frame, best_diff = f, dt

    if best_frame:
        partner_video_path = best_frame.get("video_path", "")
        partner_source = Path(partner_video_path).name if partner_video_path else ""
        return {
            "partner_video_path": partner_video_path,
            "partner_frame_number": best_frame.get("frame_number", ""),
            "partner_index": best_frame.get("index", ""),
            "partner_camera": other_camera,
            "partner_abs_time_diff": f"{best_diff:.3f}",
            "partner_source": partner_source,
        }

    return {
        "partner_video_path": "",
        "partner_frame_number": "",
        "partner_index": "",
        "partner_camera": other_camera,
        "partner_abs_time_diff": "",
        "partner_source": "",
    }

def run() -> Path:
    """
    Analyze frames: detection + scene + GPX enrichment + partner matching.
    Scene scores drive clip selection - high scene change = interesting moment.
    """
    extract_csv = extract_path()
    out_csv = _mk(enrich_path())

    if not extract_csv.exists():
        log.error("[analyze] extract.csv missing - run extract step first")
        return out_csv

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

    # Sort by camera + timestamp for scene continuity
    log.info("[analyze] Sorting frames by camera and timestamp...")
    rows.sort(key=lambda r: (r.get("camera", ""), float(r.get("abs_time_epoch", 0) or 0.0)))

    # Initialize with configurable scene detection window
    gpx_index = _load_gpx_index()
    analyzer = FrameAnalyzer(scene_comparison_window_s=CFG.SCENE_COMPARISON_WINDOW_S)
    enriched_rows: List[Dict] = []
    matched_gps = 0
    matched_partners = 0

    log.info(f"[analyze] Scene detection: comparing frames {CFG.SCENE_COMPARISON_WINDOW_S}s apart")


    try:
        pbar = tqdm(rows, desc="[analyze] Processing frames", unit="frame", ncols=80)
        for idx, r in enumerate(pbar):
            progress_pct = int((idx / len(rows)) * 100)
            pbar.set_postfix_str(f"{idx}/{len(rows)} ({progress_pct}%)")

            video_path = Path(r["video_path"])
            frame_number = int(r["frame_number"])
            camera = r["camera"]

            # Combined analysis (detection + scene in one frame extraction)
            analysis = analyzer.analyze_frame(video_path, frame_number, camera)

            # Partner matching
            partner_data = _find_partner_for_frame(r, rows)

            # Merge all metadata
            enriched = {**r, **analysis, **partner_data}

            # Validity flags
            detect_ok = float(enriched.get("detect_score", 0) or 0.0) >= CFG.MIN_DETECT_SCORE
            paired_ok = bool(enriched.get("partner_index"))
            enriched["bike_detected"] = "true" if detect_ok else "false"
            enriched["paired_ok"] = "true" if paired_ok else "false"
            if paired_ok:
                matched_partners += 1

            # GPX telemetry
            enriched = _enrich_with_gpx(enriched, gpx_index)
            if enriched.get("gpx_missing") == "false":
                matched_gps += 1

            enriched_rows.append(enriched)

        # Normalize scene scores and compute final ranking
        enriched_rows = _normalize_scene_scores(enriched_rows)
        enriched_rows = _compute_scores(enriched_rows)

        detection_frames = sum(1 for r in enriched_rows if r.get("bike_detected") == "true")
        log.info(
            f"[analyze] Complete: {len(enriched_rows)} frames; "
            f"detections: {detection_frames}; partners: {matched_partners}; "
            f"GPS matches: {matched_gps}"
        )

    finally:
        analyzer.cleanup()
        cleanup_model()

    # Sort chronologically for output
    enriched_rows.sort(key=lambda r: float(r.get("abs_time_epoch", 0) or 0.0))

    # Write enriched output
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