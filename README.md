# Velo Films AI

# Cycliq Video Pipeline

Automated highlight reel generation from dual-camera cycling footage (Cycliq Fly12Sport + Fly6Pro) with GPX telemetry integration.

## Overview

This pipeline processes synchronized front/rear cycling camera footage to create professional highlight reels with:
- AI-powered scene detection and selection (YOLO object detection)
- GPS-enriched telemetry overlays (speed, elevation, gradient, heart rate, cadence)
- Side-by-side picture-in-picture compositing
- Minimap visualization with route tracking
- Automated temporal alignment across cameras and GPX data

## Features

### Intelligent Selection
- **YOLO-based detection**: Identifies cyclists, vehicles, traffic events
- **Scene-aware scoring**: Prioritizes high-activity moments (traffic, speed changes, hills)
- **Partner matching**: Synchronizes front/rear camera clips showing the same moment
- **Manual override**: GUI for fine-tuning AI selections

### Camera Alignment
- **Automatic sync**: Handles Cycliq metadata quirks (UTC bug, creation_time offsets)
- **Per-camera calibration**: Fly12Sport +2s offset, Fly6Pro exact timing
- **GPX integration**: Aligns video to GPS timeline with configurable tolerance

### Professional Output
- **Dual-view compositing**: Main view + PiP with configurable positioning
- **Telemetry gauges**: Speed, cadence, heart rate, elevation, gradient
- **Route minimap**: Live position tracking on OpenStreetMap tiles
- **Title cards**: Customizable intro/outro with ride statistics

## Requirements

### Hardware
- **Tested on**: Mac Mini M1 (Apple Silicon)
- **Storage**: ~10GB per hour of 1440p footage
- **RAM**: 16GB+ recommended for YOLO processing

### Software
- Python 3.9+
- FFmpeg with VideoToolbox support (hardware encoding)
- ffprobe (bundled with FFmpeg)

### Python Dependencies
```
PySide6>=6.6.0          # GUI framework
opencv-python>=4.8.0    # Video processing
ultralytics>=8.0.0      # YOLO object detection
gpxpy>=1.5.0            # GPX parsing
staticmap>=0.5.0        # Minimap generation
pandas>=2.0.0           # Data processing
numpy>=1.24.0           # Numerical operations
Pillow>=10.0.0          # Image manipulation
```

## Installation

```bash
# Clone repository
git clone <repository-url>
cd cycliq-video-pipeline

# Create virtual environment
python3 -m venv venv
source venv/bin/activate  # On macOS/Linux

# Install dependencies
pip install -r requirements.txt

# Verify FFmpeg installation
ffmpeg -version
ffprobe -version
```

## Project Structure

```
project/
├── source/
│   ├── core/
│   │   ├── pipeline_executor.py    # Main pipeline orchestrator
│   │   └── step_registry.py        # Step function registry
│   ├── steps/
│   │   ├── align.py                # Camera alignment
│   │   ├── extract.py              # Frame metadata generation
│   │   ├── analyze.py              # YOLO detection + scoring
│   │   ├── select.py               # AI-powered clip selection
│   │   └── build.py                # Video composition
│   ├── utils/
│   │   ├── video_utils.py          # Video probing, camera offsets
│   │   ├── gpx_utils.py            # GPS data processing
│   │   └── overlay_utils.py        # Telemetry rendering
│   ├── gui/
│   │   └── manual_selection_window.py  # Manual review interface
│   └── config.py                   # Configuration management
├── assets/
│   ├── music/                      # Background audio
│   └── fonts/                      # Overlay fonts
└── README.md
```

## Usage

### Quick Start

```bash
# Launch GUI
python -m source.main

# Or run CLI pipeline
python -m source.steps.align
python -m source.steps.extract
python -m source.steps.analyze
python -m source.steps.select
python -m source.steps.build
```

### Pipeline Stages

#### 1. **Flatten** - GPX Processing
```bash
# Converts GPX to flat CSV timeline with 1-second sampling
# Outputs: flatten.csv (gpx_epoch, lat, lon, elevation, speed, etc.)
```

#### 2. **Align** - Camera Synchronization
```bash
# Probes video metadata to determine recording start times
# Handles Cycliq-specific timing quirks:
#   - Fly12Sport: creation_time = end + 2s
#   - Fly6Pro: creation_time = exact end
# Outputs: camera_offsets.json
```

**Example output:**
```json
{
  "Fly6Pro": 0.0,
  "Fly12Sport": 11.0
}
```

#### 3. **Extract** - Frame Metadata Generation
```bash
# Samples frames at 5-second intervals
# Applies camera offsets for temporal alignment
# Filters frames before GPX start time
# Outputs: extract.csv (frame_number, abs_time_epoch, video_path, etc.)
```

#### 4. **Analyze** - AI Detection & Enrichment
```bash
# Runs YOLO object detection on sampled frames
# Enriches with GPX telemetry (speed, gradient, elevation)
# Calculates scene scores based on activity level
# Outputs: enrich.csv (detect_score, speed_kmh, gradient, bbox_area, etc.)
```

#### 5. **Select** - Clip Selection
```bash
# AI pre-selection based on scoring weights
# Partner matching (finds synchronized front/rear moments)
# Manual review GUI for fine-tuning
# Outputs: select.csv (final clip decisions)
```

**Scoring weights (configurable):**
```python
SCORE_WEIGHTS = {
    "detect_score": 0.20,   # YOLO detections
    "scene_boost": 0.35,    # High-activity scenes
    "speed_kmh": 0.25,      # Speed variation
    "gradient": 0.10,       # Hill climbing
    "bbox_area": 0.10,      # Object proximity
}
```

#### 6. **Build** - Video Composition
```bash
# Extracts selected clips from source videos
# Applies PiP compositing (main view + secondary)
# Outputs: Individual clip files in clips/
```

#### 7. **Splash** - Title Cards
```bash
# Generates intro/outro with ride stats
# Renders route overview map
# Outputs: splash_intro.mp4, splash_outro.mp4
```

#### 8. **Concat** - Final Assembly
```bash
# Concatenates: intro + clips + outro
# Adds background music with ducking
# Hardware-accelerated encoding (VideoToolbox on M1)
# Outputs: {project_name}.mp4
```

## Configuration

### Global Settings (`config.py`)

```python
# Sampling
EXTRACT_INTERVAL_SECONDS = 5  # Frame sampling rate

# Target duration
HIGHLIGHT_TARGET_DURATION_S = 180.0  # 3-minute highlights

# Clip timing
CLIP_PRE_ROLL_S = 0.2   # Lead-in before scored moment
CLIP_OUT_LEN_S = 2.8    # Total clip length
MIN_GAP_BETWEEN_CLIPS = 45.0  # Avoid repetitive clips

# YOLO detection
YOLO_DETECT_CLASSES = [1]  # 1 = bicycle
YOLO_MIN_CONFIDENCE = 0.10
YOLO_BATCH_SIZE = 4

# Camera weights (for multi-camera prioritization)
CAMERA_WEIGHTS = {
    "Fly12Sport": 1.0,  # Front camera
    "Fly6Pro": 1.0,     # Rear camera
}

# Scene detection
SCENE_PRIORITY_MODE = True
SCENE_HIGH_THRESHOLD = 0.50   # High-activity threshold
SCENE_MAJOR_THRESHOLD = 0.70  # Major event threshold

# Zone filtering (reduce start/end clips)
START_ZONE_DURATION_S = 1200.0  # First 20 minutes
MAX_START_ZONE_FRAC = 0.10      # Max 10% of clips from start
END_ZONE_DURATION_S = 1200.0
MAX_END_ZONE_FRAC = 0.10

# Hardware acceleration
USE_MPS = True  # Metal Performance Shaders (M1)
FFMPEG_HWACCEL = 'videotoolbox'  # Hardware encoding
```

### Per-Project Settings

Projects are stored in `PROJECTS_ROOT/{ride_name}/`:
```
2025-12-28 Highvale Petrie Mt Mee/
├── source_videos/          # Input: Fly12Sport_*.MP4, Fly6Pro_*.MP4
├── ride.gpx               # Input: GPS track
├── working/               # Intermediate CSVs
│   ├── flatten.csv
│   ├── camera_offsets.json
│   ├── extract.csv
│   ├── enrich.csv
│   └── select.csv
├── clips/                 # Individual video clips
├── frames/                # Extracted JPEG frames (if enabled)
├── logs/                  # Pipeline logs
└── {ride_name}.mp4       # Final output
```

## Camera-Specific Timing

### Cycliq Metadata Quirks

Both Cycliq cameras store `creation_time` in MP4 metadata, but with different behaviors:

| Camera | creation_time | Correction |
|--------|--------------|------------|
| **Fly12Sport** | End of recording **+ 2 seconds** | Subtract `duration + 2` |
| **Fly6Pro** | Exact end of recording | Subtract `duration + 0` |

This is **automatically detected** by `video_utils.detect_camera_creation_time_offset()`.

### Why This Matters

Without correction:
- Timestamps drift 2 seconds late for Fly12Sport
- Camera offset incorrectly calculated as 13s (should be 11s)
- Frame timestamps don't match burnt-in video timestamps

With correction:
- Frame timestamps align perfectly with burnt-in video display
- Correct camera offset (11s in test footage)
- Accurate GPX sync for speed/elevation overlays

## Troubleshooting

### Empty extract.csv

**Symptoms:**
```
WARNING: No frames generated (possibly all before GPX start)
```

**Causes:**
1. Missing `flatten.csv` - Run flatten step first
2. Camera offsets not loaded - Run align step first
3. All video timestamps before GPX start time

**Fix:**
```bash
# Ensure steps run in order:
python -m source.steps.flatten  # Creates flatten.csv
python -m source.steps.align    # Creates camera_offsets.json
python -m source.steps.extract  # Should now work
```

### Camera Alignment Errors

**Symptoms:**
```
ERROR: fix_cycliq_utc_bug() missing 2 required positional arguments
```

**Fix:**
- Ensure `video_utils.py` is updated with the latest version
- Check that `align.py` passes `video_path` to `infer_recording_start()`

### Timestamp Mismatch

**Symptoms:**
- CSV timestamps don't match burnt-in video timestamps
- Camera offsets seem wrong

**Diagnosis:**
```bash
# Extract a test frame and check timestamp
ffmpeg -i source_videos/Fly12Sport_1131.MP4 -vf "select=eq(n\,450)" -frames:v 1 -update 1 test_frame.jpg

# Check metadata
ffprobe -v quiet -print_format json -show_entries format_tags=creation_time source_videos/Fly12Sport_1131.MP4
```

**Expected behavior:**
- Frame 450 at 30fps = 15 seconds into video
- If video starts at 19:01:49, frame 450 should show 19:02:04
- If timestamps don't match, camera offset detection may need updating

### YOLO Performance

**For M1 Macs:**
```python
# Enable Metal Performance Shaders
USE_MPS = True  # in config.py
```

**For slower machines:**
```python
# Reduce batch size
YOLO_BATCH_SIZE = 1  # Process one frame at a time

# Reduce image size
YOLO_IMAGE_SIZE = 320  # Faster than 640 (default)
```

## Technical Details

### Time Model

The pipeline uses a unified time model across all stages:

```
real_start_epoch = creation_time_utc - (duration + camera_offset)
abs_time_epoch = real_start_epoch + seconds_into_clip
session_ts_s = abs_time_epoch - global_session_start_epoch
```

Where:
- `creation_time_utc`: From MP4 metadata (after UTC bug fix)
- `camera_offset`: Per-camera creation_time bias (Fly12Sport: 2s, Fly6Pro: 0s)
- `global_session_start_epoch`: Earliest aligned camera start time
- `session_ts_s`: Used for partner matching and GPX lookups

### Partner Matching

Clips are matched across cameras using temporal tolerance:

```python
PARTNER_TIME_TOLERANCE_S = 1.0  # Must be within 1 second

# Example:
# Fly12Sport clip at session_ts = 125.3s
# Fly6Pro clip at session_ts = 125.8s
# Delta = 0.5s < 1.0s → Match found!
```

### GPX Enrichment

Frame metadata is enriched with GPS data using nearest-neighbor lookup:

```python
GPX_TOLERANCE = 1.0  # Match if within 1 second

# For each frame:
# 1. Find GPX point where abs(gpx_epoch - frame_epoch) < 1.0
# 2. Copy telemetry: speed, elevation, gradient, lat, lon, hr, cadence
```

## Development

### Adding New Camera Models

Edit `video_utils.py`:

```python
def detect_camera_creation_time_offset(video_path: Path) -> float:
    known_offsets = {
        "Fly12Sport": 2.0,
        "Fly6Pro": 0.0,
        "YourNewCamera": 0.5,  # Add your camera here
    }
    return known_offsets.get(camera_name, 0.0)
```

### Custom Scoring Weights

Edit `config.py`:

```python
SCORE_WEIGHTS = {
    "detect_score": 0.30,   # Increase to prioritize detections
    "scene_boost": 0.20,    # Decrease to reduce scene bias
    "speed_kmh": 0.30,      # Increase to favor high-speed moments
    "gradient": 0.10,
    "bbox_area": 0.10,
}
```

### Extending YOLO Classes

```python
# Detect cars and motorcycles
YOLO_DETECT_CLASSES = [1, 2, 3]  # bicycle, car, motorcycle

# Custom class weights
YOLO_CLASS_WEIGHTS = {
    "bicycle": 3.0,      # Prioritize cyclists
    "car": 1.0,
    "motorcycle": 2.0,
    "truck": 1.0,
}
```

## License


## Acknowledgments

- **YOLO**: Ultralytics YOLOv8 for object detection
- **FFmpeg**: Video processing and encoding
- **Cycliq**: Fly12Sport and Fly6Pro camera systems
- **OpenStreetMap**: Basemap tiles for minimap generation

## Support

For issues, questions, or contributions:
- Open an issue on GitHub
- Check logs in `{project}/logs/`
- Enable debug logging: `LOG_LEVEL = 'DEBUG'` in config.py

**Built with as a hobby for the cycling community**