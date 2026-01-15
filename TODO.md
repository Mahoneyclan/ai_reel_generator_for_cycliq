## TODO

### COMPLETED
[x] **FFmpeg hardware acceleration** - Use `h264_videotoolbox` instead of `libx264`
  - `source/steps/build_helpers/clip_renderer.py:356` ✓
  - `source/steps/splash_helpers/animation_renderer.py:215` ✓

[x] **Increase YOLO batch size** - Default 4 too small for modern GPUs
  - `source/config.py:130` - Changed default from 4 to 8 ✓

[x] **Parallelize minimap pre-rendering** - Now uses ThreadPoolExecutor
  - `source/steps/build_helpers/minimap_prerenderer.py` ✓

[x] **Parallelize elevation pre-rendering** - Now uses ThreadPoolExecutor
  - `source/steps/build_helpers/elevation_prerenderer.py` ✓

[x] **Audio normalization** - Consistent volume across clips and music
  - Added loudnorm filter (-16 LUFS broadcast standard) to camera audio
  - Added loudnorm to music mixing for consistent levels
  - `source/utils/ffmpeg.py`, `source/steps/build_helpers/segment_concatenator.py` ✓

[~] **Minimap sizing and positioning** - Partially working
  - ✓ Renders at route's geographic aspect ratio
  - ✓ Scales to fit within PIP width and height constraints
  - ✓ Dynamic elevation plot positioning based on actual minimap height
  - ✗ Width still not always matching PIP exactly for some route shapes
  - `source/utils/map_overlay.py`, `source/steps/build_helpers/minimap_prerenderer.py`, `source/steps/build_helpers/clip_renderer.py`

[x] **Reduce log file count** - Filter to app modules only
  - `source/utils/log.py` - Added APP_LOG_PREFIXES filter ✓

[x] **Fix RIDE_FOLDER reset bug** - Preserve runtime values in reload_config()
  - `source/config.py:reload_config()` ✓

[x] **Expand YOLO detection classes** - More cycling-relevant objects
  - Default now: person, bicycle, car, motorcycle, bus, truck, traffic light, stop sign
  - Added bus (5) to class map and available classes ✓

[x] **Fix score weights sum** - Weights must sum to 1.0
  - `source/config.py` ✓

[x] **Smooth clip transitions** - Professional crossfade transitions
  - 0.2s crossfade between all clips using FFmpeg xfade filter
  - 0.3s fade in on first clip (after intro)
  - 0.3s fade out on last clip (before outro)
  - Audio crossfade with acrossfade filter
  - `source/steps/build_helpers/segment_concatenator.py` ✓

[x] **GPX file location** - Relocate from raw movies to working files
  - Added `CFG.GPX_FILE` property pointing to `WORKING_DIR / "ride.gpx"`
  - Updated Strava/Garmin import panels to save GPX to project folder
  - Pipeline steps (flatten, build, intro) check project dir first, fallback to raw input
  - `source/config.py`, `source/importer/import_controller.py`, `source/io_paths.py` ✓

### PENDING

[ ] **Camera Offset Calibration Window** - Compare burnt-in timestamp to metadata
  - **Priority**: High (run before analysis phase)
  - **Purpose**: Adjust per-camera KNOWN_OFFSETS by visually comparing:
    1. Burnt-in timestamp (visible in frame)
    2. Raw metadata creation_time
    3. Calculated start time (creation_time - duration + offset)
  - **UI Layout** (based on manual_selection_window skeleton):
    - Grid view: first frame from each clip, grouped by camera
    - Left column: Fly6Pro clips with thumbnails + metadata
    - Right column: Fly12Sport clips with thumbnails + metadata
    - Each cell shows: thumbnail, filename, burnt-in time, metadata time, calculated time, delta
  - **Data source**: align.csv and extract.csv (pre-analysis data)
  - **Controls**:
    - Spinbox per camera to adjust offset in real-time
    - "Recalculate" button to update calculated times
    - "Save to Config" button to persist KNOWN_OFFSETS
  - **Files to create/modify**:
    - NEW: `source/gui/camera_offset_window.py`
    - Reference: `source/gui/manual_selection_window.py` (skeleton)
    - Config: `source/config.py` (KNOWN_OFFSETS)

[ ] **Pre-composite gauge overlays** - 5 separate gauge inputs cause re-encoding
  - `source/steps/build_helpers/clip_renderer.py:298-335`
  - Render all gauges to single PNG, overlay once

[ ] **Parallelize splash PNG saves** - Sequential PIL saves
  - `source/steps/splash_helpers/animation_renderer.py:203-205`

[ ] **Auto-detect hardware capabilities** - Adjust settings for MacBook Air vs Mac Mini
