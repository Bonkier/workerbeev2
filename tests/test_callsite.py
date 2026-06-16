# SPDX-License-Identifier: GPL-3.0-or-later
"""Tests for `src.wbcore.callsite`, using fake Finder/Verifier/Mouse so
they run with zero IO."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional

import numpy as np
import pytest

from src.wbcore.callsite import (
    CallSite,
    CallSiteBundle,
    build_call_sites,
)
from src.wbcore.detection import Match
from src.wbcore.input import Mouse
from src.wbcore.regionspec import Region, WindowGeometry
from src.wbcore.verifier import Verifier
from src.wbcore.vision import Finder, TemplateLoader


# ---- fakes -------------------------------------------------------------

class _RecordingBackend:
    """Both CaptureFn and InputBackend for one fixture."""

    def __init__(self, frame: np.ndarray):
        self.frame = frame
        self.capture_calls: list = []
        self.click_calls: list = []
        self.move_calls: list = []
        self.cursor = (0, 0)

    # CaptureFn
    def __call__(self, rect) -> np.ndarray:
        self.capture_calls.append(rect)
        return self.frame

    # InputBackend
    def move_to(self, x, y, **kw):
        self.move_calls.append((x, y, kw))
        self.cursor = (x, y)

    def click(self, x=None, y=None, **kw):
        self.click_calls.append((x, y, kw))
        if x is not None and y is not None:
            self.cursor = (x, y)

    def drag_to(self, x, y, **kw):
        pass

    def position(self):
        return self.cursor


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


# Custom resolvers so tests don't depend on the live PTH/REGIONS dicts.

def _fake_pth_resolver(name: str):
    # Strip the legacy '.' disambiguator just like the real resolver.
    return f"path/to/{name.split('.')[0]}.png"


def _fake_region_resolver(name: str):
    table = {
        "Confirm": Region(100, 200, 50, 60),
        "Start": Region(0, 0, 1920, 1080),
    }
    return table.get(name)


def _make_pipeline(template: np.ndarray, frame: np.ndarray):
    backend = _RecordingBackend(frame)
    window = WindowGeometry.identity()
    loader = TemplateLoader(
        prefilled={"path/to/Confirm.png": template,
                   "path/to/Start.png": template},
    )
    finder = Finder(window=window, backend=backend, loader=loader)
    mouse = Mouse(window=window, backend=backend)
    verifier = Verifier(
        finder=finder, mouse=mouse, sleep=lambda _: None,  # type: ignore[arg-type]
    )
    return backend, finder, mouse, verifier


def _make_cs(action="find", **kw):
    """Construct a CallSite with fakes injected."""
    backend, finder, mouse, verifier = _make_pipeline(
        _checker(),
        _embed((400, 400), _checker(), at=(220, 110)),
    )
    cs = CallSite(
        finder=finder, mouse=mouse, verifier=verifier,
        action=action,
        template_resolver=_fake_pth_resolver,
        region_resolver=_fake_region_resolver,
        **kw,
    )
    return cs, backend


# ---- override chaining ---------------------------------------------------

def test_override_returns_new_instance():
    cs, _ = _make_cs()
    cs2 = cs(conf=0.85)
    assert cs is not cs2
    assert cs.conf is None
    assert cs2.conf == 0.85


def test_override_click_true_sets_action_to_click():
    cs, _ = _make_cs(action="find")
    cs2 = cs(click=True)
    assert cs2.action == "click"


def test_override_click_false_sets_action_to_find():
    cs, _ = _make_cs(action="click")
    cs2 = cs(click=False)
    assert cs2.action == "find"


def test_override_wait_false_sets_timeout_zero():
    cs, _ = _make_cs()
    cs2 = cs(wait=False)
    assert cs2.timeout == 0.0


def test_override_wait_number_maps_to_timeout():
    cs, _ = _make_cs()
    cs2 = cs(wait=10)
    assert cs2.timeout == 10.0


def test_override_error_maps_to_error_on_miss():
    cs, _ = _make_cs()
    cs2 = cs(error=True)
    assert cs2.error_on_miss is True


def test_unknown_overrides_go_into_load_kwargs():
    """`comp=0.94` is a template-load kwarg, not a CallSite attribute."""
    cs, _ = _make_cs()
    cs2 = cs(comp=0.94, v_comp=0.8)
    assert cs2.load_kwargs == {"comp": 0.94, "v_comp": 0.8}


def test_override_click_tuple_stores_click_at_in_load_kwargs():
    """Legacy click=(x, y) becomes a click_at override."""
    cs, _ = _make_cs()
    cs2 = cs(click=(1690, 897))
    assert cs2.load_kwargs.get("click_at") == (1690, 897)


def test_chained_overrides_merge():
    cs, _ = _make_cs()
    cs2 = cs(conf=0.85)(wait=False)(error=True)
    assert cs2.conf == 0.85
    assert cs2.timeout == 0.0
    assert cs2.error_on_miss is True


# ---- find / wait / click using PTH+REGIONS lookup ----------------------

def test_find_resolves_template_and_region_from_name():
    cs, _ = _make_cs()
    hit = cs.find("Confirm")
    assert hit is not None


def test_find_returns_none_on_miss():
    # Frame without the template.
    backend = _RecordingBackend(_solid(400, 400, (0, 0, 0)))
    window = WindowGeometry.identity()
    loader = TemplateLoader(prefilled={"path/to/Confirm.png": _checker()})
    finder = Finder(window=window, backend=backend, loader=loader)
    verifier = Verifier(finder=finder, sleep=lambda _: None)  # type: ignore[arg-type]

    cs = CallSite(
        finder=finder, verifier=verifier,
        template_resolver=_fake_pth_resolver,
        region_resolver=_fake_region_resolver,
        conf=0.95,
    )
    assert cs.find("Confirm") is None


def test_find_with_error_on_miss_raises():
    backend = _RecordingBackend(_solid(400, 400, (0, 0, 0)))
    window = WindowGeometry.identity()
    loader = TemplateLoader(prefilled={"path/to/Confirm.png": _checker()})
    finder = Finder(window=window, backend=backend, loader=loader)

    cs = CallSite(
        finder=finder,
        template_resolver=_fake_pth_resolver,
        region_resolver=_fake_region_resolver,
        conf=0.95,
        error_on_miss=True,
    )
    with pytest.raises(RuntimeError, match="not found"):
        cs.find("Confirm")


def test_wait_uses_verifier_polling():
    cs, _ = _make_cs(timeout=1.0, poll=0.1)
    hit = cs.wait("Confirm")
    assert hit is not None


def test_wait_without_verifier_raises():
    backend, finder, _mouse, _verifier = _make_pipeline(
        _checker(), _embed((400, 400), _checker(), at=(220, 110)),
    )
    cs = CallSite(
        finder=finder, verifier=None,
        template_resolver=_fake_pth_resolver,
        region_resolver=_fake_region_resolver,
    )
    with pytest.raises(RuntimeError, match="requires a Verifier"):
        cs.wait("Confirm")


def test_click_calls_mouse_at_match_center():
    cs, backend = _make_cs()
    ok = cs.click("Confirm")
    assert ok is True
    assert len(backend.click_calls) == 1


def test_click_without_verifier_raises():
    backend, finder, mouse, _verifier = _make_pipeline(
        _checker(), _embed((400, 400), _checker(), at=(220, 110)),
    )
    cs = CallSite(
        finder=finder, mouse=mouse, verifier=None,
        template_resolver=_fake_pth_resolver,
        region_resolver=_fake_region_resolver,
    )
    with pytest.raises(RuntimeError, match="requires a Verifier"):
        cs.click("Confirm")


def test_click_with_click_at_overrides_target():
    """Legacy click=(x, y) routes to Verifier.click_when_found click_at."""
    cs, backend = _make_cs()
    cs2 = cs(click=(500, 600))
    cs2.click("Confirm")
    x, y, _kw = backend.click_calls[0]
    assert (x, y) == (500, 600)


# ---- name shorthand handles 'Confirm.1' style --------------------------

def test_dotted_name_uses_base_for_template_lookup():
    """`'Confirm.1'` -> template 'Confirm', region 'Confirm.1'."""
    # Region resolver knows 'Confirm' but not 'Confirm.1'; falls through.
    cs, _ = _make_cs()
    hit = cs.find("Confirm.1")  # base name 'Confirm' resolves template
    assert hit is not None


# ---- explicit region override takes precedence -------------------------

def test_explicit_region_overrides_name_lookup():
    cs, backend = _make_cs()
    explicit = Region(50, 60, 100, 100)
    cs.find("Confirm", region=explicit)
    # Capture call's screen rect should match explicit region origin,
    # not the name-lookup origin (100, 200).
    assert backend.capture_calls[0].x == 50
    assert backend.capture_calls[0].y == 60


def test_template_ref_can_be_ndarray_directly():
    """Bypass the PTH lookup by passing an ndarray."""
    backend, finder, mouse, verifier = _make_pipeline(
        _checker(),
        _embed((300, 300), _checker(), at=(120, 80)),
    )
    cs = CallSite(
        finder=finder, mouse=mouse, verifier=verifier,
        template_resolver=_fake_pth_resolver,
        region_resolver=_fake_region_resolver,
    )
    hit = cs.find(_checker())
    assert hit is not None


# ---- build_call_sites bundle -------------------------------------------

def test_bundle_returns_five_named_presets():
    backend, finder, mouse, verifier = _make_pipeline(
        _checker(),
        _embed((300, 300), _checker(), at=(120, 80)),
    )
    bundle = build_call_sites(finder, mouse, verifier)
    assert isinstance(bundle, CallSiteBundle)
    assert isinstance(bundle.loc, CallSite)
    assert bundle.loc.action == "find"
    assert bundle.click.action == "click"
    assert bundle.now.timeout == 0.0
    assert bundle.try_click.action == "click"
    assert bundle.try_click.error_on_miss is True
    assert bundle.now_click.action == "click"
    assert bundle.now_click.timeout == 0.0


def test_bundle_presets_share_pipeline():
    backend, finder, mouse, verifier = _make_pipeline(
        _checker(),
        _embed((300, 300), _checker(), at=(120, 80)),
    )
    bundle = build_call_sites(finder, mouse, verifier)
    assert bundle.loc.finder is finder
    assert bundle.click.finder is finder
    assert bundle.now.finder is finder


def test_default_conf_propagates_into_bundle():
    backend, finder, mouse, verifier = _make_pipeline(
        _checker(),
        _embed((300, 300), _checker(), at=(120, 80)),
    )
    bundle = build_call_sites(finder, mouse, verifier, default_conf=0.85)
    for cs in (bundle.loc, bundle.click, bundle.now,
               bundle.try_click, bundle.now_click):
        assert cs.conf == 0.85


# ---- __getitem__ shorthand ---------------------------------------------

def test_index_dispatches_to_find_when_action_find():
    cs, _ = _make_cs(action="find", timeout=0.0)
    hit = cs["Confirm"]
    assert hit is not None


def test_index_raises_when_action_click():
    cs, _ = _make_cs(action="click")
    with pytest.raises(NotImplementedError):
        _ = cs["Confirm"]
