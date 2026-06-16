# SPDX-License-Identifier: GPL-3.0-or-later
"""Pure coordinate translations between FHD reference and screen pixels.

Every function is `(value, WindowGeometry) -> value`: no capture, no
clicks, no telemetry. Centralizing the scale arithmetic that legacy
code spread inline (`comp = p.WINDOW[2] / 1920`) kills a class of
forgot-to-scale bugs.
"""
from __future__ import annotations

from .types import FHD_HEIGHT, FHD_WIDTH, Region, ScreenRect, WindowGeometry


def region_to_screen(region: Region, window: WindowGeometry) -> ScreenRect:
    """Translate an FHD region into the screen rectangle to capture."""
    s = window.scale
    return ScreenRect(
        x=round(window.x + region.x * s),
        y=round(window.y + region.y * s),
        w=round(region.w * s),
        h=round(region.h * s),
    )


def point_fhd_to_screen(
    point: tuple[int, int], window: WindowGeometry
) -> tuple[int, int]:
    """Translate an FHD-space click target into a screen-pixel target."""
    x, y = point
    s = window.scale
    return (int(window.x + x * s), int(window.y + y * s))


def point_screen_to_fhd(
    point: tuple[int, int], window: WindowGeometry
) -> tuple[int, int]:
    """Translate a screen-pixel point back into FHD reference (inverse of point_fhd_to_screen)."""
    x, y = point
    inv = window.inv_scale
    return (int((x - window.x) * inv), int((y - window.y) * inv))


def lift_match_to_fhd(
    match_box: tuple[int, int, int, int],
    region: Region,
    window: WindowGeometry,
) -> tuple[int, int, int, int]:
    """Translate a detection-layer Match (image-local) into FHD coords.

    Detection coords are relative to the cropped, window-scaled frame.
    Two steps to lift them: undo the window scale (multiply by
    inv_scale), then offset by the region origin.
    """
    mx, my, mw, mh = match_box
    inv = window.inv_scale
    fhd_x = int(mx * inv) + region.x
    fhd_y = int(my * inv) + region.y
    fhd_w = int(mw * inv)
    fhd_h = int(mh * inv)
    return (fhd_x, fhd_y, fhd_w, fhd_h)


def scale_size(size: tuple[int, int], window: WindowGeometry) -> tuple[int, int]:
    """Scale a (w, h) pair from FHD reference to screen pixels (jitter targets, radii)."""
    w, h = size
    s = window.scale
    return (int(w * s), int(h * s))


__all__ = [
    "FHD_HEIGHT",
    "FHD_WIDTH",
    "region_to_screen",
    "point_fhd_to_screen",
    "point_screen_to_fhd",
    "lift_match_to_fhd",
    "scale_size",
]
