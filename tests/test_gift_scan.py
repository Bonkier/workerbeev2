# SPDX-License-Identifier: GPL-3.0-or-later
"""The end-of-run gift scan: the shelf pages are captured until the bottom
and named off the shop, and the run record gets the result."""
import threading
import types

import numpy as np

from wbcore import shop as S


def test_the_shelf_pages_are_captured_until_the_bottom(monkeypatch):
    pages = iter([np.full((4, 4, 3), v, np.uint8) for v in (10, 10, 20, 20, 30, 30, 30)])
    monkeypatch.setattr(S, "screenshot", lambda region=None: next(pages))
    at_bottom = iter([False, False, True])
    monkeypatch.setattr(S, "now_rgb", types.SimpleNamespace(
        button=lambda name, *a, **k: next(at_bottom) if name == "scroll.0" else True))
    drags = []
    monkeypatch.setattr(S, "browse_fast", lambda hook, up=False: drags.append(up))
    monkeypatch.setattr(S.time, "sleep", lambda s: None)
    frames = S._capture_shelf(1083)
    assert [int(f[0, 0, 0]) for f in frames] == [10, 20, 30] and drags == [False, False]


def test_a_single_page_shelf_is_one_frame(monkeypatch):
    frame = np.zeros((4, 4, 3), np.uint8)
    monkeypatch.setattr(S, "screenshot", lambda region=None: frame)
    monkeypatch.setattr(S, "now_rgb", types.SimpleNamespace(button=lambda *a, **k: False))
    monkeypatch.setattr(S, "browse_fast", lambda hook, up=False: (_ for _ in ()).throw(AssertionError("no drag")))
    monkeypatch.setattr(S.time, "sleep", lambda s: None)
    assert len(S._capture_shelf(1083)) == 1


def test_the_shelf_is_named_off_the_shop_and_handed_to_the_run_record(monkeypatch):
    frames = [np.zeros((482, 790, 3), np.uint8)]
    monkeypatch.setattr(S, "amplify", lambda img: img)
    monkeypatch.setattr(S, "_market_scan", lambda image, reg, names: {"Blanket": (1000, 400)})
    monkeypatch.setattr(S.LocateRGB, "try_locate",
                        lambda *a, **k: (_ for _ in ()).throw(S.gui.ImageNotFoundException()))
    monkeypatch.setattr(S.LocateRGB, "check", lambda *a, **k: True)      # the uptie badge
    emitted = []
    monkeypatch.setattr(S.tele, "gifts", lambda items: emitted.append(items))
    S._GIFT_SCAN.update(thread=None, items=None)
    assert S.finish_gift_scan() == [] and emitted == []                  # nothing pending
    worker = threading.Thread(target=S._name_shelf_later,
                              args=(frames, S.REG["fuse_shelf"], 1.0, {"holder"}, ["Blanket"]))
    S._GIFT_SCAN["thread"] = worker
    worker.start()
    assert S.finish_gift_scan(timeout=10) == [("Blanket", True)]
    assert emitted == [[("Blanket", True)]]
    assert S.finish_gift_scan() == []                                     # handed over once
