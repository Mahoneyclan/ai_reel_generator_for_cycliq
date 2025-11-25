# source/steps/splash.py
"""
Splash step: produces _intro.mp4 and _outro.mp4.
Intro: logo → map+banner → flip → collage (with intro.mp3 soundtrack).
Outro: collage → text → logo → black (with outro.mp3 soundtrack).
"""

from __future__ import annotations
import csv
import math
import subprocess
import json
from pathlib import Path
from typing import Tuple, List
from PIL import Image, ImageDraw, ImageFont

from ..config import DEFAULT_CONFIG as CFG
from ..io_paths import select_path, clips_dir, splash_assets_dir, _mk
from ..utils.log import setup_logger
from ..utils.gpx import load_gpx, compute_stats
from ..utils.map_overlay import render_splash_map_with_xy

log = setup_logger("steps.splash")

# --- Configuration Constants ---
AUDIO_SAMPLE_RATE = "48000"

# Canvas constants
OUT_W, OUT_H, FPS = 2560, 1440, 30
BANNER_HEIGHT = 220
TITLE_FONT_SIZE = 80
STATS_FONT_SIZE = 55
FONT_FILE = "/Library/Fonts/Arial.ttf"

# Outro constants
OUTRO_DURATION_S = 3.7
OUTRO_TITLE_TEXT = "Velo Films"
OUTRO_TITLE_APPEAR_T, OUTRO_TITLE_FADEIN_D = 1.0, 0.5
OUTRO_FADEOUT_START_T, OUTRO_FADEOUT_D = 3.0, 0.7

# Asset names
OPEN_COLLAGE_NAME = "splash_open_collage.png"
CLOSE_COLLAGE_NAME = "close_splash_collage.png"
OPEN_LOGO_MP4 = "splash_open_logo.mp4"
OPEN_MAP_MP4 = "splash_open_map.mp4"
OPEN_FLIP_MP4 = "splash_open_flip.mp4"
OPEN_COLLAGE_MP4 = "splash_open_collage.mp4"
CLOSE_COLLAGE_MP4 = "splash_close_collage.mp4"
CLOSE_LOGO_MP4 = "splash_close_logo.mp4"
CLOSE_BLACK_MP4 = "splash_close_black.mp4"
INTRO_TEMP_MP4 = "_intro_temp.mp4"
OUTRO_TEMP_MP4 = "_outro_temp.mp4"

# Logo asset
LOGO_PATH = CFG.PROJECT_ROOT / "assets" / "velo_films.png"

# Track temp files created during splash generation (for cleanup)
_temp_files: list[Path] = []


# --- Utilities ---

def _run_ffmpeg(cmd: List[str]):
    """Run ffmpeg with logging and error reporting."""
    log.debug(f"[splash] ffmpeg: {' '.join(cmd)}")
    subprocess.run(cmd, check=True)


def _create_video_clip(input_source: Path | str, duration: float, output_path: Path,
                      filter_vf: str = "", duration_type: str = "loop") -> Path:
    """Create a video clip from an image or color source."""
    _temp_files.append(output_path)

    cmd = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y"]

    if duration_type == "loop":
        cmd.extend(["-loop", "1", "-t", f"{duration:.2f}", "-framerate", str(FPS),
                   "-i", str(input_source)])
    else:
        cmd.extend(["-f", "lavfi", "-i", str(input_source)])

    # Add silent audio
    cmd.extend(["-f", "lavfi", "-i", f"anullsrc=channel_layout=stereo:sample_rate={AUDIO_SAMPLE_RATE}",
               "-shortest"])

    if filter_vf:
        cmd.extend(["-vf", filter_vf])

    cmd.extend(["-map", "0:v", "-map", "1:a",
               "-c:v", CFG.VIDEO_CODEC, "-b:v", CFG.BITRATE, "-pix_fmt", "yuv420p",
               "-c:a", "aac", "-ar", AUDIO_SAMPLE_RATE, "-ac", "2", str(output_path)])

    log.debug(f"[splash] Creating {output_path.name} with duration {duration:.2f}s")
    _run_ffmpeg(cmd)
    return output_path

def _safe_font(size: int):
    try:
        return ImageFont.truetype(FONT_FILE, size)
    except Exception:
        return ImageFont.load_default()

def _read_csv_rows(p: Path) -> list[dict]:
    if not p.exists():
        return []
    with p.open() as f:
        return list(csv.DictReader(f))

def _select_rows() -> list[dict]:
    return _read_csv_rows(select_path())

def _get_video_duration(video_path: Path) -> float:
    try:
        result = subprocess.run([
            "ffprobe", "-v", "quiet", "-print_format", "json",
            "-show_entries", "format=duration", str(video_path)
        ], capture_output=True, text=True, check=True)
        data = json.loads(result.stdout)
        return float(data.get("format", {}).get("duration", 0))
    except Exception:
        return 0.0

def _add_music_to_video(video_path: Path, music_path: Path, output_path: Path):
    """Add music track to video with duration matched to video."""
    if not music_path.exists():
        log.warning(f"[splash] Music file not found: {music_path}, skipping audio overlay")
        subprocess.run(["cp", str(video_path), str(output_path)], check=True)
        return

    duration = _get_video_duration(video_path)
    if duration == 0:
        log.warning(f"[splash] Could not determine video duration for {video_path}")
        subprocess.run(["cp", str(video_path), str(output_path)], check=True)
        return

    log.info(f"[splash] Adding {music_path.name} to {video_path.name} (duration: {duration:.2f}s)")

    _run_ffmpeg([
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
        "-i", str(video_path),
        "-i", str(music_path),
        "-filter_complex", "[1:a]volume=1.0[music]",
        "-map", "0:v", "-map", "[music]",
        "-t", f"{duration:.3f}",
        "-c:v", "copy",
        "-c:a", "aac", "-ar", AUDIO_SAMPLE_RATE, "-ac", "2",
        str(output_path)
    ])

def _collect_main_frames() -> list[Path]:
    """Collect frames for recommended clips, using index + Primary/Partner suffix."""
    select_csv = select_path()
    if not select_csv.exists():
        log.warning("[splash] select.csv not found, falling back to all frames")
        return sorted(CFG.FRAMES_DIR.glob("*.jpg"))

    try:
        rows = list(csv.DictReader(select_csv.open()))
    except Exception as e:
        log.error(f"[splash] Failed to read select.csv: {e}")
        return []

    recommended_rows = [r for r in rows if r.get("recommended") == "true"]
    if not recommended_rows:
        log.warning("[splash] No recommended clips found in select.csv")
        return []

    frame_pairs = []
    partner_count = 0

    for row in recommended_rows:
        idx = row["index"]
        epoch = float(row.get("abs_time_epoch", 0) or 0.0)

        # Primary frame
        primary_path = CFG.FRAMES_DIR / f"{idx}_Primary.jpg"
        if primary_path.exists():
            frame_pairs.append((epoch, primary_path))
            log.debug(f"[splash] ✓ Found primary: {primary_path.name}")
        else:
            log.warning(f"[splash] ✗ Primary frame missing: {primary_path}")

        # Partner frame (always use same index + _Partner)
        partner_path = CFG.FRAMES_DIR / f"{idx}_Partner.jpg"
        if partner_path.exists():
            frame_pairs.append((epoch, partner_path))
            partner_count += 1
            log.info(f"[splash] ✓ Found partner: {partner_path.name}")
        else:
            log.debug(f"[splash] No partner frame for {idx}")

    frame_pairs.sort(key=lambda x: x[0])
    frames = [path for _, path in frame_pairs]

    log.info(f"[splash] Collected {len(frames)} frames "
             f"({len(frames) - partner_count} primary + {partner_count} partner) "
             f"from {len(recommended_rows)} recommended clips")
    return frames

# --- Collage helpers ---

def _grid_for_n(n: int, w: int, h: int) -> tuple[int, int]:
    if n <= 0:
        return 1, 1
    ratio = w / h
    cols = max(1, int(round(math.sqrt(n * ratio))))
    rows = max(1, math.ceil(n / cols))
    while cols * rows < n:
        cols += 1
        rows = math.ceil(n / cols)
    return cols, rows

def _collage_image(w: int, h: int, files: list[Path]) -> Image.Image:
    if not files:
        return Image.new("RGB", (w, h), (20, 20, 20))

    cols, rows = _grid_for_n(len(files), w, h)
    tile_w, tile_h = w // cols, h // rows
    canvas = Image.new("RGB", (w, h), (8, 8, 8))

    idx = 0
    for r in range(rows):
        for c in range(cols):
            if idx >= len(files):
                break
            try:
                src = Image.open(files[idx]).convert("RGB")
            except Exception:
                src = Image.new("RGB", (tile_w, tile_h), (0, 0, 0))
            tile = src.resize((tile_w, tile_h), Image.Resampling.LANCZOS)
            canvas.paste(tile, (c * tile_w, r * tile_h))
            idx += 1

    return canvas

# --- Closing splash (outro) ---

def _build_outro_sequence(collage_png: Path):
    """Build the outro sequence: collage with text fade → logo → black → concat → music."""
    # Use splash_assets_dir for temporary clips
    assets = _mk(splash_assets_dir())

    # Collage outro with "Velo Films" text + fade
    outro_collage = assets / CLOSE_COLLAGE_MP4
    _temp_files.append(outro_collage)

    alpha = (
        f"if(lt(t,{OUTRO_TITLE_APPEAR_T}),0,"
        f" if(lt(t,{OUTRO_TITLE_APPEAR_T + OUTRO_TITLE_FADEIN_D}),"
        f"(t-{OUTRO_TITLE_APPEAR_T})/{OUTRO_TITLE_FADEIN_D},1))"
    )
    draw = (
        "drawtext="
        f"fontfile='{FONT_FILE}':text='{OUTRO_TITLE_TEXT}':"
        "x=(w-text_w)/2:y=(h-text_h)/2:fontsize=160:fontcolor=white:"
        "bordercolor=black@0.45:borderw=6:shadowcolor=black@0.7:shadowx=4:shadowy=4:"
        f"alpha='{alpha}'"
    )
    fade = f"fade=t=out:st={OUTRO_FADEOUT_START_T}:d={OUTRO_FADEOUT_D}:alpha=0"
    vf = (
        f"scale={OUT_W}:{OUT_H}:force_original_aspect_ratio=decrease,"
        f"pad={OUT_W}:{OUT_H}:(ow-iw)/2:(oh-ih)/2,{draw},{fade}"
    )

    _run_ffmpeg([
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
        "-loop", "1", "-t", f"{OUTRO_DURATION_S:.2f}", "-framerate", str(FPS),
        "-i", str(collage_png),
        "-f", "lavfi", "-i", f"anullsrc=channel_layout=stereo:sample_rate={AUDIO_SAMPLE_RATE}", "-shortest",
        "-vf", vf, "-map", "0:v", "-map", "1:a",
        "-c:v", CFG.VIDEO_CODEC, "-b:v", CFG.BITRATE, "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-ar", AUDIO_SAMPLE_RATE, "-ac", "2", str(outro_collage)
    ])

    # Logo still
    logo_clip = assets / CLOSE_LOGO_MP4
    _create_video_clip(
        LOGO_PATH,
        duration=2.0,
        output_path=logo_clip,
        filter_vf="scale=2560:1440:force_original_aspect_ratio=decrease,"
                  "pad=2560:1440:(ow-iw)/2:(oh-ih)/2:black"
    )

    # Black screen
    black_clip = assets / CLOSE_BLACK_MP4
    _create_video_clip(
        f"color=c=black:s={OUT_W}x{OUT_H}:d=2",
        duration=2.0,
        output_path=black_clip,
        duration_type="color"
    )

    # Concat: collage → logo → black
    concat_list = assets / "splash_close_concat.txt"
    _temp_files.append(concat_list)
    concat_list.write_text(
        f"file '{outro_collage}'\n"
        f"file '{logo_clip}'\n"
        f"file '{black_clip}'\n"
    )
    temp_out = assets / OUTRO_TEMP_MP4
    _temp_files.append(temp_out)
    _run_ffmpeg([
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
        "-f", "concat", "-safe", "0", "-i", str(concat_list), "-c", "copy", str(temp_out)
    ])

    # Add outro.mp3 music track - output to PROJECT_DIR
    outro_final = CFG.PROJECT_DIR / "_outro.mp4"
    _add_music_to_video(temp_out, CFG.OUTRO_MUSIC, outro_final)
    log.info(f"[splash] wrote {outro_final}")
    return outro_final

def run_closing() -> Tuple[tuple[int, int, int, int], list[Path]]:
    """Generate _outro.mp4 and return grid info + files for opening."""
    # Collect main-camera frame files
    files: list[Path] = _collect_main_frames()
    log.info(f"[splash] Using {len(files)} main camera frames for collage")

    n = len(files)
    cols, rows_n = _grid_for_n(n, OUT_W, OUT_H - BANNER_HEIGHT)
    tile_w, tile_h = OUT_W // cols, (OUT_H - BANNER_HEIGHT) // rows_n

    # Build and persist collage image
    collage = _collage_image(OUT_W, OUT_H - BANNER_HEIGHT, files)
    assets = _mk(splash_assets_dir())
    cpath = assets / CLOSE_COLLAGE_NAME
    collage.save(cpath, quality=95)
    log.info(f"[splash] wrote outro collage {cpath}")

    # Build outro sequence
    _build_outro_sequence(cpath)

    # Return grid info for opening splash
    return (cols, rows_n, tile_w, tile_h), files

# --- Opening splash (intro) ---

def _compose_map_only_canvas(stats) -> Image.Image:
    """Create opening map canvas with ride banner."""
    canvas = Image.new("RGB", (OUT_W, OUT_H), (0, 0, 0))
    draw = ImageDraw.Draw(canvas, "RGBA")

    # Banner background
    draw.rectangle([0, 0, OUT_W, BANNER_HEIGHT], fill=(0, 0, 0, 200))

    # Ride title
    ride_name = CFG.RIDE_FOLDER
    title_font = _safe_font(TITLE_FONT_SIZE)
    tw = int(draw.textlength(ride_name, font=title_font))
    draw.text(((OUT_W - tw) // 2, 30), ride_name, font=title_font, fill=(255, 255, 255))

    # Stats line
    banner_text = ""
    if stats:
        d_s = int(stats.get("duration_s", 0))
        h = d_s // 3600
        m = (d_s % 3600) // 60
        banner_text = (
            f"Distance: {stats.get('distance_km', 0):.1f} km   "
            f"Duration: {h}h {m}m   "
            f"Avg: {stats.get('avg_speed', 0):.1f} km/h   "
            f"Ascent: {stats.get('total_climb_m', 0):.0f} m"
        )
    stats_font = _safe_font(STATS_FONT_SIZE)
    tw2 = int(draw.textlength(banner_text, font=stats_font))
    draw.text(((OUT_W - tw2) // 2, 120), banner_text, font=stats_font, fill=(255, 255, 255))

    # Map overlay
    gpx_pts = load_gpx(str(CFG.INPUT_GPX_FILE))
    if not gpx_pts:
        raise RuntimeError(f"[splash] GPX file {CFG.INPUT_GPX_FILE} loaded but no points found")

    base, _ = render_splash_map_with_xy(gpx_pts, gutters_px=(0, 0, 0, 0))
    base = base.resize((OUT_W, OUT_H - BANNER_HEIGHT))
    canvas.paste(base, (0, BANNER_HEIGHT))
    return canvas

def _tiles_for_grid(base_img: Image.Image, files: list[Path], grid_info):
    """Extract map tiles and frame tiles for flip animation."""
    cols, rows, tile_w, tile_h = grid_info

    # Map tiles cut from base image
    map_tiles = []
    for r in range(rows):
        for c in range(cols):
            x0 = c * tile_w
            y0 = BANNER_HEIGHT + r * tile_h
            tile = base_img.crop((x0, y0, x0 + tile_w, y0 + tile_h))
            map_tiles.append(tile)

    # Frame tiles from input frames
    frame_tiles = []
    idx = 0
    total_slots = cols * rows
    for s in range(total_slots):
        if idx < len(files):
            try:
                src = Image.open(files[idx]).convert("RGB")
            except Exception:
                src = Image.new("RGB", (tile_w, tile_h), (0, 0, 0))
            frame_tiles.append(src.resize((tile_w, tile_h), Image.Resampling.LANCZOS))
            idx += 1
        else:
            frame_tiles.append(None)
    return map_tiles, frame_tiles

def _render_flip_frames(base_img: Image.Image, grid_info, map_tiles, frame_tiles,
                        flip_duration_s=1.2, fps=FPS):
    """Render flip animation frames."""
    cols, rows, tile_w, tile_h = grid_info
    n_frames = max(1, int(round(flip_duration_s * fps)))
    frames = []
    slots = [(c, r, c * tile_w, BANNER_HEIGHT + r * tile_h)
             for r in range(rows) for c in range(cols)]

    for i in range(n_frames):
        t = i / (n_frames - 1) if n_frames > 1 else 1.0
        half = 0.5
        if t <= half:
            sx = 1.0 - (t / half)
            use_map = True
        else:
            sx = (t - half) / half
            use_map = False

        frame = base_img.copy()
        for s_idx, (c, r, x0, y0) in enumerate(slots):
            tile_src = map_tiles[s_idx] if use_map or frame_tiles[s_idx] is None else frame_tiles[s_idx]
            if tile_src is None:
                continue
            w_scaled = max(1, int(round(tile_w * sx)))
            if w_scaled == tile_w:
                frame.paste(tile_src, (x0, y0))
            else:
                tile_scaled = tile_src.resize((w_scaled, tile_h), Image.Resampling.LANCZOS)
                x_center = x0 + (tile_w - w_scaled) // 2
                frame.paste(tile_scaled, (x_center, y0))
        frames.append(frame)
    return frames

def _encode_frames_to_clip(frames: list[Image.Image], out_fp: Path, fps=FPS):
    """Encode frame sequence to video clip."""
    tmp_dir = _mk(splash_assets_dir() / "flip_frames")
    _temp_files.append(tmp_dir)
    for idx, img in enumerate(frames):
        frame_path = tmp_dir / f"flip_{idx:04d}.png"
        _temp_files.append(frame_path)
        img.save(frame_path, quality=95)

    _run_ffmpeg([
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
        "-framerate", str(fps), "-i", str(tmp_dir / "flip_%04d.png"),
        "-f", "lavfi", "-i", f"anullsrc=channel_layout=stereo:sample_rate={AUDIO_SAMPLE_RATE}", "-shortest",
        "-map", "0:v", "-map", "1:a",
        "-c:v", CFG.VIDEO_CODEC, "-b:v", CFG.BITRATE, "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-ar", AUDIO_SAMPLE_RATE, "-ac", "2", str(out_fp)
    ])

def run_opening(grid_info, files) -> Path:
    """Generate _intro.mp4."""
    stats = None
    try:
        gpx_pts = load_gpx(str(CFG.INPUT_GPX_FILE))
        stats = compute_stats(gpx_pts)
    except Exception as e:
        log.warning(f"[splash] GPX unavailable: {e}")

    # Use splash_assets_dir for temporary clips
    assets = _mk(splash_assets_dir())

    # 1) Logo intro
    logo_clip = assets / OPEN_LOGO_MP4
    _create_video_clip(
        LOGO_PATH,
        duration=2.0,
        output_path=logo_clip,
        filter_vf="scale=2560:1440:force_original_aspect_ratio=decrease,"
                  "pad=2560:1440:(ow-iw)/2:(oh-ih)/2:black"
    )

    # 2) Map-only still
    map_canvas = _compose_map_only_canvas(stats)
    map_still = assets / "splash_open_map.png"
    _temp_files.append(map_still)  # temp asset
    map_canvas.save(map_still, quality=95)
    map_clip = assets / OPEN_MAP_MP4
    _create_video_clip(map_still, duration=2.0, output_path=map_clip)

    # 3) Flip animation
    base_img = map_canvas
    map_tiles, frame_tiles = _tiles_for_grid(base_img, files, grid_info)
    flip_frames = _render_flip_frames(base_img, grid_info, map_tiles, frame_tiles,
                                      flip_duration_s=1.2, fps=FPS)
    flip_clip = assets / OPEN_FLIP_MP4
    _encode_frames_to_clip(flip_frames, flip_clip, fps=FPS)

    # 4) Collage still (persisted)
    collage_canvas = _collage_image(OUT_W, OUT_H - BANNER_HEIGHT, files)
    collage_canvas_full = Image.new("RGB", (OUT_W, OUT_H), (0, 0, 0))
    collage_canvas_full.paste(collage_canvas, (0, BANNER_HEIGHT))
    collage_still = assets / OPEN_COLLAGE_NAME
    collage_canvas_full.save(collage_still, quality=95)
    log.info(f"[splash] wrote intro collage {collage_still}")
    collage_clip = assets / OPEN_COLLAGE_MP4
    _create_video_clip(collage_still, duration=2.0, output_path=collage_clip)

    # Concatenate: logo → map → flip → collage
    concat_list = assets / "splash_open_concat.txt"
    _temp_files.append(concat_list)
    concat_list.write_text(
        f"file '{logo_clip}'\n"
        f"file '{map_clip}'\n"
        f"file '{flip_clip}'\n"
        f"file '{collage_clip}'\n"
    )
    temp_out = assets / INTRO_TEMP_MP4
    _temp_files.append(temp_out)
    _run_ffmpeg([
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
        "-f", "concat", "-safe", "0", "-i", str(concat_list), "-c", "copy", str(temp_out)
    ])

    # 5) Add intro.mp3 music track - output to PROJECT_DIR
    intro_final = CFG.PROJECT_DIR / "_intro.mp4"
    _add_music_to_video(temp_out, CFG.INTRO_MUSIC, intro_final)

    log.info(f"[splash] wrote {intro_final}")
    return intro_final

# --- Combined entrypoint ---

def run() -> Tuple[Path, Path]:
    """Generate both _intro.mp4 and _outro.mp4 in PROJECT_DIR."""
    global _temp_files
    _temp_files = []  # Reset temp files list for this run

    grid_info, files = run_closing()
    intro = run_opening(grid_info, files)

    # Clean up temporary files and directories
    for temp_item in _temp_files:
        if not temp_item.exists():
            continue
        try:
            if temp_item.is_dir():
                # Remove directory and all contents
                import shutil
                shutil.rmtree(temp_item)
                log.debug(f"[splash] cleaned up directory {temp_item.name}")
            else:
                # Remove file
                temp_item.unlink()
                log.debug(f"[splash] cleaned up {temp_item.name}")
        except Exception as e:
            log.warning(f"[splash] could not delete {temp_item.name}: {e}")

    # Return final outputs in PROJECT_DIR
    outro_final = CFG.PROJECT_DIR / "_outro.mp4"
    return intro, outro_final

if __name__ == "__main__":
    run()