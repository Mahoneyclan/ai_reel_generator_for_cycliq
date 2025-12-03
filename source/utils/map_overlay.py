# source/utils/map_overlay.py

from __future__ import annotations
from typing import Tuple, List, Dict
from io import BytesIO
import logging

import matplotlib
matplotlib.use("Agg", force=True)
import matplotlib.pyplot as plt
from PIL import Image

from shapely.geometry import LineString, Point
import geopandas as gpd
import contextily as ctx

from ..config import DEFAULT_CONFIG as CFG
from .gpx import GpxPoint, GPXIndex

from source.utils.log import setup_logger

log = setup_logger("utils.map_overlay")

# --- Caches ---
_gpx_index_cache: Dict[int, GPXIndex] = {}
_splash_cache: Dict[Tuple[int, Tuple[int, int]], Tuple[Image.Image, Tuple[float, float, float, float]]] = {}

# --- Helpers ---
def _rgba(rgb: Tuple[int, int, int]) -> List[float]:
    return [c / 255.0 for c in rgb] + [1.0]

def _sample_by_time(gpx_points: List[GpxPoint], interval_s: int = 6) -> List[GpxPoint]:
    simplified = []
    last_ts = None
    for pt in gpx_points:
        if last_ts is None or (pt.timestamp_epoch - last_ts) >= interval_s:
            simplified.append(pt)
            last_ts = pt.timestamp_epoch
    return simplified

def _get_gpx_index(gpx_points: List[GpxPoint]) -> GPXIndex:
    key = id(gpx_points)
    if key not in _gpx_index_cache:
        _gpx_index_cache[key] = GPXIndex(gpx_points)
    return _gpx_index_cache[key]

def _render_base_figure(gpx_points: List[GpxPoint], size: Tuple[int, int]) -> Tuple[plt.Figure, plt.Axes, Tuple[float, float, float, float]]:
    sampled = _sample_by_time(gpx_points, interval_s=getattr(CFG, "MAP_SAMPLE_INTERVAL_S", 6))
    coords = [(p.lon, p.lat) for p in sampled]
    if len(coords) < 2:
        fig = plt.figure(figsize=(size[0]/100, size[1]/100), dpi=100)
        ax = fig.add_axes([0, 0, 1, 1]); ax.axis("off")
        return fig, ax, (0.0, 0.0, 0.0, 0.0)

    gdf = gpd.GeoDataFrame(geometry=[LineString(coords)], crs="EPSG:4326").to_crs(epsg=3857)
    x_min, y_min, x_max, y_max = gdf.total_bounds
    pad_pct = getattr(CFG, "MAP_PADDING_PCT", 0.06)
    dx, dy = x_max - x_min, y_max - y_min
    x_min -= dx * pad_pct; x_max += dx * pad_pct
    y_min -= dy * pad_pct; y_max += dy * pad_pct

    fig = plt.figure(figsize=(size[0]/100, size[1]/100), dpi=100)
    ax = fig.add_axes([0, 0, 1, 1]); ax.axis("off")
    ax.set_xlim(x_min, x_max); ax.set_ylim(y_min, y_max)

    try:
        ctx.add_basemap(ax, crs="EPSG:3857", source=ctx.providers.OpenStreetMap.Mapnik)
        ax.set_xlim(x_min, x_max); ax.set_ylim(y_min, y_max)
    except Exception as e:
        log.warning(f"[map_overlay] basemap fallback: {e}")
        ax.set_facecolor((0.95, 0.95, 0.95, 1.0))

    route_color = getattr(CFG, "MAP_ROUTE_COLOR", (0, 255, 0))
    route_width = getattr(CFG, "MAP_ROUTE_WIDTH", 4)
    gdf.plot(ax=ax, color=_rgba(route_color), linewidth=route_width, zorder=5)

    return fig, ax, (x_min, x_max, y_max, y_min)

def _figure_to_image(fig: plt.Figure) -> Image.Image:
    buf = BytesIO()
    fig.savefig(buf, format="png", bbox_inches=None, pad_inches=0, transparent=True)
    buf.seek(0)
    img = Image.open(buf).convert("RGBA")
    plt.close(fig)
    return img

# --- Public API ---
def render_splash_map_with_xy(
    gpx_points: List[GpxPoint],
    size: Tuple[int, int] = (2560, 1440),
    gutters_px: Tuple[int, int, int, int] = (0, 0, 0, 0),
) -> Tuple[Image.Image, Tuple[float, float, float, float]]:
    key = (id(gpx_points), size)
    if key in _splash_cache:
        return _splash_cache[key]

    fig, ax, extent = _render_base_figure(gpx_points, size)
    img = _figure_to_image(fig)
    _splash_cache[key] = (img, extent)
    return img, extent

def render_overlay_minimap(
    gpx_points: List[GpxPoint],
    current_ts: float,
    size: Tuple[int, int] = (512, 512),
) -> Image.Image:
    fig, ax, extent = _render_base_figure(gpx_points, size)
    gpx_index = _get_gpx_index(gpx_points)
    pt = gpx_index.find_nearest(current_ts)
    if pt:
        try:
            pt_merc = gpd.GeoSeries([Point(pt.lon, pt.lat)], crs="EPSG:4326").to_crs(epsg=3857)
            marker_color = getattr(CFG, "MAP_MARKER_COLOR", (255, 255, 0))
            base_radius = getattr(CFG, "MAP_MARKER_RADIUS", 6)
            pt_merc.plot(ax=ax, color=_rgba(marker_color), markersize=base_radius * 10, zorder=10)
        except Exception as e:
            log.warning(f"[map_overlay] marker plot failed: {e}")
    return _figure_to_image(fig)
