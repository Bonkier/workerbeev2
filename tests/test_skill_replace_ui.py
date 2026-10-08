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


def test_the_hint_no_longer_runs_its_sentences_together():
    from gui_v2.copy import MD_SKILL_REPLACEMENT_HINT_RICH as hint
    assert "market.Input" not in hint and "skilland" not in hint
    assert ".  " not in hint and "  " not in hint
