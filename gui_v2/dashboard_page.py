# SPDX-License-Identifier: GPL-3.0-or-later
"""Dashboard: landing surface after the splash."""

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QHBoxLayout, QLabel, QVBoxLayout, QWidget,
)

from . import stats
from .stats_page import _HistoryRow
from .copy import DASHBOARD_ACTIVITY_EMPTY
from .theme import Sizing
from .widgets import (
    Card, GhostButton, LinkButton, PageHeader, PrimaryButton, StatTiles,
)

_MAX_ACTIVITY_ROWS = 5


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
        outer.addWidget(self._build_activity_section())
        outer.addStretch(1)

    # --- Hero (last run + start CTA) -------------------------------
    def _build_hero(self) -> QWidget:
        card = Card(parent=self, padding=Sizing.SPACE_XL)
        card.body.setSpacing(Sizing.SPACE_XS)

        title = QLabel("Ready to grind", card)
        title.setObjectName("heroTitle")
        card.body.addWidget(title)

        self._hero_sub = QLabel("No runs yet", card)
        self._hero_sub.setObjectName("heroSubtitle")
        card.body.addWidget(self._hero_sub)

        card.body.addSpacing(Sizing.SPACE_MD)

        cta_row = QHBoxLayout()
        cta_row.setSpacing(Sizing.SPACE_MD)
        start_btn = PrimaryButton("Start Mirror Dungeon", card)
        start_btn.clicked.connect(self.start_requested.emit)
        cta_row.addWidget(start_btn)

        hint = QLabel("Press F9 to pause", card)
        hint.setObjectName("heroHint")
        hint.setAlignment(
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter
        )
        cta_row.addWidget(hint)
        cta_row.addStretch(1)
        card.body.addLayout(cta_row)

        return card

    # --- Stats strip -----------------------------------------------
    def _build_stats_section(self) -> QWidget:
        card = Card("STATISTICS", self)
        self._tiles = StatTiles([
            ("Total runs", "0"),
            ("Success rate", "0%"),
            ("Total run time", "0h 0m", True),
            ("Mirrors cleared", "0"),
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
        self._tiles.set_value("Total runs", str(agg["total"]))
        self._tiles.set_value("Success rate", f"{agg['success_rate']:.0f}%")
        self._tiles.set_value("Total run time", stats.fmt_total(agg["total_time"]))
        self._tiles.set_value("Mirrors cleared", str(agg["mirrors_cleared"]))

        if agg["total"]:
            self._hero_sub.setText(
                f"{agg['completed']} completed  ·  "
                f"{agg['success_rate']:.0f}% success  ·  "
                f"{stats.fmt_total(agg['total_time'])} grinding")
        else:
            self._hero_sub.setText("No runs yet")

        self._rebuild_activity()

    def _rebuild_activity(self):
        while self._activity_body.count():
            item = self._activity_body.takeAt(0)
            w = item.widget()
            if w is not None:
                w.deleteLater()

        runs = list(reversed(stats.load_runs()))[:_MAX_ACTIVITY_ROWS]
        if not runs:
            self._activity_empty = QLabel(
                DASHBOARD_ACTIVITY_EMPTY,
                self, objectName="inlineHint",
            )
            self._activity_body.addWidget(self._activity_empty)
            return
        for r in runs:
            self._activity_body.addWidget(_HistoryRow(r, self))

    def showEvent(self, event):
        super().showEvent(event)
        self.refresh_stats()
