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

[x] **Minimap sizing and positioning** - Fixed
  - ✓ Renders at route's geographic aspect ratio
  - ✓ Maximizes available space: width = PIP width, height = video - PIP - elevation - margins
  - ✓ Dynamic elevation plot positioning based on actual minimap height
  - ✓ Wide routes fill width (576px), tall routes fill height (532px)
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

[x] **Camera Offset Calibration Window** - Visual offset adjustment tool
  - `source/gui/camera_offset_window.py` - New calibration window
  - Shows thumbnails with burnt-in timestamps vs calculated times
  - Per-camera spinbox controls for real-time adjustment
  - Saves to project_config.json (per-project) and updates CameraRegistry
  - Accessible via Pipeline Panel > Project Tools > Calibrate button
  - Note: H.265 vs H.264 codec choice affects write timing (use same codec on both cameras) ✓

[x] **Pre-composite gauge overlays** - Single PNG per clip instead of 5 overlays
  - `source/steps/build_helpers/gauge_prerenderer.py` - Parallel composite rendering
  - `source/steps/build_helpers/clip_renderer.py` - Single overlay filter
  - `source/steps/build.py` - Integration with GaugePrerenderer ✓

[x] **Parallelize splash PNG saves** - Uses ThreadPoolExecutor
  - `source/steps/splash_helpers/animation_renderer.py` - Parallel frame saving ✓

[ ] **Auto-detect hardware capabilities** - Adjust settings for MacBook Air vs Mac Mini
