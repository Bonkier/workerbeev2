# SPDX-License-Identifier: GPL-3.0-or-later
"""Tests for `src.wbcore.regions` + `Region.coerce` + tuple-accepting Finder.

Three things to verify:

1. `Region.coerce(...)` accepts a Region, a 4-tuple, a 4-list, or None,
   and rejects everything else.
2. `regions.REGIONS` lazily exposes the live `REG` dict as
   `dict[str, Region]`; `regions.as_region(...)` extends `coerce` with
   string-name lookup.
3. `Finder.find` / `Finder.find_all` accept tuples in place of Regions
   for back-compat migration.
"""
from __future__ import annotations

import numpy as np
import pytest

from src.wbcore.regionspec import Region, WindowGeometry
from src.wbcore.vision import Finder, TemplateLoader


# ---- Region.coerce ------------------------------------------------------

def test_coerce_passes_region_through():
    r = Region(10, 20, 30, 40)
    assert Region.coerce(r) is r


def test_coerce_wraps_tuple():
    assert Region.coerce((1, 2, 3, 4)) == Region(1, 2, 3, 4)


def test_coerce_wraps_list():
    assert Region.coerce([1, 2, 3, 4]) == Region(1, 2, 3, 4)


def test_coerce_none_returns_full_frame():
    assert Region.coerce(None) == Region.full()


def test_coerce_rejects_wrong_length():
    with pytest.raises(ValueError):
        Region.coerce((1, 2, 3))
    with pytest.raises(ValueError):
        Region.coerce((1, 2, 3, 4, 5))


def test_coerce_rejects_unsupported_type():
    with pytest.raises(TypeError):
        Region.coerce(object())


def test_coerce_casts_floats_to_ints():
    r = Region.coerce((1.7, 2.4, 3.0, 4.9))
    assert r == Region(1, 2, 3, 4)


# ---- regions module -----------------------------------------------------

def test_regions_exposes_legacy_REG_as_Region_dict():
    from src.wbcore.regions import REGIONS

    # Spot-check a handful of well-known entries from paths.REG.
    assert isinstance(REGIONS["Confirm"], Region)
    assert isinstance(REGIONS["MD"], Region)
    assert isinstance(REGIONS["Start"], Region)


def test_regions_values_match_legacy_REG_tuples():
    from src.wbcore.regions import REGIONS
    from src.wbcore.utils.paths import REG

    # Every Region in REGIONS must match the legacy tuple shape.
    for name, region in REGIONS.items():
        legacy = REG[name]
        assert region == Region(*legacy), name


def test_regions_supports_contains_iter_len():
    from src.wbcore.regions import REGIONS
    from src.wbcore.utils.paths import REG

    assert "Confirm" in REGIONS
    assert "definitely-not-a-region" not in REGIONS
    assert len(REGIONS) > 50          # the real REG is over 100
    # Iteration covers every key.
    seen = set(REGIONS)
    assert seen == set(name for name, v in REG.items()
                       if isinstance(v, tuple) and len(v) == 4)


def test_regions_get_returns_default_on_miss():
    from src.wbcore.regions import REGIONS
    sentinel = Region(0, 0, 1, 1)
    assert REGIONS.get("not-a-real-name", sentinel) is sentinel


# ---- as_region ---------------------------------------------------------

def test_as_region_passes_region_through():
    from src.wbcore.regions import as_region
    r = Region(10, 20, 30, 40)
    assert as_region(r) is r


def test_as_region_wraps_tuple():
    from src.wbcore.regions import as_region
    assert as_region((1, 2, 3, 4)) == Region(1, 2, 3, 4)


def test_as_region_none_returns_full():
    from src.wbcore.regions import as_region
    assert as_region(None) == Region.full()


def test_as_region_string_looks_up_in_REGIONS():
    from src.wbcore.regions import REGIONS, as_region
    # Pick any real entry.
    assert as_region("Confirm") == REGIONS["Confirm"]


def test_as_region_unknown_string_raises():
    from src.wbcore.regions import as_region
    with pytest.raises(KeyError):
        as_region("definitely-not-a-real-region")


def test_as_region_rejects_dict():
    from src.wbcore.regions import as_region
    with pytest.raises(TypeError):
        as_region({"x": 1})


# ---- Finder accepts tuples ---------------------------------------------

def _checker(size=32, tile=4):
    img = np.zeros((size, size, 3), dtype=np.uint8)
    for y in range(0, size, tile):
        for x in range(0, size, tile):
            if ((x // tile) + (y // tile)) % 2 == 0:
                img[y:y + tile, x:x + tile] = (255, 255, 255)
    return img


def _solid(h, w, color):
    img = np.zeros((h, w, 3), dtype=np.uint8)
    img[:, :] = color
    return img


def _embed(frame_size, template, at):
    h, w = frame_size
    frame = _solid(h, w, (12, 12, 12))
    th, tw = template.shape[:2]
    y, x = at
    frame[y:y + th, x:x + tw] = template
    return frame


class _RecordingBackend:
    def __init__(self, frame):
        self.frame = frame
        self.calls = []

    def __call__(self, rect):
        self.calls.append(rect)
        return self.frame


def test_finder_find_accepts_tuple_region():
    template = _checker()
    cropped = _embed((200, 300), template, at=(50, 70))

    finder = Finder(
        window=WindowGeometry.identity(),
        backend=_RecordingBackend(cropped),
        loader=TemplateLoader(prefilled={"c": template}),
    )

    # Legacy 4-tuple shape, NOT a Region.
    hit = finder.find("c", region=(400, 200, 300, 200), conf=0.95)

    assert hit is not None
    # Position is the same as if we'd passed Region(400, 200, 300, 200).
    assert (hit.x, hit.y) == (470, 250)


def test_finder_find_all_accepts_tuple_region():
    template = _checker(size=16, tile=4)
    cropped = _solid(200, 300, (12, 12, 12))
    th, tw = template.shape[:2]
    for (y, x) in [(20, 30), (140, 220)]:
        cropped[y:y + th, x:x + tw] = template

    finder = Finder(
        window=WindowGeometry.identity(),
        backend=_RecordingBackend(cropped),
        loader=TemplateLoader(prefilled={"c": template}),
    )

    hits = finder.find_all("c", region=(100, 100, 300, 200), conf=0.9)
    locations = sorted((h.x, h.y) for h in hits)
    assert locations == [(130, 120), (320, 240)]


def test_finder_find_none_region_still_works():
    """Regression: None region defaults to full FHD frame."""
    finder = Finder(
        window=WindowGeometry.identity(),
        backend=_RecordingBackend(_solid(100, 100, (0, 0, 0))),
        loader=TemplateLoader(prefilled={"c": _checker()}),
    )
    # Just exercise the path; we expect None back (uniform frame).
    assert finder.find("c", region=None, conf=0.99) is None
