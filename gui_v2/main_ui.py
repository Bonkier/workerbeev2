# SPDX-License-Identifier: GPL-3.0-or-later
"""Main UI shell: sidebar navigation + page stack."""

from PySide6.QtCore import Qt, QTimer, Signal
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
from .theme import Sizing
from .widgets import AnimatedStack


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
    """Text-only nav row; :checked shows a yellow left-edge bar."""

    def __init__(self, key: str, label: str,
                 parent: QWidget | None = None):
        super().__init__(label, parent)
        self.key = key
        self.setObjectName("sidebarItem")
        self.setCheckable(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFlat(True)


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

        # Window controls float top-right; inset so page headers clear them
        # while the sidebar runs full-height.
        content_wrap = QWidget(self)
        content_wrap.setObjectName("contentInset")
        content_wrap.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        # The inset's themed gradient lives in global QSS (#contentInset).
        cw = QVBoxLayout(content_wrap)
        cw.setContentsMargins(0, Sizing.SPACE_MD, 0, 0)
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
    def _build_sidebar(self) -> QWidget:
        sidebar = QFrame(self)
        sidebar.setObjectName("sidebar")
        sidebar.setFixedWidth(232)
        col = QVBoxLayout(sidebar)
        col.setContentsMargins(
            Sizing.SPACE_MD, Sizing.SPACE_XXL,
            Sizing.SPACE_MD, Sizing.SPACE_LG,
        )
        col.setSpacing(Sizing.SPACE_XXS)

        brand_row = QHBoxLayout()
        brand_row.setContentsMargins(0, 0, 0, 0)
        brand_row.setSpacing(Sizing.SPACE_SM)

        logo_pix = _load_app_icon(30)
        if logo_pix is not None:
            logo = QLabel(sidebar)
            logo.setPixmap(logo_pix)
            logo.setFixedSize(30, 30)
            logo.setScaledContents(True)
            brand_row.addWidget(logo, alignment=Qt.AlignmentFlag.AlignVCenter)

        brand_text = QVBoxLayout()
        brand_text.setContentsMargins(0, 0, 0, 0)
        brand_text.setSpacing(0)
        title = QLabel("WorkerBee", sidebar)
        title.setObjectName("sidebarBrand")
        brand_text.addWidget(title)
        tagline = QLabel("Limbus automation", sidebar)
        tagline.setObjectName("sidebarTagline")
        brand_text.addWidget(tagline)
        brand_row.addLayout(brand_text)
        brand_row.addStretch(1)
        col.addLayout(brand_row)

        col.addSpacing(Sizing.SPACE_LG)

        for key, label in _NAV_ITEMS:
            btn = _SidebarItem(key, label, sidebar)
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
        self._pages["mirror_dungeon"] = mirror

        lux = LuxcavationPage(self._stack)
        lux.start_exp_requested.connect(self.start_requested.emit)
        lux.start_thread_requested.connect(self.start_requested.emit)
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
        sa.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
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

    # --- Public hooks ----------------------------------------------
    def page(self, key: str) -> QWidget | None:
        return self._pages.get(key)

    def navigate_to(self, key: str):
        self._select(key)
