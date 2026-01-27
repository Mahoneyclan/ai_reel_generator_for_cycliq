# source/utils/map_overlay.py
"""
Map overlay rendering with managed caching.

Provides GPX route visualization with marker overlay.
Implements LRU cache with size limits to prevent memory bloat.
"""

from __future__ import annotations
from typing import Tuple, List, Optional
from io import BytesIO
from collections import OrderedDict
import hashlib

import matplotlib
matplotlib.use("Agg", force=True)
import matplotlib.pyplot as plt
from PIL import Image

from shapely.geometry import LineString, Point
import geopandas as gpd
import contextily as ctx

from ..config import DEFAULT_CONFIG as CFG
from .gpx import GpxPoint, GPXIndex
from .log import setup_logger

log = setup_logger("utils.map_overlay")

# Cache configuration
MAX_GPX_INDEX_CACHE_SIZE = 10
MAX_SPLASH_CACHE_SIZE = 5

# Managed caches using OrderedDict for LRU behavior
_gpx_index_cache: OrderedDict[str, GPXIndex] = OrderedDict()
_splash_cache: OrderedDict[str, Tuple[Image.Image, Tuple[float, float, float, float]]] = OrderedDict()


def _compute_gpx_hash(gpx_points: List[GpxPoint]) -> str:
    """
    Compute stable hash for GPX points list.
    
    Uses first/last point coordinates and total count as fingerprint.
    More reliable than id() which changes across invocations.
    
    Args:
        gpx_points: List of GPS trackpoints
    
    Returns:
        Hash string for cache key
    """
    if not gpx_points:
        return "empty"
    
    # Create fingerprint from first/last coords, count, and hash of all coords
    first = gpx_points[0]
    last = gpx_points[-1]
    all_coords = "".join([f"{p.lat:.6f}{p.lon:.6f}" for p in gpx_points])
    fingerprint = f"{first.lat:.6f},{first.lon:.6f},{last.lat:.6f},{last.lon:.6f},{len(gpx_points)},{hash(all_coords)}"
    
    return hashlib.md5(fingerprint.encode()).hexdigest()[:16]


def _rgba(rgb: Tuple[int, int, int]) -> List[float]:
    """Convert RGB tuple to RGBA float list for matplotlib."""
    return [c / 255.0 for c in rgb] + [1.0]


def _sample_by_time(gpx_points: List[GpxPoint], interval_s: int = 6) -> List[GpxPoint]:
    """
    Downsample GPX points by time interval for rendering performance.
    
    Args:
        gpx_points: Full GPS trackpoints list
        interval_s: Minimum seconds between sampled points
    
    Returns:
        Downsampled points list
    """
    simplified = []
    last_ts = None
    
    for pt in gpx_points:
        if last_ts is None or (pt.timestamp_epoch - last_ts) >= interval_s:
            simplified.append(pt)
            last_ts = pt.timestamp_epoch
    
    return simplified


def _get_gpx_index(gpx_points: List[GpxPoint]) -> GPXIndex:
    """
    Get or create GPXIndex with LRU caching.
    
    Args:
        gpx_points: GPS trackpoints to index
    
    Returns:
        GPXIndex for fast timestamp lookups
    """
    cache_key = _compute_gpx_hash(gpx_points)
    
    # Check cache
    if cache_key in _gpx_index_cache:
        # Move to end (most recently used)
        _gpx_index_cache.move_to_end(cache_key)
        return _gpx_index_cache[cache_key]
    
    # Create new index
    gpx_index = GPXIndex(gpx_points)
    _gpx_index_cache[cache_key] = gpx_index
    
    # Enforce size limit (LRU eviction)
    while len(_gpx_index_cache) > MAX_GPX_INDEX_CACHE_SIZE:
        oldest_key = next(iter(_gpx_index_cache))
        evicted = _gpx_index_cache.pop(oldest_key)
        log.debug(f"Evicted GPX index from cache (size={len(evicted)})")
    
    return gpx_index


def _render_base_figure(
    gpx_points: List[GpxPoint],
    size: Tuple[int, int],
    is_splash: bool = False,
) -> Tuple[plt.Figure, plt.Axes, Tuple[float, float, float, float]] | Tuple[None, None, None]:
    """
    Render base map figure with route overlay.

    Args:
        gpx_points: GPS trackpoints to render
        size: Target output size (width, height) - used to calculate render resolution
        is_splash: True for splash map (uses thicker route width)

    Returns:
        Tuple of (figure, axes, extent) or (None, None, None) on failure. Extent is (x_min, x_max, y_max, y_min).
    """
    # Downsample for performance
    sampled = _sample_by_time(gpx_points, interval_s=getattr(CFG, "MAP_SAMPLE_INTERVAL_S", 6))
    coords = [(p.lon, p.lat) for p in sampled]

    if len(coords) < 2:
        # Fallback for insufficient data
        log.warning("Cannot render map, less than 2 GPX points.")
        return None, None, None

    # Create GeoDataFrame and project to Web Mercator
    gdf = gpd.GeoDataFrame(
        geometry=[LineString(coords)],
        crs="EPSG:4326"
    ).to_crs(epsg=3857)

    # Calculate bounds with padding
    x_min, y_min, x_max, y_max = gdf.total_bounds
    pad_pct = getattr(CFG, "MAP_PADDING_PCT", 0.06)
    dx, dy = x_max - x_min, y_max - y_min
    x_min -= dx * pad_pct
    x_max += dx * pad_pct
    y_min -= dy * pad_pct
    y_max += dy * pad_pct

    # Calculate figure size based on ROUTE aspect ratio, not target
    # This ensures bbox_inches='tight' won't crop away target dimensions
    route_width = x_max - x_min
    route_height = y_max - y_min
    route_aspect = route_width / route_height if route_height > 0 else 1.0

    # Render at high resolution (2x target) for quality, then scale in _figure_to_image
    base_dim = max(size[0], size[1]) * 2
    if route_aspect >= 1.0:
        # Wide route: width is limiting
        fig_w = base_dim
        fig_h = base_dim / route_aspect
    else:
        # Tall route: height is limiting
        fig_h = base_dim
        fig_w = base_dim * route_aspect

    # Create figure matching route aspect ratio
    fig = plt.figure(figsize=(fig_w/100, fig_h/100), dpi=100)
    ax = fig.add_axes([0, 0, 1, 1])
    ax.axis("off")
    ax.set_xlim(x_min, x_max)
    ax.set_ylim(y_min, y_max)

    # Check if transparent mode is enabled (no basemap, semi-transparent background)
    use_transparent = getattr(CFG, "MAP_TRANSPARENT_MODE", True)

    if use_transparent:
        # Semi-transparent dark background like gauges/elevation plot
        fig.patch.set_alpha(0.0)
        ax.set_facecolor((0, 0, 0, 0.5))
    else:
        # Add basemap tiles
        try:
            # Default to OpenStreetMap if not specified in config
            basemap_source = getattr(ctx.providers, CFG.MAP_BASEMAP_PROVIDER, ctx.providers.OpenStreetMap.Mapnik)
            ctx.add_basemap(
                ax,
                crs="EPSG:3857",
                source=basemap_source
            )
        except Exception as e:
            log.warning(f"Basemap load failed, using fallback: {e}")
            ax.set_facecolor((0.95, 0.95, 0.95, 1.0))

    # Reapply limits and aspect after basemap
    ax.set_xlim(x_min, x_max)
    ax.set_ylim(y_min, y_max)
    ax.set_aspect('equal')  # Preserve geographic proportions

    # Draw route
    route_color = getattr(CFG, "MAP_ROUTE_COLOR", (0, 255, 0))
    if is_splash:
        route_line_width = getattr(CFG, "MAP_SPLASH_ROUTE_WIDTH", 24)
    else:
        route_line_width = getattr(CFG, "MAP_ROUTE_WIDTH", 12)
    gdf.plot(
        ax=ax,
        color=_rgba(route_color),
        linewidth=route_line_width,
        zorder=5
    )

    return fig, ax, (x_min, x_max, y_max, y_min)


def _figure_to_image(fig: plt.Figure, target_size: Tuple[int, int] = None) -> Image.Image:
    """
    Convert matplotlib figure to PIL Image.

    Args:
        fig: Matplotlib figure to convert
        target_size: Optional (width, height) to resize output to exact dimensions

    Returns:
        PIL Image in RGBA mode at exact target_size if specified
    """
    buf = BytesIO()
    # Use tight bbox to crop to actual map content
    fig.savefig(
        buf,
        format="png",
        bbox_inches='tight',
        pad_inches=0.02,  # Small padding around map content
        transparent=False,
        facecolor=(0.95, 0.95, 0.95)  # Light gray background (matches map tiles)
    )
    buf.seek(0)
    img = Image.open(buf).convert("RGBA")
    plt.close(fig)

    # Fit within target bounds preserving aspect ratio
    # Result: width <= target_w, height <= target_h, no padding
    if target_size:
        target_w, target_h = target_size
        img_w, img_h = img.size

        # Calculate scale to fit within bounds
        scale = min(target_w / img_w, target_h / img_h)
        new_w = int(img_w * scale)
        new_h = int(img_h * scale)

        # Resize preserving aspect ratio
        img = img.resize((new_w, new_h), Image.LANCZOS)

    return img


def render_splash_map_with_xy(
    gpx_points: List[GpxPoint],
    size: Tuple[int, int] = (2560, 1440),
) -> Tuple[Image.Image, Tuple[float, float, float, float]]:
    """
    Render full-route splash map with coordinate extent.
    
    Cached for performance - same GPX + size returns cached result.
    
    Args:
        gpx_points: GPS trackpoints to render
        size: Output size (width, height) in pixels
    
    Returns:
        Tuple of (image, extent) where extent is (x_min, x_max, y_max, y_min)
    """
    # Generate cache key
    gpx_hash = _compute_gpx_hash(gpx_points)
    cache_key = f"{gpx_hash}_{size[0]}x{size[1]}"
    
    # Check cache
    if cache_key in _splash_cache:
        _splash_cache.move_to_end(cache_key)
        return _splash_cache[cache_key]
    
    # Render new map - scale to fill target area while preserving aspect ratio
    fig, ax, extent = _render_base_figure(gpx_points, size, is_splash=True)
    if fig is None:
        # Handle rendering failure from _render_base_figure
        fallback_img = Image.new("RGBA", size, (0, 0, 0, 0))
        return fallback_img, (0, 0, 0, 0)
    img = _figure_to_image(fig, target_size=size)
    
    # Cache result
    _splash_cache[cache_key] = (img, extent)
    
    # Enforce cache size limit
    while len(_splash_cache) > MAX_SPLASH_CACHE_SIZE:
        oldest_key = next(iter(_splash_cache))
        evicted_img, _ = _splash_cache.pop(oldest_key)
        log.debug(f"Evicted splash map from cache (size={evicted_img.size})")
    
    return img, extent


def render_overlay_minimap(
    gpx_points: List[GpxPoint],
    current_ts: float,
    size: Tuple[int, int] = (576, 576),
) -> Image.Image:
    """
    Render minimap with current position marker.
    
    Not cached due to constantly changing current_ts parameter.
    
    Args:
        gpx_points: GPS trackpoints for route
        current_ts: Current timestamp epoch for marker position
        size: Output size (width, height) in pixels
    
    Returns:
        PIL Image with route and position marker
    """
    # Render base map
    fig, ax, extent = _render_base_figure(gpx_points, size)
    if fig is None:
        # Handle rendering failure by returning a blank image
        log.warning("Base figure rendering failed for minimap, returning blank image.")
        return Image.new("RGBA", size, (0, 0, 0, 0))
    
    # Add current position marker
    gpx_index = _get_gpx_index(gpx_points)
    current_point = gpx_index.find_nearest(current_ts)
    
    if current_point:
        try:
            # Project marker to Web Mercator
            pt_merc = gpd.GeoSeries(
                [Point(current_point.lon, current_point.lat)], 
                crs="EPSG:4326"
            ).to_crs(epsg=3857)
            
            # Draw marker
            marker_color = getattr(CFG, "MAP_MARKER_COLOR", (255, 255, 0))
            base_radius = getattr(CFG, "MAP_MARKER_RADIUS", 6)
            
            pt_merc.plot(
                ax=ax, 
                color=_rgba(marker_color), 
                markersize=base_radius * 10, 
                zorder=10
            )
        except Exception as e:
            log.warning(f"Marker plot failed: {e}")

    # Ensure exact output size for consistent overlay positioning
    return _figure_to_image(fig, target_size=size)


def clear_map_caches() -> None:
    """
    Clear all map rendering caches.
    
    Call this when switching projects or to free memory.
    """
    global _gpx_index_cache, _splash_cache
    
    gpx_count = len(_gpx_index_cache)
    splash_count = len(_splash_cache)
    
    _gpx_index_cache.clear()
    _splash_cache.clear()
    
    if gpx_count > 0 or splash_count > 0:
        log.info(f"Cleared map caches (GPX: {gpx_count}, Splash: {splash_count})")


def get_cache_stats() -> dict:
    """
    Get current cache statistics.
    
    Returns:
        Dict with cache sizes and limits
    """
    return {
        "gpx_index_count": len(_gpx_index_cache),
        "gpx_index_limit": MAX_GPX_INDEX_CACHE_SIZE,
        "splash_count": len(_splash_cache),
        "splash_limit": MAX_SPLASH_CACHE_SIZE,
    }