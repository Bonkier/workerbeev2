# SPDX-License-Identifier: GPL-3.0-or-later
"""Fixture tests for `src.wbcore.verifier`.

Sleep is injected, so the entire suite runs at zero wall time. We use
a `_ScriptedFinder` that returns a pre-programmed sequence of results,
which proves the poll/retry schedule does what it claims without
depending on the real Finder.
"""
from __future__ import annotations

from typing import Any, Optional

import numpy as np
import pytest

from src.wbcore.detection import Match
from src.wbcore.input import InputBackend, Mouse
from src.wbcore.regionspec import Region, WindowGeometry
from src.wbcore.vision import Finder, TemplateLoader
from src.wbcore.verifier import Verifier


# ---- fakes ---------------------------------------------------------------

class _ScriptedFinder:
    """Returns a pre-programmed sequence of Match|None values.

    Each call to `find` consumes one value. Raises if the script runs
    out, so tests fail loudly on schedule mismatches rather than
    masking them with None.
    """

    def __init__(self, results: list[Optional[Match]]):
        self._results = list(results)
        self.find_calls = 0

    def find(self, *_args: Any, **_kwargs: Any) -> Optional[Match]:
        if not self._results:
            raise AssertionError(
                "_ScriptedFinder ran out of programmed results"
            )
        self.find_calls += 1
        return self._results.pop(0)


class _ClockSleep:
    """Records every sleep duration without actually sleeping."""

    def __init__(self) -> None:
        self.calls: list[float] = []

    def __call__(self, seconds: float) -> None:
        self.calls.append(seconds)


class _RecordingInput:
    """Minimal InputBackend fake for testing Verifier.click_when_found."""

    def __init__(self) -> None:
        self.click_calls: list[tuple[Optional[int], Optional[int], dict]] = []
        self.cursor = (0, 0)

    def move_to(self, x: int, y: int, **kw: Any) -> None:
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

    def drag_to(self, x: int, y: int, **kw: Any) -> None:
        self.cursor = (x, y)

    def position(self) -> tuple[int, int]:
        return self.cursor


def _hit(x: int = 100, y: int = 200) -> Match:
    return Match(x=x, y=y, w=40, h=20, confidence=0.99, template_name="t")


# ---- wait_for: success cases ---------------------------------------------

def test_wait_for_returns_first_hit_immediately():
    finder = _ScriptedFinder([_hit()])
    sleep = _ClockSleep()
    verifier = Verifier(finder=finder, sleep=sleep)  # type: ignore[arg-type]

    hit = verifier.wait_for("t", timeout=5, poll=0.1)

    assert hit is not None
    assert finder.find_calls == 1
    assert sleep.calls == []  # no sleep before first attempt


def test_wait_for_polls_until_hit():
    finder = _ScriptedFinder([None, None, _hit()])
    sleep = _ClockSleep()
    verifier = Verifier(finder=finder, sleep=sleep)  # type: ignore[arg-type]

    hit = verifier.wait_for("t", timeout=5, poll=0.1)

    assert hit is not None
    assert finder.find_calls == 3
    # 2 sleeps between 3 attempts.
    assert sleep.calls == [0.1, 0.1]


# ---- wait_for: timeout ---------------------------------------------------

def test_wait_for_times_out_and_returns_none():
    # 50 attempts = 5s / 0.1s. All miss -> None.
    finder = _ScriptedFinder([None] * 50)
    sleep = _ClockSleep()
    verifier = Verifier(finder=finder, sleep=sleep)  # type: ignore[arg-type]

    hit = verifier.wait_for("t", timeout=5, poll=0.1)

    assert hit is None
    assert finder.find_calls == 50
    # 49 sleeps between 50 attempts.
    assert len(sleep.calls) == 49


def test_wait_for_respects_custom_poll_interval():
    # 2 attempts = 1.0s / 0.5s.
    finder = _ScriptedFinder([None, None])
    sleep = _ClockSleep()
    verifier = Verifier(finder=finder, sleep=sleep)  # type: ignore[arg-type]

    hit = verifier.wait_for("t", timeout=1.0, poll=0.5)

    assert hit is None
    assert finder.find_calls == 2
    assert sleep.calls == [0.5]


# ---- wait_for: edge cases ------------------------------------------------

def test_wait_for_zero_timeout_still_attempts_once():
    finder = _ScriptedFinder([_hit()])
    sleep = _ClockSleep()
    verifier = Verifier(finder=finder, sleep=sleep)  # type: ignore[arg-type]

    hit = verifier.wait_for("t", timeout=0, poll=0.1)

    assert hit is not None
    assert finder.find_calls == 1
    assert sleep.calls == []


def test_wait_for_negative_timeout_still_attempts_once():
    finder = _ScriptedFinder([None])
    sleep = _ClockSleep()
    verifier = Verifier(finder=finder, sleep=sleep)  # type: ignore[arg-type]

    hit = verifier.wait_for("t", timeout=-1, poll=0.1)

    assert hit is None
    assert finder.find_calls == 1
    assert sleep.calls == []


def test_wait_for_short_timeout_at_least_one_attempt():
    # timeout 0.05 / poll 0.1 = 0 attempts under int division, but we
    # guarantee at least one.
    finder = _ScriptedFinder([_hit()])
    sleep = _ClockSleep()
    verifier = Verifier(finder=finder, sleep=sleep)  # type: ignore[arg-type]

    hit = verifier.wait_for("t", timeout=0.05, poll=0.1)

    assert hit is not None
    assert finder.find_calls == 1


# ---- wait_for: argument forwarding ---------------------------------------

class _ArgRecordingFinder:
    """Records the args of every find() call."""

    def __init__(self, result: Optional[Match] = None):
        self.result = result
        self.calls: list[tuple[tuple, dict]] = []

    def find(self, *args: Any, **kwargs: Any) -> Optional[Match]:
        self.calls.append((args, kwargs))
        return self.result


def test_wait_for_passes_region_conf_load_kwargs_to_finder():
    finder = _ArgRecordingFinder(result=_hit())
    verifier = Verifier(finder=finder, sleep=_ClockSleep())  # type: ignore[arg-type]
    region = Region(10, 20, 100, 100)

    verifier.wait_for(
        "name.png",
        region=region,
        conf=0.85,
        timeout=1,
        poll=0.1,
        comp=0.94,
    )

    args, kwargs = finder.calls[0]
    assert args[0] == "name.png"
    assert kwargs["region"] == region
    assert kwargs["conf"] == 0.85
    assert kwargs["comp"] == 0.94


# ---- click_when_found ----------------------------------------------------

def _mouse_with_recorder() -> tuple[Mouse, _RecordingInput]:
    backend = _RecordingInput()
    return Mouse(WindowGeometry.identity(), backend), backend


def test_click_when_found_clicks_match_center_on_hit():
    mouse, backend = _mouse_with_recorder()
    finder = _ScriptedFinder([_hit(x=100, y=200)])
    verifier = Verifier(
        finder=finder, mouse=mouse, sleep=_ClockSleep(),  # type: ignore[arg-type]
    )

    ok = verifier.click_when_found("t", timeout=5)

    assert ok is True
    # Hit center = (100 + 40//2, 200 + 20//2) = (120, 210).
    assert backend.click_calls == [(120, 210, {})]


def test_click_when_found_returns_false_on_timeout_without_clicking():
    mouse, backend = _mouse_with_recorder()
    finder = _ScriptedFinder([None] * 50)
    verifier = Verifier(
        finder=finder, mouse=mouse, sleep=_ClockSleep(),  # type: ignore[arg-type]
    )

    ok = verifier.click_when_found("t", timeout=5)

    assert ok is False
    assert backend.click_calls == []


def test_click_when_found_uses_click_at_override():
    mouse, backend = _mouse_with_recorder()
    finder = _ScriptedFinder([_hit(x=999, y=999)])
    verifier = Verifier(
        finder=finder, mouse=mouse, sleep=_ClockSleep(),  # type: ignore[arg-type]
    )

    ok = verifier.click_when_found("t", click_at=(1690, 897), timeout=5)

    assert ok is True
    # Click target is the override, not hit.center.
    assert backend.click_calls == [(1690, 897, {})]


def test_click_when_found_forwards_tsize_with_scaling():
    backend = _RecordingInput()
    mouse = Mouse(WindowGeometry(x=0, y=0, w=3840, h=2160), backend)  # 2x
    finder = _ScriptedFinder([_hit(x=100, y=100)])
    verifier = Verifier(
        finder=finder, mouse=mouse, sleep=_ClockSleep(),  # type: ignore[arg-type]
    )

    ok = verifier.click_when_found("t", timeout=5, tsize=(5, 5))

    assert ok is True
    # FHD center (120, 110) -> 2x screen (240, 220); tsize doubles.
    x, y, kw = backend.click_calls[0]
    assert (x, y) == (240, 220)
    assert kw == {"tsize": (10, 10)}


def test_click_when_found_without_mouse_raises():
    finder = _ScriptedFinder([_hit()])
    verifier = Verifier(finder=finder, sleep=_ClockSleep())  # type: ignore[arg-type]
    with pytest.raises(RuntimeError):
        verifier.click_when_found("t", timeout=1)


# ---- integration with real Finder + injected backends -------------------

def _solid(h, w, color):
    img = np.zeros((h, w, 3), dtype=np.uint8)
    img[:, :] = color
    return img


def _checker(size=32, tile=4):
    img = np.zeros((size, size, 3), dtype=np.uint8)
    for y in range(0, size, tile):
        for x in range(0, size, tile):
            if ((x // tile) + (y // tile)) % 2 == 0:
                img[y:y + tile, x:x + tile] = (255, 255, 255)
    return img


def test_verifier_with_real_finder_clicks_real_match():
    template = _checker()
    region = Region(x=400, y=200, w=300, h=200)
    cropped = _solid(region.h, region.w, (12, 12, 12))
    th, tw = template.shape[:2]
    cropped[50:50 + th, 70:70 + tw] = template

    finder = Finder(
        window=WindowGeometry.identity(),
        backend=lambda _rect: cropped,
        loader=TemplateLoader(prefilled={"c": template}),
    )
    input_backend = _RecordingInput()
    mouse = Mouse(WindowGeometry.identity(), input_backend)

    verifier = Verifier(
        finder=finder, mouse=mouse, sleep=_ClockSleep(),  # type: ignore[arg-type]
    )

    ok = verifier.click_when_found("c", region=region, conf=0.95, timeout=1)

    assert ok is True
    # Template at (70, 50) in cropped; FHD = (470, 250); center = (470+16, 250+16).
    assert input_backend.click_calls == [(486, 266, {})]
