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


def test_a_tab_that_does_not_read_is_logged_dumped_and_clicked_at_its_spot(monkeypatch, caplog):
    monkeypatch.setattr(B.LocateRGB, "locate", lambda *a, **k: None)
    monkeypatch.setattr(B.LocateRGB, "get_conf", lambda *a, **k: 0.81)
    clicks, dumps = [], []
    monkeypatch.setattr(B, "win_click", lambda x, y, *a, **k: clicks.append((int(x), int(y))))
    monkeypatch.setattr(B, "_diag_once", lambda tag, advise=None, **kw: dumps.append((tag, advise, kw)))
    monkeypatch.setattr(B.time, "sleep", lambda s: None)
    gated = []
    monkeypatch.setattr(B, "_wait_gift_menu", lambda timer=5.0: gated.append(1) or True)
    with caplog.at_level("INFO"):
        assert B._click_keyword_tab("keywordless") is True
    assert clicks == [(1098, 286)] and gated == [1]          # the upstream way: header, then the spot
    assert "template best 0.81" in caplog.text
    assert "at its fixed spot (1098, 286), template best 0.81" in caplog.text
    tag, advise, kw = dumps[0]
    assert tag == "gifttab_keywordless" and "0.81" in advise
    assert len(kw["extra"]) == 11 and kw["region"] == B._GIFT_TAB_REGION
    assert kw["gate"] == 0.85
    # A template that reads is clicked where it is, with no dump.
    del clicks[:], dumps[:]
    monkeypatch.setattr(B.LocateRGB, "locate", lambda *a, **k: (1064, 251, 68, 69))
    with caplog.at_level("INFO"):
        assert B._click_keyword_tab("keywordless") is True
    assert clicks == [(1098, 285)] and dumps == []
    assert "by template at (1098, 285)" in caplog.text


def test_a_dump_happens_once_per_run_and_raises_the_advisory(monkeypatch):
    from wbcore.utils import params as p, envcheck as E
    said, dumped = [], []
    monkeypatch.setattr(p, "DIAG_DONE", set())
    monkeypatch.setattr(p, "WARNING", lambda msg: said.append(msg))
    monkeypatch.setattr(B, "dump_template_diag", lambda tag, **kw: dumped.append(tag) or "C:/x/report.png")
    monkeypatch.setattr(E, "last_report", lambda: {"window": {"left": 0, "top": 0, "width": 1920, "height": 1080},
                                                   "monitors": [], "host": None, "hdr": True,
                                                   "night_light": False, "color_filter": False,
                                                   "specs": {}, "capture": {"width": 1920, "height": 1080,
                                                                            "brightness": 50.0, "saturation": 30.0}})
    assert B._diag_once("gifttab_keywordless", advise="the tab was not recognised.") == "C:/x/report.png"
    assert B._diag_once("gifttab_keywordless", advise="again") is None
    assert dumped == ["gifttab_keywordless"] and len(said) == 1
    assert said[0].startswith("Detection check: the tab was not recognised.")
    assert "HDR" in said[0] and "report.png" in said[0]


def test_the_advisory_is_shown_without_taking_focus_and_one_at_a_time(monkeypatch):
    from gui_v2 import run_coordinator as RC
    shown, pinged, closed = [], [], []

    class Dlg:
        def close(self):
            closed.append(1)
    monkeypatch.setattr(RC, "show_advisory",
                        lambda parent, text, title="": shown.append((title, text)) or Dlg())
    monkeypatch.setattr(RC, "show_notice", lambda parent, text, title="": pinged.append(("notice", text)))

    class Fake:
        _ui = None

        def _discord_stuck(self, reason):
            pinged.append(("discord", reason))
    fake = Fake()
    RC.RunCoordinator._on_warning(fake, "Detection check: HDR is on.")
    assert shown == [("Detection check", "Detection check: HDR is on.")] and pinged == []
    RC.RunCoordinator._on_warning(fake, "Detection check: the tab was not recognised.")
    assert len(shown) == 2 and closed == [1]                 # the first was replaced


def test_the_upstream_way_waits_for_the_header_and_clicks_the_spot(monkeypatch, caplog):
    clicks, pressed, asked = [], [], []
    monkeypatch.setattr(B.LocateRGB, "locate", lambda *a, **k: (_ for _ in ()).throw(AssertionError("no template read")))
    monkeypatch.setattr(B, "win_click", lambda x, y, *a, **k: clicks.append((int(x), int(y))))
    monkeypatch.setattr(B.time, "sleep", lambda s: None)
    monkeypatch.setattr(B.gui, "press", lambda key: pressed.append(key))
    answers = {"startGift": [False, False, True], "Confirm": [True, False, False]}

    class Now:
        def button(self, key, *a, **k):
            asked.append(key)
            return answers[key].pop(0) if answers.get(key) else False
    monkeypatch.setattr(B, "now", Now())
    with caplog.at_level("INFO"):
        assert B._click_keyword_tab("keywordless", fixed=True) is True
    assert clicks == [(1098, 286)]
    assert pressed == ["enter"]                               # a confirm in the way is cleared
    assert asked.index("startGift") == 0 and "the upstream way" in caplog.text
    assert B.REG["startGift"] == (1265, 220, 312, 70) and "startGift" in B.PTH
    assert "keywordless" not in B.PTH                         # the old-layout SAIKAI tab is gone
    assert not hasattr(B, "saikai_gift_search")


def test_a_gift_missing_after_the_template_click_gets_the_upstream_tab_click(monkeypatch, caplog):
    tabs, finds = [], []
    monkeypatch.setattr(B.loc, "button", lambda *a, **k: True)
    monkeypatch.setattr(B, "_wait_gift_menu", lambda timer=5.0: True)
    monkeypatch.setattr(B.time, "sleep", lambda s: None)
    monkeypatch.setattr(B, "_click_keyword_tab", lambda kw, fixed=False: tabs.append((kw, fixed)) or True)
    monkeypatch.setattr(B, "_gift_scroll", lambda n: None)
    monkeypatch.setattr(B, "tap_center", lambda *a, **k: True)
    monkeypatch.setattr(B, "_leave_gift_menu", lambda *a, **k: True)
    monkeypatch.setattr(B, "_diag_once", lambda *a, **k: (_ for _ in ()).throw(AssertionError("no dump")))

    def find(path, max_scrolls=6):
        finds.append(max_scrolls)
        return len(finds) >= 3                                # only after the tab was re-selected
    monkeypatch.setattr(B, "_find_and_click_gift", find)
    with caplog.at_level("INFO"):
        assert B.gift_search(["Spiderweb Entangled in Red"]) == 1
    assert tabs == [("keywordless", False), ("keywordless", True)]
    assert finds == [0, 6, 6]
    assert "selecting the tab the upstream way" in caplog.text
