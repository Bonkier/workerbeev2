# SPDX-License-Identifier: GPL-3.0-or-later
"""Offscreen functional tests for the market gift tags: the fuse/enhance gift
tags and the "Buy EGO fuel" toggle. Persistence is stubbed out so the live
config file is never written; each test asserts it stayed byte-identical."""
from __future__ import annotations

import os
from pathlib import Path

import pytest

pytest.importorskip("PySide6")
os.environ["QT_QPA_PLATFORM"] = "offscreen"

_CONFIG = Path(__file__).resolve().parents[1] / "config" / "v2_ui.json"


def _config_bytes():
    return _CONFIG.read_bytes() if _CONFIG.exists() else None


@pytest.fixture(scope="module")
def qapp():
    from PySide6.QtWidgets import QApplication
    return QApplication.instance() or QApplication([])


@pytest.fixture
def page(qapp, monkeypatch):
    import gui_v2.settings as settings
    import gui_v2.mirror_dungeon_page as mdp
    before = _config_bytes()
    monkeypatch.setattr(settings, "save_section", lambda *a, **k: None)
    monkeypatch.setattr(mdp, "save_section", lambda *a, **k: None)
    pg = mdp.MirrorDungeonPage()
    pg._loading = True
    pg._custom_run.setChecked(False)        # a known start, whatever is saved
    pg._apply_custom_run(False)
    yield pg
    pg.deleteLater()
    assert _config_bytes() == before


def _tile_names(gallery, count):
    names = sorted(gallery._tiles)
    if len(names) < count:
        pytest.skip("market catalog unavailable")
    return names[:count]


def test_a_gift_click_opens_its_tags_and_ticks_them(page):
    from gui_v2.mirror_dungeon_page import _MARKET_MODE_KEYS, _GiftTagPopup
    g = page._market_gallery
    name, = _tile_names(g, 1)
    tile = g._tiles[name]
    g.reset()

    tile.click()
    pop = g._popup
    assert isinstance(pop, _GiftTagPopup) and pop.name == name and pop.isVisible()
    assert list(pop.rows) == list(_MARKET_MODE_KEYS) and tile._active
    assert not any(r.is_on() for r in pop.rows.values())

    pop.rows["fuse"].click()
    assert name in g._fuse and pop.rows["fuse"].is_on()
    assert ("fuse", 0) in tile._badges()

    pop.rows["enhance1"].click()
    assert name in g._enh1
    assert ("enhance1", 0) in tile._badges()

    pop.rows["enhance2"].click()
    assert name in g._enh2 and name not in g._enh1
    assert pop.rows["enhance2"].is_on() and not pop.rows["enhance1"].is_on()
    assert ("enhance2", 0) in tile._badges()

    pop.rows["enhance1"].click()
    assert name in g._enh1 and name not in g._enh2
    assert name in g._fuse
    assert g._count.text() == "1 configured"

    pop.rows["buy"].click()
    assert g._buy == [name] and pop.rows["buy"]._note == "#1"
    assert tile._badges() == [("buy", 1), ("fuse", 0), ("enhance1", 0)]
    pop.hide()                                   # a click elsewhere does this
    assert g._popup is None and not tile._active


def test_config_roundtrip(page):
    g = page._market_gallery
    a, b = _tile_names(g, 2)
    g.reset()

    g.toggle_tag("fuse", a)
    g.toggle_tag("enhance1", a)
    g.toggle_tag("enhance2", b)

    cfg = g.config()
    assert cfg["fuse"] == [a]
    assert cfg["enhance1"] == [a]
    assert cfg["enhance2"] == [b]

    g.reset()
    empty = g.config()
    assert empty["fuse"] == [] and empty["enhance1"] == [] \
        and empty["enhance2"] == []

    g.set_config(cfg)
    assert g.config() == cfg

    g.set_config({"keep_fuse": [a]})
    restored = g.config()
    assert restored["fuse"] == [] and restored["enhance1"] == [] \
        and restored["enhance2"] == []

    g.set_config({"enhance1": [a], "enhance2": [a, "No Such Gift"]})
    exclusive = g.config()
    assert exclusive["enhance1"] == [a] and exclusive["enhance2"] == []


def test_buy_ego_fuel_toggle(page):
    page._default_market_workflow.setChecked(True)
    assert not page._buy_fuel_row.isEnabled()

    page._default_market_workflow.setChecked(False)
    assert page._buy_fuel_row.isEnabled()

    page._buy_ego_fuel.setChecked(False)
    assert page._market_controls_config()["buy_ego_fuel"] is False
    page._buy_ego_fuel.setChecked(True)
    assert page._market_controls_config()["buy_ego_fuel"] is True


def test_build_settings_buy_ego_fuel():
    from gui_v2.run_config import build_settings
    assert build_settings({})["buy_ego_fuel"] is False
    on = build_settings({"market_controls": {"buy_ego_fuel": True}})
    assert on["buy_ego_fuel"] is True
    tags = {"fuse": ["A"], "enhance1": ["B"], "enhance2": ["C"]}
    passed = build_settings({"market_gifts": tags})
    assert passed["market_gifts"] == tags


def test_saikai_preset_shape():
    from wbcore.market_catalog import (
        SAIKAI_MARKET_KEEP, SAIKAI_MARKET_TAGS, load_market_catalog,
    )
    assert len(SAIKAI_MARKET_KEEP) == 9
    assert SAIKAI_MARKET_TAGS["keep_fuse"] == SAIKAI_MARKET_KEEP
    assert SAIKAI_MARKET_TAGS["keep_sell"] == SAIKAI_MARKET_KEEP
    # The guide sheet's shops: Clear Mirror off any shelf, the Poise gifts
    # in its ranking, then the floor 2 and floor 4 gifts.
    assert SAIKAI_MARKET_TAGS["buy"] == [
        "Clear Mirror, Calm Water", "Emerald Elytra", "Nebulizer",
        "Endorphin Kit", "Contaminated Needle & Thread", "Sundered Memory"]
    # The optional Artistic Sense is the last fuse target.
    assert SAIKAI_MARKET_TAGS["fuse"] == [
        "Clear Mirror, Calm Water", "Sundered Memory", "Artistic Sense"]
    # ++ where the sheet marks it; Endorphin Kit and Sundered Memory stay plain.
    assert SAIKAI_MARKET_TAGS["enhance2"] == [
        "Clear Mirror, Calm Water", "Stone Tomb", "Emerald Elytra",
        "Nebulizer", "Contaminated Needle & Thread", "Artistic Sense"]
    tagged = (set(SAIKAI_MARKET_TAGS["buy"]) | set(SAIKAI_MARKET_TAGS["fuse"])
              | set(SAIKAI_MARKET_TAGS["enhance2"]))
    assert tagged <= set(SAIKAI_MARKET_KEEP)          # nothing the run wants is fuel
    cat = load_market_catalog()
    if not cat:
        pytest.skip("market catalog unavailable")
    for name in SAIKAI_MARKET_KEEP:
        assert name in cat, name
    for name in SAIKAI_MARKET_TAGS["buy"]:
        assert cat[name].get("buy_path"), name
    for name in SAIKAI_MARKET_TAGS["fuse"] + SAIKAI_MARKET_TAGS["enhance2"]:
        assert cat[name].get("sell_path"), name


def test_saikai_market_slot_swap(page):
    from gui_v2.mirror_dungeon_page import SAIKAI_LABEL
    g = page._market_gallery
    if "Clear Mirror, Calm Water" not in g._tiles:
        pytest.skip("market catalog unavailable")

    # Start from a known normal config: no custom run.
    page._custom_run.setChecked(False)
    page._apply_custom_run(False)
    page._sync_run()
    g.reset()
    other = next(n for n in g._tiles
                 if n != "Clear Mirror, Calm Water")
    g.toggle_tag("sell", other)
    normal_cfg = g.config()
    assert other in normal_cfg["sell"]

    # SAIKAI selected: gallery swaps to the preset-seeded, EDITABLE slot.
    page._custom_strategy.set_selected(SAIKAI_LABEL)
    page._custom_run.setChecked(True)
    page._sync_run()
    assert page._market_slot == "saikai"
    cfg = g.config()
    assert cfg["fuse"] == ["Clear Mirror, Calm Water", "Sundered Memory"]
    assert len(cfg["keep_fuse"]) == 7
    assert other not in cfg["sell"]

    # Fully configurable: untag a preset gift, tag another one.
    g.toggle_tag("fuse", "Clear Mirror, Calm Water")
    assert "Clear Mirror, Calm Water" not in g.config()["fuse"]
    g.toggle_tag("fuse", other)
    assert other in g.config()["fuse"]

    # state() carries both slots independently.
    st = page.state()
    assert st["market_gifts"] == normal_cfg
    assert other in st["market_gifts_saikai"]["fuse"]
    assert "Clear Mirror, Calm Water" not in st["market_gifts_saikai"]["fuse"]

    # Back to normal: the normal config returns; SAIKAI edits persist in slot.
    page._custom_run.setChecked(False)
    page._sync_run()
    assert page._market_slot == "normal"
    assert g.config() == normal_cfg
    assert other in page._market_slots["saikai"]["fuse"]

    page._custom_run.setChecked(True)
    page._sync_run()
    assert other in g.config()["fuse"]


def test_saikai_run_uses_saikai_slot():
    from gui_v2.run_config import SAIKAI_LABEL, build_settings
    base = {"custom_run": True, "custom_strategy": SAIKAI_LABEL}

    # Never saved: seeded from the preset.
    seeded = build_settings(dict(base))["market_gifts"]
    assert seeded["fuse"] == ["Clear Mirror, Calm Water", "Sundered Memory",
                              "Artistic Sense"]

    # Saved slot (even empty) wins over the preset.
    custom = {"fuse": ["Nebulizer"], "buy": []}
    got = build_settings(dict(base, market_gifts_saikai=custom,
                              market_gifts={"buy": ["X"]}))["market_gifts"]
    assert got == custom
    empty = build_settings(dict(base, market_gifts_saikai={}))["market_gifts"]
    assert empty == {}

    # Non-SAIKAI runs keep using the normal slot.
    normal = build_settings({"market_gifts": {"buy": ["X"]},
                             "market_gifts_saikai": custom})["market_gifts"]
    assert normal == {"buy": ["X"]}


def test_the_tag_rows_show_the_gifts_as_art_and_add_by_name(page):
    from PySide6.QtGui import QFontMetrics, QPixmap
    from gui_v2.mirror_dungeon_page import (
        _MARKET_MODE_KEYS, _MARKET_MODES, _TAG_GLYPH, _GiftPickPopup,
        _TagAddButton, _TagGiftChip, _TagRow, _TagRowHead,
    )
    g = page._market_gallery
    a, b = _tile_names(g, 2)
    g.reset()
    assert list(g._tag_rows) == list(_MARKET_MODE_KEYS)
    for key, flow in g._tag_rows.items():            # every row is there, with its +
        assert flow.count() == 1 and flow.itemAt(0).widget() is g._add_btns[key]
        assert isinstance(g._add_btns[key], _TagAddButton)
        assert g._add_btns[key].isEnabled()
    heads = g._rows_holder.findChildren(_TagRowHead)
    assert len(heads) == len(_MARKET_MODES)
    labels = {key: label.upper() for key, label in _MARKET_MODES}
    for head in heads:                                # room for the whole name
        text_w = QFontMetrics(head._font).horizontalAdvance(head._label)
        assert head.width() > text_w + _TAG_GLYPH
        assert head._label == labels[head.key()]
        head.render(QPixmap(head.size()))
    rows = g._rows_holder.findChildren(_TagRow)       # a ledger: a rule under each but the last
    assert [r.head.key() for r in rows] == list(_MARKET_MODE_KEYS)
    assert [r._last for r in rows] == [False] * 6 + [True]

    g.toggle_tag("buy", a)
    g.toggle_tag("buy", b)
    flow = g._tag_rows["buy"]
    chips = [flow.itemAt(i).widget() for i in range(flow.count())]
    assert [type(w) for w in chips] == [_TagGiftChip, _TagGiftChip, _TagAddButton]
    assert [c.name() for c in chips[:2]] == [a, b] and chips[1]._number == 2
    assert chips[0].toolTip().startswith(a) and not chips[0]._pix.isNull()
    chips[0].render(QPixmap(chips[0].size()))
    chips[0].click()                                  # the chip's x takes the tag off
    assert g._buy == [b]

    g._add_btns["fuse"].click()
    pop = g._popup
    assert isinstance(pop, _GiftPickPopup) and pop.key == "fuse" and pop.isVisible()
    assert len(pop.rows) == len(g._tiles)
    pop.search.setText(a[:6])
    shown = [r for r in pop.rows.values() if not r.isHidden()]
    assert shown and all(a[:6].lower() in r.name.lower() for r in shown)
    pop.rows[a].click()
    assert a in g._fuse and pop.rows[a].is_on()
    pop.search.setText(b)
    first = next(r.name for r in pop.rows.values() if not r.isHidden())
    was = g.has_tag("fuse", first)
    pop._take_first()                                 # Enter takes the first match
    assert g.has_tag("fuse", first) != was
    pop.rows[a].click()                               # a second click takes it off
    assert a not in g._fuse
    pop.search.setText("no gift has this name")
    assert not pop._empty.isHidden()
    pop.hide()
    assert g._popup is None
    assert g._count.text() == "%d configured" % len(set(g._buy) | g._fuse)


def test_the_picked_search_gifts_show_as_art_chips_with_their_names(page):
    """Above the search, each pick is a chip with the gift's art and name.
    The chip's x unpicks it; no pick is mandatory, whatever the run."""
    from PySide6.QtGui import QFontMetrics
    from gui_v2.mirror_dungeon_page import _PickChip
    gifts = page._gift_gallery
    gifts.set_selected([])
    gifts._toggle("Ardent Flower")
    gifts._toggle("Charred Disk")
    chips = gifts._chips_holder.findChildren(_PickChip)
    assert [c.name() for c in chips] == ["Ardent Flower", "Charred Disk"]
    assert all(not c._pix.isNull() and c._pix.height() <= c._ART for c in chips)
    assert all("Click to remove" in c.toolTip() for c in chips)
    label = QFontMetrics(chips[0]._font).horizontalAdvance("Ardent Flower")
    assert chips[0].width() > chips[0]._ART + label + chips[0]._MARK
    chips[0].click()
    assert gifts.selected() == ["Charred Disk"]
    assert not hasattr(gifts, "set_locked")
    gifts.reset()                                     # Reset clears every pick
    assert gifts.selected() == []


def test_a_saved_search_comes_back_as_saved_under_a_custom_run(page, monkeypatch):
    """Loading a setup puts no gift in: what was saved is what the run
    searches, the run's own gifts taken off included."""
    import gui_v2.mirror_dungeon_page as mdp
    from gui_v2.run_config import HOLLOW_LABEL, RUN_SEARCH_GIFTS, SAIKAI_LABEL
    gifts = page._gift_gallery
    own = {n for names in RUN_SEARCH_GIFTS.values() for n in names}
    other = next(n for n in gifts._tiles if n not in own)
    for strategy, picks in ((HOLLOW_LABEL, [other]), (SAIKAI_LABEL, []),
                            (HOLLOW_LABEL, []), (SAIKAI_LABEL, [other])):
        saved = {"custom_run": True, "custom_strategy": strategy, "gift_search": picks}
        monkeypatch.setattr(mdp, "load_section",
                            lambda name, s=saved: dict(s) if name == "mirror" else {})
        page._restore_state()
        assert page.state()["custom_strategy"] == strategy
        assert page.state()["gift_search"] == picks
    page._loading = True


def test_a_run_brings_its_search_gift_and_takes_it_off_again(page):
    """Picking SAIKAI by hand puts Spiderweb ahead of the picks, as an
    ordinary pick; leaving the run takes it off and keeps the rest. A
    saved setup is loaded as it was saved."""
    from gui_v2.run_config import HOLLOW_LABEL, RUN_SEARCH_GIFTS, SAIKAI_LABEL
    gifts = page._gift_gallery
    gift, = RUN_SEARCH_GIFTS[SAIKAI_LABEL]
    other = next(n for n in gifts._tiles if n != gift
                 and n not in RUN_SEARCH_GIFTS[HOLLOW_LABEL])
    gifts.set_selected([other])
    page._custom_strategy.set_selected(SAIKAI_LABEL)
    page._custom_run.setChecked(True)
    page._sync_run()
    assert gifts.selected() == [other]                # loading: nothing is put in
    page._custom_run.setChecked(False)
    page._sync_run()
    page._loading = False                             # now by hand
    try:
        page._custom_run.setChecked(True)
        assert gifts.selected() == [gift, other]
        gifts._toggle(gift)                           # off like any other pick
        assert gifts.selected() == [other] and page.state()["gift_search"] == [other]
        gifts._toggle(gift)
        page._custom_strategy.set_selected(HOLLOW_LABEL)    # Hollow starts from its own two
        page._sync_run()
        assert gifts.selected() == list(RUN_SEARCH_GIFTS[HOLLOW_LABEL])
        gifts._toggle(other)
        page._custom_strategy.set_selected(SAIKAI_LABEL)    # the third pick comes along
        page._sync_run()
        assert gifts.selected() == [gift, other]
        page._custom_run.setChecked(False)
    finally:
        page._loading = True
    assert gifts.selected() == [other]                # the run's gift left with it
    gifts.set_selected([gift])                        # and can be picked by hand again
    assert gifts.selected() == [gift]
    gifts.set_selected([])


def test_hollow_seeds_its_slot_with_the_sheets_plan_and_clears_the_gift_search(page):
    from gui_v2 import run_summary as RS
    from gui_v2.run_config import (HOLLOW_LABEL, HOLLOW_SEARCH_GIFTS, build_settings,
                                   hollow_market_seed)
    from wbcore import hollow as H
    g = page._market_gallery
    if H._MIRROR not in g._tiles:
        pytest.skip("market catalog unavailable")
    page._custom_run.setChecked(False)
    page._apply_custom_run(False)
    page._sync_run()
    page._market_slots["hollow"] = None        # not whatever the saved config holds
    page._market_floors["hollow"] = {}
    g.reset()
    other = next(n for n in g._tiles if n not in H.MARKET_PROTECTED[1])
    g.toggle_tag("buy", other)
    normal_cfg = g.config()
    assert other in normal_cfg["buy"]
    gifts = page._gift_gallery
    pick = next(n for n in gifts._tiles if n not in HOLLOW_SEARCH_GIFTS)
    gifts.set_selected([pick])
    assert gifts.selected() == [pick]

    page._loading = False                  # an interactive pick of Hollow
    try:
        page._custom_strategy.set_selected(HOLLOW_LABEL)
        page._custom_run.setChecked(True)
        page._sync_run()
    finally:
        page._loading = True
    assert page._market_slot == "hollow" and g.config()["buy"] == []
    assert set(gifts.selected()) == set(HOLLOW_SEARCH_GIFTS)   # the pick is gone
    assert pick not in gifts.selected()
    # The sheet's plan fills the slot as ordinary tags: on the tiles, in the
    # rows and in the config, every one of them editable.
    seed, seed_floors = hollow_market_seed()
    assert seed["fuse"] == [H._CONCEIT, H._MIRROR, H._DECAY, H._SENSE]
    assert seed["keep_fuse"] == seed["keep_sell"] == [
        H._CONCEIT, H._DECAY, H.STARTING_GIFT, H._THREAD, H._MIRROR, H._SENSE]
    assert seed["enhance2"] == [H.STARTING_GIFT, H._MIRROR, H._SENSE]
    cfg = g.config()
    assert cfg["fuse"] == sorted(seed["fuse"]) and cfg["enhance2"] == sorted(seed["enhance2"])
    assert cfg["keep_fuse"] == cfg["keep_sell"] == sorted(seed["keep_fuse"])
    assert g._tiles[H._MIRROR]._badges() == [
        ("keep_fuse", 0), ("keep_sell", 0), ("fuse", 0), ("enhance2", 0)]
    assert g._count.text() == "6 configured"
    assert all(btn.isEnabled() for btn in g._add_btns.values())
    fuse_row = g._tag_rows["fuse"]
    fuse_chips = [fuse_row.itemAt(i).widget() for i in range(fuse_row.count() - 1)]
    assert {c.name() for c in fuse_chips} == set(seed["fuse"])
    g._tiles[H._MIRROR].click()                     # its popover: nothing greyed
    pop = g._popup
    assert pop.rows["fuse"].is_on() and pop.rows["fuse"].isEnabled()
    pop.rows["fuse"].click()                        # a plan tag comes off like any other
    assert H._MIRROR not in g._fuse and not pop.rows["fuse"].is_on()
    pop.rows["fuse"].click()
    assert H._MIRROR in g._fuse
    pop.hide()
    g.toggle_tag("buy", other)
    st = page.state()
    assert st["market_gifts"] == normal_cfg
    assert st["market_gifts_hollow"]["buy"] == [other]
    assert st["market_gifts_hollow"]["fuse"] == sorted(seed["fuse"])
    built = build_settings(st)["market_gifts"]
    assert built["buy"] == [other] and set(built["fuse"]) == set(seed["fuse"])
    targets = next(grp["names"] for grp in RS.md_gifts(st)
                   if grp["caption"] == "MARKET TARGETS")
    assert set(seed["fuse"]) <= set(targets) and other in targets
    # Each floor page holds what that floor keeps on top, as its own tags.
    # (Grand Welcome on floors 1 and 2; it is fuel from floor 3.)
    page._on_floor("Floor 1")
    assert g._keep_fuse == {H._WELCOME}
    assert g.config()["keep_fuse"] == seed_floors["1"]["tags"]["keep_fuse"]
    page._on_floor("Floor 4")
    assert g._keep_sell == g._keep_fuse == set()
    page._on_floor("Floor 2")
    assert g._keep_fuse == {H._WELCOME}
    g.toggle_tag("keep_sell", H._WELCOME)           # a floor's plan tag is editable too
    assert g._keep_sell == {H._WELCOME}
    page._on_floor("All floors")
    floors = page.state()["market_floors"]["hollow"]
    assert floors["2"]["tags"]["keep_sell"] == [H._WELCOME]
    assert floors["1"]["tags"]["keep_fuse"] == seed_floors["1"]["tags"]["keep_fuse"]
    # Back to normal: the normal tags return; Hollow's edits stay in its slot.
    page._custom_run.setChecked(False)
    page._sync_run()
    assert g.config() == normal_cfg
    assert page._market_slots["hollow"]["buy"] == [other]
    assert build_settings(page.state())["market_gifts"] == normal_cfg
    # Picking Hollow again keeps what is now its own config.
    page._loading = False
    try:
        page._custom_strategy.set_selected(HOLLOW_LABEL)
        page._custom_run.setChecked(True)
        page._sync_run()
    finally:
        page._loading = True
    assert g.config()["buy"] == [other]
    # Clearing every plan tag hands the shop the sheet's plan again, and the
    # rows show it again at once.
    g.reset()
    assert g.config()["fuse"] == sorted(seed["fuse"]) and g.config()["buy"] == []
    assert g._count.text() == "6 configured"
    assert set(build_settings(page.state())["market_gifts"]["fuse"]) == set(seed["fuse"])
    g.toggle_tag("buy", other)                      # a buy alone is not the plan
    g._remove_tag("fuse", H._MIRROR)
    assert g.config()["fuse"] == sorted(n for n in seed["fuse"] if n != H._MIRROR)
    assert build_settings(page.state())["market_gifts"]["fuse"] == g.config()["fuse"]
