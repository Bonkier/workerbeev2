# SPDX-License-Identifier: GPL-3.0-or-later
"""The weekly bonus toggles on the reward screen: every charge, one charge
per run, or none, read from the three ON/OFF toggles."""
import types

import pytest

from wbcore import bot as B
from wbcore.utils import params as p


class _Screen:
    """Three toggles with the game's chaining: switching one off also
    switches off the ones after it, switching one on the ones before it.
    `available` charges cap how many can be on."""

    def __init__(self, states, available=3):
        self.states = list(states)
        self.available = available
        self.clicks = []

    def button(self, name, key, click=False, conf=0.9, **_k):
        i = ("bonus", "bonus2", "bonus3").index(key)
        state = self.states[i]
        hit = ((name == "bonus" and state == "on")
               or (name == "bonus_off" and state == "off"))
        if hit and click:
            self.clicks.append(key)
            if state == "on":
                for j in range(i, 3):
                    self.states[j] = "off"
            elif i < self.available:
                for j in range(i + 1):
                    self.states[j] = "on"
        return hit


@pytest.fixture
def screen(monkeypatch):
    def make(states, available=3):
        scr = _Screen(states, available)
        monkeypatch.setattr(B, "now_rgb", types.SimpleNamespace(button=scr.button))
        monkeypatch.setattr(B, "wait_while_condition", lambda cond, *a, **k: not cond())
        monkeypatch.setattr(B, "win_moveTo", lambda *a, **k: None)
        monkeypatch.setattr(B.time, "sleep", lambda s: None)
        return scr
    return make


def test_every_charge_is_switched_back_on(screen, monkeypatch):
    monkeypatch.setattr(p, "BONUS", True)
    monkeypatch.setattr(p, "BONUS_ONE", False)
    scr = screen(["on", "off", "off"])              # last run took one
    B.handle_bonus()
    assert scr.states == ["on", "on", "on"] and scr.clicks == ["bonus2", "bonus3"]
    scr = screen(["on", "off", "off"], available=2)
    B.handle_bonus()
    assert scr.states == ["on", "on", "off"]
    assert scr.clicks == ["bonus2", "bonus3", "bonus3"]   # the third would not take
    scr = screen(["on", "on", "on"])
    B.handle_bonus()
    assert scr.clicks == []


def test_one_charge_per_run(screen, monkeypatch):
    monkeypatch.setattr(p, "BONUS", True)
    monkeypatch.setattr(p, "BONUS_ONE", True)
    scr = screen(["on", "on", "on"])
    B.handle_bonus()
    assert scr.states == ["on", "off", "off"] and scr.clicks == ["bonus2"]
    scr = screen(["on", "off", "off"])              # the game kept last run's choice
    B.handle_bonus()
    assert scr.clicks == []


def test_no_bonus_switches_the_first_off(screen, monkeypatch):
    monkeypatch.setattr(p, "BONUS", False)
    scr = screen(["on", "on", "on"])
    B.handle_bonus()
    assert scr.states == ["off", "off", "off"] and scr.clicks == ["bonus"]


def test_three_off_is_the_week_used_up_only_when_a_charge_will_not_take(screen, monkeypatch, caplog):
    monkeypatch.setattr(p, "BONUS", True)
    monkeypatch.setattr(p, "BONUS_ONE", False)
    scr = screen(["off", "off", "off"], available=0)      # greyed: nothing takes
    with caplog.at_level("INFO"):
        B.handle_bonus()
    assert scr.clicks == ["bonus", "bonus"] and "used up" in caplog.text
    scr = screen(["off", "off", "off"])                   # last run claimed none
    B.handle_bonus()
    assert scr.states == ["on", "on", "on"]
    monkeypatch.setattr(p, "BONUS_ONE", True)
    scr = screen(["off", "off", "off"])
    B.handle_bonus()
    assert scr.states == ["on", "off", "off"]
    monkeypatch.setattr(p, "BONUS", False)
    scr = screen(["off", "off", "off"])
    B.handle_bonus()
    assert scr.clicks == []


def test_the_summary_hides_one_per_run_without_claim_bonus():
    from gui_v2 import run_summary as RS

    def switched_on(behaviour):
        rows = dict(sum((rows for _cap, rows in RS.md_summary({"behaviour": behaviour})), []))
        return rows["Switched on"]
    assert "One weekly bonus per run" in switched_on({"bonus": True, "bonus_one": True})
    assert "One weekly bonus per run" not in switched_on({"bonus": False, "bonus_one": True})


def test_unreadable_toggles_claim_as_they_are(screen, monkeypatch, caplog):
    monkeypatch.setattr(p, "BONUS", False)
    scr = screen(["on", "on", "on"])
    monkeypatch.setattr(B, "now_rgb", types.SimpleNamespace(button=lambda *a, **k: False))
    with caplog.at_level("WARNING"):
        B.handle_bonus()
    assert scr.clicks == [] and "not readable" in caplog.text


def test_the_option_reaches_the_bot_and_the_summary():
    from gui_v2 import run_config as RC, run_summary as RS
    md = {"behaviour": {"bonus": True, "bonus_one": True}}
    settings = RC.build_settings(md)
    assert settings["bonus"] is True and settings["bonus_one"] is True
    assert RC.build_settings({"behaviour": {}})["bonus_one"] is False
    assert RS.BEHAVIOUR_LABELS["bonus_one"] == "One weekly bonus per run"
