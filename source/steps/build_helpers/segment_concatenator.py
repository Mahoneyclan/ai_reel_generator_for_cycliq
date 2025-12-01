# source/steps/build_helpers/segment_concatenator.py
"""
Multi-segment video assembly with music overlay.
Concatenates clips into ~30s segments and adds background music.
"""

from __future__ import annotations
import subprocess
from pathlib import Path
from typing import List

from ...config import DEFAULT_CONFIG as CFG
from ...utils.log import setup_logger
from ...utils.music import create_music_track_manager
from ...io_paths import _mk

log = setup_logger("steps.build_helpers.segment_concatenator")

AUDIO_SAMPLE_RATE = "48000"


class SegmentConcatenator:
    """Concatenates clips into segments with music overlay."""
    
    def __init__(self, project_dir: Path, working_dir: Path):
        """
        Args:
            project_dir: Project directory for output segments
            working_dir: Working directory for temp files
        """
        self.project_dir = project_dir
        self.working_dir = _mk(working_dir)
        self.temp_files: List[Path] = []
    
    def concatenate_into_segments(
        self,
        clips: List[Path],
        music_path: Path,
        music_volume: float = 0.5,
        raw_audio_volume: float = 0.6
    ) -> List[Path]:
        """
        Concatenate clips into ~30s segments with music.
        
        Args:
            clips: List of clip paths to concatenate
            music_path: Path to music directory
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
        
        segment_paths: List[Path] = []
        
        for seg_idx in range(num_segments):
            start = seg_idx * highlights_per_segment
            end = min(start + highlights_per_segment, len(clips))
            segment_clips = clips[start:end]
            
            if not segment_clips:
                continue
            
            # Create segment
            segment_path = self._create_segment(
                segment_clips=segment_clips,
                segment_num=seg_idx + 1,
                music_path=music_path,
                music_volume=music_volume,
                raw_audio_volume=raw_audio_volume
            )
            
            if segment_path:
                segment_paths.append(segment_path)
        
        # Cleanup temp files
        self._cleanup_temp_files()
        
        return segment_paths
    
    def _create_segment(
        self,
        segment_clips: List[Path],
        segment_num: int,
        music_path: Path,
        music_volume: float,
        raw_audio_volume: float
    ) -> Path:
        """Create single segment from clips with music overlay."""
        # Step 1: Concatenate clips
        raw_segment = self._concatenate_clips(segment_clips, segment_num)
        if not raw_segment:
            return None
        
        # Step 2: Add music overlay
        final_segment = self._add_music_overlay(
            video_path=raw_segment,
            segment_num=segment_num,
            music_path=music_path,
            music_volume=music_volume,
            raw_audio_volume=raw_audio_volume
        )
        
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
    
    def _add_music_overlay(
        self,
        video_path: Path,
        segment_num: int,
        music_path: Path,
        music_volume: float,
        raw_audio_volume: float
    ) -> Path:
        """Add music overlay to segment."""
        output_path = self.project_dir / f"_middle_{segment_num:02d}.mp4"
        
        # Get random music track
        music_manager = create_music_track_manager(CFG)
        music_track = music_manager.get_track_path()
        
        if not music_track or not music_track.exists():
            log.warning(f"[segment] No music found, creating video-only segment {segment_num}")
            return self._copy_without_music(video_path, output_path)
        
        # Add music with volume mixing
        cmd = [
            "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
            "-i", str(video_path),
            "-stream_loop", "-1", "-i", str(music_track),
            "-filter_complex",
            f"[0:a]volume={raw_audio_volume}[raw];"
            f"[1:a]volume={music_volume}[music];"
            f"[raw][music]amix=inputs=2:dropout_transition=0[out]",
            "-map", "0:v", "-map", "[out]",
            "-c:v", "copy", "-c:a", "aac", "-ar", AUDIO_SAMPLE_RATE,
            "-shortest",
            str(output_path)
        ]
        
        try:
            subprocess.run(cmd, check=True)
            log.info(f"[segment] Added music to segment {segment_num}: {music_track.name}")
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