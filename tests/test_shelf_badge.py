# SPDX-License-Identifier: GPL-3.0-or-later
"""The catalogue scan of the owned shelf recognises a gift that has been
uptied: the + or ++ badge covers the top of its cell, and the match is tried
again with that band masked out."""
import cv2
import numpy as np
import pytest

from wbcore import shop as S
from wbcore.market_catalog import load_market_catalog
from wbcore.utils import params as p

NAME = "Torn Bandolier"
REG = (920, 295, 790, 482)


def _shelf(badge=False, scale=1.0):
    """A shelf capture with the Bandolier's cell at a known spot; `badge`
    paints the orange ++ over its top band."""
    rng = np.random.default_rng(7)
    shelf = rng.integers(20, 50, size=(REG[3], REG[2], 3), dtype=np.uint8)
    tpl = cv2.imread(load_market_catalog()[NAME]["sell_path"])
    h, w = tpl.shape[:2]
    x0, y0 = 341, 100                                   # 1261, 395 on screen
    shelf[y0:y0 + h, x0:x0 + w] = tpl
    if badge:
        # The orange ++ plate the game draws over the tier bars.
        cv2.rectangle(shelf, (x0 + 22, y0 + 4), (x0 + 84, y0 + 30), (20, 90, 230), -1)
        cv2.putText(shelf, "++", (x0 + 30, y0 + 26), cv2.FONT_HERSHEY_DUPLEX, 0.9,
                    (90, 230, 255), 3, cv2.LINE_AA)
    centre = (REG[0] + x0 + w // 2, REG[1] + y0 + h // 2)
    if scale != 1.0:
        shelf = cv2.resize(shelf, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)
    return shelf, centre


@pytest.fixture(autouse=True)
def _fhd(monkeypatch):
    monkeypatch.setattr(p, "WINDOW", (0, 0, 1920, 1080))


def test_a_plain_cell_and_a_badged_cell_both_read(monkeypatch):
    for badge in (False, True):
        shelf, centre = _shelf(badge)
        hit = S._market_scan(S.amplify(shelf), REG, [NAME])
        assert NAME in hit, "badge %s" % badge
        assert abs(hit[NAME][0] - centre[0]) <= 3 and abs(hit[NAME][1] - centre[1]) <= 3


def test_the_badge_alone_would_have_lost_the_cell():
    shelf, _centre = _shelf(badge=True)
    tpl = S.amplify(cv2.imread(load_market_catalog()[NAME]["sell_path"]))
    whole, _loc = S._ccoeff_best(S.amplify(shelf), tpl)
    assert whole < S._MARKET_CONF                        # why it went as fuel


def test_an_absent_gift_is_not_invented():
    shelf, _centre = _shelf(badge=True)
    hit = S._market_scan(S.amplify(shelf), REG, ["Fragment of Conceit", "Grand Welcome"])
    assert hit == {}


def test_a_smaller_window_is_matched_at_its_scale(monkeypatch):
    shelf, centre = _shelf(badge=True, scale=1366 / 1920)
    monkeypatch.setattr(p, "WINDOW", (0, 0, 1366, 768))
    hit = S._market_scan(S.amplify(shelf), REG, [NAME])
    assert NAME in hit
    assert abs(hit[NAME][0] - centre[0]) <= 4 and abs(hit[NAME][1] - centre[1]) <= 4
