# SPDX-License-Identifier: GPL-3.0-or-later
"""Offscreen functional tests for the Market/Fuse tab: the fuse/enhance gift
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
    yield pg
    pg.deleteLater()
    assert _config_bytes() == before


def _tile_names(gallery, count):
    names = sorted(gallery._tiles)
    if len(names) < count:
        pytest.skip("market catalog unavailable")
    return names[:count]


def test_new_tag_modes_and_badges(page):
    from gui_v2.mirror_dungeon_page import (
        _MARKET_ENH1_COL, _MARKET_ENH2_COL, _MARKET_FUSE_COL,
    )
    g = page._market_gallery
    name, = _tile_names(g, 1)
    tile = g._tiles[name]
    g.reset()

    g._mode_btns["fuse"].click()
    tile.click()
    assert name in g._fuse
    assert ("C", _MARKET_FUSE_COL) in tile._badges()

    g._mode_btns["enhance1"].click()
    tile.click()
    assert name in g._enh1
    assert ("E1", _MARKET_ENH1_COL) in tile._badges()

    g._mode_btns["enhance2"].click()
    tile.click()
    assert name in g._enh2 and name not in g._enh1
    assert ("E2", _MARKET_ENH2_COL) in tile._badges()

    g._mode_btns["enhance1"].click()
    tile.click()
    assert name in g._enh1 and name not in g._enh2
    assert name in g._fuse
    assert g._count.text() == "1 configured"


def test_config_roundtrip(page):
    g = page._market_gallery
    a, b = _tile_names(g, 2)
    g.reset()

    g._mode_btns["fuse"].click()
    g._tiles[a].click()
    g._mode_btns["enhance1"].click()
    g._tiles[a].click()
    g._mode_btns["enhance2"].click()
    g._tiles[b].click()

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
    assert len(SAIKAI_MARKET_KEEP) == 7
    assert SAIKAI_MARKET_TAGS["keep_fuse"] == SAIKAI_MARKET_KEEP
    assert SAIKAI_MARKET_TAGS["keep_sell"] == SAIKAI_MARKET_KEEP
    # Only the two T4s are fuse targets; all six craft gifts are buys.
    assert SAIKAI_MARKET_TAGS["fuse"] == [
        "Clear Mirror, Calm Water", "Sundered Memory"]
    assert SAIKAI_MARKET_TAGS["buy"] == SAIKAI_MARKET_KEEP[1:]
    assert SAIKAI_MARKET_TAGS["enhance2"] == [
        "Clear Mirror, Calm Water", "Nebulizer", "Stone Tomb",
        "Emerald Elytra"]
    cat = load_market_catalog()
    if not cat:
        pytest.skip("market catalog unavailable")
    for name in SAIKAI_MARKET_KEEP:
        assert name in cat, name


def test_saikai_market_slot_swap(page):
    from gui_v2.mirror_dungeon_page import SAIKAI_LABEL
    g = page._market_gallery
    if "Clear Mirror, Calm Water" not in g._tiles:
        pytest.skip("market catalog unavailable")

    # Start from a known normal config.
    page._custom_run.setChecked(True)
    page._apply_custom_run(True)
    page._custom_strategy.set_selected("F3 Hard")
    page._update_gift_lock()
    g.reset()
    g._mode_btns["sell"].click()
    other = next(n for n in g._tiles
                 if n != "Clear Mirror, Calm Water")
    g._tiles[other].click()
    normal_cfg = g.config()
    assert other in normal_cfg["sell"]

    # SAIKAI selected: gallery swaps to the preset-seeded, EDITABLE slot.
    page._custom_strategy.set_selected(SAIKAI_LABEL)
    page._update_gift_lock()
    assert page._market_slot == "saikai"
    cfg = g.config()
    assert cfg["fuse"] == ["Clear Mirror, Calm Water", "Sundered Memory"]
    assert len(cfg["keep_fuse"]) == 7
    assert other not in cfg["sell"]

    # Fully configurable: untag a preset gift, tag another one.
    g._mode_btns["fuse"].click()
    g._tiles["Clear Mirror, Calm Water"].click()
    assert "Clear Mirror, Calm Water" not in g.config()["fuse"]
    g._tiles[other].click()
    assert other in g.config()["fuse"]

    # state() carries both slots independently.
    st = page.state()
    assert st["market_gifts"] == normal_cfg
    assert other in st["market_gifts_saikai"]["fuse"]
    assert "Clear Mirror, Calm Water" not in st["market_gifts_saikai"]["fuse"]

    # Back to normal: the normal config returns; SAIKAI edits persist in slot.
    page._custom_strategy.set_selected("F3 Hard")
    page._update_gift_lock()
    assert page._market_slot == "normal"
    assert g.config() == normal_cfg
    assert other in page._market_slots["saikai"]["fuse"]

    page._custom_strategy.set_selected(SAIKAI_LABEL)
    page._update_gift_lock()
    assert other in g.config()["fuse"]


def test_saikai_run_uses_saikai_slot():
    from gui_v2.run_config import SAIKAI_LABEL, build_settings
    base = {"custom_run": True, "custom_strategy": SAIKAI_LABEL}

    # Never saved: seeded from the preset.
    seeded = build_settings(dict(base))["market_gifts"]
    assert seeded["fuse"] == ["Clear Mirror, Calm Water", "Sundered Memory"]

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
