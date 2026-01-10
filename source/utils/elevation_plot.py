# source/utils/elevation_plot.py
"""
Elevation profile plot overlay.
Shows full ride elevation with current position marker.
"""

from __future__ import annotations
from pathlib import Path
from typing import List, Tuple
import csv

import matplotlib
matplotlib.use("Agg", force=True)
import matplotlib.pyplot as plt
from PIL import Image
from io import BytesIO

from .log import setup_logger

log = setup_logger("utils.elevation_plot")


def load_elevation_data(flatten_csv: Path) -> List[Tuple[float, float]]:
    """
    Load elevation data from flatten.csv.

    Returns:
        List of (epoch, elevation) tuples sorted by epoch
    """
    data = []
    try:
        with flatten_csv.open() as f:
            for row in csv.DictReader(f):
                epoch = float(row.get("gpx_epoch", 0) or 0)
                elev = float(row.get("elevation", 0) or 0)
                if epoch > 0:
                    data.append((epoch, elev))
    except Exception as e:
        log.warning(f"Failed to load elevation data: {e}")

    # Sort by epoch
    data.sort(key=lambda x: x[0])
    return data


def render_elevation_plot(
    elevation_data: List[Tuple[float, float]],
    current_epoch: float,
    output_path: Path,
    width: int = 460,
    height: int = 120,
) -> Path:
    """
    Render elevation profile plot with current position marker.

    Args:
        elevation_data: List of (epoch, elevation) tuples
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

    epochs = [e[0] for e in elevation_data]
    elevs = [e[1] for e in elevation_data]

    # Create figure with transparent background
    dpi = 100
    fig, ax = plt.subplots(figsize=(width / dpi, height / dpi), dpi=dpi)
    fig.patch.set_alpha(0.0)

    # Semi-transparent dark background for the plot area
    ax.set_facecolor((0, 0, 0, 0.5))

    # Plot elevation profile - filled area
    ax.fill_between(epochs, elevs, alpha=0.6, color='#4CAF50', linewidth=0)
    ax.plot(epochs, elevs, color='#2E7D32', linewidth=1.5)

    # Find current elevation by interpolation
    current_elev = None
    for i, (ep, el) in enumerate(elevation_data):
        if ep >= current_epoch:
            if i > 0 and ep > current_epoch:
                # Interpolate between previous and current point
                prev_ep, prev_el = elevation_data[i - 1]
                if ep != prev_ep:
                    ratio = (current_epoch - prev_ep) / (ep - prev_ep)
                    current_elev = prev_el + ratio * (el - prev_el)
                else:
                    current_elev = el
            else:
                current_elev = el
            break

    # Fallback to last point if beyond data
    if current_elev is None and elevation_data:
        current_elev = elevation_data[-1][1]
        current_epoch = elevation_data[-1][0]

    # Draw current position marker (yellow dot)
    if current_elev is not None:
        ax.scatter(
            [current_epoch], [current_elev],
            color='#FFD700', s=80, zorder=10,
            edgecolors='black', linewidths=1
        )

    # Style the plot
    ax.set_xlim(epochs[0], epochs[-1])

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
