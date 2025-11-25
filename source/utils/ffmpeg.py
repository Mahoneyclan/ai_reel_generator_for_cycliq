# source/utils/ffmpeg.py
"""
Thin wrappers for common ffmpeg ops: encode stills, mux audio.
- Splash/outro clips always get a silent AAC track.
- Highlight clips preserve camera audio.
"""

from __future__ import annotations
import subprocess
from pathlib import Path
from ..config import DEFAULT_CONFIG as CFG

AUDIO_SAMPLE_RATE = "48000"

def run_ffmpeg(cmd: list[str]):
    """Execute ffmpeg command."""
    subprocess.run(cmd, check=True)

def mux_audio(video_fp: Path, audio_src_fp: Path, out_fp: Path,
              t_start: float, duration: float):
    """
    Mux highlight video with camera audio.
    - Video comes from the pre-cut highlight clip (video_fp).
    - Audio is cut from the original camera file (audio_src_fp).
    """
    cmd = [
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
        "-ss", f"{t_start:.3f}", "-t", f"{duration:.3f}", "-i", str(audio_src_fp),
        "-i", str(video_fp),
        "-map", "1:v", "-map", "0:a?",
        "-c:v", "copy",
        "-c:a", "aac", "-ar", AUDIO_SAMPLE_RATE, "-ac", "2",
        "-shortest", str(out_fp)
    ]
    run_ffmpeg(cmd)