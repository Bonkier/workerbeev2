# SPDX-License-Identifier: GPL-3.0-or-later
"""Smoke tests for `src.wbcore.live`.

`live.py` is the boundary layer that intentionally couples to legacy
globals (`params.WINDOW`, `os_windows_backend`, `telemetry.match`).
We can't run the full thing without the bridge plugin on sys.path, so
these tests cover the parts that don't require live IO:

- public API surface (live_pipeline is importable, has the right
  signature)
- error paths (no params.WINDOW set, malformed WINDOW)

Full integration is verified by hand against the running app, since
the bridge is a runtime requirement that pytest can't satisfy.
"""
from __future__ import annotations

import inspect
import sys
import types

import pytest


def test_live_pipeline_is_importable():
    from src.wbcore.live import live_pipeline
    assert callable(live_pipeline)


def test_live_pipeline_signature_matches_documented_api():
    from src.wbcore.live import live_pipeline
    sig = inspect.signature(live_pipeline)
    params = sig.parameters
    assert "prefilled_templates" in params
    assert "default_conf" in params
    # All public params are keyword-only.
    for name in ("prefilled_templates", "default_conf"):
        assert params[name].kind == inspect.Parameter.KEYWORD_ONLY


def test_resolve_window_rejects_missing_window(monkeypatch):
    """If params.WINDOW is None, _resolve_window raises a useful error."""
    from src.wbcore import live

    fake_params = types.SimpleNamespace(WINDOW=None)
    fake_utils = types.SimpleNamespace(params=fake_params)
    monkeypatch.setitem(sys.modules, "src.wbcore.utils", fake_utils)
    monkeypatch.setitem(sys.modules, "src.wbcore.utils.params", fake_params)

    with pytest.raises(RuntimeError, match="params.WINDOW is unset"):
        live._resolve_window()


def test_resolve_window_rejects_malformed_tuple(monkeypatch):
    from src.wbcore import live

    fake_params = types.SimpleNamespace(WINDOW=(0, 0))  # wrong arity
    fake_utils = types.SimpleNamespace(params=fake_params)
    monkeypatch.setitem(sys.modules, "src.wbcore.utils", fake_utils)
    monkeypatch.setitem(sys.modules, "src.wbcore.utils.params", fake_params)

    with pytest.raises(RuntimeError, match="wrong shape"):
        live._resolve_window()


def test_resolve_window_builds_geometry_from_valid_tuple(monkeypatch):
    from src.wbcore import live
    from src.wbcore.regionspec import WindowGeometry

    fake_params = types.SimpleNamespace(WINDOW=(100, 50, 1920, 1080))
    fake_utils = types.SimpleNamespace(params=fake_params)
    monkeypatch.setitem(sys.modules, "src.wbcore.utils", fake_utils)
    monkeypatch.setitem(sys.modules, "src.wbcore.utils.params", fake_params)

    geom = live._resolve_window()
    assert isinstance(geom, WindowGeometry)
    assert (geom.x, geom.y, geom.w, geom.h) == (100, 50, 1920, 1080)
