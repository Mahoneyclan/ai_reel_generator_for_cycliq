# Performance Optimization TODO

## Critical (5-10x speedup)

- [x] **FFmpeg hardware acceleration** - Use `h264_videotoolbox` instead of `libx264`
  - `source/steps/build_helpers/clip_renderer.py:356` ✓
  - `source/steps/splash_helpers/animation_renderer.py:215` ✓

- [x] **Increase YOLO batch size** - Default 4 too small for modern GPUs
  - `source/config.py:130` - Changed default from 4 to 8 ✓

## High Impact (2-4x speedup)

- [x] **Parallelize minimap pre-rendering** - Now uses ThreadPoolExecutor
  - `source/steps/build_helpers/minimap_prerenderer.py` ✓

- [x] **Parallelize elevation pre-rendering** - Now uses ThreadPoolExecutor
  - `source/steps/build_helpers/elevation_prerenderer.py` ✓

- [ ] **Parallelize segment music overlay** - Complex refactor (deferred)
  - `source/steps/build_helpers/segment_concatenator.py:110-127`
  - Requires pre-calculating music offsets before parallel execution

## Medium Impact (1.5-2x speedup)

- [ ] **Pre-composite gauge overlays** - 5 separate gauge inputs cause re-encoding
  - `source/steps/build_helpers/clip_renderer.py:298-335`
  - Render all gauges to single PNG, overlay once

- [ ] **Parallelize splash PNG saves** - Sequential PIL saves
  - `source/steps/splash_helpers/animation_renderer.py:203-205`

## Low Priority

- [ ] **Dynamic YOLO batch sizing** - Auto-scale based on GPU memory
- [ ] **Optimize filter chain order** - Minimize re-encoding passes
- [ ] **Auto-detect hardware capabilities** - Adjust settings for Air vs Pro

## Completed Summary

| Optimization | Expected Speedup | Status |
|--------------|------------------|--------|
| FFmpeg h264_videotoolbox | 5-10x encoding | ✓ Done |
| YOLO batch size 4→8 | 2x detection | ✓ Done |
| Parallel minimap rendering | 4-8x | ✓ Done |
| Parallel elevation rendering | 4-8x | ✓ Done |
