# SPDX-License-Identifier: GPL-3.0-or-later
"""The Skill Replacement block: a real on/off switch per sinner, numbered
rows, and one state shared by the switch, the chip and the saved config."""

import pytest
from PySide6.QtWidgets import QApplication

_app = QApplication.instance() or QApplication([])


@pytest.fixture
def page(monkeypatch):
    import gui_v2.settings as st
    import gui_v2.mirror_dungeon_page as M
    # Never write the live config from a test.
    monkeypatch.setattr(st, "save_section", lambda *a, **k: None)
    monkeypatch.setattr(st, "save_settings", lambda *a, **k: None)
    monkeypatch.setattr(M, "save_section", lambda *a, **k: None)
    pg = M.MirrorDungeonPage()
    pg._view.set_selected("Advanced")       # the saved view may be Basic
    pg._show_view("Advanced")
    pg._loading = True
    # Start from a known state whatever the saved config holds.
    for name in list(pg._skill_active):
        pg._set_skill_active(name, False)
    pg._on_skill_sinner_selected("Faust")
    pg._on_skill_sinner_selected("Yi Sang")
    return pg


def _dimmed(pg):
    return pg._skill_priority_stack._cards[0]._text.styleSheet().startswith("color")


def test_rows_are_numbered_in_priority_order(page):
    stack = page._skill_priority_stack
    assert [c._rank.text() for c in stack._cards] == ["1", "2", "3"]
    assert [c.swap() for c in stack._cards] == page._skill_order["Yi Sang"]


def test_the_switch_turns_a_sinner_on_and_marks_its_chip(page):
    assert not page._skill_toggle.isChecked() and _dimmed(page)
    page._skill_toggle.setChecked(True)
    assert "Yi Sang" in page._skill_active
    assert page._skill_chips["Yi Sang"].is_active()
    assert not _dimmed(page)
    assert "Yi Sang" in page.state()["skill_replace"]["active"]


def test_double_clicking_the_chip_moves_the_switch_too(page):
    page._on_skill_sinner_toggle_active("Yi Sang")
    assert page._skill_toggle.isChecked() and not _dimmed(page)
    page._on_skill_sinner_toggle_active("Yi Sang")
    assert not page._skill_toggle.isChecked() and _dimmed(page)
    assert "Yi Sang" not in page._skill_active


def test_switching_sinner_shows_that_sinners_own_state(page):
    page._skill_toggle.setChecked(True)             # Yi Sang on
    page._on_skill_sinner_selected("Faust")
    assert not page._skill_toggle.isChecked() and _dimmed(page)
    page._on_skill_sinner_selected("Yi Sang")
    assert page._skill_toggle.isChecked() and not _dimmed(page)


def test_a_dimmed_row_is_still_editable(page):
    card = page._skill_priority_stack._cards[0]
    assert _dimmed(page) and card._spin.isEnabled()
    card._spin.setValue(3)
    assert page._skill_repeats["Yi Sang"][card.swap()] == 3


def test_the_block_is_capped_in_width(page):
    import gui_v2.mirror_dungeon_page as M
    assert page._skill_priority_stack.parentWidget().parentWidget() \
        .maximumWidth() == M._SKILL_BLOCK_W


def test_the_names_sit_beside_the_block_level_with_its_rows(page):
    import gui_v2.mirror_dungeon_page as M
    from PySide6.QtWidgets import QLabel
    page.resize(1100, 2400)
    page.show()
    _app.processEvents()

    def top(w):
        return w.mapTo(page, w.rect().topLeft()).y()

    def bottom(w):
        return w.mapTo(page, w.rect().bottomLeft()).y()

    details = page._skill_details
    assert details.width() == M._SKILL_BLOCK_W
    chips = list(page._skill_chips.values())
    cards = page._skill_priority_stack._cards
    assert len(chips) == 12 and M._SKILL_CHIP_COLS == 4

    # Every name is to the right of the block.
    right_edge = details.mapTo(page, details.rect().topRight()).x()
    assert min(c.mapTo(page, c.rect().topLeft()).x() for c in chips) > right_edge

    # Each name row is level with a swap row, top and bottom.
    for i, card in enumerate(cards):
        for chip in chips[i * 4:i * 4 + 4]:
            assert (top(chip), bottom(chip)) == (top(card), bottom(card))

    # And the two captions share a line.
    caps = {w.text(): top(w) for w in page.findChildren(QLabel)
            if w.text() in ("PRIORITY", "SINNERS")}
    assert caps["PRIORITY"] == caps["SINNERS"]
    page.hide()


def test_the_swap_floors_default_to_every_floor_and_follow_each_other(page):
    from PySide6.QtCore import QEvent, QPointF, Qt
    from PySide6.QtGui import QMouseEvent
    from PySide6.QtWidgets import QApplication
    import gui_v2.mirror_dungeon_page as M
    assert page._swap_floors == {1, 2, 3, 4, 5}
    assert page.state()["skill_replace"]["skip_floors"] == []
    assert len(page._swap_strips) == 2 and len(page._swap_rows) == 5
    assert all(isinstance(s, M._FloorPicks) and s.floors() == {1, 2, 3, 4, 5}
               for s in page._swap_strips)
    assert page._swap_labels[0].text() == "Skills will be swapped on every shop."
    page._swap_rows[2].setChecked(False)                  # a floor page's switch
    assert page._swap_floors == {1, 3, 4, 5}
    assert page.state()["skill_replace"]["skip_floors"] == [2]
    assert all(s.floors() == {1, 3, 4, 5} for s in page._swap_strips)
    assert page._swap_labels[1].text() == "Skills will be swapped on floors 1, 3, 4 and 5."
    picks = page._swap_strips[0]                          # a cell on the General card
    x = 3 * (picks._CELL_W + picks._GAP) + picks._CELL_W / 2
    c = QPointF(x, picks._CELL_H / 2)
    assert picks._cell_at(int(x)) == 4
    QApplication.sendEvent(picks, QMouseEvent(
        QEvent.Type.MouseButtonRelease, c, c, c, Qt.MouseButton.LeftButton,
        Qt.MouseButton.NoButton, Qt.KeyboardModifier.NoModifier))
    assert not page._swap_rows[4].isChecked()
    assert page.state()["skill_replace"]["skip_floors"] == [2, 4]
    page._swap_strips[1].floor_toggled.emit(5, False)
    assert page._swap_labels[0].text() == "Skills will be swapped on floors 1 and 3."
    for f in (1, 3):
        page._swap_strips[1].floor_toggled.emit(f, False)
    assert page._swap_labels[0].text() == "No floor picked: skills will not be swapped."
    page._swap_rows[3].setChecked(True)
    assert page._swap_labels[0].text() == "Skills will be swapped on floor 3."
    assert page._swap_strips[0]._tip(3).startswith("Skills will be swapped on floor 3")
    assert page._swap_strips[0]._tip(1) == "Click to swap skills on floor 1 too."


def test_the_swap_floors_come_back_from_a_save_and_default_when_missing(page, monkeypatch):
    import gui_v2.mirror_dungeon_page as M
    s = page.state()
    s["skill_replace"]["skip_floors"] = [1, "5", "x", 9, True]
    monkeypatch.setattr(M, "load_section", lambda *a, **k: dict(s))
    page._restore_state()
    assert page._swap_floors == {2, 3, 4}
    assert not page._swap_rows[1].isChecked() and page._swap_rows[2].isChecked()
    assert all(st.floors() == {2, 3, 4} for st in page._swap_strips)
    del s["skill_replace"]["skip_floors"]
    page._restore_state()
    assert page._swap_floors == {1, 2, 3, 4, 5}
    del s["skill_replace"]
    page._swap_rows[2].setChecked(False)
    page._restore_state()
    assert page._swap_floors == {1, 2, 3, 4, 5}


def test_the_run_builder_and_the_summary_carry_the_floors_left_dark():
    from gui_v2 import run_config as RC
    from gui_v2 import run_summary as RS
    md = {"difficulty": "Normal", "teams": [{"name": "Burn", "affinities": ["Burn"]}],
          "skill_replace": {"active": ["Faust"], "order": {}, "repeats": {},
                            "skip_floors": ["2", 4, "x", 0, 6]}}
    _c, _t, settings, _h = RC.build_md_run(md, {}, {})
    assert settings["skill_replace"]["skip_floors"] == [2, 4]
    rows = {l: v for _c, items in RS.md_summary(md) for l, v in items}
    assert rows["Skill replacement"] == "Faust on floors 1, 3 and 5"
    md["skill_replace"]["skip_floors"] = [1, 2, 3, 4, 5]
    rows = {l: v for _c, items in RS.md_summary(md) for l, v in items}
    assert rows["Skill replacement"] == "Faust on no floor"
    md["skill_replace"].pop("skip_floors")
    assert RC.build_md_run(md, {}, {})[2]["skill_replace"]["skip_floors"] == []
    rows = {l: v for _c, items in RS.md_summary(md) for l, v in items}
    assert rows["Skill replacement"] == "Faust"
    assert RC.floors_phrase({3}) == "floor 3" and RC.floors_phrase(()) == "no floor"
    assert RC.floors_phrase([5, 1]) == "floors 1 and 5"


def test_the_shop_skips_the_skill_offers_on_a_floor_left_dark(monkeypatch):
    from wbcore import shop as S
    from wbcore.utils import params as p
    monkeypatch.setattr(p, "SKILL_REPLACE_ACTIVE", {"Faust"}, raising=False)
    monkeypatch.setattr(p, "SKILL_REPLACE_SKIP_FLOORS", {2, 3}, raising=False)
    monkeypatch.setattr(p, "SKILL_REPLACE_USED_THIS_SHOP", 0, raising=False)
    monkeypatch.setattr(p, "SUPER", "shop", raising=False)
    scanned = []
    monkeypatch.setattr(S, "_scan_active_sinner_offer",
                        lambda: scanned.append(1) or (None, None, None))
    monkeypatch.setitem(S.PTH, S._SKILL_REPLACE_MENU, S.PTH.get(S._SKILL_REPLACE_MENU, "x"))
    monkeypatch.setattr(p, "LVL", 3, raising=False)
    assert S.do_skill_replace() == 0 and scanned == []
    monkeypatch.setattr(p, "LVL", 4, raising=False)
    assert S.do_skill_replace() == 0 and scanned == [1]
    monkeypatch.setattr(p, "SKILL_REPLACE_SKIP_FLOORS", set(), raising=False)
    monkeypatch.setattr(p, "LVL", 2, raising=False)
    assert S.do_skill_replace() == 0 and scanned == [1, 1]
