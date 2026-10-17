# SPDX-License-Identifier: GPL-3.0-or-later
"""The run start since the Mirror of Sisyphe update: the dungeon connects
before the team screen, the resume table lands on the matching step, and a
Start click that is not followed by the entry dialog is re-located instead
of re-clicked."""
import types

import pytest

from wbcore import bot as B
from wbcore.utils import params as p
from wbcore.utils import utils as U


def _start_from(monkeypatch, key):
    """dungeon_start with `key` the one marker visible on the first scan;
    returns the action slice handed to chain_actions."""
    seen = []

    def button(name, *a, **k):
        return name == key and not seen
    monkeypatch.setattr(B, "now", types.SimpleNamespace(button=button))
    monkeypatch.setattr(B, "now_click", types.SimpleNamespace(button=lambda *a, **k: False))
    monkeypatch.setattr(B, "chain_actions", lambda _preset, actions: seen.append(list(actions)))
    assert B.dungeon_start() is True
    assert len(seen) == 1
    return seen[0]


def test_the_resume_table_lands_on_the_matching_step(monkeypatch):
    start = _start_from(monkeypatch, "Start")
    assert isinstance(start[2], U.Action) and start[2].key == "Start"
    assert start[2].retries == 0
    entry = _start_from(monkeypatch, "enterInvert")
    assert isinstance(entry[0], U.Action) and entry[0].ver == "connecting"
    assert entry[3] is B.select_team                  # connecting gone, team screen up
    assert _start_from(monkeypatch, "ConfirmTeam")[0] is B.select_team
    assert _start_from(monkeypatch, "enterBonus")[0] is B.select_grace
    confirm = _start_from(monkeypatch, "Confirm.0")[0]
    assert isinstance(confirm, U.Action) and confirm.key == "Confirm.0"
    assert _start_from(monkeypatch, "refuse")[1] is B.select_starting_gift
    assert len(_start_from(monkeypatch, "Confirm")) == 2  # leave the gift menu, wait out loading


def test_resume_waits_for_the_start_button_to_go(monkeypatch):
    waits = []
    monkeypatch.setattr(B, "now_click", types.SimpleNamespace(
        button=lambda name, *a, **k: name == "resume"))
    monkeypatch.setattr(B, "now", types.SimpleNamespace(button=lambda *a, **k: False))
    monkeypatch.setattr(B, "wait_while_condition",
                        lambda cond, *a, **k: waits.append(k.get("timer")))
    assert B.dungeon_start() is True
    assert waits == [5]


def _preset(monkeypatch):
    checks = []

    class Cl:
        @staticmethod
        def check(path, **params):
            checks.append(params.get("click"))
            return True
    monkeypatch.setattr(U.gui, "getActiveWindowTitle", lambda: p.LIMBUS_NAME)
    monkeypatch.setattr(U, "wait_while_condition", lambda *a, **k: False)   # never verifies
    return U.LocatePreset(cl=Cl, click=True), checks


def test_a_start_click_without_its_dialog_is_not_reclicked(monkeypatch):
    preset, checks = _preset(monkeypatch)
    with pytest.raises(RuntimeError, match="after 0 retries"):
        preset.button("Start", ver="enterInvert", retries=0)
    assert checks == [True]                            # the one click, no retry
    del checks[:]
    with pytest.raises(RuntimeError, match="after 0 retries"):
        U.Action("Start", ver="enterInvert", retries=0).execute(preset)
    assert checks == [True]


def test_the_default_still_reclicks_three_times(monkeypatch):
    preset, checks = _preset(monkeypatch)
    with pytest.raises(RuntimeError, match="after 3 retries"):
        preset.button("Start", ver="enterInvert")
    assert checks == [True] * 4
