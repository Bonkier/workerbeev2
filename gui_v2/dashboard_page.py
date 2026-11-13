# SPDX-License-Identifier: GPL-3.0-or-later
"""Dashboard: the landing page after the splash. Your record as a hero
line and headline tiles, and the newest runs in full."""

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QHBoxLayout, QLabel, QVBoxLayout, QWidget

from . import settings as app_settings
from . import stats
from .stats_page import _HistoryRow
from .copy import DASHBOARD_ACTIVITY_EMPTY
from .theme import Sizing
from .widgets import (
    Card, GhostButton, LinkButton, PageHeader, PrimaryButton, StatTiles,
    _title_label,
)

_MAX_ACTIVITY_ROWS = 5
_KEY_DEFAULTS = {"pause": "F9", "stop": "F2"}


class _KeyCap(QLabel):
    """A key the way it is printed on the cap."""

    def __init__(self, text: str, parent=None):
        super().__init__(text, parent, objectName="keyCap")
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)


class DashboardPage(QWidget):

    start_requested = Signal()
    view_history_requested = Signal()

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("root")
        self._build()
        self.refresh_stats()

    def _build(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(
            Sizing.SPACE_XXL, Sizing.SPACE_XL,
            Sizing.SPACE_XXL, Sizing.SPACE_XL,
        )
        outer.setSpacing(Sizing.SPACE_LG)

        header = PageHeader("Dashboard", self)
        refresh = GhostButton("Refresh", self)
        refresh.clicked.connect(self.refresh_stats)
        header.add_action(refresh)
        outer.addWidget(header)

        outer.addWidget(self._build_hero())
        outer.addWidget(self._build_stats_section())
        # Panels keep their natural height and the leftover goes to a trailing
        # spacer; the page backdrop's grid makes the empty area read as
        # intentional where a stretched panel looked broken.
        outer.addWidget(self._build_activity_section())
        outer.addStretch(1)

    # --- Hero (the record in a line + start CTA) -----------------------
    def _build_hero(self) -> QWidget:
        card = Card(parent=self, padding=Sizing.SPACE_XL)
        card.body.setSpacing(Sizing.SPACE_SM)

        title = _title_label("Ready to grind", card, pixel=4, section=False)
        if isinstance(title, QLabel):
            title.setObjectName("heroTitle")
        card.body.addWidget(title)

        self._hero_sub = QLabel("No runs yet", card, objectName="heroSubtitle")
        self._hero_sub.setWordWrap(True)
        card.body.addWidget(self._hero_sub)

        card.body.addSpacing(Sizing.SPACE_MD)

        cta_row = QHBoxLayout()
        cta_row.setSpacing(Sizing.SPACE_LG)
        from . import seasonal
        start_btn = PrimaryButton(
            seasonal.title("Start Mirror Dungeon"), card)
        start_btn.clicked.connect(self.start_requested.emit)
        cta_row.addWidget(start_btn)

        # The two keys a running macro answers to, read from the saved
        # shortcuts so a rebind shows here too.
        self._key_caps = {}
        for key, word in (("pause", "pause"), ("stop", "stop")):
            cap = _KeyCap(_KEY_DEFAULTS[key], card)
            self._key_caps[key] = cap
            cta_row.addWidget(cap, 0, Qt.AlignmentFlag.AlignVCenter)
            cta_row.addWidget(QLabel(word, card, objectName="heroHint"),
                              0, Qt.AlignmentFlag.AlignVCenter)
        cta_row.addStretch(1)
        card.body.addLayout(cta_row)
        return card

    def _refresh_keys(self):
        try:
            saved = (app_settings.load_section("app_settings") or {}).get(
                "shortcuts") or {}
        except Exception:
            saved = {}
        for key, cap in self._key_caps.items():
            cap.setText(str(saved.get(key) or _KEY_DEFAULTS[key]))

    # --- Stats: the headline tiles ----------------------------------
    def _build_stats_section(self) -> QWidget:
        card = Card("STATISTICS", self)
        self._tiles = StatTiles([
            ("Total runs", "0"),
            ("Dungeons cleared", "0"),
            ("Success rate", "0%"),
            ("Average run", "0s"),
            ("Total run time", "0h 0m", True),
        ], parent=card)
        card.body.addWidget(self._tiles)
        return card

    # --- Recent activity feed --------------------------------------
    def _build_activity_section(self) -> QWidget:
        view_all = LinkButton("View all", self)
        view_all.clicked.connect(self.view_history_requested.emit)
        card = Card("RECENT ACTIVITY", self, trailing=view_all)
        self._activity_body = QVBoxLayout()
        self._activity_body.setContentsMargins(0, 0, 0, 0)
        self._activity_body.setSpacing(Sizing.SPACE_XS)
        self._activity_empty = QLabel(
            DASHBOARD_ACTIVITY_EMPTY,
            card, objectName="inlineHint",
        )
        self._activity_body.addWidget(self._activity_empty)
        card.body.addLayout(self._activity_body)
        return card

    # --- live refresh ----------------------------------------------
    def refresh_stats(self):
        agg = stats.aggregate()
        runs = stats.load_runs()
        self._tiles.set_value("Total runs", str(agg["total"]))
        self._tiles.set_value("Dungeons cleared", str(agg["mirrors_cleared"]))
        self._tiles.set_value("Success rate", "%.0f%%" % agg["success_rate"])
        self._tiles.set_value("Average run", stats.fmt_duration(agg["avg_duration"]))
        self._tiles.set_value("Total run time", stats.fmt_total(agg["total_time"]))

        if runs:
            parts = ["%d completed" % agg["completed"],
                     "%.0f%% success" % agg["success_rate"],
                     "%s grinding" % stats.fmt_total(agg["total_time"])]
            last = float(runs[-1].get("ts", 0) or 0)
            if last:
                parts.append("last run %s" % stats.fmt_ago(last))
            self._hero_sub.setText("  ·  ".join(parts))
        else:
            self._hero_sub.setText(
                "No runs yet. Set one up on the Mirror Dungeon page and the "
                "record fills in here.")
        self._refresh_keys()
        self._rebuild_activity(runs)

    def _rebuild_activity(self, runs):
        while self._activity_body.count():
            item = self._activity_body.takeAt(0)
            w = item.widget()
            if w is not None:
                w.setParent(None)
                w.deleteLater()

        newest = list(reversed(runs))[:_MAX_ACTIVITY_ROWS]
        if not newest:
            self._activity_empty = QLabel(
                DASHBOARD_ACTIVITY_EMPTY,
                self, objectName="inlineHint",
            )
            self._activity_body.addWidget(self._activity_empty)
            return
        for r in newest:
            self._activity_body.addWidget(_HistoryRow(r, self))

    def showEvent(self, event):
        super().showEvent(event)
        self.refresh_stats()
