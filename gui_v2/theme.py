# SPDX-License-Identifier: GPL-3.0-or-later
"""Design tokens (colors, fonts, sizing, motion) - single source of truth."""


class Colors:
    # Background layers, bottom to top.
    BG_BASE       = "#0d0d0e"   # window background
    BG_RAISED     = "#161618"   # cards, sidebar
    BG_OVERLAY    = "#1f1f22"   # modals, hover on cards
    BG_HOVER      = "#2a2a2e"   # button / list item hover
    BG_PRESSED    = "#34343a"

    # Window backdrop gradient stops (top -> bottom). Themeable.
    BG_WINDOW_TOP = "#141418"
    BG_WINDOW_MID = "#0e0e10"
    BG_WINDOW_BOT = "#0a0a0b"

    BORDER_SUBTLE = "#26262a"
    BORDER_STRONG = "#34343a"

    TEXT_PRIMARY   = "#f5f5f6"
    TEXT_SECONDARY = "#a0a0a8"
    TEXT_TERTIARY  = "#6c6c74"
    TEXT_DISABLED  = "#48484f"

    # Brand accent. Primary button, focus rings, progress.
    ACCENT         = "#f4c430"
    ACCENT_HOVER   = "#fad158"
    ACCENT_PRESSED = "#d9ad24"
    ACCENT_MUTED   = "#7a6418"   # subtle accents on dark bg

    SUCCESS = "#3ed598"
    WARNING = "#f0b357"
    ERROR   = "#f55e5e"
    INFO    = "#6db9ff"


class Sizing:
    SPACE_XXS = 2
    SPACE_XS  = 4
    SPACE_SM  = 8
    SPACE_MD  = 12
    SPACE_LG  = 16
    SPACE_XL  = 24
    SPACE_XXL = 32

    RADIUS_SM = 6
    RADIUS_MD = 10
    RADIUS_LG = 14
    RADIUS_PILL = 999

    BUTTON_HEIGHT = 36
    INPUT_HEIGHT  = 36
    TITLEBAR_HEIGHT = 36

    # Splash-to-main target sizes in logical (DPI-scaled) pixels. MainWindow
    # clamps both to a screen fraction. The compact 2.5:1 banner sizes the
    # splash; a wider strip read as oversized in the frozen exe (PyInstaller's
    # DPI manifest scales differently than a source run).
    SPLASH_W = 400
    SPLASH_H = 160
    MAIN_W   = 1280
    MAIN_H   = 800

    MAX_SCREEN_FRACTION = 0.85


class Motion:
    # Durations in ms.
    INSTANT = 100
    QUICK   = 180
    NORMAL  = 280
    SLOW    = 460
    HERO    = 720


class Fonts:
    # Segoe UI Variable is the Win11 system font; falls back on Win10.
    FAMILY = "Segoe UI Variable, Segoe UI, Inter, system-ui, sans-serif"
    FAMILY_MONO = "Cascadia Code, Consolas, monospace"

    # Sizes (pt).
    SIZE_XS    = 10
    SIZE_SM    = 11
    SIZE_BASE  = 12
    SIZE_MD    = 13
    SIZE_LG    = 16
    SIZE_XL    = 20
    SIZE_TITLE = 26
    SIZE_DISPLAY = 30   # large mono numerals in stat tiles
