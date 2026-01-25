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

[ ] **Review highlight selection algorithm** - Some high-value clips not being selected
  - Problem: Not all clips in project files are producing highlights despite having high value imagery
  - Investigation needed: Review scoring algorithm and selection thresholds
  - Check if certain visual features are being underweighted
  - Verify clip candidates aren't being filtered out prematurely
  - `source/analysis/scoring.py` - Scoring weights and thresholds
  - `source/steps/analyze.py` - Clip selection logic

[ ] **Improve raw file visualization in manual_select** - Distinguish source video files
  - Problem: Hard to identify which raw video file each clip originates from
  - Solution: Add visual separators or labels showing source file boundaries
  - Could use: color coding, section headers, file name labels, or timeline markers
  - `source/gui/manual_select.py` - Manual selection interface

[ ] **iMovie-style timeline selection** - More dynamic clip selection interface
  - Problem: Current selection uses discrete thumbnail grid, not intuitive for video editing
  - Solution: Research timeline-based selection like iMovie's scrubbing interface
  - Features to investigate:
    - Filmstrip view: continuous strip of frames you can scrub through
    - Drag to select: click and drag to define in/out points on timeline
    - Hover preview: show frame preview as mouse moves over timeline
    - Zoom in/out: adjust timeline granularity (seconds vs minutes)
    - Waveform display: audio visualization to help find interesting moments
  - Libraries to research: PyQt timeline widgets, video editing UI frameworks
  - `source/gui/manual_select.py` - Would need significant redesign

[ ] **Asset caching** - Skip re-rendering unchanged minimaps/gauges/elevation
  - Cache with content hashes
  - Check hash before rendering, skip if unchanged
  - Medium complexity, affects all pre-renderer classes

[ ] **CSV streaming** - Memory-efficient handling for large projects (10,000+ frames)
  - Stream CSV rows in chunks instead of loading entire file
  - Only needed for very large projects


[ ] **Distance-based elevation plot** - Switch x-axis from time to distance
  - Problem: When ride is paused (stationary periods), time-based plot shows flat sections
  - Solution: Use cumulative km travelled on x-axis instead of time
  - Provides consistent visual scale regardless of stops/pauses
  - `source/steps/build_helpers/elevation_prerenderer.py` - Update x-axis calculation
  - `source/analysis/elevation.py` - May need distance calculation utilities
  - Consider: Should handle zero-distance segments (GPS drift while stationary)

[ ] **Allow non-reciprocal clip pairs** - Don't require matching front/rear segments
  - Problem: Currently may require both Fly12 (front) and Fly6 (rear) footage for same timespan
  - Solution: Allow clips from only one camera if the other has no interesting content
  - Use case: Overtaking vehicle only visible from rear, or scenic view only from front
  - Benefits: More flexible clip selection, better utilization of single-camera moments
  - `source/analysis/scoring.py` or `source/steps/analyze.py` - Clip pairing logic
  - `source/steps/build_helpers/segment_concatenator.py` - Handle single-camera segments
  - Consider: How to display single-camera clips (full width? maintain PIP layout with blank?)

[ ] **Handle single-camera segments** - Continue processing when one camera battery dies
  - Problem: If Fly12 or Fly6 battery goes flat mid-ride, pipeline may fail or skip remaining footage
  - Solution: Allow clips from only available camera for any time period
  - Real-world scenario: Front camera dies at 2hr mark, rear camera continues to 3hr mark
  - Pipeline should: 
    - Detect when only one camera has footage for a timespan
    - Score and select clips from available camera only
    - Render single-camera clips with appropriate layout
  - **PIP handling options:**
    - Option A: Show available camera full-width, no PIP inset
   
  - `source/steps/analyze.py` - Camera availability detection per timestamp
  - `source/analysis/scoring.py` - Single-camera scoring logic
  - `source/steps/build_helpers/clip_renderer.py` - PIP layout logic for single-camera
  - `source/steps/build_helpers/segment_concatenator.py` - Handle mixed paired/single clips

[ ] **Hide gauges with null data** - Don't display gauges when data is unavailable
  - Problem: Gauges may show placeholder or zero values when data is null/missing
  - Solution: Check each gauge's data before rendering; skip if null
  - Examples: No speed data (GPS dropout), no heart rate (sensor disconnected), no elevation
  - `source/steps/build_helpers/gauge_prerenderer.py` - Add null checks before rendering each gauge
  - Consider: Show partial gauge panel with only available data vs hide entire panel

[ ] **Per-second gauge rendering** - Generate gauge overlays for each second of footage
  - Problem: Current gauges show static values per clip segment (e.g., one gauge for 10-second clip)
  - Solution: Generate unique gauge overlay for every second to show real-time data changes
  - Benefits: 
    - Speed gauge updates live as you accelerate/decelerate
    - Distance/elevation increment visibly throughout clip
    - More dynamic and engaging overlays
  - Implementation:
    - `source/steps/build_helpers/gauge_prerenderer.py` - Generate gauge per second instead of per clip
    - Storage: Create gauges/second_XXXXX.png for each timestamp
    - `source/steps/build_helpers/clip_renderer.py` - Apply time-indexed gauge sequence to video
    - FFmpeg: Use overlay with frame-accurate timing or concat filter with 1fps gauge video
  - Considerations:
    - Storage: ~3600 gauge PNGs for 1hr ride vs ~30 for highlight reel
    - Performance: Pre-rendering takes longer but playback unaffected
    - Caching strategy important for iterative builds