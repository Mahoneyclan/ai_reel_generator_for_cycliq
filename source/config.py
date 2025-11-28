# source/config.py
"""
Hard-fork configuration for MP4 streaming pipeline.
All working files moved to project directories. Source files remain untouched.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from pathlib import Path
from datetime import timezone, timedelta

@dataclass
class Config:
    # --- Logging ---
    LOG_LEVEL: str = "INFO"

    # --- Project paths ---
    PROJECT_ROOT: Path = Path(__file__).resolve().parents[1]
    PROJECTS_ROOT: Path = Path("/Volumes/GDrive/Fly_Projects") # NEW: All Project output and working files here
    INPUT_BASE_DIR: Path = Path("/Volumes/GDrive/Fly")  # NEW: Raw source only

    # --- Core pipeline settings ---
    RIDE_FOLDER: str = ""  # This is now the PROJECT folder name
    SOURCE_FOLDER: str = ""  # NEW: Raw source folder name
    
    EXTRACT_FPS: float = 1.0  # Reduced for performance
    
    HIGHLIGHT_TARGET_DURATION_S: float = 180.0
    CLIP_PRE_ROLL_S: float = 0.2
    CLIP_OUT_LEN_S: float = 2.8

    MIN_GAP_BETWEEN_CLIPS: float = 45.0  # Reduced for denser clips

    # --- Scene-aware selection ---
    SCENE_PRIORITY_MODE: bool = True  # Enable scene-based gap filtering
    SCENE_HIGH_THRESHOLD: float = 0.50  # "Significant" scene change
    SCENE_MAJOR_THRESHOLD: float = 0.70  # "Major" scene change
    SCENE_MAJOR_GAP_MULTIPLIER: float = 0.5  # Major scenes can be 50% closer
    SCENE_HIGH_GAP_MULTIPLIER: float = 0.75  # High scenes can be 75% closer
    SCENE_COMPARISON_WINDOW_S: float = 8.0  # Compare frames N seconds apart (not just adjacent),  Higher = detects major scene changes (e.g., 10s = new location) while Lower = detects quick action (e.g., 3s = passing cyclist)


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

    # Available class names for UI selection
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
    YOLO_DETECT_CLASSES: list = field(default_factory=lambda: [1])  # 1=bicycle
    YOLO_IMAGE_SIZE: int = 640
    YOLO_MIN_CONFIDENCE: float = 0.10  # Lower to catch more
    YOLO_BATCH_SIZE: int = 4  # M1 8GB safe batch size
    MIN_DETECT_SCORE: float = 0.10  # Lower threshold
    MIN_SPEED_PENALTY: float = 2.0  # Lower to keep slower moments

    # --- Candidate selection (NEW - add this) ---
    CANDIDATE_FRACTION: float = 2  # Select top 1.5x target clips as candidates for final selection
    REQUIRE_GPS_FOR_SELECTION: bool = False  # If True, only select frames with valid GPS data  
    # --- Zone filtering ---
    START_ZONE_DURATION_S: float = 1200.0
    START_ZONE_PENALTY: float = 0.5
    MAX_START_ZONE_FRAC: float = 0.10 
    
    END_ZONE_DURATION_S: float = 1200.0
    END_ZONE_PENALTY: float = 1.0
    MAX_END_ZONE_FRAC: float = 0.10  

    # --- Scoring weights (streaming-optimized) ---
    CAMERA_WEIGHTS: dict = field(default_factory=lambda: {
        "Fly12Sport": 2.0,
        "Fly6Pro": 1.0,
    })
    SCORE_WEIGHTS: dict = field(default_factory=lambda: {
        "detect_score": 0.20,    # Reduce from 0.35 (most frames already pass)
        "scene_boost": 0.35,     # INCREASE from 0.20 (this is your differentiator)
        "speed_kmh": 0.25,       # Keep same
        "gradient": 0.10,        # Keep same
        "bbox_area": 0.10,       # Keep same
    })


    # --- M1 hardware acceleration ---
    USE_MPS: bool = True
    FFMPEG_HWACCEL: str = "videotoolbox"

    # --- Time alignment ---
    CAMERA_CREATION_TIME_TZ = timezone(timedelta(hours=10))
    CAMERA_CREATION_TIME_IS_LOCAL_WRONG_Z: bool = True
    CAMERA_TIME_OFFSETS: dict = field(default_factory=lambda: {
        "Fly12Sport": 0.0,
        "Fly6Pro": 0.0,
    })
    GPX_TIME_OFFSET_S: float = 0.0
    GPX_TOLERANCE: float = 2.0
    PARTNER_TIME_TOLERANCE_S: float = 2.0


    # --- Path properties (PROJECT files) ---
    @property
    def PROJECT_DIR(self) -> Path: 
        """Working project directory (all outputs)"""
        return self.PROJECTS_ROOT / self.RIDE_FOLDER
    
    @property
    def INPUT_DIR(self) -> Path: 
        """Raw source directory (read-only)"""
        return self.INPUT_BASE_DIR / self.SOURCE_FOLDER
    
    @property
    def INPUT_VIDEOS_DIR(self) -> Path: 
        """Raw videos (read-only)"""
        return self.INPUT_DIR
    
    @property
    def INPUT_GPX_FILE(self) -> Path: 
        """Raw GPX file (read-only)"""
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
        return self.PROJECT_DIR / "frames"  # Empty in streaming mode
    
    @property
    def SPLASH_ASSETS_DIR(self) -> Path: 
        return self.PROJECT_DIR / "splash_assets"
    
    @property
    def MINIMAP_DIR(self) -> Path: 
        return self.PROJECT_DIR / "minimaps"
    
    @property
    def GAUGE_DIR(self) -> Path: 
        return self.PROJECT_DIR / "gauges"

    # --- Audio assets (static, in source project) ---
    ASSETS_DIR = PROJECT_ROOT / "assets"
    MUSIC_DIR: Path = ASSETS_DIR / "music"
    INTRO_MUSIC = ASSETS_DIR / "intro.mp3"
    OUTRO_MUSIC = ASSETS_DIR / "outro.mp3"

    MUSIC_VOLUME: float = 0.5
    RAW_AUDIO_VOLUME = 0.6

    # --- PiP & minimap overlay ---
    PIP_SCALE_RATIO: float = 0.30
    PIP_MARGIN: int = 30
    MINIMAP_SCALE_RATIO: float = 0.25
    MINIMAP_MARGIN: int = 30
    MINIMAP_ANCHOR: str = "top_right"
    MAP_ROUTE_COLOR: tuple[int, int, int] = (40, 180, 60)
    MAP_ROUTE_WIDTH: int = 8
    MAP_MARKER_COLOR: tuple[int, int, int] = (230, 175, 0)
    MAP_MARKER_RADIUS: int = 8
    MAP_PADDING_PCT: float = 0.25
    MAP_ZOOM_PIP: int = 14
    MAP_ZOOM_SPLASH: int = 12

    # --- Splash map settings ---
    MAP_SPLASH_SIZE: tuple[int, int] = (2560, 1440)

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
    VIDEO_CODEC: str = "libx264"
    BITRATE: str = "8M"
    MAXRATE: str = "12M"
    BUFSIZE: str = "24M"

DEFAULT_CONFIG = Config()