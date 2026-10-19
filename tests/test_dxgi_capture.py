# SPDX-License-Identifier: GPL-3.0-or-later
"""The DXGI capture path: the display holding the region is picked, the
crop lands where GDI's would, a region past the display's edge is padded,
a failure hands over to GDI for good, and the backend dispatches."""
import sys
import types

import numpy as np
import pytest

from wbcore.utils import dxgi_capture as D
from wbcore.utils import params as p


def _fake_dxcam(monkeypatch, outputs, frames=None, create=None):
    class Rect:
        def __init__(self, l, t, r, b):
            self.left, self.top, self.right, self.bottom = l, t, r, b

    class Out:
        def __init__(self, rect):
            self.desc = types.SimpleNamespace(DesktopCoordinates=Rect(*rect))

    class Cam:
        """frame: an array (every grab answers it), None (never a frame), or
        a list popped per grab (None entries mean nothing changed)."""
        def __init__(self, frame):
            self.frame, self.calls, self.released = frame, [], False

        def grab(self, region=None):
            self.calls.append(region)
            if isinstance(self.frame, list):
                return self.frame.pop(0) if self.frame else None
            return None if self.frame is None else self.frame.copy()

        def release(self):
            self.released = True

    cams = []

    def _create(device_idx=0, output_idx=None, output_color="RGB"):
        cam = Cam(frames[(device_idx, output_idx)])
        cams.append(cam)
        return cam
    mod = types.SimpleNamespace(create=create or _create)
    setattr(mod, "__factory", types.SimpleNamespace(
        devices=[object()], outputs=[[Out(r) for r in outputs]]))

    class Dup:
        def __init__(self):
            self.duplicator = _Pointer()

    class Stage:
        def __init__(self):
            self.texture, self.width, self.height = _Pointer(), 4, 4
    core = types.SimpleNamespace(duplicator=types.SimpleNamespace(Duplicator=Dup),
                                 stagesurf=types.SimpleNamespace(StageSurface=Stage))
    monkeypatch.setitem(sys.modules, "dxcam", mod)
    monkeypatch.setitem(sys.modules, "dxcam.core", core)
    monkeypatch.setitem(sys.modules, "dxcam.core.duplicator", core.duplicator)
    monkeypatch.setitem(sys.modules, "dxcam.core.stagesurf", core.stagesurf)
    D._STATE.update(cam=None, rect=None, last=None, failed=None, failed_at=0.0, misses=0,
                    patched=False)
    return cams


class _Pointer:
    def Release(self):
        raise AssertionError("a manual Release: comtypes releases on collection")


def _frame(w, h, seed):
    return np.random.default_rng(seed).integers(0, 255, size=(h, w, 3), dtype=np.uint8)


def test_the_crop_matches_the_display_and_its_offset(monkeypatch):
    primary, left = _frame(1920, 1080, 1), _frame(1280, 1024, 2)
    cams = _fake_dxcam(monkeypatch, [(0, 0, 1920, 1080), (-1280, 0, 0, 1024)],
                       {(0, 0): primary, (0, 1): left})
    got = D.grab((100, 200, 300, 150))
    assert np.array_equal(got, primary[200:350, 100:400])
    assert cams[0].calls == [None]                                # the whole display, cut here
    got = D.grab((-1000, 500, 200, 100))                          # the display to the left
    assert np.array_equal(got, left[500:600, 280:480])
    assert cams[0].released and len(cams) == 2                    # one camera at a time
    assert D.active() and D.why_not() is None
    # dxcam's two manual releases are gone: dropping the pointers is enough.
    dup, st = sys.modules["dxcam.core.duplicator"], sys.modules["dxcam.core.stagesurf"]
    d, s = dup.Duplicator(), st.StageSurface()
    d.release(); s.release()
    assert d.duplicator is None and s.texture is None and s.width == 0


def test_nothing_changed_means_the_last_frame_still_stands(monkeypatch):
    primary = _frame(1920, 1080, 5)
    cams = _fake_dxcam(monkeypatch, [(0, 0, 1920, 1080)], {(0, 0): [primary, None, None]})
    assert np.array_equal(D.grab((0, 0, 50, 50)), primary[:50, :50])
    assert np.array_equal(D.grab((10, 10, 50, 50)), primary[10:60, 10:60])   # from the kept frame
    assert np.array_equal(D.grab((20, 20, 50, 50)), primary[20:70, 20:70])
    assert len(cams[0].calls) == 3 and D.active()


def test_a_region_past_the_edge_is_padded_like_gdi_shows_it(monkeypatch):
    primary = _frame(1920, 1080, 3)
    _fake_dxcam(monkeypatch, [(0, 0, 1920, 1080)], {(0, 0): primary})
    got = D.grab((1800, 1000, 200, 100))
    assert got.shape == (100, 200, 3)
    assert np.array_equal(got[:80, :120], primary[1000:1080, 1800:1920])
    assert not got[80:, :].any() and not got[:, 120:].any()


def test_a_failure_hands_over_to_gdi_until_a_retry_or_a_run_start(monkeypatch):
    calls = []

    def boom(**kw):
        calls.append(1)
        raise OSError("no duplication for you")
    _fake_dxcam(monkeypatch, [(0, 0, 1920, 1080)], create=boom)
    assert D.grab((0, 0, 100, 100)) is None
    assert "no duplication" in D.why_not() and not D.active()
    assert D.grab((0, 0, 100, 100)) is None and len(calls) == 1    # not tried again at once
    D._STATE["failed_at"] -= D._RETRY_AFTER + 1                    # a minute later: tried again
    assert D.grab((0, 0, 100, 100)) is None and len(calls) == 2
    D.reset()                                                      # a run start: tried again
    assert D.why_not() is None
    assert D.grab((0, 0, 100, 100)) is None and len(calls) == 3
    cams = _fake_dxcam(monkeypatch, [(0, 0, 1920, 1080)], {(0, 0): None})
    for _ in range(D._MISS_LIMIT - 1):
        assert D.grab((0, 0, 10, 10)) is None and D.why_not() is None
    assert D.grab((0, 0, 10, 10)) is None and "without a frame" in D.why_not()
    assert cams[0].released


@pytest.mark.skipif(not sys.platform.startswith("win"), reason="the Windows backend")
def test_the_backend_prefers_dxgi_and_falls_back_to_gdi(monkeypatch):
    from wbcore.utils import os_windows_backend as be
    shown = np.full((10, 20, 3), 7, np.uint8)
    copy = np.full((10, 20, 3), 9, np.uint8)
    monkeypatch.setattr(be.dxgi_capture, "grab", lambda region: shown)
    monkeypatch.setattr(be, "screenshot_gdi", lambda *a, **k: copy)
    monkeypatch.setattr(p, "CAPTURE_DXGI", True)
    assert be.screenshot(region=(0, 0, 20, 10)) is shown
    monkeypatch.setattr(be.dxgi_capture, "grab", lambda region: None)
    assert be.screenshot(region=(0, 0, 20, 10)) is copy
    monkeypatch.setattr(be.dxgi_capture, "grab", lambda region: shown)
    monkeypatch.setattr(p, "CAPTURE_DXGI", False)
    assert be.screenshot(region=(0, 0, 20, 10)) is copy            # the toggle is off
    assert be.screenshot(allScreens=True) is copy                  # whole desktop: GDI


def test_a_window_on_no_known_display_rereads_the_displays_at_reset(monkeypatch):
    primary = _frame(1920, 1080, 9)
    _fake_dxcam(monkeypatch, [(0, 0, 1920, 1080)], {(0, 0): primary})
    assert D.grab((3000, 100, 50, 50)) is None                     # a display dxcam never saw
    assert "no display holds" in D.why_not()
    reloaded = []
    import importlib
    monkeypatch.setattr(importlib, "reload", lambda mod: reloaded.append(mod))
    D.reset()
    assert reloaded and D.why_not() is None and D._STATE["patched"] is False
