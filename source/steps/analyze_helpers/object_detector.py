# source/steps/analyze_helpers/object_detector.py
"""
YOLO-based bicycle detection for frame analysis.
Handles model loading, caching, and cleanup with thread-safety.
"""

from __future__ import annotations
import numpy as np
from typing import Dict, Optional
import threading

from ...config import DEFAULT_CONFIG as CFG
from ...utils.log import setup_logger

log = setup_logger("steps.analyze_helpers.object_detector")

# Thread-safe model management
_model_lock = threading.Lock()
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
    Thread-safe implementation.
    
    Returns:
        YOLO model instance
    """
    global _model_instance
    
    with _model_lock:
        if _model_instance is not None:
            return _model_instance
        
        # Load model
        from ultralytics import YOLO
        torch = _get_torch()
        
        device = 'mps' if CFG.USE_MPS and torch.backends.mps.is_available() else 'cpu'
        log.info(f"Loading YOLOv8n on {device}...")
        
        _model_instance = YOLO('yolov8n.pt').to(device)
        
        return _model_instance


def cleanup_model():
    """
    Release YOLO model and GPU/MPS memory.
    
    Thread-safe with proper ordering to prevent race conditions.
    Sets _model_instance to None BEFORE deletion to ensure cleanup
    completes even if an exception occurs.
    """
    global _model_instance
    
    with _model_lock:
        if _model_instance is None:
            return
        
        # Critical: Set to None FIRST to prevent re-entry
        model_to_delete = _model_instance
        _model_instance = None
        
        try:
            del model_to_delete
            log.debug("Released YOLO model")
        except Exception as e:
            log.warning(f"Model deletion warning: {e}")
    
    # GPU cache cleanup (outside lock - doesn't need synchronization)
    try:
        torch = _get_torch()
        if CFG.USE_MPS and torch.backends.mps.is_available():
            torch.mps.empty_cache()
            log.debug("Cleared MPS cache")
    except Exception as e:
        log.warning(f"MPS cache clear warning: {e}")
    
    # Force garbage collection
    import gc
    gc.collect()


class ObjectDetector:
    """YOLO-based bicycle detector with detection statistics."""
    
    def __init__(self):
        """Initialize detector and load model."""
        self.model = get_model()
        self.frames_processed = 0
        self.detections_found = 0
    
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
            
            max_conf = 0.0
            max_area = 0.0
            count = 0
            
            for r in results:
                if r.boxes is None:
                    continue
                
                for b in r.boxes:
                    cls = int(b.cls[0])
                    
                    # Filter to configured detection classes
                    if cls not in CFG.YOLO_DETECT_CLASSES:
                        continue
                    
                    conf = float(b.conf[0])
                    x1, y1, x2, y2 = b.xyxy[0].tolist()
                    area = max(0.0, (x2 - x1) * (y2 - y1))
                    
                    max_conf = max(max_conf, conf)
                    max_area = max(max_area, area)
                    count += 1
            
            self.frames_processed += 1
            
            if count > 0:
                self.detections_found += 1
            
            return {
                "detect_score": round(max_conf, 3),
                "num_detections": count,
                "bbox_area": round(max_area, 1)
            }
        
        except Exception as e:
            log.error(f"Detection failed: {e}")
            return self._empty_result()
    
    def _empty_result(self) -> Dict[str, float]:
        """Return empty detection result for failed frames."""
        return {
            "detect_score": 0.0,
            "num_detections": 0,
            "bbox_area": 0.0
        }
    
    def get_stats(self) -> Dict:
        """
        Return processing and detection statistics.
        
        Returns:
            Dict with frames_processed and detection_rate
        """
        detection_rate = 0.0
        if self.frames_processed > 0:
            detection_rate = (self.detections_found / self.frames_processed) * 100
        
        return {
            "frames_processed": self.frames_processed,
            "detections_found": self.detections_found,
            "detection_rate_pct": f"{detection_rate:.1f}%"
        }