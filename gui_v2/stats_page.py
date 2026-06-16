# SPDX-License-Identifier: GPL-3.0-or-later
"""Stats page - run history and aggregate metrics, read from the
persistent run log (see stats.py). refresh_stats() is called by the
RunCoordinator whenever a run finishes, and on show.

Two tabs: "Runs" (overview tiles + per-run history, each report expandable
to show the packs chosen and each floor's clear time) and "Overall stats"
(per floor, the packs ranked by fastest average clear time)."""

import csv
import datetime as _dt

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFileDialog, QHBoxLayout, QLabel, QScrollArea, QToolButton, QVBoxLayout,
    QWidget,
)

from . import stats
from .copy import (
    STATS_HISTORY_EMPTY,
    STATS_PACKS_EMPTY,
    STATS_PACKS_HINT,
)
from .theme import Colors, Sizing
from .widgets import (
    AnimatedStack, Card, GhostButton, HRule, IconlessTabBar, PageHeader,
    StatTiles, humanize_pack,
)

_MAX_HISTORY_ROWS = 14
_MAX_RANK_ROWS = 8     # packs shown per floor in Overall stats


class StatsPage(QWidget):

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

        header = PageHeader("Stats", self)
        self._export_btn = GhostButton("Export CSV", self)
        self._export_btn.clicked.connect(self._export_csv)
        header.add_action(self._export_btn)
        outer.addWidget(header)

        # Match the Mirror Dungeon page aesthetic: text-only tab strip with
        # a sliding yellow underline + a thin horizontal rule, content
        # below switching via AnimatedStack inside its own scroll area.
        self._TABS = ("Runs", "Overall stats")
        self._tabbar = IconlessTabBar(list(self._TABS), default="Runs",
                                      parent=self)
        self._tabbar.selection_changed.connect(self._on_tab)
        outer.addWidget(self._tabbar)
        outer.addWidget(HRule(self))

        self._tab_stack = AnimatedStack(self)
        self._tab_stack.addWidget(self._scroll(self._build_runs_tab()))
        self._tab_stack.addWidget(self._scroll(self._build_overall_tab()))
        outer.addWidget(self._tab_stack, 1)

    def _scroll(self, content: QWidget) -> QScrollArea:
        sa = QScrollArea(self)
        sa.setObjectName("pageScroll")
        sa.setWidgetResizable(True)
        sa.setFrameShape(QScrollArea.Shape.NoFrame)
        sa.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        sa.setWidget(content)
        return sa

    def _on_tab(self, label: str):
        if label in self._TABS:
            self._tab_stack.setCurrentIndex(self._TABS.index(label))

    # --- "Runs" tab -------------------------------------------------
    def _build_runs_tab(self) -> QWidget:
        w = QWidget(self)
        v = QVBoxLayout(w)
        v.setContentsMargins(0, Sizing.SPACE_MD, 0, 0)
        v.setSpacing(Sizing.SPACE_LG)

        overview = Card("OVERVIEW", w)
        self._tiles = StatTiles([
            ("Runs completed", "0"),
            ("Failed runs", "0 / 0"),
            ("Average duration", "0m 0s"),
            ("Total grind time", "0h 0m", True),
        ], parent=overview)
        overview.body.addWidget(self._tiles)
        v.addWidget(overview)

        history = Card("HISTORY", w)
        self._history_body = QVBoxLayout()
        self._history_body.setContentsMargins(0, 0, 0, 0)
        self._history_body.setSpacing(Sizing.SPACE_XS)
        self._history_empty = QLabel(
            STATS_HISTORY_EMPTY,
            w, objectName="inlineHint",
        )
        self._history_body.addWidget(self._history_empty)
        history.body.addLayout(self._history_body)
        v.addWidget(history)
        v.addStretch(1)
        return w

    # --- "Overall stats" tab ----------------------------------------
    def _build_overall_tab(self) -> QWidget:
        w = QWidget(self)
        v = QVBoxLayout(w)
        v.setContentsMargins(0, Sizing.SPACE_MD, 0, 0)
        v.setSpacing(Sizing.SPACE_LG)

        card = Card("BEST PACKS BY FLOOR", w)
        card.body.addWidget(QLabel(
            STATS_PACKS_HINT, w, objectName="inlineHint"))
        self._overall_body = QVBoxLayout()
        self._overall_body.setContentsMargins(0, Sizing.SPACE_XS, 0, 0)
        self._overall_body.setSpacing(Sizing.SPACE_XS)
        self._overall_empty = QLabel(
            STATS_PACKS_EMPTY, w, objectName="inlineHint")
        self._overall_body.addWidget(self._overall_empty)
        card.body.addLayout(self._overall_body)
        v.addWidget(card)
        v.addStretch(1)
        return w

    # --- live refresh ----------------------------------------------
    def refresh_stats(self):
        agg = stats.aggregate()
        self._tiles.set_value("Runs completed", str(agg["completed"]))
        self._tiles.set_value("Failed runs",
                              f"{agg['failed']} / {agg['total']}")
        self._tiles.set_value("Average duration",
                              stats.fmt_duration(agg["avg_duration"]))
        self._tiles.set_value("Total grind time",
                              stats.fmt_total(agg["total_time"]))
        self._rebuild_history()
        self._rebuild_overall()

    @staticmethod
    def _clear(layout):
        while layout.count():
            item = layout.takeAt(0)
            w = item.widget()
            if w is not None:
                w.deleteLater()

    def _rebuild_history(self):
        self._clear(self._history_body)
        runs = list(reversed(stats.load_runs()))[:_MAX_HISTORY_ROWS]
        if not runs:
            self._history_body.addWidget(QLabel(
                STATS_HISTORY_EMPTY,
                self, objectName="inlineHint"))
            return
        for r in runs:
            self._history_body.addWidget(_HistoryRow(r, self))

    def _rebuild_overall(self):
        self._clear(self._overall_body)
        data = stats.aggregate_packs()
        if not data:
            self._overall_body.addWidget(QLabel(
                STATS_PACKS_EMPTY, self, objectName="inlineHint"))
            return
        for fl in sorted(data):
            rows = data[fl]
            if not rows:
                continue
            head = QLabel(f"Floor {fl}", self, objectName="settingTitle")
            self._overall_body.addWidget(head)
            for rank, row in enumerate(rows[:_MAX_RANK_ROWS], 1):
                self._overall_body.addWidget(_PackRankRow(rank, row, self))

    def showEvent(self, event):
        super().showEvent(event)
        self.refresh_stats()

    # --- export ----------------------------------------------------
    def _export_csv(self):
        runs = stats.load_runs()
        if not runs:
            return
        default = f"workerbee_runs_{_dt.date.today().isoformat()}.csv"
        path, _ = QFileDialog.getSaveFileName(
            self, "Export run history", default, "CSV files (*.csv)")
        if not path:
            return
        try:
            with open(path, "w", newline="", encoding="utf-8") as f:
                w = csv.writer(f)
                w.writerow(["timestamp", "result", "duration_seconds",
                            "team", "mode", "floors"])
                for r in runs:
                    ts = r.get("ts", 0)
                    when = (_dt.datetime.fromtimestamp(ts).isoformat()
                            if ts else "")
                    floors = "; ".join(
                        f"F{f.get('floor')}:{f.get('pack')}="
                        f"{int(round(f.get('duration', 0) or 0))}s"
                        for f in (r.get("floors") or []))
                    w.writerow([
                        when,
                        "completed" if r.get("completed") else "failed",
                        int(round(r.get("duration", 0) or 0)),
                        r.get("team", ""),
                        r.get("mode", "mirror"),
                        floors,
                    ])
        except OSError:
            pass


class _HistoryRow(QWidget):
    """One run in the history list: result dot, team, duration, age, plus a
    'more details' expander showing the packs chosen and each floor's time."""

    def __init__(self, run: dict, parent: QWidget | None = None):
        super().__init__(parent)
        col = QVBoxLayout(self)
        col.setContentsMargins(0, Sizing.SPACE_XXS, 0, Sizing.SPACE_XXS)
        col.setSpacing(Sizing.SPACE_XXS)

        top = QWidget(self)
        row = QHBoxLayout(top)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(Sizing.SPACE_SM)

        completed = bool(run.get("completed"))
        dot = QLabel("●", top)  # filled circle
        dot.setStyleSheet(
            f"color: {Colors.SUCCESS if completed else Colors.ERROR};")
        row.addWidget(dot)

        team = (run.get("team") or "").strip()
        label = team.title() if team else "Mirror Dungeon"
        result = "Completed" if completed else "Failed"
        name = QLabel(f"{label}  ·  {result}", top,
                      objectName="settingTitle")
        row.addWidget(name)
        row.addStretch(1)

        dur = QLabel(stats.fmt_duration(run.get("duration", 0)), top,
                     objectName="inlineMeta")
        row.addWidget(dur)
        sep = QLabel("·", top, objectName="inlineMeta")
        row.addWidget(sep)
        ago = QLabel(stats.fmt_ago(run.get("ts", 0)), top,
                     objectName="inlineMeta")
        ago.setMinimumWidth(64)
        ago.setAlignment(Qt.AlignmentFlag.AlignRight
                         | Qt.AlignmentFlag.AlignVCenter)
        row.addWidget(ago)
        col.addWidget(top)

        floors = [f for f in (run.get("floors") or []) if isinstance(f, dict)]
        self._details = None
        if floors:
            self._toggle = QToolButton(self)
            self._toggle.setObjectName("expander")
            self._toggle.setCheckable(True)
            self._toggle.setText("▸ more details")
            self._toggle.setCursor(Qt.CursorShape.PointingHandCursor)
            self._toggle.setStyleSheet("QToolButton { border: none; }")
            self._toggle.toggled.connect(self._on_toggle)
            col.addWidget(self._toggle, 0, Qt.AlignmentFlag.AlignLeft)

            self._details = QWidget(self)
            dv = QVBoxLayout(self._details)
            dv.setContentsMargins(Sizing.SPACE_LG, 0, 0, Sizing.SPACE_XS)
            dv.setSpacing(0)
            for f in floors:
                raw_pack = str(f.get("pack", ""))
                dur_text = stats.fmt_duration(f.get("duration", 0))
                if raw_pack == "Restart":
                    # Synthetic entry from a THRILL F1 forfeit on a prior
                    # attempt before this run completed; no floor number
                    # to show, just the elapsed time of that attempt.
                    label_text = f"Restart  -  {dur_text}"
                else:
                    humanized = humanize_pack(raw_pack) or "(skipped)"
                    label_text = (f"Floor {f.get('floor', '?')}:  "
                                  f"{humanized}  -  {dur_text}")
                dv.addWidget(QLabel(label_text, self._details,
                                    objectName="inlineMeta"))
            self._details.setVisible(False)
            col.addWidget(self._details)

    def _on_toggle(self, on: bool):
        self._toggle.setText(
            ("▾ more details") if on else ("▸ more details"))
        if self._details is not None:
            self._details.setVisible(on)


class _PackRankRow(QWidget):
    """One ranked pack in the Overall stats tab: rank, name, avg/best, count."""

    def __init__(self, rank: int, data: dict, parent: QWidget | None = None):
        super().__init__(parent)
        row = QHBoxLayout(self)
        row.setContentsMargins(0, Sizing.SPACE_XXS, 0, Sizing.SPACE_XXS)
        row.setSpacing(Sizing.SPACE_SM)

        num = QLabel(f"{rank}.", self, objectName="inlineMeta")
        num.setFixedWidth(22)
        row.addWidget(num)
        row.addWidget(QLabel(humanize_pack(str(data.get("pack", ""))), self,
                             objectName="settingTitle"))
        row.addStretch(1)
        row.addWidget(QLabel(
            f"avg {stats.fmt_duration(data.get('avg', 0))}", self,
            objectName="inlineMeta"))
        row.addWidget(QLabel("·", self, objectName="inlineMeta"))
        row.addWidget(QLabel(
            f"best {stats.fmt_duration(data.get('best', 0))}", self,
            objectName="inlineMeta"))
        row.addWidget(QLabel("·", self, objectName="inlineMeta"))
        cnt = QLabel(f"{int(data.get('count', 0))}x", self,
                     objectName="inlineMeta")
        cnt.setMinimumWidth(40)
        cnt.setAlignment(Qt.AlignmentFlag.AlignRight
                         | Qt.AlignmentFlag.AlignVCenter)
        row.addWidget(cnt)
