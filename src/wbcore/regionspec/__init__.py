# SPDX-License-Identifier: GPL-3.0-or-later
"""RegionSpec: pure coordinate translation.

Two coordinate spaces, three translations, no IO. See README.md.
"""
from .translate import (
    lift_match_to_fhd,
    point_fhd_to_screen,
    point_screen_to_fhd,
    region_to_screen,
    scale_size,
)
from .types import (
    FHD_HEIGHT,
    FHD_WIDTH,
    Region,
    ScreenRect,
    WindowGeometry,
)

__all__ = [
    "FHD_WIDTH",
    "FHD_HEIGHT",
    "Region",
    "ScreenRect",
    "WindowGeometry",
    "region_to_screen",
    "point_fhd_to_screen",
    "point_screen_to_fhd",
    "lift_match_to_fhd",
    "scale_size",
]
