## TODO

### COMPLETED

#### Performance Optimizations (Phase 1)
[x] **Hardware codec detection** - Auto-select optimal FFmpeg encoder
  - `source/utils/hardware.py` - New hardware detection module
  - Apple Silicon: `h264_videotoolbox` (hardware accelerated)
  - Intel Mac: Falls back to `libx264` (software)
  - `source/config.py` - Added PREFERRED_CODEC setting ✓

[x] **Dynamic worker scaling** - Task-specific parallelism
  - Removed arbitrary 8-worker cap
  - FFmpeg tasks: half of CPU cores
  - I/O tasks (minimap, gauge, elevation): scales with CPU count
  - `source/steps/build.py`, all pre-renderers ✓

[x] **Adaptive YOLO batch size** - Based on system RAM
  - 8GB → batch 8, 16GB → batch 16, 32GB → batch 32
  - `source/utils/hardware.py:get_yolo_batch_size()` ✓

[x] **Increase minimap zoom level** - Higher detail
  - `source/config.py` - MAP_ZOOM_PIP: 14 → 15 ✓

#### Video Processing
[x] **FFmpeg hardware acceleration** - Use `h264_videotoolbox` instead of `libx264`
  - `source/steps/build_helpers/clip_renderer.py` ✓
  - `source/steps/splash_helpers/animation_renderer.py` ✓

[x] **Smooth clip transitions** - Professional crossfade transitions
  - 0.2s crossfade between all clips using FFmpeg xfade filter
  - 0.3s fade in on first clip (after intro)
  - 0.3s fade out on last clip (before outro)
  - Audio crossfade with acrossfade filter
  - `source/steps/build_helpers/segment_concatenator.py` ✓

[x] **Audio normalization** - Consistent volume across clips and music
  - Added loudnorm filter (-16 LUFS broadcast standard) to camera audio
  - Added loudnorm to music mixing for consistent levels
  - `source/utils/ffmpeg.py`, `source/steps/build_helpers/segment_concatenator.py` ✓

#### Detection & Analysis
[x] **Increase YOLO batch size** - Default 4 too small for modern GPUs
  - `source/config.py` - Changed default from 4 to 8 ✓

[x] **Expand YOLO detection classes** - More cycling-relevant objects
  - Default now: person, bicycle, car, motorcycle, bus, truck, traffic light, stop sign
  - Added bus (5) to class map and available classes ✓

[x] **Fix score weights sum** - Weights must sum to 1.0
  - `source/config.py` ✓

#### Pre-rendering & Overlays
[x] **Parallelize minimap pre-rendering** - Now uses ThreadPoolExecutor
  - `source/steps/build_helpers/minimap_prerenderer.py` ✓

[x] **Parallelize elevation pre-rendering** - Now uses ThreadPoolExecutor
  - `source/steps/build_helpers/elevation_prerenderer.py` ✓

[x] **Pre-composite gauge overlays** - Single PNG per clip instead of 5 overlays
  - `source/steps/build_helpers/gauge_prerenderer.py` - Parallel composite rendering
  - `source/steps/build_helpers/clip_renderer.py` - Single overlay filter
  - `source/steps/build.py` - Integration with GaugePrerenderer ✓

[x] **Parallelize splash PNG saves** - Uses ThreadPoolExecutor
  - `source/steps/splash_helpers/animation_renderer.py` - Parallel frame saving ✓

[x] **Minimap sizing and positioning** - Fixed
  - Renders at route's geographic aspect ratio
  - Maximizes available space: width = PIP width, height = video - PIP - elevation - margins
  - Dynamic elevation plot positioning based on actual minimap height
  - `source/utils/map_overlay.py`, `source/steps/build_helpers/minimap_prerenderer.py` ✓

[x] **Trophy overlays in separate folder** - Moved from clips/ to trophies/
  - `source/config.py` - Added TROPHY_DIR property
  - `source/io_paths.py` - Added trophy_dir() function
  - `source/steps/build_helpers/clip_renderer.py` - Updated trophy path ✓

#### Configuration & Logging
[x] **Reduce log file count** - Filter to app modules only
  - `source/utils/log.py` - Added APP_LOG_PREFIXES filter ✓

[x] **Fix RIDE_FOLDER reset bug** - Preserve runtime values in reload_config()
  - `source/config.py:reload_config()` ✓

[x] **GPX file location** - Relocate from raw movies to working files
  - Added `CFG.GPX_FILE` property pointing to `WORKING_DIR / "ride.gpx"`
  - Updated Strava/Garmin import panels to save GPX to project folder
  - Pipeline steps check project dir first, fallback to raw input ✓

#### GUI & Tools
[x] **Camera Offset Calibration Window** - Visual offset adjustment tool
  - `source/gui/camera_offset_window.py` - New calibration window
  - Shows thumbnails with burnt-in timestamps vs calculated times
  - Per-camera spinbox controls for real-time adjustment
  - Saves to project_config.json (per-project) and updates CameraRegistry
  - Note: H.265 vs H.264 codec choice affects write timing ✓

[x] **Auto-detect hardware capabilities** - Adjust settings for MacBook Air vs Mac Mini
  - `source/utils/hardware.py` - Detects Apple Silicon, RAM, CPU cores
  - Logs system info at build start for diagnostics ✓

---

### PENDING (Optional)

[ ] **Asset caching** - Skip re-rendering unchanged minimaps/gauges/elevation
  - Cache with content hashes
  - Check hash before rendering, skip if unchanged
  - Medium complexity, affects all pre-renderer classes

[ ] **CSV streaming** - Memory-efficient handling for large projects (10,000+ frames)
  - Stream CSV rows in chunks instead of loading entire file
  - Only needed for very large projects
