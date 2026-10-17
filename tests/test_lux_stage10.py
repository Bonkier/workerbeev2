# SPDX-License-Identifier: GPL-3.0-or-later
"""EXP Luxcavation stage 10: the two-digit badge is read first by its whole
digits row, and a card without a consecutive bar yet is entered once."""
import cv2
import numpy as np

from wbcore import lux as L
from wbcore.utils import params as p
from wbcore.utils import utils as U


def _crop_with(name, dx=26, dy=16):
    t = cv2.imread(U.PTH[name])
    crop = np.full((L._BADGE_CROP_H, L._BADGE_CROP_W, 3), 20, np.uint8)
    h, w = t.shape[:2]
    crop[dy:dy + h, dx:dx + w] = t
    return crop


def test_the_badge_reader_tells_10_from_1_and_8():
    assert L._read_stage_crop(_crop_with("lux_stage10")) == 10
    assert L._read_stage_crop(_crop_with("lux_stage10", dx=10)) == 10    # a card wobble
    assert L._read_stage_crop(_crop_with("lux_stage1")) == 1
    assert L._read_stage_crop(_crop_with("lux_stage8")) == 8
    assert L._read_stage_crop(None) is None


def test_the_stage_search_falls_back_to_the_badge(monkeypatch):
    monkeypatch.setattr(L, "_scan_for_stage", lambda stage: None)
    monkeypatch.setattr(L, "_scan_for_badge", lambda stage: (1493, 271, 75, 64))
    monkeypatch.setattr(L, "_scroll_exp",
                        lambda d: (_ for _ in ()).throw(AssertionError("no scroll needed")))
    assert L._find_exp_stage(10) == (None, (1493, 271, 75, 64))
    monkeypatch.setattr(L, "_scan_for_stage", lambda stage: (900, 360, 277, 39))
    assert L._find_exp_stage(10) == ((900, 360, 277, 39), None)


def test_a_card_without_a_consecutive_bar_is_entered_once(monkeypatch):
    monkeypatch.setattr(L, "_find_exp_stage", lambda stage: (None, (1493, 271, 75, 64)))
    monkeypatch.setattr(L, "_setup_lux_consecutive_batch",
                        lambda *a, **k: (_ for _ in ()).throw(AssertionError("no popup without a bar")))
    doors = []
    monkeypatch.setattr(L, "_click_enterdoor_for_stage", lambda box: doors.append(box) or True)
    monkeypatch.setattr(p, "LUX_EXP_STAGE", 10)
    monkeypatch.setattr(p, "LUX_SKIP_EXP", False)
    assert L.select_exp_stage(5) == 1
    assert doors == [(1493, 271, 75, 64)]


def test_the_page_offers_stage_10():
    from gui_v2 import luxcavation_page as LP
    assert LP._EXP_STAGES[-1] == "10" and len(LP._EXP_STAGES) == 10
