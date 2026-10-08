# SPDX-License-Identifier: GPL-3.0-or-later
"""The overlay shown between pressing Start and the run beginning: what is
about to run, and a countdown the user can cancel or skip.

It covers the WorkerBee window (the click that raised it happened there) and
owns no timing of its own: the run coordinator ticks it, so the button text,
the Stop button, the hotkeys and this overlay always agree on what is
pending. The run overlay draws the same summary over the game."""

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QColor, QImage, QPainter, QPixmap
from PySide6.QtWidgets import (
    QFrame, QGridLayout, QHBoxLayout, QLabel, QVBoxLayout, QWidget,
)

from .theme import Colors, Sizing
from .widgets import GhostButton, PrimaryButton

_PANEL_W = 780
# One label width for every section, so the values in a column line up
# from one section to the next.
_LABEL_W = 128
# Gift art: named tiles for the gifts searched for, bare thumbnails for the
# (longer) list of market targets.
GIFT_TILE, GIFT_THUMB, GIFT_TILE_W = 56, 40, 104

_IMAGES: dict = {}


def gift_image(name: str, size: int):
    """The gift's illustration scaled to `size`, or None when there is no
    art for it. Cached, because the in-game overlay repaints many times a
    second, and cached as QImage rather than QPixmap: a pixmap that outlives
    the application object crashes the interpreter on the way out, and a
    module-level cache always outlives it."""
    key = (name, int(size))
    if key not in _IMAGES:
        img = None
        try:
            from .giftart import art_path
            path = art_path(name)
            if path:
                src = QImage(path)
                if not src.isNull():
                    img = src.scaled(
                        size, size, Qt.AspectRatioMode.KeepAspectRatio,
                        Qt.TransformationMode.SmoothTransformation)
        except Exception:
            img = None
        _IMAGES[key] = img
    return _IMAGES[key]


def gift_pixmap(name: str, size: int):
    """gift_image as a pixmap for a label. Not cached, for the reason above."""
    img = gift_image(name, size)
    return QPixmap.fromImage(img) if img is not None else None


def pixel_safe(text: str) -> str:
    """Text for the 5x7 face, which has round brackets but no square ones."""
    return str(text or "").replace("[", "(").replace("]", ")")


def _voxel() -> bool:
    try:
        from .skins import is_voxel
        return is_voxel()
    except Exception:
        return False


class StartOverlay(QWidget):
    """Scrim over `host` with a centred summary panel and a countdown."""

    start_now = Signal()
    cancelled = Signal()

    def __init__(self, host: QWidget):
        super().__init__(host)
        self._host = host
        self._count = None
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.hide()
        # Follows the host's size by polling while it is up (at most the
        # length of a countdown). An event filter on the host would do it
        # without a timer, but this widget is the host's child: as the
        # host is destroyed it still delivers events to a filter that is
        # itself half torn down, which crashed the interpreter on exit.
        self._fit = QTimer(self)
        self._fit.setInterval(100)
        self._fit.timeout.connect(self._fit_host)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(Sizing.SPACE_XL, Sizing.SPACE_XL,
                                 Sizing.SPACE_XL, Sizing.SPACE_XL)
        outer.addStretch(1)
        row = QHBoxLayout()
        row.addStretch(1)
        self._panel = QFrame(self)
        self._panel.setObjectName("startPanel")
        self._panel.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self._panel.setMaximumWidth(_PANEL_W)
        self._panel_col = QVBoxLayout(self._panel)
        self._panel_col.setContentsMargins(
            Sizing.SPACE_XL, Sizing.SPACE_XL, Sizing.SPACE_XL, Sizing.SPACE_LG)
        self._panel_col.setSpacing(Sizing.SPACE_MD)
        row.addWidget(self._panel, 10)
        row.addStretch(1)
        outer.addLayout(row)
        outer.addStretch(1)

    # --- public -----------------------------------------------------
    def open(self, summary: dict, seconds: int):
        """Show the overlay for a pending start. `summary` comes from
        run_summary.md_start / lux_start."""
        self._build(summary)
        self.set_remaining(seconds)
        self.setGeometry(self._host.rect())
        self.show()
        self.raise_()
        self.setFocus()
        self._fit.start()

    def set_remaining(self, seconds: int):
        if self._count is not None:
            self._count.setText(str(max(0, int(seconds))))

    def close_overlay(self):
        self._fit.stop()
        self.hide()

    def _fit_host(self):
        if self.geometry() != self._host.rect():
            self.setGeometry(self._host.rect())

    # --- build ------------------------------------------------------
    def _clear(self, layout):
        while layout.count():
            item = layout.takeAt(0)
            w = item.widget()
            if w is not None:
                w.setParent(None)
                w.deleteLater()
            elif item.layout() is not None:
                self._clear(item.layout())

    def _build(self, summary: dict):
        from .style import voxel_page_color
        voxel = _voxel()
        col = self._panel_col
        self._clear(col)
        # Solid, not the translucent card tint: it sits on a scrim, and a
        # see-through panel would show the page text through the summary.
        self._panel.setStyleSheet(
            "QFrame#startPanel { background-color: %s; border: 1px solid %s;"
            " border-radius: %dpx; }" % (
                voxel_page_color() if voxel else Colors.BG_RAISED,
                Colors.ACCENT_MUTED, Sizing.RADIUS_LG))

        # The kind of run is the largest thing on the panel; the countdown
        # sits beside it, a size down.
        head = QHBoxLayout()
        head.setSpacing(Sizing.SPACE_LG)
        names = QVBoxLayout()
        names.setSpacing(Sizing.SPACE_SM)
        names.addWidget(QLabel("STARTING IN", self._panel,
                               objectName="sectionLabel"),
                        0, Qt.AlignmentFlag.AlignLeft)
        names.addWidget(self._headline(summary.get("title", ""), voxel))
        subtitle = summary.get("subtitle")
        if subtitle:
            names.addWidget(self._subline(subtitle, voxel))
        head.addLayout(names)
        head.addStretch(1)
        head.addWidget(self._make_count(voxel), 0,
                       Qt.AlignmentFlag.AlignTop)
        col.addLayout(head)

        hint = QLabel("Switch to Limbus Company now. The run starts when "
                      "the countdown ends.", self._panel)
        hint.setWordWrap(True)
        hint.setStyleSheet(f"color: {Colors.TEXT_SECONDARY};")
        col.addWidget(hint)

        gifts = summary.get("gifts") or []
        if gifts:
            strip = QGridLayout()
            strip.setContentsMargins(0, Sizing.SPACE_SM, 0, 0)
            strip.setHorizontalSpacing(Sizing.SPACE_XL)
            strip.setColumnStretch(0, 1)
            strip.setColumnStretch(1, 1)
            for i, group in enumerate(gifts[:2]):
                strip.addWidget(self._gift_group(group), 0, i,
                                Qt.AlignmentFlag.AlignTop)
            col.addLayout(strip)

        # Sections fill two columns, top to bottom then across.
        sections = summary.get("sections") or []
        grid = QGridLayout()
        grid.setContentsMargins(0, Sizing.SPACE_SM, 0, Sizing.SPACE_SM)
        grid.setHorizontalSpacing(Sizing.SPACE_XL)
        grid.setVerticalSpacing(Sizing.SPACE_LG)
        grid.setColumnStretch(0, 1)
        grid.setColumnStretch(1, 1)
        per_col = max(1, (len(sections) + 1) // 2)
        for i, (caption, rows) in enumerate(sections):
            grid.addWidget(self._section(caption, rows), i % per_col,
                           i // per_col, Qt.AlignmentFlag.AlignTop)
        col.addLayout(grid)

        buttons = QHBoxLayout()
        buttons.setSpacing(Sizing.SPACE_SM)
        keys = QLabel("Esc cancels, Enter starts now", self._panel)
        keys.setStyleSheet(f"color: {Colors.TEXT_TERTIARY};")
        buttons.addWidget(keys)
        buttons.addStretch(1)
        cancel = GhostButton("Cancel", self._panel)
        # Signal to signal, not to `.emit`: a bound emit held by the
        # connection ties the button and this widget into a cycle that
        # crashes the interpreter when the garbage collector unpicks it.
        cancel.clicked.connect(self.cancelled)
        buttons.addWidget(cancel)
        go = PrimaryButton("Start now", self._panel)
        go.clicked.connect(self.start_now)
        buttons.addWidget(go)
        col.addLayout(buttons)

    def _headline(self, title: str, voxel: bool) -> QWidget:
        if voxel:
            from .voxel import PixelLabel
            return PixelLabel(pixel_safe(title), pixel=6,
                              color=Colors.TEXT_PRIMARY, parent=self._panel)
        lbl = QLabel(title, self._panel)
        lbl.setStyleSheet(
            f"color: {Colors.TEXT_PRIMARY}; font-size: 30pt; font-weight: 700;")
        return lbl

    def _subline(self, text: str, voxel: bool) -> QWidget:
        if voxel:
            from .voxel import PixelLabel
            return PixelLabel(pixel_safe(text), pixel=3, color=Colors.ACCENT,
                              parent=self._panel)
        lbl = QLabel(text, self._panel)
        lbl.setStyleSheet(
            f"color: {Colors.ACCENT}; font-size: 13pt; font-weight: 700;")
        return lbl

    def _make_count(self, voxel: bool) -> QWidget:
        if voxel:
            from .voxel import PixelLabel
            self._count = PixelLabel("10", pixel=5, color=Colors.ACCENT,
                                     parent=self._panel)
        else:
            self._count = QLabel("10", self._panel)
            self._count.setStyleSheet(
                f"color: {Colors.ACCENT}; font-size: 24pt; font-weight: 700;")
        return self._count

    def _gift_group(self, group: dict) -> QWidget:
        """One captioned run of gift art: tiles with names, or thumbnails."""
        box = QWidget(self._panel)
        col = QVBoxLayout(box)
        col.setContentsMargins(0, 0, 0, 0)
        col.setSpacing(Sizing.SPACE_XS)
        col.addWidget(QLabel(group.get("caption", ""), box,
                             objectName="sectionLabel"),
                      0, Qt.AlignmentFlag.AlignLeft)
        names = list(group.get("names") or [])
        if not names:
            none = QLabel("None", box)
            none.setStyleSheet(f"color: {Colors.TEXT_SECONDARY};")
            col.addWidget(none)
            return box

        named = bool(group.get("named"))
        size = GIFT_TILE if named else GIFT_THUMB
        limit = 3 if named else 8
        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(Sizing.SPACE_SM)
        for name in names[:limit]:
            row.addWidget(self._gift(name, size, named, box), 0,
                          Qt.AlignmentFlag.AlignTop)
        if len(names) > limit:
            more = QLabel("+%d" % (len(names) - limit), box)
            more.setStyleSheet(f"color: {Colors.TEXT_SECONDARY};")
            row.addWidget(more, 0, Qt.AlignmentFlag.AlignVCenter)
        row.addStretch(1)
        col.addLayout(row)
        return box

    def _gift(self, name: str, size: int, named: bool, parent) -> QWidget:
        art = QLabel(parent)
        art.setFixedSize(size, size)
        art.setAlignment(Qt.AlignmentFlag.AlignCenter)
        art.setToolTip(name)
        pm = gift_pixmap(name, size)
        if pm is not None:
            art.setPixmap(pm)
        else:
            # No art for this gift: an empty framed slot, not a broken image.
            art.setStyleSheet(
                f"border: 1px solid {Colors.BORDER_STRONG};"
                f" color: {Colors.TEXT_TERTIARY};")
            art.setText("?")
        if not named:
            return art
        tile = QWidget(parent)
        tile.setFixedWidth(GIFT_TILE_W)
        col = QVBoxLayout(tile)
        col.setContentsMargins(0, 0, 0, 0)
        col.setSpacing(Sizing.SPACE_XXS)
        col.addWidget(art, 0, Qt.AlignmentFlag.AlignHCenter)
        label = QLabel(name, tile)
        label.setWordWrap(True)
        label.setAlignment(Qt.AlignmentFlag.AlignHCenter
                           | Qt.AlignmentFlag.AlignTop)
        label.setStyleSheet(f"color: {Colors.TEXT_PRIMARY};")
        col.addWidget(label)
        return tile

    def _section(self, caption: str, rows: list) -> QWidget:
        box = QWidget(self._panel)
        col = QVBoxLayout(box)
        col.setContentsMargins(0, 0, 0, 0)
        col.setSpacing(Sizing.SPACE_XS)
        col.addWidget(QLabel(caption, box, objectName="sectionLabel"),
                      0, Qt.AlignmentFlag.AlignLeft)
        grid = QGridLayout()
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setHorizontalSpacing(Sizing.SPACE_MD)
        grid.setVerticalSpacing(Sizing.SPACE_XXS)
        grid.setColumnMinimumWidth(0, _LABEL_W)
        grid.setColumnStretch(1, 1)
        for r, (label, value) in enumerate(rows):
            name = QLabel(label, box)
            name.setStyleSheet(f"color: {Colors.TEXT_SECONDARY};")
            grid.addWidget(name, r, 0, Qt.AlignmentFlag.AlignTop)
            val = QLabel(str(value), box)
            val.setWordWrap(True)
            val.setStyleSheet(f"color: {Colors.TEXT_PRIMARY};")
            grid.addWidget(val, r, 1)
        col.addLayout(grid)
        return box

    # --- events -----------------------------------------------------
    def paintEvent(self, _event):
        p = QPainter(self)
        p.fillRect(self.rect(), QColor(4, 6, 8, 210))
        p.end()

    def mousePressEvent(self, event):
        event.accept()          # the scrim swallows clicks meant for the page

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Escape:
            self.cancelled.emit()
        elif event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            self.start_now.emit()
        else:
            super().keyPressEvent(event)
