# source/utils/music.py
from pathlib import Path
from typing import Optional
import logging

log = logging.getLogger(__name__)

class MusicTrackManager:
    """Automatically discovers and cycles through .mp3 tracks in MUSIC_DIR."""

    def __init__(self, music_dir: Path):
        self.music_dir = Path(music_dir)
        self.available_tracks = self._discover_tracks()
        self._cycle_index = 0

    def _discover_tracks(self) -> list[str]:
        """Return all .mp3 filenames in music_dir."""
        if not self.music_dir.exists():
            log.warning(f"Music directory not found: {self.music_dir}")
            return []
        tracks = [f.name for f in self.music_dir.glob("*.mp3")]
        if not tracks:
            log.warning(f"No .mp3 files found in {self.music_dir}")
        else:
            log.info(f"Discovered {len(tracks)} tracks in {self.music_dir}")
        return tracks

    def get_track_path(self) -> Optional[Path]:
        """Return the next track path, cycling through available tracks."""
        if not self.available_tracks:
            return None
        track = self.available_tracks[self._cycle_index % len(self.available_tracks)]
        self._cycle_index += 1
        return self.music_dir / track

    def list_available_tracks(self) -> list[str]:
        """List all discovered tracks."""
        return self.available_tracks


def create_music_track_manager(cfg) -> MusicTrackManager:
    return MusicTrackManager(cfg.MUSIC_DIR)
