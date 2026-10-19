# SPDX-License-Identifier: GPL-3.0-or-later
"""The grace screen: a click is verified by the cost strip changing, in the
old 80 px spot or anywhere on the strip, and a click that never takes leaves
a report and the error the start chain retries on."""
import pytest

from wbcore import bot as B
from wbcore.utils import params as p


def _quiet(monkeypatch, changes):
    """`changes` is popped once per verification poll: True means the strip
    changed on that poll."""
    monkeypatch.setattr(B, "screenshot", lambda region=None: __import__("numpy").zeros((2, 2, 3), "uint8"))
    monkeypatch.setattr(B, "_region_changed", lambda before, region: changes.pop(0) if changes else False)
    monkeypatch.setattr(B, "wait_while_condition",
                        lambda cond, interval=0.1, timer=3: not cond())
    monkeypatch.setattr(B.gui, "getActiveWindowTitle", lambda: p.LIMBUS_NAME)
    monkeypatch.setattr(B.time, "sleep", lambda s: None)


def test_a_grace_click_counts_when_either_spot_changes(monkeypatch):
    clicks = []
    monkeypatch.setattr(B, "win_click", lambda x, y, *a, **k: clicks.append((x, y)))
    _quiet(monkeypatch, [False, True])                  # the narrow spot still, the strip moved
    assert B._click_grace(335, 375, "0") is True
    assert clicks == [(335, 375)]


def test_a_grace_click_that_never_takes_reports_and_raises(monkeypatch):
    clicks, dumps = [], []
    monkeypatch.setattr(B, "win_click", lambda x, y, *a, **k: clicks.append((x, y)))
    monkeypatch.setattr(B, "_diag_once", lambda tag, **kw: dumps.append((tag, kw)))
    _quiet(monkeypatch, [])
    with pytest.raises(RuntimeError, match="grace 2 level"):
        B._click_grace(869, 530, "2 level")
    assert clicks == [(869, 530)] * 3
    assert dumps[0][0] == "grace_2_level" and dumps[0][1]["region"] == B._GRACE_COST_STRIP


def test_select_grace_clicks_the_grid_and_the_level_arrows(monkeypatch):
    seen = []
    monkeypatch.setattr(B, "_click_grace", lambda x, y, what: seen.append((x, y, what)) or True)
    monkeypatch.setattr(p, "BUFF", [1, 0, 2, 0, 0, 3, 0, 0, 0, 1])
    B.select_grace()
    assert seen == [(335, 375, "0"),
                    (929, 375, "2"), (869, 530, "2 level"),     # level 2: the left arrow
                    (335, 732, "5"), (395, 887, "5 level"),     # level 3: the right arrow
                    (1523, 732, "9")]
