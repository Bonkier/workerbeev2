# SPDX-License-Identifier: GPL-3.0-or-later
"""The starter-gift confirms: each GET dialog is cleared with Enter and the
loop leaves the moment the EGO Gift Search menu shows. Then the picks made
under BUILD > Starting gifts, taken by the row their art is on."""
import types

import pytest

from wbcore import bot as B
from wbcore.utils import params as p


def _screen(monkeypatch, frames):
    """`frames`: the markers visible at each poll; sleeping moves to the next."""
    it = iter(frames)
    cur = {"v": next(it), "sleeps": 0, "clicks": []}
    monkeypatch.setattr(B, "now", types.SimpleNamespace(
        button=lambda name, *a, **k: name in cur["v"]))
    monkeypatch.setattr(B, "now_click", types.SimpleNamespace(
        button=lambda name, *a, **k: (cur["clicks"].append(name), name in cur["v"])[1]
        if name in cur["v"] else False))

    def tick(_s):
        cur["sleeps"] += 1
        cur["v"] = next(it, cur["v"])
    monkeypatch.setattr(B.time, "sleep", tick)
    return cur


def test_the_menu_showing_steadily_ends_the_wait(monkeypatch):
    cur = _screen(monkeypatch, [{"giftsearch"}])
    assert B._starter_get_dialog() is False
    assert cur["sleeps"] == 2                                # three polls, 0.2 s


def test_a_passing_menu_frame_does_not_end_the_wait(monkeypatch):
    cur = _screen(monkeypatch, [{"giftsearch"}, set(), {"packconfirm"}])
    assert B._starter_get_dialog() is True


def test_a_get_dialog_is_reported_at_once(monkeypatch):
    cur = _screen(monkeypatch, [{"packconfirm"}, {"giftsearch"}])
    assert B._starter_get_dialog() is True
    assert cur["sleeps"] == 0


def test_the_wait_polls_until_either_shows(monkeypatch):
    cur = _screen(monkeypatch, [set(), set(), set(), {"packconfirm"}])
    assert B._starter_get_dialog() is True and cur["sleeps"] == 3
    cur = _screen(monkeypatch, [set(), set(), {"giftsearch"}])
    assert B._starter_get_dialog() is False and cur["sleeps"] == 4


def test_the_wait_gives_up_after_its_timer(monkeypatch):
    clock = {"t": 0.0}
    monkeypatch.setattr(B.time, "time", lambda: clock.__setitem__("t", clock["t"] + 0.5) or clock["t"])
    cur = _screen(monkeypatch, [set()])
    assert B._starter_get_dialog(timer=2.0) is False
    assert cur["sleeps"] <= 4


def test_one_starter_gift_means_one_enter_then_the_search(monkeypatch):
    calls = {"enter": 0, "search": None, "waited": 0}
    dialogs = iter([True, False])
    monkeypatch.setattr(B, "_select_archetype_gifts", lambda *a, **k: None)
    monkeypatch.setattr(B, "_starter_get_dialog", lambda timer=3.0: next(dialogs))
    monkeypatch.setattr(B, "wait_while_condition",
                        lambda *a, **k: calls.__setitem__("waited", calls["waited"] + 1) or True)
    monkeypatch.setattr(B.gui, "press",
                        lambda key: calls.__setitem__("enter", calls["enter"] + (key == "enter")))
    monkeypatch.setattr(B.time, "sleep", lambda s: None)
    monkeypatch.setattr(B, "gift_search", lambda t: calls.__setitem__("search", list(t)))
    monkeypatch.setattr(p, "RUN_SCRIPT", "")
    monkeypatch.setattr(p, "GIFT_SEARCH", ["Carmilla"], raising=False)
    B.select_starting_gift()
    assert calls == {"enter": 1, "search": ["Carmilla"], "waited": 1}


def test_two_starter_gifts_mean_two_enters(monkeypatch):
    calls = {"enter": 0}
    dialogs = iter([True, True, False])
    monkeypatch.setattr(B, "_select_archetype_gifts", lambda *a, **k: None)
    monkeypatch.setattr(B, "_starter_get_dialog", lambda timer=3.0: next(dialogs))
    monkeypatch.setattr(B, "wait_while_condition", lambda *a, **k: True)
    monkeypatch.setattr(B.gui, "press",
                        lambda key: calls.__setitem__("enter", calls["enter"] + (key == "enter")))
    monkeypatch.setattr(B.time, "sleep", lambda s: None)
    monkeypatch.setattr(B, "gift_search", lambda t: None)
    monkeypatch.setattr(p, "RUN_SCRIPT", "")
    monkeypatch.setattr(p, "GIFT_SEARCH", ["Carmilla"], raising=False)
    B.select_starting_gift()
    assert calls["enter"] == 2


def test_leaving_the_menu_returns_the_moment_the_dungeon_loads(monkeypatch):
    cur = _screen(monkeypatch, [{"loading"}])
    presses = []
    monkeypatch.setattr(B.gui, "press", lambda key: presses.append(key))
    assert B._leave_gift_menu() is True
    assert cur["sleeps"] == 0 and presses == []


def test_leaving_the_menu_confirms_each_dialog_as_it_shows(monkeypatch):
    cur = _screen(monkeypatch, [{"Confirm"}, set(), {"packconfirm"}, set(), {"PackChoice"}])
    presses = []
    clock = {"t": 0.0}
    monkeypatch.setattr(B.time, "time", lambda: clock.__setitem__("t", clock["t"] + 0.2) or clock["t"])
    monkeypatch.setattr(B.gui, "press", lambda key: presses.append(key))
    assert B._leave_gift_menu() is True
    assert presses == ["enter", "enter"]
    assert cur["sleeps"] == 4


def test_the_starlight_question_is_answered_by_its_own_button(monkeypatch):
    cur = _screen(monkeypatch, [{"starlightConfirm"}, set(), {"loading"}])
    presses = []
    clock = {"t": 0.0}
    monkeypatch.setattr(B.time, "time", lambda: clock.__setitem__("t", clock["t"] + 0.2) or clock["t"])
    monkeypatch.setattr(B.gui, "press", lambda key: presses.append(key))
    assert B._leave_gift_menu() is True
    assert cur["clicks"] == ["starlightConfirm"] and presses == []


def test_leaving_the_menu_gives_up_after_its_timer(monkeypatch):
    cur = _screen(monkeypatch, [set()])
    clock = {"t": 0.0}
    monkeypatch.setattr(B.time, "time", lambda: clock.__setitem__("t", clock["t"] + 0.5) or clock["t"])
    monkeypatch.setattr(B.gui, "press", lambda key: None)
    assert B._leave_gift_menu(timer=2.0) is False


class _Clicks:
    """Stands in for ClickAction: records the point and the verify key."""
    log = []

    def __init__(self, click, ver=None):
        self.click, self.ver = click, ver

    def execute(self, preset, ver=None):
        _Clicks.log.append((self.click, self.ver))
        return True


@pytest.fixture
def archetype(monkeypatch):
    del _Clicks.log[:]
    monkeypatch.setattr(B, "ClickAction", _Clicks)
    monkeypatch.setattr(p, "GIFTS", [{"checks": ["Burn", "smallBurn", (315, 370),
                                                 "reBurn", "bigBurn", 0]}])
    monkeypatch.setattr(p, "BUFF", [0] * 10)
    monkeypatch.setattr(p, "STARTER_GIFT", "", raising=False)
    return _Clicks.log


def _picked(log):
    return [c for c, v in log if v == "selected!"]


def _keyword(log):
    return [c for c, v in log if v == "gifts!"]


def test_a_picked_starter_gift_is_taken_by_the_row_its_art_is_on(archetype, monkeypatch):
    from wbcore import starter_gifts as SG
    from wbcore.teams import TEAMS
    looked = []
    monkeypatch.setattr(SG, "find_row",
                        lambda name, templates=(), tries=10: looked.append(name) or 2)
    p.STARTER_GIFT = "Pain of Stifled Rage"
    B._select_archetype_gifts()
    assert looked == ["Pain of Stifled Rage"]
    assert _keyword(archetype) == [(315, 370)] and _picked(archetype) == [(1239, 703)]
    del archetype[:]
    monkeypatch.setattr(SG, "find_row", lambda *a, **k: None)   # art not seen
    B._select_archetype_gifts()
    assert _picked(archetype) == [(1239, 395)]                  # the keyword's usual row
    del archetype[:]
    p.STARTER_GIFT = "Stone Tomb"                 # another keyword's gift: that keyword is clicked
    monkeypatch.setattr(SG, "find_row",
                        lambda name, templates=(), tries=10: looked.append(name) or 1)
    B._select_archetype_gifts(team=p.GIFTS[0], row=lambda: 0)   # over the team and its row
    assert _keyword(archetype) == [TEAMS["POISE"]["checks"][2]]
    assert _picked(archetype) == [(1239, 549)] and looked[-1] == "Stone Tomb"
    del archetype[:]
    p.STARTER_GIFT = ""
    B._select_archetype_gifts(row=lambda: None)   # no pick: the team's keyword and usual row
    assert _keyword(archetype) == [(315, 370)] and _picked(archetype) == [(1239, 395)]
    del archetype[:]
    p.STARTER_GIFT = "Nope"                       # not a starter gift: as if nothing were picked
    B._select_archetype_gifts()
    assert _keyword(archetype) == [(315, 370)] and _picked(archetype) == [(1239, 395)]
    del archetype[:]
    p.STARTER_GIFT = "Fiery Down"
    p.BUFF[3] = 1                                 # Star Shower: the pick plus one
    B._select_archetype_gifts()
    assert _picked(archetype) == [(1239, 395), (1239, 549)]


def test_hollows_own_gift_picked_under_build_keeps_the_runs_finder(archetype, monkeypatch):
    from wbcore import starter_gifts as SG
    from wbcore.teams import TEAMS
    monkeypatch.setattr(p, "RUN_SCRIPT", "hollow", raising=False)
    p.STARTER_GIFT = "Torn Bandolier"
    assert B._starter_pick() == (None, None)
    looked = []
    monkeypatch.setattr(SG, "find_row", lambda *a, **k: looked.append(a) or 0)
    B._select_archetype_gifts(TEAMS["PIERCE"], lambda: 2)     # the run's own row finder
    assert looked == [] and _keyword(archetype) == [TEAMS["PIERCE"]["checks"][2]]
    assert _picked(archetype) == [(1239, 703)]
    p.STARTER_GIFT = "Stone Tomb"                             # any other pick is a pick
    assert B._starter_pick() == (TEAMS["POISE"], "Stone Tomb")
    monkeypatch.setattr(p, "RUN_SCRIPT", "", raising=False)
    p.STARTER_GIFT = "Torn Bandolier"                         # outside Hollow too
    assert B._starter_pick() == (TEAMS["PIERCE"], "Torn Bandolier")


def test_the_rows_taken_follow_the_graces():
    from wbcore import starter_gifts as SG
    assert SG.rows_taken(1) == [1]
    assert SG.rows_taken(1, star_shower=True) == [1, 0]
    assert SG.rows_taken(0, star_shower=True) == [0, 1]
    assert SG.rows_taken(2, star_shower=True) == [2, 0]
    assert SG.rows_taken(1, True, True) == [1, 0, 2]
    assert SG.rows_taken(2, False, True) == [2, 0]
    assert SG.taken("Stone Tomb", star_shower=True) == ["Stone Tomb", "Cigarette Holder"]
    assert SG.taken("Torn Bandolier") == ["Torn Bandolier"]
    assert SG.taken("") == [] and SG.taken("Nope", True, True) == []


def test_the_starter_table_and_the_usual_picks():
    from wbcore import gift_catalog
    from wbcore import starter_gifts as SG
    from wbcore.teams import TEAMS
    assert list(SG.STARTER_GIFTS) == ["Burn", "Bleed", "Tremor", "Rupture", "Sinking",
                                      "Poise", "Charge", "Slash", "Pierce", "Blunt"]
    for keyword, names in SG.STARTER_GIFTS.items():
        assert len(names) == 3 and TEAMS[keyword.upper()]["checks"][0] == keyword
        for name in names:
            assert gift_catalog.gift_info(name), name
    assert SG.usual_pick("Pierce") == "Plume of Proof"
    assert SG.usual_pick("Burn") == "Hellterfly's Dream"
    assert SG.usual_row("nope") == 0 and SG.usual_pick("nope") == ""
    assert SG.keyword_of("Torn Bandolier") == "Pierce" and SG.keyword_of("nope") == ""


def test_find_row_reads_the_art_at_a_few_sizes(monkeypatch):
    from wbcore import starter_gifts as SG
    calls = []

    class Loc:
        @staticmethod
        def locate(tpl, region=None, conf=0.8, comp=1.0):
            calls.append(comp)
            if comp == 1.35:
                return (1200, 520, 74, 58)              # centre y 549: the middle row
            if comp == 1.2:
                raise RuntimeError("scale too big")    # skipped, not fatal
            return None
    monkeypatch.setattr(SG, "LocateRGB", Loc)
    monkeypatch.setattr(SG.time, "sleep", lambda s: None)
    assert SG.find_row("Torn Bandolier") == 1
    assert calls == [1.0, 1.2, 1.35]
    monkeypatch.setattr(SG, "LocateRGB", types.SimpleNamespace(locate=lambda *a, **k: None))
    assert SG.find_row("Torn Bandolier", tries=2) is None


def test_the_run_settings_and_the_overlay_carry_the_pick():
    from gui_v2 import run_summary as R
    from gui_v2.run_config import HOLLOW_LABEL, SAIKAI_LABEL, build_settings
    assert build_settings({"starter_gift": "Fiery Down"})["starter_gift"] == "Fiery Down"
    assert build_settings({})["starter_gift"] == ""
    md = {"starter_gift": "Stone Tomb"}
    hollow_md = {**md, "custom_run": True, "custom_strategy": HOLLOW_LABEL}
    bare_hollow = {"custom_run": True, "custom_strategy": HOLLOW_LABEL}
    assert dict(R.md_summary(md)[0][1])["Starter gift"] == "Poise: Stone Tomb"
    assert dict(R.md_summary({})[0][1])["Starter gift"] == "The team keyword's usual pick"
    saikai = dict(R.md_summary({"custom_run": True, "custom_strategy": SAIKAI_LABEL,
                                "saikai_status": "Sinking"})[0][1])
    assert saikai["Starter gift"] == "Sinking: Red Order (the usual pick)"
    hollow = R.md_summary(hollow_md)
    assert dict(hollow[0][1])["Starter gift"] == "Poise: Stone Tomb"      # the pick, not the run's own
    assert dict(R.md_summary(bare_hollow)[0][1])["Starter gift"] == "Pierce: Torn Bandolier (the run's own)"
    def market(m):
        return next(dict(rows)["Market"] for _t, rows in R.md_summary(m)
                    if "Market" in dict(rows))
    markets = [market(m) for m in (bare_hollow, hollow_md)]
    assert markets[0].startswith("Torn Bandolier uptied first on floor 1, then the heal and the floor plan")
    assert markets[1].startswith("The heal, then the floor plan")
    assert R.md_gifts(md)[0] == {"caption": "STARTER GIFT", "named": True, "names": ["Stone Tomb"]}
    assert R.md_gifts({})[0]["caption"] == "GIFT SEARCH"
    assert R.md_gifts(bare_hollow)[0] == {"caption": "STARTER GIFT", "named": True,
                                          "names": ["Torn Bandolier"]}
    assert R.md_gifts(hollow_md)[0]["names"] == ["Stone Tomb"]
