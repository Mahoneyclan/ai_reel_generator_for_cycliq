# Velo Films AI

**Automated cycling highlight reel generator for dual-camera Cycliq setups**

Transform hours of cycling footage into cinematic highlight reels using AI-powered scene detection, bicycle tracking, and GPS telemetry overlays.

---

## 🎯 Features

### Core Pipeline
- ✅ **Dual-camera sync** - Automatically aligns Fly12 Sport & Fly6 Pro footage
- ✅ **AI bike detection** - YOLOv8 identifies cyclists and interesting moments
- ✅ **Scene change detection** - Highlights visual transitions and action
- ✅ **GPS enrichment** - Overlays speed, heart rate, cadence, elevation, gradient
- ✅ **Smart selection** - AI pre-selects clips, you review and finalize
- ✅ **Cinematic output** - PiP, minimaps, gauges, intro/outro with music

### User Experience
- 🖥️ **Native macOS GUI** - Clean, intuitive interface
- 📊 **Real-time progress** - Live feedback during all operations
- 🔍 **Analysis tools** - Identify bottlenecks in clip selection
- 🎬 **Visual review** - Preview all candidate clips before finalizing
- ⚙️ **Preferences** - Fine-tune detection, scoring, and output settings

### Performance
- ⚡ **M1 optimized** - Hardware acceleration for encoding & detection
- 🚀 **Streaming mode** - No intermediate JPEG extraction
- 🔄 **Parallel import** - 2-3x faster clip copying from cameras
- 💾 **Memory efficient** - Processes long rides without RAM issues

---

## 📋 Requirements

### Hardware
- **Mac Mini M1** (or any Apple Silicon Mac)
- **Cycliq cameras**: Fly12 Sport (front) + Fly6 Pro (rear)
- **Optional**: Garmin/Wahoo GPS device for telemetry

### Software
- **macOS 12+** (Monterey or later)
- **Python 3.9+**
- **FFmpeg** with VideoToolbox support
- **YOLOv8** (auto-downloads on first run)
- **Strava Account** (optional, for GPX import)

### Python Dependencies
```bash
pip install -r requirements.txt
```

**Core packages:**
- PySide6 (GUI)
- ultralytics (YOLO)
- opencv-python
- pillow
- gpxpy
- geopandas
- contextily
- matplotlib
- requests (Strava API)

---

## 🚀 Quick Start

### 1. Installation

```bash
# Clone repository
git clone https://github.com/yourusername/velo_films_ai.git
cd velo_films_ai

# Install dependencies
pip install -r requirements.txt

# Install FFmpeg (if not already installed)
brew install ffmpeg
```

### 2. Project Setup

**Option A: Import from Strava (Recommended)**

```bash
# Launch GUI
python main.py
```

1. Click **"Get Strava GPX"**
2. Follow OAuth login (first time only)
3. Select ride from your Strava activities
4. GPX auto-downloads to project folder
5. Continue with step 3 below

**Option B: Import from Cameras**

```bash
# Launch GUI
python main.py
```

**First-time setup:**
1. Click **"Import Clips"** to copy footage from cameras
2. Select cameras (Fly12S, Fly6Pro) and set ride date/name
3. Wait for import to complete
4. Select the newly created project from the list

### 3. Run Pipeline

**Step-by-step workflow:**

1. **Prepare** - Validates inputs, aligns camera timestamps
2. **Analyze** - AI detects bikes, scores scenes, enriches with GPS
3. **Select** - AI pre-selects clips, you review and finalize
4. **Build** - Renders clips with overlays and assembles final video

Each step takes 5-15 minutes depending on ride length.

### 4. Output

Final video saved to:
```
/Volumes/GDrive/Fly_Projects/[YYYY-MM-DD Ride Name]/[YYYY-MM-DD Ride Name].mp4
```

---

## 📁 Project Structure

```
velo_films_ai/
├── source/
│   ├── config.py              # Global configuration
│   ├── io_paths.py            # Path helpers
│   ├── main.py                # GUI entry point
│   │
│   ├── core/                  # Pipeline orchestration
│   │   ├── pipeline_executor.py
│   │   ├── step_registry.py
│   │   └── models/
│   │
│   ├── steps/                 # Pipeline stages
│   │   ├── preflight.py       # Input validation
│   │   ├── flatten.py         # GPX parsing
│   │   ├── align.py           # Camera sync
│   │   ├── extract.py         # Frame metadata
│   │   ├── analyze.py         # AI detection + scoring
│   │   ├── select.py          # Clip selection
│   │   ├── build.py           # Clip rendering
│   │   ├── splash.py          # Intro/outro
│   │   └── concat.py          # Final assembly
│   │
│   ├── gui/                   # User interface
│   │   ├── main_window.py
│   │   ├── manual_selection_window.py
│   │   ├── preferences_window.py
│   │   ├── import_window.py
│   │   └── controllers/       # UI logic
│   │
│   └── utils/                 # Shared utilities
│       ├── gpx.py             # GPS handling
│       ├── video_utils.py     # Video I/O
│       ├── map_overlay.py     # Minimap rendering
│       ├── gauge_overlay.py   # HUD gauges
│       └── progress_reporter.py
│
├── assets/                    # Static resources
│   ├── velo_films.png         # Logo
│   └── music/                 # Background tracks
│
└── tests/                     # Unit tests
```

---

## ⚙️ Configuration

### Key Settings (Preferences Window)

**Core Pipeline:**
- `EXTRACT_FPS` - Frame sampling rate (default: 1.0 fps)
- `HIGHLIGHT_TARGET_DURATION_S` - Target video length (default: 180s)
- `MIN_GAP_BETWEEN_CLIPS` - Spacing between clips (default: 45s)
- `SCENE_COMPARISON_WINDOW_S` - Scene detection sensitivity (default: 8s)

**Detection:**
- `YOLO_MIN_CONFIDENCE` - Detection threshold (default: 0.10)
- `YOLO_DETECT_CLASSES` - Object classes to detect (default: bicycle)
- `MIN_DETECT_SCORE` - Minimum score for clip inclusion (default: 0.10)

**Scoring Weights:**
```python
SCORE_WEIGHTS = {
    "detect_score": 0.20,    # Bike detection confidence
    "scene_boost": 0.35,     # Scene change magnitude
    "speed_kmh": 0.25,       # Riding speed
    "gradient": 0.10,        # Hill gradient
    "bbox_area": 0.10,       # Detection box size
}
```

**M1 Performance:**
- `USE_MPS` - Enable GPU acceleration (default: True)
- `YOLO_BATCH_SIZE` - Detection batch size (default: 4)
- `FFMPEG_HWACCEL` - Hardware encoder (default: videotoolbox)

### Advanced Configuration

Edit `source/config.py` directly for:
- Camera time offsets
- PiP/minimap sizing
- HUD gauge layout
- Zone penalties (start/end of ride)
- Music volume levels

---

## 🎬 Usage Guide

### Manual Clip Selection

After the **Analyze** step, the **Select** step opens a review window:

1. **Preview Mode**
   - Each "moment" shows Primary + Partner camera frames
   - Metadata displayed: time, speed, detection score, scene change
   - Green border = AI recommended, Gray = candidate

2. **Selection Controls**
   - Click a perspective to select its frame pair
   - Only one perspective per moment can be selected
   - Click again to deselect

3. **Finalization**
   - Counter shows: "Selected: X clips"
   - "Use X Clips & Continue" persists selection to `select.csv`

### Analysis Tools

**Selection Analyzer** (after Analyze step):
- Shows bottlenecks in clip filtering
- Provides actionable recommendations
- Displays score distributions

Access via: **Analyze Selection** button

**Log Viewer**:
- View detailed pipeline logs
- Filter by step or severity
- Useful for debugging

Access via: **View Log** button

### Import from Cameras

**Import Clips** workflow:
1. Mount Fly12S and Fly6Pro (appear as volumes)
2. Click **Import Clips**
3. Select cameras to import from
4. Set ride date and name
5. Wait for parallel copy (shows progress)

Files copied to: `/Volumes/GDrive/Fly/[YYYY-MM-DD Ride Name]/`

---

## 🔧 Troubleshooting

### No Clips Selected

**Symptoms:** Select step completes but `select.csv` is empty

**Solutions:**
1. Run **Analyze Selection** to identify bottleneck
2. Lower `MIN_DETECT_SCORE` in Preferences (try 0.05)
3. Add more YOLO detection classes (person, car, motorcycle)
4. Reduce `MIN_GAP_BETWEEN_CLIPS` for denser selection

### Camera Time Misalignment

**Symptoms:** Partner frames don't match, PiP shows wrong timing

**Solutions:**
1. Check `camera_offsets.json` in project's `working/` folder
2. Manually adjust `CAMERA_TIME_OFFSETS` in Preferences
3. Re-run **Prepare** step after adjustment

### GPU/MPS Errors

**Symptoms:** "MPS backend not available" or slow YOLO

**Solutions:**
1. Disable `USE_MPS` in Preferences (M1 Performance tab)
2. Reduce `YOLO_BATCH_SIZE` to 1 or 2
3. Update PyTorch: `pip install --upgrade torch torchvision`

### Memory Issues

**Symptoms:** "Killed" or system slowdown during extract/analyze

**Solutions:**
1. Reduce `EXTRACT_FPS` (try 0.5 fps)
2. Lower `YOLO_BATCH_SIZE` to 2
3. Process shorter rides first
4. Close other apps during pipeline execution

### No GPS Data

**Symptoms:** "⚠️ No GPX files found" in preflight

**Solutions:**
1. **Import from Strava:** Click "Get Strava GPX" button
2. **Manual copy:** Ensure `ride.gpx` exists in source folder
3. Pipeline continues without GPS (minimaps/telemetry disabled)
4. Manually copy GPX from Garmin/Wahoo to ride folder

### Strava Authentication Failed

**Symptoms:** "Failed to authenticate with Strava"

**Solutions:**
1. Verify Strava app is configured:
   - Check `source/strava/strava_config.py`
   - Set `CLIENT_ID` and `CLIENT_SECRET`
2. Create Strava app at: https://www.strava.com/settings/api
3. Set callback domain to `localhost`
4. Clear old tokens: `rm ~/.velo_films/strava_tokens.json`
5. See `STRAVA_SETUP.md` for detailed instructions

---

## 📊 Output Structure

```
/Volumes/GDrive/Fly_Projects/[Project Name]/
├── [Project Name].mp4         # Final highlight reel
├── logs/                      # Pipeline logs (per step)
├── working/                   # Pipeline data (CSVs + JSON)
│   ├── flatten.csv            # GPX timeline (1 Hz)
│   ├── extract.csv            # Frame metadata
│   ├── enriched.csv           # AI scores + GPS
│   ├── select.csv             # Selected clips
│   └── camera_offsets.json    # Sync offsets
├── clips/                     # Individual highlight clips
│   ├── clip_0001.mp4
│   ├── clip_0002.mp4
│   └── ...
├── frames/                    # Extracted preview frames (JPEGs)
├── splash_assets/             # Intro/outro resources
├── minimaps/                  # Pre-rendered minimaps (PNGs)
├── gauges/                    # Pre-rendered gauges (PNGs)
└── _middle_01.mp4             # Intermediate segments
    _middle_02.mp4
    _intro.mp4
    _outro.mp4
```

### CSV Schema

**enriched.csv** (main dataset):
- `index` - Unique frame ID (camera_clip_frame)
- `camera` - Fly12Sport / Fly6Pro
- `video_path` - Source MP4 file
- `frame_number` - Frame index in video
- `abs_time_epoch` - GPS timestamp
- `detect_score` - YOLO confidence (0.0-1.0)
- `scene_boost` - Scene change score (0.0-1.0)
- `speed_kmh`, `hr_bpm`, `cadence_rpm`, etc. - Telemetry
- `partner_index` - Paired frame from other camera
- `score_weighted` - Final composite score

**select.csv** (candidates + recommended):
- All fields from `enriched.csv`
- `recommended` - "true" / "false" (AI pre-selection)

---

## 🎨 Customization

### Adding Music Tracks

1. Place `.mp3` files in `assets/music/`
2. Pipeline randomly selects tracks for segments
3. Volume adjustable via `MUSIC_VOLUME` in Preferences

### Changing Intro/Outro

1. Replace `assets/velo_films.png` with your logo
2. Edit `assets/intro.mp3` and `assets/outro.mp3`
3. Modify timing in `source/steps/splash_helpers/intro_builder.py`

### Custom Gauge Layout

Edit `source/utils/gauge_overlay.py`:
- `SPEED_GAUGE_SIZE` - Main gauge size
- `SMALL_GAUGE_SIZE` - Telemetry gauge size

Reposition in `source/steps/build_helpers/gauge_renderer.py`:
- `calculate_gauge_positions()` method

### Scoring Algorithm

Adjust weights in Preferences or `config.py`:
```python
SCORE_WEIGHTS = {
    "detect_score": 0.20,   # Increase for more bike-focused clips
    "scene_boost": 0.35,    # Increase for more action/transitions
    "speed_kmh": 0.25,      # Increase for faster riding
    "gradient": 0.10,       # Increase for climbs
    "bbox_area": 0.10,      # Increase for closer detections
}
```

---

## 🧪 Testing

```bash
# Run unit tests
pytest tests/

# Run specific test module
pytest tests/test_gpx.py

# Run with coverage
pytest --cov=source tests/
```

**Test structure:**
- `tests/test_gpx.py` - GPS parsing and indexing
- `tests/test_video_utils.py` - Frame extraction
- `tests/test_selection.py` - Clip selection logic
- `tests/test_pipeline.py` - End-to-end integration

---

## 🐛 Known Issues

1. **Strava GPX Import** - Not yet implemented (coming next)
2. **Multi-ride Projects** - Currently one project = one ride
3. **Windows/Linux** - Untested (macOS M1 only for now)
4. **4K Video** - High memory usage, reduce batch sizes

---

## 🗺️ Roadmap

### v1.1 (Current)
- ✅ **Strava GPX import via OAuth** - Download rides directly from Strava
- ⬜ Batch processing (multiple rides)
- ⬜ Custom detection zones (highlight specific segments)

### v1.2 (Future)
- ⬜ Windows/Linux support
- ⬜ Cloud rendering (offload heavy processing)
- ⬜ Web dashboard for project management
- ⬜ Advanced color grading

### v2.0 (Vision)
- ⬜ Multi-camera support (3+ cameras)
- ⬜ Live streaming integration
- ⬜ AI-generated commentary
- ⬜ Social media auto-posting


---

**Built with as a hobby for the cycling community**