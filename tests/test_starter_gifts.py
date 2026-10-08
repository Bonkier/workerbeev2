# SPDX-License-Identifier: GPL-3.0-or-later
"""The starter-gift confirms: each GET dialog is cleared with Enter and the
loop leaves the moment the EGO Gift Search menu shows."""
import types

from wbcore import bot as B
from wbcore.utils import params as p


def _screen(monkeypatch, frames):
    """`frames`: the markers visible at each poll; sleeping moves to the next."""
    it = iter(frames)
    cur = {"v": next(it), "sleeps": 0, "clicks": []}
    monkeypatch.setattr(B, "now", types.SimpleNamespace(
        button=lambda name, *a, **k: name in cur["v"]))
    monkeypatch.setattr(B, "now_click", types.SimpleNamespace(
        button=lambda name, *a, **k: (cur["clicks"].append(name), name in cur["v"])[1]
        if name in cur["v"] else False))

    def tick(_s):
        cur["sleeps"] += 1
        cur["v"] = next(it, cur["v"])
    monkeypatch.setattr(B.time, "sleep", tick)
    return cur


def test_the_menu_showing_steadily_ends_the_wait(monkeypatch):
    cur = _screen(monkeypatch, [{"giftsearch"}])
    assert B._starter_get_dialog() is False
    assert cur["sleeps"] == 2                                # three polls, 0.2 s


def test_a_passing_menu_frame_does_not_end_the_wait(monkeypatch):
    cur = _screen(monkeypatch, [{"giftsearch"}, set(), {"packconfirm"}])
    assert B._starter_get_dialog() is True


def test_a_get_dialog_is_reported_at_once(monkeypatch):
    cur = _screen(monkeypatch, [{"packconfirm"}, {"giftsearch"}])
    assert B._starter_get_dialog() is True
    assert cur["sleeps"] == 0


def test_the_wait_polls_until_either_shows(monkeypatch):
    cur = _screen(monkeypatch, [set(), set(), set(), {"packconfirm"}])
    assert B._starter_get_dialog() is True and cur["sleeps"] == 3
    cur = _screen(monkeypatch, [set(), set(), {"giftsearch"}])
    assert B._starter_get_dialog() is False and cur["sleeps"] == 4


def test_the_wait_gives_up_after_its_timer(monkeypatch):
    clock = {"t": 0.0}
    monkeypatch.setattr(B.time, "time", lambda: clock.__setitem__("t", clock["t"] + 0.5) or clock["t"])
    cur = _screen(monkeypatch, [set()])
    assert B._starter_get_dialog(timer=2.0) is False
    assert cur["sleeps"] <= 4


def test_one_starter_gift_means_one_enter_then_the_search(monkeypatch):
    calls = {"enter": 0, "search": None, "waited": 0}
    dialogs = iter([True, False])
    monkeypatch.setattr(B, "_select_archetype_gifts", lambda *a, **k: None)
    monkeypatch.setattr(B, "_starter_get_dialog", lambda timer=3.0: next(dialogs))
    monkeypatch.setattr(B, "wait_while_condition",
                        lambda *a, **k: calls.__setitem__("waited", calls["waited"] + 1) or True)
    monkeypatch.setattr(B.gui, "press",
                        lambda key: calls.__setitem__("enter", calls["enter"] + (key == "enter")))
    monkeypatch.setattr(B.time, "sleep", lambda s: None)
    monkeypatch.setattr(B, "gift_search", lambda t: calls.__setitem__("search", list(t)))
    monkeypatch.setattr(p, "RUN_SCRIPT", "")
    monkeypatch.setattr(p, "GIFT_SEARCH", ["Carmilla"], raising=False)
    B.select_starting_gift()
    assert calls == {"enter": 1, "search": ["Carmilla"], "waited": 1}


def test_two_starter_gifts_mean_two_enters(monkeypatch):
    calls = {"enter": 0}
    dialogs = iter([True, True, False])
    monkeypatch.setattr(B, "_select_archetype_gifts", lambda *a, **k: None)
    monkeypatch.setattr(B, "_starter_get_dialog", lambda timer=3.0: next(dialogs))
    monkeypatch.setattr(B, "wait_while_condition", lambda *a, **k: True)
    monkeypatch.setattr(B.gui, "press",
                        lambda key: calls.__setitem__("enter", calls["enter"] + (key == "enter")))
    monkeypatch.setattr(B.time, "sleep", lambda s: None)
    monkeypatch.setattr(B, "gift_search", lambda t: None)
    monkeypatch.setattr(p, "RUN_SCRIPT", "")
    monkeypatch.setattr(p, "GIFT_SEARCH", ["Carmilla"], raising=False)
    B.select_starting_gift()
    assert calls["enter"] == 2


def test_leaving_the_menu_returns_the_moment_the_dungeon_loads(monkeypatch):
    cur = _screen(monkeypatch, [{"loading"}])
    presses = []
    monkeypatch.setattr(B.gui, "press", lambda key: presses.append(key))
    assert B._leave_gift_menu() is True
    assert cur["sleeps"] == 0 and presses == []


def test_leaving_the_menu_confirms_each_dialog_as_it_shows(monkeypatch):
    cur = _screen(monkeypatch, [{"Confirm"}, set(), {"packconfirm"}, set(), {"PackChoice"}])
    presses = []
    clock = {"t": 0.0}
    monkeypatch.setattr(B.time, "time", lambda: clock.__setitem__("t", clock["t"] + 0.2) or clock["t"])
    monkeypatch.setattr(B.gui, "press", lambda key: presses.append(key))
    assert B._leave_gift_menu() is True
    assert presses == ["enter", "enter"]
    assert cur["sleeps"] == 4


def test_the_starlight_question_is_answered_by_its_own_button(monkeypatch):
    cur = _screen(monkeypatch, [{"starlightConfirm"}, set(), {"loading"}])
    presses = []
    clock = {"t": 0.0}
    monkeypatch.setattr(B.time, "time", lambda: clock.__setitem__("t", clock["t"] + 0.2) or clock["t"])
    monkeypatch.setattr(B.gui, "press", lambda key: presses.append(key))
    assert B._leave_gift_menu() is True
    assert cur["clicks"] == ["starlightConfirm"] and presses == []


def test_leaving_the_menu_gives_up_after_its_timer(monkeypatch):
    cur = _screen(monkeypatch, [set()])
    clock = {"t": 0.0}
    monkeypatch.setattr(B.time, "time", lambda: clock.__setitem__("t", clock["t"] + 0.5) or clock["t"])
    monkeypatch.setattr(B.gui, "press", lambda key: None)
    assert B._leave_gift_menu(timer=2.0) is False
