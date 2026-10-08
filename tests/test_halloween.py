# SPDX-License-Identifier: GPL-3.0-or-later
"""The October season: on by date, titles only, darker and red, and gone
again in November. Plus Thrill, which is locked as W.I.P all year."""

import datetime

import pytest
from PySide6.QtWidgets import QApplication

from gui_v2 import seasonal

_app = QApplication.instance() or QApplication([])


@pytest.fixture
def evil():
    """Halloween on, with the palette restored afterwards so no other test
    inherits red."""
    from gui_v2 import themes
    seasonal.force(seasonal.HALLOWEEN)
    yield
    seasonal.force("off")
    themes.apply_saved_theme()


# --- when it is on -----------------------------------------------------

class _Date(datetime.date):
    _today = datetime.date(2026, 10, 1)

    @classmethod
    def today(cls):
        return cls._today


@pytest.mark.parametrize("day, expected", [
    (datetime.date(2026, 9, 30), ""),
    (datetime.date(2026, 10, 1), seasonal.HALLOWEEN),
    (datetime.date(2026, 10, 31), seasonal.HALLOWEEN),
    (datetime.date(2026, 11, 1), ""),
])
def test_the_season_follows_the_calendar(monkeypatch, day, expected):
    monkeypatch.delenv("WORKERBEE_SEASON", raising=False)
    _Date._today = day
    monkeypatch.setattr(seasonal.datetime, "date", _Date)
    seasonal.force(None)
    assert seasonal.active() == expected


def test_the_environment_can_force_it_either_way(monkeypatch):
    _Date._today = datetime.date(2026, 6, 1)
    monkeypatch.setattr(seasonal.datetime, "date", _Date)
    seasonal.force(None)
    monkeypatch.setenv("WORKERBEE_SEASON", "halloween")
    assert seasonal.is_halloween()
    _Date._today = datetime.date(2026, 10, 15)
    monkeypatch.setenv("WORKERBEE_SEASON", "off")
    assert not seasonal.is_halloween()


# --- names -------------------------------------------------------------

def test_titles_turn_evil(evil):
    assert seasonal.title("Mirror Dungeon") == "EVIL Dungeon"
    assert seasonal.title("Luxcavation") == "EVILuxcavation"
    assert seasonal.title("Stats") == "EVIL Statistics"
    assert seasonal.title("STATISTICS") == "EVIL STATISTICS"
    assert seasonal.title("Start Mirror Dungeon") == "Start EVIL Dungeon"
    assert seasonal.title("EXP Luxcavation") == "EXP EVILuxcavation"
    assert seasonal.brand() == ("Evil", "Bee")


def test_settings_and_gift_names_are_left_alone(evil):
    for name in ("Settings", "Help", "RUN COUNT", "Skip EGO fusion",
                 "Pack search", "Spiderweb Entangled in Red",
                 "Clear Mirror, Calm Water", "SKILL REPLACEMENT"):
        assert seasonal.title(name) == name


def test_nothing_changes_out_of_season():
    assert seasonal.title("Mirror Dungeon") == "Mirror Dungeon"
    assert seasonal.brand() == ("Worker", "Bee")


def test_spooky_tips_fit_the_subtitle_slot():
    assert len(seasonal.SPOOKY_TIPS) >= 12
    assert all(len(t) <= 34 for t in seasonal.SPOOKY_TIPS)
    assert not any(chr(0x2014) in t or chr(0x2013) in t
                   for t in seasonal.SPOOKY_TIPS)


# --- look --------------------------------------------------------------

def test_the_palette_goes_darker_and_red(evil):
    from gui_v2 import themes
    from gui_v2.theme import Colors
    themes.apply_saved_theme()
    assert Colors.ACCENT == seasonal.RED
    assert Colors.BG_BASE == seasonal.BACKGROUND
    # Darker than the stock background.
    assert sum(themes._to_rgb(Colors.BG_BASE)) < sum(
        themes._to_rgb(themes.DEFAULT_BG))


def test_the_palette_comes_back_after_the_season():
    from gui_v2 import themes
    from gui_v2.theme import Colors
    seasonal.force(seasonal.HALLOWEEN)
    themes.apply_saved_theme()
    seasonal.force("off")
    themes.apply_saved_theme()
    assert Colors.ACCENT != seasonal.RED
    assert Colors.BG_BASE != seasonal.BACKGROUND


def test_the_wordmark_reads_evilbee_in_red_and_white(evil):
    from PySide6.QtGui import QColor, QImage
    from gui_v2.voxel import PixelWordmark, _GLYPHS
    assert all(ch in _GLYPHS for ch in "EvilBee")
    wm = PixelWordmark(4)
    assert wm._text == "EvilBee" and wm._split == 4
    img = QImage(wm.size(), QImage.Format.Format_ARGB32)
    img.fill(QColor(0, 0, 0))
    wm.render(img)
    colours = {img.pixelColor(x, y).name()
               for x in range(img.width()) for y in range(img.height())}
    assert QColor(seasonal.RED).name() in colours
    assert QColor(seasonal.BONE).name() in colours


def test_the_bee_gets_bat_wings_in_red_and_black(evil):
    from PySide6.QtGui import QPixmap
    from gui_v2 import voxel
    logo = voxel.VoxelLogo(72)
    pal = logo._palette()
    assert pal[voxel._BODY].name() == seasonal.RED
    # A wing on each side, reaching further out than the bee's own.
    xs = [x for x, _y, _z in voxel._BAT_WING_VOXELS]
    assert min(xs) == -max(xs) and max(xs) > max(
        x for x, _y, _z in voxel._WING_VOXELS)
    pm = QPixmap(72, 72)
    logo.render(pm)                     # paints without error


def test_pages_and_nav_are_retitled_but_settings_is_not(evil, monkeypatch):
    import gui_v2.settings as st
    monkeypatch.setattr(st, "save_section", lambda *a, **k: None)
    monkeypatch.setattr(st, "save_settings", lambda *a, **k: None)
    from gui_v2.main_ui import MainUI, _SidebarItem
    ui = MainUI()
    labels = [it.text() for it in ui.findChildren(_SidebarItem)]
    assert "EVIL Dungeon" in labels and "EVILuxcavation" in labels
    assert "EVIL Statistics" in labels
    assert "Settings" in labels and "Mirror Dungeon" not in labels


def test_the_loading_screen_uses_spooky_tips_and_paints(evil):
    from PySide6.QtGui import QPixmap
    from gui_v2.splash import SplashWidget, _LoadingPane
    sp = SplashWidget()
    sp.resize(400, 160)
    pane = sp.findChild(_LoadingPane)
    assert set(pane._tips) == set(seasonal.SPOOKY_TIPS)
    pm = QPixmap(sp.size())
    sp.render(pm)                       # the graveyard paints without error


def test_the_overlay_bee_and_wordmark_paint_in_season(evil):
    from PySide6.QtGui import QPixmap
    from gui_v2.overlay import RunOverlay
    ov = RunOverlay(preview=True)
    ov.load_demo()
    ov.resize(720, 400)
    pm = QPixmap(720, 400)
    ov.render(pm)
    assert len(ov._BAT_ROWS[0]) == len(ov._BEE_ROWS[0])


# --- Thrill is locked, in and out of season ----------------------------

@pytest.fixture
def md_page(monkeypatch):
    import gui_v2.settings as st
    import gui_v2.mirror_dungeon_page as M
    monkeypatch.setattr(st, "save_section", lambda *a, **k: None)
    monkeypatch.setattr(M, "save_section", lambda *a, **k: None)
    page = M.MirrorDungeonPage()
    page._loading = True
    return page


def test_clicking_thrill_selects_nothing_and_says_wip(md_page, monkeypatch):
    from gui_v2 import dialogs
    shown = []
    monkeypatch.setattr(dialogs, "show_notice",
                        lambda parent, text, title="": shown.append(title))
    seg = md_page._custom_strategy
    before = seg.selected()
    assert before != "Thrill"
    seg._buttons["Thrill"].click()
    assert seg.selected() == before
    assert shown == ["W.I.P"]


def test_thrill_cannot_be_selected_by_a_saved_config(md_page):
    seg = md_page._custom_strategy
    seg.set_selected("Thrill")
    assert seg.selected() != "Thrill"
    md_page._custom_run.setChecked(True)
    assert md_page.state()["custom_strategy"] != "Thrill"


def test_a_locked_segment_never_holds_the_selection():
    from gui_v2.widgets import Segmented
    seg = Segmented(["A", "B", "C"], default="B")
    hits = []
    seg.locked_clicked.connect(hits.append)
    seg.set_locked("B")                 # locking the current one moves off it
    assert seg.selected() == "A"
    seg._buttons["B"].click()
    assert seg.selected() == "A" and hits == ["B"]
    seg._buttons["C"].click()
    assert seg.selected() == "C"
