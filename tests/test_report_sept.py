# SPDX-License-Identifier: GPL-3.0-or-later
"""Regressions from one user report: an unwinnable boss re-entered for hours,
an avoided pack picked anyway, a window-size popup that stole focus, SAIKAI's
gift leaking into Thrill runs, and exported configs carrying the Discord
token. Each case uses the values from that report."""

import inspect

from PySide6.QtWidgets import QApplication

from gui_v2 import run_config, settings as S
from gui_v2 import run_coordinator as RC
from wbcore import battle, bot
from wbcore.utils import params as p
from wbcore.utils import utils as U

_app = QApplication.instance() or QApplication([])


# --- pack pins ---------------------------------------------------------

_PACKS = {
    "4": {"WARPExpressBokGak": "avoid", "Line2": "priority"},
    "5": {"WARPExpressBokGak": "avoid", "Line2": "priority",
          "TheSurrenderedWitnessing": "avoid"},
}


def test_pack_avoided_on_two_floors_is_banned_on_both(monkeypatch):
    monkeypatch.setattr(p, "HARD", True)
    monkeypatch.setattr(p, "EXTREME", False)
    _pri, avo = run_config._build_packs(_PACKS, {})
    banned = U.generate_packs_av(avo)
    assert "WARPExpressBokGak" in banned["floor4"]      # was missing
    assert "WARPExpressBokGak" in banned["floor5"]
    assert "TheSurrenderedWitnessing" in banned["floor5"]


def test_pack_prioritised_on_two_floors_is_wanted_on_both(monkeypatch):
    monkeypatch.setattr(p, "HARD", True)
    monkeypatch.setattr(p, "EXTREME", False)
    pri, avo = run_config._build_packs(_PACKS, {})
    pick = U.generate_packs_pr(pri)
    assert "Line2" in pick["floor4"] and "Line2" in pick["floor5"]
    # A single-floor pin used to BAN the pack on its other floor.
    assert "Line2" not in U.generate_packs_av(avo)["floor4"]


def test_scripted_single_floor_pins_still_work(monkeypatch):
    monkeypatch.setattr(p, "HARD", False)
    monkeypatch.setattr(p, "EXTREME", False)
    pick = U.generate_packs_pr(run_config._SAIKAI_PRIORITY)
    assert pick["floor1"] == ["FlatbrokeGamblers"]
    assert "HellsChicken" in pick["floor2"]
    assert "FlatbrokeGamblers" not in pick["floor2"]


def test_saikai_run_honours_the_users_two_floor_avoid(monkeypatch):
    monkeypatch.setattr(p, "HARD", True)
    monkeypatch.setattr(p, "EXTREME", False)
    avo = run_config._scripted_avoid_with_user(
        run_config._SAIKAI_AVOID, run_config._SAIKAI_PRIORITY,
        {"packs": _PACKS, "global_packs": {}})
    assert "WARPExpressBokGak" in U.generate_packs_av(avo)["floor4"]


# --- unwinnable battle -------------------------------------------------

def test_a_stuck_battle_asks_for_the_run_to_be_forfeited():
    src = inspect.getsource(battle.fight)
    stuck = src[src.index("Got stuck in hard battle"):]
    assert "p.STUCK_FORFEIT = True" in stuck[:stuck.index("Re-attempting")]
    loop = inspect.getsource(bot.main_loop)
    assert "_forfeit_stuck_run()" in loop
    assert p.STUCK_FORFEIT is False


def _fake_forfeit_env(monkeypatch, visible):
    """Stub the screen and input. `visible` maps a template to the ESC press
    count at which it becomes visible."""
    state = {"esc": 0, "chain": 0}

    class Now:
        @staticmethod
        def button(key, *a, **k):
            need = visible.get(key)
            return need is not None and state["esc"] >= need

    class Gui:
        PauseException = bot.gui.PauseException

        @staticmethod
        def press(key, *a, **k):
            if key == "esc":
                state["esc"] += 1

    monkeypatch.setattr(bot, "now", Now)
    monkeypatch.setattr(bot, "gui", Gui)
    monkeypatch.setattr(bot, "chain_actions",
                        lambda *a, **k: state.__setitem__("chain", state["chain"] + 1))
    monkeypatch.setattr(bot, "connection", lambda: None)
    monkeypatch.setattr(bot.time, "sleep", lambda s: None)
    return state


def test_forfeit_presses_esc_until_the_menu_is_up(monkeypatch):
    # First ESC closes the node panel, the second opens the pause menu.
    state = _fake_forfeit_env(monkeypatch, {"forfeit": 2})
    bot._forfeit_stuck_run()
    assert state["esc"] == 2
    assert state["chain"] == 1


def test_forfeit_does_nothing_when_already_on_the_defeat_screen(monkeypatch):
    state = _fake_forfeit_env(monkeypatch, {"defeat": 0})
    bot._forfeit_stuck_run()
    assert state["esc"] == 0 and state["chain"] == 0


# --- window-size advice ------------------------------------------------

def test_window_size_advice_does_not_ping_discord_or_block(monkeypatch):
    advised, pinged, blocking = [], [], []

    class Fake:
        _ui = None

        def _discord_stuck(self, reason):
            pinged.append(reason)

    monkeypatch.setattr(RC, "show_resolution_help",
                        lambda parent, text, **k: advised.append(text))
    monkeypatch.setattr(RC, "show_notice",
                        lambda parent, text, **k: blocking.append(text))
    RC.RunCoordinator._on_warning(
        Fake(), "Game window (1920 x 1200) is not 16:9\nIt is recommended...")
    assert len(advised) == 1
    assert pinged == [] and blocking == []

    # A real failure still pings and blocks.
    RC.RunCoordinator._on_warning(Fake(), "Scheduler has no enabled tasks.")
    assert len(pinged) == 1 and blocking == ["Scheduler has no enabled tasks."]


def test_the_advisory_is_shown_without_taking_focus():
    from gui_v2 import dialogs as D
    dlg = D.show_advisory(None, "Game window (1920 x 1200) is not 16:9")
    try:
        assert not dlg.isModal()
        assert dlg.testAttribute(RC.Qt.WidgetAttribute.WA_ShowWithoutActivating)
        assert dlg.windowFlags() & RC.Qt.WindowType.WindowDoesNotAcceptFocus
    finally:
        dlg.close()


def test_window_size_advice_is_raised_once_per_size():
    from wbcore.utils import os_windows_backend as B
    src = inspect.getsource(B.set_window)
    assert "_advised_window_size != (client_width, client_height)" in src
    assert B._advised_window_size is None or isinstance(
        B._advised_window_size, tuple)


# --- the SAIKAI gift lock ----------------------------------------------

def test_turning_saikai_off_unequips_its_gift():
    from gui_v2.mirror_dungeon_page import _GiftGallery
    g = _GiftGallery()
    gift = "Spiderweb Entangled in Red"
    assert gift in g._tiles
    g.set_locked([gift])                 # SAIKAI
    assert gift in g.selected()
    g.set_locked([])                     # switch to Thrill
    assert gift not in g.selected()


def test_it_is_unequipped_even_if_it_was_picked_before_saikai():
    from gui_v2.mirror_dungeon_page import _GiftGallery
    g = _GiftGallery()
    gift = "Spiderweb Entangled in Red"
    other = next(n for n in g._tiles if n != gift)
    g.set_selected([gift, other])
    g.set_locked([gift])
    g.set_locked([])
    assert gift not in g.selected()
    assert other in g.selected()         # other picks are left alone
    g.set_selected([gift])               # and it can be picked by hand again
    assert gift in g.selected()


# --- exports and credentials -------------------------------------------

_SECRET = {"enabled": True, "token_enc": "dpapi:AAAA", "channel_id": "1"}


def _fake_store(monkeypatch, configs, live):
    monkeypatch.setattr(S, "_load_configs", lambda: configs)
    monkeypatch.setattr(S, "_save_configs", lambda c: None)
    monkeypatch.setattr(S, "load_settings", lambda: dict(live))
    applied = []
    monkeypatch.setattr(S, "replace_all_settings", applied.append)
    return applied


def test_export_never_writes_the_discord_section(monkeypatch, tmp_path):
    _fake_store(monkeypatch,
                {"THRILL": {"mirror": {"run_count": 3}, "discord": _SECRET}}, {})
    out = tmp_path / "THRILL.json"
    assert S.export_config_to("THRILL", str(out))
    text = out.read_text(encoding="utf-8")
    assert "token_enc" not in text and "dpapi" not in text
    assert "channel_id" not in text
    assert '"run_count": 3' in text


def test_import_drops_a_foreign_token_and_load_keeps_the_local_one(
        monkeypatch, tmp_path):
    import json
    configs = {}
    applied = _fake_store(monkeypatch, configs,
                          {"discord": {"token_enc": "dpapi:LOCAL"}})
    src = tmp_path / "shared.json"
    src.write_text(json.dumps({
        "format": S._EXPORT_TAG, "name": "shared",
        "settings": {"mirror": {"run_count": 9}, "discord": _SECRET}}),
        encoding="utf-8")
    assert S.import_config_from(str(src)) == "shared"
    assert "discord" not in configs["shared"]
    assert S.load_config("shared")
    assert applied[0]["discord"] == {"token_enc": "dpapi:LOCAL"}
    assert applied[0]["mirror"] == {"run_count": 9}
