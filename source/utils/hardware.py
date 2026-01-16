# source/utils/hardware.py
"""
Hardware detection utilities for performance optimization.
Detects Apple Silicon, available encoders, and optimal settings.
"""

from __future__ import annotations
import os
import platform
import subprocess
from functools import lru_cache
from typing import Tuple

from .log import setup_logger

log = setup_logger("utils.hardware")


@lru_cache(maxsize=1)
def is_apple_silicon() -> bool:
    """Check if running on Apple Silicon (M1/M2/M3)."""
    return platform.machine() == 'arm64' and platform.system() == 'Darwin'


@lru_cache(maxsize=1)
def get_system_memory_gb() -> int:
    """Get total system memory in GB."""
    if platform.system() != 'Darwin':
        return 8  # Default assumption

    try:
        result = subprocess.run(
            ['sysctl', '-n', 'hw.memsize'],
            capture_output=True, text=True, timeout=5
        )
        return int(result.stdout.strip()) // (1024**3)
    except Exception:
        return 8


@lru_cache(maxsize=1)
def get_cpu_count() -> int:
    """Get number of CPU cores."""
    return os.cpu_count() or 4


@lru_cache(maxsize=1)
def get_available_encoders() -> Tuple[str, ...]:
    """Get list of available FFmpeg video encoders."""
    try:
        result = subprocess.run(
            ['ffmpeg', '-hide_banner', '-encoders'],
            capture_output=True, text=True, timeout=10
        )
        # Parse encoder names from output
        encoders = []
        for line in result.stdout.split('\n'):
            if line.strip().startswith('V'):
                parts = line.split()
                if len(parts) >= 2:
                    encoders.append(parts[1])
        return tuple(encoders)
    except Exception as e:
        log.warning(f"[hw] Could not detect FFmpeg encoders: {e}")
        return ()


@lru_cache(maxsize=1)
def get_optimal_video_codec() -> str:
    """
    Select optimal FFmpeg video codec based on hardware.

    Priority on Apple Silicon:
        1. hevc_videotoolbox (HEVC hardware encoder - best quality/speed)
        2. h264_videotoolbox (H.264 hardware encoder - good compatibility)
        3. libx264 (software fallback)

    On Intel/other:
        1. libx264 (universal software encoder)

    Returns:
        FFmpeg codec name for -c:v parameter
    """
    encoders = get_available_encoders()

    if is_apple_silicon():
        # Prefer H.264 hardware for better compatibility (intermediate clips need to be viewable)
        # HEVC has container/metadata issues that prevent standalone playback
        if 'h264_videotoolbox' in encoders:
            log.info("[hw] Using h264_videotoolbox (Apple Silicon H.264 hardware encoder)")
            return 'h264_videotoolbox'
        if 'hevc_videotoolbox' in encoders:
            log.info("[hw] Using hevc_videotoolbox (Apple Silicon HEVC hardware encoder)")
            return 'hevc_videotoolbox'

    log.info("[hw] Using libx264 (software encoder)")
    return 'libx264'


def get_worker_count(task_type: str = 'general') -> int:
    """
    Get optimal worker count for different task types.

    Args:
        task_type:
            'ffmpeg' - CPU/GPU intensive video encoding
            'io' - I/O bound tasks (file operations, network)
            'cpu' - CPU-bound computation
            'general' - Default for mixed workloads

    Returns:
        Optimal number of parallel workers
    """
    cpu_count = get_cpu_count()

    if task_type == 'ffmpeg':
        # FFmpeg with hardware acceleration is GPU-bound
        # Multiple processes compete for GPU, diminishing returns after ~6
        # But more CPU cores help with filter processing
        if is_apple_silicon():
            # M1: 8 cores, M1 Pro: 10, M1 Max: 10, M2: 8, M2 Pro: 12
            # Use half cores, min 2, max 8 for hardware encoding
            workers = max(2, min(8, cpu_count // 2))
        else:
            # Software encoding is CPU-bound, use more cores
            workers = max(2, min(12, cpu_count // 2))

    elif task_type == 'io':
        # I/O bound tasks can have more concurrent workers
        # Limited by disk/network, not CPU
        workers = max(4, min(16, cpu_count))

    elif task_type == 'cpu':
        # CPU-intensive tasks - use most cores but leave headroom
        workers = max(2, cpu_count - 2)

    else:  # 'general'
        # Default: half of cores, reasonable for mixed workloads
        workers = max(2, min(12, cpu_count // 2))

    return workers


def get_yolo_batch_size() -> int:
    """
    Determine optimal YOLO batch size based on available GPU memory.

    Apple Silicon uses unified memory, so we can be more aggressive
    with batch sizes compared to discrete GPUs.

    Memory guidelines:
        8GB  -> batch 8 (conservative)
        16GB -> batch 16
        32GB -> batch 32
        64GB -> batch 48 (leave room for system)

    Returns:
        Optimal batch size for YOLO inference
    """
    if not is_apple_silicon():
        return 8  # Conservative default for non-Apple systems

    ram_gb = get_system_memory_gb()

    if ram_gb >= 64:
        batch = 48
    elif ram_gb >= 32:
        batch = 32
    elif ram_gb >= 16:
        batch = 16
    else:
        batch = 8

    log.debug(f"[hw] YOLO batch size: {batch} (system RAM: {ram_gb}GB)")
    return batch


def log_system_info():
    """Log system hardware information for diagnostics."""
    log.info(f"[hw] Platform: {platform.system()} {platform.machine()}")
    log.info(f"[hw] Apple Silicon: {is_apple_silicon()}")
    log.info(f"[hw] CPU cores: {get_cpu_count()}")
    log.info(f"[hw] System RAM: {get_system_memory_gb()}GB")
    log.info(f"[hw] Optimal video codec: {get_optimal_video_codec()}")
    log.info(f"[hw] YOLO batch size: {get_yolo_batch_size()}")
