# SPDX-License-Identifier: GPL-3.0-or-later
"""Initializing-screen splash, crossfaded out when init finishes."""

import math
import os
import random

from PySide6.QtCore import (
    Property, QEasingCurve, QPropertyAnimation, Qt, QTimer, Signal,
)
from PySide6.QtGui import QColor, QIcon, QLinearGradient, QPainter, QPixmap
from PySide6.QtWidgets import (
    QFrame, QHBoxLayout, QLabel, QProgressBar, QPushButton, QStackedWidget,
    QVBoxLayout, QWidget,
)

from . import seasonal
from .spinner import Spinner
from .theme import Sizing
from .voxel import PixelWordmark, VoxelLogo


_BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


# Rotated through the subtitle slot. Keep each under ~40 chars to avoid wrap.
_LOADING_TIPS = (
    "Bees have five eyes",
    "Honey never spoils",
    "Queens lay 2,000 eggs a day",
    "Only female bees can sting",
    "Wings flap 230 times a second",
    "Bees recognise human faces",
    "Bees see ultraviolet light",
    "Waggle dances map flowers",
    "Bees have hair on their eyes",
    "Drones die after mating",
    "Bees predate flowers",
    "Honey is technically bee vomit",
    "Queens far outlive workers",
    "Bumblebees fly in light rain",
    "100 flowers per foraging trip",
    "Bees understand zero",
    "1 in 3 bites is bee pollinated",
    "The buzz is wings, not voice",
    "Bees navigate by the sun",
    "Worker = 1/12 tsp of honey ever",
)


def _read_version() -> str:
    for candidate in (
        os.path.join(_BASE_DIR, "version.json"),
        os.path.join(os.path.dirname(_BASE_DIR), "version.json"),
    ):
        try:
            with open(candidate, "r", encoding="utf-8") as f:
                v = f.read().strip()
                if v:
                    return v
        except Exception:
            continue
    return "dev"


def _load_app_icon(size: int = 72) -> QPixmap | None:
    """The .ico mark. The splash and the voxel sidebar both use the animated
    bee instead, but the legacy sidebar still brands with this."""
    icon_path = os.path.join(_BASE_DIR, "app_icon.ico")
    if not os.path.exists(icon_path):
        return None
    try:
        return QIcon(icon_path).pixmap(size, size)
    except Exception:
        return None


class _LoadingPane(QWidget):
    """Default splash content: icon left, text/progress right."""

    def __init__(self, parent=None):
        super().__init__(parent)
        row = QHBoxLayout(self)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(Sizing.SPACE_LG)
        # Full-width banner, not a square card.
        row.setAlignment(Qt.AlignmentFlag.AlignVCenter)

        row.addWidget(VoxelLogo(72, self),
                      alignment=Qt.AlignmentFlag.AlignVCenter)

        # Title + subtitle + progress + status, filling remaining width.
        text_col = QVBoxLayout()
        text_col.setSpacing(Sizing.SPACE_SM)
        text_col.setAlignment(Qt.AlignmentFlag.AlignVCenter)

        text_col.addWidget(PixelWordmark(4, self),
                           alignment=Qt.AlignmentFlag.AlignLeft)

        self.subtitle = QLabel("")
        self.subtitle.setObjectName("splashSubtitle")
        self.subtitle.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        text_col.addWidget(self.subtitle)

        # Tip rotation, paused when explicit subtitle text is pinned.
        self._tips = list(seasonal.SPOOKY_TIPS if seasonal.is_halloween()
                          else _LOADING_TIPS)
        random.shuffle(self._tips)
        self._tip_index = 0
        self._tips_pinned = False
        self._current_subtitle_raw = self._tips[0]
        self._apply_subtitle(self._tips[0])
        # Re-apply post-layout so elision uses the real label width (currently 0).
        # `self` as context: Qt drops the call if this pane is destroyed
        # first. Without it the callback ran on a deleted label.
        QTimer.singleShot(
            0, self, lambda: self._apply_subtitle(self._current_subtitle_raw))

        self._tip_timer = QTimer(self)
        self._tip_timer.setInterval(2500)
        self._tip_timer.timeout.connect(self._cycle_tip)
        self._tip_timer.start()

        text_col.addSpacing(Sizing.SPACE_SM)

        self.bar = QProgressBar(self)
        self.bar.setObjectName("splashBar")
        self.bar.setRange(0, 100)
        self.bar.setTextVisible(False)
        self.bar.setValue(0)
        # No fixed width; the bar stretches to fill the column.
        text_col.addWidget(self.bar)

        status_row = QHBoxLayout()
        status_row.setSpacing(Sizing.SPACE_SM)
        status_row.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)

        self.spinner = Spinner(self, size=12, line_width=2)
        status_row.addWidget(self.spinner)

        self.status = QLabel("Starting...")
        self.status.setObjectName("splashStatus")
        self.status.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        self._status_raw = "Starting..."
        status_row.addWidget(self.status, stretch=1)
        text_col.addLayout(status_row)

        row.addLayout(text_col, stretch=1)

    def apply_status(self, text: str | None = None):
        """Set the status line, eliding only against the width the label
        really has. Callers reach this well before the first layout, when
        every widget is still at its default width, so the raw text is kept
        and re-elided on every resize instead of being clipped once."""
        if text is not None:
            self._status_raw = text
        raw = self._status_raw
        avail = self.status.width()
        fm = self.status.fontMetrics()
        if avail <= 0 or avail >= fm.horizontalAdvance(raw):
            self.status.setText(raw)
        else:
            # Middle, not right: the tail carries the download counter
            # ("118 / 240 MB"), which is the half worth keeping.
            self.status.setText(
                fm.elidedText(raw, Qt.TextElideMode.ElideMiddle, avail))
        self.status.setToolTip(raw)

    def resizeEvent(self, e):
        super().resizeEvent(e)
        # Can fire mid-construction, before the labels exist, and re-eliding
        # changes a size hint - so only act on a real width change.
        if getattr(self, "_status_raw", None) is None:
            return
        if e.oldSize().width() == e.size().width():
            return
        self.apply_status()
        self._apply_subtitle(self._current_subtitle_raw)

    def _cycle_tip(self):
        if self._tips_pinned:
            return
        self._tip_index = (self._tip_index + 1) % len(self._tips)
        self._apply_subtitle(self._tips[self._tip_index])

    def _apply_subtitle(self, text: str):
        """Set the subtitle, right-eliding if it won't fit the label width."""
        self._current_subtitle_raw = text
        fm = self.subtitle.fontMetrics()
        avail = self.subtitle.width()
        if avail <= 0:
            avail = 220              # pre-layout fallback
        self.subtitle.setText(
            fm.elidedText(text, Qt.TextElideMode.ElideRight, avail)
        )

    def pin_subtitle(self, text: str):
        """Pin explicit subtitle; halts tip rotation until resume_tips()."""
        self._tips_pinned = True
        self._apply_subtitle(text)

    def resume_tips(self):
        self._tips_pinned = False
        self._apply_subtitle(self._tips[self._tip_index])


class _UpdatePromptPane(QWidget):
    """Update-available prompt: icon left; title, version diff/size, two buttons right."""

    update_now = Signal()
    update_skip = Signal()

    def __init__(self, current_version: str, new_version: str,
                 size_mb: int, parent=None):
        super().__init__(parent)
        row = QHBoxLayout(self)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(Sizing.SPACE_LG)
        row.setAlignment(Qt.AlignmentFlag.AlignVCenter)

        row.addWidget(VoxelLogo(72, self),
                      alignment=Qt.AlignmentFlag.AlignVCenter)

        col = QVBoxLayout()
        col.setSpacing(Sizing.SPACE_XS)
        col.setAlignment(Qt.AlignmentFlag.AlignVCenter)

        title = QLabel("Update Available")
        title.setObjectName("splashTitle")
        title.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        col.addWidget(title)

        meta = QLabel(
            f"v{current_version.lstrip('v')} → "
            f"{new_version.lstrip('v')} · {size_mb} MB"
        )
        meta.setObjectName("splashMeta")
        meta.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        col.addWidget(meta)

        col.addSpacing(Sizing.SPACE_SM)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(Sizing.SPACE_SM)
        btn_row.setAlignment(Qt.AlignmentFlag.AlignLeft)

        yes_btn = QPushButton("Update Now")
        yes_btn.setObjectName("splashPrimary")
        yes_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        yes_btn.clicked.connect(self.update_now.emit)
        btn_row.addWidget(yes_btn)

        no_btn = QPushButton("Skip")
        no_btn.setObjectName("splashSecondary")
        no_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        no_btn.clicked.connect(self.update_skip.emit)
        btn_row.addWidget(no_btn)

        col.addLayout(btn_row)
        row.addLayout(col, stretch=1)


def _c(hex_str: str, alpha: int = 255) -> QColor:
    col = QColor(hex_str)
    col.setAlpha(max(0, min(255, alpha)))
    return col


class _BeeScenery(QWidget):
    """Pixel scenery band that scrolls right to left behind the splash.

    Everything is drawn from integers on a fixed pixel grid rather than from
    an image, so it scales with the splash without resampling and stays crisp.
    Three parallax layers plus drifting bees; the whole band fades out into the
    card's gradient at its bottom edge so there is no hard seam.
    """

    _UNIT = 3            # size of one drawn "pixel"
    _TICK = 66           # ms per frame (~15fps; it is meant to be slow)
    _SPAN = 240          # world width of one repeat, in units

    # (period in units, height in units, colour, speed multiplier)
    _HILLS = ((60, 8, "#2b2340", 0.35), (37, 5, "#3a2d55", 0.6))
    _SPOOKY_HILLS = ((60, 8, "#24142b", 0.35), (37, 5, "#32193a", 0.6))

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self._t = 0.0
        self._timer = QTimer(self)
        self._timer.setInterval(self._TICK)
        self._timer.timeout.connect(self._advance)

    def showEvent(self, event):
        super().showEvent(event)
        self._timer.start()

    def hideEvent(self, event):
        super().hideEvent(event)
        self._timer.stop()

    def _advance(self):
        self._t += 1.0
        self.update()

    def _hive(self, p, x, y, u):
        """A skep hive: stacked bands, widest in the middle."""
        body = _c("#7a5a1f")
        dark = _c("#5d4416")
        for i, w in enumerate((3, 5, 6, 6, 5)):
            p.fillRect(int(x - w * u // 2), int(y + i * u),
                       int(w * u), u, body if i % 2 == 0 else dark)
        p.fillRect(int(x - u // 2), int(y + 5 * u), u, u, dark)

    def _flower(self, p, x, y, u, petal, bloom=1.0):
        """`bloom` 0..1 opens the head: bud, then side petals, then the top
        pair, so a row of them ripples open instead of appearing at once."""
        stem = _c("#3f6b32")
        p.fillRect(int(x), int(y), u, 4 * u, stem)
        p.fillRect(int(x - u), int(y + 2 * u), u, u, stem)   # leaf
        head_y = int(y - 2 * u)
        if bloom < 0.25:                      # closed bud
            p.fillRect(int(x), head_y + u, u, u, petal)
            return
        p.fillRect(int(x), head_y, u, u, _c("#f4c430"))      # centre
        p.fillRect(int(x - u), head_y, u, u, petal)
        p.fillRect(int(x + u), head_y, u, u, petal)
        if bloom > 0.55:
            p.fillRect(int(x), head_y - u, u, u, petal)
            p.fillRect(int(x), head_y + u, u, u, petal)
        if bloom > 0.8:
            p.fillRect(int(x - u), head_y - u, u, u, petal)
            p.fillRect(int(x + u), head_y - u, u, u, petal)

    def _grass(self, p, x, base, u, seed):
        """A tuft that leans with a slow breeze; the lean is a function of
        position so neighbouring tufts move together like a wave."""
        blade = _c("#4a3a52" if seasonal.is_halloween() else "#2f5626")
        sway = math.sin(self._t * 0.05 + seed * 0.7)
        for i, h in enumerate((2, 3, 2)):
            bx = x + (i - 1) * u
            for row in range(h):
                lean = int(round(sway * (row / max(1, h - 1)) * u))
                p.fillRect(int(bx + lean), int(base - (row + 1) * u),
                           u, u, blade)

    def _bee(self, p, x, y, u):
        gold, dark = _c("#f4c430"), _c("#1b1608")
        p.fillRect(int(x), int(y), 2 * u, 2 * u, gold)
        p.fillRect(int(x + 2 * u), int(y), u, 2 * u, dark)
        p.fillRect(int(x + 3 * u), int(y), u, 2 * u, gold)
        p.fillRect(int(x - u), int(y), u, u, dark)          # head
        wing = _c("#cfe6ff", 150 if int(self._t) % 2 else 90)
        p.fillRect(int(x + u), int(y - u), 2 * u, u, wing)

    # --- the October set: a graveyard under a low moon -----------------
    def _moon(self, p, cx, cy, u):
        """A blood-orange moon built from rows of blocks, with a faint halo."""
        rows = (3, 5, 7, 7, 7, 5, 3)
        halo = _c("#ff6a1a", 22)
        for i, wd in enumerate((5, 7, 9, 9, 9, 9, 9, 7, 5)):
            p.fillRect(int(cx - wd * u / 2), int(cy + (i - 1) * u),
                       int(wd * u), u, halo)
        body, crater = _c("#e89a3a"), _c("#c2772a")
        for i, wd in enumerate(rows):
            p.fillRect(int(cx - wd * u / 2), int(cy + i * u),
                       int(wd * u), u, body)
        p.fillRect(int(cx - 2 * u), int(cy + 2 * u), u, u, crater)
        p.fillRect(int(cx + u), int(cy + 4 * u), u, u, crater)
        p.fillRect(int(cx), int(cy + u), u, u, crater)

    def _tombstone(self, p, x, y, u):
        """A round-shouldered slab with a cross cut into it."""
        stone, cut = _c("#8a8499"), _c("#3d384a")
        for i, wd in enumerate((2, 4, 4, 4, 4)):
            p.fillRect(int(x - wd * u // 2), int(y + i * u), int(wd * u), u,
                       stone)
        p.fillRect(int(x - u // 2), int(y + u), u, 3 * u, cut)
        p.fillRect(int(x - 3 * u // 2), int(y + 2 * u), 3 * u, u, cut)

    def _pumpkin(self, p, x, y, u, glow):
        """A jack-o'-lantern; `glow` 0..1 flickers the light in its face."""
        rind = _c("#d9661a")
        for i, wd in enumerate((3, 5, 5, 3)):
            p.fillRect(int(x - wd * u // 2), int(y + i * u), int(wd * u), u,
                       rind)
        p.fillRect(int(x - u // 2), int(y - u), u, u, _c("#3f5a2a"))    # stem
        lit = _c("#ffd23f", int(140 + 115 * glow))
        p.fillRect(int(x - 3 * u // 2), int(y + u), u, u, lit)          # eyes
        p.fillRect(int(x + u // 2), int(y + u), u, u, lit)
        p.fillRect(int(x - u), int(y + 2 * u), 2 * u, u, lit)           # mouth

    def _dead_tree(self, p, x, base, u):
        """A bare trunk with a few crooked branches."""
        bark = _c("#57465f")
        p.fillRect(int(x), int(base - 8 * u), u, 8 * u, bark)
        p.fillRect(int(x - 2 * u), int(base - 6 * u), 2 * u, u, bark)
        p.fillRect(int(x - 2 * u), int(base - 8 * u), u, 2 * u, bark)
        p.fillRect(int(x + u), int(base - 5 * u), 2 * u, u, bark)
        p.fillRect(int(x + 2 * u), int(base - 7 * u), u, 2 * u, bark)
        p.fillRect(int(x + u), int(base - 9 * u), u, u, bark)

    _BAT_UP = ("#......#", "##.##.##", ".######.", "...##...")
    _BAT_DOWN = ("...##...", ".######.", "##.##.##", "#......#")

    def _bat(self, p, x, y, u):
        """A bat in two frames, wings up then down, with a pair of red eyes."""
        body = _c("#6b5580")
        up = int(self._t / 3) % 2 == 0
        rows = self._BAT_UP if up else self._BAT_DOWN
        for ry, row in enumerate(rows):
            for rx, cell in enumerate(row):
                if cell == "#":
                    p.fillRect(int(x + rx * u), int(y + ry * u), u, u, body)
        eye_y = y + (2 if up else 1) * u
        half = max(1, u // 2)
        p.fillRect(int(x + 3 * u), int(eye_y), half, half, _c("#ff3b3b"))
        p.fillRect(int(x + 4 * u + half), int(eye_y), half, half,
                   _c("#ff3b3b"))

    def paintEvent(self, _event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, False)
        spooky = seasonal.is_halloween()
        u = self._UNIT
        w, h = self.width(), self.height()
        # Ground sits well above the band's bottom edge: the fade below it is
        # what blends the scene into the card, so anything drawn at the very
        # bottom would be painted straight over.
        base = int(h * 0.62)

        if spooky:
            self._moon(p, w * 0.80, base * 0.10, u)
        for period, height, colour, speed in (
                self._SPOOKY_HILLS if spooky else self._HILLS):
            off = (self._t * speed) % (period * u)
            col = _c(colour)
            x = -off
            while x < w + period * u:
                for step in range(period):
                    # A rounded mound: tallest in the middle of the period.
                    frac = 1.0 - abs((step / period) * 2.0 - 1.0)
                    bar = int(height * u * frac)
                    if bar > 0:
                        p.fillRect(int(x + step * u), base - bar, u, bar, col)
                x += period * u

        # Ground line, then grass across it.
        p.fillRect(0, base, w, u, _c("#2a1c30" if spooky else "#243d1e"))
        tuft = 0
        gx = -((self._t * 1.0) % (6 * u))
        while gx < w:
            self._grass(p, gx, base, u, tuft)
            gx += 6 * u
            tuft += 1

        # Foreground: hives and flowers, each blooming on its own phase.
        off = (self._t * 1.0) % (self._SPAN * u)
        x = -off
        while spooky and x < w + self._SPAN * u:
            # Graves, lanterns and bare trees where the hives and
            # flowers stand the rest of the year.
            self._tombstone(p, x + 30 * u, base - 5 * u, u)
            for at, phase in ((78, 0.0), (196, 3.4)):
                flick = (math.sin(self._t * 0.23 + phase) + 1.0) / 2.0
                self._pumpkin(p, x + at * u, base - 4 * u, u, flick)
            for at in (104, 222):
                self._dead_tree(p, x + at * u, base, u)
            self._tombstone(p, x + 150 * u, base - 5 * u, u)
            x += self._SPAN * u
        while x < w + self._SPAN * u:
            self._hive(p, x + 30 * u, base - 5 * u, u)
            for at, colour, phase in ((78, "#e0609a", 0.0),
                                      (96, "#9a6fe0", 1.9),
                                      (196, "#e0609a", 3.4),
                                      (214, "#7fd4a0", 5.0)):
                bloom = (math.sin(self._t * 0.035 + phase) + 1.0) / 2.0
                self._flower(p, x + at * u, base - 3 * u, u,
                             _c(colour), bloom)
            self._hive(p, x + 150 * u, base - 5 * u, u)
            x += self._SPAN * u

        # Bees drifting across, each on its own sine.
        for i in range(3):
            speed = 1.6 + i * 0.5
            bx = w - ((self._t * speed) + i * 210) % (w + 120)
            by = (base * 0.35) + math.sin((self._t * 0.08) + i * 1.7) * 4 * u
            if spooky:
                self._bat(p, bx, by, u)
            else:
                self._bee(p, bx, by, u)

        # Fade the band into whatever is below it, starting at the ground.
        top = int(h * 0.60)
        grad = QLinearGradient(0, top, 0, h)
        grad.setColorAt(0.0, QColor(0, 0, 0, 0))
        grad.setColorAt(0.65, QColor(0, 0, 0, 205))
        grad.setColorAt(1.0, QColor(0, 0, 0, 255))
        p.fillRect(0, top, w, h - top, grad)
        p.end()


class _SplashCard(QFrame):
    """Splash surface: a dusk gradient that fades to black at the bottom,
    with the scenery band riding along its top edge."""

    def paintEvent(self, event):
        p = QPainter(self)
        grad = QLinearGradient(0, 0, 0, self.height())
        if seasonal.is_halloween():
            grad.setColorAt(0.0, QColor("#1c0a14"))
            grad.setColorAt(0.45, QColor("#0d0509"))
        else:
            grad.setColorAt(0.0, QColor("#1b1533"))
            grad.setColorAt(0.45, QColor("#120e20"))
        grad.setColorAt(1.0, QColor("#000000"))
        p.fillRect(self.rect(), grad)
        p.end()
        super().paintEvent(event)

class SplashWidget(QWidget):
    """Splash container hosting one of two panes (loading / prompt)."""

    status_changed = Signal(str)
    update_now = Signal()
    update_skip = Signal()

    close_clicked = Signal()

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("root")
        self._animated_progress = 0.0
        self._progress_anim: QPropertyAnimation | None = None
        self._prompt_pane: _UpdatePromptPane | None = None
        self._build_ui()
        self._build_close_btn()

    def _build_ui(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self._card = _SplashCard(self)
        self._card.setObjectName("splashCard")
        # Opaque bg: transparent tip / status labels would ghost otherwise.
        # WA_StyledBackground lets the card's QSS gradient repaint behind them.
        self._card.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)

        card_lay = QVBoxLayout(self._card)
        # Tighter padding so the landscape splash isn't eaten by margins.
        card_lay.setContentsMargins(
            Sizing.SPACE_LG, Sizing.SPACE_LG, Sizing.SPACE_LG, Sizing.SPACE_SM
        )
        card_lay.setSpacing(0)

        # Scenery sits behind the panes, pinned to the card's top band.
        self._scenery = _BeeScenery(self._card)
        self._scenery.lower()

        self._stack = QStackedWidget(self._card)
        self._loading = _LoadingPane(self._stack)
        self._stack.addWidget(self._loading)
        card_lay.addWidget(self._stack, stretch=1)

        # Version footer; hidden on the update prompt (would duplicate the diff).
        self._ver = QLabel(f"v{_read_version().lstrip('v')}")
        self._ver.setObjectName("splashVersion")
        self._ver.setAlignment(Qt.AlignmentFlag.AlignCenter)
        card_lay.addWidget(self._ver)

        outer.addWidget(self._card)

    def _build_close_btn(self):
        """Floating close button, absolutely pinned over either pane."""
        self._close_btn = QPushButton("✕", self)
        self._close_btn.setObjectName("splashClose")
        self._close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._close_btn.clicked.connect(self.close_clicked.emit)
        self._close_btn.raise_()
        self._reposition_close_btn()

    def _resize_scenery(self):
        band = max(48, int(self._card.height() * 0.55))
        self._scenery.setGeometry(0, 0, self._card.width(), band)

    def _reposition_close_btn(self):
        margin = Sizing.SPACE_MD
        self._close_btn.move(
            self.width() - self._close_btn.width() - margin,
            margin,
        )

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if hasattr(self, "_close_btn"):
            self._reposition_close_btn()
        if hasattr(self, "_scenery"):
            self._resize_scenery()

    # Animated progress drives the loading bar.
    def _get_progress(self) -> float:
        return self._animated_progress

    def _set_progress(self, v: float):
        self._animated_progress = v
        self._loading.bar.setValue(int(v))

    animatedProgress = Property(float, _get_progress, _set_progress)

    # Public API
    def set_status(self, text: str, percent: int | None = None):
        if self._stack.currentWidget() is not self._loading:
            self._stack.setCurrentWidget(self._loading)
        self._loading.apply_status(text)
        self.status_changed.emit(text)
        if percent is not None:
            self.animate_to(percent)

    def animate_to(self, percent: int):
        percent = max(0, min(100, int(percent)))
        if self._progress_anim is not None:
            self._progress_anim.stop()
        anim = QPropertyAnimation(self, b"animatedProgress", self)
        anim.setDuration(380)
        anim.setStartValue(self._animated_progress)
        anim.setEndValue(float(percent))
        anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._progress_anim = anim
        anim.start()

    def set_subtitle(self, text: str):
        """Pin subtitle text; tip rotation resumes on show_loading()."""
        self._loading.pin_subtitle(text)

    def show_update_prompt(self, current: str, new: str, size_mb: int):
        """Swap in the update prompt, wiring its buttons to update_now / update_skip."""
        if self._prompt_pane is not None:
            self._stack.removeWidget(self._prompt_pane)
            self._prompt_pane.deleteLater()
        self._prompt_pane = _UpdatePromptPane(current, new, size_mb, self._stack)
        self._prompt_pane.update_now.connect(self.update_now.emit)
        self._prompt_pane.update_skip.connect(self.update_skip.emit)
        self._stack.addWidget(self._prompt_pane)
        self._stack.setCurrentWidget(self._prompt_pane)
        self._ver.hide()

    def show_loading(self):
        if self._stack.currentWidget() is not self._loading:
            self._stack.setCurrentWidget(self._loading)
        self._ver.show()
        self._loading.resume_tips()

    def set_subtle(self, text: str):
        # Back-compat for error display.
        self._loading.status.setText(text)

    def stop_spinner(self):
        self._loading.spinner.stop()
