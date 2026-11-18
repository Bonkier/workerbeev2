# SPDX-License-Identifier: GPL-3.0-or-later
"""One report, twice in the same log: Pack Search logged "secured" while its
window was still open, the pick that followed dragged on the window, and the
run sat on an unrecognised screen until the bot gave up. Pack Search now has
to see the floor screen come back, and the stuck recovery no longer presses
ESC past a screen it knows."""

import os
import time as real_time

import pytest

from wbcore import pack
from wbcore.utils import params as p
from wbcore.utils import utils as U

STEM, KEY = "ps_Line 2", "Line2"


class _Hit:
    center = (1000, 500)


class _Clock:
    """Stands in for the time module so the waits cost nothing."""

    def __init__(self):
        self.now = 0.0

    def time(self):
        return self.now

    def sleep(self, seconds):
        self.now += seconds


class _Screen:
    """The Pack Search window as the bot sees it. `closes_on` is the confirm
    round (card click + Confirm + Enter) that finally closes it, or None if
    it never does; `extra_enter` closes it on a lone Enter instead."""

    def __init__(self, closes_on=1, extra_enter=False, cancel_works=True,
                 recognisable=True, label=False, note=False):
        self.open = True
        self.label = label          # the card wears "Unselectable"
        self.note = note            # "This Theme Pack is already available."
        self.closes_on = closes_on
        self.extra_enter = extra_enter
        self.cancel_works = cancel_works
        self.recognisable = recognisable
        self.card_clicks = 0
        self.cancelled = False
        self.keys = []
        self._armed = False

    def find(self, name, region=None, **kw):
        if name == "PackChoice":
            return None if self.open else _Hit()
        if not (self.open and self.recognisable):
            return None
        if name == "unselectable":
            return _Hit() if self.label else None
        if name == "packavailable":
            return _Hit() if self.note and self.card_clicks else None
        return _Hit() if name in (STEM, "packconfirm") else None

    def click_at(self, point=None, **kw):
        if point == pack._SAIKAI_PACK_CANCEL:
            self.cancelled = True
            if self.cancel_works:
                self.open = False
        elif point == _Hit.center:
            self.card_clicks += 1
            self._armed = True

    def press(self, key, **kw):
        self.keys.append(key)
        if key == "enter":
            if self._armed and self.card_clicks == self.closes_on:
                self.open = False
            elif not self._armed and self.extra_enter:
                self.open = False
            self._armed = False
        elif key == "esc":
            self.open = False


@pytest.fixture
def env(monkeypatch):
    dumps = []
    monkeypatch.setattr(pack, "time", _Clock())
    monkeypatch.setattr(pack, "tap_center", lambda *a, **k: True)
    monkeypatch.setattr(pack, "dump_template_diag",
                        lambda tag, *names: dumps.append(tag))

    def use(screen):
        monkeypatch.setattr(pack, "ops", screen)
        return screen
    use.dumps = dumps
    return use


def test_a_confirm_that_lands_first_time_is_untouched(env):
    screen = env(_Screen(closes_on=1))
    assert pack._secure_search_pick(STEM, KEY, _Hit(), "PackSearch") is True
    assert screen.card_clicks == 1 and screen.keys == ["enter"]
    assert not screen.cancelled and env.dumps == []


def test_a_missed_confirm_is_retried_instead_of_called_secured(env):
    screen = env(_Screen(closes_on=2))
    assert pack._secure_search_pick(STEM, KEY, _Hit(), "PackSearch") is True
    assert screen.card_clicks == 2
    assert not screen.cancelled and env.dumps == []


def test_a_late_second_prompt_is_answered_without_reselecting(env):
    screen = env(_Screen(closes_on=None, extra_enter=True))
    assert pack._secure_search_pick(STEM, KEY, _Hit(), "PackSearch") is True
    assert screen.card_clicks == 1 and screen.keys == ["enter", "enter"]


def test_a_window_that_never_confirms_is_cancelled_not_left_open(env):
    screen = env(_Screen(closes_on=None))
    assert pack._secure_search_pick(STEM, KEY, _Hit(), "PackSearch") is False
    assert screen.card_clicks == pack._SEARCH_CONFIRM_TRIES
    assert screen.cancelled and not screen.open
    assert env.dumps == ["packsearch_open"]


def test_esc_backs_out_when_the_cancel_click_misses(env):
    screen = env(_Screen(closes_on=None, cancel_works=False))
    assert pack._secure_search_pick(STEM, KEY, _Hit(), "PackSearch") is False
    assert screen.keys[-1] == "esc" and not screen.open


def test_an_unrecognised_screen_is_not_clicked_on(env):
    # Neither the floor nor the search window: no cancel click, no ESC.
    screen = env(_Screen(closes_on=None, recognisable=False))
    assert pack._secure_search_pick(STEM, KEY, _Hit(), "PackSearch") is None
    assert not screen.cancelled and "esc" not in screen.keys
    assert env.dumps == ["packsearch_open"]


def test_search_reports_failure_after_a_cancel(env, monkeypatch):
    env(_Screen(closes_on=None))
    monkeypatch.setattr(pack, "PTH", {"packsearch": "x", "packconfirm": "x"})
    monkeypatch.setattr(p, "HARD", True, raising=False)
    assert pack._pack_search_window(4, [(STEM, KEY)], "PackSearch") is None


def test_search_still_returns_the_pack_when_it_closes(env, monkeypatch):
    env(_Screen(closes_on=2))
    monkeypatch.setattr(pack, "PTH", {"packsearch": "x", "packconfirm": "x"})
    monkeypatch.setattr(p, "HARD", True, raising=False)
    assert pack._pack_search_window(4, [(STEM, KEY)], "PackSearch") == KEY


def test_no_blind_pick_while_something_covers_the_floor(env, monkeypatch):
    env(_Screen(closes_on=None, recognisable=False))
    picks = []
    monkeypatch.setattr(pack, "_evaluate_packs",
                        lambda *a, **k: picks.append(k.get("strict")) or None)
    assert pack._pick_after_search(4, [], KEY, True) is None
    # Only the strict looks for the secured pack ran; the fallback did not.
    assert picks == [True] * pack._POST_SEARCH_TRIES


def test_the_fallback_pick_still_runs_on_the_floor_screen(env, monkeypatch):
    screen = env(_Screen())
    screen.open = False
    monkeypatch.setattr(pack, "_evaluate_packs",
                        lambda *a, strict=False, **k: None if strict else 2)
    assert pack._pick_after_search(4, [], KEY, False) == 2


# --- stuck recovery ----------------------------------------------------

def _fake_recovery(monkeypatch, known_after=None, menu_after=None):
    """`known_after`: ESC count at which a known screen shows. `menu_after`:
    ESC count at which the pause menu (forfeit) is up."""
    state = {"esc": 0}

    class Gui:
        @staticmethod
        def getActiveWindowTitle():
            return p.LIMBUS_NAME

        @staticmethod
        def set_window():
            pass

        @staticmethod
        def press(key, *a, **k):
            if key == "esc":
                state["esc"] += 1

    class Now:
        @staticmethod
        def button(key, *a, **k):
            return (key == "PackChoice" and known_after is not None
                    and state["esc"] >= known_after)

    class Loc:
        @staticmethod
        def button(key, *a, **k):
            return (key == "forfeit" and menu_after is not None
                    and state["esc"] == menu_after)

    monkeypatch.setattr(U, "gui", Gui)
    monkeypatch.setattr(U, "now", Now)
    monkeypatch.setattr(U, "loc", Loc)
    monkeypatch.setattr(U, "win_click", lambda *a, **k: None)
    monkeypatch.setattr(U.time, "sleep", lambda s: None)
    return state


def test_recovery_stops_at_the_first_esc_that_uncovers_a_known_screen(monkeypatch):
    state = _fake_recovery(monkeypatch, known_after=1)
    U.handle_fuckup()
    assert state["esc"] == 1          # a second would open the pause menu


def test_recovery_still_presses_twice_on_an_unknown_screen(monkeypatch):
    state = _fake_recovery(monkeypatch)
    U.handle_fuckup()
    assert state["esc"] == 2


def test_recovery_closes_a_pause_menu_it_opened(monkeypatch):
    state = _fake_recovery(monkeypatch, menu_after=2)
    U.handle_fuckup()
    assert state["esc"] == 3


def test_the_stuck_screen_is_saved_before_recovery_touches_it():
    import inspect
    from wbcore import bot
    loop = inspect.getsource(bot.main_loop)
    dump = loop.index('dump_template_diag(\n                                "stuck"')
    assert dump < loop.index("handle_fuckup()", dump)
    assert "stuck_dumped = False" in loop[loop.index("last_error = 0", dump):]
    assert '"stuck_final"' in loop


def test_old_screen_dumps_are_pruned(tmp_path):
    for i in range(U._DIAG_KEEP + 5):
        path = tmp_path / ("diag_stuck_%03d.png" % i)
        path.write_bytes(b"x")
        stamp = real_time.time() - 1000 + i
        os.utime(path, (stamp, stamp))
    (tmp_path / "keep_me.txt").write_text("not a dump")
    U._prune_diag_dumps(str(tmp_path))
    left = sorted(f.name for f in tmp_path.glob("diag_*.png"))
    assert len(left) == U._DIAG_KEEP
    assert left[0] == "diag_stuck_005.png"        # the oldest five went
    assert (tmp_path / "keep_me.txt").exists()


# --- the wanted pack is on the floor bar already ---------------------------

def test_a_card_marked_unselectable_sends_the_bot_back_to_the_floor(env):
    screen = env(_Screen(closes_on=None, label=True))
    assert pack._pack_search_window(3, [(STEM, KEY)], "T") == KEY
    assert screen.card_clicks == 0 and screen.cancelled and not screen.open


def test_the_already_available_note_cancels_the_search_and_keeps_the_pack(env):
    screen = env(_Screen(closes_on=None, note=True))
    assert pack._pack_search_window(3, [(STEM, KEY)], "T") == KEY
    assert screen.card_clicks == 1 and screen.cancelled and not screen.open


def test_the_floor_pick_is_then_retried_strictly(env, monkeypatch):
    env(_Screen(closes_on=None, label=True))
    monkeypatch.setattr(pack, "_configured_search_candidates",
                        lambda level: [(STEM, KEY)])
    monkeypatch.setattr(p, "PICK", {"floor3": []}, raising=False)
    assert pack._configured_pack_search(3) is True
    assert p.PICK["floor3"][0] == KEY


def test_the_card_band_is_waited_on_until_it_stops_moving(monkeypatch):
    import numpy as np
    frames = iter([np.full((4, 4, 3), v, np.uint8) for v in (10, 60, 120, 120)])
    last = {"f": None}

    def shot(region=None):
        last["f"] = next(frames, last["f"])
        return last["f"]
    monkeypatch.setattr(pack, "screenshot", shot)
    monkeypatch.setattr(pack, "time", _Clock())
    assert pack._wait_cards_still() is True
    assert pack.time.now == pytest.approx(0.75)       # three ticks
    moving = iter(range(100))
    monkeypatch.setattr(pack, "screenshot",
                        lambda region=None: np.full((4, 4, 3), next(moving) * 50 % 256, np.uint8))
    monkeypatch.setattr(pack, "time", _Clock())
    assert pack._wait_cards_still(timeout=1.0) is False


def test_the_window_is_searched_without_hunting_a_refresh_logo(env, monkeypatch):
    # The window lost its refresh logo; three seconds went on waiting for it.
    env(_Screen(closes_on=1))
    taps = []
    monkeypatch.setattr(pack, "tap_center",
                        lambda name, *a, **k: taps.append(name) or True)
    monkeypatch.setattr(pack, "PTH", {"packsearch": "x", "packconfirm": "x",
                                      "packrefresh": "x"})
    monkeypatch.setattr(p, "HARD", False, raising=False)
    assert pack._pack_search_window(1, [(STEM, KEY)], "PackSearch") == KEY
    assert taps == ["packsearch", "packconfirm"]
    assert pack.time.now < 6.0


# --- the window that is not there ------------------------------------------
# One report: the bot hovering over a pack, then clicking a gift under
# another pack, in a loop. The search window had not opened and the hunt
# went on over the floor screen.

class _Floor:
    """The floor screen and a Pack Search button. `opens_on` is the click
    on it that opens the window, or None if none does."""

    def __init__(self, opens_on=None):
        self.opens_on = opens_on
        self.open = False
        self.taps = 0
        self.cancel_clicks = 0
        self.scrolls = 0
        self.keys = []

    def tap(self, name, *a, **k):
        if name == "packsearch":
            self.taps += 1
            if self.opens_on is not None and self.taps >= self.opens_on:
                self.open = True
        return True

    def find(self, name, region=None, **kw):
        if name == "PackChoice":
            return None if self.open else _Hit()
        if not self.open:
            return None
        return _Hit() if name in (STEM, "packconfirm") else None

    def click_at(self, point=None, **kw):
        if point == pack._SAIKAI_PACK_CANCEL:
            self.cancel_clicks += 1
            self.open = False

    def scroll(self, *a, **k):
        self.scrolls += 1

    def press(self, key, **kw):
        self.keys.append(key)
        if key == "enter":
            self.open = False


def test_a_window_that_did_not_open_is_not_hunted_in(env, monkeypatch):
    floor = env(_Floor())
    monkeypatch.setattr(pack, "tap_center", floor.tap)
    assert pack._pack_search_window(4, [(STEM, KEY)], "PackSearch") is None
    assert floor.taps == 2                       # clicked once more, then left
    assert floor.scrolls == 0 and floor.cancel_clicks == 0
    assert env.dumps == ["packsearch_closed"]


def test_a_second_click_opens_the_window(env, monkeypatch):
    floor = env(_Floor(opens_on=2))
    monkeypatch.setattr(pack, "tap_center", floor.tap)
    monkeypatch.setattr(p, "HARD", False, raising=False)
    assert pack._pack_search_window(1, [(STEM, KEY)], "PackSearch") == KEY
    assert floor.taps == 2 and env.dumps == []


def test_cancelling_from_the_floor_screen_clicks_nothing(env):
    floor = env(_Floor())
    assert pack._cancel_search() is True
    assert floor.cancel_clicks == 0 and floor.keys == []


# --- the other difficulty's list ------------------------------------------------

class _Tabbed(_Screen):
    """A search window whose tab reads `tab`."""

    def __init__(self, tab, **kw):
        super().__init__(**kw)
        self.tab = tab

    def find(self, name, region=None, **kw):
        if name in ("normalpackUI", "hardpackUI"):
            return _Hit() if self.open and name == self.tab else None
        return super().find(name, region, **kw)


def _reopening(screen, monkeypatch):
    def tap(name, *a, **k):
        if name == "packsearch":
            screen.open = True
        return True
    monkeypatch.setattr(pack, "tap_center", tap)


def test_the_other_difficultys_list_is_closed_and_the_floor_switched(env, monkeypatch):
    screen = env(_Tabbed("normalpackUI", closes_on=1))
    switched = []

    def set_difficulty(want_hard):
        assert not screen.open                   # the window was closed first
        switched.append(want_hard)
        screen.tab = "hardpackUI"
    monkeypatch.setattr(pack, "_set_difficulty", set_difficulty)
    _reopening(screen, monkeypatch)
    monkeypatch.setattr(p, "HARD", True, raising=False)
    assert pack._pack_search_window(5, [(STEM, KEY)], "PackSearch") == KEY
    assert switched == [True] and screen.cancelled


def test_a_list_that_stays_wrong_is_cancelled_not_searched(env, monkeypatch):
    screen = env(_Tabbed("normalpackUI", closes_on=1))
    monkeypatch.setattr(pack, "_set_difficulty", lambda want_hard: None)
    _reopening(screen, monkeypatch)
    monkeypatch.setattr(p, "HARD", True, raising=False)
    assert pack._pack_search_window(5, [(STEM, KEY)], "PackSearch") is None
    assert screen.card_clicks == 0 and not screen.open


def test_the_right_list_is_searched_at_once(env, monkeypatch):
    screen = env(_Tabbed("hardpackUI", closes_on=1))
    monkeypatch.setattr(pack, "_set_difficulty",
                        lambda want_hard: pytest.fail("the switch was right"))
    monkeypatch.setattr(p, "HARD", True, raising=False)
    assert pack._pack_search_window(5, [(STEM, KEY)], "PackSearch") == KEY
    assert not screen.cancelled


# --- the floor's Normal/Hard switch ------------------------------------------------

class _Switch:
    """The switch at the top right of the floor screen. `double` holds the
    clicks the game takes twice; `readable` off hides its label and leaves
    the HARD banner under the title."""

    def __init__(self, hard=False, double=(), readable=True):
        self.hard = hard
        self.double = set(double)
        self.readable = readable
        self.clicks = 0

    def find(self, name, region=None, **kw):
        if name == "pillHard":
            return _Hit() if self.readable and self.hard else None
        if name == "pillNormal":
            return _Hit() if self.readable and not self.hard else None
        if name == "hardDifficulty":
            return _Hit() if self.hard else None
        return None

    def click_at(self, point=None, **kw):
        assert point == pack._PILL_POINT
        self.clicks += 1
        if self.clicks not in self.double:
            self.hard = not self.hard


def test_a_switch_that_reads_right_is_left_alone(env):
    switch = env(_Switch(hard=True))
    pack._set_difficulty(True)
    assert switch.clicks == 0


@pytest.mark.parametrize("want_hard", [True, False])
def test_one_click_sets_the_switch(env, want_hard):
    switch = env(_Switch(hard=not want_hard))
    pack._set_difficulty(want_hard)
    assert switch.hard is want_hard and switch.clicks == 1


def test_a_click_the_game_took_twice_is_made_again(env):
    switch = env(_Switch(hard=False, double={1}))
    pack._set_difficulty(True)
    assert switch.hard and switch.clicks == 2


def test_an_unreadable_switch_goes_by_the_banner_with_one_click(env):
    switch = env(_Switch(hard=False, readable=False))
    pack._set_difficulty(True)
    assert switch.clicks == 1
    switch = env(_Switch(hard=True, readable=False))
    pack._set_difficulty(True)
    assert switch.clicks == 0


# --- a pick that did not take ---------------------------------------------------------

def test_a_pick_that_did_not_take_is_not_followed_by_another_search(monkeypatch):
    calls = {"search": 0, "refresh": 0}

    class Ops:
        def find(self, name, region=None, **kw):
            return _Hit() if name == "PackChoice" else None

        def click_at(self, point=None, **kw):
            if point == pack._FLOOR_BAR_POINT:
                calls["refresh"] += 1

        def move_to(self, *a, **k):
            pass

        drag_to = move_to

    def search(level):
        calls["search"] += 1
        return False

    monkeypatch.setattr(pack, "ops", Ops())
    monkeypatch.setattr(pack, "time", _Clock())
    monkeypatch.setattr(pack, "_read_floor_number", lambda prev: 3)
    monkeypatch.setattr(pack, "_maybe_switch_difficulty", lambda level: None)
    monkeypatch.setattr(pack, "_set_difficulty", lambda want_hard: None)
    monkeypatch.setattr(pack, "_wait_cards_still", lambda *a, **k: True)
    monkeypatch.setattr(pack, "_configured_search_candidates",
                        lambda level: [(STEM, KEY)])
    monkeypatch.setattr(pack, "_configured_pack_search", search)
    monkeypatch.setattr(pack, "_evaluate_packs",
                        lambda level, regions, skip, skips, strict=False, only=None:
                        None if strict else 1)
    monkeypatch.setattr(pack, "wait_while_condition", lambda *a, **k: False)
    monkeypatch.setattr(pack, "dump_template_diag", lambda *a, **k: None)
    monkeypatch.setattr(p, "PACK_STUCK", {"level": None, "fails": 0})
    monkeypatch.setattr(p, "LVL", 3)
    monkeypatch.setattr(p, "HARD", False)
    monkeypatch.setattr(p, "BUFF", [0] * 12)
    monkeypatch.setattr(p, "PACK_REFRESHES", 7)
    monkeypatch.setattr(p, "PACK_SEARCH", True)
    assert pack.pack() is True
    assert calls == {"search": 1, "refresh": 1}
    assert pack.pack() is True                   # the floor screen is still up
    assert calls == {"search": 1, "refresh": 1}  # picked again, nothing else
    assert p.PACK_STUCK["fails"] == 2
