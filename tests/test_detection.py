# SPDX-License-Identifier: GPL-3.0-or-later
"""Fixture tests for `src.wbcore.detection`.

These tests run without a display, without a game window, and without
any of the legacy `Locate` machinery. They cover:

1. Self-match: a template matched against a frame that contains it
   exactly returns confidence ~1.0 at the expected location.
2. Sub-threshold: a clearly-different template returns no Match.
3. Multi-match + NMS: two copies of a template inside the frame yield
   two distinct Match objects, sorted by confidence.
4. Color modes: GRAY mode produces a Match at the same location as
   RGB; EDGES mode finds a sharp template.
5. Real ImageAssets PNG: the matcher works on a real on-disk template
   (self-match against itself), proving the pipeline is not just
   synthetic.
"""
from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np
import pytest

from src.wbcore.detection import (
    ColorMode,
    Match,
    MatchMethod,
    match_all,
    match_one,
)

_REPO = Path(__file__).resolve().parents[1]
_CONFIRM_PNG = _REPO / "ImageAssets" / "UI" / "Confirm.png"


# --- helpers -------------------------------------------------------------

def _solid(h: int, w: int, color: tuple[int, int, int]) -> np.ndarray:
    """Build a uint8 BGR rectangle filled with `color`."""
    img = np.zeros((h, w, 3), dtype=np.uint8)
    img[:, :] = color
    return img


def _checker(size: int = 32, tile: int = 4) -> np.ndarray:
    """A high-contrast checkerboard, sharp enough that Canny finds edges."""
    img = np.zeros((size, size, 3), dtype=np.uint8)
    for y in range(0, size, tile):
        for x in range(0, size, tile):
            if ((x // tile) + (y // tile)) % 2 == 0:
                img[y:y + tile, x:x + tile] = (255, 255, 255)
    return img


def _frame_with(template: np.ndarray, at: tuple[int, int],
                size: tuple[int, int] = (200, 300)) -> np.ndarray:
    """Build a frame with `template` placed at top-left position `at`."""
    h, w = size
    frame = _solid(h, w, (40, 40, 40))
    th, tw = template.shape[:2]
    y, x = at
    frame[y:y + th, x:x + tw] = template
    return frame


# --- 1. self-match -------------------------------------------------------

def test_self_match_returns_high_confidence():
    template = _checker()
    frame = _frame_with(template, at=(50, 70))

    hit = match_one(frame, template, conf=0.9)

    assert hit is not None
    assert isinstance(hit, Match)
    assert hit.x == 70 and hit.y == 50
    assert hit.w == template.shape[1] and hit.h == template.shape[0]
    assert hit.confidence > 0.99


def test_self_match_center_and_box():
    template = _checker(size=16, tile=4)
    frame = _frame_with(template, at=(20, 30), size=(64, 80))
    hit = match_one(frame, template)

    assert hit is not None
    assert hit.box == (30, 20, 16, 16)
    assert hit.center == (30 + 8, 20 + 8)


# --- 2. sub-threshold ----------------------------------------------------

def test_no_match_when_template_absent():
    # Frame is uniform grey; template is the checkerboard. There is no
    # near-copy of the checker pattern in the frame, so no Match.
    frame = _solid(200, 200, (40, 40, 40))
    template = _checker()

    assert match_one(frame, template, conf=0.95) is None
    assert match_all(frame, template, conf=0.95) == []


# --- 3. multi-match + NMS -----------------------------------------------

def test_match_all_finds_multiple_copies():
    template = _checker(size=16, tile=4)
    frame = _solid(200, 300, (40, 40, 40))
    th, tw = template.shape[:2]
    # Two copies, separated comfortably more than nms_threshold.
    for (y, x) in [(20, 30), (140, 220)]:
        frame[y:y + th, x:x + tw] = template

    hits = match_all(frame, template, conf=0.9, nms_threshold=8)

    assert len(hits) == 2
    locations = sorted((h.x, h.y) for h in hits)
    assert locations == [(30, 20), (220, 140)]
    # Sorted by confidence descending.
    assert hits[0].confidence >= hits[1].confidence


def test_nms_collapses_near_duplicates():
    template = _checker(size=16, tile=4)
    frame = _frame_with(template, at=(20, 30), size=(64, 80))
    # Even with a low threshold, a single copy must yield exactly one Match
    # (cv2's matchTemplate can produce a small cluster of high-scoring cells
    # around the true location; NMS must collapse them).
    hits = match_all(frame, template, conf=0.95, nms_threshold=8)
    assert len(hits) == 1


# --- 4. color modes ------------------------------------------------------

def test_gray_mode_locates_same_position_as_rgb():
    template = _checker()
    frame = _frame_with(template, at=(50, 70))

    rgb = match_one(frame, template, color_mode=ColorMode.RGB)
    gray = match_one(frame, template, color_mode=ColorMode.GRAY)

    assert rgb is not None and gray is not None
    assert (rgb.x, rgb.y) == (gray.x, gray.y)


def test_edges_mode_finds_sharp_template():
    template = _checker()
    frame = _frame_with(template, at=(60, 90))

    hit = match_one(frame, template, conf=0.8, color_mode=ColorMode.EDGES)

    assert hit is not None
    assert (hit.x, hit.y) == (90, 60)


# --- 5. real PNG fixture -------------------------------------------------

@pytest.mark.skipif(
    not _CONFIRM_PNG.exists(),
    reason="ImageAssets/UI/Confirm.png missing; skipping real-PNG fixture test",
)
def test_real_png_self_match():
    template = cv2.imread(str(_CONFIRM_PNG))
    assert template is not None, "Confirm.png failed to decode"

    # Embed the real template inside a larger neutral frame so the matcher
    # has somewhere to slide. Position 137x91 has no meaning beyond
    # 'definitely not at the origin'.
    th, tw = template.shape[:2]
    frame = _solid(th + 200, tw + 200, (12, 12, 12))
    frame[91:91 + th, 137:137 + tw] = template

    hit = match_one(
        frame,
        template,
        conf=0.95,
        template_name="Confirm.png",
    )

    assert hit is not None
    assert (hit.x, hit.y) == (137, 91)
    assert hit.confidence > 0.99
    assert hit.template_name == "Confirm.png"


# --- 6. method coverage --------------------------------------------------

@pytest.mark.parametrize(
    "method",
    [
        MatchMethod.CCOEFF_NORMED,
        MatchMethod.CCORR_NORMED,
        MatchMethod.SQDIFF_NORMED,
    ],
)
def test_every_method_supports_self_match(method: MatchMethod):
    template = _checker()
    frame = _frame_with(template, at=(40, 50))
    hit = match_one(frame, template, conf=0.9, method=method)
    assert hit is not None
    assert (hit.x, hit.y) == (50, 40)
    assert 0.0 <= hit.confidence <= 1.0


def test_confidence_is_always_in_unit_interval():
    template = _checker()
    frame = _frame_with(template, at=(10, 20))
    for method in MatchMethod:
        hit = match_one(frame, template, conf=0.5, method=method)
        assert hit is not None
        assert 0.0 <= hit.confidence <= 1.0, (method, hit.confidence)
