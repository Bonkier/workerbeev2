# SPDX-License-Identifier: GPL-3.0-or-later
"""UI skins. The v2.4 "voxel" look and the original v2 look, switchable at
runtime from Settings ("Legacy v2 UI").

A skin only mutates design tokens (Sizing/Fonts and a couple of Colors);
style.build_global_qss reads those tokens when it builds the sheet, so one
switch restyles every page at once. Colour choice stays with themes.py - the
skin decides shape and typography, the theme decides hue."""

from .settings import load_settings, save_settings
from .theme import Colors, Fonts, Sizing

VOXEL = "voxel"
LEGACY = "legacy"

# The v2 look, captured at import so switching back is exact rather than a
# hand-copied approximation.
_SIZING_KEYS = ("RADIUS_SM", "RADIUS_MD", "RADIUS_LG", "RADIUS_PILL",
                "SPACE_XXS", "SPACE_XS", "SPACE_SM", "SPACE_MD", "SPACE_LG",
                "SPACE_XL", "SPACE_XXL", "BUTTON_HEIGHT", "INPUT_HEIGHT")
_FONT_KEYS = ("FAMILY", "FAMILY_MONO", "SIZE_XS", "SIZE_SM", "SIZE_BASE",
              "SIZE_MD", "SIZE_LG", "SIZE_XL", "SIZE_TITLE", "SIZE_DISPLAY")

_LEGACY = {
    "sizing": {k: getattr(Sizing, k) for k in _SIZING_KEYS},
    "fonts": {k: getattr(Fonts, k) for k in _FONT_KEYS},
}

# Voxel: square everything, and tighten the grid. The reference look is dense
# pixel-art UI - lots of information on a quiet, dark surface - so the spacing
# scale drops roughly a third and controls lose their generous padding.
_VOXEL_SIZING = {
    "RADIUS_SM": 0, "RADIUS_MD": 0, "RADIUS_LG": 0, "RADIUS_PILL": 0,
    "SPACE_XXS": 2, "SPACE_XS": 3, "SPACE_SM": 6, "SPACE_MD": 8,
    "SPACE_LG": 11, "SPACE_XL": 15, "SPACE_XXL": 20,
    "BUTTON_HEIGHT": 28, "INPUT_HEIGHT": 28,
}
# Body text stays a readable UI face - a true pixel font at 12pt is unreadable
# on a dense settings page. The pixel styling lives in the wordmark, the logo
# and the mono/display faces, which is where it is legible. Sizes step down
# one notch for density.
_VOXEL_FONTS = {
    "FAMILY": "Segoe UI Variable, Segoe UI, Inter, system-ui, sans-serif",
    "FAMILY_MONO": "Cascadia Mono, Consolas, monospace",
    "SIZE_XS": 9, "SIZE_SM": 10, "SIZE_BASE": 11, "SIZE_MD": 11,
    "SIZE_LG": 14, "SIZE_XL": 17, "SIZE_TITLE": 20, "SIZE_DISPLAY": 24,
}


def current_skin() -> str:
    """Persisted skin id; voxel is the v2.4 default."""
    s = load_settings().get("ui") or {}
    skin = s.get("skin", VOXEL)
    return LEGACY if skin == LEGACY else VOXEL


def is_voxel() -> bool:
    """Skin the design tokens are currently built for. Cached, because every
    custom-painted widget asks this on every repaint - reading settings off
    disk there would cost a file read per frame."""
    global _active
    if _active is None:
        _active = current_skin()
    return _active == VOXEL


_active = None


def apply_saved_skin():
    """Mutate the design tokens for the persisted skin. Call BEFORE
    build_global_qss (and before themes.apply_saved_theme, which layers the
    colour palette on top)."""
    _apply(current_skin())


def _apply(skin: str):
    global _active
    _active = skin
    if skin == VOXEL:
        for k, v in _VOXEL_SIZING.items():
            setattr(Sizing, k, v)
        for k, v in _VOXEL_FONTS.items():
            setattr(Fonts, k, v)
    else:
        for k, v in _LEGACY["sizing"].items():
            setattr(Sizing, k, v)
        for k, v in _LEGACY["fonts"].items():
            setattr(Fonts, k, v)


def set_skin(skin: str):
    """Persist and apply a skin, restyling the running app in place."""
    skin = LEGACY if skin == LEGACY else VOXEL
    ui = dict(load_settings().get("ui") or {})
    ui["skin"] = skin
    save_settings({"ui": ui})
    _apply(skin)
    _rebrand_running_app()
    try:
        from .themes import _restyle_running_app
        _restyle_running_app()
    except Exception:
        pass


def _rebrand_running_app():
    """Swap the sidebar brand between the voxel mark and the v2 icon+labels
    without a restart. MainUI owns the widgets; ask it to rebuild."""
    try:
        from PySide6.QtWidgets import QApplication
    except Exception:
        return
    app = QApplication.instance()
    if app is None:
        return
    for top in app.topLevelWidgets():
        for w in [top] + top.findChildren(object):
            rebrand = getattr(w, "rebuild_brand", None)
            if callable(rebrand):
                try:
                    rebrand()
                except Exception:
                    pass


__all__ = ["VOXEL", "LEGACY", "current_skin", "is_voxel",
           "apply_saved_skin", "set_skin"]
