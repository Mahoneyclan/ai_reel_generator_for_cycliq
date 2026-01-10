# source/utils/draw_gauge.py
"""
Gauge drawing primitives for circular gauges.
Creates speed, cadence, heart rate, elevation, and gradient gauges.
"""

from __future__ import annotations
from PIL import Image, ImageDraw, ImageFont
import math

def safe_font(size: int):
    """Load system font with fallback."""
    try:
        return ImageFont.truetype("/System/Library/Fonts/SFNS.ttf", size)
    except Exception:
        return ImageFont.load_default()


def _scale_font_size(base_size: int, gauge_size: int, reference_size: int) -> int:
    """Scale font size proportionally to gauge size."""
    return max(8, int(base_size * gauge_size / reference_size))

def _polar(cx, cy, r, ang_deg):
    """Convert polar coordinates to cartesian."""
    a = math.radians(ang_deg)
    return int(cx + r * math.cos(a)), int(cy + r * math.sin(a))

def _draw_dial(draw, cx, cy, r_outer, start_deg, end_deg,
               n_ticks, red_frac=0.8, two_sided: bool = False):
    """Draw gauge tick marks."""
    r_ticks = r_outer - 12
    for i in range(n_ticks + 1):
        frac = i / n_ticks
        ang = start_deg + (end_deg - start_deg) * frac
        if two_sided:
            color = "red" if (frac < (1 - red_frac) or frac > red_frac) else "black"
        else:
            color = "red" if frac > red_frac else "black"
        x1, y1 = _polar(cx, cy, r_ticks, ang)
        x2, y2 = _polar(cx, cy, r_ticks - 10, ang)
        draw.line([(x1, y1), (x2, y2)], fill=color, width=2)

def _draw_needle(draw, cx, cy, r_outer, ang_val):
    """Draw gauge needle."""
    r_needle = r_outer - 18
    nx, ny = _polar(cx, cy, r_needle, ang_val)
    draw.line([(cx, cy), (nx, ny)], fill="black", width=5)
    draw.ellipse((cx - 6, cy - 6, cx + 6, cy + 6), fill="black")

def _draw_small_gauge(img, rect, value: float,
                      min_val: float, max_val: float,
                      title: str, unit: str,
                      start_deg: int, end_deg: int,
                      two_sided: bool = False,
                      side: str = "center"):
    """Draw a small circular gauge with semi-transparent background."""
    x, y, w, h = rect
    cx, cy = x + w // 2, y + h // 2
    r_outer = min(w, h) // 2 - 6
    draw = ImageDraw.Draw(img)

    # Semi-transparent white background (RGBA) - alpha 160 = ~63% opaque
    draw.ellipse((x + 4, y + 4, x + w - 4, y + h - 4),
                 fill=(255, 255, 255, 160), outline="black", width=2)

    frac_val = (value - min_val) / (max_val - min_val if max_val != min_val else 1.0)
    frac_val = max(0.0, min(frac_val, 1.0))
    ang_val = start_deg + (end_deg - start_deg) * frac_val

    _draw_dial(draw, cx, cy, r_outer, start_deg, end_deg,
               20, red_frac=0.9, two_sided=two_sided)
    _draw_needle(draw, cx, cy, r_outer, ang_val)

    # Fonts - scaled based on gauge size (reference size 120px)
    gauge_size = min(w, h)
    title_font = safe_font(_scale_font_size(9, gauge_size, 120))
    val_font = safe_font(_scale_font_size(18, gauge_size, 120))
    unit_font = safe_font(_scale_font_size(11, gauge_size, 120))

    # Title centered near top - scaled offset
    title_offset = int(8 * gauge_size / 120)
    tw = draw.textlength(title, font=title_font)
    draw.text((cx - tw // 2, cy + title_offset), title, fill="black", font=title_font)

    # Value + unit placement
    val_txt = f"{int(round(value))}"
    val_w = draw.textlength(val_txt, font=val_font)

    unit_txt = unit
    unit_w = draw.textlength(unit_txt, font=unit_font)

    offset_10 = int(10 * gauge_size / 120)
    if side == "left":
        vx = cx - r_outer + offset_10
    elif side == "right":
        vx = cx + r_outer - val_w - offset_10
    else:  # center
        vx = cx - val_w // 2

    vy = cy - int(30 * gauge_size / 120)  # vertical anchor at hub height, scaled
    unit_gap = int(20 * gauge_size / 120)
    draw.text((vx, vy), val_txt, fill="black", font=val_font)
    draw.text((vx + (val_w - unit_w)//2, vy + unit_gap), unit_txt, fill="black", font=unit_font)

# --- Gauge types ---

def draw_speed_gauge(img, rect, value: float, max_val: float):
    """Draw large speed gauge (bottom horizontal arc) with semi-transparent background."""
    x, y, w, h = rect
    cx, cy = x + w // 2, y + h // 2
    r_outer = min(w, h) // 2 - 6
    gauge_size = min(w, h)
    draw = ImageDraw.Draw(img)

    # Semi-transparent white background (RGBA) - alpha 160 = ~63% opaque
    draw.ellipse((x + 4, y + 4, x + w - 4, y + h - 4),
                 fill=(255, 255, 255, 160), outline="black", width=3)

    # Horizontal bottom arc (speedometer style), left → right
    start_deg, end_deg = 180, 360
    _draw_dial(draw, cx, cy, r_outer, start_deg, end_deg, 40, red_frac=0.5)

    frac_val = 0.0 if max_val <= 0 else max(0.0, min(value / max_val, 1.0))
    ang_val = start_deg + (end_deg - start_deg) * frac_val
    _draw_needle(draw, cx, cy, r_outer, ang_val)

    # Place readout below the needle hub - fonts scaled (reference size 240px)
    val_font = safe_font(_scale_font_size(60, gauge_size, 240))
    txt = f"{int(round(value))}"
    tw = draw.textlength(txt, font=val_font)
    val_offset = int(10 * gauge_size / 240)
    draw.text((cx - tw // 2, cy + val_offset), txt, fill="black", font=val_font)

    unit_font = safe_font(_scale_font_size(20, gauge_size, 240))
    txt = "km/h"
    tw = draw.textlength(txt, font=unit_font)
    unit_offset = int(70 * gauge_size / 240)
    draw.text((cx - tw // 2, cy + unit_offset), txt, fill="black", font=unit_font)

def draw_cadence_gauge(img, rect, value, max_val):
    """Draw cadence gauge (horizontal arc like speed gauge)."""
    _draw_small_gauge(
        img, rect, value, 0, max_val,
        "CADENCE", "rpm",
        start_deg=180, end_deg=360,   # horizontal bottom arc
        side="center"
    )

def draw_hr_gauge(img, rect, value, max_val):
    """Draw heart rate gauge (left half)."""
    _draw_small_gauge(
        img, rect, value, 80, max_val,
        "HEART RATE", "bpm",
        start_deg=90, end_deg=270,    # left half
        side="right"                  # readout right of hub
    )

def draw_elev_gauge(img, rect, value, max_val):
    """Draw elevation gauge (left half)."""
    _draw_small_gauge(
        img, rect, value, 0, max_val,
        "ELEVATION", "m",
        start_deg=90, end_deg=270,    # left half
        side="right"
    )

def draw_gradient_gauge(img, rect, value, min_val, max_val):
    """Draw gradient gauge (horizontal arc, two-sided for +/-)."""
    _draw_small_gauge(
        img, rect, value, min_val, max_val,
        "GRADIENT", "%",
        start_deg=180, end_deg=360,   # horizontal bottom arc
        two_sided=True, side="center"
    )