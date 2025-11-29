# source/steps/build.py
"""
Render highlight clips with overlays (PiP, minimap, gauges).
Produces individual clips and concatenates them into _middle.mp4 with underscore music.
"""

from __future__ import annotations
import csv
import subprocess
from pathlib import Path
from typing import Dict
from source.utils.progress_reporter import progress_iter

from ..config import DEFAULT_CONFIG as CFG
from ..io_paths import select_path, clips_dir, minimap_dir, gauge_dir, _mk
from ..utils import gauge_overlay
from ..utils.log import setup_logger
from ..utils.gpx import load_gpx, GpxPoint
from ..utils.ffmpeg import mux_audio
from ..utils.map_overlay import render_overlay_minimap
from ..utils.music import create_music_track_manager

log = setup_logger("steps.build")

AUDIO_SAMPLE_RATE = "48000"

# --- Video encoding constants ---
VIDEO_CODEC_OPTS = {
    "codec": lambda: CFG.VIDEO_CODEC,
    "bitrate": lambda: CFG.BITRATE,
    "maxrate": lambda: CFG.MAXRATE,
    "bufsize": lambda: CFG.BUFSIZE,
    "pix_fmt": "yuv420p",
}

def _run_ffmpeg_command(args: list, description: str = "") -> None:
    """Run ffmpeg command with consistent logging."""
    if description:
        log.debug(f"[build] {description}")
    subprocess.run(args, check=True)

def _prerender_minimaps(rows: list[dict], gpx_points: list[GpxPoint], out_dir: Path) -> Dict[int, Path]:
    """Pre-render all minimaps for selected clips (old style: per clip)."""
    if not gpx_points:
        return {}
    
    log.info(f"[build] Pre-rendering {len(rows)} minimaps...")
    minimap_paths: Dict[int, Path] = {}
    
    for idx, r in enumerate(progress_iter(rows, desc="Rendering minimaps", unit="map"), start=1):
        try:
            gpx_epoch = r.get("gpx_epoch")
            if not gpx_epoch:
                continue
            epoch = float(gpx_epoch)
            img = render_overlay_minimap(gpx_points, epoch)
            mpath = out_dir / f"minimap_{idx:04d}.png"
            img.save(mpath)
            minimap_paths[idx] = mpath
        except Exception as e:
            log.warning(f"[build] minimap {idx} failed: {e}")
    
    log.info(f"[build] Pre-rendered {len(minimap_paths)} minimaps")
    return minimap_paths

def _anchor_expr(anchor: str, margin: int) -> str:
    """Generate ffmpeg overlay position expression for anchored elements."""
    if anchor == "top_right":
        return f"W-w-{margin}:{margin}"
    if anchor == "top_left":
        return f"{margin}:{margin}"
    if anchor == "bottom_right":
        return f"W-w-{margin}:H-h-{margin}"
    if anchor == "bottom_left":
        return f"{margin}:H-h-{margin}"
    return f"W-w-{margin}:{margin}"

def _calculate_gauge_positions(padding: tuple, speed_gauge_size: int, small_gauge_size: int) -> Dict[str, tuple]:
    """HUD layout anchored bottom-left: radial cluster around speed gauge."""
    gx, gy = padding
    SPACING = 20
    OVERLAP = 15

    speed = speed_gauge_size
    small = small_gauge_size

    # Speed gauge bottom-left anchor
    speed_x = gx + small - OVERLAP + SPACING
    speed_y = f"H - {gy} - {speed}"

    # Small gauges around speed
    top_y = f"{speed_y}"
    bottom_y = f"{speed_y} + {speed - small}"
    right_x = f"{speed_x} + {speed - OVERLAP} + {SPACING}"
    left_x = f"{speed_x} - {small} + {OVERLAP}"

    positions = {
        "speed": (f"{speed_x}", f"H - h - {gy}"),
        "hr": (left_x, top_y),
        "cadence": (right_x, top_y),
        "elev": (left_x, bottom_y),
        "gradient": (right_x, bottom_y),
    }

    return positions

def run() -> Path:
    """Render all highlight clips and create _middle.mp4."""
    out_dir = _mk(clips_dir())
    p = select_path()
    
    if not p.exists():
        log.warning("[build] select.csv missing")
        return out_dir
    
    with p.open() as f:
        rows = list(csv.DictReader(f))
    
    # Filter only recommended clips
    rows = [r for r in rows if r.get("recommended", "false").lower() == "true"]

    if not rows:
        log.warning("[build] empty or no recommended clips in select.csv")
        return out_dir

    # Load GPX points once
    try:
        gpx_points = load_gpx(str(CFG.INPUT_GPX_FILE))
        log.info(f"[build] GPX {len(gpx_points)} pts")
    except Exception as e:
        log.warning(f"[build] no GPX minimap: {e}")
        gpx_points = []

    minimap_path = _mk(minimap_dir())
    gauge_path = _mk(gauge_dir())

    # Pre-render minimaps
    minimap_paths = _prerender_minimaps(rows, gpx_points, minimap_path)
    
    # Compute gauge maxes
    gauge_maxes = gauge_overlay.compute_gauge_maxes(select_path())

    # Build individual clips
    individual_clips = []
    
    # Use progress_iter with better description
    for idx, r in enumerate(progress_iter(rows, desc="Encoding clips", unit="clip"), start=1):
        try:
            main_video = CFG.INPUT_VIDEOS_DIR / r["source"]
            partner_video = (CFG.INPUT_VIDEOS_DIR / r["partner_source"]) if r.get("partner_source") else None
            t_start = max(0.0, float(r.get("session_ts_s", 0) or 0) - CFG.CLIP_PRE_ROLL_S)
            duration = CFG.CLIP_OUT_LEN_S
            out_fp = out_dir / f"clip_{idx:04d}.mp4"

            inputs: list[str] = ["-ss", f"{t_start:.3f}", "-t", f"{duration:.3f}", "-i", str(main_video)]
            filters: list[str] = []
            cur = "[0:v]"

            # PiP
            if partner_video and partner_video.exists():
                inputs += ["-ss", f"{t_start:.3f}", "-t", f"{duration:.3f}", "-i", str(partner_video)]
                filters.append(
                    f"[1:v]scale=iw*{CFG.PIP_SCALE_RATIO}:-1[pip];"
                    f"{cur}[pip]overlay=W-w-{CFG.PIP_MARGIN}:H-h-{CFG.PIP_MARGIN}[v1]"
                )
                cur = "[v1]"

            # Minimap overlay
            if idx in minimap_paths:
                mpath = minimap_paths[idx]
                inputs += ["-i", str(mpath)]
                minimap_idx = len([a for a in inputs if a == "-i"]) - 1
                overlay_expr = _anchor_expr(CFG.MINIMAP_ANCHOR, CFG.MINIMAP_MARGIN)
                filters.append(f"{cur}[{minimap_idx}:v]overlay={overlay_expr}[vmap]")
                cur = "[vmap]"

            # Gauges
            telemetry = {
                "speed": [float(r.get("speed_kmh") or 0.0)],
                "cadence": [float(r.get("cadence_rpm") or 0.0)],
                "hr": [float(r.get("hr_bpm") or 0.0)],
                "elev": [float(r.get("elevation") or 0.0)],
                "gradient": [float(r.get("gradient_pct") or 0.0)],
            }
            clip_gauge_path = _mk(gauge_path / f"clip_{idx:04d}")
            
            try:
                gauge_images = gauge_overlay.create_all_gauge_images(
                    telemetry, gauge_maxes, clip_gauge_path, idx
                )
            except Exception as e:
                log.error(f"[build] Gauge creation failed for clip {idx}: {e}")
                gauge_images = {}

            positions = _calculate_gauge_positions(
                padding=CFG.HUD_PADDING,
                speed_gauge_size=gauge_overlay.SPEED_GAUGE_SIZE,
                small_gauge_size=gauge_overlay.SMALL_GAUGE_SIZE,
            )
            
            for gtype, (x_expr, y_expr) in positions.items():
                gpath = gauge_images.get(gtype)
                if not gpath:
                    continue
                inputs += ["-loop", "1", "-t", f"{duration:.3f}", "-i", str(gpath)]
                idx_in = len([a for a in inputs if a == "-i"]) - 1
                filters.append(f"{cur}[{idx_in}:v]overlay={x_expr}:{y_expr}[vhud]")
                cur = "[vhud]"

            # Assemble ffmpeg command
            cmd = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", *inputs]
            if filters:
                cmd += ["-filter_complex", ";".join(filters), "-map", cur]
            else:
                cmd += ["-map", "0:v"]
            
            # Add video encoding parameters
            cmd += [
                "-c:v", CFG.VIDEO_CODEC,
                "-b:v", CFG.BITRATE,
                "-maxrate", CFG.MAXRATE,
                "-bufsize", CFG.BUFSIZE,
                "-pix_fmt", "yuv420p",
                str(out_fp),
            ]
            _run_ffmpeg_command(cmd, f"Encoding clip {idx:04d} with overlays")

            # Best-effort audio mux
            try:
                tmp = out_fp.with_suffix(".mux.mp4")
                mux_audio(out_fp, main_video, tmp, t_start, duration)
                tmp.replace(out_fp)
                individual_clips.append(out_fp)
            except Exception as e:
                log.warning(f"[build] audio mux failed for clip {idx}: {e}")
                if tmp and tmp.exists():
                    tmp.unlink()

        except Exception as e:
            log.error(f"[build] failed row {idx}: {e}", exc_info=True)

    # Concatenate clips into multiple ~30s segments
    if individual_clips:
        highlights_per_segment = int(30.0 // CFG.CLIP_OUT_LEN_S)
        num_segments = (len(individual_clips) + highlights_per_segment - 1) // highlights_per_segment
        log.info(f"[build] Concatenating into {num_segments} × 30s segments...")

        for seg_idx in range(num_segments):
            start = seg_idx * highlights_per_segment
            end = min(start + highlights_per_segment, len(individual_clips))
            segment_clips = individual_clips[start:end]

            if not segment_clips:
                continue

            concat_list = CFG.WORKING_DIR / f"middle_list_{seg_idx+1:02d}.txt"
            _mk(concat_list.parent)
            with concat_list.open("w") as f:
                for clip in segment_clips:
                    f.write(f"file '{clip.resolve()}'\n")

            middle_raw = CFG.FINAL_REEL_PATH.parent/ f"_middle_raw_{seg_idx+1:02d}.mp4"
            middle_final = CFG.FINAL_REEL_PATH.parent / f"_middle_{seg_idx+1:02d}.mp4"

            # Concatenate segment clips
            concat_cmd = [
                "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
                "-f", "concat", "-safe", "0", "-i", str(concat_list),
                "-c", "copy", str(middle_raw)
            ]
            _run_ffmpeg_command(concat_cmd, f"Concatenating segment {seg_idx+1}")

            # Apply music overlay
            music_manager = create_music_track_manager(CFG)
            music_track = music_manager.get_track_path()

            if music_track and music_track.exists():
                audio_cmd = [
                    "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
                    "-i", str(middle_raw),
                    "-stream_loop", "-1", "-i", str(music_track),
                    "-filter_complex",
                    f"[0:a]volume={CFG.RAW_AUDIO_VOLUME}[raw];"
                    f"[1:a]volume={CFG.MUSIC_VOLUME}[music];"
                    f"[raw][music]amix=inputs=2:dropout_transition=0[out]",
                    "-map", "0:v", "-map", "[out]",
                    "-c:v", "copy", "-c:a", "aac", "-ar", AUDIO_SAMPLE_RATE,
                    "-shortest", str(middle_final)
                ]
                _run_ffmpeg_command(audio_cmd, f"Adding music to segment {seg_idx+1}: {music_track.name}")
            else:
                log.warning("[build] No music tracks found, creating video-only segment")
                audio_cmd = [
                    "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
                    "-i", str(middle_raw),
                    "-c", "copy", str(middle_final)
                ]
                _run_ffmpeg_command(audio_cmd, f"Creating segment {seg_idx+1} without music")

            # Clean up temp files
            try:
                middle_raw.unlink()
                concat_list.unlink()
            except Exception as e:
                log.debug(f"[build] cleanup warning: {e}")

            log.info(f"[build] Created {middle_final}")

    return out_dir

if __name__ == "__main__":
    run()