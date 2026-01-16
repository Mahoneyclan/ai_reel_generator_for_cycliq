# Optimization Plan

This document outlines performance optimizations for both Mac Mini (M1) and MacBook deployments.

## Current State

| Component | Current Setting | Notes |
|-----------|----------------|-------|
| Video codec | `libx264` (software) | Hardware encoding available on M1 |
| FFmpeg hwaccel | `videotoolbox` | Hardware decoding enabled |
| Worker cap | `8` maximum | Limits parallelism on high-core machines |
| YOLO batch | `8` fixed | Should be adaptive to GPU memory |
| YOLO model | `yolo11s.pt` | Good balance of speed/accuracy |
| Pre-rendering | Parallel (minimaps, gauges, elevation) | Already optimized |

## Priority 1: FFmpeg Codec Optimization

**Impact: ~40-60% faster clip encoding**

### Current (Software H.264)
```python
VIDEO_CODEC: str = 'libx264'
```

### Proposed (Hardware HEVC)
Use Apple's VideoToolbox hardware encoder for M1 chips.

**Changes to `source/config.py`:**
```python
# Smart codec selection based on hardware
PREFERRED_CODEC: str = field(default_factory=lambda: _get_config_value('PREFERRED_CODEC', 'auto'))
# Options: 'auto', 'hevc_videotoolbox', 'h264_videotoolbox', 'libx264', 'libx265'
```

**New helper in `source/utils/hardware.py`:**
```python
def get_optimal_codec() -> str:
    """
    Select optimal FFmpeg codec based on hardware capabilities.

    Returns:
        Codec name for FFmpeg -c:v parameter
    """
    import platform
    import subprocess

    # Check for Apple Silicon
    if platform.machine() == 'arm64' and platform.system() == 'Darwin':
        # Verify VideoToolbox availability
        try:
            result = subprocess.run(
                ['ffmpeg', '-hide_banner', '-encoders'],
                capture_output=True, text=True
            )
            if 'hevc_videotoolbox' in result.stdout:
                return 'hevc_videotoolbox'
            if 'h264_videotoolbox' in result.stdout:
                return 'h264_videotoolbox'
        except Exception:
            pass

    return 'libx264'  # Fallback
```

**Compatibility:**
- Mac Mini M1: Uses `hevc_videotoolbox` (fastest)
- MacBook (Intel): Falls back to `libx264` (works everywhere)

---

## Priority 2: Dynamic Worker Scaling

**Impact: Better CPU utilization on high-core machines**

### Current
```python
# source/steps/build.py:192
workers = max(1, min(8, cpu_count // 2))
```

### Proposed
Scale workers based on actual core count and task type.

**New helper in `source/utils/hardware.py`:**
```python
def get_worker_count(task_type: str = 'general') -> int:
    """
    Get optimal worker count for different task types.

    Args:
        task_type: 'ffmpeg', 'yolo', 'io', 'general'

    Returns:
        Optimal worker count
    """
    import os

    cpu_count = os.cpu_count() or 4

    # Task-specific scaling
    if task_type == 'ffmpeg':
        # FFmpeg is CPU/GPU intensive, limit parallel processes
        # M1 Pro/Max can handle more, base M1 should be conservative
        return max(2, min(12, cpu_count // 2))

    elif task_type == 'yolo':
        # GPU-bound, limited benefit from more workers
        # MPS handles batching internally
        return 1  # Process batches serially

    elif task_type == 'io':
        # I/O bound tasks (minimap rendering, file operations)
        # Can be more aggressive with workers
        return max(4, min(16, cpu_count))

    else:
        # General tasks
        return max(2, min(12, cpu_count // 2))
```

**Files to update:**
- `source/steps/build.py` - `_get_max_workers()`
- `source/steps/build_helpers/minimap_prerenderer.py`
- `source/steps/build_helpers/elevation_prerenderer.py`
- `source/steps/build_helpers/gauge_prerenderer.py`

---

## Priority 3: Adaptive YOLO Batch Size

**Impact: ~20-30% faster detection on GPUs with more memory**

### Current
```python
YOLO_BATCH_SIZE: int = 8  # Fixed
```

### Proposed
Auto-detect optimal batch size based on available GPU memory.

**New helper in `source/utils/hardware.py`:**
```python
def get_yolo_batch_size() -> int:
    """
    Determine optimal YOLO batch size based on available GPU memory.

    M1 Unified Memory:
        8GB  -> batch 4-8
        16GB -> batch 16
        32GB -> batch 32
        64GB -> batch 64
    """
    import platform

    if platform.system() != 'Darwin':
        return 8  # Default for non-Mac

    try:
        import subprocess
        result = subprocess.run(
            ['sysctl', '-n', 'hw.memsize'],
            capture_output=True, text=True
        )
        total_ram_gb = int(result.stdout.strip()) // (1024**3)

        # Conservative estimates for unified memory
        if total_ram_gb >= 64:
            return 64
        elif total_ram_gb >= 32:
            return 32
        elif total_ram_gb >= 16:
            return 16
        else:
            return 8
    except Exception:
        return 8
```

**Update `source/config.py`:**
```python
YOLO_BATCH_SIZE: int = field(default_factory=lambda: _get_config_value(
    'YOLO_BATCH_SIZE',
    get_yolo_batch_size()  # Dynamic default
))
```

---

## Priority 4: Pre-rendered Asset Cache

**Impact: Skip re-rendering unchanged assets on re-builds**

### Concept
Cache pre-rendered minimaps, gauges, and elevation plots with content hashes.
Skip regeneration if inputs haven't changed.

**Cache structure:**
```
{project}/working/cache/
    minimaps/
        minimap_0001_{hash}.png
    gauges/
        gauge_0001_{hash}.png
    elevation/
        elev_0001_{hash}.png
    cache_manifest.json
```

**Manifest format:**
```json
{
    "minimap_0001": {
        "hash": "abc123",
        "inputs": {"lat": 12.34, "lon": 56.78, "epoch": 1234567890}
    }
}
```

**Implementation:**
1. Before pre-rendering, check if cached asset exists with matching input hash
2. If match, skip rendering and use cached file
3. If no match, render and update cache

This is a medium-complexity feature that requires changes to all pre-renderer classes.

---

## Priority 5: Memory-Efficient CSV Streaming

**Impact: Handle larger projects without memory issues**

### Current
```python
with extract_csv.open() as f:
    rows = list(csv.DictReader(f))  # Loads entire file
```

### Proposed
Stream CSV rows for very large projects.

**For enrichment (needs full dataset for scoring):**
Keep current approach but add memory warning for large files.

**For build step (can process in chunks):**
```python
def _iter_csv_rows(csv_path: Path, chunk_size: int = 1000):
    """Iterate CSV rows in memory-efficient chunks."""
    with csv_path.open() as f:
        reader = csv.DictReader(f)
        chunk = []
        for row in reader:
            chunk.append(row)
            if len(chunk) >= chunk_size:
                yield chunk
                chunk = []
        if chunk:
            yield chunk
```

---

## Implementation Order

### Phase 1: Quick Wins (Immediate)
1. **FFmpeg codec optimization** - Single file change, major speedup
2. **Dynamic worker scaling** - Remove arbitrary 8-worker cap

### Phase 2: Detection Optimization
3. **Adaptive YOLO batch size** - Better GPU utilization

### Phase 3: Caching (Optional)
4. **Asset cache** - Skip redundant pre-rendering

### Phase 4: Large Project Support (Optional)
5. **CSV streaming** - Handle projects with 10,000+ frames

---

## Testing Matrix

| Machine | CPU | RAM | Expected Gains |
|---------|-----|-----|----------------|
| Mac Mini M1 | 8-core | 16GB | 40-60% faster build |
| MacBook Pro M1 Pro | 10-core | 16-32GB | 50-70% faster build |
| MacBook Intel | i7/i9 | 16GB | 10-20% faster (worker scaling) |

---

## Benchmark Commands

Run before/after optimization to measure impact:

```bash
# Time the full build step
time python -c "from source.steps import build; build.run()"

# Time just clip rendering (excludes pre-rendering)
time python -c "
from source.steps.build import _load_recommended_moments
from source.steps.build_helpers import ClipRenderer
moments = _load_recommended_moments()[:5]  # First 5 clips
# ... render test
"
```

---

## Config Additions Summary

New settings for `source/config.py`:

```python
# Hardware optimization
PREFERRED_CODEC: str = field(default_factory=lambda: _get_config_value('PREFERRED_CODEC', 'auto'))
ENABLE_ASSET_CACHE: bool = field(default_factory=lambda: _get_config_value('ENABLE_ASSET_CACHE', True))
MAX_WORKERS_OVERRIDE: int = field(default_factory=lambda: _get_config_value('MAX_WORKERS_OVERRIDE', 0))  # 0 = auto
```

---

## Rollback Plan

All optimizations are backward-compatible:
- Codec selection falls back to `libx264` if hardware unavailable
- Worker scaling uses same range as before (just smarter selection)
- Batch size has safe defaults
- Cache can be disabled or cleared

No data format changes. Existing projects work without modification.
