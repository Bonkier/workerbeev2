# SPDX-License-Identifier: GPL-3.0-or-later
"""The sidebar opens and closes to a rail, remembers the choice, and the
title bar's search box follows its width."""
import pytest
from PySide6.QtWidgets import QApplication, QMainWindow, QWidget

from gui_v2.theme import Sizing


def _quiet(mp):
    from tests.test_hollow import _quiet as quiet
    quiet(mp.setattr)


@pytest.fixture(scope="module")
def ui():
    from tests.conftest import destroy
    mp = pytest.MonkeyPatch()
    _quiet(mp)
    QApplication.instance() or QApplication([])
    from gui_v2.main_ui import MainUI
    host = QWidget()
    host.resize(1280, 860)
    main = MainUI(host)
    main.setGeometry(0, 0, 1280, 860)
    yield main
    destroy(main, host)
    mp.undo()


def test_the_sidebar_closes_to_a_rail_and_opens_again(ui, monkeypatch):
    from gui_v2 import main_ui as M
    saved, widths = [], []
    monkeypatch.setattr(M, "save_settings", lambda u: saved.append(u))
    ui.sidebar_width_changed.connect(widths.append)
    ui.set_sidebar_open(False, animate=False)
    assert ui._sidebar.width() == M._RAIL_WIDTH and widths[-1] == M._RAIL_WIDTH
    assert not ui.is_sidebar_open()
    assert all(b._rail for b in ui._items.values())
    md = ui._items["mirror_dungeon"]
    assert md.text() and md.toolTip() == md.text()      # the label stays, as the tooltip
    assert ui._version_lbl.isHidden()
    assert saved[-1] == {"sidebar_collapsed": True}
    ui.set_sidebar_open(True, animate=False)
    assert ui._sidebar.width() == Sizing.SIDEBAR_WIDTH and ui.is_sidebar_open()
    assert not any(b._rail for b in ui._items.values()) and md.toolTip() == ""
    assert not ui._version_lbl.isHidden()
    assert saved[-1] == {"sidebar_collapsed": False}
    ui.toggle_sidebar()                                  # the animated path
    assert not ui.is_sidebar_open() and saved[-1] == {"sidebar_collapsed": True}
    ui.set_sidebar_open(True, animate=False, persist=False)
    assert len(saved) == 3


def test_a_saved_closed_sidebar_starts_closed(monkeypatch):
    from gui_v2 import main_ui as M
    from tests.conftest import destroy
    mp = pytest.MonkeyPatch()
    _quiet(mp)
    monkeypatch.setattr(M, "load_settings", lambda: {"sidebar_collapsed": True})
    monkeypatch.setattr(M, "save_settings", lambda u: None)
    QApplication.instance() or QApplication([])
    host = QWidget()
    main = M.MainUI(host)
    try:
        assert main._sidebar.width() == M._RAIL_WIDTH and not main.is_sidebar_open()
    finally:
        destroy(main, host)
        mp.undo()


def test_every_nav_item_has_its_own_two_letter_tag(ui):
    tags = [b.tag for b in ui._items.values()]
    assert all(len(t) == 2 and t.isupper() for t in tags)
    assert len(set(tags)) == len(tags)


def test_the_title_bar_follows_the_sidebar_width():
    QApplication.instance() or QApplication([])
    from gui_v2.main_window import _TitleBar
    win = QMainWindow()
    bar = _TitleBar(win)
    try:
        assert bar._side_gap.sizeHint().width() == Sizing.SIDEBAR_WIDTH - Sizing.SPACE_MD
        bar.set_sidebar_width(56)
        assert bar._side_gap.sizeHint().width() == 56 - Sizing.SPACE_MD
        bar.set_sidebar_width(Sizing.SIDEBAR_WIDTH)
        assert bar._side_gap.sizeHint().width() == Sizing.SIDEBAR_WIDTH - Sizing.SPACE_MD
    finally:
        bar.deleteLater()
        win.deleteLater()
