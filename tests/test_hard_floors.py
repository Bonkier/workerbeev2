# SPDX-License-Identifier: GPL-3.0-or-later
"""Hard from a floor: the Packs tab's Hard switches, the floors they lock,
the pack pool each floor lists, what the run builder and the start overlay
make of it, and the Extreme lock."""
import pytest

from gui_v2 import run_config as RC
from gui_v2 import run_summary as RS


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
    pg._loading = True
    pg._custom_run.setChecked(False)          # the live config may have a scripted run on
    pg._difficulty.set_selected("Normal")
    pg._on_difficulty("Normal")
    yield pg
    destroy(pg)


def _chips(page, floor):
    return set(page._floor_packs._chips[floor])


def test_extreme_is_locked_and_the_behaviour_toggle_is_gone(page):
    assert "Extreme" in page._difficulty._locked
    assert "pack_search" not in page.state()["behaviour"]
    assert "pack_search" not in page._behaviour


def test_a_hard_switch_locks_the_floors_after_it_and_frees_the_ones_before(page):
    from gui_v2.mirror_dungeon_page import FLOORS, HARD_FLOORS
    rows = page._hard_rows
    assert all(not t.isChecked() and t.isEnabled() for t in rows.values())
    rows[3].setChecked(True)
    assert page._hard_from == 3 and page.state()["hard_from_floor"] == 3
    assert [rows[f].isChecked() for f in (1, 2, 3, 4, 5)] == [False, False, True, True, True]
    assert [rows[f].isEnabled() for f in (1, 2, 3, 4, 5)] == [True, True, True, False, False]
    assert _chips(page, 2) == set(FLOORS[2]) and _chips(page, 4) == set(HARD_FLOORS[4])
    rows[2].setChecked(True)                               # an earlier flip wins
    assert page._hard_from == 2 and rows[3].isChecked() and not rows[3].isEnabled()
    assert _chips(page, 3) == set(HARD_FLOORS[3])
    rows[2].setChecked(False)                              # off at the flip: all Normal again
    assert page._hard_from is None and page.state()["hard_from_floor"] == 0
    assert all(not t.isChecked() and t.isEnabled() for t in rows.values())
    assert _chips(page, 4) == set(FLOORS[4])


def test_hard_is_a_flip_on_floor_one_and_the_switches_steer_the_difficulty(page):
    from gui_v2.mirror_dungeon_page import HARD_FLOORS
    rows = page._hard_rows
    page._difficulty.set_selected("Hard")
    page._on_difficulty("Hard")
    assert all(t.isChecked() for t in rows.values())
    assert rows[1].isEnabled() and not any(rows[f].isEnabled() for f in (2, 3, 4, 5))
    assert "switch that floor off first" in rows[4].toolTip()
    assert page.state()["hard_from_floor"] == 1 and _chips(page, 1) == set(HARD_FLOORS[1])
    rows[1].setChecked(False)                                  # off at floor 1: Normal
    assert page._difficulty.selected() == "Normal" and page._hard_from is None
    assert all(t.isEnabled() and not t.isChecked() for t in rows.values())
    rows[3].setChecked(True)                                   # a later flip keeps Normal
    assert page._difficulty.selected() == "Normal" and page.state()["difficulty"] == "Normal"
    rows[1].setChecked(True)                                   # floor 1: Hard
    assert page._difficulty.selected() == "Hard" and page._hard_from == 1
    page._difficulty.set_selected("Normal")
    page._on_difficulty("Normal")
    assert all(t.isEnabled() and not t.isChecked() for t in rows.values())


def test_picking_a_scripted_run_seeds_its_flip_and_leaves_the_switches_free(page):
    page._loading = False
    page._custom_run.setChecked(True)
    page._seed_flip(RC.HOLLOW_LABEL)                      # what the strategy signal does
    assert page._hard_from == 5 and page._hard_rows[5].isChecked()
    assert all(page._hard_rows[f].isEnabled() for f in (1, 2, 3, 4, 5))
    page._hard_rows[3].setChecked(True)                   # the user's to change
    assert page._hard_from == 3 and page.state()["hard_from_floor"] == 3
    page._seed_flip(RC.SAIKAI_LABEL)
    assert page._hard_from == 4
    page._seed_flip(RC.THRILL_LABEL)
    assert page._hard_from is None and all(t.isEnabled() for t in page._hard_rows.values())
    page._seed_flip("F3 Hard")
    assert page._hard_from == 3
    page._custom_run.setChecked(False)


def test_a_saved_flip_comes_back_and_a_saved_extreme_reads_as_hard(page, monkeypatch):
    import gui_v2.mirror_dungeon_page as M
    s = page.state()
    s.update(difficulty="Normal", hard_from_floor=4, custom_run=False)
    monkeypatch.setattr(M, "load_section", lambda *a, **k: dict(s))
    page._restore_state()
    assert page._hard_from == 4 and page._hard_rows[5].isChecked() and not page._hard_rows[5].isEnabled()
    assert page._hard_rows[3].isEnabled() and not page._hard_rows[3].isChecked()
    s.update(difficulty="Extreme", hard_from_floor=0)
    page._restore_state()
    assert page._difficulty.selected() == "Hard" and page._hard_from == 1
    s.update(difficulty="Hard", hard_from_floor=0)             # an older save
    page._restore_state()
    assert page._hard_from == 1 and page._hard_rows[1].isEnabled()


def test_the_builder_flips_at_the_switched_floor():
    md = {"difficulty": "Normal", "hard_from_floor": 3,
          "teams": [{"name": "Burn", "affinities": ["Burn"]}]}
    _count, _teams, settings, hard = RC.build_md_run(md, {}, {})
    assert hard is True and settings["hard_from_floor"] == 3
    md["hard_from_floor"] = 0
    assert RC.build_md_run(md, {}, {})[3] is False
    md.update(difficulty="Hard", hard_from_floor=3)          # Hard is Hard from floor 1
    _c, _t, settings, hard = RC.build_md_run(md, {}, {})
    assert hard is True and settings["hard_from_floor"] == 1
    assert settings["pack_search"] is True


def test_the_overlay_names_the_flip_and_the_search_floors():
    rows = {k: v for section in RS.md_summary({"difficulty": "Normal", "hard_from_floor": 3,
                                                "pack_refreshes": 2,
                                                "pack_search_cfg": {"floors": {
                                                    "3": {"enabled": True, "pack": "Line 2"},
                                                    "5": {"enabled": True, "pack": "Line 4"},
                                                    "4": {"enabled": False, "pack": "Line 2"}}}})
            for k, v in section[1]}
    assert rows["Difficulty"] == "Normal, then Hard from floor 3"
    assert rows["Pack search"] == "Floors 3 and 5, 2 refreshes"
    rows = {k: v for section in RS.md_summary({"difficulty": "Hard"}) for k, v in section[1]}
    assert rows["Difficulty"] == "Hard" and rows["Pack search"] == "No floor configured, 0 refreshes"



def test_the_packs_tab_leads_the_scripted_runs_own_packs():
    md = {"custom_run": True, "custom_strategy": RC.SAIKAI_LABEL,
          "packs": {"2": {"TheForgotten": "priority"}, "3": {"NagelundHammer": "avoid"}},
          "global_packs": {"AutomatedFactory": "priority"}}
    _count, teams, _settings, _hard = RC.build_md_run(md, {}, {})
    packs, pins = teams[0]["priority"]
    assert packs[:2] == ["TheForgotten", "AutomatedFactory"]            # the user's first
    assert pins["TheForgotten"] == [2] and "AutomatedFactory" not in pins
    assert "FlatbrokeGamblers" in packs and pins["FlatbrokeGamblers"] == 1  # the script's follow
    assert "NagelundHammer" in teams[0]["avoid"][0]
    hollow = dict(md, custom_strategy=RC.HOLLOW_LABEL)
    packs, pins = RC.build_md_run(hollow, {}, {})[1][0]["priority"]
    assert packs[0] == "TheForgotten" and pins["Line2"] == 5



def test_the_scripted_runs_follow_the_pages_flip_and_keep_their_own_without_one():
    hollow = {"custom_run": True, "custom_strategy": RC.HOLLOW_LABEL}
    assert RC.build_md_run(hollow, {}, {})[2]["hard_from_floor"] == 5         # an older save
    assert RC.build_md_run(dict(hollow, hard_from_floor=3), {}, {})[2]["hard_from_floor"] == 3
    assert RC.build_md_run(dict(hollow, hard_from_floor=0), {}, {})[2]["hard_from_floor"] == 99
    saikai = {"custom_run": True, "custom_strategy": RC.SAIKAI_LABEL}
    _c, _t, settings, hard = RC.build_md_run(saikai, {}, {})
    assert settings["hard_from_floor"] == 4 and hard is True
    _c, _t, settings, hard = RC.build_md_run(dict(saikai, hard_from_floor=0), {}, {})
    assert settings["hard_from_floor"] == 99 and hard is False and settings["pack_search"] is True
    assert RC.build_md_run(dict(saikai, hard_from_floor=1), {}, {})[2]["hard_from_floor"] == 1
    thrill = {"custom_run": True, "custom_strategy": RC.THRILL_LABEL}
    assert RC.build_md_run(thrill, {}, {})[3] is False
    _c, _t, settings, hard = RC.build_md_run(dict(thrill, hard_from_floor=2), {}, {})
    assert settings["hard_from_floor"] == 2 and hard is True
    rows = {k: v for section in RS.md_summary(dict(hollow, hard_from_floor=3)) for k, v in section[1]}
    assert rows["Difficulty"] == "Normal, then Hard from floor 3"
    rows = {k: v for section in RS.md_summary(dict(saikai, hard_from_floor=0, saikai_floor10=True))
            for k, v in section[1]}
    assert rows["Difficulty"] == "Normal on every floor, leaving after floor 10"



def test_every_run_takes_the_build_tabs_graces_and_falls_back_to_its_own():
    picked = {"Star of the Beginning": 1, "Star Shower": 2}
    for label in (RC.SAIKAI_LABEL, RC.THRILL_LABEL, RC.HOLLOW_LABEL):
        md = {"custom_run": True, "custom_strategy": label, "grace": picked}
        buff = RC.build_md_run(md, {}, {})[2]["buff"]
        assert buff[0] == 1 and buff[3] == 2 and sum(1 for v in buff if v) == 2, label
        none = RC.build_md_run({"custom_run": True, "custom_strategy": label}, {}, {})[2]["buff"]
        assert [n for n, v in zip(RC._GRACE_ORDER, none) if v] == RC.PRESET_GRACES[label]
        rows = {k: v for section in RS.md_summary({"custom_run": True, "custom_strategy": label})
                for k, v in section[1]}
        assert rows["Graces"] == ", ".join(RC.PRESET_GRACES[label]) + " (none picked, so the run's own)", label
    plain = {k: v for section in RS.md_summary({"difficulty": "Hard"}) for k, v in section[1]}
    assert plain["Graces"] == "None"
    picked_rows = {k: v for section in RS.md_summary({"difficulty": "Hard", "grace": picked}) for k, v in section[1]}
    assert picked_rows["Graces"] == "Star of the Beginning, Star Shower +"
