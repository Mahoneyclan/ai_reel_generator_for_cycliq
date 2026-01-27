# source/utils/elevation_plot.py
"""
Elevation profile plot overlay.
Shows full ride elevation with current position marker.
Uses distance-based x-axis for consistent scale regardless of stops/pauses.
"""

from __future__ import annotations
from pathlib import Path
from typing import List, Tuple
import csv
import math

import matplotlib
matplotlib.use("Agg", force=True)
import matplotlib.pyplot as plt
from PIL import Image
from io import BytesIO

from .log import setup_logger

log = setup_logger("utils.elevation_plot")


def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """
    Calculate distance between two GPS points using Haversine formula.

    Returns:
        Distance in kilometers
    """
    R = 6371.0  # Earth radius in km

    lat1_rad = math.radians(lat1)
    lat2_rad = math.radians(lat2)
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)

    a = math.sin(dlat / 2) ** 2 + math.cos(lat1_rad) * math.cos(lat2_rad) * math.sin(dlon / 2) ** 2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))

    return R * c


def load_elevation_data(flatten_csv: Path) -> List[Tuple[float, float, float]]:
    """
    Load elevation data from flatten.csv with cumulative distance.

    Returns:
        List of (epoch, distance_km, elevation) tuples sorted by epoch
    """
    data = []
    try:
        with flatten_csv.open() as f:
            rows = list(csv.DictReader(f))

        if not rows:
            return data

        cumulative_distance = 0.0
        prev_lat = None
        prev_lon = None

        for row in rows:
            epoch = float(row.get("gpx_epoch", 0) or 0)
            elev = float(row.get("elevation", 0) or 0)
            lat = float(row.get("lat", 0) or 0)
            lon = float(row.get("lon", 0) or 0)

            if epoch <= 0 or lat == 0 or lon == 0:
                continue

            # Calculate distance from previous point
            if prev_lat is not None and prev_lon is not None:
                segment_dist = _haversine_km(prev_lat, prev_lon, lat, lon)
                # Filter out GPS noise (> 500m jump in 1 second is unrealistic)
                if segment_dist < 0.5:
                    cumulative_distance += segment_dist

            prev_lat = lat
            prev_lon = lon
            data.append((epoch, cumulative_distance, elev))

    except Exception as e:
        log.warning(f"Failed to load elevation data: {e}")

    # Sort by epoch (should already be sorted)
    data.sort(key=lambda x: x[0])
    return data


def render_elevation_plot(
    elevation_data: List[Tuple[float, float, float]],
    current_epoch: float,
    output_path: Path,
    width: int = 460,
    height: int = 120,
) -> Path:
    """
    Render elevation profile plot with current position marker.
    Uses distance-based x-axis for consistent scale regardless of stops/pauses.

    Args:
        elevation_data: List of (epoch, distance_km, elevation) tuples
        current_epoch: Current timestamp for position marker
        output_path: Where to save the PNG
        width: Output image width
        height: Output image height

    Returns:
        Path to rendered PNG
    """
    if not elevation_data:
        # Return transparent placeholder
        img = Image.new("RGBA", (width, height), (0, 0, 0, 0))
        img.save(output_path)
        return output_path

    # Extract distance and elevation (x-axis is now distance, not time)
    distances = [e[1] for e in elevation_data]
    elevs = [e[2] for e in elevation_data]

    # Create figure with transparent background
    dpi = 100
    fig, ax = plt.subplots(figsize=(width / dpi, height / dpi), dpi=dpi)
    fig.patch.set_alpha(0.0)

    # Semi-transparent dark background for the plot area
    ax.set_facecolor((0, 0, 0, 0.5))

    # Plot elevation profile - filled area (x-axis = distance in km)
    ax.fill_between(distances, elevs, alpha=0.6, color='#4CAF50', linewidth=0)
    ax.plot(distances, elevs, color='#2E7D32', linewidth=1.5)

    # Find current position by mapping epoch to distance
    current_dist = None
    current_elev = None
    for i, (ep, dist, el) in enumerate(elevation_data):
        if ep >= current_epoch:
            if i > 0 and ep > current_epoch:
                # Interpolate between previous and current point
                prev_ep, prev_dist, prev_el = elevation_data[i - 1]
                if ep != prev_ep:
                    ratio = (current_epoch - prev_ep) / (ep - prev_ep)
                    current_dist = prev_dist + ratio * (dist - prev_dist)
                    current_elev = prev_el + ratio * (el - prev_el)
                else:
                    current_dist = dist
                    current_elev = el
            else:
                current_dist = dist
                current_elev = el
            break

    # Fallback to last point if beyond data
    if current_dist is None and elevation_data:
        current_dist = elevation_data[-1][1]
        current_elev = elevation_data[-1][2]

    # Draw current position marker (yellow dot)
    if current_dist is not None and current_elev is not None:
        ax.scatter(
            [current_dist], [current_elev],
            color='#FFD700', s=80, zorder=10,
            edgecolors='black', linewidths=1
        )

    # Style the plot
    ax.set_xlim(distances[0], distances[-1])

    # Add some padding to y-axis
    elev_range = max(elevs) - min(elevs) if max(elevs) != min(elevs) else 100
    ax.set_ylim(min(elevs) - elev_range * 0.1, max(elevs) + elev_range * 0.15)

    ax.axis('off')

    # Add elevation labels (min/max) on the left edge
    ax.text(
        0.02, 0.92, f"{int(max(elevs))}m",
        transform=ax.transAxes, fontsize=8, color='white',
        va='top', fontweight='bold'
    )
    ax.text(
        0.02, 0.08, f"{int(min(elevs))}m",
        transform=ax.transAxes, fontsize=8, color='white',
        va='bottom', fontweight='bold'
    )

    # Add total distance label on the right edge
    total_dist = distances[-1] if distances else 0
    ax.text(
        0.98, 0.08, f"{total_dist:.1f}km",
        transform=ax.transAxes, fontsize=8, color='white',
        va='bottom', ha='right', fontweight='bold'
    )

    # Tight layout
    plt.subplots_adjust(left=0, right=1, top=1, bottom=0)

    # Save to buffer
    buf = BytesIO()
    fig.savefig(
        buf, format='png', bbox_inches='tight', pad_inches=0.02,
        transparent=True, dpi=dpi
    )
    buf.seek(0)
    img = Image.open(buf).convert("RGBA")
    plt.close(fig)

    # Resize to exact dimensions if needed
    if img.size != (width, height):
        img = img.resize((width, height), Image.LANCZOS)

    img.save(output_path)
    return output_path
