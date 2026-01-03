# source/steps/analyze_helpers/score_calculator.py
"""
Composite scoring for frame ranking.
Combines detection, scene change, speed, gradient, and bbox area into final scores.
"""

from __future__ import annotations
from typing import Dict, List

from ...config import DEFAULT_CONFIG as CFG
from ...utils.log import setup_logger
from ...utils.common import safe_float as _sf

log = setup_logger("steps.analyze_helpers.score_calculator")


class ScoreCalculator:
    """Computes composite and weighted scores for frame ranking."""
    
    def __init__(self):
        self.score_weights = CFG.SCORE_WEIGHTS
        self.camera_weights = CFG.CAMERA_WEIGHTS
    
    def normalize_scene_scores(self, rows: List[Dict]) -> List[Dict]:
        """
        Normalize scene_boost to 0-1 range.
        High scene scores indicate interesting visual changes (action, transitions).
        """
        if not rows or self.score_weights.get("scene_boost", 0) == 0:
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
            log.info(
                f"[score_calculator] Scene scores - "
                f"Top: {sorted_scores[0]:.3f}, "
                f"Median: {sorted_scores[len(sorted_scores)//2]:.3f}, "
                f"Min: {sorted_scores[-1]:.3f}"
            )
        
        return rows
    
    def compute_scores(self, rows: List[Dict]) -> List[Dict]:
        """
        Compute composite and weighted scores for all frames.
        Scene boost is a key component - high scene change = interesting moment.
        """
        W = self.score_weights
        out = []
        
        for r in rows:
            detect = _sf(r.get("detect_score"))
            scene_boost = _sf(r.get("scene_boost"))
            speed = _sf(r.get("speed_kmh"))
            grad_norm = abs(_sf(r.get("gradient_pct"))) / 8.0
            bbox_norm = _sf(r.get("bbox_area")) / 400_000.0
            
            # Speed normalization: scale to 0-1 range (no explicit slow-speed penalty)
            try:
                speed_norm = float(speed) / 60.0
            except (ValueError, TypeError):
                speed_norm = 0.0
            # Clamp between 0 and 1 for sensible contribution
            if speed_norm < 0.0:
                speed_norm = 0.0
            elif speed_norm > 1.0:
                speed_norm = 1.0
            
            # Composite score with scene boost
            score = (
                W["detect_score"] * detect +
                W["scene_boost"]  * scene_boost +  # 🎬 Scene changes boost ranking
                W["speed_kmh"]    * speed_norm +
                W["gradient"]     * grad_norm +
                W["bbox_area"]    * bbox_norm
            )
            
            # Apply camera weight
            camera = r.get("camera", "")
            w = self.camera_weights.get(camera, 1.0)
            
            r2 = dict(r)
            r2["score_composite"] = f"{score:.3f}"
            r2["score_weighted"] = f"{(score * w):.3f}"
            out.append(r2)
        
        return out
    
    def get_stats(self, rows: List[Dict]) -> Dict:
        """Return scoring statistics."""
        if not rows:
            return {}
        
        composite_scores = [_sf(r.get("score_composite")) for r in rows]
        weighted_scores = [_sf(r.get("score_weighted")) for r in rows]
        
        return {
            "composite_avg": f"{sum(composite_scores) / len(composite_scores):.3f}",
            "composite_max": f"{max(composite_scores):.3f}",
            "weighted_avg": f"{sum(weighted_scores) / len(weighted_scores):.3f}",
            "weighted_max": f"{max(weighted_scores):.3f}",
        }