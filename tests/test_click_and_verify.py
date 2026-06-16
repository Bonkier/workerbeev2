# SPDX-License-Identifier: GPL-3.0-or-later
"""Tests for `Verifier.click_and_verify` and `CallSite.button`.

The flow snapshots a region before clicking and watches it for change.
A fake CaptureFn returns different frames on successive calls to
simulate the screen changing post-click.
"""
from __future__ import annotations

from typing import Any, Optional

import numpy as np
import pytest

from src.wbcore.callsite import CallSite
from src.wbcore.detection import Match
from src.wbcore.input import Mouse
from src.wbcore.regionspec import Region, ScreenRect, WindowGeometry
from src.wbcore.verifier import Verifier
from src.wbcore.vision import Finder, TemplateLoader


# ---- shared fakes -------------------------------------------------------

class _MultiFrameBackend:
    """CaptureFn + InputBackend with a programmable frame sequence. With
    `change_on_click=True`, verify-region snapshots return `frame_before`
    until a click lands, then `frame_after`; otherwise they stay on
    `frame_before` to simulate a no-effect click."""

    def __init__(
        self,
        frame_main: np.ndarray,
        frame_before: np.ndarray,
        frame_after: Optional[np.ndarray] = None,
        change_on_click: bool = True,
    ):
        self.frame_main = frame_main          # for finder.find calls
        self.frame_before = frame_before      # for verify snapshot pre-click
        self.frame_after = (
            frame_after if frame_after is not None else frame_before
        )
        self.change_on_click = change_on_click
        self.clicked = False
        self.capture_calls: list = []
        self.click_calls: list = []

    def __call__(self, rect: ScreenRect) -> np.ndarray:
        self.capture_calls.append(rect)
        # Main-frame-sized rect == finder call; smaller == verify snapshot.
        if (rect.w, rect.h) == (self.frame_main.shape[1], self.frame_main.shape[0]):
            return self.frame_main
        if self.change_on_click and self.clicked:
            return self.frame_after
        return self.frame_before

    def move_to(self, x, y, **kw):
        pass

    def click(self, x=None, y=None, **kw):
        self.click_calls.append((x, y, kw))
        self.clicked = True

    def drag_to(self, x, y, **kw):
        pass

    def position(self):
        return (0, 0)


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


def _frame_with(template, at, frame_size=(200, 300)):
    h, w = frame_size
    frame = _solid(h, w, (12, 12, 12))
    th, tw = template.shape[:2]
    y, x = at
    frame[y:y + th, x:x + tw] = template
    return frame


# ---- Verifier.click_and_verify -----------------------------------------

def _build_verifier(template, before, after=None, change_on_click=True):
    """Construct a real Verifier + Finder wired to the multi-frame backend.

    `template` is the template to find. `before` and `after` are the
    verify-region frames pre- and post-click respectively.
    """
    main_frame = _frame_with(template, at=(50, 70), frame_size=(200, 300))

    backend = _MultiFrameBackend(
        frame_main=main_frame,
        frame_before=before,
        frame_after=after,
        change_on_click=change_on_click,
    )
    window = WindowGeometry.identity()
    loader = TemplateLoader(prefilled={"t": template})
    finder = Finder(window=window, backend=backend, loader=loader)
    mouse = Mouse(window=window, backend=backend)
    verifier = Verifier(
        finder=finder, mouse=mouse, sleep=lambda _: None,  # type: ignore[arg-type]
    )
    return verifier, backend


def test_click_and_verify_success_on_first_attempt():
    """Snapshot taken, click happens, post-click region differs -> verified."""
    template = _checker()
    before = _solid(40, 50, (100, 100, 100))  # uniform pre-click region
    after = _solid(40, 50, (200, 50, 50))      # different post-click

    verifier, backend = _build_verifier(template, before, after)

    ok = verifier.click_and_verify(
        "t",
        verify_region=Region(0, 0, 50, 40),
        region=Region(400, 200, 300, 200),
        conf=0.95,
        timeout=1,
        verify_timeout=1,
        verify_poll=0.1,
        change_threshold=0.95,
    )

    assert ok is True
    # Exactly one click landed.
    assert len(backend.click_calls) == 1


def test_click_and_verify_retries_on_no_change():
    """Region stays the same -> no-effect -> retry click. After N
    retries we give up and raise."""
    template = _checker()
    before = _solid(40, 50, (100, 100, 100))
    # change_on_click=False: verify region NEVER changes post-click.
    verifier, backend = _build_verifier(
        template, before, after=before, change_on_click=False,
    )

    with pytest.raises(RuntimeError, match="verification failed"):
        verifier.click_and_verify(
            "t",
            verify_region=Region(0, 0, 50, 40),
            region=Region(400, 200, 300, 200),
            conf=0.95,
            timeout=1,
            verify_timeout=0.5,
            verify_poll=0.1,
            max_retries=2,
            change_threshold=0.95,
        )

    # We clicked once per retry, so max_retries clicks total.
    assert len(backend.click_calls) == 2


def test_click_and_verify_returns_false_when_template_not_found():
    """Initial find misses entirely -> no clicks, no verification, return False."""
    template = _checker()
    backend = _MultiFrameBackend(
        frame_main=_solid(200, 300, (0, 0, 0)),       # template absent
        frame_before=_solid(40, 50, (0, 0, 0)),
    )
    window = WindowGeometry.identity()
    finder = Finder(
        window=window, backend=backend,
        loader=TemplateLoader(prefilled={"t": template}),
    )
    mouse = Mouse(window=window, backend=backend)
    verifier = Verifier(
        finder=finder, mouse=mouse, sleep=lambda _: None,  # type: ignore[arg-type]
    )

    ok = verifier.click_and_verify(
        "t",
        verify_region=Region(0, 0, 50, 40),
        region=Region(0, 0, 300, 200),
        conf=0.99,
        timeout=0.5,
        verify_timeout=0.2,
    )
    assert ok is False
    assert backend.click_calls == []


def test_click_and_verify_without_mouse_raises():
    template = _checker()
    backend = _MultiFrameBackend(
        frame_main=_frame_with(template, at=(50, 70)),
        frame_before=_solid(40, 50, (100, 100, 100)),
    )
    window = WindowGeometry.identity()
    finder = Finder(
        window=window, backend=backend,
        loader=TemplateLoader(prefilled={"t": template}),
    )
    verifier = Verifier(
        finder=finder, mouse=None, sleep=lambda _: None,  # type: ignore[arg-type]
    )
    with pytest.raises(RuntimeError, match="requires a Mouse"):
        verifier.click_and_verify(
            "t", verify_region=Region(0, 0, 50, 40), region=Region(0, 0, 300, 200),
        )


def test_click_and_verify_accepts_tuple_verify_region():
    """verify_region as a 4-tuple should be coerced via Region.coerce."""
    template = _checker()
    before = _solid(40, 50, (100, 100, 100))
    after = _solid(40, 50, (200, 50, 50))
    verifier, backend = _build_verifier(template, before, after)

    ok = verifier.click_and_verify(
        "t",
        verify_region=(0, 0, 50, 40),  # tuple, not Region
        region=(400, 200, 300, 200),
        conf=0.95,
        timeout=1,
        verify_timeout=1,
        change_threshold=0.95,
    )
    assert ok is True


# ---- CallSite.button bridge --------------------------------------------

def _fake_template_resolver(name: str):
    return f"path/to/{name.split('.')[0]}.png"


def _fake_region_resolver(name: str):
    table = {
        "Confirm": Region(400, 200, 300, 200),
        "result_panel": Region(0, 0, 50, 40),
        "result_panel!": Region(0, 0, 50, 40),
    }
    return table.get(name)


def _build_cs(template, before, after=None, change_on_click=True, action="click"):
    main_frame = _frame_with(template, at=(50, 70), frame_size=(200, 300))
    backend = _MultiFrameBackend(
        frame_main=main_frame, frame_before=before,
        frame_after=after, change_on_click=change_on_click,
    )
    window = WindowGeometry.identity()
    finder = Finder(
        window=window, backend=backend,
        loader=TemplateLoader(prefilled={"path/to/Confirm.png": template}),
    )
    mouse = Mouse(window=window, backend=backend)
    verifier = Verifier(
        finder=finder, mouse=mouse, sleep=lambda _: None,  # type: ignore[arg-type]
    )
    cs = CallSite(
        finder=finder, mouse=mouse, verifier=verifier,
        action=action,
        template_resolver=_fake_template_resolver,
        region_resolver=_fake_region_resolver,
        timeout=1, poll=0.1,
    )
    return cs, backend


def test_button_no_ver_delegates_to_click_when_action_is_click():
    template = _checker()
    before = _solid(40, 50, (100, 100, 100))
    cs, backend = _build_cs(template, before, action="click")
    ok = cs.button("Confirm")
    assert ok is True
    assert len(backend.click_calls) == 1


def test_button_no_ver_returns_truthy_match_when_action_is_find():
    template = _checker()
    before = _solid(40, 50, (100, 100, 100))
    cs, backend = _build_cs(template, before, action="find")
    # Set timeout to 0 to take the find (no wait) path.
    cs_find = cs(wait=False)
    result = cs_find.button("Confirm")
    assert bool(result)
    assert backend.click_calls == []   # find-only does not click


def test_button_with_ver_runs_click_and_verify_success():
    template = _checker()
    before = _solid(40, 50, (100, 100, 100))
    after = _solid(40, 50, (200, 50, 50))
    cs, backend = _build_cs(template, before, after, action="click")

    ok = cs.button(
        "Confirm",
        ver=(0, 0, 50, 40),
    )
    assert ok is True


def test_button_with_ver_string_lookup_in_REGIONS():
    """ver='result_panel' resolves via the region_resolver."""
    template = _checker()
    before = _solid(40, 50, (100, 100, 100))
    after = _solid(40, 50, (200, 50, 50))
    cs, backend = _build_cs(template, before, after, action="click")

    ok = cs.button("Confirm", ver="result_panel")
    assert ok is True


def test_button_with_ver_string_bang_suffix_lookup():
    """ver='result_panel!' strips the trailing ! and looks up the same."""
    template = _checker()
    before = _solid(40, 50, (100, 100, 100))
    after = _solid(40, 50, (200, 50, 50))
    cs, backend = _build_cs(template, before, after, action="click")

    ok = cs.button("Confirm", ver="result_panel!")
    assert ok is True


def test_button_ver_unknown_string_raises():
    template = _checker()
    before = _solid(40, 50, (100, 100, 100))
    cs, _ = _build_cs(template, before, action="click")
    with pytest.raises(KeyError):
        cs.button("Confirm", ver="not-a-real-region")


def test_button_ver_unsupported_type_raises():
    template = _checker()
    before = _solid(40, 50, (100, 100, 100))
    cs, _ = _build_cs(template, before, action="click")
    with pytest.raises(TypeError):
        cs.button("Confirm", ver={"not": "a region"})


def test_button_passes_overrides_through():
    """Per-call overrides on `.button(...)` reach the verifier."""
    template = _checker()
    before = _solid(40, 50, (100, 100, 100))
    after = _solid(40, 50, (200, 50, 50))
    cs, backend = _build_cs(template, before, after, action="click")

    ok = cs.button(
        "Confirm", ver=(0, 0, 50, 40),
        conf=0.95,
    )
    assert ok is True
