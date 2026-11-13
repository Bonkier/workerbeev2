# SPDX-License-Identifier: GPL-3.0-or-later
"""The Basic view: the Basic/Advanced switch, the owner's presets and what
they write, and the user's own configs."""
from __future__ import annotations

import pytest

pytest.importorskip("PySide6")


@pytest.fixture
def store(monkeypatch):
    """Settings kept in memory; the page and the presets read and write it."""
    from PySide6.QtWidgets import QApplication
    QApplication.instance() or QApplication([])
    import gui_v2.settings as st
    import gui_v2.mirror_dungeon_page as M
    import gui_v2.presets as P
    data = {}
    for mod in (st, M, P):
        monkeypatch.setattr(mod, "load_section",
                            lambda name: data.get(name, {}))
        monkeypatch.setattr(mod, "save_section",
                            lambda name, value: data.__setitem__(name, value))
    return data


@pytest.fixture
def page(store):
    from tests.conftest import destroy
    import gui_v2.mirror_dungeon_page as M
    pg = M.MirrorDungeonPage()
    yield pg
    destroy(pg)


def _shows(widget, page):
    return widget.isVisibleTo(page)


def test_a_fresh_install_opens_basic_and_the_switch_is_remembered(page, store):
    assert page._view.selected() == "Basic"
    assert page._view_stack.currentIndex() == 0
    assert not _shows(page._tabbar, page) and not _shows(page._rule, page)
    assert page._header._actions_row.indexOf(page._view) == 0   # beside Start
    page._view._buttons["Advanced"].click()
    assert page._view_stack.currentWidget() is page._tab_stack
    assert _shows(page._tabbar, page) and _shows(page._rule, page)
    assert store["md_view"] == {"mode": "advanced"}
    page._view._buttons["Basic"].click()
    assert store["md_view"] == {"mode": "basic"}
    assert page._view_stack.currentIndex() == 0


def test_an_existing_setup_opens_advanced_unless_a_view_was_kept(store):
    from tests.conftest import destroy
    import gui_v2.mirror_dungeon_page as M
    store["mirror"] = {"run_count": 3}
    pg = M.MirrorDungeonPage()
    assert pg._view.selected() == "Advanced" and _shows(pg._tabbar, pg)
    destroy(pg)
    store["md_view"] = {"mode": "basic"}
    pg = M.MirrorDungeonPage()
    assert pg._view.selected() == "Basic"
    destroy(pg)


def test_a_tab_is_only_in_the_advanced_view(page):
    assert page._view.selected() == "Basic"
    page._tabbar._buttons["Build"].click()
    assert page._view.selected() == "Advanced"
    assert page._tab_stack.currentIndex() == list(page._TABS).index("Build")


def test_the_basic_run_count_is_the_general_tabs(page):
    page._basic_runs.setValue(12)
    assert page._run_count.value() == 12
    page._run_count.setValue(3)
    assert page._basic_runs.value() == 3


def test_the_hollow_preset_writes_the_run_and_the_team(store):
    from gui_v2 import presets as P
    from gui_v2.run_config import HOLLOW_GRACE_SEED, HOLLOW_LABEL, hollow_market_seed
    store["mirror"] = {"run_count": 7, "behaviour": {"altf4": True, "winrate": False},
                       "grace_slots": {"normal": {"Star Shower": 2}},
                       "packs": {"1": {"TheOutcast": "priority"}}}
    store["app_settings"] = {"volume": 3, "custom_teams": {
        "SAIKAI": {"order": ["Outis"], "keyword": "Poise"},
        "Hollow": {"order": ["Faust", "Gregor"], "keyword": "Sinking"}}}
    assert P.apply("hollow")
    m = store["mirror"]
    assert m["custom_run"] is True and m["custom_strategy"] == HOLLOW_LABEL
    assert m["difficulty"] == "Normal" and m["hard_from_floor"] == 5
    assert m["run_count"] == 7                                   # stays the user's
    assert m["behaviour"]["altf4"] is True                       # not the preset's to set
    assert m["behaviour"]["winrate"] is True and m["behaviour"]["skip_ego_check"] is False
    assert {n: v for n, v in m["grace_slots"]["hollow"].items() if v} == HOLLOW_GRACE_SEED
    assert m["grace_slots"]["normal"] == {"Star Shower": 2}      # the other run's picks
    assert m["grace"] == m["grace_slots"]["hollow"]
    assert m["gift_search"] == ["Sharp Needle & Thread", "Grand Welcome"]
    assert m["starter_gift"] == "Torn Bandolier"       # the sheet's Normal-start gift
    seed, seed_floors = hollow_market_seed()           # the sheet's plan, as editable tags
    assert m["market_gifts_hollow"] == seed and seed["fuse"]
    assert m["market_floors"] == {"hollow": seed_floors}
    assert m["market_controls"]["default_market_workflow"] is False
    assert m["packs"]["1"]["FlatbrokeGamblers"] == "priority" and "TheOutcast" not in m["packs"]["1"]
    assert m["pack_search_cfg"]["floors"]["4"] == {"enabled": True, "pack": "Hatred and Despair"}
    app = store["app_settings"]
    assert app["volume"] == 3
    team = app["custom_teams"]["Hollow"]
    assert team["heal"] == "Hong Lu" and team["keyword"] == "Rupture"
    assert team["exclude"] == ["Faust"] and team["exclude_set"] is True
    assert "Faust" not in team["order"] and len(team["order"]) == 7
    assert app["custom_teams"]["SAIKAI"] == {"order": ["Outis"], "keyword": "Poise"}
    assert P.active(True, HOLLOW_LABEL) == "hollow"
    assert P.active(False, HOLLOW_LABEL) is None and P.active(True, "") is None


def test_the_saikai_preset_seeds_the_market_and_the_house_of_spiders(store):
    from gui_v2 import presets as P
    from gui_v2.run_config import SAIKAI_LABEL
    from wbcore.market_catalog import SAIKAI_MARKET_TAGS
    assert P.apply("saikai")
    m = store["mirror"]
    assert m["custom_run"] is True and m["custom_strategy"] == SAIKAI_LABEL
    assert m["hard_from_floor"] == 4
    assert m["market_gifts_saikai"] == {k: list(v) for k, v in SAIKAI_MARKET_TAGS.items()}
    assert m["gift_search"] == ["Spiderweb Entangled in Red"]
    assert m["starter_gift"] == "Stone Tomb"
    assert m["behaviour"]["swap_max_energy"] is False
    assert all(not f["enabled"] for f in m["pack_search_cfg"]["floors"].values())
    assert {v for fl in m["packs"].values() for v in fl.values()} == {"avoid"}
    team = store["app_settings"]["custom_teams"]["SAIKAI"]
    assert team["order"][0] == "Ryōshū" and len(team["order"]) == 7
    assert team["keyword"] == "Poise" and set(team["exclude"]) == set(team["order"])
    assert P.apply("nope") is False and P.get("nope") is None


def test_the_preset_rosters_and_pack_searches_are_real():
    import os
    from gui_v2 import presets as P
    from gui_v2.giftart import preset_portrait
    import gui_v2.mirror_dungeon_page as M
    from gui_v2.settings_page import _SINNER_NAMES
    for preset in P.PRESETS:
        for run, team in preset["teams"].items():
            assert set(team["order"]) <= set(_SINNER_NAMES), run
            assert set(team["exclude"]) <= set(_SINNER_NAMES), run
        floors = preset["mirror"]["pack_search_cfg"]["floors"]
        for fl, ent in floors.items():
            if ent["enabled"]:
                assert ent["pack"] in M._pack_search_names_for_floor(int(fl)), (preset["key"], fl)
        assert preset["tagline"] and preset["needs"]
        for label, text, portraits in preset["needs"]:
            assert label and portraits
            for pic in portraits:
                assert os.path.isfile(preset_portrait(pic["stem"])), pic["stem"]
                assert pic["name"]
    # The words are the owner's sheet's, cut to the lines that state a need.
    assert P.get("hollow")["tagline"].startswith("This new farming strategy")
    assert "THANKS" not in P.get("hollow")["tagline"]
    assert P.get("saikai")["needs"][0][2][0]["req"] == "Lv. 65+ \u00b7 UT 4+"
    assert [n[0] for n in P.get("hollow")["needs"]] == ["Identities", "Substitutes", "E.G.O"]
    assert [n[0] for n in P.get("saikai")["needs"]] == ["Identities", "Substitutes"]
    assert P.default_team("Hollow")["order"][0] == "Hong Lu"
    assert P.default_team("SAIKAI")["order"][0] == "Ry\u014dsh\u016b"
    assert P.default_team("Thrill") == {}


def test_applying_a_preset_from_its_card_sets_the_run_up_and_names_it(page, store, monkeypatch):
    import gui_v2.mirror_dungeon_page as M
    from gui_v2.run_config import HOLLOW_LABEL
    asked = []
    monkeypatch.setattr(M, "ask_choice", lambda *a: asked.append(a) or "secondary")
    loads = []
    page.config_loaded.connect(lambda: loads.append(1))
    card = page._preset_buttons["hollow"]
    plate = page._config_plate
    assert not _shows(card.mark, page) and not card.is_active()
    assert plate.text() == "CUSTOM" and plate.kind == "custom"
    card.apply.click()
    assert loads == [1]
    assert len(asked) == 1 and asked[0][2] == "Config applied!"
    assert "Set sinner order" in asked[0][1] and asked[0][3] == "Go to custom run settings"
    assert asked[0][4] == "Continue anyway"
    page._restore_state()                     # what the shell does on config_loaded
    assert page._custom_run.isChecked()
    assert page._custom_strategy.selected() == HOLLOW_LABEL
    assert page._market_slot == "hollow" and page._hard_from == 5
    assert card.is_active() and _shows(page._preset_marks["hollow"], page)
    assert not page._preset_buttons["saikai"].is_active()
    assert not _shows(page._preset_marks["saikai"], page)
    assert plate.text() == "HOLLOW" and plate.kind == "preset"
    assert "Hollow preset" in plate.toolTip()
    assert "Hollow is set up" in page._basic_status.text()
    page._run_count.setValue(page._run_count.value() + 1)   # the run count is not the setup
    assert card.is_active() and plate.text() == "HOLLOW"
    page._difficulty.set_selected("Hard")      # any setting of the run's: Custom
    page._save_state()
    assert not card.is_active() and not _shows(page._preset_marks["hollow"], page)
    assert plate.text() == "CUSTOM" and plate.kind == "custom"
    page._difficulty.set_selected("Normal")
    page._save_state()
    assert card.is_active() and plate.text() == "HOLLOW"
    page._custom_run.setChecked(False)         # the frame follows the settings
    assert not card.is_active() and plate.text() == "CUSTOM"


def test_the_prompt_can_open_the_custom_run_settings(page, store, monkeypatch):
    import gui_v2.mirror_dungeon_page as M
    monkeypatch.setattr(M, "ask_choice", lambda *a: "primary")
    asked = []
    page.open_team_settings.connect(asked.append)
    page._use_preset("saikai")
    assert asked == ["SAIKAI"]
    monkeypatch.setattr(M, "ask_choice", lambda *a: None)      # closed: nothing
    page._use_preset("hollow")
    assert asked == ["SAIKAI"]
    assert store["md_config"] == {}                           # a preset names itself


def test_each_preset_is_a_compact_card_that_unfolds_on_hover(page):
    from PySide6.QtCore import QAbstractAnimation, QEvent, QPointF, Qt
    from PySide6.QtGui import QKeyEvent, QMouseEvent
    from PySide6.QtWidgets import QApplication
    from gui_v2 import presets as P
    import gui_v2.mirror_dungeon_page as M
    for preset in P.PRESETS:
        card = page._preset_buttons[preset["key"]]
        assert isinstance(card, M._PresetCard) and card.title == preset["title"]
        assert card.width() == M._PresetCard.W
        label, _text, pics = preset["needs"][0]
        assert label == "Identities"
        assert [t.stem for t in card.portraits] == [p["stem"] for p in pics]
        for tile, pic in zip(card.portraits, pics):
            assert tile.toolTip().startswith(pic["name"]) and pic["req"] in tile.toolTip()
            assert not tile._pix.isNull() and tile.width() == M._MiniPortrait.SIZE
        assert card.meta.text().startswith(P.floor_code(preset["mirror"]))
        assert "Hard from floor" not in card.meta.text()
        assert not card.actions.isVisibleTo(card) and card.actions.maximumHeight() == 0
        card.set_open(True, animate=False)
        assert card.is_open() and card.actions.isVisibleTo(card)
        assert card.actions.maximumHeight() == card.actions.sizeHint().height() > 0
        assert card.details.text() == "More details" and card.apply.text() == "Apply config"
        assert card.details.search_skip and card.apply.search_skip
        card.set_open(False, animate=False)
        assert not card.is_open() and card.actions.maximumHeight() == 0
    hollow = page._preset_buttons["hollow"]
    assert [t.stem for t in hollow.portraits] == ["mao_faust"]
    saikai = page._preset_buttons["saikai"]
    assert len(saikai.portraits) == 7 and saikai.portraits[0].stem == "blade_ryoshu"
    assert "Rupture team" in hollow.meta.text() and "Poise team" in saikai.meta.text()
    hollow.set_open(True)                                 # animated from the hover
    assert hollow._anim.state() == QAbstractAnimation.State.Running
    hollow._anim.stop()
    opened = []
    hollow.details_requested.connect(opened.append)

    def click(w):
        c = QPointF(w.rect().center())
        for et, held in ((QEvent.Type.MouseButtonPress, Qt.MouseButton.LeftButton),
                         (QEvent.Type.MouseButtonRelease, Qt.MouseButton.NoButton)):
            QApplication.sendEvent(w, QMouseEvent(
                et, c, c, c, Qt.MouseButton.LeftButton, held,
                Qt.KeyboardModifier.NoModifier))

    click(hollow)                                         # the face opens the details
    assert opened == ["hollow"]
    click(hollow.portraits[0])
    assert opened == ["hollow"] * 2
    QApplication.sendEvent(hollow, QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_Return,
                                             Qt.KeyboardModifier.NoModifier))
    assert opened == ["hollow"] * 3
    hollow.details.click()
    assert opened == ["hollow"] * 4


def test_a_clicked_card_folds_again_and_only_key_focus_holds_it(page, monkeypatch):
    from PySide6.QtCore import QAbstractAnimation, QEvent, Qt
    from PySide6.QtGui import QFocusEvent
    from PySide6.QtTest import QTest
    from PySide6.QtWidgets import QWidget
    import gui_v2.mirror_dungeon_page as M
    saikai, hollow = page._preset_buttons["saikai"], page._preset_buttons["hollow"]
    saikai._pointer_inside = lambda: False                # the pointer is elsewhere
    focus = {"w": None}
    monkeypatch.setattr(M.QApplication, "focusWidget", staticmethod(lambda: focus["w"]))

    def heading(card):
        running = card._anim.state() == QAbstractAnimation.State.Running
        return card._anim.endValue() if running else card._open

    # A click gives the card focus and the closed details window hands it
    # back: neither holds the card open once the pointer has moved on.
    for reason in (Qt.FocusReason.MouseFocusReason,
                   Qt.FocusReason.ActiveWindowFocusReason,
                   Qt.FocusReason.OtherFocusReason):
        saikai.set_open(True, animate=False)              # the hover's doing
        focus["w"] = saikai
        saikai.focusInEvent(QFocusEvent(QEvent.Type.FocusIn, reason))
        assert not saikai._keyed
        saikai._settle()
        assert heading(saikai) == 0.0
    saikai.set_open(True, animate=False)
    focus["w"] = saikai.details                           # the button took the click
    saikai.eventFilter(saikai.details, QFocusEvent(QEvent.Type.FocusIn,
                                                   Qt.FocusReason.MouseFocusReason))
    saikai._settle()
    assert heading(saikai) == 0.0
    # The window coming back settles the card without any focus at all.
    saikai.set_open(True, animate=False)
    focus["w"] = None
    M.QApplication.sendEvent(saikai, QEvent(QEvent.Type.WindowActivate))
    QTest.qWait(30)
    assert heading(saikai) == 0.0
    # Tabbing to the card opens it and holds it, through its own buttons and
    # while another window has the focus, until the focus moves on here.
    focus["w"] = saikai
    saikai.focusInEvent(QFocusEvent(QEvent.Type.FocusIn, Qt.FocusReason.TabFocusReason))
    assert saikai._keyed and heading(saikai) == 1.0
    saikai._settle()
    assert heading(saikai) == 1.0
    focus["w"] = saikai.details
    saikai._settle()
    assert saikai._keyed and heading(saikai) == 1.0
    elsewhere = QWidget()                                 # the details window
    focus["w"] = elsewhere
    saikai._settle()
    assert saikai._keyed and heading(saikai) == 1.0
    focus["w"] = saikai
    saikai.focusInEvent(QFocusEvent(QEvent.Type.FocusIn,
                                    Qt.FocusReason.ActiveWindowFocusReason))
    saikai._settle()
    assert saikai._keyed and heading(saikai) == 1.0
    focus["w"] = hollow
    saikai.focusOutEvent(QFocusEvent(QEvent.Type.FocusOut, Qt.FocusReason.TabFocusReason))
    saikai._settle()
    assert not saikai._keyed and heading(saikai) == 0.0
    saikai._anim.stop()
    elsewhere.deleteLater()


def test_the_floor_code_reads_like_players_write_it():
    import gui_v2.presets as P
    assert P.floor_code({"difficulty": "Normal", "hard_from_floor": 5}) == "4N1H"
    assert P.floor_code({"difficulty": "Normal", "hard_from_floor": 4}) == "3N2H"
    assert P.floor_code({"difficulty": "Normal", "hard_from_floor": 1}) == "5H"
    assert P.floor_code({"difficulty": "Normal", "hard_from_floor": 99}) == "5N"
    assert P.floor_code({"difficulty": "Normal", "hard_from_floor": "x"}) == "5N"
    assert P.floor_code({"difficulty": "Hard", "hard_from_floor": 3}) == "5H"
    assert P.floor_code({}) == "5N"
    assert P.floor_code(P.get("hollow")["mirror"]) == "4N1H"
    assert P.floor_code(P.get("saikai")["mirror"]) == "3N2H"


def test_more_details_opens_the_run_sheet(page, store, monkeypatch):
    from PySide6.QtCore import Qt
    from gui_v2 import presets as P
    import gui_v2.mirror_dungeon_page as M
    from gui_v2.preset_details import PresetDetailsDialog, _UnitRow, _notes_html, _rich
    assert page._details is None
    page._preset_buttons["saikai"].details.click()
    dlg = page._details
    assert isinstance(dlg, PresetDetailsDialog) and dlg.key == "saikai" and dlg.isVisible()
    preset = P.get("saikai")
    assert [h.text() for h in dlg.headers] == (
        ["SINNER ORDER", "SINNER SWAP EXCLUSION"] + [n[0].upper() for n in preset["needs"]])
    assert type(dlg.headers[0]) is type(dlg.headers[-1])     # the same face as the roster's headers
    from gui_v2.voxel import PixelLabel
    for head in dlg.headers:
        if isinstance(head, PixelLabel):
            assert head._inset[0] == 0 and head.objectName() == "sheetHeading"
    assert [p.name for p in dlg.order] == preset["teams"]["SAIKAI"]["order"]
    assert [p.number for p in dlg.order] == list(range(1, len(dlg.order) + 1))
    assert [p.name for p in dlg.excluded] == preset["teams"]["SAIKAI"]["exclude"]
    assert all(p.number == 0 for p in dlg.excluded)
    wanted = [p["stem"] for _l, _t, pics in preset["needs"] for p in pics]
    assert [u.stem for u in dlg.units] == wanted and len(wanted) == 10
    ryoshu = dlg.units[0]
    assert ryoshu.caption.text().startswith("Blade of the House")
    assert ryoshu.req.text().startswith("Lv. 65+") and "UT 4+" in ryoshu.req.text()
    assert "Will be solo-ing the entire dungeon" in ryoshu.notes.text()
    assert "\u25aa" in ryoshu.notes.text()
    assert ryoshu.notes.textFormat() == Qt.TextFormat.RichText
    assert all(not u.art.pixmap().isNull() for u in dlg.units)
    assert [p.label.text() for p in dlg.facts] == [
        "DIFFICULTY", "TEAM KEYWORD", "SKILL 3 ONLY", "GRACES", "STARTING GIFTS",
        "GIFT SEARCH", "PACK SEARCH", "MARKET"]
    values = {p.label.text(): p.value.text() for p in dlg.facts if p.value is not None}
    chips = {p.label.text(): p.chips for p in dlg.facts if p.value is None}
    assert values["DIFFICULTY"] == "3N2H \u00b7 Hard from floor 4"
    assert values["TEAM KEYWORD"] == "Poise" and values["PACK SEARCH"] == "Off"
    assert sorted(chips) == ["GIFT SEARCH", "GRACES", "MARKET", "STARTING GIFTS"]
    # Stone Tomb is the pick; Star Shower adds the other of the first two.
    assert [c.name for c in chips["STARTING GIFTS"]] == ["Stone Tomb", "Cigarette Holder"]
    assert all(not c._pix.isNull() for c in chips["STARTING GIFTS"])
    assert [c.name for c in chips["GRACES"]] == [
        "Star of the Beginning", "Interstellar Travel", "Star Shower"]
    assert chips["GRACES"][2].toolTip() == "Star-shower"
    assert [c.name for c in chips["GIFT SEARCH"]] == ["Spiderweb Entangled in Red"]
    assert all(not c._pix.isNull() for c in chips["GRACES"] + chips["GIFT SEARCH"])
    market = {c.name: [(m.key, m.number) for m in c.marks] for c in chips["MARKET"]}
    assert len(market) == 9 and all(not c.art._pix.isNull() for c in chips["MARKET"])
    assert market["Contaminated Needle & Thread"] == [
        ("keep_fuse", 0), ("keep_sell", 0), ("buy", 5), ("enhance2", 0)]
    assert market["Artistic Sense"] == [
        ("keep_fuse", 0), ("keep_sell", 0), ("fuse", 0), ("enhance2", 0)]
    buys = sorted(n for marks in market.values() for k, n in marks if k == "buy")
    assert buys == [1, 2, 3, 4, 5, 6]
    from gui_v2.mirror_dungeon_page import _MARKET_MODES
    for chip in chips["MARKET"]:
        for mark in chip.marks:
            assert mark.toolTip().startswith(dict(_MARKET_MODES)[mark.key])
            assert (" #%d" % mark.number in mark.toolTip()) == (mark.key == "buy")
    assert "House of Spider" in dlg.lede.text()
    page._preset_buttons["hollow"].details.click()       # a second sheet replaces the first
    hollow = page._details
    assert hollow is not dlg and hollow.key == "hollow"
    values = {p.label.text(): p.value.text() for p in hollow.facts if p.value is not None}
    chips = {p.label.text(): p.chips for p in hollow.facts if p.value is None}
    assert values["SINNER TO HEAL"] == "Hong Lu" and "SKILL 3 ONLY" not in values
    team = P.get("hollow")["teams"]["Hollow"]
    assert [p.name for p in hollow.order] == team["order"]
    assert [p.name for p in hollow.excluded] == team["exclude"] == ["Faust"]
    assert [(c.floor, c.name) for c in chips["PACK SEARCH"]] == [
        (3, "To be Cleaved"), (4, "Hatred and Despair"), (5, "Line 2")]
    assert all(not c.art._pix.isNull() and c.art.toolTip() == c.name
               for c in chips["PACK SEARCH"])
    market = {c.name: [(m.key, m.number) for m in c.marks] for c in chips["MARKET"]}
    assert len(market) == 6
    assert market["Torn Bandolier"] == [("keep_fuse", 0), ("keep_sell", 0),
                                        ("enhance2", 0)]
    assert [c.name for c in chips["STARTING GIFTS"]] == ["Torn Bandolier"]
    assert market["Clear Mirror, Calm Water"] == [
        ("keep_fuse", 0), ("keep_sell", 0), ("fuse", 0), ("enhance2", 0)]
    bare = _UnitRow({"stem": "blade_ryoshu", "name": "Bare"})
    assert bare.req.isHidden() and bare.notes.isHidden()
    bare.deleteLater()
    monkeypatch.setattr(M, "ask_choice", lambda *a: "secondary")
    loads = []
    page.config_loaded.connect(lambda: loads.append(1))
    hollow.apply.click()                                  # applies from the sheet, closing it
    assert loads == [1] and not hollow.isVisible() and page._details is None
    page._restore_state()
    assert page._config_plate.text() == "HOLLOW"
    rich = _rich("Head line\n- one\n- two\n\nTail")
    assert rich.count("<p") == 4 and rich.count("\u2022") == 2
    assert "text-indent:-12px" in rich and "margin:0 0 8px 12px" in rich
    assert _rich("a & b") == "<p style=\"margin:0 0 0px 0px;\">a &amp; b</p>"
    assert _notes_html("- a\n- b").count("\u25aa") == 2 and "&amp;" in _notes_html("a & b")


def test_the_config_plate_sits_beside_the_title_and_names_a_saved_config(page, store, monkeypatch):
    import gui_v2.settings as st
    plate = page._config_plate
    assert page._header._row.indexOf(plate) == 1          # right after the title
    assert plate.text() == "CUSTOM" and plate.kind == "custom"
    assert plate.height() == 24 and plate.width() > 40
    monkeypatch.setattr(st, "list_configs", lambda: ["Mine"])
    monkeypatch.setattr(st, "load_config", lambda name: True)
    saved = []
    monkeypatch.setattr(st, "save_config", saved.append)
    page._refresh_configs()
    page._config_load_buttons["Mine"].click()
    assert store["md_config"] == {"saved": "Mine", "fingerprint": None}
    page._restore_state()                                  # the shell reloads the pages
    assert store["md_config"]["fingerprint"] and plate.text() == "MINE"
    assert plate.kind == "saved" and "'Mine'" in plate.toolTip()
    page._run_count.setValue(page._run_count.value() + 1)  # not part of a config's identity
    assert plate.text() == "MINE"
    page._retry_count.setValue(page._retry_count.value() + 1)
    assert plate.text() == "CUSTOM"
    page._retry_count.setValue(page._retry_count.value() - 1)
    assert plate.text() == "MINE"
    page._config_name.setText("A much longer name than the plate shows")
    page._save_basic_config()
    assert saved == ["A much longer name than the plate shows"]
    assert plate.text() == "A MUCH LONGER NAME THAN " and plate.kind == "saved"
    assert store["md_config"]["saved"] == plate.name == "A much longer name than the plate shows"


def test_the_identity_check_compares_what_a_preset_lays_down():
    import gui_v2.mirror_dungeon_page as M
    assert M._norm({"1": {"a": "x"}, 2: {}, 3: []}) == {"1": {"a": "x"}}
    assert M._norm([]) is None and M._norm(0) is None and M._norm(False) is None
    assert M._norm(True) is True and M._norm(1) == 1 and M._norm("0") == "0"
    assert M._norm(["b", "a"]) == ["a", "b"] and M._norm(["b", "a"], "buy") == ["b", "a"]
    assert M._norm({"buy": ["b", "a"], "fuse": ["b", "a"], "card": ["z", "y"]}) == {
        "buy": ["b", "a"], "fuse": ["a", "b"], "card": ["z", "y"]}

def test_your_configs_load_and_save(page, monkeypatch):
    import gui_v2.settings as st
    names, calls = ["Mine"], []

    def load(name):
        calls.append(("load", name))
        return name in names

    def save(name):
        calls.append(("save", name))
        names.append(name)

    monkeypatch.setattr(st, "list_configs", lambda: list(names))
    monkeypatch.setattr(st, "load_config", load)
    monkeypatch.setattr(st, "save_config", save)
    page._refresh_configs()
    assert list(page._config_load_buttons) == ["Mine"]
    assert not _shows(page._configs_empty, page)
    loads = []
    page.config_loaded.connect(lambda: loads.append(1))
    page._config_load_buttons["Mine"].click()
    assert calls == [("load", "Mine")] and loads == [1]
    assert "Loaded 'Mine'" in page._basic_status.text()
    page._config_name.setText("   ")
    page._save_basic_config()
    assert calls == [("load", "Mine")] and "name" in page._basic_status.text()
    page._config_name.setText("Second")
    page._save_basic_config()
    assert calls[-1] == ("save", "Second") and page._config_name.text() == ""
    assert "Second" in page._config_load_buttons
    names.clear()
    page._refresh_configs()
    assert _shows(page._configs_empty, page) and not page._config_load_buttons


def test_the_basic_view_points_at_the_custom_run_settings(page, monkeypatch):
    import gui_v2.mirror_dungeon_page as mdp
    from gui_v2.run_config import HOLLOW_LABEL, SAIKAI_LABEL
    saved = {"app_settings": {}}
    monkeypatch.setattr(mdp, "load_section", lambda name: saved.get(name, {}))
    asked = []
    page.open_team_settings.connect(asked.append)
    assert page._team_button.text() == "Go to custom run settings"
    page._custom_run.setChecked(False)
    page._refresh_team_warning()
    assert page._team_warn.isHidden()
    page._custom_run.setChecked(True)
    page._custom_strategy.set_selected(SAIKAI_LABEL)
    page._sync_run()
    assert not page._team_warn.isHidden()
    assert page._team_warn.text().startswith("SAIKAI has not been configured")
    page._team_button.click()
    assert asked == ["SAIKAI"]
    saved["app_settings"] = {"custom_teams": {"SAIKAI": {"order": ["Outis"]}}}   # before the flag
    page._refresh_team_warning()
    assert page._team_warn.isHidden()
    saved["app_settings"] = {"custom_teams": {                              # a preset's order
        "SAIKAI": {"order": ["Outis"], "configured": False}}}
    page._refresh_team_warning()
    assert not page._team_warn.isHidden() and "SAIKAI" in page._team_warn.text()
    page._custom_strategy.set_selected(HOLLOW_LABEL)
    page._sync_run()
    assert page._team_warn.text().startswith("HOLLOW has not been configured")
    page._team_button.click()
    assert asked == ["SAIKAI", "Hollow"]
    page._custom_run.setChecked(False)
    assert page._team_warn.isHidden()


def test_a_preset_does_not_count_as_configuring_the_team(monkeypatch):
    from gui_v2 import presets as P
    store = {"mirror": {}, "app_settings": {"custom_teams": {
        "Hollow": {"configured": True, "order": ["Gregor"]}}}}
    monkeypatch.setattr(P, "load_section", lambda name: store.get(name, {}))
    monkeypatch.setattr(P, "save_section",
                        lambda name, value: store.__setitem__(name, value))
    assert P.apply("saikai") and P.apply("hollow")
    teams = store["app_settings"]["custom_teams"]
    assert teams["SAIKAI"]["configured"] is False
    assert teams["SAIKAI"]["order"] == P.default_team("SAIKAI")["order"]
    assert teams["Hollow"]["configured"] is True             # the user's flag stays
    assert teams["Hollow"]["order"][0] == "Hong Lu"
