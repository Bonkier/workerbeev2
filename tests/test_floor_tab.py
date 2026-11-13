# SPDX-License-Identifier: GPL-3.0-or-later
"""The Floor Packs/Market tab: the floor bar, the run-wide shop steps, a
floor's own market tags and shop steps, how they reach the run and the
shop's floor switch, and what the start overlay says about them."""
from __future__ import annotations

import pytest

pytest.importorskip("PySide6")


@pytest.fixture
def page(monkeypatch):
    from PySide6.QtWidgets import QApplication
    from tests.conftest import destroy
    QApplication.instance() or QApplication([])
    import gui_v2.settings as st
    import gui_v2.mirror_dungeon_page as M
    monkeypatch.setattr(st, "save_section", lambda *a, **k: None)
    monkeypatch.setattr(M, "save_section", lambda *a, **k: None)
    pg = M.MirrorDungeonPage()
    pg._custom_run.setChecked(False)          # the live config may have a scripted run on
    pg._apply_custom_run(False)
    yield pg
    destroy(pg)


def _two(page):
    names = sorted(page._market_gallery._tiles)
    if len(names) < 2:
        pytest.skip("market catalog unavailable")
    return names[:2]


def test_the_tabs_and_the_floor_bar(page):
    assert page._TABS == ("General", "Build", "Floor Packs/Market", "EGO Gift Search")
    assert list(page._floor_bar._buttons) == [
        "All floors", "Floor 1", "Floor 2", "Floor 3", "Floor 4", "Floor 5"]
    assert page._floor_stack.count() == 6 and page._floor_stack.currentIndex() == 0
    assert not page._floor_packs._tab_scroll.isVisibleTo(page)   # the floor bar drives it
    page._floor_bar._buttons["Floor 3"].click()
    assert page._market_floor == 3 and page._floor_stack.currentIndex() == 3
    assert page._floor_packs._stack.currentIndex() == 3
    assert page._market_scope.text() == "Floor 3"
    page._floor_bar._buttons["All floors"].click()
    assert page._market_floor is None and page._floor_packs._stack.currentIndex() == 0
    assert page._market_scope.text() == "All floors"


def test_the_packs_are_card_tiles_six_to_a_row(page):
    from gui_v2 import widgets as W
    from gui_v2.theme import Sizing
    packs = page._floor_packs
    tiles = packs._chips[1]
    assert tiles and packs.PER_ROW == 6
    gap = packs._stack.widget(0).layout().spacing()      # the grid's own gap
    assert gap == Sizing.SPACE_SM

    def art_for(width):
        art = (width - 2 - 5 * gap) // 6 - 2 * W.PackTile._PAD
        return art - art % 4

    packs._fit_tiles(1000)                                # what a resize does
    art = art_for(1000)
    for tile in tiles.values():
        assert isinstance(tile, W.PackTile)
        assert tile._pix is not None and not tile._pix.isNull(), tile.text()
        assert tile._pix.width() == art and tile._pix.height() > art   # portrait card
        assert tile.sizeHint().width() == art + 2 * tile._PAD
        assert tile.sizeHint().height() > tile._pix.height() + 2 * tile.fontMetrics().lineSpacing()
    assert 6 * (art + 2 * W.PackTile._PAD) + 5 * gap < 1000
    tile = next(iter(tiles.values()))
    seen = []
    tile.state_changed.connect(lambda name, st: seen.append((name, st)))
    tile.click()
    assert tile.state() == "priority" and seen == [(tile.text(), "priority")]
    tile.click()
    tile.click()
    assert tile.state() == "neutral" and len(seen) == 3
    page._hard_rows[3].setChecked(True)                   # the pools rebuild at the same width
    assert all(t._pix is not None and t._pix.width() == art
               for t in page._floor_packs._chips[4].values())
    packs._fit_tiles(700)                                 # narrower: every tile follows
    assert all(t._pix.width() == art_for(700) for t in packs._chips[4].values())
    assert all(t._pix.width() == art_for(700) for t in packs._global_chips.values())
    assert {w for _p, w in W._pack_arts} == {art_for(700)}   # one width live


def test_the_floor_bar_labels_have_room_for_the_bold_face(page):
    from PySide6.QtGui import QFont, QFontMetrics
    from gui_v2.theme import Fonts
    from gui_v2.widgets import ui_font
    bold = QFontMetrics(ui_font(Fonts.SIZE_SM, QFont.Weight.DemiBold))
    for label, btn in page._floor_bar._buttons.items():
        assert btn.minimumWidth() >= bold.horizontalAdvance(label) + 32


def test_the_shop_steps_are_the_behaviour_skips_the_other_way_round(page):
    from gui_v2 import run_config as RC
    steps = page._shop_steps
    assert set(steps) == {"skip_restshop", "skip_ego_check", "skip_ego_fusion",
                          "skip_ego_enhancing", "skip_ego_buying", "skip_sinner_healing"}
    assert not any(k in page._behaviour for k in steps)
    assert set(page._behaviour_groups) == {"RUN", "ON DEFEAT", "WHEN FINISHED"}
    for tog in steps.values():
        tog.setChecked(True)
    steps["skip_ego_fusion"].setChecked(False)
    beh = page.state()["behaviour"]
    assert beh["skip_ego_fusion"] is True and beh["skip_ego_buying"] is False
    settings = RC.build_settings(page.state())
    assert settings["skip_ego_fusion"] is True and settings["skip_ego_buying"] is False
    assert settings["market_floors"] == {}


def test_a_floor_keeps_its_own_tags_and_steps(page):
    from gui_v2 import run_config as RC
    a, b = _two(page)
    g = page._market_gallery
    g.reset()
    g.toggle_tag("buy", a)                                # run-wide: buy a
    page._floor_bar._buttons["Floor 2"].click()
    assert g.config()["buy"] == []                        # the floor starts clean
    g.toggle_tag("fuse", b)                               # floor 2: fuse b
    page._step_rows[2]["skip_ego_fusion"]._buttons["Off"].click()
    page._step_rows[3]["skip_ego_buying"]._buttons["On"].click()
    st = page.state()
    assert st["market_gifts"]["buy"] == [a]
    assert st["market_floors"]["normal"] == {           # Hollow's slot keeps its own
        "2": {"tags": {"keep_fuse": [], "keep_sell": [], "sell": [], "buy": [],
                       "fuse": [b], "enhance1": [], "enhance2": []},
              "steps": {"skip_ego_fusion": True}},
        "3": {"steps": {"skip_ego_buying": False}}}
    page._floor_bar._buttons["All floors"].click()
    assert g.config()["buy"] == [a] and g.config()["fuse"] == []
    page._floor_bar._buttons["Floor 2"].click()
    assert g.config()["fuse"] == [b] and g.config()["buy"] == []
    settings = RC.build_settings(st)
    assert settings["market_gifts"]["buy"] == [a]
    assert settings["market_floors"][2]["market_gifts"]["buy"] == [a]   # the run-wide tags join in
    assert settings["market_floors"][2]["market_gifts"]["fuse"] == [b]
    assert settings["market_floors"][2]["skip_ego_fusion"] is True
    assert settings["market_floors"][3] == {"skip_ego_buying": False}


def test_the_floor_settings_come_back_after_a_restart(page, monkeypatch):
    import gui_v2.mirror_dungeon_page as M
    from tests.conftest import destroy
    a, _b = _two(page)
    page._floor_bar._buttons["Floor 4"].click()
    g = page._market_gallery
    g.reset()
    g.toggle_tag("sell", a)
    page._step_rows[4]["skip_sinner_healing"]._buttons["Off"].click()
    saved = page.state()
    monkeypatch.setattr(M, "load_section", lambda name: saved)
    again = M.MirrorDungeonPage()
    try:
        assert again._market_floors["normal"][4]["tags"]["sell"] == [a]
        assert again._market_floors["normal"][4]["steps"] == {"skip_sinner_healing": True}
        assert again._step_rows[4]["skip_sinner_healing"].selected() == "Off"
        assert again._step_rows[1]["skip_sinner_healing"].selected() == "Default"
        assert again._market_floor is None and again._market_gallery.config() == saved["market_gifts"]
        again._floor_bar._buttons["Floor 4"].click()
        assert again._market_gallery.config()["sell"] == [a]
        assert again.state()["market_floors"] == saved["market_floors"]
    finally:
        destroy(again)


def test_each_strategy_has_its_own_floor_settings(page):
    from gui_v2 import run_config as RC
    from gui_v2.mirror_dungeon_page import SAIKAI_LABEL
    page._floor_bar._buttons["Floor 1"].click()
    page._step_rows[1]["skip_ego_buying"]._buttons["Off"].click()
    page._custom_run.setChecked(True)
    page._apply_custom_run(True)
    page._custom_strategy.set_selected(SAIKAI_LABEL)
    page._sync_run()
    assert page._market_slot == "saikai"
    assert page._step_rows[1]["skip_ego_buying"].selected() == "Default"
    page._step_rows[1]["skip_ego_fusion"]._buttons["Off"].click()
    st = page.state()
    assert st["market_floors"]["normal"]["1"]["steps"] == {"skip_ego_buying": True}
    assert st["market_floors"]["saikai"]["1"]["steps"] == {"skip_ego_fusion": True}
    assert RC.build_settings(st)["market_floors"] == {1: {"skip_ego_fusion": True}}
    page._custom_run.setChecked(False)
    page._apply_custom_run(False)
    assert page._market_slot == "normal"
    assert page._step_rows[1]["skip_ego_buying"].selected() == "Off"
    assert page._step_rows[1]["skip_ego_fusion"].selected() == "Default"


def test_floor_tags_lie_over_the_run_wide_ones():
    from gui_v2.run_config import merge_market_tags
    base = {"buy": ["A", "B"], "sell": ["C"], "keep_sell": ["D"],
            "enhance2": ["E"], "fuse": ["F"]}
    floor = {"buy": ["B", "G"], "keep_sell": ["C"], "enhance1": ["E"]}
    got = merge_market_tags(base, floor)
    assert got["buy"] == ["B", "G", "A"]                       # the floor's order first
    assert got["sell"] == [] and got["keep_sell"] == ["C", "D"]  # C is kept on this floor
    assert got["enhance1"] == ["E"] and got["enhance2"] == []    # one uptie here
    assert got["fuse"] == ["F"] and got["keep_fuse"] == []
    assert merge_market_tags(base, {}) == {**{m: [] for m in got}, **{k: list(v) for k, v in base.items()}}


def test_a_saved_floor_entry_is_read_back_defensively():
    from gui_v2.mirror_dungeon_page import _clean_market_floors
    raw = {"normal": {"2": {"tags": {"buy": ["A", 3], "junk": ["x"]},
                            "steps": {"skip_ego_fusion": True, "nope": True,
                                      "skip_ego_buying": "yes"}},
                      "9": {"steps": {"skip_ego_fusion": True}},
                      "3": {"tags": {"buy": []}}},
           "other": {"1": {"steps": {"skip_ego_fusion": True}}}}
    clean = _clean_market_floors(raw)
    assert set(clean) == {"normal", "saikai", "hollow"}
    assert clean["normal"] == {2: {"tags": {"keep_fuse": [], "keep_sell": [], "sell": [],
                                            "buy": ["A"], "fuse": [], "enhance1": [],
                                            "enhance2": []},
                                   "steps": {"skip_ego_fusion": True}}}
    assert _clean_market_floors(None) == {"normal": {}, "saikai": {}, "hollow": {}}


def test_hollow_keeps_its_gift_check_whatever_a_floor_says():
    from gui_v2 import run_config as RC
    md = {"custom_run": True, "custom_strategy": RC.HOLLOW_LABEL,
          "market_floors": {"hollow": {"2": {"steps": {"skip_ego_check": True,
                                                       "skip_ego_buying": True}}},
                            "normal": {"1": {"steps": {"skip_ego_fusion": True}}}}}
    _count, _teams, settings, _hard = RC.build_md_run(md, {}, {})
    floors = settings["market_floors"]
    assert floors[2]["skip_ego_buying"] is True and "skip_ego_check" not in floors[2]
    # An unseeded Hollow slot: the sheet's floor keeps lie under every floor.
    seed, seed_floors = RC.hollow_market_seed()
    assert set(floors) == {1, 2}                              # Grand Welcome's floors
    for fl, ent in seed_floors.items():
        for mode, names in ent["tags"].items():
            assert floors[int(fl)]["market_gifts"][mode][:len(names)] == names
    assert floors[1]["market_gifts"]["fuse"] == seed["fuse"]
    assert settings["market_gifts"]["fuse"] == seed["fuse"]


def test_hollows_plan_lies_under_an_unseeded_slot_only():
    from gui_v2 import run_config as RC
    from wbcore import hollow as H
    seed, floors = RC.hollow_market_seed()
    assert set(seed) == {"keep_fuse", "keep_sell", "sell", "buy", "fuse",
                         "enhance1", "enhance2"}
    assert seed["fuse"] == [H._CONCEIT, H._MIRROR, H._DECAY, H._SENSE]
    assert seed["keep_fuse"] == seed["keep_sell"] == [
        H._CONCEIT, H._DECAY, H.STARTING_GIFT, H._THREAD, H._MIRROR, H._SENSE]
    assert seed["enhance2"] == [H.STARTING_GIFT, H._MIRROR, H._SENSE]
    assert seed["buy"] == seed["sell"] == seed["enhance1"] == []
    # Grand Welcome is kept on floors 1 and 2 and is fuel from floor 3.
    assert floors == {"1": {"tags": {"keep_fuse": [H._WELCOME]}},
                      "2": {"tags": {"keep_fuse": [H._WELCOME]}}}
    assert RC.hollow_seeded(None) is False and RC.hollow_seeded({"buy": ["X"]}) is False
    assert RC.hollow_seeded({"fuse": [H._MIRROR]}) is True
    assert RC.hollow_slot_tags(None) == seed
    laid = RC.hollow_slot_tags({"buy": ["X"], "keep_sell": ["Y"]})
    assert laid["buy"] == ["X"] and laid["keep_sell"] == seed["keep_sell"] + ["Y"]
    assert laid["fuse"] == seed["fuse"]
    own = RC.hollow_slot_tags({"fuse": [H._MIRROR]})
    assert own["fuse"] == [H._MIRROR] and not own.get("keep_fuse")
    assert RC.hollow_floor_tags(None, {}) == floors
    assert RC.hollow_floor_tags({"fuse": [H._MIRROR]}, {}) == {}
    kept = RC.hollow_floor_tags(None, {2: {"steps": {"skip_ego_check": True}}})
    assert kept["2"] == {"steps": {"skip_ego_check": True},
                         "tags": {"keep_fuse": [H._WELCOME]}}
    assert kept["1"] == floors["1"]


def test_the_shop_lays_a_floors_settings_over_the_run_wide_ones(monkeypatch):
    from wbcore import shop as S
    from wbcore.utils import params as p
    monkeypatch.setattr(p, "MARKET_GIFTS", {"buy": ["A"], "fuse": []}, raising=False)
    monkeypatch.setattr(p, "SKIP_EGO_FUSION", False, raising=False)
    monkeypatch.setattr(p, "SKIP_EGO_BUYING", True, raising=False)
    monkeypatch.setattr(p, "MARKET_FLOORS", {
        2: {"market_gifts": {"buy": ["B", "A"]}, "skip_ego_fusion": True},
        3: {"skip_ego_buying": False}}, raising=False)
    monkeypatch.setattr(p, "SHOP_RUNWIDE", {}, raising=False)
    monkeypatch.setattr(p, "FLOOR_CONFIG_LOGGED", None, raising=False)
    monkeypatch.setattr(p, "LVL", 2, raising=False)
    S.snapshot_runwide()
    S.apply_floor_config()
    assert p.MARKET_GIFTS == {"buy": ["B", "A"]}
    assert p.SKIP_EGO_FUSION is True and p.SKIP_EGO_BUYING is True
    p.MARKET_GIFTS["buy"].append("scratch")                # the visit may scribble on it
    S.apply_floor_config(3)
    assert p.MARKET_GIFTS == {"buy": ["A"], "fuse": []}
    assert p.SKIP_EGO_FUSION is False and p.SKIP_EGO_BUYING is False
    S.apply_floor_config(4)
    assert p.MARKET_GIFTS == {"buy": ["A"], "fuse": []} and p.SKIP_EGO_BUYING is True
    assert p.SHOP_RUNWIDE["MARKET_GIFTS"] == {"buy": ["A"], "fuse": []}


def test_the_start_summary_lists_the_floor_settings():
    from gui_v2 import run_summary as RS
    md = {"market_controls": {"default_market_workflow": False},
          "market_gifts": {"buy": ["W"]},
          "market_floors": {"normal": {
              "1": {"steps": {"skip_ego_fusion": True}},
              "3": {"tags": {"fuse": ["X"], "buy": ["Y", "Z"], "keep_sell": ["Y"]},
                    "steps": {"skip_ego_fusion": False}}}}}
    rows = {label: value for _cap, items in RS.md_summary(md) for label, value in items}
    assert rows["Floor settings"] == "Floor 1: no fusion; Floor 3: buy 2, fuse 1, keep 1, fusion"
    assert "Floor settings" not in {l for _c, items in RS.md_summary({}) for l, _v in items}
    targets = next(g for g in RS.md_gifts(md) if g["caption"] == "MARKET TARGETS")
    assert targets["names"] == ["W", "Y", "Z", "X"]
