# source/steps/analyze_helpers/object_detector.py
"""
YOLO-based bicycle detection for frame analysis.
Handles model loading, caching, and cleanup.
"""

from __future__ import annotations
import numpy as np
from typing import Dict, Optional

from ...config import DEFAULT_CONFIG as CFG
from ...utils.log import setup_logger

log = setup_logger("steps.analyze_helpers.object_detector")

# Module-level cache for YOLO model
_model_instance = None
_torch_imported = False
_torch = None


def _get_torch():
    """Lazy import torch to avoid startup overhead."""
    global _torch_imported, _torch
    if not _torch_imported:
        import torch as _torch_module
        _torch = _torch_module
        _torch_imported = True
    return _torch


def get_model():
    """
    Load YOLO model once, reuse across frames.
    Uses MPS acceleration on M1 Macs if available.
    """
    global _model_instance
    if _model_instance is None:
        from ultralytics import YOLO
        torch = _get_torch()
        device = 'mps' if CFG.USE_MPS and torch.backends.mps.is_available() else 'cpu'
        log.info(f"[object_detector] Loading YOLOv8n on {device}...")
        _model_instance = YOLO('yolov8n.pt').to(device)
    return _model_instance


def cleanup_model():
    """Release YOLO model and GPU/MPS memory."""
    global _model_instance
    if _model_instance is not None:
        try:
            del _model_instance
            _model_instance = None
            log.debug("[object_detector] Released YOLO model")
        except Exception as e:
            log.warning(f"[object_detector] Model cleanup warning: {e}")

    torch = _get_torch()
    if CFG.USE_MPS and torch.backends.mps.is_available():
        try:
            torch.mps.empty_cache()
            log.debug("[object_detector] Cleared MPS cache")
        except Exception as e:
            log.warning(f"[object_detector] MPS cache clear warning: {e}")

    import gc
    gc.collect()


class ObjectDetector:
    """YOLO-based bicycle detector."""
    
    def __init__(self):
        self.model = get_model()
        self.frames_processed = 0
    
    def detect(self, frame: np.ndarray) -> Dict[str, float]:
        """
        Run YOLO detection on RGB frame.
        
        Args:
            frame: RGB numpy array (H, W, 3)
            
        Returns:
            Dict with detect_score, num_detections, bbox_area
        """
        if frame is None:
            return self._empty_result()
        
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
            
            self.frames_processed += 1
            
            return {
                "detect_score": round(max_conf, 3),
                "num_detections": count,
                "bbox_area": round(max_area, 1)
            }
            
        except Exception as e:
            log.error(f"[object_detector] Detection failed: {e}")
            return self._empty_result()
    
    def _empty_result(self) -> Dict[str, float]:
        """Return empty detection result."""
        return {
            "detect_score": 0.0,
            "num_detections": 0,
            "bbox_area": 0.0
        }
    
    def get_stats(self) -> Dict:
        """Return processing statistics."""
        return {
            "frames_processed": self.frames_processed
        }