# SPDX-License-Identifier: GPL-3.0-or-later
"""Global toggle for descriptive helper labels (settingSubtitle, inlineHint)."""

from .settings import load_section

# Status readouts, titles and Help body are left alone.
_HELP_OBJECT_NAMES = frozenset({"settingSubtitle", "inlineHint"})


def is_enabled() -> bool:
    cfg = load_section("app_settings") or {}
    return bool(cfg.get("show_descriptions", True))


def apply(show: bool | None = None) -> None:
    """Show or hide descriptive labels; show=None reads the saved pref."""
    try:
        from PySide6.QtWidgets import QApplication
    except Exception:
        return
    app = QApplication.instance()
    if app is None:
        return
    if show is None:
        show = is_enabled()
    for widget in app.allWidgets():
        if widget.objectName() in _HELP_OBJECT_NAMES:
            widget.setVisible(bool(show))
