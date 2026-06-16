# SPDX-License-Identifier: GPL-3.0-or-later
"""Verify the legacy `Locate*` / `win_*` / `screenshot` surface in
`utils.utils` now routes through the SOLID pipeline.

The legacy entry points are still defined but their implementations
are shims. These tests inject a fake `gui` module and a fake
`p.WINDOW` so the pipeline resolves to known fakes, then call the
legacy names and assert the new pipeline got the call.

This proves: bot.py / battle.py / etc. continue to compile, the
legacy spelling continues to work at call sites, and the new SOLID
pipeline is the engine underneath.
"""
from __future__ import annotations

import sys
import types
from typing import Any, Optional

import numpy as np
import pytest


# ---------- fake gui module shape -----------------------------------------

class _FakeGui:
    """os_windows_backend lookalike for the shim layer."""

    class ImageNotFoundException(Exception):
        pass

    def __init__(self) -> None:
        self.screenshot_calls: list = []
        self.click_calls: list = []
        self.move_calls: list = []
        self.drag_calls: list = []
        self.cursor: tuple[int, int] = (0, 0)
        self.frame: Optional[np.ndarray] = None  # what screenshot returns
        # `gui.center` is used by legacy LocatePreset.try_find; mirror it.
    @staticmethod
    def center(box):
        x, y, w, h = box
        return (x + w // 2, y + h // 2)

    def screenshot(self, imageFilename=None, region=None, **kw: Any):
        self.screenshot_calls.append(region)
        return self.frame if self.frame is not None else np.zeros((10, 10, 3), dtype=np.uint8)

    def moveTo(self, x, y, **kw):
        self.move_calls.append((x, y, kw))
        self.cursor = (x, y)

    def click(self, x=None, y=None, **kw):
        self.click_calls.append((x, y, kw))
        if x is not None and y is not None:
            self.cursor = (x, y)

    def dragTo(self, x, y, **kw):
        self.drag_calls.append((x, y, kw))
        self.cursor = (x, y)

    def get_position(self):
        return self.cursor

    def getActiveWindowTitle(self):
        return "Limbus Company"


# ---------- fixture: a hot-swapped utils.utils that uses a fake gui ------

@pytest.fixture
def shim_env(monkeypatch):
    """Install a fake gui + p.WINDOW so the lazy `_pipeline()` resolves.

    Returns `(utils_module, fake_gui)`. The fake gui's call recorders
    are how tests assert the new pipeline routed work to it.
    """
    # Defer imports so we hit the monkeypatched modules.
    from src.wbcore.utils import utils as utils_mod
    from src.wbcore.utils import params as p_mod

    # Drop any cached pipeline so it rebuilds against our fakes.
    utils_mod._reset_pipeline_cache()

    fake_gui = _FakeGui()
    monkeypatch.setattr(utils_mod, "gui", fake_gui)
    monkeypatch.setattr(p_mod, "WINDOW", (137, 91, 1920, 1080))

    yield utils_mod, fake_gui

    utils_mod._reset_pipeline_cache()


# ---------- screenshot ---------------------------------------------------

def test_screenshot_routes_through_capture(shim_env):
    utils_mod, fake_gui = shim_env
    fake_gui.frame = np.ones((50, 100, 3), dtype=np.uint8)
    out = utils_mod.screenshot(region=(200, 300, 100, 50))

    assert isinstance(out, np.ndarray)
    # Pipeline path: gui.screenshot is called once with a tuple in screen px.
    assert len(fake_gui.screenshot_calls) == 1
    rect = fake_gui.screenshot_calls[0]
    # Identity window: region origin offset by p.WINDOW (137, 91).
    assert rect == (337, 391, 100, 50)


# ---------- win_* mouse helpers -----------------------------------------

def test_win_click_routes_through_mouse(shim_env):
    utils_mod, fake_gui = shim_env
    utils_mod.win_click((100, 200))
    assert fake_gui.click_calls == [(237, 291, {})]


def test_win_click_no_args_clicks_in_place(shim_env):
    utils_mod, fake_gui = shim_env
    utils_mod.win_click()
    assert fake_gui.click_calls == [(None, None, {})]


def test_win_click_two_positional_args(shim_env):
    utils_mod, fake_gui = shim_env
    utils_mod.win_click(100, 200)
    assert fake_gui.click_calls == [(237, 291, {})]


def test_win_moveTo_routes_through_mouse(shim_env):
    utils_mod, fake_gui = shim_env
    utils_mod.win_moveTo((50, 60))
    assert fake_gui.move_calls == [(187, 151, {})]


def test_win_dragTo_routes_through_mouse(shim_env):
    utils_mod, fake_gui = shim_env
    utils_mod.win_dragTo((50, 60))
    assert fake_gui.drag_calls == [(187, 151, {})]


def test_win_get_position_translates_back_to_fhd(shim_env):
    utils_mod, fake_gui = shim_env
    fake_gui.cursor = (237, 291)
    assert utils_mod.win_get_position() == (100, 200)


# ---------- Locate* class shims -----------------------------------------

def _checker(size=32, tile=4):
    img = np.zeros((size, size, 3), dtype=np.uint8)
    for y in range(0, size, tile):
        for x in range(0, size, tile):
            if ((x // tile) + (y // tile)) % 2 == 0:
                img[y:y + tile, x:x + tile] = (255, 255, 255)
    return img


def test_LocateRGB_locate_returns_legacy_tuple(shim_env):
    utils_mod, fake_gui = shim_env
    template = _checker()
    # Embed the template in a frame the fake gui will return.
    h, w = template.shape[:2]
    frame = np.zeros((100, 200, 3), dtype=np.uint8)
    frame[20:20 + h, 40:40 + w] = template
    fake_gui.frame = frame

    result = utils_mod.LocateRGB.locate(template, region=(0, 0, 200, 100), conf=0.95)

    assert result is not None
    # Legacy returns (x, y, w, h) tuple.
    assert isinstance(result, tuple) and len(result) == 4
    assert result[0] == 40 and result[1] == 20


def test_LocateGray_locate_uses_gray_color_mode(shim_env):
    utils_mod, fake_gui = shim_env
    template = _checker()
    h, w = template.shape[:2]
    frame = np.zeros((100, 200, 3), dtype=np.uint8)
    frame[20:20 + h, 40:40 + w] = template
    fake_gui.frame = frame

    # Gray-mode locate should still find the synthetic checker.
    result = utils_mod.LocateGray.locate(template, region=(0, 0, 200, 100), conf=0.95)
    assert result is not None
    assert result[0] == 40 and result[1] == 20


def test_LocateRGB_locate_all_returns_legacy_list(shim_env):
    utils_mod, fake_gui = shim_env
    template = _checker(size=16, tile=4)
    th, tw = template.shape[:2]
    frame = np.zeros((150, 250, 3), dtype=np.uint8)
    for (y, x) in [(20, 30), (100, 180)]:
        frame[y:y + th, x:x + tw] = template
    fake_gui.frame = frame

    results = utils_mod.LocateRGB.locate_all(template, region=(0, 0, 250, 150), conf=0.95)
    assert len(results) == 2
    # Every entry is a 4-tuple, not a Match.
    for r in results:
        assert isinstance(r, tuple) and len(r) == 4


def test_LocateRGB_try_locate_raises_on_miss(shim_env):
    utils_mod, fake_gui = shim_env
    template = _checker()
    fake_gui.frame = np.zeros((100, 200, 3), dtype=np.uint8)  # template absent

    with pytest.raises(fake_gui.ImageNotFoundException):
        utils_mod.LocateRGB.try_locate(template, region=(0, 0, 200, 100), conf=0.99)


def test_LocateRGB_check_no_click_returns_bool(shim_env):
    utils_mod, fake_gui = shim_env
    template = _checker()
    h, w = template.shape[:2]
    frame = np.zeros((100, 200, 3), dtype=np.uint8)
    frame[20:20 + h, 40:40 + w] = template
    fake_gui.frame = frame

    result = utils_mod.LocateRGB.check(
        template, region=(0, 0, 200, 100), conf=0.95, wait=False,
    )
    assert result is True


def test_LocateRGB_check_with_click_calls_gui_click(shim_env):
    utils_mod, fake_gui = shim_env
    template = _checker()
    h, w = template.shape[:2]
    frame = np.zeros((100, 200, 3), dtype=np.uint8)
    frame[20:20 + h, 40:40 + w] = template
    fake_gui.frame = frame

    result = utils_mod.LocateRGB.check(
        template, region=(0, 0, 200, 100), conf=0.95, wait=False, click=True,
    )
    assert result is True
    # gui.click was called once by the shim -> Mouse -> BackendAdapter.
    assert len(fake_gui.click_calls) == 1


def test_LocateRGB_check_error_raises_on_miss(shim_env):
    utils_mod, fake_gui = shim_env
    template = _checker()
    fake_gui.frame = np.zeros((100, 200, 3), dtype=np.uint8)  # template absent

    with pytest.raises(RuntimeError, match="needs debugging"):
        utils_mod.LocateRGB.check(
            template, region=(0, 0, 200, 100), conf=0.99,
            wait=False, error=True,
        )


def test_pipeline_unset_window_falls_back_to_legacy_win_click(monkeypatch):
    """If `p.WINDOW` is None, shim fallback path runs the legacy math."""
    from src.wbcore.utils import utils as utils_mod
    from src.wbcore.utils import params as p_mod

    utils_mod._reset_pipeline_cache()
    fake_gui = _FakeGui()
    monkeypatch.setattr(utils_mod, "gui", fake_gui)
    monkeypatch.setattr(p_mod, "WINDOW", None)

    # Pipeline build will fail; win_click should fall back.
    with pytest.raises(TypeError):
        # Legacy fallback dereferences p.WINDOW[2] which is None[2] -> TypeError.
        utils_mod.win_click((100, 200))


def test_pipeline_cache_reused_across_calls(shim_env):
    """Calling _pipeline() repeatedly should hit the cache."""
    utils_mod, _ = shim_env
    pl1 = utils_mod._pipeline()
    pl2 = utils_mod._pipeline()
    assert pl1 is pl2


def test_pipeline_reset_invalidates_cache(shim_env):
    utils_mod, _ = shim_env
    pl1 = utils_mod._pipeline()
    utils_mod._reset_pipeline_cache()
    pl2 = utils_mod._pipeline()
    assert pl1 is not pl2
