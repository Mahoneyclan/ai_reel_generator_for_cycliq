# source/steps/build_helpers/clip_renderer.py
"""
Individual clip rendering with overlays.
Handles PiP, minimap, gauges, and audio muxing.

Moment-based version:
- main_row: selected perspective for this moment (recommended=true).
- pip_row:  opposite camera for same moment (always used as PiP).

FIXED:
- Each camera gets its own t_start calculated from its own adjusted_start_time
- This ensures perfect alignment even when cameras have different offsets
"""

from __future__ import annotations
import subprocess
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from ...config import DEFAULT_CONFIG as CFG
from ...utils.log import setup_logger
from ...utils.ffmpeg import mux_audio
from ...utils.trophy_overlay import create_trophy_overlay
from ...utils.hardware import get_optimal_video_codec, is_apple_silicon
from ...io_paths import _mk, trophy_dir

log = setup_logger("steps.build_helpers.clip_renderer")

AUDIO_SAMPLE_RATE = "48000"


class ClipRenderer:
    """Renders individual highlight clips with all overlays."""

    def __init__(self, output_dir: Path):
        """
        Args:
            output_dir: Directory for rendered clips
        """
        self.output_dir = _mk(output_dir)

    # -------------------------------------------------------------------------
    # Public API
    # -------------------------------------------------------------------------

    def render_clip(
        self,
        main_row: Dict,
        pip_row: Dict,
        clip_idx: int,
        minimap_path: Optional[Path],
        elevation_path: Optional[Path],
        gauge_path: Optional[Path],
    ) -> Optional[Path]:
        """
        Render single clip with all overlays (main + PiP + minimap + gauges).

        Time model:
            abs_time_epoch      = world-aligned timestamp of the moment
            adjusted_start_time = real start time of the source clip (UTC)
            clip_start_epoch    = parsed adjusted_start_time
            offset_in_clip      = abs_time_epoch - clip_start_epoch
            t_start             = max(0, offset_in_clip - CLIP_PRE_ROLL_S)

        CRITICAL: main and pip videos need separate t_start values
        because they have different adjusted_start_time values.
        """

        main_video = CFG.INPUT_VIDEOS_DIR / main_row["source"]
        pip_video = CFG.INPUT_VIDEOS_DIR / pip_row["source"]

        # ---------------------------------------------------------------------
        # Compute t_start for BOTH cameras (they may differ!)
        # ---------------------------------------------------------------------
        t_start_main = self._compute_t_start(main_row, clip_idx, "main")
        t_start_pip = self._compute_t_start(pip_row, clip_idx, "pip")

        if t_start_main is None:
            log.error(f"[clip] Failed to compute t_start for main camera (clip {clip_idx})")
            return None

        if t_start_pip is None:
            log.warning(f"[clip] Failed to compute t_start for pip camera (clip {clip_idx})")
            t_start_pip = t_start_main  # Fallback to main timing

        duration = CFG.CLIP_OUT_LEN_S
        output_path = self.output_dir / f"clip_{clip_idx:04d}.mp4"

        # Build ffmpeg command with separate timing for each camera
        inputs, filter_complex, final_stream = self._build_ffmpeg_inputs_and_filters(
            main_video=main_video,
            pip_video=pip_video,
            t_start_main=t_start_main,
            t_start_pip=t_start_pip,
            minimap_path=minimap_path,
            elevation_path=elevation_path,
            duration=duration,
            main_row=main_row,
            clip_idx=clip_idx,
            gauge_path=gauge_path,
        )

        cmd = self._build_encode_command(inputs, filter_complex, final_stream, output_path)

        try:
            subprocess.run(cmd, check=True)
            if not output_path.exists():
                log.error(f"[clip] FFmpeg reported success but {output_path} was not created")
                return None
            log.debug(
                f"[clip] Encoded clip {clip_idx:04d} "
                f"(main@{t_start_main:.3f}s, pip@{t_start_pip:.3f}s)"
            )
        except subprocess.CalledProcessError as e:
            log.error(f"[clip] FFmpeg failed for clip {clip_idx}: {e}")
            return None

        # Mux audio from main camera
        return self._mux_audio(output_path, main_video, t_start_main, duration, clip_idx)

    # -------------------------------------------------------------------------
    # Internal helpers
    # -------------------------------------------------------------------------

    def _compute_t_start(
        self,
        row: Dict,
        clip_idx: int,
        camera_role: str
    ) -> Optional[float]:
        """
        Compute extraction start time for a single camera.

        Uses:
        - abs_time_epoch: world time of the selected moment
        - clip_start_epoch: real start time of this source clip (from extract)
        - duration_s: clip duration for bounds checking

        Returns:
        t_start (float): seconds into the clip to begin extraction,
        or None if invalid.
        """
        try:
            abs_epoch = float(row.get("abs_time_epoch") or 0.0)
            clip_start_epoch = float(row.get("clip_start_epoch") or 0.0)
            duration_s = float(row.get("duration_s") or 0.0)
        except (ValueError, TypeError) as e:
            log.error(
                f"[clip] Invalid time fields for {camera_role} camera in clip {clip_idx}: {e}"
            )
            return None

        if abs_epoch == 0.0 or clip_start_epoch == 0.0:
            log.error(
                f"[clip] Missing abs_time_epoch or clip_start_epoch for "
                f"{camera_role} camera in clip {clip_idx}"
            )
            return None

        # Offset of the desired moment inside the clip
        offset_in_clip = abs_epoch - clip_start_epoch

        if offset_in_clip < 0:
            log.warning(
                f"[clip] Negative offset_in_clip ({offset_in_clip:.3f}s) "
                f"for {camera_role} camera in clip {clip_idx:04d} "
                f"({row.get('source')})"
            )

        # Apply pre-roll
        t_start = max(0.0, offset_in_clip - CFG.CLIP_PRE_ROLL_S)

        # Bounds check
        if duration_s > 0 and t_start >= duration_s:
            log.error(
                f"[clip] t_start={t_start:.3f}s beyond clip duration "
                f"{duration_s:.3f}s for {camera_role} camera "
                f"({row.get('source')}) in clip_idx={clip_idx}"
            )
            return None

        return t_start



    def _build_ffmpeg_inputs_and_filters(
        self,
        main_video: Path,
        pip_video: Optional[Path],
        t_start_main: float,
        t_start_pip: float,
        minimap_path: Optional[Path],
        elevation_path: Optional[Path],
        duration: float,
        main_row: Dict,
        clip_idx: int,
        gauge_path: Optional[Path],
    ) -> Tuple[List[str], List[str], str]:
        """
        Build ffmpeg inputs and filter_complex for all overlays.

        CRITICAL: Uses separate t_start values for main and pip cameras.
        """
        inputs: List[str] = [
            "-ss",
            f"{t_start_main:.3f}",
            "-t",
            f"{duration:.3f}",
            "-i",
            str(main_video),
        ]
        filters: List[str] = []
        current_stream = "[0:v]"

        # PiP overlay (with its own t_start!)
        if pip_video and pip_video.exists():
            inputs.extend(
                [
                    "-ss",
                    f"{t_start_pip:.3f}",  # ✓ CORRECT - uses pip timing!
                    "-t",
                    f"{duration:.3f}",
                    "-i",
                    str(pip_video),
                ]
            )
            # [1:v] is pip
            filters.append(
                f"[1:v]scale=iw*{CFG.PIP_SCALE_RATIO}:-1[pip];"
                f"{current_stream}[pip]overlay=W-w-{CFG.PIP_MARGIN}:H-h-{CFG.PIP_MARGIN}[v1]"
            )
            current_stream = "[v1]"
        else:
            log.warning("[clip] PiP video missing; rendering main camera only")

        # Minimap overlay - positioned at top-right with margin
        # Minimap is pre-rendered to fit within PIP width x available height
        OVERLAY_MARGIN = CFG.MINIMAP_MARGIN

        if minimap_path and minimap_path.exists():
            inputs.extend(["-i", str(minimap_path)])
            minimap_idx = len([a for a in inputs if a == "-i"]) - 1
            # Position at top-right: X = W-w-margin, Y = margin
            minimap_filter = f"[{minimap_idx}:v]overlay=W-w-{OVERLAY_MARGIN}:{OVERLAY_MARGIN}"
            filters.append(
                f"{current_stream}{minimap_filter}[vmap]"
            )
            current_stream = "[vmap]"
            log.debug(f"[clip] Minimap filter: {minimap_filter}")

        # Elevation plot overlay (below minimap, same right alignment)
        if elevation_path and elevation_path.exists() and CFG.SHOW_ELEVATION_PLOT:
            inputs.extend(["-i", str(elevation_path)])
            elev_idx = len([a for a in inputs if a == "-i"]) - 1
            # Position: right-aligned with minimap, below it with 10px gap
            # Get actual minimap height from file (varies by route aspect ratio)
            minimap_height = 500  # Default fallback
            if minimap_path and minimap_path.exists():
                try:
                    from PIL import Image
                    with Image.open(minimap_path) as mm_img:
                        minimap_height = mm_img.height
                except Exception:
                    pass
            elev_y = OVERLAY_MARGIN + minimap_height + 10
            filters.append(
                f"{current_stream}[{elev_idx}:v]overlay=W-w-{OVERLAY_MARGIN}:{elev_y}[velev]"
            )
            current_stream = "[velev]"

        # PR Trophy badge overlay (top-left, only for Strava PR clips)
        if str(main_row.get("strava_pr", "false")).lower() == "true":
            segment_name = main_row.get("segment_name", "PR Segment")
            # Parse segment details for badge display
            try:
                segment_distance = float(main_row.get("segment_distance", 0) or 0)
            except (ValueError, TypeError):
                segment_distance = 0
            try:
                segment_grade = float(main_row.get("segment_grade", 0) or 0)
            except (ValueError, TypeError):
                segment_grade = 0

            trophy_path = _mk(trophy_dir()) / f"trophy_{clip_idx:04d}.png"
            try:
                create_trophy_overlay(
                    segment_name,
                    trophy_path,
                    distance_m=segment_distance,
                    grade_pct=segment_grade,
                )
                inputs.extend(["-loop", "1", "-t", f"{duration:.3f}", "-i", str(trophy_path)])
                trophy_idx = len([a for a in inputs if a == "-i"]) - 1
                # Position: top-left with same margin as minimap
                filters.append(
                    f"{current_stream}[{trophy_idx}:v]overlay={CFG.MINIMAP_MARGIN}:{CFG.MINIMAP_MARGIN}[vtrophy]"
                )
                current_stream = "[vtrophy]"
                log.debug(f"[clip] Added PR badge for clip {clip_idx}: {segment_name}")
            except Exception as e:
                log.warning(f"[clip] Failed to create trophy badge for clip {clip_idx}: {e}")

        # Composite gauge overlay (single pre-rendered PNG at bottom-left)
        current_stream = self._add_gauge_overlay(
            filters, inputs, current_stream, gauge_path, duration
        )

        return inputs, filters, current_stream

    def _add_gauge_overlay(
        self,
        filters: List[str],
        inputs: List[str],
        current_stream: str,
        gauge_path: Optional[Path],
        duration: float,
    ) -> str:
        """Add single composite gauge overlay to filter chain."""
        if not gauge_path or not gauge_path.exists():
            return current_stream

        inputs.extend(
            ["-loop", "1", "-t", f"{duration:.3f}", "-i", str(gauge_path)]
        )
        idx_in = len([a for a in inputs if a == "-i"]) - 1

        # Position at bottom-left with HUD_PADDING
        x, y = CFG.HUD_PADDING
        filters.append(
            f"{current_stream}[{idx_in}:v]overlay={x}:H-h-{y}[vhud]"
        )

        return "[vhud]"

    def _build_encode_command(
        self,
        inputs: List[str],
        filters: List[str],
        final_stream: str,
        output_path: Path,
    ) -> List[str]:
        """Build complete ffmpeg encoding command with optimal hardware acceleration."""
        cmd = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y"]

        # Add hardware acceleration for decoding on Apple Silicon
        if is_apple_silicon() and CFG.FFMPEG_HWACCEL == "videotoolbox":
            cmd.extend(["-hwaccel", "videotoolbox"])

        cmd.extend(inputs)

        if filters:
            filter_str = ";".join(filters)
            cmd.extend(["-filter_complex", filter_str, "-map", final_stream])
        else:
            cmd.extend(["-map", "0:v"])

        # Select optimal video codec based on hardware and config
        if CFG.PREFERRED_CODEC == 'auto':
            video_codec = get_optimal_video_codec()
        else:
            video_codec = CFG.PREFERRED_CODEC

        cmd.extend(
            [
                "-c:v",
                video_codec,
                "-b:v",
                CFG.BITRATE,
                "-maxrate",
                CFG.MAXRATE,
                "-bufsize",
                CFG.BUFSIZE,
                "-pix_fmt",
                "yuv420p",
                str(output_path),
            ]
        )

        return cmd

    def _mux_audio(
        self,
        video_path: Path,
        source_video: Path,
        t_start: float,
        duration: float,
        clip_idx: int,
    ) -> Optional[Path]:
        """Mux camera audio into rendered clip."""
        try:
            temp_path = video_path.with_suffix(".mux.mp4")
            mux_audio(video_path, source_video, temp_path, t_start, duration)
            temp_path.replace(video_path)
            return video_path
        except Exception as e:
            log.warning(f"[clip] Audio mux failed for clip {clip_idx}: {e}")
            return video_path  # Return video without audio

    @staticmethod
    def _anchor_expr(anchor: str, margin: int) -> str:
        """Generate ffmpeg overlay position expression."""
        anchors = {
            "top_right": f"W-w-{margin}:{margin}",
            "top_left": f"{margin}:{margin}",
            "bottom_right": f"W-w-{margin}:H-h-{margin}",
            "bottom_left": f"{margin}:H-h-{margin}",
        }
        return anchors.get(anchor, f"W-w-{margin}:{margin}")