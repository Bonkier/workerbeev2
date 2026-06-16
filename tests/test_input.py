# SPDX-License-Identifier: GPL-3.0-or-later
"""Fixture tests for `src.wbcore.input`.

Pure FHD-to-screen translation through Mouse, exercised against a
RecordingInputBackend that satisfies the InputBackend protocol. No
display, no mouse driver, no pyautogui.
"""
from __future__ import annotations

from typing import Any, Optional

import pytest

from src.wbcore.input import InputBackend, Mouse
from src.wbcore.regionspec import WindowGeometry


class _RecordingBackend:
    """Recording fake satisfying InputBackend.

    Cursor position is a writable attribute so tests can simulate
    backend-side movement.
    """

    def __init__(self, cursor: tuple[int, int] = (0, 0)):
        self.cursor = cursor
        self.move_calls: list[tuple[int, int, dict[str, Any]]] = []
        self.click_calls: list[
            tuple[Optional[int], Optional[int], dict[str, Any]]
        ] = []
        self.drag_calls: list[tuple[int, int, dict[str, Any]]] = []

    def move_to(self, x: int, y: int, **kwargs: Any) -> None:
        self.move_calls.append((x, y, kwargs))
        self.cursor = (x, y)

    def click(
        self,
        x: Optional[int] = None,
        y: Optional[int] = None,
        **kwargs: Any,
    ) -> None:
        self.click_calls.append((x, y, kwargs))
        if x is not None and y is not None:
            self.cursor = (x, y)

    def drag_to(self, x: int, y: int, **kwargs: Any) -> None:
        self.drag_calls.append((x, y, kwargs))
        self.cursor = (x, y)

    def position(self) -> tuple[int, int]:
        return self.cursor


# Sanity: the fake actually satisfies the protocol at type level.
def test_recording_backend_satisfies_protocol():
    backend: InputBackend = _RecordingBackend()
    assert hasattr(backend, "move_to")
    assert hasattr(backend, "click")
    assert hasattr(backend, "drag_to")
    assert hasattr(backend, "position")


# ---- identity window -----------------------------------------------------

def test_click_at_identity_window_passes_fhd_through():
    backend = _RecordingBackend()
    mouse = Mouse(WindowGeometry.identity(), backend)
    mouse.click((1315, 818))
    assert backend.click_calls == [(1315, 818, {})]


def test_click_with_offset_window_adds_origin():
    backend = _RecordingBackend()
    window = WindowGeometry(x=137, y=91, w=1920, h=1080)
    mouse = Mouse(window, backend)
    mouse.click((100, 200))
    assert backend.click_calls == [(237, 291, {})]


def test_click_with_no_point_passes_none():
    """Legacy `win_click()` with no args == click at current cursor."""
    backend = _RecordingBackend()
    mouse = Mouse(WindowGeometry.identity(), backend)
    mouse.click()
    assert backend.click_calls == [(None, None, {})]


# ---- scaled windows ------------------------------------------------------

def test_click_at_4k_window_scales_point():
    backend = _RecordingBackend()
    window = WindowGeometry(x=0, y=0, w=3840, h=2160)  # 2x scale
    mouse = Mouse(window, backend)
    mouse.click((100, 50))
    assert backend.click_calls == [(200, 100, {})]


def test_click_at_half_window_halves_point():
    backend = _RecordingBackend()
    window = WindowGeometry(x=0, y=0, w=960, h=540)  # 0.5x scale
    mouse = Mouse(window, backend)
    mouse.click((1000, 500))
    assert backend.click_calls == [(500, 250, {})]


# ---- tsize scaling -------------------------------------------------------

def test_tsize_scales_with_window_at_identity():
    backend = _RecordingBackend()
    mouse = Mouse(WindowGeometry.identity(), backend)
    mouse.click((100, 100), tsize=(5, 5))
    x, y, kw = backend.click_calls[0]
    assert (x, y) == (100, 100)
    assert kw == {"tsize": (5, 5)}


def test_tsize_scales_with_window_at_4k():
    backend = _RecordingBackend()
    window = WindowGeometry(x=0, y=0, w=3840, h=2160)
    mouse = Mouse(window, backend)
    mouse.click((100, 100), tsize=(5, 5))
    x, y, kw = backend.click_calls[0]
    assert (x, y) == (200, 200)
    assert kw == {"tsize": (10, 10)}


def test_tsize_none_is_passed_through_unchanged():
    backend = _RecordingBackend()
    mouse = Mouse(WindowGeometry.identity(), backend)
    mouse.click((100, 100), tsize=None)
    _, _, kw = backend.click_calls[0]
    assert kw == {"tsize": None}


# ---- other actions -------------------------------------------------------

def test_move_to_translates_point():
    backend = _RecordingBackend()
    window = WindowGeometry(x=200, y=100, w=1920, h=1080)
    mouse = Mouse(window, backend)
    mouse.move_to((50, 60))
    assert backend.move_calls == [(250, 160, {})]


def test_drag_to_translates_point():
    backend = _RecordingBackend()
    window = WindowGeometry(x=200, y=100, w=1920, h=1080)
    mouse = Mouse(window, backend)
    mouse.drag_to((50, 60))
    assert backend.drag_calls == [(250, 160, {})]


def test_move_to_passes_extra_kwargs():
    backend = _RecordingBackend()
    mouse = Mouse(WindowGeometry.identity(), backend)
    mouse.move_to((10, 20), duration=0.5)
    _, _, kw = backend.move_calls[0]
    assert kw == {"duration": 0.5}


# ---- position ------------------------------------------------------------

def test_position_translates_back_to_fhd():
    # Backend reports screen coords; Mouse returns FHD.
    window = WindowGeometry(x=137, y=91, w=1920, h=1080)
    backend = _RecordingBackend(cursor=(237, 291))
    mouse = Mouse(window, backend)
    assert mouse.position() == (100, 200)


def test_position_round_trip_through_click():
    """Click at FHD point, read it back; should match FHD input."""
    window = WindowGeometry(x=137, y=91, w=1920, h=1080)
    backend = _RecordingBackend()
    mouse = Mouse(window, backend)
    mouse.click((640, 480))
    assert mouse.position() == (640, 480)


def test_position_round_trip_at_4k():
    window = WindowGeometry(x=400, y=200, w=3840, h=2160)
    backend = _RecordingBackend()
    mouse = Mouse(window, backend)
    mouse.click((123, 456))
    # 2x scale: screen coord is (646, 1112). Back to FHD: (123, 456).
    assert mouse.position() == (123, 456)


# ---- kwargs preservation -------------------------------------------------

def test_unrelated_kwargs_survive():
    backend = _RecordingBackend()
    mouse = Mouse(WindowGeometry.identity(), backend)
    mouse.click((10, 20), button="right", clicks=2, tsize=(3, 3))
    x, y, kw = backend.click_calls[0]
    assert (x, y) == (10, 20)
    assert kw == {"button": "right", "clicks": 2, "tsize": (3, 3)}
