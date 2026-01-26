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

#### Clip Selection
[x] **Allow single-camera moments** - Relax strict camera pairing requirement
  - Single-camera moments now allowed in selection (previously dropped 20-50%)
  - Added `dual_camera` weight (0.05) to prefer dual-perspective moments
  - Reduced `scene_boost` weight from 0.35 → 0.30 to accommodate
  - `source/config.py` - Added `dual_camera` to SCORE_WEIGHTS ✓
  - `source/steps/select.py` - Relaxed `_group_rows_by_moment()` pairing logic ✓
  - Added `is_single_camera` flag to select.csv output ✓

---

### PENDING

#### P1 - High Impact / Core Quality

[ ] **Further selection algorithm tuning** - Additional improvements if needed
  - ~~Camera pairing too strict~~ ✓ FIXED - single-camera moments now allowed
  - Sampling grid: 5-second intervals may miss peak action
  - Candidate pool: Consider increasing `CANDIDATE_FRACTION` 2.5 → 5.0
  - Gap filtering: Consider reducing `MIN_GAP_BETWEEN_CLIPS` 15s → 10s
  - Weight tuning: May need further adjustment based on results

[ ] **Hide gauges with null data** - Don't display gauges when data is unavailable
  - Problem: Gauges may show placeholder or zero values when data is null/missing
  - Solution: Check each gauge's data before rendering; skip if null
  - Examples: No speed data (GPS dropout), no heart rate (sensor disconnected), no elevation
  - `source/steps/build_helpers/gauge_prerenderer.py` - Add null checks before rendering each gauge
  - Consider: Show partial gauge panel with only available data vs hide entire panel

#### P2 - Workflow Improvements

[ ] **Improve raw file visualization in manual_select** - Distinguish source video files
  - Problem: Hard to identify which raw video file each clip originates from
  - Solution: Add visual separators or labels showing source file boundaries
  - Could use: color coding, section headers, file name labels, or timeline markers
  - `source/gui/manual_select.py` - Manual selection interface

[x] **Single-camera clip rendering** - Display layout for single-perspective clips
  - Selection allows single-camera moments ✓
  - Rendering renders main camera full-width (no PiP) for single-camera clips ✓
  - `source/steps/build.py` - `_load_recommended_moments()` allows pip=None ✓
  - `source/steps/build_helpers/clip_renderer.py` - Handles `pip_row=None` ✓

#### P3 - Visual Enhancements

[ ] **Distance-based elevation plot** - Switch x-axis from time to distance
  - Problem: When ride is paused (stationary periods), time-based plot shows flat sections
  - Solution: Use cumulative km travelled on x-axis instead of time
  - Provides consistent visual scale regardless of stops/pauses
  - `source/steps/build_helpers/elevation_prerenderer.py` - Update x-axis calculation
  - `source/analysis/elevation.py` - May need distance calculation utilities
  - Consider: Should handle zero-distance segments (GPS drift while stationary)

[x] **Handle single-camera segments** - Continue processing when one camera battery dies
  - Selection handles single-camera moments ✓
  - Rendering handles single-camera clips (full-width, no PiP) ✓
  - Real-world scenario: Front camera dies at 2hr mark, rear camera continues to 3hr mark
  - Implemented: Option A - Show available camera full-width, no PIP inset ✓

#### P4 - Performance / Infrastructure

[ ] **Asset caching** - Skip re-rendering unchanged minimaps/gauges/elevation
  - Cache with content hashes
  - Check hash before rendering, skip if unchanged
  - Medium complexity, affects all pre-renderer classes

[ ] **Dynamic gauge rendering** - Real-time telemetry updates without storage explosion
  - Problem: Current gauges show static values per clip segment (e.g., one gauge for 4.5-second clip)
  - Goal: Speed/cadence/HR update live during playback without generating thousands of PNGs
  - **Current approach:** 1 PNG per clip (~30 files for highlight reel) - efficient but static
  - **Research findings - Alternative approaches:**
    | Approach | Storage | Dynamic | Complexity |
    |----------|---------|---------|------------|
    | FFmpeg drawtext | Zero | Per-frame | Low |
    | Gauge video loop + text | ~5-10 MB | Per-frame | Medium |
    | Per-second cached PNGs | ~500-1000 files | Per-second | Low |
  - **Recommended: FFmpeg drawtext filter**
    - Zero PNG generation overhead
    - Per-frame telemetry accuracy via expression evaluation
    - Filter: `drawtext=text='Speed\: %{expr}':x=30:y=30`
    - Trade-off: text-only display (loses circular gauge visuals)
  - **Alternative: Hybrid gauge loop + drawtext**
    - Pre-render 2-second looping gauge background videos (~1-2 MB each)
    - Overlay with drawtext for live values
    - Maintains visual appeal + dynamic updates
  - **Implementation steps:**
    1. Pre-interpolate telemetry to frame resolution in ClipRenderer
    2. Use FFmpeg drawtext with expressions for live values
    3. Optional: create looping gauge background videos for visual appeal
  - **Files to modify:**
    - `source/steps/build_helpers/clip_renderer.py` - Add drawtext filter chain
    - `source/steps/build_helpers/gauge_prerenderer.py` - May become optional/removed
  - **Note:** Current approach is fine for highlight reels; this is only needed if dynamic updates are desired

#### P5 - Future / Research

[ ] **iMovie-style timeline selection** - Manual clip selection when algorithm fails
  - **Why needed:** Algorithm is missing high-value clips; need manual scrubbing to find them
  - Problem: Current grid-based card UI not intuitive for finding moments in long footage
  - Solution: Timeline-based selection like iMovie's scrubbing interface
  - **Research findings:**
    - **Recommended approach:** QGraphicsView-based timeline (used by Shotcut, Kdenlive)
    - **Reference library:** [asnunes/QTimeLine](https://github.com/asnunes/QTimeLine) - PyQt5 timeline widget
    - **Key features:**
      - Filmstrip view: horizontal strip of frame thumbnails (50-100px each)
      - Drag-to-select: click and drag to define in/out points
      - Hover preview: show frame time/enlarged thumbnail on hover
      - Zoom in/out: seconds vs minutes granularity (Ctrl+/- or slider)
      - Waveform display: librosa for audio visualization
    - **Architecture:**
      ```
      TimelineGraphicsView (QGraphicsView)
      └── TimelineScene (QGraphicsScene)
          ├── RulerTrack (time labels + grid)
          ├── FilmstripTrack (ThumbnailItems[])
          ├── SelectionOverlay (drag handles for in/out)
          ├── PlayheadCursor (vertical line)
          └── WaveformTrack (audio visualization)
      ```
    - **Thumbnail optimization:**
      - FFmpeg seeking (`-ss` before `-i`) = 3.8x faster extraction
      - QPixmapCache for runtime caching
      - Pre-cache during enrichment phase
      - Viewport culling (QGraphicsView renders only visible items)
    - **Dependencies to add:** `librosa`, `soundfile`, `scipy`
  - **Complexity:** High (~40-60 hours total)
    | Feature | Effort |
    |---------|--------|
    | Basic filmstrip + scroll | 4-6h |
    | Zoom in/out | 6-8h |
    | Selection handles (drag) | 6-8h |
    | Thumbnail caching | 4-6h |
    | Waveform display | 6-8h |
    | Full integration | 15-20h |
  - **Phased approach:**
    1. Foundation: TimelineGraphicsView + static filmstrip + time ruler
    2. Interaction: zoom + selection overlay + drag handles
    3. Polish: hover preview + metadata panel
    4. Advanced: waveform + keyboard shortcuts
  - **Files to modify/create:**
    - `source/gui/timeline_window.py` - New timeline UI
    - `source/gui/manual_selection_window.py` - May integrate or replace
  - **Note:** Keep moment-based model; timeline selects moment groups, not individual frames