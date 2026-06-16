# SPDX-License-Identifier: GPL-3.0-or-later
"""Fixture tests for `src.wbcore.vision`.

All IO is injected. We use a fake `CaptureFn` that returns a pre-built
ndarray, and a `TemplateLoader` either pre-seeded with ndarrays or
pointed at a real on-disk PNG. Nothing in these tests needs a game
window, a display server, or the bridge backend.
"""
from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np
import pytest

from src.wbcore.detection import ColorMode, Match
from src.wbcore.regionspec import Region, ScreenRect, WindowGeometry
from src.wbcore.vision import (
    CaptureFn,
    Finder,
    TemplateLoader,
    capture,
)


_REPO = Path(__file__).resolve().parents[1]
_CONFIRM_PNG = _REPO / "ImageAssets" / "UI" / "Confirm.png"


# ---- helpers -------------------------------------------------------------

def _solid(h: int, w: int, color: tuple[int, int, int]) -> np.ndarray:
    img = np.zeros((h, w, 3), dtype=np.uint8)
    img[:, :] = color
    return img


def _checker(size: int = 32, tile: int = 4) -> np.ndarray:
    img = np.zeros((size, size, 3), dtype=np.uint8)
    for y in range(0, size, tile):
        for x in range(0, size, tile):
            if ((x // tile) + (y // tile)) % 2 == 0:
                img[y:y + tile, x:x + tile] = (255, 255, 255)
    return img


class _RecordingBackend:
    """Fake CaptureFn that records what it was asked to capture."""

    def __init__(self, frame: np.ndarray):
        self.frame = frame
        self.calls: list[ScreenRect] = []

    def __call__(self, rect: ScreenRect) -> np.ndarray:
        self.calls.append(rect)
        return self.frame


# ---- capture -------------------------------------------------------------

def test_capture_translates_region_via_window():
    frame = _solid(540, 960, (10, 10, 10))
    backend = _RecordingBackend(frame)
    window = WindowGeometry(x=100, y=50, w=1920, h=1080)
    region = Region(x=200, y=300, w=400, h=200)

    out = capture(region, window, backend)

    assert out is frame
    assert len(backend.calls) == 1
    # Identity-scale window: region is offset by window origin only.
    assert backend.calls[0] == ScreenRect(x=300, y=350, w=400, h=200)


def test_capture_full_frame_when_region_none():
    frame = _solid(1080, 1920, (0, 0, 0))
    backend = _RecordingBackend(frame)
    window = WindowGeometry.identity()

    capture(None, window, backend)

    assert backend.calls[0] == ScreenRect(x=0, y=0, w=1920, h=1080)


def test_capture_rejects_non_ndarray():
    def bad_backend(_rect: ScreenRect):
        return "not an ndarray"

    with pytest.raises(TypeError):
        capture(Region.full(), WindowGeometry.identity(), bad_backend)  # type: ignore[arg-type]


# ---- TemplateLoader ------------------------------------------------------

def test_loader_cache_hits_on_repeat():
    tmpl = _checker()
    loader = TemplateLoader(prefilled={"fake.png": tmpl})
    a = loader.load("fake.png")
    b = loader.load("fake.png")
    assert loader.is_cached("fake.png")
    assert a.shape == b.shape


def test_loader_cache_can_be_disabled():
    tmpl = _checker()
    loader = TemplateLoader(cache=False, prefilled={"fake.png": tmpl})
    # prefilled still works as a one-shot seed; cache disabled just
    # means new imreads are not retained. Verify with an ndarray pass-through.
    out = loader.load(tmpl)
    assert out.shape == tmpl.shape


def test_loader_resize_via_window_scale():
    tmpl = _checker(size=64)  # 64x64 raw
    loader = TemplateLoader(prefilled={"fake.png": tmpl})

    raw = loader.load("fake.png", window=WindowGeometry.identity())
    half = loader.load("fake.png", window=WindowGeometry(x=0, y=0, w=960, h=540))

    assert raw.shape[:2] == (64, 64)
    assert half.shape[:2] == (32, 32)  # 0.5x scale


def test_loader_v_comp_validates():
    loader = TemplateLoader(prefilled={"fake.png": _checker()})
    with pytest.raises(ValueError):
        loader.load("fake.png", v_comp=2.0)
    with pytest.raises(ValueError):
        loader.load("fake.png", v_comp=0)


def test_loader_h_comp_validates():
    loader = TemplateLoader(prefilled={"fake.png": _checker()})
    with pytest.raises(ValueError):
        loader.load("fake.png", h_comp=0)


def test_loader_missing_file_raises():
    loader = TemplateLoader()
    with pytest.raises(FileNotFoundError):
        loader.load("definitely/does/not/exist.png")


@pytest.mark.skipif(
    not _CONFIRM_PNG.exists(),
    reason="ImageAssets/UI/Confirm.png missing; skipping real PNG load",
)
def test_loader_reads_real_png_from_disk():
    loader = TemplateLoader()
    tmpl = loader.load(_CONFIRM_PNG, window=WindowGeometry.identity())
    assert tmpl.ndim == 3
    assert loader.is_cached(_CONFIRM_PNG)
    assert loader.cache_size() == 1


# ---- usage tracking ------------------------------------------------------

def test_usage_tracking_disabled_by_default():
    loader = TemplateLoader(prefilled={"a.png": _checker()})
    loader.load("a.png")
    loader.load("a.png")
    assert loader.usage_report() == []
    assert loader.usage_total() == 0


def test_usage_tracking_counts_loads_per_path():
    loader = TemplateLoader(
        prefilled={"a.png": _checker(), "b.png": _checker()},
        track_usage=True,
    )
    loader.load("a.png")
    loader.load("a.png")
    loader.load("a.png")
    loader.load("b.png")

    report = loader.usage_report()
    assert report == [(3, "a.png"), (1, "b.png")]
    assert loader.usage_total() == 4


def test_usage_tracking_ignores_ndarray_loads():
    """Direct ndarray loads have no path to attribute; don't count them."""
    tmpl = _checker()
    loader = TemplateLoader(track_usage=True)
    loader.load(tmpl)
    loader.load(tmpl)
    assert loader.usage_report() == []


def test_usage_report_sorted_descending_then_alphabetical():
    loader = TemplateLoader(
        prefilled={
            "z.png": _checker(),
            "a.png": _checker(),
            "m.png": _checker(),
        },
        track_usage=True,
    )
    loader.load("z.png")
    loader.load("a.png"); loader.load("a.png")
    loader.load("m.png"); loader.load("m.png")

    # m and a tied at 2; alphabetical tiebreak puts a first. z is third.
    assert loader.usage_report() == [(2, "a.png"), (2, "m.png"), (1, "z.png")]


def test_reset_usage_clears_counters_but_keeps_cache():
    loader = TemplateLoader(
        prefilled={"a.png": _checker()},
        track_usage=True,
    )
    loader.load("a.png")
    loader.load("a.png")
    loader.reset_usage()
    assert loader.usage_report() == []
    assert loader.is_cached("a.png")  # cache survived


# ---- Finder --------------------------------------------------------------

def _embed(frame_size, template, at):
    """Place `template` at `at` in a fresh frame of `frame_size`."""
    h, w = frame_size
    frame = _solid(h, w, (12, 12, 12))
    th, tw = template.shape[:2]
    y, x = at
    frame[y:y + th, x:x + tw] = template
    return frame


def test_finder_returns_match_in_fhd_coords_identity_window():
    template = _checker()
    region = Region(x=400, y=200, w=300, h=200)
    # The frame we hand the backend is the cropped region (200x300).
    cropped = _embed((region.h, region.w), template, at=(50, 70))

    window = WindowGeometry.identity()
    backend = _RecordingBackend(cropped)
    loader = TemplateLoader(prefilled={"checker": template})
    finder = Finder(window=window, backend=backend, loader=loader)

    hit = finder.find("checker", region=region, conf=0.95)

    assert hit is not None
    # match was at (70, 50) in the cropped frame at identity scale,
    # region origin is (400, 200), so FHD is (470, 250).
    assert (hit.x, hit.y) == (470, 250)


def test_finder_under_4k_window_lifts_correctly():
    template = _checker()
    region = Region(x=400, y=200, w=300, h=200)
    # 4K window: capture comes back at 2x. Cropped frame is 400x600.
    th, tw = template.shape[:2]
    cropped = _solid(region.h * 2, region.w * 2, (12, 12, 12))
    # 2x version of the template:
    big_template = cv2.resize(template, (tw * 2, th * 2), interpolation=cv2.INTER_NEAREST)
    cropped[100:100 + big_template.shape[0], 140:140 + big_template.shape[1]] = big_template

    window = WindowGeometry(x=0, y=0, w=3840, h=2160)
    backend = _RecordingBackend(cropped)
    # The loader will scale the raw template up to 2x via window.scale.
    loader = TemplateLoader(prefilled={"checker": template})
    finder = Finder(window=window, backend=backend, loader=loader)

    hit = finder.find("checker", region=region, conf=0.9)

    assert hit is not None
    # Match in cropped frame at (140, 100). Undo 2x scale -> (70, 50) in
    # FHD-local; offset by region (400, 200) -> (470, 250).
    assert (hit.x, hit.y) == (470, 250)


def test_finder_returns_none_when_template_absent():
    region = Region(x=0, y=0, w=200, h=200)
    cropped = _solid(region.h, region.w, (40, 40, 40))
    template = _checker()

    window = WindowGeometry.identity()
    backend = _RecordingBackend(cropped)
    loader = TemplateLoader(prefilled={"checker": template})
    finder = Finder(window=window, backend=backend, loader=loader)

    assert finder.find("checker", region=region, conf=0.95) is None


def test_finder_find_all_lifts_each_hit():
    template = _checker(size=16, tile=4)
    region = Region(x=100, y=100, w=300, h=200)
    cropped = _solid(region.h, region.w, (12, 12, 12))
    th, tw = template.shape[:2]
    for (y, x) in [(20, 30), (140, 220)]:
        cropped[y:y + th, x:x + tw] = template

    window = WindowGeometry.identity()
    backend = _RecordingBackend(cropped)
    loader = TemplateLoader(prefilled={"checker": template})
    finder = Finder(window=window, backend=backend, loader=loader)

    hits = finder.find_all("checker", region=region, conf=0.9, nms_threshold=8)

    locations = sorted((h.x, h.y) for h in hits)
    # (30, 20) and (220, 140) in cropped + (100, 100) region origin.
    assert locations == [(130, 120), (320, 240)]


def test_finder_telemetry_fires_on_hit():
    template = _checker()
    region = Region(x=10, y=20, w=200, h=200)
    cropped = _embed((region.h, region.w), template, at=(30, 40))

    events: list[tuple[str, tuple[int, int, int, int]]] = []

    finder = Finder(
        window=WindowGeometry.identity(),
        backend=_RecordingBackend(cropped),
        loader=TemplateLoader(prefilled={"checker": template}),
        on_match=lambda name, box: events.append((name, box)),
    )

    finder.find("checker", region=region, conf=0.9)

    assert len(events) == 1
    name, box = events[0]
    assert name == "checker"
    # FHD-lifted box: cropped match was at (40, 30); region origin (10, 20).
    assert box[:2] == (50, 50)


def test_finder_telemetry_does_not_fire_on_miss():
    events: list[tuple[str, tuple[int, int, int, int]]] = []
    finder = Finder(
        window=WindowGeometry.identity(),
        backend=_RecordingBackend(_solid(200, 200, (0, 0, 0))),
        loader=TemplateLoader(prefilled={"checker": _checker()}),
        on_match=lambda name, box: events.append((name, box)),
    )
    finder.find("checker", region=Region(0, 0, 200, 200), conf=0.95)
    assert events == []


def test_finder_accepts_explicit_frame_skips_capture():
    template = _checker()
    frame = _embed((200, 300), template, at=(40, 50))
    backend_calls: list[ScreenRect] = []

    def backend(rect: ScreenRect) -> np.ndarray:
        backend_calls.append(rect)
        return np.zeros((1, 1, 3), dtype=np.uint8)

    finder = Finder(
        window=WindowGeometry.identity(),
        backend=backend,
        loader=TemplateLoader(prefilled={"checker": template}),
    )

    hit = finder.find(
        "checker",
        region=Region(0, 0, 300, 200),
        conf=0.95,
        frame=frame,
    )

    assert hit is not None
    # If the frame is provided we must not call the backend at all.
    assert backend_calls == []


@pytest.mark.skipif(
    not _CONFIRM_PNG.exists(),
    reason="ImageAssets/UI/Confirm.png missing; skipping real PNG round trip",
)
def test_finder_real_png_end_to_end():
    template = cv2.imread(str(_CONFIRM_PNG))
    th, tw = template.shape[:2]
    # Build a frame that has Confirm.png embedded somewhere.
    region = Region(x=300, y=400, w=tw + 300, h=th + 200)
    cropped = _solid(region.h, region.w, (8, 8, 8))
    cropped[80:80 + th, 120:120 + tw] = template

    finder = Finder(
        window=WindowGeometry.identity(),
        backend=_RecordingBackend(cropped),
        loader=TemplateLoader(),  # real disk path
    )

    hit = finder.find(_CONFIRM_PNG, region=region, conf=0.95)

    assert hit is not None
    # FHD-lifted: cropped (120, 80) + region origin (300, 400) = (420, 480).
    assert (hit.x, hit.y) == (420, 480)
    assert hit.confidence > 0.99
