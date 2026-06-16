# SPDX-License-Identifier: GPL-3.0-or-later
"""Fixture tests for `src.wbcore.pipeline`.

The adapter shape mirrors `os_windows_backend` / `os_x11_backend`:
both expose `screenshot(region=tuple)`, `moveTo`, `click`, `dragTo`,
and `get_position`. We build a fake module with that exact shape and
verify the adapter routes correctly.
"""
from __future__ import annotations

from types import SimpleNamespace
from typing import Any, Optional

import numpy as np
import pytest

from src.wbcore.input import InputBackend
from src.wbcore.pipeline import BackendAdapter, build_pipeline
from src.wbcore.regionspec import (
    Region,
    ScreenRect,
    WindowGeometry,
)
from src.wbcore.vision import CaptureFn, Finder, TemplateLoader
from src.wbcore.verifier import Verifier
from src.wbcore.input import Mouse


# ---- fake gui module ----------------------------------------------------

class _FakeGui:
    """Shape-compatible with os_windows_backend / os_x11_backend."""

    def __init__(self) -> None:
        self.screenshot_calls: list[tuple[int, int, int, int]] = []
        self.move_calls: list[tuple[int, int, dict]] = []
        self.click_calls: list[
            tuple[Optional[int], Optional[int], dict]
        ] = []
        self.drag_calls: list[tuple[int, int, dict]] = []
        self.cursor: tuple[int, int] = (0, 0)
        # Default screenshot result; tests can override.
        self.frame: np.ndarray = np.zeros((10, 10, 3), dtype=np.uint8)

    def screenshot(self, region=None, **_kw: Any) -> np.ndarray:
        self.screenshot_calls.append(region)
        return self.frame

    def moveTo(self, x: int, y: int, **kw: Any) -> None:
        self.move_calls.append((x, y, kw))
        self.cursor = (x, y)

    def click(
        self,
        x: Optional[int] = None,
        y: Optional[int] = None,
        **kw: Any,
    ) -> None:
        self.click_calls.append((x, y, kw))
        if x is not None and y is not None:
            self.cursor = (x, y)

    def dragTo(self, x: int, y: int, **kw: Any) -> None:
        self.drag_calls.append((x, y, kw))
        self.cursor = (x, y)

    def get_position(self) -> tuple[int, int]:
        return self.cursor


# ---- BackendAdapter as CaptureFn ---------------------------------------

def test_adapter_satisfies_capturefn_protocol():
    adapter = BackendAdapter(_FakeGui())
    # CaptureFn is Callable[[ScreenRect], ndarray]; check callability.
    assert callable(adapter)


def test_adapter_screenshot_unpacks_screenrect_to_tuple():
    gui = _FakeGui()
    adapter = BackendAdapter(gui)
    rect = ScreenRect(x=137, y=91, w=400, h=200)

    out = adapter(rect)

    assert isinstance(out, np.ndarray)
    assert gui.screenshot_calls == [(137, 91, 400, 200)]


def test_adapter_coerces_non_ndarray_to_ndarray():
    gui = _FakeGui()
    # Some backends return mss-style lazy frames. Adapter normalizes.
    gui.frame = [[0, 0, 0]] * 4  # type: ignore[assignment]

    adapter = BackendAdapter(gui)
    out = adapter(ScreenRect(0, 0, 10, 10))

    assert isinstance(out, np.ndarray)


# ---- BackendAdapter as InputBackend ------------------------------------

def test_adapter_satisfies_inputbackend_protocol():
    backend: InputBackend = BackendAdapter(_FakeGui())
    assert hasattr(backend, "move_to")
    assert hasattr(backend, "click")
    assert hasattr(backend, "drag_to")
    assert hasattr(backend, "position")


def test_adapter_move_to_routes_to_gui_moveTo():
    gui = _FakeGui()
    adapter = BackendAdapter(gui)
    adapter.move_to(100, 200, duration=0.5)
    assert gui.move_calls == [(100, 200, {"duration": 0.5})]


def test_adapter_click_routes_to_gui_click():
    gui = _FakeGui()
    adapter = BackendAdapter(gui)
    adapter.click(50, 60, button="right", clicks=2)
    assert gui.click_calls == [(50, 60, {"button": "right", "clicks": 2})]


def test_adapter_click_with_none_passes_through():
    gui = _FakeGui()
    adapter = BackendAdapter(gui)
    adapter.click(None, None)
    assert gui.click_calls == [(None, None, {})]


def test_adapter_drag_to_routes_to_gui_dragTo():
    gui = _FakeGui()
    adapter = BackendAdapter(gui)
    adapter.drag_to(300, 400, duration=0.2)
    assert gui.drag_calls == [(300, 400, {"duration": 0.2})]


def test_adapter_position_routes_to_gui_get_position():
    gui = _FakeGui()
    gui.cursor = (789, 654)
    adapter = BackendAdapter(gui)
    assert adapter.position() == (789, 654)


# ---- build_pipeline ----------------------------------------------------

def test_build_pipeline_returns_correct_types():
    gui = _FakeGui()
    window = WindowGeometry.identity()

    finder, mouse, verifier = build_pipeline(window, gui)

    assert isinstance(finder, Finder)
    assert isinstance(mouse, Mouse)
    assert isinstance(verifier, Verifier)


def test_build_pipeline_shares_one_adapter_between_finder_and_mouse():
    gui = _FakeGui()
    window = WindowGeometry.identity()

    finder, mouse, _verifier = build_pipeline(window, gui)

    # Both backends should be the same BackendAdapter instance, so a
    # single gui module call routes through both vision and input.
    assert finder.backend is mouse.backend
    assert isinstance(finder.backend, BackendAdapter)


def test_build_pipeline_wires_verifier_to_finder_and_mouse():
    gui = _FakeGui()
    window = WindowGeometry.identity()

    finder, mouse, verifier = build_pipeline(window, gui)

    assert verifier.finder is finder
    assert verifier.mouse is mouse


def test_build_pipeline_passes_loader_through():
    gui = _FakeGui()
    window = WindowGeometry.identity()
    custom_loader = TemplateLoader(prefilled={"x": np.zeros((4, 4, 3), dtype=np.uint8)})

    finder, _mouse, _verifier = build_pipeline(
        window, gui, loader=custom_loader,
    )

    assert finder.loader is custom_loader


def test_build_pipeline_passes_on_match_through():
    gui = _FakeGui()
    window = WindowGeometry.identity()
    sink: list = []
    cb = lambda name, box: sink.append((name, box))  # noqa: E731

    finder, _mouse, _verifier = build_pipeline(window, gui, on_match=cb)

    assert finder.on_match is cb


def test_build_pipeline_passes_default_conf_through():
    gui = _FakeGui()
    finder, _mouse, _verifier = build_pipeline(
        WindowGeometry.identity(), gui, default_conf=0.85,
    )
    assert finder.default_conf == 0.85


# ---- end-to-end: click round-trip through the live wiring -------------

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


def test_pipeline_end_to_end_finds_and_clicks_via_fake_gui():
    """Full pipeline + adapter, exercised with a fake gui module.

    Demonstrates the production wiring: one fake gui, one adapter,
    Finder reads from it, Mouse writes to it.
    """
    template = _checker()
    region = Region(x=400, y=200, w=300, h=200)
    cropped = _solid(region.h, region.w, (12, 12, 12))
    th, tw = template.shape[:2]
    cropped[50:50 + th, 70:70 + tw] = template

    gui = _FakeGui()
    gui.frame = cropped  # whatever region is requested, return this

    loader = TemplateLoader(prefilled={"checker": template})

    _finder, _mouse, verifier = build_pipeline(
        WindowGeometry.identity(), gui, loader=loader,
    )

    # Verifier polls finder via adapter.__call__; clicks via adapter.click.
    ok = verifier.click_when_found(
        "checker", region=region, conf=0.95, timeout=1,
    )

    assert ok is True
    # Capture: one screenshot call, region in screen coords.
    assert gui.screenshot_calls == [(400, 200, 300, 200)]
    # Click: at the match center in FHD (=screen, identity window).
    # Match was at (70, 50) in cropped; FHD (470, 250); center (470+16, 250+16).
    assert gui.click_calls == [(486, 266, {})]


def test_pipeline_end_to_end_under_4k_scaling():
    """Same end-to-end test, but with a 2x window. Verifies scaling
    is consistent across Vision capture and Input click."""
    template = _checker()
    region = Region(x=400, y=200, w=300, h=200)
    # Frame from a 2x window: scaled cropped frame, scaled template
    # placement.
    cropped = _solid(region.h * 2, region.w * 2, (12, 12, 12))
    import cv2
    big_t = cv2.resize(template, (template.shape[1] * 2, template.shape[0] * 2),
                        interpolation=cv2.INTER_NEAREST)
    cropped[100:100 + big_t.shape[0], 140:140 + big_t.shape[1]] = big_t

    gui = _FakeGui()
    gui.frame = cropped

    loader = TemplateLoader(prefilled={"checker": template})
    window = WindowGeometry(x=0, y=0, w=3840, h=2160)

    _finder, _mouse, verifier = build_pipeline(window, gui, loader=loader)

    ok = verifier.click_when_found(
        "checker", region=region, conf=0.9, timeout=1,
    )

    assert ok is True
    # Capture region scaled to 2x: (400*2, 200*2, 300*2, 200*2).
    assert gui.screenshot_calls == [(800, 400, 600, 400)]
    # Click center: FHD (470+16, 250+16) = (486, 266). Screen 2x = (972, 532).
    assert gui.click_calls == [(972, 532, {})]
