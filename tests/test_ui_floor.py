# SPDX-License-Identifier: GPL-3.0-or-later
"""The floor a tool's screens stand on: captions that can be read, marks
that are drawn and not typed, and a landing page that does not repeat the
record as a row of big numbers."""
import time

import pytest
from PySide6.QtWidgets import QApplication

from tests.conftest import destroy
from gui_v2 import dashboard_page, stats, themes
from gui_v2.stats_page import _HistoryRow, _Lamp
from gui_v2.style import BAND_TINT, CARD_TINT
from gui_v2.theme import Colors
from gui_v2.widgets import StatTiles


def _over(base, tint):
    """`base` under a white wash of the tint's alpha, as the voxel sheet
    lays its panels and bands."""
    r, g, b = themes._to_rgb(base)
    a = tint[3] / 255.0
    return themes._to_hex(*(v + (255 - v) * a for v in (r, g, b)))


def _caption_grounds():
    panel = _over("#0e1013", CARD_TINT)                 # the voxel page, default
    return {
        "voxel panel": panel,
        "voxel band": _over(panel, BAND_TINT),
        "legacy card": themes._BG_DEFAULTS["BG_RAISED"],
        "legacy overlay": themes._BG_DEFAULTS["BG_OVERLAY"],
    }


@pytest.mark.parametrize("ground", sorted(_caption_grounds()))
def test_a_caption_reads_on_every_surface_it_sits_on(ground):
    tone = themes._TEXT_DEFAULTS["TEXT_TERTIARY"]
    assert themes.contrast(tone, _caption_grounds()[ground]) >= themes.CAPTION_CONTRAST


def test_the_steps_of_text_stay_apart():
    tones = [themes._TEXT_DEFAULTS[k] for k in ("TEXT_PRIMARY", "TEXT_SECONDARY",
                                                 "TEXT_TERTIARY", "TEXT_DISABLED")]
    ground = themes._BG_DEFAULTS["BG_BASE"]
    ratios = [themes.contrast(t, ground) for t in tones]
    assert ratios == sorted(ratios, reverse=True)
    assert all(a / b >= 1.2 for a, b in zip(ratios, ratios[1:]))


@pytest.mark.parametrize("bg, text", [("#1d2530", "#c9d1d9"), ("#2a1f2e", "#d8c8e0"),
                                      ("#0d0d0e", "#9aa0a6"), ("#f2efe6", "#2a2a28")])
def test_a_custom_text_colour_keeps_its_captions_readable(monkeypatch, bg, text):
    for key in themes._BG_KEYS + themes._TEXT_KEYS:
        monkeypatch.setattr(Colors, key, getattr(Colors, key))
    themes._apply_background(bg)
    themes._apply_text(text)
    assert themes.contrast(Colors.TEXT_TERTIARY, Colors.BG_OVERLAY) >= themes.CAPTION_CONTRAST
    # Still a dimmer step than the main text wherever the palette allows it.
    assert (themes.contrast(Colors.TEXT_TERTIARY, Colors.BG_OVERLAY)
            <= themes.contrast(Colors.TEXT_PRIMARY, Colors.BG_OVERLAY))


def _run(i, completed=True):
    return {"ts": time.time() - 3600 * (i + 1), "completed": completed,
            "duration": 1000 + i, "team": "RUPTURE", "run": "Hollow",
            "floors": [{"floor": 1, "pack": "FlatbrokeGamblers", "duration": 200}],
            "gifts": []}


@pytest.fixture
def dashboard(monkeypatch):
    app = QApplication.instance() or QApplication([])
    runs = [_run(i, completed=i != 2) for i in range(12)]       # newest first
    runs.reverse()                                               # as the file keeps them
    monkeypatch.setattr(stats, "load_runs", lambda: list(runs))
    monkeypatch.setattr(stats, "aggregate", lambda: {
        "total": 12, "completed": 11, "mirrors_cleared": 11, "success_rate": 91.7,
        "avg_duration": 1207.0, "total_time": 7200.0})
    monkeypatch.setattr(dashboard_page.app_settings, "load_section", lambda name: {})
    page = dashboard_page.DashboardPage()
    yield page
    destroy(page)
    app.processEvents()


def test_the_landing_page_states_the_record_once(dashboard):
    assert dashboard.findChildren(StatTiles) == []
    line = dashboard._hero_sub.text()
    assert "11 completed" in line and "92% success" in line
    assert "20m 7s a run" in line and "grinding" in line and "last run" in line


def test_the_room_goes_to_the_recent_runs(dashboard):
    rows = dashboard.findChildren(_HistoryRow)
    assert len(rows) == dashboard_page._MAX_ACTIVITY_ROWS == 10


def test_a_runs_result_and_its_caret_are_drawn(dashboard):
    rows = dashboard.findChildren(_HistoryRow)
    lamps = [row.lamp for row in rows]
    assert all(isinstance(lamp, _Lamp) for lamp in lamps)
    assert [lamp.ok for lamp in lamps].count(False) == 1       # the one failed run
    row = rows[0]
    assert row._toggle.text() == "details"
    closed = row._toggle.icon().pixmap(9, 9).toImage()
    assert not closed.isNull()
    row._toggle.setChecked(True)
    assert row._details.isVisibleTo(row)
    assert row._toggle.icon().pixmap(9, 9).toImage() != closed
