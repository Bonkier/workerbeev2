# SPDX-License-Identifier: GPL-3.0-or-later
"""The start overlay: what the summary says, and that the countdown, the
Start now / Cancel buttons and the coordinator all agree on one pending
start."""

import pytest
from PySide6.QtCore import QObject, QTimer
from PySide6.QtWidgets import QApplication, QWidget

from gui_v2 import run_coordinator as RC
from gui_v2 import run_summary as R
from gui_v2.run_config import SAIKAI_LABEL
from tests.conftest import destroy

_app = QApplication.instance() or QApplication([])


def _rows(sections):
    return {label: value for _cap, rows in sections for label, value in rows}


# --- the summary text --------------------------------------------------

_SAIKAI = {
    "custom_run": True, "custom_strategy": SAIKAI_LABEL, "run_count": 9999,
    "retry_count": 0, "pack_refreshes": 3,
    "gift_search": ["Spiderweb Entangled in Red"],
    "market_gifts_saikai": {"buy": list("abcdef"), "fuse": ["a", "b"],
                            "enhance1": [], "enhance2": ["a", "c", "d", "e"]},
    "market_controls": {"default_market_workflow": True},
    "skill_replace": {"active": ["Ryōshū"]},
    "behaviour": {"bonus": True, "restart": True, "pack_search": True,
                  "altf4": False, "claim_on_defeat": False},
    "packs": {"4": {"Line2": "priority", "WARPExpressBokGak": "avoid"},
              "5": {"Line2": "priority", "WARPExpressBokGak": "avoid"}},
    "global_packs": {"LakeWorld": "avoid"},
    "saikai_status": "Poise", "saikai_order": ["Ryōshū", "Faust"],
}


def test_saikai_summary_reads_like_the_run_that_will_happen():
    rows = _rows(R.md_summary(_SAIKAI, {"mouse_speed": 110,
                                        "macro_profile": "Safe"}))
    assert rows["Runs"] == "Loop forever"
    assert rows["Difficulty"] == "Normal, then Hard from floor 4"
    assert rows["Retries on defeat"] == "Unlimited"
    assert rows["Team keyword"] == "Poise"
    assert rows["Market"] == "Custom: buy 6, fuse 2, uptie 4"
    assert rows["Skill replacement"] == "Ryōshū"
    assert rows["Pack search"] == "The run's own packs, 3 refreshes"
    # A pack set on two floors is one pack, not two.
    assert rows["Packs"] == "1 prioritised, 2 avoided"
    assert rows["Switched on"] == "Claim bonus, Restart on failure"
    assert rows["Mouse"] == "110% speed, Safe profile"


def test_saikai_difficulty_variants():
    def diff(**over):
        return _rows(R.md_summary(dict(_SAIKAI, **over)))["Difficulty"]
    assert diff(hard_from_floor=1) == "Hard on every floor"
    assert diff(hard_from_floor=0) == "Normal on every floor"
    assert diff(hard_from_floor=2) == "Normal, then Hard from floor 2"
    assert diff(saikai_floor10=True).endswith("leaving after floor 10")


def test_standard_run_summary():
    md = {
        "custom_run": False, "custom_strategy": SAIKAI_LABEL,   # ignored
        "difficulty": "Hard", "run_count": 3, "retry_count": 2,
        "pack_refreshes": 1, "gift_search": [],
        "market_controls": {"default_market_workflow": True},
        "teams": [{"name": "Burn", "affinities": ["Burn", "Wrath"]},
                  {"name": "Poise", "affinities": ["Poise"]}],
        "behaviour": {"pack_search": False},
    }
    rows = _rows(R.md_summary(md))
    assert rows["Runs"] == "3" and "Strategy" not in rows
    assert rows["Difficulty"] == "Hard"
    assert rows["Retries on defeat"] == "2"
    assert rows["Team rotation"] == "Burn (Burn, Wrath), Poise (Poise)"
    assert rows["Market"] == "Default workflow"
    assert rows["Skill replacement"] == "Off"
    assert rows["Pack search"] == "No floor configured, 1 refresh"
    assert rows["Switched on"] == "Nothing"
    assert "Mouse" not in rows                  # no app settings given


def test_thrill_summary():
    rows = _rows(R.md_summary({"custom_run": True, "custom_strategy": "Thrill",
                               "thrill_status": "Rupture"}))
    assert rows["Difficulty"] == "Normal, forfeit after floor 3"
    assert rows["Team keyword"] == "Rupture"
    assert rows["Sinner order"] == "Default"


def test_lux_summaries():
    lux = {"exp_runs": 5, "exp_stage": "VIII", "exp_team": "Slash",
           "thd_runs": 2, "thd_diff": "50", "thd_team": "Burn"}
    assert _rows(R.lux_summary("exp", lux)) == {
        "Runs": "5", "Stage": "VIII", "Team": "Slash"}
    assert _rows(R.lux_summary("thread", lux)) == {
        "Runs": "2", "Difficulty": "50", "Team": "Burn"}
    assert R.run_title("exp") == "EXP Luxcavation"
    assert R.run_title("thread") == "Thread Luxcavation"
    assert R.run_title("md") == "Mirror Dungeon"


def test_every_behaviour_toggle_on_the_page_has_a_label(monkeypatch):
    import gui_v2.settings as st
    import gui_v2.mirror_dungeon_page as M
    monkeypatch.setattr(st, "save_section", lambda *a, **k: None)
    monkeypatch.setattr(M, "save_section", lambda *a, **k: None)
    page = M.MirrorDungeonPage()
    page._loading = True
    keys = set(page.state()["behaviour"]) - {"pack_search"}
    assert keys <= set(R.BEHAVIOUR_LABELS), keys - set(R.BEHAVIOUR_LABELS)


def test_summary_text_has_no_long_dashes():
    text = repr(R.md_summary(_SAIKAI, {"mouse_speed": 100}))
    assert chr(0x2014) not in text and chr(0x2013) not in text


# --- countdown wiring --------------------------------------------------

class _Page:
    def __init__(self):
        self.armed = []

    def set_arming(self, seconds):
        self.armed.append(seconds)

    def state(self):
        return dict(_SAIKAI)


class _GameOverlay:
    """Stands in for the over-the-game RunOverlay and records what it is told."""

    def __init__(self):
        self.pending = None
        self.calls = []

    def set_pending(self, summary, seconds, cancel_key="F2"):
        self.pending = {"title": summary["title"], "summary": summary,
                        "remaining": seconds, "cancel_key": cancel_key}
        self.calls.append(("set", seconds))

    def set_pending_remaining(self, seconds):
        if self.pending is not None:
            self.pending["remaining"] = seconds
        self.calls.append(("tick", seconds))

    def clear_pending(self):
        self.pending = None
        self.calls.append(("clear", 0))


class _Controller:
    def is_running(self):
        return False


class _Coord(QObject):
    """RunCoordinator's countdown methods on a bare object: building the real
    coordinator would register global hotkeys and start the Discord bot."""

    def __init__(self, host):
        super().__init__()
        self._ui = host
        self._controller = _Controller()
        self._settings = None
        self._md = _Page()
        self._lux = _Page()
        self._countdown_timer = QTimer(self)
        self._countdown_remaining = 0
        self._countdown_action = None
        self._countdown_page = None
        self._BUTTON_START_DELAY_S = 10
        self._start_overlay = None
        self._overlay = _GameOverlay()
        self.warnings = []
        self.fired = []

    def _on_warning(self, msg):
        self.warnings.append(msg)

    def _md_state(self):
        return self._md.state()

    def _start_md(self):
        self.fired.append("md")

    def _start_lux(self, mode):
        self.fired.append(mode)

    def _stop(self):
        self.fired.append("stop")


for _name in ("_arm_button_start", "_pending_summary", "_open_start_overlay",
              "_apply_arming", "_on_countdown_tick", "_fire_pending_start",
              "_cancel_countdown", "_toggle_md", "_toggle_lux",
              "_hollow_fallback_ok"):
    setattr(_Coord, _name, getattr(RC.RunCoordinator, _name))


@pytest.fixture
def coord(monkeypatch):
    monkeypatch.setattr(RC, "build_md_run", lambda *a, **k: (1, {}, {}, True))
    monkeypatch.setattr(RC, "build_lux_run", lambda *a, **k: (1, 0, {}, {}, True))
    monkeypatch.setattr(RC, "load_section", lambda name: {"mouse_speed": 100})
    host = QWidget()
    host.resize(1200, 800)
    host.show()
    c = _Coord(host)
    c._host = host                      # keep it alive for the test
    yield c
    # The start lambda closes over `c`, so this graph is a reference cycle:
    # take it apart in order here instead of leaving it to the collector.
    c._countdown_timer.stop()
    c._countdown_action = None
    destroy(c._start_overlay, host, c)


def _arm(c, kind="md"):
    c._arm_button_start(lambda: c.fired.append(kind), c._md, kind)


def test_pressing_start_opens_the_overlay_at_ten(coord):
    _arm(coord)
    ov = coord._start_overlay
    assert ov.isVisible() and ov._count.text() == "10"
    assert ov.geometry() == coord._ui.rect()
    assert coord._md.armed[-1] == 10 and coord.fired == []
    assert coord._countdown_timer.isActive()


def test_the_overlay_counts_down_and_starts_at_zero(coord):
    _arm(coord)
    for _ in range(3):
        coord._on_countdown_tick()
    assert coord._start_overlay._count.text() == "7" and coord.fired == []
    for _ in range(7):
        coord._on_countdown_tick()
    assert coord.fired == ["md"]
    assert not coord._start_overlay.isVisible()
    assert not coord._countdown_timer.isActive()


def test_start_now_skips_the_wait_and_fires_once(coord):
    _arm(coord)
    coord._start_overlay.start_now.emit()
    assert coord.fired == ["md"]
    assert not coord._start_overlay.isVisible()
    coord._on_countdown_tick()                  # a late tick must not re-fire
    assert coord.fired == ["md"]


def test_cancel_closes_the_overlay_and_starts_nothing(coord):
    _arm(coord)
    coord._start_overlay.cancelled.emit()
    assert coord.fired == []
    assert not coord._start_overlay.isVisible()
    assert not coord._countdown_timer.isActive()
    assert coord._md.armed[-1] == 0             # the page button is restored


def test_a_run_that_cannot_be_built_reports_now_not_after_the_wait(
        coord, monkeypatch):
    def boom(*a, **k):
        raise ValueError("Add at least one team first.")
    monkeypatch.setattr(RC, "build_md_run", boom)
    _arm(coord)
    assert coord.warnings == ["Add at least one team first."]
    assert coord._start_overlay is None
    assert not coord._countdown_timer.isActive() and coord.fired == []


def test_luxcavation_gets_its_own_title_and_rows(coord):
    _arm(coord, "exp")
    ov = coord._start_overlay
    assert ov.isVisible()
    from PySide6.QtWidgets import QLabel
    texts = {w.text() for w in ov.findChildren(QLabel)}
    assert "Stage" in texts and "Strategy" not in texts


# --- the same countdown, over the game ---------------------------------

def test_the_game_overlay_is_told_the_same_thing_as_the_window(coord):
    _arm(coord)
    game = coord._overlay
    assert game.pending["title"] == "Mirror Dungeon"
    assert game.pending["remaining"] == 10
    for _ in range(4):
        coord._on_countdown_tick()
    assert game.pending["remaining"] == 6
    assert coord._start_overlay._count.text() == "6"
    coord._start_overlay.cancelled.emit()
    assert game.pending is None                 # cancelled in both places


def test_the_game_overlay_is_cleared_when_the_run_starts(coord):
    _arm(coord)
    coord._start_overlay.start_now.emit()
    assert coord._overlay.pending is None and coord.fired == ["md"]


def test_the_game_overlay_names_the_configured_stop_key(coord, monkeypatch):
    monkeypatch.setattr(RC, "load_section",
                        lambda name: {"shortcuts": {"stop": "F6"}})
    _arm(coord)
    assert coord._overlay.pending["cancel_key"] == "F6"


def _real_overlay(monkeypatch, focused, rect=(100, 50, 1280, 720)):
    from gui_v2 import overlay as O
    ov = O.RunOverlay()
    state = {"focused": focused}
    monkeypatch.setattr(ov, "_game_focused", lambda: state["focused"])
    monkeypatch.setattr(ov, "_live_game_rect", lambda: rect)
    monkeypatch.setattr(ov, "_dpr", lambda: 1.0)
    return ov, state


def test_pending_shows_over_a_focused_game_before_any_run(monkeypatch):
    ov, state = _real_overlay(monkeypatch, focused=True)
    assert not ov._run_active
    ov.set_pending(R.md_start(_SAIKAI), 10)
    assert ov.isVisible()
    assert (ov.x(), ov.y(), ov.width(), ov.height()) == (100, 50, 1280, 720)
    # Tab away from the game: it must not sit on top of other windows.
    state["focused"] = False
    ov._track()
    assert not ov.isVisible()
    state["focused"] = True
    ov._track()
    assert ov.isVisible()
    ov.clear_pending()
    assert not ov.isVisible() and ov._pending is None
    destroy(ov)


def test_pending_never_schedules_the_capture_probe(monkeypatch):
    # The probe paints a magenta block: fine mid-run, not over the summary.
    ov, _state = _real_overlay(monkeypatch, focused=True)
    ov.set_pending({"title": "Mirror Dungeon"}, 10)
    assert ov.isVisible() and not ov._probe_scheduled
    ov.clear_pending()
    destroy(ov)


def test_pending_paints_without_error_at_small_and_large_sizes(monkeypatch):
    from gui_v2 import overlay as O
    from PySide6.QtGui import QPixmap
    for size in ((1920, 1080), (1280, 720), (800, 450)):
        ov = O.RunOverlay(preview=True)
        ov.resize(*size)
        ov.set_pending(R.md_start(_SAIKAI, {"mouse_speed": 100}), 10)
        pm = QPixmap(*size)
        ov.render(pm)
        ov.set_pending_remaining(1)
        ov.render(pm)
        ov.clear_pending()
        ov.render(pm)
        destroy(ov)


# --- start hotkeys go through the same countdown ------------------------

def test_the_md_hotkey_shows_the_overlay_instead_of_starting_at_once(coord):
    coord._toggle_md()
    assert coord.fired == []                    # nothing has started yet
    assert coord._start_overlay.isVisible()
    assert coord._overlay.pending["title"] == "Mirror Dungeon"
    assert coord._overlay.pending["remaining"] == 10
    for _ in range(10):
        coord._on_countdown_tick()
    assert coord.fired == ["md"]


def test_pressing_the_hotkey_again_cancels_the_pending_start(coord):
    coord._toggle_md()
    coord._toggle_md()
    assert coord.fired == []
    assert not coord._countdown_timer.isActive()
    assert coord._overlay.pending is None
    assert not coord._start_overlay.isVisible()


def test_the_lux_hotkeys_show_their_own_summary(coord):
    coord._toggle_lux("thread")
    assert coord.fired == []
    assert coord._overlay.pending["title"] == "Thread Luxcavation"
    for _ in range(10):
        coord._on_countdown_tick()
    assert coord.fired == ["thread"]


def test_a_hotkey_during_a_run_still_stops_it(coord):
    coord._controller.is_running = lambda: True
    coord._toggle_md()
    assert coord.fired == ["stop"] and coord._start_overlay is None


# --- headline and gift art ---------------------------------------------

def test_start_summary_carries_the_run_type_and_the_gifts():
    start = R.md_start(_SAIKAI, {"mouse_speed": 100})
    assert start["title"] == "Mirror Dungeon"
    assert start["subtitle"] == SAIKAI_LABEL
    search, market = start["gifts"]
    assert search == {"caption": "GIFT SEARCH", "named": True,
                      "names": ["Spiderweb Entangled in Red"]}
    # buy, fuse and uptie lists merged, each gift once, in that order.
    assert market["names"] == list("abcdef") and market["named"] is False


def test_a_standard_run_on_the_default_market_shows_no_market_art():
    md = {"custom_run": False, "gift_search": [],
          "market_controls": {"default_market_workflow": True}}
    start = R.md_start(md)
    assert start["subtitle"] == "Standard run"
    assert [g["caption"] for g in start["gifts"]] == ["GIFT SEARCH"]
    assert start["gifts"][0]["names"] == []
    assert R.lux_start("exp", {})["gifts"] == []


def test_the_run_type_is_the_largest_text_on_the_panel(coord):
    from gui_v2.voxel import PixelLabel
    from gui_v2.skins import is_voxel
    _arm(coord)
    ov = coord._start_overlay
    if not is_voxel():
        pytest.skip("pixel sizes only apply to the voxel skin")
    labels = ov.findChildren(PixelLabel)
    title = next(l for l in labels if l.text() == "MIRROR DUNGEON")
    assert title._pixel == max(l._pixel for l in labels)
    assert title._pixel > ov._count._pixel
    # Square brackets are not in the pixel face; the subtitle uses round ones.
    assert any(l.text() == "SAIKAI (RYOSHU)" for l in labels)


def test_gift_art_is_shown_for_the_chosen_gifts(coord):
    from PySide6.QtWidgets import QLabel
    from gui_v2 import start_overlay as SO
    assert SO.gift_pixmap("Spiderweb Entangled in Red", SO.GIFT_TILE) is not None
    assert SO.gift_pixmap("No Such Gift", SO.GIFT_TILE) is None
    _arm(coord)
    labels = coord._start_overlay.findChildren(QLabel)
    art = [l for l in labels if l.toolTip() == "Spiderweb Entangled in Red"]
    assert art and art[0].pixmap() is not None and not art[0].pixmap().isNull()
    # A gift with no art gets a framed "?" slot, not a broken image.
    assert any(l.text() == "?" for l in labels)


# --- Hollow without a fallback team -----------------------------------------

def test_hollow_without_a_fallback_team_asks_before_arming(coord, monkeypatch):
    import gui_v2.dialogs as D
    from gui_v2.run_config import HOLLOW_LABEL
    asked, revealed = [], []
    answer = {"v": "secondary"}
    monkeypatch.setattr(D, "ask_choice", lambda *a, **k: asked.append(k) or answer["v"])
    coord._ui._reveal_stk_settings = lambda run=None: revealed.append(run)
    coord._md_state = lambda: {"custom_run": True, "custom_strategy": HOLLOW_LABEL,
                               "hollow_order": ["Faust"]}
    _arm(coord)
    assert len(asked) == 1 and asked[0]["secondary"] == "Go to HOLLOW settings"
    assert revealed == ["Hollow"] and coord.fired == []
    assert not coord._countdown_timer.isActive()
    answer["v"] = "primary"
    _arm(coord)
    assert len(asked) == 2 and coord._countdown_timer.isActive()
    coord._cancel_countdown()
    # A fallback team set, or another strategy: no question.
    coord._md_state = lambda: {"custom_run": True, "custom_strategy": HOLLOW_LABEL,
                               "hollow_order": ["Faust", "Gregor"]}
    _arm(coord)
    assert len(asked) == 2 and coord._countdown_timer.isActive()
    coord._cancel_countdown()
    answer["v"] = None
    coord._md_state = lambda: {"custom_run": True, "custom_strategy": "F3 Hard",
                               "hollow_order": []}
    _arm(coord)
    assert len(asked) == 2 and coord._countdown_timer.isActive()
