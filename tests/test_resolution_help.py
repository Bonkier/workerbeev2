# SPDX-License-Identifier: GPL-3.0-or-later
"""The wrong-resolution notice: it has to say why the window is the wrong
shape and what to try, for the shapes people actually turn up with."""

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

from gui_v2 import resolution_help as R

_app = QApplication.instance() or QApplication([])

MESSAGE = ("Game window (1920 x 1200) is not 16:9\nIt is recommended to set "
           "the game to either\n1920 x 1080 or 1280 x 720")


def display(index, w, h, primary=False):
    return {"index": index, "width": w, "height": h, "primary": primary}


# --- reading the warning -------------------------------------------------

def test_the_size_is_read_from_the_run_warning():
    assert R.parse_size(MESSAGE) == (1920, 1200)
    assert R.parse_size("Scheduler has no enabled tasks.") is None
    assert R.parse_size("Game window (0 x 0) is not 16:9") is None


@pytest.mark.parametrize("size, shape", [
    ((1920, 1200), "16:10"),
    ((1280, 800), "16:10"),
    ((2560, 1080), "21:9"),
    ((3440, 1440), "21:9"),
    ((1024, 768), "4:3"),
    ((1280, 1024), "5:4"),
    ((1920, 1061), "almost 16:9"),
    ((1920, 1080), "16:9"),
    ((1366, 768), "16:9"),          # the backend accepts this one too
])
def test_the_shape_is_named(size, shape):
    assert R.shape_name(*size) == shape


def test_the_16_9_test_is_the_backends_own():
    for w, h in ((1920, 1080), (1280, 720), (1366, 768), (2560, 1440)):
        assert R.is_16_9(w, h) == (int(w / 16) == int(h / 9)) is True
    assert not R.is_16_9(1920, 1200)


def test_the_part_the_bot_falls_back_to_is_the_centred_16_9():
    assert R.used_area(1920, 1200) == (1920, 1080)
    assert R.used_area(2560, 1080) == (1920, 1080)


# --- the advice ----------------------------------------------------------

def test_fullscreen_on_a_16_10_display_is_told_to_go_windowed():
    report = R.collect(1920, 1200, [display(1, 1920, 1200, True)])
    found = R.findings(report)
    assert report["fills"]["index"] == 1
    assert "display 1" in found["detail"] and "16:10" in found["detail"]
    assert "Windowed" in found["steps"][0]
    assert "1920 x 1080" in found["steps"][1]


def test_a_second_16_9_display_is_offered():
    report = R.collect(1920, 1200, [display(1, 1920, 1200, True),
                                    display(2, 2560, 1440)])
    steps = R.findings(report)["steps"]
    assert any("display 2" in s and "16:9" in s for s in steps)


def test_a_squeezed_window_is_recognised():
    report = R.collect(1920, 1061, [display(1, 1920, 1080, True)])
    found = R.findings(report)
    assert report["shape"] == "almost 16:9" and report["fills"] is None
    assert "19 px too short" in found["detail"]
    assert "1920 x 1080" in found["detail"]
    # A 1920 x 1080 window cannot fit a 1920 x 1080 display.
    assert "1280 x 720" in found["steps"][0]
    assert any("does not fit" in s for s in found["steps"])


def test_an_odd_window_size_is_sent_to_the_games_settings():
    report = R.collect(1600, 1000, [display(1, 2560, 1440, True)])
    found = R.findings(report)
    assert "Settings > Graphics" in found["steps"][0]
    assert "1920 x 1080" in found["steps"][0]


@pytest.mark.parametrize("size, displays", [
    ((1920, 1200), [display(1, 1920, 1200, True)]),
    ((1920, 1061), [display(1, 1920, 1080, True)]),
    ((1600, 1000), [display(1, 2560, 1440, True)]),
    ((1024, 768), []),
])
def test_every_case_ends_with_what_to_do_next(size, displays):
    report = R.collect(size[0], size[1], displays)
    found = R.findings(report)
    assert len(found["steps"]) >= 3
    assert any("start it again" in s for s in found["steps"])
    text = R.format_report(report)
    assert "%d x %d" % size in text and "1. " in text
    assert chr(0x2014) not in text and chr(0x2013) not in text
    rows = R.checks(report)
    assert rows[0][0] == "Game window" and rows[0][2] is False


# --- the notice ----------------------------------------------------------

def test_the_notice_never_blocks_or_takes_focus():
    dlg = R.show_resolution_help(None, MESSAGE,
                                 [display(1, 1920, 1200, True)])
    try:
        assert isinstance(dlg, R.ResolutionHelpDialog)
        assert not dlg.isModal()
        assert dlg.testAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        assert dlg.windowFlags() & Qt.WindowType.WindowDoesNotAcceptFocus
    finally:
        dlg.close()


def test_a_new_size_replaces_the_notice_already_up():
    first = R.show_resolution_help(None, MESSAGE, [])
    second = R.show_resolution_help(
        None, "Game window (2560 x 1080) is not 16:9", [])
    try:
        assert not first.isVisible()
        assert second.isVisible()
    finally:
        second.close()


def test_copy_puts_the_report_on_the_clipboard():
    dlg = R.show_resolution_help(None, MESSAGE,
                                 [display(1, 1920, 1200, True)])
    try:
        dlg._on_copy()
        text = QApplication.clipboard().text()
        assert "WorkerBee resolution report" in text
        assert "1920 x 1200 (16:10)" in text
    finally:
        dlg.close()


def test_text_without_a_size_falls_back_to_the_plain_advisory(monkeypatch):
    shown = []
    monkeypatch.setattr(R, "show_advisory",
                        lambda parent, text, **k: shown.append(text))
    R.show_resolution_help(None, "Game window (unknown) is not 16:9")
    assert shown == ["Game window (unknown) is not 16:9"]


# --- found by review ---------------------------------------------------

def test_a_display_a_pixel_out_from_scaling_still_counts_as_filled():
    # 2560 x 1600 at 150% comes back from Qt as 2561 x 1601.
    report = R.collect(2560, 1600, [display(1, 2561, 1601, True)])
    assert report["fills"] is not None
    found = R.findings(report)
    assert "Windowed" in found["steps"][0]
    assert ("Display 1", "2560 x 1600 (16:10), filled by the game",
            False) in R.checks(report)


def test_a_maximised_window_is_not_mistaken_for_fullscreen():
    report = R.collect(1920, 1017, [display(1, 1920, 1080, True)])
    assert report["fills"] is None


def test_fullscreen_is_only_suggested_on_a_16_9_display():
    wide = R.findings(R.collect(1920, 1061, [display(1, 2560, 1080, True)]))
    assert not any("Fullscreen" in s for s in wide["steps"])
    plain = R.findings(R.collect(1920, 1061, [display(1, 1920, 1080, True)]))
    assert any("or Fullscreen" in s for s in plain["steps"])


def test_the_steps_use_the_games_own_labels():
    found = R.findings(R.collect(1920, 1200, [display(1, 1920, 1200, True)]))
    assert "under Resolution, select Windowed" in found["steps"][0]
    assert "screen mode" not in " ".join(found["steps"]).lower()


def test_each_run_measures_the_window_afresh():
    import inspect
    from wbcore import bot
    for fn in (bot.execute_me, bot.convert_enkephalin_only):
        src = inspect.getsource(fn)
        reset = src.index("gui._advised_window_size = None")
        assert reset < src.index("gui.set_window()")


# --- both sizes are recommended wherever the display can show both ------

@pytest.mark.parametrize("host, expected", [
    (display(1, 2560, 1440, True), "1920 x 1080 or 1280 x 720"),
    (display(1, 1920, 1200, True), "1920 x 1080 or 1280 x 720"),
    (display(1, 1920, 1080, True),
     "1920 x 1080 (in Fullscreen) or 1280 x 720 (Windowed)"),
    (display(1, 2560, 1080, True), "1280 x 720"),   # fullscreen is 21:9
    (display(1, 1366, 768, True), "1280 x 720"),    # too small for more
    (None, "1920 x 1080 or 1280 x 720"),
])
def test_which_sizes_are_recommended(host, expected):
    assert R._recommend(host) == expected


def test_a_full_hd_display_is_offered_1920_x_1080_as_well():
    for size in ((1600, 1000), (1920, 1061)):
        found = R.findings(R.collect(size[0], size[1],
                                     [display(1, 1920, 1080, True)]))
        assert "1920 x 1080 (in Fullscreen) or 1280 x 720 (Windowed)" in (
            found["steps"][0])


def test_sizes_are_kept_on_one_line_on_screen_but_not_in_the_report():
    nbsp = chr(0xA0)
    assert R._no_break("set it to 1920 x 1080 now") == (
        "set it to 1920%sx%s1080 now" % (nbsp, nbsp))
    report = R.collect(1920, 1200, [display(1, 1920, 1200, True)])
    assert nbsp not in R.format_report(report)
