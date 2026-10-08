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
    QFileDialog, QHBoxLayout, QLabel, QMessageBox, QScrollArea, QSizePolicy,
    QToolButton, QVBoxLayout, QWidget,
)

import os

from PySide6.QtGui import QColor, QPainter, QPen, QPixmap

from . import stats


def _pack_thumb(key: str, height: int, parent) -> QLabel:
    """The pack's in-game theme card, scaled to a row. Portrait art, so the
    height is what is fixed and the width follows."""
    from .giftart import pack_icon
    lbl = QLabel(parent)
    lbl.setFixedHeight(height)
    pm = QPixmap(pack_icon(key))
    if pm.isNull():
        lbl.setFixedWidth(0)
        return lbl
    scaled = pm.scaledToHeight(height, Qt.TransformationMode.SmoothTransformation)
    lbl.setPixmap(scaled)
    lbl.setFixedWidth(scaled.width())
    return lbl


class _FloorCell(QWidget):
    """One floor of a run, stacked: FLOOR n, the pack name, its theme card,
    then the clear time. Reads as the row of packs the run actually drew."""

    _CARD_H = 104
    # Wide enough for the longest single word in any pack name at pixel size
    # 2 (13 characters), so the title never has to be cut or hyphenated.
    _WIDTH = 158

    def __init__(self, floor, pack_key: str, label: str, duration: str,
                 parent=None):
        super().__init__(parent)
        self.setFixedWidth(self._WIDTH)
        self.setToolTip(
            f"{label}\nFloor {floor}  -  {duration}"
            if floor else f"{label}  -  {duration}")
        col = QVBoxLayout(self)
        col.setContentsMargins(0, 0, 0, 0)
        col.setSpacing(Sizing.SPACE_SM)

        from .skins import is_voxel
        from .voxel import PixelBlock
        self._voxel = is_voxel()

        # Three tiers, separated by colour rather than size: the floor is the
        # quiet label, the pack is the subject, the time is the number.
        col.addWidget(self._text(
            f"Floor {floor}" if floor else "Restart", Colors.TEXT_SECONDARY))

        name = self._text(label if floor else "", Colors.TEXT_PRIMARY)
        # Kept so the strip can level every name to the tallest one; names
        # wrap to different line counts and the cards would otherwise sit at
        # different heights along the row.
        self.title = name
        col.addWidget(name)

        col.addWidget(_pack_thumb(pack_key, self._CARD_H, self),
                      0, Qt.AlignmentFlag.AlignHCenter)
        col.addWidget(self._text(duration, Colors.ACCENT))

    def _text(self, text: str, color: str):
        from .voxel import PixelBlock
        if self._voxel:
            return PixelBlock(text, pixel=2, color=color,
                              max_width=self._WIDTH, parent=self)
        lbl = QLabel(text, self, objectName="inlineMeta")
        lbl.setStyleSheet(f"color: {color};")
        lbl.setWordWrap(True)
        lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        return lbl


def _gift_icon_path(name: str) -> str:
    """Full wiki art for a gift, else its in-game template, else ""."""
    from .giftart import art_path
    hit = art_path(name)
    if hit:
        return hit
    try:
        from wbcore.market_catalog import market_gift_info
        info = market_gift_info(name) or {}
        if info.get("path"):
            return info["path"]
    except Exception:
        pass
    try:
        from wbcore.utils.paths import PTH
        return PTH.get(name, "") or ""
    except Exception:
        return ""
from .copy import (
    STATS_HISTORY_EMPTY,
    STATS_PACKS_EMPTY,
    STATS_PACKS_HINT,
)
from .theme import Colors, Sizing
from .widgets import (
    AnimatedStack, Card, ElidedLabel, GhostButton, HRule, IconlessTabBar,
    PageHeader, StatTiles, humanize_pack,
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
        self._clear_btn = GhostButton("Clear stats", self)
        self._clear_btn.clicked.connect(self._clear_stats)
        header.add_action(self._clear_btn)
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
        sa.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
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
        v.setSpacing(Sizing.SPACE_MD)

        hint = QLabel(STATS_PACKS_HINT, w, objectName="inlineHint")
        hint.setWordWrap(True)
        v.addWidget(hint)
        # One card per floor, built on refresh: a floor's packs only mean
        # anything against each other, so they get their own block.
        self._overall_body = QVBoxLayout()
        self._overall_body.setContentsMargins(0, 0, 0, 0)
        self._overall_body.setSpacing(Sizing.SPACE_MD)
        v.addLayout(self._overall_body)
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
                w.setParent(None)
                w.deleteLater()
            elif item.layout() is not None:
                StatsPage._clear(item.layout())
                item.layout().setParent(None)

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
            empty = Card("BEST PACKS BY FLOOR", self)
            empty.body.addWidget(QLabel(
                STATS_PACKS_EMPTY, empty, objectName="inlineHint"))
            self._overall_body.addWidget(empty)
            return
        for fl in sorted(data):
            rows = [r for r in data[fl] if r][:_MAX_RANK_ROWS]
            if not rows:
                continue
            card = Card(f"FLOOR {fl}", self)
            runs = sum(int(r.get("count", 0) or 0) for r in rows)
            card.body.addWidget(QLabel(
                f"{len(rows)} pack{'s' if len(rows) != 1 else ''}  ·  "
                f"{runs} clear{'s' if runs != 1 else ''}",
                card, objectName="inlineMeta"))
            # Bars are relative to the fastest pack on this floor, then
            # stretched across the floor's own spread: raw ratios sit in a
            # narrow band (0.8-1.0) where every bar looks the same length.
            avgs = [float(r.get("avg", 0) or 0) for r in rows]
            fastest = min((a for a in avgs if a > 0), default=0.0)
            raw = [(fastest / a) if (fastest > 0 and a > 0) else 0.0
                   for a in avgs]
            lo = min(raw) if raw else 0.0
            span = 1.0 - lo
            for rank, (row, r) in enumerate(zip(rows, raw), 1):
                frac = 1.0 if span < 0.02 else 0.25 + 0.75 * (r - lo) / span
                card.body.addWidget(_PackRankRow(rank, row, frac, card))
            self._overall_body.addWidget(card)

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
                            "team", "mode", "floors", "gifts"])
                for r in runs:
                    ts = r.get("ts", 0)
                    when = (_dt.datetime.fromtimestamp(ts).isoformat()
                            if ts else "")
                    floors = "; ".join(
                        f"F{f.get('floor')}:{f.get('pack')}="
                        f"{int(round(f.get('duration', 0) or 0))}s"
                        for f in (r.get("floors") or []))
                    gifts = "; ".join(
                        str(g.get("name", "")) + ("[+]" if g.get("uptied") else "")
                        for g in (r.get("gifts") or []))
                    w.writerow([
                        when,
                        "completed" if r.get("completed") else "failed",
                        int(round(r.get("duration", 0) or 0)),
                        r.get("team", ""),
                        r.get("mode", "mirror"),
                        floors,
                        gifts,
                    ])
        except OSError:
            pass

    # --- clear -----------------------------------------------------
    def _clear_stats(self):
        resp = QMessageBox.question(
            self, "Clear stats",
            "Delete all recorded run history and stats? This cannot be undone.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if resp == QMessageBox.StandardButton.Yes:
            stats.clear()
            self.refresh_stats()


class _GiftStrip(QWidget):
    """A run's EGO gifts as a wrapped row of icons. Uptied gifts carry a
    small accent "+" badge in the corner, so the haul reads at a glance
    instead of as a paragraph of names."""

    _ICON = 34
    _GAP = 4

    def __init__(self, gifts, parent=None):
        super().__init__(parent)
        self._items = []
        for g in gifts:
            name = str(g.get("name", ""))
            pm = QPixmap(_gift_icon_path(name))
            if not pm.isNull():
                pm = pm.scaled(self._ICON, self._ICON,
                               Qt.AspectRatioMode.KeepAspectRatio,
                               Qt.TransformationMode.SmoothTransformation)
            self._items.append((name, pm, bool(g.get("uptied"))))
        self.setToolTip(", ".join(
            n + (" [+]" if u else "") for n, _p, u in self._items))
        self._cols = 1
        self.setMinimumHeight(self._ICON + 2)

    def _layout_cols(self) -> int:
        step = self._ICON + self._GAP
        return max(1, (self.width() + self._GAP) // step)

    def resizeEvent(self, e):
        cols = self._layout_cols()
        if cols != self._cols:
            self._cols = cols
            rows = -(-len(self._items) // cols) if self._items else 1
            self.setMinimumHeight(rows * (self._ICON + self._GAP))
        super().resizeEvent(e)

    def refresh_theme(self):
        self.update()

    def paintEvent(self, _e):
        if not self._items:
            return
        p = QPainter(self)
        cols = self._layout_cols()
        step = self._ICON + self._GAP
        badge = QColor(Colors.ACCENT)
        b = 11
        for i, (_name, pm, up) in enumerate(self._items):
            x = (i % cols) * step
            y = (i // cols) * step
            if not pm.isNull():
                # Centre it: the in-game templates are not square, and
                # top-left anchoring left them sitting higher than their
                # neighbours with the badge detached from the art.
                ox = x + (self._ICON - pm.width()) // 2
                oy = y + (self._ICON - pm.height()) // 2
                p.drawPixmap(int(ox), int(oy), pm)
                bx, by = int(ox + pm.width() - b), int(oy)
            else:
                p.fillRect(int(x), int(y), self._ICON, self._ICON,
                           QColor(Colors.BG_OVERLAY))
                bx, by = int(x + self._ICON - b), int(y)
            if up:
                # "+" badge, top-right of the art.
                p.fillRect(bx, by, b, b, badge)
                p.setPen(QPen(QColor(Colors.BG_BASE), 2))
                p.drawLine(bx + 3, by + b // 2, bx + b - 3, by + b // 2)
                p.drawLine(bx + b // 2, by + 3, bx + b // 2, by + b - 3)
        p.end()


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
        self._row = row
        self._after_name = row.count()
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
        gifts = [g for g in (run.get("gifts") or []) if isinstance(g, dict)]
        self._details = None
        if floors or gifts:
            self._toggle = QToolButton(top)
            self._toggle.setObjectName("expander")
            self._toggle.setCheckable(True)
            self._toggle.setText("▸ details")
            self._toggle.setCursor(Qt.CursorShape.PointingHandCursor)
            self._toggle.setStyleSheet("QToolButton { border: none; }")
            self._toggle.toggled.connect(self._on_toggle)
            # On the title line, not a line of its own: a second row per run
            # doubled the panel's height for one word.
            self._row.insertWidget(self._after_name, self._toggle)

            self._details = QWidget(self)
            dv = QVBoxLayout(self._details)
            dv.setContentsMargins(Sizing.SPACE_LG, 0, 0, Sizing.SPACE_XS)
            dv.setSpacing(0)
            if floors:
                strip = QWidget(self._details)
                sh = QHBoxLayout(strip)
                sh.setContentsMargins(0, Sizing.SPACE_LG, 0, Sizing.SPACE_SM)
                sh.setSpacing(Sizing.SPACE_SM)
                for f in floors:
                    raw_pack = str(f.get("pack", ""))
                    dur_text = stats.fmt_duration(f.get("duration", 0))
                    if raw_pack == "Restart":
                        # Synthetic entry from a THRILL F1 forfeit on an
                        # earlier attempt; no floor and no pack of its own.
                        sh.addWidget(_FloorCell(
                            None, "", "Restart", dur_text, strip))
                        continue
                    sh.addWidget(_FloorCell(
                        f.get("floor", "?"), raw_pack,
                        humanize_pack(raw_pack) or "(skipped)",
                        dur_text, strip))
                sh.addStretch(1)
                cells = [sh.itemAt(i).widget() for i in range(sh.count())
                         if sh.itemAt(i).widget() is not None]
                if cells and hasattr(cells[0].title, "level_to"):
                    # Every name gets the same slot height, centred in it, so
                    # the cards and times line up whatever the line count.
                    tallest = max(c.title.line_count() for c in cells)
                    for c in cells:
                        c.title.level_to(tallest)
                else:
                    tallest = max((c.title.sizeHint().height()
                                   for c in cells), default=0)
                    for c in cells:
                        c.title.setFixedHeight(tallest)
                        c.title.setAlignment(
                            Qt.AlignmentFlag.AlignVCenter
                            | Qt.AlignmentFlag.AlignHCenter)
                dv.addWidget(strip)
            if gifts:
                # End-of-run fuse-shelf scan; [+] marks an uptied gift
                # Icons, not a wall of names: a run's gift haul is much
                # easier to read as art, with a "+" badge marking the ones
                # that were uptied.
                uptied = sum(1 for g in gifts if g.get("uptied"))
                dv.addWidget(QLabel(
                    f"Gifts  ({len(gifts)}, {uptied} uptied)",
                    self._details, objectName="inlineMeta"))
                dv.addWidget(_GiftStrip(gifts, self._details))
            self._details.setVisible(False)
            col.addWidget(self._details)

    def _on_toggle(self, on: bool):
        self._toggle.setText("▾ details" if on else "▸ details")
        if self._details is not None:
            self._details.setVisible(on)


class _BlockBar(QWidget):
    """Chunky block bar - the skin's chart primitive. `frac` is 0..1 of the
    cells lit."""

    _CELL, _GAP, _H = 6, 3, 9

    def __init__(self, frac: float, best: bool = False,
                 parent: QWidget | None = None):
        super().__init__(parent)
        self._frac = max(0.0, min(1.0, float(frac)))
        self._best = best
        self.setFixedHeight(self._H)
        self.setSizePolicy(QSizePolicy.Policy.Expanding,
                           QSizePolicy.Policy.Fixed)
        self.setMinimumWidth(60)

    def refresh_theme(self):
        self.update()

    def paintEvent(self, _event):
        p = QPainter(self)
        step = self._CELL + self._GAP
        cells = max(1, (self.width() + self._GAP) // step)
        lit = int(round(self._frac * cells))
        on = QColor(Colors.ACCENT if self._best else Colors.TEXT_TERTIARY)
        off = QColor(Colors.BG_HOVER)
        for i in range(cells):
            p.fillRect(i * step, 0, self._CELL, self.height(),
                       on if i < lit else off)


class _PackRankRow(QWidget):
    """One ranked pack in the Overall stats tab: rank, name, a bar showing how
    close its average is to the floor's fastest, then avg/best/count in fixed
    columns so the numbers line up down the card."""

    _NAME_W, _NUM_W = 212, 92

    def __init__(self, rank: int, data: dict, frac: float = 0.0,
                 parent: QWidget | None = None):
        super().__init__(parent)
        row = QHBoxLayout(self)
        row.setContentsMargins(0, Sizing.SPACE_XXS, 0, Sizing.SPACE_XXS)
        row.setSpacing(Sizing.SPACE_MD)

        num = QLabel(f"{rank}", self,
                     objectName="rankBest" if rank == 1 else "inlineMeta")
        num.setFixedWidth(18)
        num.setAlignment(Qt.AlignmentFlag.AlignRight
                         | Qt.AlignmentFlag.AlignVCenter)
        row.addWidget(num)

        row.addWidget(_pack_thumb(str(data.get("pack", "")), 26, self))
        name = ElidedLabel(humanize_pack(str(data.get("pack", ""))), self,
                           objectName="settingTitle")
        name.setFixedWidth(self._NAME_W)
        row.addWidget(name)

        row.addWidget(_BlockBar(frac, rank == 1, self), 1)

        for text in (f"avg {stats.fmt_duration(data.get('avg', 0))}",
                     f"best {stats.fmt_duration(data.get('best', 0))}",
                     f"{int(data.get('count', 0))}x"):
            # ElideLeft, not the default: the value is the informative part,
            # the "avg"/"best" prefix is redundant with the column position.
            lbl = ElidedLabel(text, self, Qt.TextElideMode.ElideLeft,
                              objectName="inlineMeta")
            lbl.setFixedWidth(self._NUM_W)
            lbl.setAlignment(Qt.AlignmentFlag.AlignRight
                             | Qt.AlignmentFlag.AlignVCenter)
            row.addWidget(lbl)
