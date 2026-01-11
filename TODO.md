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

[x] **Minimap sizing and positioning** - Match PIP size and margin exactly
  - MINIMAP_SIZE_RATIO: 0.30 (matches PIP_SCALE_RATIO)
  - Fixed transparent padding issue causing incorrect positioning
  - Now uses tight crop with opaque background, resized to 576x576
  - 30px margin from top and right edges (same as PIP)
  - `source/config.py`, `source/utils/map_overlay.py`, `source/steps/build_helpers/clip_renderer.py` ✓

[x] **Reduce log file count** - Filter to app modules only
  - `source/utils/log.py` - Added APP_LOG_PREFIXES filter ✓

[x] **Fix RIDE_FOLDER reset bug** - Preserve runtime values in reload_config()
  - `source/config.py:reload_config()` ✓

[x] **Expand YOLO detection classes** - More cycling-relevant objects
  - Default now: person, bicycle, car, motorcycle, bus, truck, traffic light, stop sign
  - Added bus (5) to class map and available classes ✓

[x] **Fix score weights sum** - Weights must sum to 1.0
  - `source/config.py` ✓

### PENDING

[ ] **Smooth clip transitions** - Improve professionalism of clip transitions
  - Current: hard cuts between clips
  - Options: crossfade, dip-to-black, zoom/slide transitions
  - `source/steps/build_helpers/segment_concatenator.py`

[ ] **GPX file location** - Relocate from raw movies to working files

[ ] **Parallelize segment music overlay** - Complex refactor (deferred)
  - `source/steps/build_helpers/segment_concatenator.py:110-127`
  - Requires pre-calculating music offsets before parallel execution

[ ] **Pre-composite gauge overlays** - 5 separate gauge inputs cause re-encoding
  - `source/steps/build_helpers/clip_renderer.py:298-335`
  - Render all gauges to single PNG, overlay once

[ ] **Parallelize splash PNG saves** - Sequential PIL saves
  - `source/steps/splash_helpers/animation_renderer.py:203-205`

[ ] **Auto-detect hardware capabilities** - Adjust settings for MacBook Air vs Mac Mini
