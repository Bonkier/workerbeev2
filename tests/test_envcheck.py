# SPDX-License-Identifier: GPL-3.0-or-later
"""The detection environment check: what counts as a problem, what the
summary says, how the Night light blob reads."""
from wbcore.utils import envcheck as E

_OK = {"window": {"left": 0, "top": 0, "width": 1920, "height": 1080},
       "monitors": [{"left": 0, "top": 0, "width": 1920, "height": 1080,
                     "primary": True, "scale": 100}],
       "host": {"left": 0, "top": 0, "width": 1920, "height": 1080,
                "primary": True, "scale": 100},
       "hdr": False, "night_light": False, "color_filter": False,
       "capture": {"width": 1920, "height": 1080, "brightness": 60.0, "saturation": 40.0},
       "capture_backend": "dxgi", "gdi_stale": False, "windows_build": 26200,
       "specs": {}}


def test_a_plain_1080p_window_raises_nothing():
    assert E.issues(_OK) == []
    lines = E.summary(_OK)
    assert lines[0] == "Game window 1920 x 1080 at (0, 0)"
    assert "scale 100%" in lines[1] and "HDR off" in lines[2]


def test_each_known_pitfall_is_named():
    def kinds(**over):
        rep = dict(_OK, **over)
        return [what for _l, what, _h in E.issues(rep)]
    scaled = E.issues(dict(_OK, host=dict(_OK["host"], scale=125)))
    assert scaled[0][0] == "info" and "scaling is 125%" in scaled[0][1]       # a true 1080p window
    small = dict(_OK, window={"left": 0, "top": 0, "width": 1280, "height": 720},
                 host=dict(_OK["host"], scale=150), capture=dict(_OK["capture"], width=1280, height=720))
    assert [lvl for lvl, w, _h in E.issues(small) if "scaling" in w] == ["warn"]
    assert all("%%" not in h for _l, _w, h in E.issues(small))
    assert E.issues(dict(_OK, hdr=True))[0][0] == "warn"
    two = _OK["monitors"] + [dict(_OK["monitors"][0], left=1920)]
    assert E.issues(dict(_OK, hdr=True, monitors=two))[0][0] == "info"
    assert kinds(night_light=True) == []           # a gamma ramp: not in the capture
    assert any("colour filter" in w for w in kinds(color_filter=True))
    odd = E.issues(dict(_OK, window={"left": 0, "top": 0, "width": 1600, "height": 1000},
                        capture=dict(_OK["capture"], width=1600, height=1000)))
    assert odd[0][0] == "info" and "not 16:9" in odd[0][1]       # set_window has its own help
    assert any("blur" in w for w in kinds(window={"left": 0, "top": 0, "width": 960, "height": 540}))
    assert any("rescaled" in w for w in kinds(window={"left": 0, "top": 0, "width": 1280, "height": 720}))
    assert any("past the edge" in w for w in kinds(window={"left": 400, "top": 0, "width": 1920, "height": 1080}))
    black = E.issues(dict(_OK, capture=dict(_OK["capture"], brightness=1.0)))
    assert black[0][0] == "error" and "black" in black[0][1]
    narrow = E.issues(dict(_OK, capture=dict(_OK["capture"], width=1366)))
    assert narrow[0][0] == "error" and "1366 px wide" in narrow[0][1]
    assert any("could not be captured" in w for w in kinds(capture=None, capture_error="boom"))


def test_the_capture_path_is_reported_and_windows_10_on_gdi_is_warned():
    assert "Capture via DXGI" in E.summary(_OK)[4]
    stale = dict(_OK, gdi_stale=True)
    assert [lvl for lvl, w, _h in E.issues(stale) if "compositor" in w] == ["info"]
    assert "compositor copy stale" in E.summary(stale)[4]
    win10 = dict(_OK, capture_backend="gdi", gdi_stale=None, windows_build=19045,
                 dxgi_error="no display holds (960, 540)")
    rows = E.issues(win10)
    assert rows[0][0] == "warn" and "Windows 10" in rows[0][1] and "fullscreen optimizations" in rows[0][2]
    assert "failed here (no display holds" in rows[0][1] and "switch Capture" not in rows[0][2]
    assert "(DXGI: no display holds" in E.summary(win10)[4]
    off = dict(win10, dxgi_error="switched off in Settings")
    assert "switched off in Settings" in E.issues(off)[0][1] and "switch Capture" in E.issues(off)[0][2]
    windowed = dict(win10, window={"left": 100, "top": 60, "width": 1600, "height": 900},
                    capture=dict(_OK["capture"], width=1600, height=900))
    assert not any("Windows 10" in w for _l, w, _h in E.issues(windowed))
    win11 = dict(win10, windows_build=22631)
    assert not any("Windows 10" in w for _l, w, _h in E.issues(win11))


def test_errors_come_first_and_unknowns_read_as_such():
    rep = dict(_OK, hdr=True, capture=dict(_OK["capture"], brightness=0.0), night_light=None)
    found = E.issues(rep)
    assert [lvl for lvl, _w, _h in found][:2] == ["error", "warn"]
    assert "Night light unknown" in E.summary(rep)[2]


def test_the_night_light_blob_reads_on_off_or_unknown():
    assert E.night_light_from_blob(bytes(18) + b"\x15" + bytes(20)) is True
    assert E.night_light_from_blob(bytes(18) + b"\x13" + bytes(20)) is False
    on = bytes.fromhex("43420100 0a020100 2a06d9b4 8ebd062a 2b0e0543 42010010 00d00a02 c614")
    off = bytes.fromhex("43420100 0a020100 2a069bd3 a9d3062a 2b0e0543 42010000 00000000")
    assert E.night_light_from_blob(on) is True and E.night_light_from_blob(off) is False
    assert E.night_light_from_blob(bytes(18) + b"\x00") is None
    assert E.night_light_from_blob(b"short") is None
    assert E.night_light_from_blob(None) is None


def test_the_advisory_leads_with_the_check_and_lists_the_fixes():
    rep = dict(_OK, hdr=True)
    text = E.advisory_text(E.issues(rep), rep)
    assert text.startswith("Detection check:")
    assert "HDR" in text and "Auto HDR" in text and "debug" in text
    led = E.advisory_text(E.issues(rep), rep, lead="the tab was not recognised.")
    assert led.startswith("Detection check: the tab was not recognised.")


def test_the_run_start_check_advises_once_per_problem_set(monkeypatch):
    from wbcore.utils import params as p
    said = []
    monkeypatch.setattr(p, "WARNING", lambda msg: said.append(msg))
    monkeypatch.setattr(E, "collect", lambda probe=True: dict(_OK, hdr=True))
    E._LAST["advised"] = None
    assert E.run_start_check() is not None and len(said) == 1
    E.run_start_check()
    assert len(said) == 1                                    # same problems: no repeat
    monkeypatch.setattr(E, "collect", lambda probe=True: dict(_OK))
    E.run_start_check()
    assert len(said) == 1                                    # nothing wrong: nothing said
    monkeypatch.setattr(E, "collect", lambda probe=True: dict(
        _OK, window={"left": 0, "top": 0, "width": 1280, "height": 720},
        capture=dict(_OK["capture"], width=1280, height=720)))
    E.run_start_check()
    assert len(said) == 1                                    # informational only: logged, not raised
    monkeypatch.setattr(E, "collect", lambda probe=True: dict(_OK, color_filter=True))
    E.run_start_check()
    assert len(said) == 2
