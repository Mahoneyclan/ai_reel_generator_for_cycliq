# source/steps/build_helpers/segment_concatenator.py
"""
Multi-segment video assembly with CONTINUOUS music overlay.
Concatenates clips into ~30s segments with seamless music progression.

KEY FEATURE: Music continues across segments without restarting.
Music stored in: assets/music/
Intro/outro music: separate files in assets/
"""

from __future__ import annotations
import subprocess
import random
import json
from pathlib import Path
from typing import List, Optional

from ...config import DEFAULT_CONFIG as CFG
from ...utils.log import setup_logger
from ...io_paths import _mk

log = setup_logger("steps.build_helpers.segment_concatenator")

AUDIO_SAMPLE_RATE = "48000"

# Supported music formats
MUSIC_EXTENSIONS = [".mp3", ".wav", ".m4a", ".aac", ".flac"]


def get_music_dir() -> Path:
    """
    Get the music directory path.
    Music is stored in: PROJECT_ROOT/assets/music/
    
    Returns:
        Path to music directory
    """
    return CFG.PROJECT_ROOT / "assets" / "music"


class SegmentConcatenator:
    """Concatenates clips into segments with continuous music overlay."""
    
    def __init__(self, project_dir: Path, working_dir: Path):
        """
        Args:
            project_dir: Project directory for output segments
            working_dir: Working directory for temp files
        """
        self.project_dir = project_dir
        self.working_dir = _mk(working_dir)
        self.temp_files: List[Path] = []
        
        # Music tracking for continuous playback
        self.selected_music_track: Optional[Path] = None
        self.music_offset: float = 0.0  # Current position in music track
    
    def concatenate_into_segments(
        self,
        clips: List[Path],
        music_volume: float = 0.5,
        raw_audio_volume: float = 0.6
    ) -> List[Path]:
        """
        Concatenate clips into ~30s segments with CONTINUOUS music.
        
        Music plays continuously across all segments:
        - Segment 1: music 0:00-0:30
        - Segment 2: music 0:30-1:00
        - Segment 3: music 1:00-1:30
        - etc.
        
        Music is loaded from: PROJECT_ROOT/assets/music/
        
        Args:
            clips: List of clip paths to concatenate
            music_volume: Music track volume (0.0-1.0)
            raw_audio_volume: Camera audio volume (0.0-1.0)
            
        Returns:
            List of paths to created segment files
        """
        if not clips:
            log.warning("[segment] No clips to concatenate")
            return []
        
        # Calculate segments
        highlights_per_segment = int(30.0 // CFG.CLIP_OUT_LEN_S)
        num_segments = (len(clips) + highlights_per_segment - 1) // highlights_per_segment
        
        log.info(
            f"[segment] Concatenating {len(clips)} clips into "
            f"{num_segments} × ~30s segments ({highlights_per_segment} clips/segment)"
        )
        
        # Select SINGLE music track for all segments
        music_dir = get_music_dir()
        self._select_music_track(music_dir)
        
        if self.selected_music_track:
            log.info(f"[segment] Using continuous music: {self.selected_music_track.name}")
        else:
            log.warning("[segment] No music track found, creating segments without music")
        
        # Reset music offset for new concatenation
        self.music_offset = 0.0
        
        segment_paths: List[Path] = []
        
        for seg_idx in range(num_segments):
            start = seg_idx * highlights_per_segment
            end = min(start + highlights_per_segment, len(clips))
            segment_clips = clips[start:end]
            
            if not segment_clips:
                continue
            
            # Create segment with continuous music
            segment_path = self._create_segment(
                segment_clips=segment_clips,
                segment_num=seg_idx + 1,
                music_volume=music_volume,
                raw_audio_volume=raw_audio_volume
            )
            
            if segment_path:
                segment_paths.append(segment_path)
        
        # Cleanup temp files
        self._cleanup_temp_files()
        
        log.info(f"[segment] Created {len(segment_paths)} segments with continuous music")
        return segment_paths
    
    def _select_music_track(self, music_path: Path) -> None:
        """
        Select a single music track from the music directory.
        
        Args:
            music_path: Path to music directory (assets/music)
        """
        music_files = self._find_music_files(music_path)
        
        if not music_files:
            self.selected_music_track = None
            return
        
        # Randomly select one track
        self.selected_music_track = random.choice(music_files)
        log.info(f"[segment] Selected music track: {self.selected_music_track.name}")
    
    def _find_music_files(self, music_path: Path) -> List[Path]:
        """
        Find all supported music files in directory.
        
        Args:
            music_path: Path to music directory
            
        Returns:
            List of music file paths
        """
        if not music_path.exists():
            log.warning(f"[segment] Music directory not found: {music_path}")
            log.info(f"[segment] Create directory and add music: mkdir -p {music_path}")
            return []
        
        music_files = []
        for ext in MUSIC_EXTENSIONS:
            music_files.extend(music_path.glob(f"*{ext}"))
            music_files.extend(music_path.glob(f"*{ext.upper()}"))
        
        # Remove duplicates and sort
        music_files = sorted(set(music_files))
        
        if music_files:
            log.info(f"[segment] Found {len(music_files)} music file(s) in {music_path}")
        
        return music_files
    
    def _get_video_duration(self, video_path: Path) -> float:
        """
        Get video duration in seconds using ffprobe.
        
        Args:
            video_path: Path to video file
            
        Returns:
            Duration in seconds, or 0.0 if unable to determine
        """
        try:
            result = subprocess.run([
                "ffprobe", "-v", "quiet", "-print_format", "json",
                "-show_entries", "format=duration", str(video_path)
            ], capture_output=True, text=True, check=True)
            
            data = json.loads(result.stdout)
            return float(data.get("format", {}).get("duration", 0))
        except Exception as e:
            log.debug(f"[segment] Could not get duration for {video_path.name}: {e}")
            return 0.0
    
    def _create_segment(
        self,
        segment_clips: List[Path],
        segment_num: int,
        music_volume: float,
        raw_audio_volume: float
    ) -> Path:
        """Create single segment from clips with continuous music overlay."""
        # Step 1: Concatenate clips
        raw_segment = self._concatenate_clips(segment_clips, segment_num)
        if not raw_segment:
            return None
        
        # Step 2: Get segment duration
        segment_duration = self._get_video_duration(raw_segment)
        if segment_duration == 0:
            log.warning(f"[segment] Could not determine duration for segment {segment_num}")
            segment_duration = len(segment_clips) * CFG.CLIP_OUT_LEN_S  # Fallback estimate
        
        # Step 3: Add continuous music overlay
        final_segment = self._add_continuous_music(
            video_path=raw_segment,
            segment_num=segment_num,
            segment_duration=segment_duration,
            music_volume=music_volume,
            raw_audio_volume=raw_audio_volume
        )
        
        # Step 4: Update music offset for next segment
        self.music_offset += segment_duration
        
        # Cleanup raw segment (temp file)
        try:
            raw_segment.unlink()
        except Exception as e:
            log.debug(f"[segment] Could not delete temp file {raw_segment.name}: {e}")
        
        return final_segment
    
    def _concatenate_clips(self, clips: List[Path], segment_num: int) -> Path:
        """Concatenate clips using FFmpeg concat demuxer."""
        # Create concat list file
        concat_list = self.working_dir / f"middle_list_{segment_num:02d}.txt"
        with concat_list.open("w") as f:
            for clip in clips:
                f.write(f"file '{clip.resolve()}'\n")
        
        self.temp_files.append(concat_list)
        
        # Output path for raw concatenation
        output_path = self.project_dir / f"_middle_raw_{segment_num:02d}.mp4"
        self.temp_files.append(output_path)
        
        # Concatenate with FFmpeg
        cmd = [
            "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
            "-f", "concat", "-safe", "0", "-i", str(concat_list),
            "-c", "copy",
            str(output_path)
        ]
        
        try:
            subprocess.run(cmd, check=True)
            log.info(f"[segment] Concatenated segment {segment_num} ({len(clips)} clips)")
            return output_path
        except subprocess.CalledProcessError as e:
            log.error(f"[segment] Concatenation failed for segment {segment_num}: {e}")
            return None
    
    def _add_continuous_music(
        self,
        video_path: Path,
        segment_num: int,
        segment_duration: float,
        music_volume: float,
        raw_audio_volume: float
    ) -> Path:
        """
        Add music overlay using continuous playback (no restart between segments).
        
        Uses -ss (seek start) to extract the correct portion of music for this segment.
        
        Args:
            video_path: Path to video segment
            segment_num: Segment number
            segment_duration: Duration of this segment in seconds
            music_volume: Music track volume
            raw_audio_volume: Camera audio volume
            
        Returns:
            Path to segment with music
        """
        output_path = self.project_dir / f"_middle_{segment_num:02d}.mp4"
        
        # If no music track selected, copy without music
        if not self.selected_music_track or not self.selected_music_track.exists():
            log.warning(f"[segment] No music for segment {segment_num}, creating video-only")
            return self._copy_without_music(video_path, output_path)
        
        # Calculate music seek position and duration
        music_start = self.music_offset
        music_duration = segment_duration
        
        log.info(
            f"[segment] Adding music to segment {segment_num}: "
            f"{self.selected_music_track.name} [{music_start:.1f}s-{music_start + music_duration:.1f}s]"
        )
        
        # Build FFmpeg command with music seek
        cmd = [
            "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
            # Video input
            "-i", str(video_path),
            # Music input with seek and loop
            "-ss", f"{music_start:.3f}",  # Start at current offset
            "-stream_loop", "-1",          # Loop if music is shorter than needed
            "-i", str(self.selected_music_track),
            # Audio mixing filter
            "-filter_complex",
            f"[0:a]volume={raw_audio_volume}[raw];"
            f"[1:a]volume={music_volume}[music];"
            f"[raw][music]amix=inputs=2:dropout_transition=0[out]",
            # Output mapping
            "-map", "0:v", "-map", "[out]",
            # Output settings
            "-c:v", "copy",
            "-c:a", "aac", "-ar", AUDIO_SAMPLE_RATE,
            "-t", f"{segment_duration:.3f}",  # Limit to segment duration
            str(output_path)
        ]
        
        try:
            subprocess.run(cmd, check=True)
            return output_path
        except subprocess.CalledProcessError as e:
            log.error(f"[segment] Music overlay failed for segment {segment_num}: {e}")
            # Fallback: copy without music
            return self._copy_without_music(video_path, output_path)
    
    def _copy_without_music(self, source: Path, dest: Path) -> Path:
        """Copy video without music overlay (fallback)."""
        cmd = [
            "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
            "-i", str(source),
            "-c", "copy",
            str(dest)
        ]
        
        try:
            subprocess.run(cmd, check=True)
            log.info(f"[segment] Created segment without music: {dest.name}")
            return dest
        except subprocess.CalledProcessError as e:
            log.error(f"[segment] Failed to copy segment: {e}")
            return None
    
    def _cleanup_temp_files(self):
        """Remove temporary files created during segment creation."""
        if not self.temp_files:
            return
        
        removed = 0
        for temp_file in self.temp_files:
            try:
                if temp_file.exists():
                    temp_file.unlink()
                    removed += 1
            except Exception as e:
                log.debug(f"[segment] Could not remove {temp_file.name}: {e}")
        
        if removed > 0:
            log.debug(f"[segment] Cleaned up {removed} temporary files")
        
        self.temp_files.clear()