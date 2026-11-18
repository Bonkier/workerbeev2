# SPDX-License-Identifier: GPL-3.0-or-later
"""Windows on a light colour scheme. The stylesheet had no rule for
tooltips or menus, so Qt drew them from the system palette: white, under
the app's own light text. A report showed a preset card's tooltip as a
white box."""
import re

from PySide6.QtCore import Qt

from gui_v2 import themes
from gui_v2.style import build_global_qss
from gui_v2.theme import Colors


def _rule(qss, selector):
    match = re.search(r"\n\s*%s\s*\{([^}]*)\}" % re.escape(selector), qss)
    assert match, "no %s rule" % selector
    return match.group(1)


def test_tooltips_and_menus_take_the_themes_colours():
    qss = build_global_qss()
    for selector in ("QToolTip", "QMenu"):
        rule = _rule(qss, selector)
        assert "background-color: %s" % Colors.BG_OVERLAY in rule
        assert "color: %s" % Colors.TEXT_PRIMARY in rule
    assert Colors.BG_HOVER in _rule(qss, "QMenu::item:selected")


class _App:
    """An application that only records the colour scheme it is given (the
    offscreen platform the tests run on has none to read back)."""

    def __init__(self):
        self.asked = []

    def styleHints(self):
        return self

    def setColorScheme(self, scheme):
        self.asked.append(scheme)


def test_qt_is_told_the_themes_scheme_whatever_windows_says():
    app = _App()
    themes.apply_colour_scheme(app)
    assert app.asked == [Qt.ColorScheme.Dark]


def test_a_light_theme_is_called_light(monkeypatch):
    monkeypatch.setattr(Colors, "BG_BASE", "#f4f4f4")
    app = _App()
    themes.apply_colour_scheme(app)
    assert app.asked == [Qt.ColorScheme.Light]
