# SPDX-License-Identifier: GPL-3.0-or-later
"""Main UI shell: sidebar navigation + page stack."""

from PySide6.QtCore import (
    Property, QEasingCurve, QPropertyAnimation, Qt, QTimer, Signal,
)
from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import (
    QFrame, QHBoxLayout, QLabel, QPushButton, QScrollArea, QStyle,
    QStyleOptionButton, QStylePainter, QVBoxLayout, QWidget,
)

from .dashboard_page import DashboardPage
from .help_page import HelpPage
from .logs_page import LogsPage
from .luxcavation_page import LuxcavationPage
from .mirror_dungeon_page import MirrorDungeonPage
from .scheduler_page import SchedulerPage
from .settings_page import SettingsPage
from .settings import load_settings, save_settings
from .splash import _load_app_icon, _read_version
from .stats_page import StatsPage
from . import seasonal
from .theme import Colors, Motion, Sizing
from .voxel import draw_pixel_text, pixel_text_width
from .widgets import AnimatedStack, ElidedLabel, PageBackdrop


# Sidebar nav: (key, label).
_NAV_ITEMS = (
    ("dashboard",      "Dashboard"),
    ("mirror_dungeon", "Mirror Dungeon"),
    ("luxcavation",    "Luxcavation"),
    ("scheduler",      "Scheduler"),
    ("stats",          "Stats"),
    ("logs",           "Logs"),
    ("settings",       "Settings"),
    ("help",           "Help"),
)


# The rail the sidebar closes to: the logo, the toggle and the tags fit it.
_RAIL_WIDTH = 56
# Two-letter pixel tags: beside the label when open, the whole row when closed.
_TAGS = {
    "dashboard": "DB", "mirror_dungeon": "MD", "luxcavation": "LX",
    "scheduler": "SC", "stats": "ST", "logs": "LG", "settings": "SE",
    "help": "HP",
}
_TAG_PIXEL = 2
_TAG_X = 16                       # tag left when open, past the caret


class _SidebarItem(QPushButton):
    """Nav row: a pixel tag, the label, and for the selected row a stepped
    caret that slides in from the left the way a menu cursor does (the
    legacy skin keeps its v2 accent edge bar and shows no tag). On the rail
    only the tag is painted, in the accent when selected; the label stays
    the button text for tooltips and tests."""

    _UNIT = 3                      # caret pixel size
    _STEPS = (1, 2, 3, 2, 1)       # blocks per row, giving a right-pointing wedge

    def __init__(self, key: str, label: str,
                 parent: QWidget | None = None):
        super().__init__(label, parent)
        self.key = key
        self.tag = _TAGS.get(key, key[:2].upper())
        self.setObjectName("sidebarItem")
        self.setCheckable(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFlat(True)
        self._grow = 0.0
        self._caret = False
        self._rail = False
        self.refresh_theme()
        self._anim = QPropertyAnimation(self, b"caretGrow", self)
        self._anim.setDuration(Motion.QUICK)
        self._anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self.toggled.connect(self._on_toggled)

    def refresh_theme(self):
        from .skins import is_voxel
        self._caret = is_voxel()
        self.update()

    def _on_toggled(self, on: bool):
        self._anim.stop()
        self._anim.setStartValue(self._grow)
        self._anim.setEndValue(1.0 if on else 0.0)
        self._anim.start()

    def _get_grow(self):
        return self._grow

    def _set_grow(self, v):
        self._grow = v
        self.update()

    caretGrow = Property(float, _get_grow, _set_grow)

    def set_rail(self, on: bool):
        """Closed sidebar: the tag alone, the label as the tooltip."""
        self._rail = bool(on)
        self.setToolTip(self.text() if self._rail else "")
        self.update()

    def paintEvent(self, event):
        opt = QStyleOptionButton()
        self.initStyleOption(opt)
        if self._rail:
            opt.text = ""
        sp = QStylePainter(self)
        sp.drawControl(QStyle.ControlElement.CE_PushButton, opt)
        sp.end()
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, False)
        if self._rail or self._caret:
            tw = pixel_text_width(self.tag, _TAG_PIXEL)
            th = 7 * _TAG_PIXEL
            x = (self.width() - tw) // 2 if self._rail else _TAG_X
            tint = Colors.ACCENT if self.isChecked() else Colors.TEXT_TERTIARY
            draw_pixel_text(p, x, (self.height() - th) // 2, self.tag,
                            _TAG_PIXEL, color=tint)
        if self._caret and self._grow > 0.0 and not self._rail:
            u = self._UNIT                 # on the rail the tag alone marks the row
            h = len(self._STEPS) * u
            y = (self.height() - h) // 2
            # Slides in from the left and fades up together.
            x = 3 - int(round((1.0 - self._grow) * 7))
            col = QColor(Colors.ACCENT)
            col.setAlpha(int(255 * self._grow))
            for i, n in enumerate(self._STEPS):
                p.fillRect(x, y + i * u, n * u, u, col)
        p.end()


class _SidebarToggle(QPushButton):
    """Opens and closes the sidebar: a pixel double chevron pointing the way
    the sidebar will move."""

    _UNIT = 2
    _STEPS = (1, 2, 3, 2, 1)

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("sidebarToggle")
        self.setFixedSize(26, 22)
        self.setFlat(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._open = True
        self.set_open(True)

    def set_open(self, on: bool):
        self._open = bool(on)
        self.setToolTip("Close the sidebar" if self._open else "Open the sidebar")
        self.update()

    def refresh_theme(self):
        self.update()

    def paintEvent(self, event):
        opt = QStyleOptionButton()
        self.initStyleOption(opt)
        sp = QStylePainter(self)
        sp.drawControl(QStyle.ControlElement.CE_PushButton, opt)
        sp.end()
        u = self._UNIT
        wedge, gap = 3 * u, 2 * u
        total = 2 * wedge + gap
        x0 = (self.width() - total) // 2
        y0 = (self.height() - len(self._STEPS) * u) // 2
        col = QColor(Colors.TEXT_SECONDARY)
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, False)
        for k in range(2):
            x = x0 + k * (wedge + gap)
            for i, n in enumerate(self._STEPS):
                # Open: wedges point left (the way out); closed: right.
                left = x + (wedge - n * u) if self._open else x
                p.fillRect(left, y0 + i * u, n * u, u, col)
        p.end()


class MainUI(QWidget):

    # Re-emitted from the Mirror Dungeon page so the launcher can wire
    # them to AutomationController without crawling the tree.
    start_requested = Signal()
    stop_requested = Signal()

    sidebar_width_changed = Signal(int)

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("root")
        self._items: dict[str, _SidebarItem] = {}
        self._sidebar_open = True
        self._pages: dict[str, QWidget] = {}
        self._build()

    def _build(self):
        root = QHBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        root.addWidget(self._build_sidebar())

        # The title bar floats as a full-width raised overlay
        # (main_window._position_titlebar), so the inset has to clear its FULL
        # height, not a token gap: at 8px the page header's action buttons were
        # drawn under the minimise/maximise/close controls, and because the bar
        # is raised it also swallowed clicks on the top of those buttons. The
        # sidebar is a sibling and still runs full-height.
        content_wrap = PageBackdrop(self)
        content_wrap.setObjectName("contentInset")
        content_wrap.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        # The inset's themed gradient lives in global QSS (#contentInset).
        cw = QVBoxLayout(content_wrap)
        cw.setContentsMargins(0, Sizing.TITLEBAR_HEIGHT, 0, 0)
        cw.setSpacing(0)
        cw.addWidget(self._build_content())
        root.addWidget(content_wrap, stretch=1)

        self._select("dashboard")
        self._side_anim = QPropertyAnimation(self, b"sidebarWidth", self)
        self._side_anim.setDuration(Motion.NORMAL)
        self._side_anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self.set_sidebar_open(
            not bool(load_settings().get("sidebar_collapsed", False)),
            animate=False, persist=False)

        # Deferred so it runs after the window is shown and allWidgets()
        # is fully populated.
        QTimer.singleShot(0, self._apply_help_text)

    def _apply_help_text(self):
        """Show/hide UI helper text per the saved setting."""
        try:
            from .help_text import apply as apply_help
            apply_help()
        except Exception:
            pass

    # --- Sidebar ----------------------------------------------------
    def _build_brand(self):
        """Sidebar brand for the active skin: the animated voxel bee with the
        pixel wordmark, or the v2 icon + text labels."""
        host = self._brand_host
        row = self._brand_row
        while row.count():                       # clear (a skin switch rebuilds)
            item = row.takeAt(0)
            w = item.widget()
            if w is not None:
                w.setParent(None)
                w.deleteLater()
            elif item.layout() is not None:
                lay = item.layout()
                while lay.count():
                    sub = lay.takeAt(0).widget()
                    if sub is not None:
                        sub.setParent(None)
                        sub.deleteLater()
                lay.setParent(None)

        voxel = False
        try:
            from .skins import is_voxel
            voxel = is_voxel()
        except Exception:
            voxel = False

        if voxel:
            from .voxel import PixelWordmark, VoxelLogo
            row.addWidget(VoxelLogo(34, host),
                          alignment=Qt.AlignmentFlag.AlignVCenter)
            text_col = QVBoxLayout()
            text_col.setContentsMargins(0, 0, 0, 0)
            text_col.setSpacing(Sizing.SPACE_XXS)
            text_col.addWidget(PixelWordmark(3, host))
            tagline = ElidedLabel("Limbus automation", host)
            tagline.setObjectName("sidebarTagline")
            text_col.addWidget(tagline)
            row.addLayout(text_col)
            row.addStretch(1)
            return

        logo_pix = _load_app_icon(30)
        if logo_pix is not None:
            logo = QLabel(host)
            logo.setPixmap(logo_pix)
            logo.setFixedSize(30, 30)
            logo.setScaledContents(True)
            row.addWidget(logo, alignment=Qt.AlignmentFlag.AlignVCenter)
        brand_text = QVBoxLayout()
        brand_text.setContentsMargins(0, 0, 0, 0)
        brand_text.setSpacing(0)
        first, second = seasonal.brand()
        title = QLabel(first + second, host)
        if seasonal.is_halloween():
            title.setTextFormat(Qt.TextFormat.RichText)
            title.setText(
                f"<span style='color:{seasonal.RED}'>{first}</span>"
                f"<span style='color:{seasonal.BONE}'>{second}</span>")
        title.setObjectName("sidebarBrand")
        brand_text.addWidget(title)
        tagline = ElidedLabel("Limbus automation", host)
        tagline.setObjectName("sidebarTagline")
        brand_text.addWidget(tagline)
        row.addLayout(brand_text)
        row.addStretch(1)

    def rebuild_brand(self):
        """Skin switch hook (skins._rebrand_running_app)."""
        if hasattr(self, "_brand_row"):
            self._build_brand()
            self._apply_brand_rail(not self._sidebar_open)

    def _build_sidebar(self) -> QWidget:
        sidebar = QFrame(self)
        sidebar.setObjectName("sidebar")
        sidebar.setFixedWidth(Sizing.SIDEBAR_WIDTH)
        self._sidebar = sidebar
        col = QVBoxLayout(sidebar)
        col.setContentsMargins(0, 0, 0, 0)
        col.setSpacing(0)

        # The brand on a header band, the toggle under it.
        band = QFrame(sidebar)
        band.setObjectName("sidebarBrandBand")
        band_col = QVBoxLayout(band)
        band_col.setContentsMargins(Sizing.SPACE_MD, Sizing.SPACE_XXL,
                                    Sizing.SPACE_MD, Sizing.SPACE_SM)
        band_col.setSpacing(Sizing.SPACE_SM)
        self._brand_host = QWidget(band)
        self._brand_row = QHBoxLayout(self._brand_host)
        self._brand_row.setContentsMargins(0, 0, 0, 0)
        self._brand_row.setSpacing(Sizing.SPACE_SM)
        self._build_brand()
        band_col.addWidget(self._brand_host)
        self._toggle_row = QHBoxLayout()
        self._toggle_row.setContentsMargins(0, 0, 0, 0)
        self._sidebar_toggle = _SidebarToggle(band)
        self._sidebar_toggle.clicked.connect(self.toggle_sidebar)
        self._toggle_row.addStretch(1)
        self._toggle_row.addWidget(self._sidebar_toggle)
        self._toggle_row.addStretch(0)
        band_col.addLayout(self._toggle_row)
        col.addWidget(band)

        nav = QWidget(sidebar)
        nav_col = QVBoxLayout(nav)
        nav_col.setContentsMargins(Sizing.SPACE_MD, Sizing.SPACE_LG,
                                   Sizing.SPACE_MD, Sizing.SPACE_LG)
        nav_col.setSpacing(Sizing.SPACE_XXS)
        for key, label in _NAV_ITEMS:
            if key == "settings":
                seam = QFrame(nav)
                seam.setObjectName("sidebarSeam")
                seam.setFixedHeight(1)
                nav_col.addSpacing(Sizing.SPACE_SM)
                nav_col.addWidget(seam)
                nav_col.addSpacing(Sizing.SPACE_SM)
            btn = _SidebarItem(key, seasonal.title(label), nav)
            btn.clicked.connect(lambda _c=False, k=key: self._select(k))
            nav_col.addWidget(btn)
            self._items[key] = btn
        nav_col.addStretch(1)
        col.addWidget(nav, 1)

        foot = QFrame(sidebar)
        foot.setObjectName("sidebarFoot")
        foot_row = QHBoxLayout(foot)
        foot_row.setContentsMargins(Sizing.SPACE_MD, Sizing.SPACE_SM,
                                    Sizing.SPACE_MD, Sizing.SPACE_SM)
        self._version_lbl = QLabel(f"v{_read_version().lstrip('v')}", foot)
        self._version_lbl.setObjectName("sidebarVersion")
        foot_row.addWidget(self._version_lbl)
        foot_row.addStretch(1)
        col.addWidget(foot)
        return sidebar

    # --- Sidebar open / closed ----------------------------------------
    def _get_sidebar_width(self):
        return self._sidebar.width()

    def _set_sidebar_width(self, w):
        self._sidebar.setFixedWidth(int(w))
        self.sidebar_width_changed.emit(int(w))

    sidebarWidth = Property(int, _get_sidebar_width, _set_sidebar_width)

    def sidebar_width(self) -> int:
        return self._sidebar.width()

    def is_sidebar_open(self) -> bool:
        return self._sidebar_open

    def toggle_sidebar(self):
        self.set_sidebar_open(not self._sidebar_open)

    def set_sidebar_open(self, open_: bool, animate: bool = True,
                         persist: bool = True):
        """Open: brand, labels and version. Closed: the 56 px rail of pixel
        tags, labels as tooltips. The choice is kept across starts."""
        self._sidebar_open = bool(open_)
        rail = not self._sidebar_open
        for btn in self._items.values():
            btn.set_rail(rail)
        self._apply_brand_rail(rail)
        self._sidebar_toggle.set_open(self._sidebar_open)
        self._toggle_row.setStretch(2, 1 if rail else 0)    # centred on the rail
        self._version_lbl.setVisible(not rail)
        target = _RAIL_WIDTH if rail else Sizing.SIDEBAR_WIDTH
        self._side_anim.stop()
        if animate:
            self._side_anim.setStartValue(self._sidebar.width())
            self._side_anim.setEndValue(target)
            self._side_anim.start()
        else:
            self._set_sidebar_width(target)
        if persist:
            save_settings({"sidebar_collapsed": rail})

    def _apply_brand_rail(self, rail: bool):
        """On the rail only the logo (the first widget of the brand row) stays."""
        first = [True]

        def walk(layout):
            for i in range(layout.count()):
                item = layout.itemAt(i)
                w, sub = item.widget(), item.layout()
                if w is not None:
                    if first[0]:
                        first[0] = False
                        continue
                    w.setVisible(not rail)
                elif sub is not None:
                    walk(sub)
        walk(self._brand_row)

    # --- Content stack ---------------------------------------------
    def _build_content(self) -> QWidget:
        self._stack = AnimatedStack(self)
        self._stack.setObjectName("contentStack")
        # Opaque background so page switches repaint cleanly; without it
        # the previous page's pixels linger.
        self._stack.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)

        dashboard = DashboardPage(self._stack)
        dashboard.start_requested.connect(
            lambda: (self._select("mirror_dungeon"),
                     self.start_requested.emit())
        )
        dashboard.view_history_requested.connect(
            lambda: self._select("stats")
        )
        self._pages["dashboard"] = dashboard

        mirror = MirrorDungeonPage(self._stack)
        mirror.start_requested.connect(self.start_requested.emit)
        mirror.stop_requested.connect(self.stop_requested.emit)
        mirror.open_stk_settings.connect(self._reveal_stk_settings)
        self._pages["mirror_dungeon"] = mirror

        lux = LuxcavationPage(self._stack)
        lux.stop_requested.connect(self.stop_requested.emit)
        self._pages["luxcavation"] = lux

        self._pages["scheduler"] = SchedulerPage(self._stack)
        self._pages["stats"] = StatsPage(self._stack)
        self._pages["logs"] = LogsPage(self._stack)
        settings_page = SettingsPage(self._stack)
        settings_page.config_loaded.connect(self._reload_after_config)
        self._pages["settings"] = settings_page
        self._pages["help"] = HelpPage(self._stack)

        # _pages holds the real page (for signals); _wrappers wraps each
        # in a scroll area so taller-than-window content stays reachable.
        self._wrappers: dict[str, QWidget] = {}
        for key, _label in _NAV_ITEMS:
            wrapper = self._wrap_scroll(self._pages[key])
            self._wrappers[key] = wrapper
            self._stack.addWidget(wrapper)

        return self._stack

    def _reload_after_config(self):
        """Re-apply theme + per-page state so a loaded config takes effect."""
        try:
            from .themes import reapply_theme
            reapply_theme()
        except Exception:
            pass
        for page in self._pages.values():
            restore = getattr(page, "_restore_state", None)
            if callable(restore):
                try:
                    restore()
                except Exception:
                    pass
        self._apply_help_text()

    def _wrap_scroll(self, page: QWidget) -> QWidget:
        # Pages that scroll internally opt out to avoid a double scroll.
        if getattr(page, "manages_scroll", False):
            return page
        sa = QScrollArea(self._stack)
        sa.setObjectName("shellScroll")
        sa.setWidgetResizable(True)
        sa.setFrameShape(QScrollArea.Shape.NoFrame)
        # AlwaysOff makes the scroll area adopt the page's full minimum width,
        # which is how a wide page (settings) pushed the whole window's
        # minimum past 2000px and drew its right-hand column off-screen with
        # no way to reach it.
        sa.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAsNeeded
        )
        sa.setWidget(page)
        return sa

    # --- Navigation -------------------------------------------------
    def _select(self, key: str):
        if key not in self._pages:
            return
        for k, btn in self._items.items():
            btn.setChecked(k == key)
        target = self._wrappers[key]
        if self._stack.currentWidget() is target:
            return
        self._stack.setCurrentWidget(target)

    def _reveal_stk_settings(self, run=None):
        """Switch to Settings and scroll the custom run card near the top,
        showing `run` when one is named. Deferred past the page transition
        so the scroll area has final geometry (the switch animates and grabs
        page pixmaps for ~Motion.NORMAL ms)."""
        self._select("settings")
        page = self._pages.get("settings")
        wrapper = self._wrappers.get("settings")
        seg = getattr(page, "_stk_seg", None)
        if run and seg is not None and run in getattr(seg, "_buttons", {}):
            seg._buttons[run].click()
        card = getattr(page, "_stk_card", None)
        if card is None or not isinstance(wrapper, QScrollArea):
            return

        def _scroll():
            y = card.mapTo(page, card.rect().topLeft()).y()
            wrapper.verticalScrollBar().setValue(max(0, y - Sizing.SPACE_XL))

        QTimer.singleShot(Motion.NORMAL, _scroll)

    # --- Public hooks ----------------------------------------------
    def page(self, key: str) -> QWidget | None:
        return self._pages.get(key)

    def navigate_to(self, key: str):
        self._select(key)
