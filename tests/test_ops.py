# SPDX-License-Identifier: GPL-3.0-or-later
"""Tests for `src.wbcore.ops`.

Exercises the four method shapes (find / click / wait_gone / raw mouse)
against synthetic frames and fake backends. No display, no game window.
"""
from __future__ import annotations

from typing import Any, Optional

import numpy as np
import pytest

from src.wbcore.detection import Match
from src.wbcore.input import Mouse
from src.wbcore.ops import Ops
from src.wbcore.regionspec import Region, ScreenRect, WindowGeometry
from src.wbcore.verifier import Verifier
from src.wbcore.vision import Finder, TemplateLoader


# ---------------------------------------------------------------- fakes

class _Backend:
    """Shared fake satisfying both CaptureFn and InputBackend."""

    def __init__(self, frame: np.ndarray):
        self.frame = frame
        self.capture_calls: list = []
        self.click_calls: list = []
        self.move_calls: list = []
        self.drag_calls: list = []
        self.cursor: tuple[int, int] = (0, 0)

    def __call__(self, rect: ScreenRect) -> np.ndarray:
        self.capture_calls.append(rect)
        return self.frame

    def move_to(self, x, y, **kw):
        self.move_calls.append((x, y, kw))
        self.cursor = (x, y)

    def click(self, x=None, y=None, **kw):
        self.click_calls.append((x, y, kw))
        if x is not None and y is not None:
            self.cursor = (x, y)

    def drag_to(self, x, y, **kw):
        self.drag_calls.append((x, y, kw))
        self.cursor = (x, y)

    def position(self):
        return self.cursor


def _checker(size: int = 32, tile: int = 4) -> np.ndarray:
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


def _embed(template, at, size=(200, 300)):
    h, w = size
    frame = _solid(h, w, (12, 12, 12))
    th, tw = template.shape[:2]
    y, x = at
    frame[y:y + th, x:x + tw] = template
    return frame


# Custom resolvers so the tests don't need PTH / REGIONS or any disk IO.
def _fake_template_resolver(name: str):
    return f"path/to/{name.split('.')[0]}.png"


def _fake_region_resolver(name: str):
    return {
        "Confirm":    Region(400, 200, 300, 200),
        "result":     Region(0, 0, 50, 40),
        "result_bang": Region(0, 0, 50, 40),
    }.get(name)


def _build_ops(template: np.ndarray, frame: np.ndarray) -> tuple[Ops, _Backend]:
    backend = _Backend(frame)
    window = WindowGeometry.identity()
    loader = TemplateLoader(prefilled={"path/to/Confirm.png": template})
    finder = Finder(window=window, backend=backend, loader=loader)
    mouse = Mouse(window=window, backend=backend)
    verifier = Verifier(finder=finder, mouse=mouse, sleep=lambda _: None)
    ops = Ops(
        finder, mouse, verifier,
        template_resolver=_fake_template_resolver,
        region_resolver=_fake_region_resolver,
    )
    return ops, backend


# ----------------------------------------------------------------- find

def test_find_returns_match_on_hit():
    template = _checker()
    frame = _embed(template, at=(50, 70))
    ops, _ = _build_ops(template, frame)
    hit = ops.find("Confirm", conf=0.95)
    assert hit is not None
    assert isinstance(hit, Match)


def test_find_returns_none_on_miss():
    template = _checker()
    frame = _solid(200, 300, (0, 0, 0))
    ops, _ = _build_ops(template, frame)
    assert ops.find("Confirm", conf=0.99) is None


def test_find_strict_raises_on_miss():
    template = _checker()
    frame = _solid(200, 300, (0, 0, 0))
    ops, _ = _build_ops(template, frame)
    with pytest.raises(Ops.OpFailure):
        ops.find("Confirm", conf=0.99, strict=True)


def test_find_with_timeout_polls_via_verifier():
    """timeout=1 routes through verifier.wait_for."""
    template = _checker()
    frame = _embed(template, at=(50, 70))
    ops, _ = _build_ops(template, frame)
    hit = ops.find("Confirm", conf=0.95, timeout=1.0)
    assert hit is not None


def test_find_accepts_explicit_region_tuple():
    template = _checker()
    frame = _embed(template, at=(50, 70))
    ops, backend = _build_ops(template, frame)
    ops.find("Confirm", region=(0, 0, 300, 200), conf=0.95)
    # The capture rect should reflect the explicit region, not the
    # resolved one (which would have been at (400, 200, 300, 200)).
    assert backend.capture_calls[0].x == 0


def test_find_accepts_ndarray_template():
    template = _checker()
    frame = _embed(template, at=(50, 70))
    ops, _ = _build_ops(template, frame)
    hit = ops.find(template, region=(0, 0, 300, 200), conf=0.95)
    assert hit is not None


# ---------------------------------------------------------------- click

def test_click_returns_true_on_hit():
    template = _checker()
    frame = _embed(template, at=(50, 70))
    ops, backend = _build_ops(template, frame)
    ok = ops.click("Confirm", conf=0.95, timeout=1.0)
    assert ok is True
    assert len(backend.click_calls) == 1


def test_click_returns_false_on_miss():
    template = _checker()
    frame = _solid(200, 300, (0, 0, 0))
    ops, backend = _build_ops(template, frame)
    ok = ops.click("Confirm", conf=0.99, timeout=0.0)
    assert ok is False
    assert backend.click_calls == []


def test_click_strict_raises_on_miss():
    template = _checker()
    frame = _solid(200, 300, (0, 0, 0))
    ops, _ = _build_ops(template, frame)
    with pytest.raises(Ops.OpFailure):
        ops.click("Confirm", conf=0.99, timeout=0.0, strict=True)


def test_click_at_overrides_target():
    template = _checker()
    frame = _embed(template, at=(50, 70))
    ops, backend = _build_ops(template, frame)
    ops.click("Confirm", conf=0.95, timeout=1.0, at=(1690, 897))
    x, y, _ = backend.click_calls[0]
    assert (x, y) == (1690, 897)


def test_click_with_tsize_propagates():
    template = _checker()
    frame = _embed(template, at=(50, 70))
    ops, backend = _build_ops(template, frame)
    ops.click("Confirm", conf=0.95, tsize=(5, 5), timeout=1.0)
    _, _, kw = backend.click_calls[0]
    assert kw == {"tsize": (5, 5)}


# --------------------------------------------------------------- verify

class _ChangingBackend(_Backend):
    """Returns frame_before for verify-region captures until a click
    lands, then returns frame_after."""

    def __init__(self, frame_main, frame_before, frame_after):
        super().__init__(frame_main)
        self.before = frame_before
        self.after = frame_after
        self.clicked = False
        self.verify_capture_size = (
            frame_before.shape[1], frame_before.shape[0])

    def __call__(self, rect: ScreenRect):
        self.capture_calls.append(rect)
        if (rect.w, rect.h) == self.verify_capture_size:
            return self.after if self.clicked else self.before
        return self.frame

    def click(self, x=None, y=None, **kw):
        super().click(x, y, **kw)
        self.clicked = True


def _build_ops_with_verify(template, before, after):
    main = _embed(template, at=(50, 70))
    backend = _ChangingBackend(main, before, after)
    window = WindowGeometry.identity()
    loader = TemplateLoader(prefilled={"path/to/Confirm.png": template})
    finder = Finder(window=window, backend=backend, loader=loader)
    mouse = Mouse(window=window, backend=backend)
    verifier = Verifier(finder=finder, mouse=mouse, sleep=lambda _: None)
    ops = Ops(
        finder, mouse, verifier,
        template_resolver=_fake_template_resolver,
        region_resolver=_fake_region_resolver,
    )
    return ops, backend


def test_click_with_verify_passes_on_change():
    template = _checker()
    before = _solid(40, 50, (100, 100, 100))
    after = _solid(40, 50, (200, 50, 50))
    ops, backend = _build_ops_with_verify(template, before, after)
    ok = ops.click("Confirm", conf=0.95, timeout=1.0,
                   verify="result", change_threshold=0.95)
    assert ok is True


def test_click_with_verify_string_bang_resolves_to_region():
    template = _checker()
    before = _solid(40, 50, (100, 100, 100))
    after = _solid(40, 50, (200, 50, 50))
    ops, backend = _build_ops_with_verify(template, before, after)
    ok = ops.click("Confirm", conf=0.95, timeout=1.0,
                   verify="result!", change_threshold=0.95)
    assert ok is True


# ------------------------------------------------------------ wait_gone

class _TimedBackend(_Backend):
    """Returns frame_with for N capture calls, then frame_without."""

    def __init__(self, frame_with, frame_without, switch_after: int = 2):
        super().__init__(frame_with)
        self.without = frame_without
        self.switch_after = switch_after
        self.n = 0

    def __call__(self, rect):
        self.n += 1
        self.capture_calls.append(rect)
        return self.frame if self.n <= self.switch_after else self.without


def test_wait_gone_returns_true_when_template_disappears():
    template = _checker()
    frame_with = _embed(template, at=(50, 70))
    frame_without = _solid(200, 300, (12, 12, 12))
    backend = _TimedBackend(frame_with, frame_without, switch_after=2)
    window = WindowGeometry.identity()
    loader = TemplateLoader(prefilled={"path/to/Confirm.png": template})
    finder = Finder(window=window, backend=backend, loader=loader)
    mouse = Mouse(window=window, backend=backend)
    verifier = Verifier(finder=finder, mouse=mouse, sleep=lambda _: None)
    ops = Ops(
        finder, mouse, verifier,
        template_resolver=_fake_template_resolver,
        region_resolver=_fake_region_resolver,
    )
    assert ops.wait_gone("Confirm", conf=0.9, timeout=1, poll=0.1) is True


def test_wait_gone_returns_false_on_timeout():
    template = _checker()
    frame_with = _embed(template, at=(50, 70))
    ops, _ = _build_ops(template, frame_with)
    assert ops.wait_gone("Confirm", conf=0.9, timeout=0.05, poll=0.01) is False


def test_wait_gone_strict_raises_on_timeout():
    template = _checker()
    frame_with = _embed(template, at=(50, 70))
    ops, _ = _build_ops(template, frame_with)
    with pytest.raises(Ops.OpFailure):
        ops.wait_gone("Confirm", conf=0.9, timeout=0.05, poll=0.01, strict=True)


# ----------------------------------------------------------- raw mouse

def test_move_to_routes_through_mouse():
    template = _checker()
    frame = _embed(template, at=(50, 70))
    ops, backend = _build_ops(template, frame)
    ops.move_to((100, 200))
    assert backend.move_calls == [(100, 200, {})]


def test_click_at_routes_through_mouse():
    template = _checker()
    frame = _embed(template, at=(50, 70))
    ops, backend = _build_ops(template, frame)
    ops.click_at((1500, 800))
    assert backend.click_calls == [(1500, 800, {})]


def test_drag_to_routes_through_mouse():
    template = _checker()
    frame = _embed(template, at=(50, 70))
    ops, backend = _build_ops(template, frame)
    ops.drag_to((300, 400))
    assert backend.drag_calls == [(300, 400, {})]


def test_cursor_round_trip_via_mouse():
    template = _checker()
    frame = _embed(template, at=(50, 70))
    ops, _ = _build_ops(template, frame)
    ops.click_at((640, 480))
    assert ops.cursor() == (640, 480)


# ------------------------------------------------------- ops factory

def test_from_pipeline_matches_direct_constructor():
    template = _checker()
    frame = _embed(template, at=(50, 70))
    backend = _Backend(frame)
    window = WindowGeometry.identity()
    loader = TemplateLoader(prefilled={"x": template})
    finder = Finder(window=window, backend=backend, loader=loader)
    mouse = Mouse(window=window, backend=backend)
    verifier = Verifier(finder=finder, mouse=mouse, sleep=lambda _: None)

    a = Ops.from_pipeline(finder, mouse, verifier)
    assert a.finder is finder
    assert a.mouse is mouse
    assert a.verifier is verifier
