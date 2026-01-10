# source/utils/trophy_overlay.py
"""
Trophy badge overlay for Strava PR clips.
Creates a badge showing segment name, distance, and grade.
"""

from __future__ import annotations
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

from .log import setup_logger

log = setup_logger("utils.trophy_overlay")


def safe_font(size: int, bold: bool = False):
    """Load system font with fallback."""
    try:
        if bold:
            return ImageFont.truetype("/System/Library/Fonts/SFNS.ttf", size)
        return ImageFont.truetype("/System/Library/Fonts/SFNS.ttf", size)
    except Exception:
        try:
            return ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", size)
        except Exception:
            return ImageFont.load_default()


def create_trophy_overlay(
    segment_name: str,
    output_path: Path,
    distance_m: float = 0,
    grade_pct: float = 0,
    width: int = 450,
    height: int = 80,
) -> Path:
    """
    Create Strava-style PR badge overlay.

    Args:
        segment_name: Name of the Strava segment
        output_path: Where to save the PNG
        distance_m: Segment distance in meters
        grade_pct: Average grade percentage
        width: Output image width
        height: Output image height

    Returns:
        Path to rendered PNG
    """
    # Create transparent image
    img = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    # Badge layout: orange left strip with trophy, white text area
    padding = 4
    corner_radius = 8
    trophy_area_width = 50

    # Colors (matching Strava badge style)
    orange_color = (243, 108, 37, 255)  # Strava orange #F36C25
    white_bg = (255, 255, 255, 245)  # Slightly transparent white
    dark_text = (51, 51, 51, 255)  # Dark gray for text
    gray_text = (128, 128, 128, 255)  # Lighter gray for stats

    # Draw main white background with rounded corners
    draw.rounded_rectangle(
        [padding, padding, width - padding, height - padding],
        radius=corner_radius,
        fill=white_bg,
    )

    # Draw orange left strip
    draw.rounded_rectangle(
        [padding, padding, trophy_area_width, height - padding],
        radius=corner_radius,
        fill=orange_color,
    )
    # Square off the right side of orange strip
    draw.rectangle(
        [trophy_area_width - corner_radius, padding, trophy_area_width, height - padding],
        fill=orange_color,
    )

    # Draw trophy icon (simple trophy shape)
    trophy_center_x = (padding + trophy_area_width) // 2
    trophy_center_y = height // 2
    _draw_trophy_icon(draw, trophy_center_x, trophy_center_y, size=28)

    # Fonts
    name_font = safe_font(20, bold=True)
    stats_font = safe_font(14)

    # Text area starts after trophy strip
    text_x = trophy_area_width + 12

    # Truncate segment name if too long
    max_name_width = width - text_x - 16
    segment_display = segment_name or "PR Segment"
    name_bbox = draw.textbbox((0, 0), segment_display, font=name_font)
    name_width = name_bbox[2] - name_bbox[0]

    while name_width > max_name_width and len(segment_display) > 10:
        segment_display = segment_display[:-4] + "..."
        name_bbox = draw.textbbox((0, 0), segment_display, font=name_font)
        name_width = name_bbox[2] - name_bbox[0]

    # Draw segment name (dark text, top line)
    name_y = 16
    draw.text((text_x, name_y), segment_display, fill=dark_text, font=name_font)

    # Build stats line: distance, grade
    stats_parts = []
    if distance_m > 0:
        dist_km = distance_m / 1000
        stats_parts.append(f"{dist_km:.2f} km")

    if grade_pct != 0:
        stats_parts.append(f"{grade_pct:.1f}%")

    if stats_parts:
        stats_line = "  ".join(stats_parts)
        stats_y = name_y + 28
        draw.text((text_x, stats_y), stats_line, fill=gray_text, font=stats_font)

    # Save
    img.save(output_path)
    log.debug(f"[trophy] Created PR badge: {output_path}")
    return output_path


def _draw_trophy_icon(draw: ImageDraw.Draw, cx: int, cy: int, size: int = 24):
    """Draw a simple trophy icon at the given center position."""
    # Trophy cup (simplified shape)
    # Use white color for trophy on orange background
    trophy_color = (255, 255, 255, 255)

    # Cup body (rounded rectangle approximation with polygon)
    cup_width = size * 0.7
    cup_height = size * 0.55
    cup_top = cy - size * 0.35
    cup_bottom = cup_top + cup_height

    # Main cup body
    cup_points = [
        (cx - cup_width/2, cup_top),
        (cx + cup_width/2, cup_top),
        (cx + cup_width/2.5, cup_bottom),
        (cx - cup_width/2.5, cup_bottom),
    ]
    draw.polygon(cup_points, fill=trophy_color)

    # Cup handles (small arcs on sides)
    handle_r = size * 0.15
    # Left handle
    draw.arc(
        [cx - cup_width/2 - handle_r*2, cup_top + size*0.1,
         cx - cup_width/2, cup_top + size*0.35],
        start=90, end=270, fill=trophy_color, width=2
    )
    # Right handle
    draw.arc(
        [cx + cup_width/2, cup_top + size*0.1,
         cx + cup_width/2 + handle_r*2, cup_top + size*0.35],
        start=270, end=90, fill=trophy_color, width=2
    )

    # Base/stem
    stem_width = size * 0.15
    stem_height = size * 0.15
    base_width = size * 0.4
    base_height = size * 0.08

    # Stem
    draw.rectangle(
        [cx - stem_width/2, cup_bottom,
         cx + stem_width/2, cup_bottom + stem_height],
        fill=trophy_color
    )

    # Base
    draw.rectangle(
        [cx - base_width/2, cup_bottom + stem_height,
         cx + base_width/2, cup_bottom + stem_height + base_height],
        fill=trophy_color
    )
