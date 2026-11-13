# SPDX-License-Identifier: GPL-3.0-or-later
"""The Build tab: grace cards like the in-game Grace of the Sisyphean Star
screen (icon, title, cost, + and ++, Select all graces, Enhance all) and the
card priority rows with their reward icons."""
from __future__ import annotations

import pytest

pytest.importorskip("PySide6")


@pytest.fixture(scope="module")
def qapp():
    from PySide6.QtWidgets import QApplication
    return QApplication.instance() or QApplication([])


@pytest.fixture
def page(qapp, monkeypatch):
    import gui_v2.settings as settings
    import gui_v2.mirror_dungeon_page as mdp
    monkeypatch.setattr(settings, "save_section", lambda *a, **k: None)
    monkeypatch.setattr(mdp, "save_section", lambda *a, **k: None)
    pg = mdp.MirrorDungeonPage()
    pg._custom_run.setChecked(False)
    yield pg
    pg.deleteLater()


def _states(page):
    return {n: c.state() for n, c in page._grace_chips.items()}


def _base_four(page):
    for i, c in enumerate(page._grace_chips.values()):
        c.set_state(1 if i < 4 else 0)
    page._refresh_grace_controls()


def test_every_grace_card_has_its_wiki_icon_title_and_cost(page):
    from gui_v2 import giftart
    from gui_v2.grace_info import GRACES
    for name, card in page._grace_chips.items():
        assert giftart.grace_icon(name), name
        assert not card._pix.isNull(), name
        assert GRACES[name]["cost"] > 0 and len(GRACES[name]["effects"]) == 3
    titles = [GRACES[n]["title"] for n in page._grace_chips]
    assert titles[3:7] == ["Star-shower", "Binary Star-shop", "Moon Star-shop",
                           "Favor of the Nebulae"]
    assert sum(g["cost"] for g in GRACES.values()) * 3 == 930   # the wiki's all-at-++ total


def test_a_click_takes_the_grace_and_the_levels_enhance_it(page):
    card = page._grace_chips["Chance Comet"]
    seen = []
    card.state_changed.connect(lambda n, s: seen.append((n, s)))
    card.set_state(0)
    card.click()
    assert card.state() == 1
    card._levels[2].click()
    assert card.state() == 2
    assert card._levels[2].isChecked() and not card._levels[3].isChecked()
    card._levels[2].click()                   # the same level again: back to base
    assert card.state() == 1 and not card._levels[2].isChecked()
    card._levels[3].click()
    assert card.state() == 3 and card._levels[3].isChecked()
    card._levels[2].click()
    assert card.state() == 2
    card.click()                              # taken at any level: a click drops it
    assert card.state() == 0 and not card._levels[2].isChecked()
    assert seen == [("Chance Comet", s) for s in (1, 2, 1, 3, 2, 0)]


def test_a_level_button_on_an_untaken_grace_takes_it_at_that_level(page):
    card = page._grace_chips["Perfected Possibility"]
    card.set_state(0)
    card._levels[3].click()
    assert card.state() == 3


def test_the_tooltip_shows_the_effects_of_the_chosen_level(page):
    card = page._grace_chips["Star of the Beginning"]
    card.set_state(0)
    assert "Starting Cost +150" in card.toolTip() and "10 starlight, 20 at +, 30 at ++" in card.toolTip()
    card.set_state(2)
    assert "Starting Cost +250" in card.toolTip() and "<b>+</b>" in card.toolTip()
    card.set_state(3)
    assert "Two Free Normal Refreshes" in card.toolTip()


def test_select_all_takes_every_grace_and_then_clears_them(page):
    for i, c in enumerate(page._grace_chips.values()):
        c.set_state(2 if i == 0 else 0)
    page._grace_all.click()
    states = _states(page)
    assert states["Star of the Beginning"] == 2 and all(states.values())
    page._grace_all.click()
    assert not any(_states(page).values())


def test_enhance_all_raises_the_taken_graces_and_back(page):
    _base_four(page)
    page._grace_enhance[2].click()
    assert [s for s in _states(page).values() if s] == [2, 2, 2, 2]
    assert page._grace_enhance[2].isChecked() and not page._grace_enhance[3].isChecked()
    page._grace_enhance[3].click()
    assert [s for s in _states(page).values() if s] == [3, 3, 3, 3]
    assert page._grace_enhance[3].isChecked()
    page._grace_enhance[3].click()
    assert [s for s in _states(page).values() if s] == [1, 1, 1, 1]
    assert not page._grace_enhance[2].isChecked() and not page._grace_enhance[3].isChecked()
    for c in page._grace_chips.values():
        c.set_state(0)
    page._refresh_grace_controls()
    assert not page._grace_enhance[2].isEnabled() and not page._grace_enhance[3].isEnabled()


def test_the_starlight_total_counts_every_level(page):
    _base_four(page)
    assert page._grace_total.text() == "60 starlight"
    page._grace_chips["Star of the Beginning"]._levels[3].click()
    assert page._grace_total.text() == "80 starlight"


def test_the_graces_reach_the_run_as_the_buff_list(page):
    from gui_v2 import run_config as RC
    _base_four(page)
    page._grace_chips["Chance Comet"].set_state(3)
    page._grace_chips["Star Shower"].set_state(2)
    st = page.state()
    assert st["grace"]["Chance Comet"] == 3 and st["grace"]["Star Shower"] == 2
    assert RC.build_settings(st)["buff"] == [1, 1, 1, 2, 0, 0, 0, 0, 3, 0]


def test_card_priority_rows_carry_the_reward_icons(page):
    from gui_v2 import giftart
    lst = page._card_priority
    assert lst.count() == 5
    for i in range(lst.count()):
        assert not lst.item(i).icon().isNull(), lst.item(i).text()
    for name in ("Cost + Gift", "Cost", "Gift", "Resource", "Starlight"):
        assert giftart.reward_icon(name), name
    lst.set_state(["Gift", "Cost", "Cost + Gift", "Resource", "Starlight"], [])
    assert lst.order()[0] == "Gift" and not lst.item(0).icon().isNull()


def test_the_starter_gifts_are_listed_per_keyword_with_their_art(page):
    from wbcore import starter_gifts as SG
    from gui_v2.mirror_dungeon_page import _StarterTile
    page._set_starter_pick("")                 # the live config may hold a pick
    assert list(page._starter_tiles) == list(SG.STARTER_GIFTS)
    for keyword, names in SG.STARTER_GIFTS.items():
        tiles = page._starter_tiles[keyword]
        assert list(tiles) == list(names)
        for name, tile in tiles.items():
            assert isinstance(tile, _StarterTile) and not tile._pix.isNull(), name
            assert tile._usual == (name == SG.usual_pick(keyword))
            assert not tile.isChecked()
    assert page.state()["starter_gift"] == ""


def test_a_click_picks_the_gift_and_a_second_click_clears_it(page):
    tiles = page._starter_tiles["Burn"]
    every = [t for row in page._starter_tiles.values() for t in row.values()]
    tiles["Fiery Down"].click()
    assert page.state()["starter_gift"] == "Fiery Down"
    assert tiles["Fiery Down"].isChecked() and not tiles["Hellterfly's Dream"].isChecked()
    tiles["Pain of Stifled Rage"].click()
    assert page.state()["starter_gift"] == "Pain of Stifled Rage"
    assert not tiles["Fiery Down"].isChecked()
    page._starter_tiles["Poise"]["Stone Tomb"].click()   # one pick in all, any keyword's
    assert page.state()["starter_gift"] == "Stone Tomb"
    assert [t.name() for t in every if t.isChecked()] == ["Stone Tomb"]
    page._starter_tiles["Poise"]["Stone Tomb"].click()
    assert page.state()["starter_gift"] == ""
    assert not any(t.isChecked() for t in every)


def test_a_saved_pick_comes_back_and_an_unknown_one_is_dropped(page, monkeypatch):
    import gui_v2.mirror_dungeon_page as mdp
    saved = {"starter_gift": "Resolution"}
    monkeypatch.setattr(mdp, "load_section",
                        lambda name: saved if name == "mirror" else {})
    page._restore_state()
    assert page.state()["starter_gift"] == "Resolution"
    assert page._starter_tiles["Slash"]["Resolution"].isChecked()
    saved["starter_gift"] = "Nope"
    page._restore_state()
    assert page.state()["starter_gift"] == ""
    assert not page._starter_tiles["Slash"]["Resolution"].isChecked()


def test_the_build_tab_starts_at_the_top_with_the_starter_card_below(page):
    sa = page._tab_stack.widget(list(page._TABS).index("Build"))
    lay = sa.widget().layout()
    assert lay.itemAt(0).layout() is not None           # the grace and card columns
    assert lay.itemAt(1).widget() is page._starter_card
    assert lay.itemAt(lay.count() - 1).spacerItem() is not None
    assert lay.count() == 3


def test_no_run_locks_the_starter_card(page, monkeypatch):
    import gui_v2.mirror_dungeon_page as mdp
    from gui_v2.run_config import HOLLOW_LABEL, SAIKAI_LABEL
    monkeypatch.setattr(mdp, "load_section", lambda name: {})
    tiles = page._starter_tiles
    every = [t for row in tiles.values() for t in row.values()]
    tiles["Burn"]["Fiery Down"].click()
    for strategy in (HOLLOW_LABEL, SAIKAI_LABEL):
        page._custom_run.setChecked(True)
        page._apply_custom_run(True)
        page._custom_strategy.set_selected(strategy)
        page._sync_run()
        assert all(t.isEnabled() for t in every)
        assert [t.name() for t in every if t.isChecked()] == ["Fiery Down"]
        assert page.state()["starter_gift"] == "Fiery Down"
    tiles["Pierce"]["Torn Bandolier"].click()     # Hollow's own gift is a pick like any other
    assert page.state()["starter_gift"] == "Torn Bandolier"
    page._custom_run.setChecked(False)
    page._apply_custom_run(False)
    page._sync_run()
    assert all(t.isEnabled() for t in every)
    assert [t.name() for t in every if t.isChecked()] == ["Torn Bandolier"]
