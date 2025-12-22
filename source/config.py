# source/config.py
"""
Hard-fork configuration for MP4 streaming pipeline.
All working files moved to project directories. Source files remain untouched.
Loads user preferences from persistent storage.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from pathlib import Path
from datetime import timezone, timedelta
from typing import Any

# Import persistent config loader
try:
    from source.utils.persistent_config import load_persistent_config
    _PERSISTENT_CONFIG = load_persistent_config()
except ImportError:
    _PERSISTENT_CONFIG = {}


def _get_config_value(key: str, default: Any) -> Any:
    """Get config value from persistent storage or use default."""
    return _PERSISTENT_CONFIG.get(key, default)


@dataclass
class Config:
    # --- Logging ---
    LOG_LEVEL: str = field(default_factory=lambda: _get_config_value('LOG_LEVEL', 'INFO'))

    # --- Project paths ---
    INPUT_BASE_DIR: Path = field(
        default_factory=lambda: Path(_get_config_value('INPUT_BASE_DIR', '/Volumes/GDrive/Fly'))
    )
    PROJECT_ROOT: Path = Path(__file__).resolve().parents[1]
    PROJECTS_ROOT: Path = field(
        default_factory=lambda: Path(_get_config_value('PROJECTS_ROOT', '/Volumes/GDrive/Fly_Projects'))
    )

    # --- Core pipeline settings ---
    RIDE_FOLDER: str = ""
    SOURCE_FOLDER: str = ""

    # Sampling interval in seconds (time-based, not FPS)
    EXTRACT_INTERVAL_SECONDS: int = field(
        default_factory=lambda: _get_config_value('EXTRACT_INTERVAL_SECONDS', 5)
    )

    HIGHLIGHT_TARGET_DURATION_S: float = field(
        default_factory=lambda: _get_config_value('HIGHLIGHT_TARGET_DURATION_S', 180.0)
    )
    CLIP_PRE_ROLL_S: float = field(default_factory=lambda: _get_config_value('CLIP_PRE_ROLL_S', 0.2))
    CLIP_OUT_LEN_S: float = field(default_factory=lambda: _get_config_value('CLIP_OUT_LEN_S', 2.8))

    MIN_GAP_BETWEEN_CLIPS: float = field(
        default_factory=lambda: _get_config_value('MIN_GAP_BETWEEN_CLIPS', 45.0)
    )

    # --- Scene-aware selection ---
    SCENE_PRIORITY_MODE: bool = field(
        default_factory=lambda: _get_config_value('SCENE_PRIORITY_MODE', True)
    )
    SCENE_HIGH_THRESHOLD: float = field(
        default_factory=lambda: _get_config_value('SCENE_HIGH_THRESHOLD', 0.50)
    )
    SCENE_MAJOR_THRESHOLD: float = field(
        default_factory=lambda: _get_config_value('SCENE_MAJOR_THRESHOLD', 0.70)
    )
    SCENE_MAJOR_GAP_MULTIPLIER: float = field(
        default_factory=lambda: _get_config_value('SCENE_MAJOR_GAP_MULTIPLIER', 0.5)
    )
    SCENE_HIGH_GAP_MULTIPLIER: float = field(
        default_factory=lambda: _get_config_value('SCENE_HIGH_GAP_MULTIPLIER', 0.75)
    )
    SCENE_COMPARISON_WINDOW_S: float = field(
        default_factory=lambda: _get_config_value('SCENE_COMPARISON_WINDOW_S', 8.0)
    )

    # --- YOLO settings ---
    YOLO_CLASS_MAP = {
        "person": 0,
        "bicycle": 1,
        "car": 2,
        "motorcycle": 3,
        "truck": 7,
        "traffic light": 9,
        "stop sign": 11
    }

    YOLO_AVAILABLE_CLASSES = [
        "person",
        "bicycle",
        "car",
        "motorcycle",
        "truck",
        "traffic light",
        "stop sign"
    ]

    # --- Detection settings ---
    YOLO_DETECT_CLASSES: list = field(
        default_factory=lambda: _get_config_value('YOLO_DETECT_CLASSES', [1])
    )
    YOLO_IMAGE_SIZE: int = field(default_factory=lambda: _get_config_value('YOLO_IMAGE_SIZE', 640))
    YOLO_MIN_CONFIDENCE: float = field(
        default_factory=lambda: _get_config_value('YOLO_MIN_CONFIDENCE', 0.10)
    )
    YOLO_BATCH_SIZE: int = field(default_factory=lambda: _get_config_value('YOLO_BATCH_SIZE', 4))
    MIN_DETECT_SCORE: float = field(
        default_factory=lambda: _get_config_value('MIN_DETECT_SCORE', 0.10)
    )
    MIN_SPEED_PENALTY: float = field(
        default_factory=lambda: _get_config_value('MIN_SPEED_PENALTY', 2.0)
    )

    # --- Candidate selection ---
    CANDIDATE_FRACTION: float = field(
        default_factory=lambda: _get_config_value('CANDIDATE_FRACTION', 2.0)
    )
    REQUIRE_GPS_FOR_SELECTION: bool = field(
        default_factory=lambda: _get_config_value('REQUIRE_GPS_FOR_SELECTION', False)
    )

    # --- Zone filtering ---
    START_ZONE_DURATION_S: float = field(
        default_factory=lambda: _get_config_value('START_ZONE_DURATION_S', 1200.0)
    )
    START_ZONE_PENALTY: float = field(
        default_factory=lambda: _get_config_value('START_ZONE_PENALTY', 0.5)
    )
    MAX_START_ZONE_FRAC: float = field(
        default_factory=lambda: _get_config_value('MAX_START_ZONE_FRAC', 0.10)
    )

    END_ZONE_DURATION_S: float = field(
        default_factory=lambda: _get_config_value('END_ZONE_DURATION_S', 1200.0)
    )
    END_ZONE_PENALTY: float = field(
        default_factory=lambda: _get_config_value('END_ZONE_PENALTY', 1.0)
    )
    MAX_END_ZONE_FRAC: float = field(
        default_factory=lambda: _get_config_value('MAX_END_ZONE_FRAC', 0.10)
    )

    # --- Scoring weights ---
    CAMERA_WEIGHTS: dict = field(default_factory=lambda: {
        "Fly12Sport": 1.0,
        "Fly6Pro": 1.0,
    })
    SCORE_WEIGHTS: dict = field(default_factory=lambda: {
        "detect_score": 0.20,
        "scene_boost": 0.35,
        "speed_kmh": 0.25,
        "gradient": 0.10,
        "bbox_area": 0.10,
    })

    # --- M1 hardware acceleration ---
    USE_MPS: bool = field(default_factory=lambda: _get_config_value('USE_MPS', True))
    FFMPEG_HWACCEL: str = field(default_factory=lambda: _get_config_value('FFMPEG_HWACCEL', 'videotoolbox'))

    # --- Time alignment ---
    CAMERA_CREATION_TIME_TZ = timezone(timedelta(hours=10))
    CAMERA_CREATION_TIME_IS_LOCAL_WRONG_Z: bool = True
    CAMERA_TIME_OFFSETS: dict = field(default_factory=lambda: {
        "Fly12Sport": 0.0,
        "Fly6Pro": 0.0,
    })
    # Toggle to enable/disable applying camera time offsets from JSON/config
    # Default is False to avoid unexpected alignment unless user opts in
    USE_CAMERA_OFFSETS: bool = field(default_factory=lambda: _get_config_value('USE_CAMERA_OFFSETS', True))
    GPX_TIME_OFFSET_S: float = field(default_factory=lambda: _get_config_value('GPX_TIME_OFFSET_S', 0.0))
    GPX_TOLERANCE: float = field(default_factory=lambda: _get_config_value('GPX_TOLERANCE', 1.0))
    PARTNER_TIME_TOLERANCE_S: float = field(
        default_factory=lambda: _get_config_value('PARTNER_TIME_TOLERANCE_S', 0.0)
    )

    # --- Path properties ---
    @property
    def PROJECT_DIR(self) -> Path:
        return self.PROJECTS_ROOT / self.RIDE_FOLDER

    @property
    def INPUT_DIR(self) -> Path:
        return self.INPUT_BASE_DIR / self.SOURCE_FOLDER

    @property
    def INPUT_VIDEOS_DIR(self) -> Path:
        return self.INPUT_DIR

    @property
    def INPUT_GPX_FILE(self) -> Path:
        return self.INPUT_DIR / "ride.gpx"

    @property
    def FINAL_REEL_PATH(self) -> Path:
        return self.PROJECT_DIR / f"{self.RIDE_FOLDER}.mp4"

    @property
    def LOG_DIR(self) -> Path:
        return self.PROJECT_DIR / "logs"

    @property
    def WORKING_DIR(self) -> Path:
        return self.PROJECT_DIR / "working"

    @property
    def CLIPS_DIR(self) -> Path:
        return self.PROJECT_DIR / "clips"

    @property
    def FRAMES_DIR(self) -> Path:
        return self.PROJECT_DIR / "frames"

    @property
    def SPLASH_ASSETS_DIR(self) -> Path:
        return self.PROJECT_DIR / "splash_assets"

    @property
    def MINIMAP_DIR(self) -> Path:
        return self.PROJECT_DIR / "minimaps"

    @property
    def GAUGE_DIR(self) -> Path:
        return self.PROJECT_DIR / "gauges"

    # --- Audio assets ---
    ASSETS_DIR = PROJECT_ROOT / "assets"
    MUSIC_DIR: Path = ASSETS_DIR / "music"
    INTRO_MUSIC = ASSETS_DIR / "intro.mp3"
    OUTRO_MUSIC = ASSETS_DIR / "outro.mp3"

    MUSIC_VOLUME: float = field(default_factory=lambda: _get_config_value('MUSIC_VOLUME', 0.5))
    RAW_AUDIO_VOLUME: float = field(default_factory=lambda: _get_config_value('RAW_AUDIO_VOLUME', 0.6))

    # --- PiP & minimap overlay ---
    PIP_SCALE_RATIO: float = field(default_factory=lambda: _get_config_value('PIP_SCALE_RATIO', 0.30))
    PIP_MARGIN: int = field(default_factory=lambda: _get_config_value('PIP_MARGIN', 30))
    MINIMAP_SCALE_RATIO: float = field(
        default_factory=lambda: _get_config_value('MINIMAP_SCALE_RATIO', 0.25)
    )
    MINIMAP_MARGIN: int = field(default_factory=lambda: _get_config_value('MINIMAP_MARGIN', 30))
    MINIMAP_ANCHOR: str = "top_right"
    MAP_ROUTE_COLOR: tuple[int, int, int] = (40, 180, 60)
    MAP_ROUTE_WIDTH: int = 8
    MAP_MARKER_COLOR: tuple[int, int, int] = (230, 175, 0)
    MAP_MARKER_RADIUS: int = 8
    MAP_PADDING_PCT: float = 0.25
    MAP_ZOOM_PIP: int = 14
    MAP_ZOOM_SPLASH: int = 12
    MAP_SPLASH_SIZE: tuple[int, int] = (2560, 1440)
    MAP_BASEMAP_PROVIDER: str = field(
        default_factory=lambda: _get_config_value('MAP_BASEMAP_PROVIDER', 'OpenStreetMap.Mapnik')
    )

    # --- HUD ---
    HUD_ANCHOR: str = "bottom_left"
    HUD_SCALE: float = 1.0
    HUD_PADDING: tuple[int, int] = (30, 30)
    GAUGE_ORDER: list[str] = field(default_factory=lambda: ["cadence", "hr", "gradient", "speed", "elev"])
    GAUGE_MAXES: dict = field(default_factory=lambda: {
        "speed": 80, "cadence": 120, "hr": 180, "elev": 5000,
        "gradient_min": -10, "gradient_max": 10,
    })

    # --- Encoding ---
    VIDEO_CODEC: str = field(default_factory=lambda: _get_config_value('VIDEO_CODEC', 'libx264'))
    BITRATE: str = field(default_factory=lambda: _get_config_value('BITRATE', '8M'))
    MAXRATE: str = field(default_factory=lambda: _get_config_value('MAXRATE', '12M'))
    BUFSIZE: str = field(default_factory=lambda: _get_config_value('BUFSIZE', '24M'))

DEFAULT_CONFIG = Config()
