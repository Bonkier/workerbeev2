# SPDX-License-Identifier: GPL-3.0-or-later
"""Initializing-screen splash, crossfaded out when init finishes."""

import os
import random

from PySide6.QtCore import (
    Property, QEasingCurve, QPropertyAnimation, Qt, QTimer, Signal,
)
from PySide6.QtGui import QIcon, QPixmap
from PySide6.QtWidgets import (
    QFrame, QHBoxLayout, QLabel, QProgressBar, QPushButton, QStackedWidget,
    QVBoxLayout, QWidget,
)

from .spinner import Spinner
from .theme import Sizing


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

        icon_pix = _load_app_icon(72)
        if icon_pix is not None:
            icon_lbl = QLabel(self)
            icon_lbl.setPixmap(icon_pix)
            icon_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            icon_lbl.setFixedSize(72, 72)
            row.addWidget(icon_lbl, alignment=Qt.AlignmentFlag.AlignVCenter)

        # Title + subtitle + progress + status, filling remaining width.
        text_col = QVBoxLayout()
        text_col.setSpacing(Sizing.SPACE_SM)
        text_col.setAlignment(Qt.AlignmentFlag.AlignVCenter)

        title = QLabel("WorkerBee")
        title.setObjectName("splashTitle")
        title.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        text_col.addWidget(title)

        self.subtitle = QLabel("")
        self.subtitle.setObjectName("splashSubtitle")
        self.subtitle.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        text_col.addWidget(self.subtitle)

        # Tip rotation, paused when explicit subtitle text is pinned.
        self._tips = list(_LOADING_TIPS)
        random.shuffle(self._tips)
        self._tip_index = 0
        self._tips_pinned = False
        self._current_subtitle_raw = self._tips[0]
        self._apply_subtitle(self._tips[0])
        # Re-apply post-layout so elision uses the real label width (currently 0).
        QTimer.singleShot(0, lambda: self._apply_subtitle(self._current_subtitle_raw))

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
        status_row.addWidget(self.status, stretch=1)
        text_col.addLayout(status_row)

        row.addLayout(text_col, stretch=1)

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

        icon_pix = _load_app_icon(72)
        if icon_pix is not None:
            icon_lbl = QLabel(self)
            icon_lbl.setPixmap(icon_pix)
            icon_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            icon_lbl.setFixedSize(72, 72)
            row.addWidget(icon_lbl, alignment=Qt.AlignmentFlag.AlignVCenter)

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

        self._card = QFrame(self)
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
        # Explicit elide so the trailing counter (e.g. "X / Y MB") survives.
        lbl = self._loading.status
        avail = lbl.width()
        if avail <= 0:
            avail = 260              # pre-layout fallback
        fm = lbl.fontMetrics()
        lbl.setText(fm.elidedText(text, Qt.TextElideMode.ElideRight, avail))
        # Tooltip keeps the raw text for narrow splash sizes.
        lbl.setToolTip(text)
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
