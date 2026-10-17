# SPDX-License-Identifier: GPL-3.0-or-later
"""The gift search on the Mirror of Sisyphe layout: the tab row reaches the
Keywordless tab, the grid reaches the panel border, and a cell that only
looks like the wanted gift is passed over."""
import cv2

from wbcore import bot as B


def test_the_tab_row_covers_every_keyword_tab():
    x0, _y, w, _h = B._GIFT_TAB_REGION
    xs = list(B._GIFT_TAB_X.values())
    assert xs == sorted(xs) and all(90 <= b - a <= 95 for a, b in zip(xs, xs[1:]))
    for kw, x in B._GIFT_TAB_X.items():
        assert x0 + 34 <= x <= x0 + w - 34, kw
    assert B._GIFT_GRID_REGION[1] + B._GIFT_GRID_REGION[3] >= 930


def test_a_look_alike_cell_is_not_taken_for_the_gift(monkeypatch):
    from wbcore import gift_catalog as G
    cat = G.load_catalog()
    blanket, bolt = cat["Blanket"]["path"], cat["T-1B Octagonal Bolt"]["path"]
    bolt_img = cv2.imread(bolt)
    monkeypatch.setattr(B, "screenshot", lambda region=None: bolt_img.copy())
    box = (0, 0, bolt_img.shape[1], bolt_img.shape[0])
    assert B._hit_is_gift(box, bolt) is True
    assert B._hit_is_gift(box, blanket) is False
    small = cv2.resize(bolt_img, None, fx=0.71, fy=0.71)   # a smaller window
    monkeypatch.setattr(B, "screenshot", lambda region=None: small.copy())
    assert B._hit_is_gift((0, 0, small.shape[1], small.shape[0]), bolt) is True
    assert B._hit_is_gift(box, "not/in/the/catalogue.png") is True


def test_the_search_scrolls_past_a_look_alike(monkeypatch):
    boxes = iter([(10, 10, 81, 86), (10, 10, 81, 86)])
    monkeypatch.setattr(B.LocateRGB, "locate", lambda *a, **k: next(boxes, None))
    verdicts = iter([False, True])
    monkeypatch.setattr(B, "_hit_is_gift", lambda box, path: next(verdicts))
    clicks, scrolls = [], []
    monkeypatch.setattr(B, "win_click", lambda *a, **k: clicks.append(a))
    monkeypatch.setattr(B, "_gift_scroll", lambda n: scrolls.append(n))
    assert B._find_and_click_gift("x", max_scrolls=2) is True
    assert scrolls == [-3] and len(clicks) == 1
