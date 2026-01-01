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
from ...utils.common import parse_iso_time
from ...io_paths import _mk
from .gauge_renderer import GaugeRenderer

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
        gauge_renderer: GaugeRenderer,
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
            duration=duration,
            main_row=main_row,
            clip_idx=clip_idx,
            gauge_renderer=gauge_renderer,
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

        Args:
            row: CSV row containing abs_time_epoch and adjusted_start_time
            clip_idx: Clip number (for logging)
            camera_role: "main" or "pip" (for logging)

        Returns:
            t_start in seconds, or None if calculation fails
        """
        try:
            # World-aligned timestamp of the moment
            abs_epoch = float(row.get("abs_time_epoch", 0.0) or 0.0)

            # Clip start time (UTC) from extract.py
            start_iso = row.get("adjusted_start_time")
            if not start_iso:
                raise ValueError(f"adjusted_start_time missing in {camera_role}_row")

            # Parse ISO timestamp using shared utility
            clip_start_dt = parse_iso_time(start_iso)
            if clip_start_dt is None:
                raise ValueError(f"Could not parse adjusted_start_time: {start_iso}")
            clip_start_epoch = clip_start_dt.timestamp()

            # Offset of this moment inside the source clip
            offset_in_clip = abs_epoch - clip_start_epoch
            if offset_in_clip < 0:
                log.warning(
                    f"[clip] Negative offset_in_clip ({offset_in_clip:.3f}s) "
                    f"for {camera_role} camera in clip {clip_idx:04d} ({row.get('source')})"
                )
                offset_in_clip = 0.0

            # Apply pre-roll in clip-local time
            t_start = max(0.0, offset_in_clip - CFG.CLIP_PRE_ROLL_S)

            # Optional: sanity check vs clip's reported duration
            try:
                clip_duration_s = float(row.get("duration_s", 0.0) or 0.0)
                if clip_duration_s > 0 and t_start >= clip_duration_s:
                    log.error(
                        f"[clip] t_start={t_start:.3f}s beyond clip duration "
                        f"{clip_duration_s:.3f}s for {camera_role} camera "
                        f"({row.get('source')}) in clip_idx={clip_idx}"
                    )
                    return None
            except Exception:
                pass

            return t_start

        except Exception as e:
            log.error(
                f"[clip] Failed to compute t_start for {camera_role} camera "
                f"in clip {clip_idx}: {e}"
            )
            return None

    def _build_ffmpeg_inputs_and_filters(
        self,
        main_video: Path,
        pip_video: Optional[Path],
        t_start_main: float,
        t_start_pip: float,
        minimap_path: Optional[Path],
        duration: float,
        main_row: Dict,
        clip_idx: int,
        gauge_renderer: GaugeRenderer,
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

        # Minimap overlay
        if minimap_path and minimap_path.exists():
            inputs.extend(["-i", str(minimap_path)])
            minimap_idx = len([a for a in inputs if a == "-i"]) - 1
            overlay_expr = self._anchor_expr(CFG.MINIMAP_ANCHOR, CFG.MINIMAP_MARGIN)
            filters.append(f"{current_stream}[{minimap_idx}:v]overlay={overlay_expr}[vmap]")
            current_stream = "[vmap]"

        # Gauge overlays (based on main camera telemetry)
        current_stream = self._add_gauge_overlays(
            filters, inputs, current_stream, main_row, clip_idx, duration, gauge_renderer
        )

        return inputs, filters, current_stream

    def _add_gauge_overlays(
        self,
        filters: List[str],
        inputs: List[str],
        current_stream: str,
        main_row: Dict,
        clip_idx: int,
        duration: float,
        gauge_renderer: GaugeRenderer,
    ) -> str:
        """Add gauge overlays to filter chain."""
        gauge_images = gauge_renderer.render_gauges_for_clip(main_row, clip_idx)

        if not gauge_images:
            return current_stream

        positions = gauge_renderer.calculate_gauge_positions(CFG.HUD_PADDING)

        for gauge_type, (x_expr, y_expr) in positions.items():
            gauge_path = gauge_images.get(gauge_type)
            if not gauge_path or not gauge_path.exists():
                continue

            inputs.extend(
                ["-loop", "1", "-t", f"{duration:.3f}", "-i", str(gauge_path)]
            )
            idx_in = len([a for a in inputs if a == "-i"]) - 1
            filters.append(
                f"{current_stream}[{idx_in}:v]overlay={x_expr}:{y_expr}[vhud]"
            )
            current_stream = "[vhud]"

        return current_stream

    def _build_encode_command(
        self,
        inputs: List[str],
        filters: List[str],
        final_stream: str,
        output_path: Path,
    ) -> List[str]:
        """Build complete ffmpeg encoding command."""
        cmd = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", *inputs]

        if filters:
            filter_str = ";".join(filters)
            cmd.extend(["-filter_complex", filter_str, "-map", final_stream])
        else:
            cmd.extend(["-map", "0:v"])

        cmd.extend(
            [
                "-c:v",
                CFG.VIDEO_CODEC,
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