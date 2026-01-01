# source/utils/ffmpeg.py
"""
Thin wrappers for common ffmpeg ops: encode stills, mux audio.
- Splash/outro clips always get a silent AAC track.
- Highlight clips preserve camera audio.
"""

from __future__ import annotations
import subprocess
from pathlib import Path

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
    
    FIXED: More robust stream mapping that handles edge cases.
    """
    # Validate inputs exist
    if not video_fp.exists():
        raise FileNotFoundError(f"Video file not found: {video_fp}")
    if not audio_src_fp.exists():
        raise FileNotFoundError(f"Audio source not found: {audio_src_fp}")
    
    cmd = [
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
        # Input 0: rendered video clip (no audio or silent audio)
        "-i", str(video_fp),
        # Input 1: original camera file (extract audio from specific time)
        "-ss", f"{t_start:.3f}", "-t", f"{duration:.3f}", "-i", str(audio_src_fp),
        # Map video from input 0, audio from input 1
        "-map", "0:v:0", "-map", "1:a:0?",
        # Copy video, encode audio
        "-c:v", "copy",
        "-c:a", "aac", "-ar", AUDIO_SAMPLE_RATE, "-ac", "2",
        "-shortest", str(out_fp)
    ]
    run_ffmpeg(cmd)