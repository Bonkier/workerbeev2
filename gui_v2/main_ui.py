# SPDX-License-Identifier: GPL-3.0-or-later
"""Main UI shell: sidebar navigation + page stack."""

from PySide6.QtCore import (
    Property, QEasingCurve, QPropertyAnimation, Qt, QTimer, Signal,
)
from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import (
    QFrame, QHBoxLayout, QLabel, QPushButton,
    QScrollArea, QVBoxLayout, QWidget,
)

from .dashboard_page import DashboardPage
from .help_page import HelpPage
from .logs_page import LogsPage
from .luxcavation_page import LuxcavationPage
from .mirror_dungeon_page import MirrorDungeonPage
from .scheduler_page import SchedulerPage
from .settings_page import SettingsPage
from .splash import _load_app_icon, _read_version
from .stats_page import StatsPage
from . import seasonal
from .theme import Colors, Motion, Sizing
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


class _SidebarItem(QPushButton):
    """Text-only nav row. The selected row is marked with a stepped caret that
    slides in from the left, the way a menu cursor does - the legacy skin keeps
    its v2 accent edge bar instead."""

    _UNIT = 3                      # caret pixel size
    _STEPS = (1, 2, 3, 2, 1)       # blocks per row, giving a right-pointing wedge

    def __init__(self, key: str, label: str,
                 parent: QWidget | None = None):
        super().__init__(label, parent)
        self.key = key
        self.setObjectName("sidebarItem")
        self.setCheckable(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFlat(True)
        self._grow = 0.0
        self._caret = False
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

    def paintEvent(self, event):
        super().paintEvent(event)
        if not self._caret or self._grow <= 0.0:
            return
        u = self._UNIT
        h = len(self._STEPS) * u
        y = (self.height() - h) // 2
        # Slides in from the left and fades up together.
        x = 3 - int(round((1.0 - self._grow) * 7))
        col = QColor(Colors.ACCENT)
        col.setAlpha(int(255 * self._grow))
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, False)
        for i, n in enumerate(self._STEPS):
            p.fillRect(x, y + i * u, n * u, u, col)
        p.end()


class MainUI(QWidget):

    # Re-emitted from the Mirror Dungeon page so the launcher can wire
    # them to AutomationController without crawling the tree.
    start_requested = Signal()
    stop_requested = Signal()

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("root")
        self._items: dict[str, _SidebarItem] = {}
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

    def _build_sidebar(self) -> QWidget:
        sidebar = QFrame(self)
        sidebar.setObjectName("sidebar")
        sidebar.setFixedWidth(Sizing.SIDEBAR_WIDTH)
        col = QVBoxLayout(sidebar)
        col.setContentsMargins(
            Sizing.SPACE_MD, Sizing.SPACE_XXL,
            Sizing.SPACE_MD, Sizing.SPACE_LG,
        )
        col.setSpacing(Sizing.SPACE_XXS)

        self._brand_host = QWidget(sidebar)
        self._brand_row = QHBoxLayout(self._brand_host)
        self._brand_row.setContentsMargins(0, 0, 0, 0)
        self._brand_row.setSpacing(Sizing.SPACE_SM)
        self._build_brand()
        col.addWidget(self._brand_host)

        col.addSpacing(Sizing.SPACE_LG)

        for key, label in _NAV_ITEMS:
            btn = _SidebarItem(key, seasonal.title(label), sidebar)
            btn.clicked.connect(lambda _c=False, k=key: self._select(k))
            col.addWidget(btn)
            self._items[key] = btn

        col.addStretch(1)

        version_lbl = QLabel(f"v{_read_version().lstrip('v')}", sidebar)
        version_lbl.setObjectName("sidebarVersion")
        col.addWidget(version_lbl)

        return sidebar

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
