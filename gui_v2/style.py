# SPDX-License-Identifier: GPL-3.0-or-later
"""Global QSS stylesheet builder."""

from .theme import Colors, Sizing, Fonts


def _rgb(hex_color: str):
    h = hex_color.lstrip("#")
    if len(h) == 3:
        h = "".join(ch * 2 for ch in h)
    try:
        return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    except (ValueError, IndexError):
        return 244, 196, 48


def _shift(hex_color: str, factor: float) -> str:
    """Lighten (>1) or darken (<1) a colour, for the voxel bevels."""
    r, g, b = _rgb(hex_color)
    cl = lambda v: max(0, min(255, int(v)))
    return f"#{cl(r * factor):02x}{cl(g * factor):02x}{cl(b * factor):02x}"


def build_global_qss() -> str:
    """The base sheet, plus the voxel overrides when that skin is active."""
    qss = _base_qss()
    try:
        from .skins import is_voxel
        if is_voxel():
            qss += _voxel_qss()
    except Exception:
        pass
    return qss


def _is_default_bg() -> bool:
    """True when the user has not picked a custom background, so the voxel
    skin may impose its own tinted surface ramp."""
    try:
        # A season sets its own (darker) base, so the ramp must derive
        # from it rather than from the skin's fixed tones.
        from . import seasonal
        if seasonal.is_halloween():
            return False
    except Exception:
        pass
    try:
        from .themes import DEFAULT_BG, current_theme
        return str(current_theme().get("bg", DEFAULT_BG)).lower() == DEFAULT_BG.lower()
    except Exception:
        return True


def voxel_page_color() -> str:
    """Fill the voxel sheet paints the page backdrop with."""
    return "#0e1013" if _is_default_bg() else Colors.BG_BASE


# Panels are a translucent lift over the page rather than an opaque slab, so
# the backdrop's grid and twinkle read faintly through them. Expressed as a
# white overlay so it works over any background colour the user picks.
CARD_TINT = (255, 255, 255, 7)
BAND_TINT = (255, 255, 255, 26)     # section header, one step lighter


def _rgba(tint) -> str:
    return "rgba(%d, %d, %d, %d)" % tint


def voxel_band_color():
    """RGBA the voxel sheet gives #sectionLabel. A section header bar has to
    paint EXACTLY this or the title chip shows a seam against the bar it sits
    in."""
    return BAND_TINT


def voxel_panel_color() -> str:
    """Fill the voxel sheet paints QFrame#card with. Widgets that paint their
    own surface (slide snapshots) have to match it or they flash a different
    shade mid-animation."""
    return "#171a1e" if _is_default_bg() else Colors.BG_RAISED


def _voxel_qss() -> str:
    """Dense pixel-art surfaces: flat fills, crisp 1px edges and tight
    padding. Deliberately restrained - the reference is a muted dusk pixel
    scene, so contrast stays low and the accent is used sparingly rather than
    outlining every control. Appended after the base sheet so it wins."""
    c = Colors
    f = Fonts
    # Cool-tinted charcoals, matching the reference scene's blue-grey darks
    # rather than the neutral near-black of the v2 theme. Only used while the
    # user is on the default background; a custom background keeps deriving
    # from their own colour so theming is not silently overridden.
    tinted = _is_default_bg()
    page = "#0e1013" if tinted else c.BG_BASE
    panel = "#171a1e" if tinted else c.BG_RAISED
    line = "#2b323a" if tinted else _shift(c.BG_RAISED, 1.55)
    seam = "#2e353f" if tinted else _shift(c.BG_RAISED, 1.75)
    line_soft = "#1b2026" if tinted else _shift(c.BG_RAISED, 1.25)
    sunk = "#0a0d10" if tinted else _shift(c.BG_BASE, 0.75)
    hover = "#1f242a" if tinted else c.BG_HOVER
    dim = "#8a939e" if tinted else c.TEXT_TERTIARY
    head = "#a9a9b4" if tinted else c.TEXT_SECONDARY
    card_tint = _rgba(CARD_TINT)
    band_tint = _rgba(BAND_TINT)
    return f"""
    /* ---- voxel skin: dense, flat, 1px edges ---- */

    /* Flat everywhere: the base sheet's window gradient makes top-of-page
       cards read as unbounded against it. */
    QMainWindow, QWidget#root, QWidget#contentInset,
    QStackedWidget#contentStack, QScrollArea#shellScroll,
    QScrollArea#pageScroll {{
        background: {page};
        border: none;
    }}

    /* ...and everything between the page backdrop and the cards is clear, so
       the backdrop's pixel grid (widgets.PageBackdrop) reads through the
       empty parts of every page instead of each layer repainting flat black.
       Scoped to the two shell scroll areas: the generic viewport name is
       shared by list and log views, which must stay opaque. */
    QWidget#contentInset QWidget#root,
    QWidget#contentInset QStackedWidget#contentStack,
    QWidget#contentInset QScrollArea#shellScroll,
    QWidget#contentInset QScrollArea#pageScroll,
    QScrollArea#shellScroll > QWidget#qt_scrollarea_viewport,
    QScrollArea#pageScroll > QWidget#qt_scrollarea_viewport {{
        background: transparent;
        border: none;
    }}

    /* Panels: a translucent lift over the page, one crisp edge, tight inner
       padding. Not an opaque slab - the backdrop grid reads through, which is
       what ties the panels to the page instead of stacking boxes on it. */
    QFrame#card {{
        background-color: {card_tint};
        border: 1px solid {line};
        border-radius: 0px;
    }}

    /* Skill-replacement rows: the same faint panel and 1px edge as the
       card they sit in, not the base sheet's solid block. */
    QFrame#skillSwapCard {{
        background-color: {card_tint};
        border: 1px solid {line};
        border-radius: 0px;
    }}
    QFrame#skillSwapCard:hover {{
        background-color: {band_tint};
        border-color: {seam};
    }}

    QFrame#sidebar {{
        background-color: {panel};
        border: none;
        border-right: 1px solid {seam};
    }}

    /* Nav: compact rows, accent only on the selected one. */
    QPushButton#sidebarItem {{
        border: none;
        border-left: 3px solid transparent;
        border-radius: 0px;
        /* Extra left padding clears the selection caret. */
        padding: 5px 10px 5px 15px;
        min-height: 26px;
        font-size: {f.SIZE_MD}pt;
        font-weight: 500;
    }}
    QPushButton#sidebarItem:hover {{
        background-color: {hover};
    }}
    /* No accent edge bar: the selected row is marked by the stepped caret
       _SidebarItem paints. The transparent border is kept so the label sits
       at the same x whether or not the row is selected. */
    QPushButton#sidebarItem:checked {{
        background-color: {c.BG_OVERLAY};
        border-left: 3px solid transparent;
        color: {c.TEXT_PRIMARY};
        font-weight: 600;
    }}

    /* Buttons: flat blocks that hug their label. The press state shifts
       tone, not geometry. */
    /* 2px vertical padding, not 4: the 1px accent border counts toward the
       box, and the CTA has to land on the same 34px as the bordered ghost
       buttons and the inputs beside it. */
    QPushButton#primaryCta, QPushButton#splashPrimary {{
        background-color: {c.ACCENT};
        color: #16130a;
        border: 1px solid {c.ACCENT};
        border-radius: 0px;
        padding: 2px 14px;
        min-height: 28px;
        max-height: 28px;
        font-weight: 600;
    }}
    QPushButton#secondary, QPushButton#splashSecondary {{
        background-color: {c.BG_OVERLAY};
        border: 1px solid {line};
        border-radius: 0px;
        padding: 4px 12px;
    }}
    QPushButton#secondary:hover, QPushButton#splashSecondary:hover {{
        border-color: {c.ACCENT_MUTED};
    }}

    /* The base sheet sizes these with literals the legacy skin depends on, so
       they never followed BUTTON_HEIGHT/INPUT_HEIGHT down to the voxel scale:
       every ghost button rendered 42px and the run spinners 46px, against 34px
       inputs beside them. Overridden by id here, voxel only. */
    QPushButton#ghostBtn {{
        border-radius: 0px;
        padding: 2px 12px;
        min-height: 28px;
        max-height: 28px;
    }}
    QSpinBox#runCount, QTimeEdit#runCount {{
        padding: 2px 6px;
        min-height: 24px;
    }}

    /* The splash card fills the whole frameless splash window, so it is the
       PAGE surface, not a card on a page: it takes {page}, not {panel}. The
       base sheet paints it with the v2 3-stop gradient, which made the first
       surface of every launch the one place the old look survived. */
    QFrame#splashCard {{
        background-color: {page};
        border: 1px solid {seam};
    }}

    /* Title-bar search: the same recessed well as the other inputs, and
       a square list under it. */
    QLineEdit#titleSearch {{
        background-color: {sunk};
        border: 1px solid {line};
        border-radius: 0px;
        padding: 0px 8px;
    }}
    QLineEdit#titleSearch:focus {{
        border: 1px solid {c.ACCENT};
    }}
    QFrame#searchPopup {{
        background-color: {panel};
        border: 1px solid {seam};
        border-radius: 0px;
    }}

    /* Inputs: recessed well, one edge, accent only on focus. */
    QLineEdit#textField, QComboBox#combo, QSpinBox, QDoubleSpinBox,
    QPlainTextEdit, QTextEdit {{
        background-color: {sunk};
        border: 1px solid {line};
        border-radius: 0px;
        padding: 2px 6px;
    }}
    QLineEdit#textField:focus, QComboBox#combo:focus,
    QSpinBox:focus, QDoubleSpinBox:focus {{
        border: 1px solid {c.ACCENT};
    }}

    /* Headers: section titles were the DIMMEST text on the page, so the
       structure could not be skimmed. Lift them above body text and reserve
       the muted tone for micro-labels underneath. */
    /* Panel titles are drawn in the pixel face (widgets._title_label), so
       these only carry the accent tick and spacing - no font override, which
       is what made every header read as a code editor. */
    /* Section titles sit on a filled band rather than floating on the page,
       so a long list reads as banded groups instead of one undifferentiated
       run of items. */
    /* The filled band alone marks a section. No accent edge bar: it is the
       most over-used selection/heading device there is, and with one on every
       header the accent stopped meaning anything. */
    QWidget#sectionLabel {{
        background-color: {band_tint};
    }}
    /* Inside a folding header the bar already paints the band across the full
       width. The title would otherwise paint a SECOND translucent layer over
       it and show as a lighter chip - two alphas compound where a solid
       colour used to match exactly. */
    QWidget#sectionHeader QWidget#sectionLabel {{
        background: transparent;
    }}
    QLabel#subSectionLabel, QLabel#inlineMeta {{
        color: {dim};
    }}

    /* No settingRow min-height here: the row derives its own floor from the
       control it wraps (widgets.SettingRow). A fixed value is applied during
       polish, i.e. AFTER the row computed its floor, so it overrides it - and
       26px is below what the legacy skin's taller toggle needs. */
    QLabel#settingTitle {{
        font-size: {f.SIZE_BASE}pt;
    }}


    /* Slim square scrollbars. */
    QScrollBar:vertical {{
        width: 10px;
        background: {c.BG_BASE};
        border-left: 1px solid {line_soft};
    }}
    QScrollBar:horizontal {{
        height: 10px;
        background: {c.BG_BASE};
        border-top: 1px solid {line_soft};
    }}
    QScrollBar::handle:vertical, QScrollBar::handle:horizontal {{
        background: {line};
        border: none;
        border-radius: 0px;
        min-height: 24px;
        min-width: 24px;
    }}
    QScrollBar::handle:vertical:hover, QScrollBar::handle:horizontal:hover {{
        background: {c.ACCENT_MUTED};
    }}

    QCheckBox::indicator {{
        border: 1px solid {line};
        border-radius: 0px;
    }}

    /* Base-sheet holdouts: these carry hardcoded pixel radii rather than the
       RADIUS_* tokens, so squaring the tokens never reached them and they
       kept rendering in the v2 shape. */
    QListWidget#orderedList::indicator,
    QSlider#slider::groove:horizontal,
    QSlider#slider::sub-page:horizontal,
    QSlider#slider::handle:horizontal,
    QProgressBar#splashBar, QProgressBar#splashBar::chunk,
    QPushButton#splashClose {{
        border-radius: 0px;
    }}

    QFrame#hrule {{
        background-color: {line_soft};
        max-height: 1px;
    }}
    """


def _base_qss() -> str:
    c = Colors
    s = Sizing
    f = Fonts
    return f"""
    * {{
        font-family: {f.FAMILY};
        font-size: {f.SIZE_BASE}pt;
        color: {c.TEXT_PRIMARY};
        outline: none;
        selection-background-color: {c.ACCENT_MUTED};
        selection-color: {c.TEXT_PRIMARY};
    }}

    /* Subtle vertical gradient on the window for depth - just enough
       to lift it off dead-flat black. Page surfaces are transparent so
       the gradient reads through. */
    QMainWindow {{
        background-color: qlineargradient(
            x1:0, y1:0, x2:0, y2:1,
            stop:0 {c.BG_WINDOW_TOP}, stop:0.45 {c.BG_WINDOW_MID},
            stop:1 {c.BG_WINDOW_BOT});
    }}
    QWidget#root {{
        background-color: transparent;
    }}

    /* The content stack carries the gradient as an OPAQUE background.
       Pages stacked on top are transparent, so switching pages repaints
       this layer and never leaves stale pixels from the previous page. */
    QStackedWidget#contentStack {{
        background-color: qlineargradient(
            x1:0, y1:0, x2:0, y2:1,
            stop:0 {c.BG_WINDOW_TOP}, stop:0.45 {c.BG_WINDOW_MID},
            stop:1 {c.BG_WINDOW_BOT});
    }}

    /* Content inset wrapper: carries the same themed gradient so the strip
       at the top (beside the floating window controls) is never a black
       band and follows the colour theme. */
    QWidget#contentInset {{
        background-color: qlineargradient(
            x1:0, y1:0, x2:0, y2:1,
            stop:0 {c.BG_WINDOW_TOP}, stop:0.45 {c.BG_WINDOW_MID},
            stop:1 {c.BG_WINDOW_BOT});
    }}

    /* Splash card - chromeless, but OPAQUE (gradient) so the rotating
       tip / status labels over it repaint cleanly instead of ghosting.
       DWM rounds the window corners over this, so square corners here
       don't show. */
    QFrame#splashCard {{
        background-color: qlineargradient(
            x1:0, y1:0, x2:0, y2:1,
            stop:0 {c.BG_WINDOW_TOP}, stop:0.45 {c.BG_WINDOW_MID},
            stop:1 {c.BG_WINDOW_BOT});
        border: none;
    }}

    /* Floating close button in top-right of splash. Subtle until hover. */
    QPushButton#splashClose {{
        background-color: transparent;
        border: none;
        color: {c.TEXT_TERTIARY};
        font-size: {f.SIZE_MD}pt;
        padding: 0;
        min-width: 28px;
        max-width: 28px;
        min-height: 28px;
        max-height: 28px;
        border-radius: 14px;
    }}
    QPushButton#splashClose:hover {{
        background-color: {c.BG_HOVER};
        color: {c.TEXT_PRIMARY};
    }}

    QLabel#splashTitle {{
        color: {c.TEXT_PRIMARY};
        font-size: {f.SIZE_XL}pt;
        font-weight: 600;
    }}

    QLabel#splashStatus {{
        color: {c.TEXT_SECONDARY};
        font-size: {f.SIZE_SM}pt;
    }}

    QLabel#splashSubtle {{
        color: {c.TEXT_TERTIARY};
        font-size: {f.SIZE_XS}pt;
    }}

    QLabel#splashSubtitle {{
        color: {c.TEXT_SECONDARY};
        font-size: {f.SIZE_SM}pt;
    }}

    /* Update prompt meta line - denser than the subtitle since it
       packs version numbers + size into one line. */
    QLabel#splashMeta {{
        color: {c.TEXT_SECONDARY};
        font-size: {f.SIZE_SM}pt;
    }}

    QLabel#splashVersion {{
        color: {c.TEXT_TERTIARY};
        font-size: {f.SIZE_XS}pt;
    }}

    /* Splash progress bar - thin, rounded, no chunks, no border. */
    QProgressBar#splashBar {{
        background-color: {c.BG_OVERLAY};
        border: none;
        border-radius: 2px;
        max-height: 4px;
        min-height: 4px;
    }}
    QProgressBar#splashBar::chunk {{
        background-color: {c.ACCENT};
        border-radius: 2px;
    }}

    /* Custom title bar - a transparent overlay holding only the window
       controls; the sidebar and content run to the top behind it, so
       there is no separate strip and no seam. */
    QFrame#titleBar {{
        background-color: transparent;
        border: none;
    }}

    QLabel#titleBarText {{
        color: {c.TEXT_SECONDARY};
        font-size: {f.SIZE_SM}pt;
        font-weight: 500;
    }}

    QPushButton#titleBarBtn, QPushButton#titleBarBtnClose {{
        background-color: transparent;
        border: none;
        color: {c.TEXT_SECONDARY};
        font-size: {f.SIZE_MD}pt;
        padding: 0px;
        min-width: 36px;
        max-width: 36px;
        min-height: 28px;
        max-height: 28px;
    }}
    QPushButton#titleBarBtn:hover {{
        background-color: {c.BG_HOVER};
        color: {c.TEXT_PRIMARY};
    }}
    /* The close button carried ONLY a :hover rule, so at rest it fell back to
       the platform default button - a light raised box next to two flat ones. */
    QPushButton#titleBarBtnClose:hover {{
        background-color: #e81123;
        color: white;
    }}

    /* Primary button */
    QPushButton#primary {{
        background-color: {c.ACCENT};
        color: #1a1500;
        border: none;
        border-radius: {s.RADIUS_MD}px;
        padding: 8px 16px;
        font-weight: 600;
        min-height: {s.BUTTON_HEIGHT}px;
    }}
    QPushButton#primary:hover  {{ background-color: {c.ACCENT_HOVER}; }}
    QPushButton#primary:pressed{{ background-color: {c.ACCENT_PRESSED}; }}

    /* Secondary button */
    QPushButton#secondary {{
        background-color: {c.BG_OVERLAY};
        color: {c.TEXT_PRIMARY};
        border: 1px solid {c.BORDER_SUBTLE};
        border-radius: {s.RADIUS_MD}px;
        padding: 8px 16px;
        min-height: {s.BUTTON_HEIGHT}px;
    }}
    QPushButton#secondary:hover  {{ background-color: {c.BG_HOVER}; border-color: {c.BORDER_STRONG}; }}
    QPushButton#secondary:pressed{{ background-color: {c.BG_PRESSED}; }}

    /* Splash-only buttons. Compact - the splash is small and the
       default 36px buttons feel chunky in that footprint. */
    QPushButton#splashPrimary {{
        background-color: {c.ACCENT};
        color: #1a1500;
        border: none;
        border-radius: {s.RADIUS_SM}px;
        padding: 4px 12px;
        font-size: {f.SIZE_SM}pt;
        font-weight: 600;
        min-height: 26px;
        max-height: 26px;
    }}
    QPushButton#splashPrimary:hover   {{ background-color: {c.ACCENT_HOVER}; }}
    QPushButton#splashPrimary:pressed {{ background-color: {c.ACCENT_PRESSED}; }}

    QPushButton#splashSecondary {{
        background-color: transparent;
        color: {c.TEXT_SECONDARY};
        border: 1px solid {c.BORDER_SUBTLE};
        border-radius: {s.RADIUS_SM}px;
        padding: 4px 12px;
        font-size: {f.SIZE_SM}pt;
        min-height: 26px;
        max-height: 26px;
    }}
    QPushButton#splashSecondary:hover   {{ background-color: {c.BG_HOVER}; color: {c.TEXT_PRIMARY}; border-color: {c.BORDER_STRONG}; }}
    QPushButton#splashSecondary:pressed {{ background-color: {c.BG_PRESSED}; }}

    /* Sidebar */
    QFrame#sidebar {{
        background-color: {c.BG_RAISED};
        border: none;
    }}

    QLabel#sidebarBrand {{
        color: {c.TEXT_PRIMARY};
        font-size: {f.SIZE_LG}pt;
        font-weight: 700;
        padding: 0;
    }}

    QLabel#sidebarTagline {{
        color: {c.TEXT_TERTIARY};
        font-size: {f.SIZE_XS}pt;
        padding: 0;
    }}

    QLabel#sidebarVersion {{
        font-family: {f.FAMILY_MONO};
        color: {c.TEXT_DISABLED};
        font-size: {f.SIZE_XS}pt;
        padding: 0 12px;
    }}

    /* Sidebar nav items. Selected gets a 3px yellow bar on the left
       via border-left; unchecked has a matching transparent border
       to keep the text aligned. */
    QPushButton#sidebarItem {{
        background-color: transparent;
        color: {c.TEXT_SECONDARY};
        border: none;
        border-left: 3px solid transparent;
        border-radius: 0;
        padding: 9px 14px 9px 13px;
        text-align: left;
        min-height: 38px;
        font-size: {f.SIZE_MD}pt;
        font-weight: 500;
    }}
    QPushButton#sidebarItem:hover {{
        color: {c.TEXT_PRIMARY};
        background-color: {c.BG_HOVER};
    }}
    QPushButton#sidebarItem:checked {{
        color: {c.TEXT_PRIMARY};
        border-left: 3px solid {c.ACCENT};
        background-color: {c.BG_OVERLAY};
        font-weight: 600;
    }}
    QPushButton#sidebarItem:checked:hover {{
        background-color: {c.BG_OVERLAY};
    }}

    /* Page chrome */
    QLabel#pageTitle {{
        color: {c.TEXT_PRIMARY};
        font-size: {f.SIZE_TITLE}pt;
        font-weight: 700;
        letter-spacing: -0.3px;
    }}

    QLabel#sectionLabel {{
        color: {c.TEXT_TERTIARY};
        font-size: {f.SIZE_XS}pt;
        font-weight: 700;
        letter-spacing: 1.5px;
        padding: 0;
    }}

    QLabel#subSectionLabel {{
        color: {c.TEXT_SECONDARY};
        font-size: {f.SIZE_SM}pt;
        font-weight: 600;
        padding: 0;
    }}

    QLabel#inlineHint {{
        color: {c.TEXT_TERTIARY};
        font-size: {f.SIZE_SM}pt;
    }}

    /* Centred empty-state heading (e.g. Scheduler with no tasks). */
    QLabel#emptyTitle {{
        color: {c.TEXT_SECONDARY};
        font-size: {f.SIZE_LG}pt;
        font-weight: 600;
    }}

    QLabel#inlineMeta {{
        color: {c.TEXT_SECONDARY};
        font-size: {f.SIZE_SM}pt;
    }}

    /* Rank 1 in a stats block. */
    QLabel#rankBest {{
        color: {c.ACCENT};
        font-size: {f.SIZE_SM}pt;
        font-weight: 700;
    }}

    /* Elevated surface panel - groups content with depth instead of
       leaving it flat on the page. Lighter bg + soft border + rounded
       corners; the drop shadow is applied in code (widgets.Card). */
    QFrame#card {{
        background-color: {c.BG_RAISED};
        border: 1px solid {c.BORDER_SUBTLE};
        border-radius: {s.RADIUS_LG}px;
    }}

    /* Horizontal rule between sections - flat alternative to card
       borders. */
    QFrame#hrule {{
        background-color: {c.BORDER_SUBTLE};
        border: none;
        max-height: 1px;
        min-height: 1px;
    }}

    /* Hero block (dashboard) - flat, no surface */
    QLabel#heroTitle {{
        color: {c.TEXT_PRIMARY};
        font-size: {f.SIZE_XL}pt;
        font-weight: 700;
        letter-spacing: -0.2px;
    }}
    QLabel#heroSubtitle {{
        color: {c.TEXT_SECONDARY};
        font-size: {f.SIZE_MD}pt;
    }}
    QLabel#heroHint {{
        color: {c.TEXT_TERTIARY};
        font-size: {f.SIZE_SM}pt;
    }}

    /* Stat lines - "label .... value" rows, flat */
    QLabel#statRowLabel {{
        color: {c.TEXT_SECONDARY};
        font-size: {f.SIZE_MD}pt;
    }}
    QLabel#statRowValue {{
        font-family: {f.FAMILY_MONO};
        color: {c.TEXT_PRIMARY};
        font-size: {f.SIZE_MD}pt;
        font-weight: 600;
    }}
    QLabel#statRowValueAccent {{
        font-family: {f.FAMILY_MONO};
        color: {c.ACCENT};
        font-size: {f.SIZE_MD}pt;
        font-weight: 700;
    }}

    /* Stat tiles - large mono numeral over a small uppercase label.
       The headline analytics strip on Dashboard / Stats. */
    QWidget#statTiles, QWidget#statTile {{
        background-color: transparent;
    }}
    QFrame#statTileDivider {{
        background-color: {c.BORDER_SUBTLE};
        border: none;
    }}
    QLabel#statTileValue {{
        font-family: {f.FAMILY_MONO};
        color: {c.TEXT_PRIMARY};
        font-size: {f.SIZE_DISPLAY}pt;
        font-weight: 700;
        letter-spacing: -0.5px;
    }}
    QLabel#statTileValueAccent {{
        font-family: {f.FAMILY_MONO};
        color: {c.ACCENT};
        font-size: {f.SIZE_DISPLAY}pt;
        font-weight: 700;
        letter-spacing: -0.5px;
    }}
    QLabel#statTileLabel {{
        color: {c.TEXT_TERTIARY};
        font-size: {f.SIZE_XS}pt;
        font-weight: 600;
        letter-spacing: 1.5px;
    }}

    /* Activity rows - hover-only highlight, no card border */
    QFrame#activityRow {{
        background-color: transparent;
        border: none;
        border-radius: {s.RADIUS_SM}px;
    }}
    QFrame#activityRow:hover {{
        background-color: {c.BG_HOVER};
    }}
    QLabel#activityDot {{
        color: {c.TEXT_SECONDARY};
        font-size: {f.SIZE_LG}pt;
    }}
    QLabel#activityTitle {{
        color: {c.TEXT_PRIMARY};
        font-size: {f.SIZE_MD}pt;
        font-weight: 600;
    }}
    QLabel#activitySubtitle {{
        color: {c.TEXT_TERTIARY};
        font-size: {f.SIZE_SM}pt;
    }}
    QLabel#activityMeta {{
        color: {c.TEXT_TERTIARY};
        font-size: {f.SIZE_SM}pt;
    }}

    /* Drag-reorder card on the skill-replacement list. Lives here rather than
       in a per-widget stylesheet so a live skin/theme switch rebuilds it. */
    QFrame#skillSwapCard {{
        background-color: {c.BG_OVERLAY};
        border: 1px solid {c.BORDER_SUBTLE};
        border-radius: {s.RADIUS_SM}px;
    }}
    QFrame#skillSwapCard:hover {{
        background-color: {c.BG_HOVER};
    }}

    /* Primary CTA */
    QPushButton#primaryCta {{
        background-color: {c.ACCENT};
        color: #1a1500;
        border: none;
        border-radius: {s.RADIUS_SM}px;
        padding: 6px 16px;
        font-size: {f.SIZE_BASE}pt;
        font-weight: 600;
        min-height: 30px;
        max-height: 30px;
    }}
    QPushButton#primaryCta:hover {{
        background-color: {c.ACCENT_HOVER};
    }}
    QPushButton#primaryCta:pressed {{
        background-color: {c.ACCENT_PRESSED};
    }}
    QPushButton#primaryCta:disabled {{
        background-color: {c.BG_OVERLAY};
        color: {c.TEXT_DISABLED};
    }}

    /* Ghost / secondary action */
    QPushButton#ghostBtn {{
        background-color: transparent;
        color: {c.TEXT_SECONDARY};
        border: 1px solid {c.BORDER_SUBTLE};
        border-radius: {s.RADIUS_SM}px;
        padding: 5px 14px;
        font-size: {f.SIZE_SM}pt;
        font-weight: 500;
        min-height: 30px;
        max-height: 30px;
    }}
    QPushButton#ghostBtn:hover {{
        background-color: {c.BG_HOVER};
        color: {c.TEXT_PRIMARY};
        border-color: {c.BORDER_STRONG};
    }}
    QPushButton#ghostBtn:pressed {{
        background-color: {c.BG_PRESSED};
    }}
    QPushButton#ghostBtn:disabled {{
        color: {c.TEXT_DISABLED};
        border-color: {c.BORDER_SUBTLE};
    }}

    /* Text-only link buttons (inline "View all", "Edit", "Remove") */
    QPushButton#linkBtn {{
        background-color: transparent;
        color: {c.TEXT_SECONDARY};
        border: none;
        padding: 4px 8px;
        font-size: {f.SIZE_SM}pt;
        font-weight: 500;
    }}
    QPushButton#linkBtn:hover {{
        color: {c.ACCENT};
    }}
    QPushButton#linkBtn[danger="true"]:hover {{
        color: {c.ERROR};
    }}

    /* Segmented control - a rounded track with a sliding highlight pill
       (both painted by widgets.Segmented). The buttons are transparent
       and just carry the text; the active one reads dark on the pill. */
    QWidget#segmented {{
        background-color: transparent;
    }}
    QPushButton#segmentedItem {{
        background-color: transparent;
        color: {c.TEXT_SECONDARY};
        border: none;
        /* Weight 700 so the button is sized for the bold (selected) label and
           the bold text cannot overflow; padding clears the capped corner
           radius (see Segmented.paintEvent). */
        padding: 6px 20px;
        font-size: {f.SIZE_SM}pt;
        font-weight: 700;
        min-height: 26px;
    }}
    QPushButton#segmentedItem:hover {{
        color: {c.TEXT_PRIMARY};
    }}
    QPushButton#segmentedItem:checked {{
        color: {c.BG_BASE};
        font-weight: 700;
    }}

    /* Luxcavation launch-console readout. */
    QLabel#luxSummary {{
        color: {c.TEXT_TERTIARY};
        font-size: {f.SIZE_SM}pt;
        font-weight: 500;
    }}

    /* Setting rows (inside sections) */
    QLabel#settingTitle {{
        color: {c.TEXT_PRIMARY};
        font-size: {f.SIZE_MD}pt;
        font-weight: 600;
    }}
    QLabel#settingSubtitle {{
        color: {c.TEXT_TERTIARY};
        font-size: {f.SIZE_SM}pt;
    }}

    /* Toggle is a custom-painted QAbstractButton (see widgets.Toggle);
       no QSS needed for its visuals. */

    /* Chip list - inline tag pills used for pack priority etc. */
    QPushButton#chip {{
        background-color: {c.BG_OVERLAY};
        color: {c.TEXT_SECONDARY};
        border: 1px solid {c.BORDER_SUBTLE};
        border-radius: 0px;
        padding: 4px 12px;
        font-size: {f.SIZE_SM}pt;
        font-weight: 500;
        min-height: 26px;
    }}
    QPushButton#chip:hover {{
        background-color: {c.BG_HOVER};
        color: {c.TEXT_PRIMARY};
        border-color: {c.BORDER_STRONG};
    }}
    QPushButton#chip:checked {{
        background-color: {c.BG_HOVER};
        color: {c.TEXT_PRIMARY};
        border-color: {c.TEXT_TERTIARY};
    }}

    /* Tri-state pack chip: neutral / prioritise (green) / avoid (red) */
    QPushButton#triChip {{
        background-color: {c.BG_OVERLAY};
        color: {c.TEXT_SECONDARY};
        border: 1px solid {c.BORDER_SUBTLE};
        border-radius: {s.RADIUS_PILL}px;
        padding: 4px 12px;
        font-size: {f.SIZE_SM}pt;
        font-weight: 500;
        min-height: 26px;
    }}
    QPushButton#triChip:hover {{
        border-color: {c.BORDER_STRONG};
        color: {c.TEXT_PRIMARY};
    }}
    QPushButton#triChip[state="priority"] {{
        background-color: rgba(62, 213, 152, 0.16);
        color: {c.SUCCESS};
        border-color: {c.SUCCESS};
    }}
    QPushButton#triChip[state="avoid"] {{
        background-color: rgba(245, 94, 94, 0.14);
        color: {c.ERROR};
        border-color: {c.ERROR};
    }}

    /* Priority list (reward-card order) */
    QFrame#priorityRow {{
        background-color: {c.BG_RAISED};
        border: 1px solid {c.BORDER_SUBTLE};
        border-radius: {s.RADIUS_SM}px;
    }}
    QFrame#priorityRow:hover {{
        border-color: {c.BORDER_STRONG};
    }}
    QLabel#priorityRank {{
        color: {c.TEXT_SECONDARY};
        font-size: {f.SIZE_MD}pt;
        font-weight: 700;
    }}
    QLabel#priorityName {{
        color: {c.TEXT_PRIMARY};
        font-size: {f.SIZE_MD}pt;
        font-weight: 500;
    }}
    QFrame#priorityRow[active="false"] {{
        background-color: transparent;
    }}
    QLabel#priorityRankDim {{
        color: {c.TEXT_DISABLED};
        font-size: {f.SIZE_MD}pt;
        font-weight: 700;
    }}
    QLabel#priorityNameDim {{
        color: {c.TEXT_TERTIARY};
        font-size: {f.SIZE_MD}pt;
        font-weight: 500;
    }}
    QPushButton#priorityArrow {{
        background-color: transparent;
        color: {c.TEXT_SECONDARY};
        border: none;
        border-radius: {s.RADIUS_SM}px;
        font-size: {f.SIZE_MD}pt;
        min-width: 30px;
        max-width: 30px;
        min-height: 28px;
    }}
    QPushButton#priorityArrow:hover {{
        background-color: {c.BG_HOVER};
        color: {c.TEXT_PRIMARY};
    }}
    QPushButton#priorityArrow:disabled {{
        color: {c.TEXT_DISABLED};
    }}

    /* Drag-reorderable ordered list (card priority, sinner order) */
    QListWidget#orderedList {{
        background-color: transparent;
        border: none;
        outline: none;
    }}
    QListWidget#orderedList::item {{
        background-color: {c.BG_RAISED};
        color: {c.TEXT_PRIMARY};
        border: 1px solid {c.BORDER_SUBTLE};
        border-radius: {s.RADIUS_SM}px;
        padding: 7px 10px;
        margin: 2px 0;
    }}
    QListWidget#orderedList::item:hover {{
        border-color: {c.BORDER_STRONG};
        background-color: {c.BG_OVERLAY};
    }}
    QListWidget#orderedList::item:selected {{
        border-color: {c.ACCENT};
        color: {c.TEXT_PRIMARY};
        background-color: {c.BG_OVERLAY};
    }}
    QListWidget#orderedList::indicator {{
        width: 16px;
        height: 16px;
        border: 1px solid {c.BORDER_STRONG};
        border-radius: 4px;
        background-color: {c.BG_OVERLAY};
    }}
    QListWidget#orderedList::indicator:checked {{
        background-color: #d8d8dc;
        border-color: #d8d8dc;
    }}

    /* Include checkbox in the sinner list */
    QPushButton#includeCheck {{
        background-color: transparent;
        color: #1a1500;
        border: 1px solid {c.BORDER_STRONG};
        border-radius: {s.RADIUS_SM}px;
        font-size: {f.SIZE_SM}pt;
        font-weight: 700;
        min-width: 22px;
        max-width: 22px;
        min-height: 22px;
        max-height: 22px;
    }}
    QPushButton#includeCheck:hover {{
        border-color: {c.TEXT_TERTIARY};
    }}
    QPushButton#includeCheck:checked {{
        background-color: #d8d8dc;
        border-color: #d8d8dc;
    }}

    /* Cycle chip (grace tiers) - off = neutral, on = accent */
    QPushButton#cycleChip {{
        background-color: {c.BG_OVERLAY};
        color: {c.TEXT_SECONDARY};
        border: 1px solid {c.BORDER_SUBTLE};
        border-radius: {s.RADIUS_PILL}px;
        padding: 4px 14px;
        font-size: {f.SIZE_SM}pt;
        font-weight: 500;
        min-height: 26px;
    }}
    QPushButton#cycleChip:hover {{
        border-color: {c.BORDER_STRONG};
        color: {c.TEXT_PRIMARY};
    }}
    QPushButton#cycleChip[on="true"] {{
        background-color: {c.BG_HOVER};
        color: {c.TEXT_PRIMARY};
        border-color: {c.TEXT_TERTIARY};
        font-weight: 600;
    }}

    /* Team rotation rows */
    QFrame#teamRow {{
        background-color: transparent;
        border: none;
        border-radius: {s.RADIUS_SM}px;
    }}
    QFrame#teamRow:hover {{
        background-color: {c.BG_HOVER};
    }}
    QLabel#teamRowName {{
        color: {c.TEXT_PRIMARY};
        font-size: {f.SIZE_MD}pt;
        font-weight: 600;
    }}
    QLabel#teamRowAffinities {{
        color: {c.TEXT_TERTIARY};
        font-size: {f.SIZE_SM}pt;
    }}

    /* Tab bar (page-level subnav). The active underline is painted and
       animated by widgets.IconlessTabBar, so no border here. */
    QPushButton#tabBtn {{
        background-color: transparent;
        color: {c.TEXT_SECONDARY};
        border: none;
        padding: 8px 16px;
        font-size: {f.SIZE_SM}pt;
        font-weight: 500;
    }}
    QPushButton#tabBtn:hover {{
        color: {c.TEXT_PRIMARY};
    }}
    QPushButton#tabBtn:checked {{
        color: {c.ACCENT};
        font-weight: 600;
    }}

    /* Spin box / time edit for numeric inputs */
    QSpinBox#runCount, QTimeEdit#runCount {{
        background-color: {c.BG_OVERLAY};
        color: {c.TEXT_PRIMARY};
        border: 1px solid {c.BORDER_SUBTLE};
        border-radius: {s.RADIUS_SM}px;
        padding: 6px 10px;
        font-size: {f.SIZE_MD}pt;
        min-height: 32px;
    }}
    QSpinBox#runCount:focus, QTimeEdit#runCount:focus {{
        border-color: {c.ACCENT};
    }}
    /* Step button SUB-CONTROLS: transparent background and no border so they
       blend into the styled pill. Giving them any geometry puts Qt6 on the
       fully-custom CC_SpinBox path, where the arrow is drawn ONLY from the
       ::up-arrow/::down-arrow rules below - there is no native fallback, so
       without those rules the step affordance is never painted at all. Qt
       renders them as filled blocks rather than true triangles, the same as
       QComboBox#combo::down-arrow. The explicit `subcontrol-position` is
       needed because without it some builds clip the buttons against the
       styled border-radius and they disappear entirely. */
    QSpinBox#runCount::up-button, QTimeEdit#runCount::up-button {{
        background-color: transparent;
        border: none;
        width: 18px;
        subcontrol-origin: padding;
        subcontrol-position: top right;
        /* Round the top-right corner so a hover bg doesn't paint a
           square over the parent's rounded corner. */
        border-top-right-radius: {s.RADIUS_SM - 1}px;
    }}
    QSpinBox#runCount::down-button, QTimeEdit#runCount::down-button {{
        background-color: transparent;
        border: none;
        width: 18px;
        subcontrol-origin: padding;
        subcontrol-position: bottom right;
        /* Same for the bottom-right corner: the down-button sits flush
           against the parent's rounded bottom-right and would otherwise
           paint a hard 90-degree corner, making the spinbox look as
           though its bottom edge had been clipped flat. */
        border-bottom-right-radius: {s.RADIUS_SM - 1}px;
    }}
    QSpinBox#runCount::up-button:hover, QTimeEdit#runCount::up-button:hover,
    QSpinBox#runCount::down-button:hover, QTimeEdit#runCount::down-button:hover {{
        background-color: {c.BG_HOVER};
    }}
    QSpinBox#runCount::up-arrow, QTimeEdit#runCount::up-arrow {{
        width: 0; height: 0;
        border-left: 4px solid transparent;
        border-right: 4px solid transparent;
        border-bottom: 5px solid {c.TEXT_PRIMARY};
    }}
    QSpinBox#runCount::down-arrow, QTimeEdit#runCount::down-arrow {{
        width: 0; height: 0;
        border-left: 4px solid transparent;
        border-right: 4px solid transparent;
        border-top: 5px solid {c.TEXT_PRIMARY};
    }}
    /* At the range limit Qt marks the sub-control :off; without this the
       indicator stays at full brightness and reads as steppable. */
    QSpinBox#runCount::up-arrow:off, QSpinBox#runCount::up-arrow:disabled,
    QTimeEdit#runCount::up-arrow:off, QTimeEdit#runCount::up-arrow:disabled {{
        border-bottom-color: {c.TEXT_TERTIARY};
    }}
    QSpinBox#runCount::down-arrow:off, QSpinBox#runCount::down-arrow:disabled,
    QTimeEdit#runCount::down-arrow:off, QTimeEdit#runCount::down-arrow:disabled {{
        border-top-color: {c.TEXT_TERTIARY};
    }}
    QSpinBox#runCount::up-arrow:hover, QTimeEdit#runCount::up-arrow:hover {{
        border-bottom-color: {c.ACCENT};
    }}
    QSpinBox#runCount::down-arrow:hover, QTimeEdit#runCount::down-arrow:hover {{
        border-top-color: {c.ACCENT};
    }}

    /* Scroll area inside pages should match the page bg */
    QScrollArea#pageScroll, QScrollArea#shellScroll,
    QScrollArea#floorTabScroll {{
        background-color: transparent;
        border: none;
    }}
    QScrollArea#pageScroll > QWidget > QWidget,
    QScrollArea#shellScroll > QWidget > QWidget,
    QScrollArea#floorTabScroll > QWidget {{
        background-color: transparent;
    }}
    /* The shell scroll areas run to the very top of the window, behind the
       transparent title-bar overlay. Inset their vertical scrollbar so it
       starts below the window-control buttons instead of clipping under
       them. content_wrap already insets content by SPACE_MD, so the
       remaining clearance is the rest of the title-bar height. */
    QScrollArea#shellScroll QScrollBar:vertical {{
        margin-top: {s.TITLEBAR_HEIGHT - s.SPACE_MD}px;
    }}

    /* Key-capture button (shortcut editor) */
    QPushButton#keyCapture {{
        background-color: {c.BG_OVERLAY};
        color: {c.TEXT_PRIMARY};
        border: 1px solid {c.BORDER_SUBTLE};
        border-radius: {s.RADIUS_SM}px;
        padding: 6px 14px;
        font-size: {f.SIZE_SM}pt;
        font-weight: 600;
        min-height: 30px;
    }}
    QPushButton#keyCapture:hover {{
        border-color: {c.BORDER_STRONG};
    }}
    QPushButton#keyCapture[capturing="true"] {{
        border-color: {c.ACCENT};
        color: {c.ACCENT};
        background-color: {c.BG_BASE};
    }}

    /* Help page body text */
    QLabel#helpBody {{
        color: {c.TEXT_SECONDARY};
        font-size: {f.SIZE_MD}pt;
        line-height: 140%;
    }}

    /* Log viewer */
    QPlainTextEdit#logView {{
        background-color: {c.BG_BASE};
        color: {c.TEXT_SECONDARY};
        border: 1px solid {c.BORDER_SUBTLE};
        border-radius: {s.RADIUS_MD}px;
        padding: 8px;
        selection-background-color: {c.ACCENT_MUTED};
    }}

    /* Modal dialog (team edit) */
    QDialog#dialog {{
        background-color: {c.BG_RAISED};
    }}
    QLabel#dialogTitle {{
        color: {c.TEXT_PRIMARY};
        font-size: {f.SIZE_LG}pt;
        font-weight: 700;
    }}
    QDialog#dialog QDialogButtonBox QPushButton {{
        background-color: {c.BG_OVERLAY};
        color: {c.TEXT_PRIMARY};
        border: 1px solid {c.BORDER_SUBTLE};
        border-radius: {s.RADIUS_SM}px;
        padding: 6px 18px;
        min-height: 30px;
        font-size: {f.SIZE_SM}pt;
    }}
    QDialog#dialog QDialogButtonBox QPushButton:hover {{
        background-color: {c.BG_HOVER};
        border-color: {c.BORDER_STRONG};
    }}
    QDialog#dialog QDialogButtonBox QPushButton:default {{
        background-color: {c.ACCENT};
        color: #1a1500;
        border-color: {c.ACCENT};
        font-weight: 700;
    }}
    QDialog#dialog QDialogButtonBox QPushButton:default:hover {{
        background-color: {c.ACCENT_HOVER};
    }}

    /* Title-bar feature search and the list it opens */
    QLineEdit#titleSearch {{
        background-color: {c.BG_OVERLAY};
        color: {c.TEXT_PRIMARY};
        border: 1px solid {c.BORDER_SUBTLE};
        border-radius: {s.RADIUS_SM}px;
        padding: 0px 10px;
        font-size: {f.SIZE_SM}pt;
        selection-background-color: {c.ACCENT_MUTED};
    }}
    QLineEdit#titleSearch:focus {{
        border-color: {c.ACCENT};
    }}
    QFrame#searchPopup {{
        background-color: {c.BG_RAISED};
        border: 1px solid {c.BORDER_STRONG};
        border-radius: {s.RADIUS_SM}px;
    }}
    QLabel#searchHeading {{
        color: {c.ACCENT};
        font-size: {f.SIZE_XS}pt;
        font-weight: 600;
        padding: 8px 12px 4px 12px;
        background: transparent;
    }}
    QLabel#searchEmpty {{
        color: {c.TEXT_TERTIARY};
        font-size: {f.SIZE_SM}pt;
        padding: 10px 12px;
        background: transparent;
    }}

    /* Text input field (Discord token / channel) */
    QLineEdit#textField {{
        background-color: {c.BG_OVERLAY};
        color: {c.TEXT_PRIMARY};
        border: 1px solid {c.BORDER_SUBTLE};
        border-radius: {s.RADIUS_SM}px;
        padding: 6px 10px;
        font-size: {f.SIZE_SM}pt;
        min-height: 28px;
        selection-background-color: {c.ACCENT_MUTED};
    }}
    QLineEdit#textField:focus {{
        border-color: {c.ACCENT};
    }}

    /* Combo box (profile / theme selectors) */
    QComboBox#combo {{
        background-color: {c.BG_OVERLAY};
        color: {c.TEXT_PRIMARY};
        border: 1px solid {c.BORDER_SUBTLE};
        border-radius: {s.RADIUS_SM}px;
        padding: 6px 12px;
        font-size: {f.SIZE_SM}pt;
        min-height: 30px;
        min-width: 150px;
    }}
    QComboBox#combo:hover {{
        border-color: {c.BORDER_STRONG};
    }}
    QComboBox#combo:focus {{
        border-color: {c.ACCENT};
    }}
    QComboBox#combo::drop-down {{
        border: none;
        width: 28px;
        subcontrol-origin: padding;
        subcontrol-position: top right;
    }}
    /* The default Qt chevron rendered in this dark theme was barely
       visible (~10% contrast against BG_OVERLAY). Replace it with a CSS
       triangle in TEXT_PRIMARY so the dropdown affordance reads clearly.
       Single triangle = no border-meet artifact, so this is safe in Qt's
       QSS unlike the matched-corner triangles we tried for the spinbox. */
    QComboBox#combo::down-arrow {{
        width: 0;
        height: 0;
        border-left: 5px solid transparent;
        border-right: 5px solid transparent;
        border-top: 6px solid {c.TEXT_PRIMARY};
        margin-right: 10px;
    }}
    QComboBox#combo::down-arrow:hover {{
        border-top-color: {c.ACCENT};
    }}
    QComboBox#combo QAbstractItemView {{
        background-color: {c.BG_OVERLAY};
        color: {c.TEXT_PRIMARY};
        border: 1px solid {c.BORDER_STRONG};
        border-radius: {s.RADIUS_SM}px;
        selection-background-color: {c.ACCENT_MUTED};
        outline: none;
        padding: 4px;
    }}
    /* Drop-down items: paint hovered + selected ourselves so Qt's default
       Windows "current item" red/orange highlight never shows through. */
    QComboBox#combo QAbstractItemView::item {{
        background-color: transparent;
        color: {c.TEXT_PRIMARY};
        padding: 6px 10px;
        border: none;
        border-radius: {s.RADIUS_SM}px;
    }}
    QComboBox#combo QAbstractItemView::item:hover {{
        background-color: {c.BG_HOVER};
        color: {c.TEXT_PRIMARY};
    }}
    QComboBox#combo QAbstractItemView::item:selected {{
        background-color: {c.ACCENT_MUTED};
        color: {c.TEXT_PRIMARY};
    }}

    /* QCheckBox: themed indicator (the native Windows control reads as
       red / orange on a dark surface, which clashes with the rest of
       the UI). Renders as a 16 px square with a 1 px subtle border;
       checked state fills with the accent yellow and shows a small dot
       since we can't easily draw a tick mark via QSS. */
    QCheckBox {{
        color: {c.TEXT_PRIMARY};
        spacing: 8px;
    }}
    QCheckBox::indicator {{
        width: 16px;
        height: 16px;
        border: 1px solid {c.BORDER_STRONG};
        border-radius: {s.RADIUS_SM}px;
        background-color: {c.BG_OVERLAY};
    }}
    QCheckBox::indicator:hover {{
        border-color: {c.ACCENT_MUTED};
    }}
    QCheckBox::indicator:checked {{
        background-color: {c.ACCENT};
        border-color: {c.ACCENT};
    }}
    QCheckBox::indicator:checked:hover {{
        background-color: {c.ACCENT_HOVER};
        border-color: {c.ACCENT_HOVER};
    }}
    QCheckBox::indicator:disabled {{
        background-color: {c.BG_HOVER};
        border-color: {c.BORDER_SUBTLE};
    }}

    /* Horizontal slider (audio volume) */
    QSlider#slider {{
        min-height: 24px;
    }}
    QSlider#slider::groove:horizontal {{
        background-color: {c.BG_HOVER};
        height: 4px;
        border-radius: 2px;
    }}
    QSlider#slider::sub-page:horizontal {{
        background-color: {c.ACCENT};
        height: 4px;
        border-radius: 2px;
    }}
    QSlider#slider::handle:horizontal {{
        background-color: {c.TEXT_PRIMARY};
        width: 14px;
        height: 14px;
        margin: -6px 0;
        border-radius: 7px;
    }}
    QSlider#slider::handle:horizontal:hover {{
        background-color: {c.ACCENT};
    }}

    /* Scrollbars - thin, minimal, no step arrows. A rounded translucent
       thumb floating on a transparent track that brightens on hover.
       Applied app-wide: pages, log view, combo popups, lists. */
    QScrollBar:vertical {{
        background: transparent;
        width: 10px;
        margin: 0px;
    }}
    QScrollBar::handle:vertical {{
        background: rgba(255, 255, 255, 0.14);
        min-height: 36px;
        border-radius: 5px;
    }}
    QScrollBar::handle:vertical:hover {{
        background: rgba(255, 255, 255, 0.28);
    }}
    QScrollBar::handle:vertical:pressed {{
        background: rgba(255, 255, 255, 0.40);
    }}
    QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
        height: 0px;
        width: 0px;
        background: none;
        border: none;
    }}
    QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{
        background: transparent;
    }}

    QScrollBar:horizontal {{
        background: transparent;
        height: 10px;
        margin: 0px;
    }}
    QScrollBar::handle:horizontal {{
        background: rgba(255, 255, 255, 0.14);
        min-width: 36px;
        border-radius: 5px;
    }}
    QScrollBar::handle:horizontal:hover {{
        background: rgba(255, 255, 255, 0.28);
    }}
    QScrollBar::handle:horizontal:pressed {{
        background: rgba(255, 255, 255, 0.40);
    }}
    QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{
        height: 0px;
        width: 0px;
        background: none;
        border: none;
    }}
    QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal {{
        background: transparent;
    }}

    QAbstractScrollArea::corner {{
        background: transparent;
        border: none;
    }}
    """
