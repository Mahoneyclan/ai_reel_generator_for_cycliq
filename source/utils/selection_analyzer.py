# source/utils/selection_analyzer.py
"""
Utility to analyze selection pipeline and identify bottlenecks.
Provides detailed statistics on why clips were or weren't selected.
"""

from __future__ import annotations
import csv
from pathlib import Path
from collections import Counter
from typing import Dict, List, Tuple, Optional

from ..config import DEFAULT_CONFIG as CFG
from ..io_paths import extract_path, enrich_path, select_path
from .log import setup_logger

log = setup_logger("utils.selection_analyzer")


class SelectionAnalyzer:
    """Analyzes the selection pipeline to identify filtering bottlenecks."""
    
    def __init__(self, project_dir: Path):
        self.project_dir = project_dir
        self.extract_csv = extract_path()
        self.enrich_csv = enrich_path()
        self.select_csv = select_path()
        
    def analyze(self) -> Dict[str, any]:
        """Run comprehensive analysis and return results."""
        results = {
            "has_data": False,
            "extract_stats": {},
            "enrich_stats": {},
            "select_stats": {},
            "bottlenecks": [],
            "recommendations": []
        }
        
        # Check if files exist
        if not self.enrich_csv.exists():
            results["error"] = "No enriched.csv found - run Analyze step first"
            return results
            
        results["has_data"] = True
        
        # Analyze enriched.csv (main data source)
        try:
            with self.enrich_csv.open() as f:
                reader = csv.DictReader(f)
                rows = list(reader)
            
            results["enrich_stats"] = self._analyze_enriched(rows)
            results["bottlenecks"] = self._identify_bottlenecks(results["enrich_stats"])
            results["recommendations"] = self._generate_recommendations(
                results["enrich_stats"], 
                results["bottlenecks"]
            )
            
        except Exception as e:
            log.error(f"[analyzer] Failed to analyze enriched.csv: {e}")
            results["error"] = str(e)
            return results
        
        # Analyze select.csv if available
        if self.select_csv.exists():
            try:
                with self.select_csv.open() as f:
                    select_rows = list(csv.DictReader(f))
                results["select_stats"] = self._analyze_select(select_rows)
            except Exception as e:
                log.warning(f"[analyzer] Failed to analyze select.csv: {e}")
        
        return results
    
    def _analyze_enriched(self, rows: List[Dict]) -> Dict:
        """Analyze enriched.csv data."""
        total = len(rows)
        
        # Validity filters
        bike_detected = sum(1 for r in rows if r.get("bike_detected") == "true")
        paired = sum(1 for r in rows if r.get("paired_ok") == "true")
        has_gps = sum(1 for r in rows if r.get("gpx_missing") == "false")
        both_valid = sum(
            1 for r in rows 
            if r.get("bike_detected") == "true" and r.get("paired_ok") == "true"
        )
        
        # Score distributions
        detect_scores = [float(r.get("detect_score", 0) or 0) for r in rows]
        scene_scores = [float(r.get("scene_boost", 0) or 0) for r in rows]
        speeds = [float(r.get("speed_kmh", 0) or 0) for r in rows if r.get("speed_kmh")]
        
        # Detection score bins
        detect_bins = Counter()
        for s in detect_scores:
            if s == 0.0:
                detect_bins["0.00 (no detection)"] += 1
            elif s < 0.05:
                detect_bins["0.00-0.05 (very low)"] += 1
            elif s < 0.10:
                detect_bins["0.05-0.10 (low)"] += 1
            elif s < 0.20:
                detect_bins["0.10-0.20 (medium)"] += 1
            elif s < 0.50:
                detect_bins["0.20-0.50 (good)"] += 1
            else:
                detect_bins["0.50+ (excellent)"] += 1
        
        # Scene boost bins
        scene_bins = Counter()
        for s in scene_scores:
            if s < 0.10:
                scene_bins["0.00-0.10 (static)"] += 1
            elif s < 0.30:
                scene_bins["0.10-0.30 (minor change)"] += 1
            elif s < 0.50:
                scene_bins["0.30-0.50 (moderate)"] += 1
            elif s < 0.70:
                scene_bins["0.50-0.70 (significant)"] += 1
            else:
                scene_bins["0.70+ (major change)"] += 1
        
        # Speed bins
        speed_bins = Counter()
        for s in speeds:
            if s < 10:
                speed_bins["< 10 km/h"] += 1
            elif s < 15:
                speed_bins["10-15 km/h"] += 1
            elif s < 20:
                speed_bins["15-20 km/h"] += 1
            elif s < 25:
                speed_bins["20-25 km/h"] += 1
            elif s < 30:
                speed_bins["25-30 km/h"] += 1
            else:
                speed_bins["30+ km/h"] += 1
        
        return {
            "total_frames": total,
            "bike_detected": bike_detected,
            "bike_detected_pct": (bike_detected / total * 100) if total > 0 else 0,
            "paired": paired,
            "paired_pct": (paired / total * 100) if total > 0 else 0,
            "has_gps": has_gps,
            "has_gps_pct": (has_gps / total * 100) if total > 0 else 0,
            "both_valid": both_valid,
            "both_valid_pct": (both_valid / total * 100) if total > 0 else 0,
            "detect_score_avg": sum(detect_scores) / len(detect_scores) if detect_scores else 0,
            "detect_score_max": max(detect_scores) if detect_scores else 0,
            "detect_bins": dict(detect_bins),
            "scene_score_avg": sum(scene_scores) / len(scene_scores) if scene_scores else 0,
            "scene_score_max": max(scene_scores) if scene_scores else 0,
            "scene_bins": dict(scene_bins),
            "speed_avg": sum(speeds) / len(speeds) if speeds else 0,
            "speed_max": max(speeds) if speeds else 0,
            "speed_bins": dict(speed_bins),
            "frames_above_min_detect": sum(1 for s in detect_scores if s >= CFG.MIN_DETECT_SCORE),
            "frames_above_min_speed": sum(1 for s in speeds if s >= 15.0),
        }
    
    def _analyze_select(self, rows: List[Dict]) -> Dict:
        """Analyze select.csv data."""
        total = len(rows)
        recommended = sum(1 for r in rows if r.get("recommended") == "true")
        
        target_clips = int(CFG.HIGHLIGHT_TARGET_DURATION_S / CFG.CLIP_OUT_LEN_S)
        
        return {
            "candidate_pool": total,
            "recommended": recommended,
            "recommendation_pct": (recommended / total * 100) if total > 0 else 0,
            "target_clips": target_clips,
            "pool_vs_target": total / target_clips if target_clips > 0 else 0,
        }
    
    def _identify_bottlenecks(self, stats: Dict) -> List[Tuple[str, str, float]]:
        """Identify which filters are removing the most clips."""
        bottlenecks = []
        
        total = stats["total_frames"]
        
        # Check bike detection
        bike_loss = total - stats["bike_detected"]
        if bike_loss > total * 0.5:  # Lost >50%
            severity = (bike_loss / total) * 100
            bottlenecks.append((
                "CRITICAL",
                f"Bike Detection: {bike_loss}/{total} frames rejected ({severity:.1f}%)",
                severity
            ))
        
        # Check pairing
        pair_loss = total - stats["paired"]
        if pair_loss > total * 0.3:  # Lost >30%
            severity = (pair_loss / total) * 100
            bottlenecks.append((
                "HIGH",
                f"Camera Pairing: {pair_loss}/{total} frames unpaired ({severity:.1f}%)",
                severity
            ))
        
        # Check GPS
        gps_loss = total - stats["has_gps"]
        if gps_loss > total * 0.2:  # Lost >20%
            severity = (gps_loss / total) * 100
            bottlenecks.append((
                "MEDIUM",
                f"GPS Matching: {gps_loss}/{total} frames without GPS ({severity:.1f}%)",
                severity
            ))
        
        # Check combined validity
        if stats["both_valid_pct"] < 20:
            bottlenecks.append((
                "CRITICAL",
                f"Combined Filters: Only {stats['both_valid']} frames pass both bike+pair filters",
                100 - stats["both_valid_pct"]
            ))
        
        # Sort by severity
        bottlenecks.sort(key=lambda x: x[2], reverse=True)
        return bottlenecks
    
    def _generate_recommendations(self, stats: Dict, bottlenecks: List) -> List[Tuple[str, str]]:
        """Generate actionable recommendations based on analysis."""
        recommendations = []
        
        # Detection score recommendations
        if stats["bike_detected_pct"] < 20:
            recommendations.append((
                "🔴 CRITICAL",
                f"MIN_DETECT_SCORE too strict: Only {stats['bike_detected']} frames detected bikes.\n"
                f"   Current: {CFG.MIN_DETECT_SCORE:.2f}\n"
                f"   Recommended: 0.05 or lower\n"
                f"   Alternative: Lower YOLO_MIN_CONFIDENCE to {CFG.YOLO_MIN_CONFIDENCE/2:.2f}"
            ))
        elif stats["bike_detected_pct"] < 50:
            recommendations.append((
                "🟡 HIGH",
                f"MIN_DETECT_SCORE restrictive: {stats['bike_detected_pct']:.1f}% frames pass.\n"
                f"   Consider reducing from {CFG.MIN_DETECT_SCORE:.2f} to 0.05"
            ))
        
        # Pairing recommendations
        if stats["paired_pct"] < 80:
            recommendations.append((
                "🟡 MEDIUM",
                f"Camera pairing issues: Only {stats['paired_pct']:.1f}% frames paired.\n"
                f"   Increase PARTNER_TIME_TOLERANCE_S from {CFG.PARTNER_TIME_TOLERANCE_S}s to 3.0s"
            ))
        
        # Scene boost recommendations
        if stats["scene_score_avg"] > 0.5:
            recommendations.append((
                "✅ GOOD",
                f"Scene detection working well (avg: {stats['scene_score_avg']:.2f}).\n"
                f"   Consider increasing scene_boost weight in SCORE_WEIGHTS to 0.30"
            ))
        
        # Gap filtering
        recommendations.append((
            "💡 TIP",
            f"MIN_GAP_BETWEEN_CLIPS is {CFG.MIN_GAP_BETWEEN_CLIPS}s.\n"
            f"   Reduce to 30s for denser clips, or increase to 90s for more variety"
        ))
        
        return recommendations


def format_analysis_report(results: Dict) -> str:
    """Format analysis results as readable text report."""
    if not results.get("has_data"):
        return results.get("error", "No data available")
    
    lines = []
    lines.append("=" * 70)
    lines.append("CLIP SELECTION ANALYSIS REPORT")
    lines.append("=" * 70)
    lines.append("")
    
    # Enriched stats
    stats = results["enrich_stats"]
    lines.append("📊 FRAME ANALYSIS")
    lines.append("-" * 70)
    lines.append(f"Total frames extracted:     {stats['total_frames']}")
    lines.append(f"Bike detected:              {stats['bike_detected']} ({stats['bike_detected_pct']:.1f}%)")
    lines.append(f"Camera paired:              {stats['paired']} ({stats['paired_pct']:.1f}%)")
    lines.append(f"GPS matched:                {stats['has_gps']} ({stats['has_gps_pct']:.1f}%)")
    lines.append(f"Pass bike+pair filters:     {stats['both_valid']} ({stats['both_valid_pct']:.1f}%)")
    lines.append("")
    
    lines.append("🎯 DETECTION SCORES")
    lines.append("-" * 70)
    lines.append(f"Average:  {stats['detect_score_avg']:.3f}")
    lines.append(f"Maximum:  {stats['detect_score_max']:.3f}")
    lines.append(f"Above threshold ({CFG.MIN_DETECT_SCORE:.2f}): {stats['frames_above_min_detect']} frames")
    lines.append("")
    lines.append("Distribution:")
    for bin_name, count in sorted(stats['detect_bins'].items()):
        pct = (count / stats['total_frames'] * 100)
        bar = "█" * int(pct / 5)
        lines.append(f"  {bin_name:25s} {count:4d} frames {bar}")
    lines.append("")
    
    lines.append("🎬 SCENE CHANGE SCORES")
    lines.append("-" * 70)
    lines.append(f"Average:  {stats['scene_score_avg']:.3f}")
    lines.append(f"Maximum:  {stats['scene_score_max']:.3f}")
    lines.append("")
    lines.append("Distribution:")
    for bin_name, count in sorted(stats['scene_bins'].items()):
        pct = (count / stats['total_frames'] * 100)
        bar = "█" * int(pct / 5)
        lines.append(f"  {bin_name:25s} {count:4d} frames {bar}")
    lines.append("")
    
    lines.append("🚴 SPEED DISTRIBUTION")
    lines.append("-" * 70)
    lines.append(f"Average:  {stats['speed_avg']:.1f} km/h")
    lines.append(f"Maximum:  {stats['speed_max']:.1f} km/h")
    lines.append("")
    for bin_name, count in sorted(stats['speed_bins'].items()):
        pct = (count / stats['total_frames'] * 100)
        bar = "█" * int(pct / 5)
        lines.append(f"  {bin_name:15s} {count:4d} frames {bar}")
    lines.append("")
    
    # Selection stats
    if "select_stats" in results:
        sel = results["select_stats"]
        lines.append("✂️  SELECTION RESULTS")
        lines.append("-" * 70)
        lines.append(f"Target clips:          {sel['target_clips']}")
        lines.append(f"Candidate pool:        {sel['candidate_pool']} ({sel['pool_vs_target']:.1f}× target)")
        lines.append(f"Pre-selected:          {sel['recommended']} ({sel['recommendation_pct']:.1f}%)")
        lines.append("")
    
    # Bottlenecks
    if results["bottlenecks"]:
        lines.append("⚠️  BOTTLENECKS IDENTIFIED")
        lines.append("-" * 70)
        for severity, message, _ in results["bottlenecks"]:
            lines.append(f"[{severity}] {message}")
        lines.append("")
    
    # Recommendations
    if results["recommendations"]:
        lines.append("💡 RECOMMENDATIONS")
        lines.append("-" * 70)
        for icon, message in results["recommendations"]:
            lines.append(f"{icon}")
            for line in message.split("\n"):
                lines.append(f"   {line}")
            lines.append("")
    
    lines.append("=" * 70)
    
    return "\n".join(lines)