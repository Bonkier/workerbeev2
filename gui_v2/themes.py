# SPDX-License-Identifier: GPL-3.0-or-later
"""Runtime theming. Apply: mutate theme.Colors, rebuild QSS, repaint."""

from .settings import load_settings, save_settings
from .theme import Colors

# Built-in accent presets. Order is the dropdown order.
PRESETS = {
    "WorkerBee Yellow": "#f4c430",
    "Ocean Blue":       "#4aa3ff",
    "Mint Green":       "#3ed598",
    "Crimson":          "#f55e5e",
    "Royal Violet":     "#a371f7",
    "Hot Pink":         "#ff6ac1",
    "Tangerine":        "#ff8a3d",
    "Teal":             "#2dd4bf",
    "Lime":             "#a3e635",
    "Ice":              "#7dd3fc",
}

# Factory default, restored by "Reset to defaults".
DEFAULT_ACCENT = PRESETS["WorkerBee Yellow"]
DEFAULT_BG = "#0d0d0e"
DEFAULT_TEXT = "#f5f5f6"


def _clamp(v: int) -> int:
    return max(0, min(255, int(v)))


def _to_rgb(hex_color: str):
    h = hex_color.lstrip("#")
    if len(h) == 3:
        h = "".join(ch * 2 for ch in h)
    try:
        return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    except (ValueError, IndexError):
        return 244, 196, 48  # brand yellow fallback


def _to_hex(r: int, g: int, b: int) -> str:
    return f"#{_clamp(r):02x}{_clamp(g):02x}{_clamp(b):02x}"


def _scale(hex_color: str, factor: float) -> str:
    """Lighten (>1) or darken (<1) a colour."""
    r, g, b = _to_rgb(hex_color)
    return _to_hex(r * factor, g * factor, b * factor)


def _mix(hex_color: str, other: str, t: float) -> str:
    """Blend toward `other` by t in [0, 1]."""
    r1, g1, b1 = _to_rgb(hex_color)
    r2, g2, b2 = _to_rgb(other)
    return _to_hex(r1 + (r2 - r1) * t, g1 + (g2 - g1) * t, b1 + (b2 - b1) * t)


def _apply_accent(accent: str):
    """Derive the accent family (hover/pressed/muted) from a base accent."""
    Colors.ACCENT = accent
    Colors.ACCENT_HOVER = _scale(accent, 1.18)
    Colors.ACCENT_PRESSED = _scale(accent, 0.82)
    Colors.ACCENT_MUTED = _scale(accent, 0.42)    # dim, selection bg


# Snapshot of the hand-tuned background palette so a non-custom theme restores
# the original look (not a computed approximation).
_BG_KEYS = (
    "BG_BASE", "BG_RAISED", "BG_OVERLAY", "BG_HOVER", "BG_PRESSED",
    "BORDER_SUBTLE", "BORDER_STRONG",
    "BG_WINDOW_TOP", "BG_WINDOW_MID", "BG_WINDOW_BOT",
)
_BG_DEFAULTS = {k: getattr(Colors, k) for k in _BG_KEYS}


def _restore_default_background():
    for k, v in _BG_DEFAULTS.items():
        setattr(Colors, k, v)


# Snapshot of the hand-tuned text palette, same restore reason.
_TEXT_KEYS = ("TEXT_PRIMARY", "TEXT_SECONDARY", "TEXT_TERTIARY",
              "TEXT_DISABLED")
_TEXT_DEFAULTS = {k: getattr(Colors, k) for k in _TEXT_KEYS}


def _restore_default_text():
    for k, v in _TEXT_DEFAULTS.items():
        setattr(Colors, k, v)


def _apply_text(text: str):
    """Derive the text palette; dim tiers mix toward the background."""
    Colors.TEXT_PRIMARY = text
    Colors.TEXT_SECONDARY = _mix(text, Colors.BG_BASE, 0.38)
    Colors.TEXT_TERTIARY = _mix(text, Colors.BG_BASE, 0.58)
    Colors.TEXT_DISABLED = _mix(text, Colors.BG_BASE, 0.74)


def _apply_background(bg: str):
    """Derive window/surface tones from one base. Lighter surfaces mix toward
    white so cards stay readable on any base."""
    Colors.BG_BASE = bg
    Colors.BG_RAISED = _mix(bg, "#ffffff", 0.06)
    Colors.BG_OVERLAY = _mix(bg, "#ffffff", 0.11)
    Colors.BG_HOVER = _mix(bg, "#ffffff", 0.16)
    Colors.BG_PRESSED = _mix(bg, "#ffffff", 0.22)
    Colors.BORDER_SUBTLE = _mix(bg, "#ffffff", 0.12)
    Colors.BORDER_STRONG = _mix(bg, "#ffffff", 0.20)
    # Gradient stops: top lighter, bottom darker than base.
    Colors.BG_WINDOW_TOP = _mix(bg, "#ffffff", 0.08)
    Colors.BG_WINDOW_MID = bg
    Colors.BG_WINDOW_BOT = _scale(bg, 0.7)


def current_theme() -> dict:
    s = load_settings().get("theme") or {}
    return {
        "preset": s.get("preset", "WorkerBee Yellow"),
        "accent": s.get("accent", DEFAULT_ACCENT),
        "bg": s.get("bg", DEFAULT_BG),
        "text": s.get("text", DEFAULT_TEXT),
    }


def apply_saved_theme():
    """Set Colors from the persisted theme. Call before build_global_qss().
    Order: background, then text (whose dim tiers derive from background)."""
    t = current_theme()
    if t["preset"] in PRESETS:
        _apply_accent(PRESETS[t["preset"]])
    else:
        _apply_accent(t["accent"])
    bg = t.get("bg", DEFAULT_BG)
    if bg and bg.lower() != DEFAULT_BG.lower():
        _apply_background(bg)
    else:
        _restore_default_background()
    text = t.get("text", DEFAULT_TEXT)
    if text and text.lower() != DEFAULT_TEXT.lower():
        _apply_text(text)
    else:
        _restore_default_text()


def _restyle_running_app():
    """Rebuild QSS and repaint so both QSS-styled and custom-painted widgets
    pick up the new colours. A plain update() leaves the title-bar strip
    stale, so we re-polish and force a synchronous repaint."""
    try:
        from PySide6.QtWidgets import QApplication, QWidget
        from .style import build_global_qss
    except Exception:
        return
    app = QApplication.instance()
    if app is None:
        return
    app.setStyleSheet(build_global_qss())
    style = app.style()
    for top in app.topLevelWidgets():
        style.unpolish(top)
        style.polish(top)
        for child in top.findChildren(QWidget):
            # Custom-painted widgets cache theme colours; let them re-read.
            refresh = getattr(child, "refresh_theme", None)
            if callable(refresh):
                try:
                    refresh()
                except Exception:
                    pass
            else:
                child.update()
        top.update()
        top.repaint()


def set_preset(name: str):
    t = current_theme()
    t["preset"] = name
    if name in PRESETS:
        t["accent"] = PRESETS[name]
    save_settings({"theme": t})
    apply_saved_theme()
    _restyle_running_app()


def set_custom_accent(accent: str):
    t = current_theme()
    t["preset"] = "Custom"
    t["accent"] = accent
    save_settings({"theme": t})
    apply_saved_theme()
    _restyle_running_app()


def set_custom_background(bg: str):
    t = current_theme()
    t["bg"] = bg
    # Custom bg promotes to a custom theme; keep the chosen accent.
    if t["preset"] in PRESETS:
        t["accent"] = PRESETS[t["preset"]]
    t["preset"] = "Custom"
    save_settings({"theme": t})
    apply_saved_theme()
    _restyle_running_app()


def set_custom_text(text: str):
    t = current_theme()
    t["text"] = text
    if t["preset"] in PRESETS:
        t["accent"] = PRESETS[t["preset"]]
    t["preset"] = "Custom"
    save_settings({"theme": t})
    apply_saved_theme()
    _restyle_running_app()


def reapply_theme():
    """Re-read the saved theme and restyle. Used after a config load swaps
    the active settings file."""
    apply_saved_theme()
    _restyle_running_app()


def reset_theme():
    save_settings({"theme": {
        "preset": "WorkerBee Yellow",
        "accent": DEFAULT_ACCENT,
        "bg": DEFAULT_BG,
        "text": DEFAULT_TEXT,
    }})
    apply_saved_theme()
    _restyle_running_app()
