# SPDX-License-Identifier: GPL-3.0-or-later
"""Fixture tests for `src.wbcore.regionspec`.

No screen capture, no game window, no opencv. Pure arithmetic.

We exercise three window geometries that bracket the realistic range:
- 1920x1080 identity (no scale)
- 3840x2160 upscale (4K monitor, 2.0x)
- 960x540 downscale (debug / small-monitor, 0.5x)

For each we check that:
- `region_to_screen` matches the inline math in legacy `screenshot()`.
- `point_fhd_to_screen` and `point_screen_to_fhd` round-trip.
- `lift_match_to_fhd` translates a detection-layer hit back into the
  canonical FHD frame.
- `scale_size` is consistent with `point_*` for distance-only values.
"""
from __future__ import annotations

import pytest

from src.wbcore.detection import Match
from src.wbcore.regionspec import (
    FHD_HEIGHT,
    FHD_WIDTH,
    Region,
    ScreenRect,
    WindowGeometry,
    lift_match_to_fhd,
    point_fhd_to_screen,
    point_screen_to_fhd,
    region_to_screen,
    scale_size,
)


# ---- types ---------------------------------------------------------------

def test_window_identity_has_unit_scale():
    w = WindowGeometry.identity()
    assert w.scale == 1.0
    assert w.inv_scale == 1.0
    assert (w.w, w.h) == (FHD_WIDTH, FHD_HEIGHT)


def test_window_4k_has_2x_scale():
    w = WindowGeometry(x=0, y=0, w=3840, h=2160)
    assert w.scale == 2.0
    assert w.inv_scale == 0.5


def test_window_half_has_half_scale():
    w = WindowGeometry(x=0, y=0, w=960, h=540)
    assert w.scale == 0.5
    assert w.inv_scale == 2.0


def test_window_rejects_zero_size():
    with pytest.raises(ValueError):
        WindowGeometry(x=0, y=0, w=0, h=1080)
    with pytest.raises(ValueError):
        WindowGeometry(x=0, y=0, w=1920, h=-1)


def test_region_geometry_helpers():
    r = Region(x=10, y=20, w=100, h=50)
    assert r.right == 110
    assert r.bottom == 70
    assert r.center == (60, 45)
    assert r.offset_point(5, 7) == (15, 27)


def test_region_full_is_fhd():
    r = Region.full()
    assert r.x == 0 and r.y == 0
    assert r.w == FHD_WIDTH and r.h == FHD_HEIGHT


# ---- region_to_screen ----------------------------------------------------

@pytest.fixture(
    params=[
        ("identity", WindowGeometry(x=0, y=0, w=1920, h=1080)),
        ("identity_offset", WindowGeometry(x=137, y=91, w=1920, h=1080)),
        ("4k", WindowGeometry(x=0, y=0, w=3840, h=2160)),
        ("4k_offset", WindowGeometry(x=400, y=200, w=3840, h=2160)),
        ("half", WindowGeometry(x=0, y=0, w=960, h=540)),
    ],
    ids=lambda p: p[0],
)
def window(request):
    return request.param[1]


def test_region_to_screen_matches_legacy_inline_math(window):
    r = Region(x=200, y=120, w=320, h=180)
    s = window.scale
    expected = ScreenRect(
        x=round(window.x + r.x * s),
        y=round(window.y + r.y * s),
        w=round(r.w * s),
        h=round(r.h * s),
    )
    assert region_to_screen(r, window) == expected


def test_region_to_screen_identity_is_identity_plus_origin():
    w = WindowGeometry(x=137, y=91, w=1920, h=1080)
    r = Region(x=10, y=20, w=30, h=40)
    s = region_to_screen(r, w)
    assert s == ScreenRect(x=147, y=111, w=30, h=40)


def test_region_to_screen_4k_doubles_dimensions():
    w = WindowGeometry(x=0, y=0, w=3840, h=2160)
    r = Region(x=100, y=50, w=200, h=80)
    s = region_to_screen(r, w)
    assert s == ScreenRect(x=200, y=100, w=400, h=160)


# ---- point translation ---------------------------------------------------

def test_point_fhd_to_screen_applies_offset_and_scale():
    w = WindowGeometry(x=400, y=200, w=3840, h=2160)
    assert point_fhd_to_screen((100, 50), w) == (600, 300)


def test_point_round_trip(window):
    p_fhd = (123, 456)
    p_screen = point_fhd_to_screen(p_fhd, window)
    p_back = point_screen_to_fhd(p_screen, window)
    # Allow at most 1 px loss to integer truncation in either direction.
    assert abs(p_back[0] - p_fhd[0]) <= 1
    assert abs(p_back[1] - p_fhd[1]) <= 1


def test_point_round_trip_exact_at_identity():
    w = WindowGeometry.identity(x=137, y=91)
    p_fhd = (123, 456)
    assert point_screen_to_fhd(point_fhd_to_screen(p_fhd, w), w) == p_fhd


# ---- lift_match_to_fhd ---------------------------------------------------

def test_lift_match_identity_just_offsets_by_region_origin():
    w = WindowGeometry.identity()
    r = Region(x=500, y=300, w=200, h=100)
    # A match at (10, 20) inside the cropped region is at (510, 320) in FHD.
    assert lift_match_to_fhd((10, 20, 40, 30), r, w) == (510, 320, 40, 30)


def test_lift_match_4k_undoes_scale_then_offsets():
    w = WindowGeometry(x=0, y=0, w=3840, h=2160)
    r = Region(x=500, y=300, w=200, h=100)
    # Frame was captured at 2x. A 20px hit in frame space is 10px in FHD.
    assert lift_match_to_fhd((20, 40, 80, 60), r, w) == (510, 320, 40, 30)


def test_lift_match_integrates_with_detection_match():
    # The Match dataclass from Phase 2 produces image-local boxes.
    # RegionSpec lifts them into FHD. This proves the two layers compose.
    w = WindowGeometry(x=137, y=91, w=1920, h=1080)
    r = Region(x=400, y=300, w=300, h=200)
    hit = Match(x=15, y=25, w=40, h=30, confidence=0.99, template_name="ok.png")
    fhd_box = lift_match_to_fhd(hit.box, r, w)
    assert fhd_box == (415, 325, 40, 30)


# ---- scale_size ----------------------------------------------------------

def test_scale_size_identity_is_passthrough():
    w = WindowGeometry.identity()
    assert scale_size((5, 5), w) == (5, 5)


def test_scale_size_4k_doubles():
    w = WindowGeometry(x=0, y=0, w=3840, h=2160)
    assert scale_size((5, 5), w) == (10, 10)


def test_scale_size_half_halves():
    w = WindowGeometry(x=0, y=0, w=960, h=540)
    assert scale_size((10, 6), w) == (5, 3)
