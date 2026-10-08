# SPDX-License-Identifier: GPL-3.0-or-later
"""Click and hover feedback for every button in the app.

Qt stylesheets have no transitions, so a QSS `:hover` / `:pressed` rule snaps
between states with nothing in between and the UI feels dead. This installs a
transparent overlay on each button that animates the feedback itself:

  hover   a 2px accent rule wipes in along the bottom edge
  press   the face darkens and a 1px inset edge appears on the top/left, so
          the control reads as pushed in
  click   an accent flash fills the face and fades out

The overlay is a child widget, so it paints after (over) whatever the button
draws - QSS-styled or custom-painted, both work - and it never touches the
button's own geometry, so no layout can be disturbed. It is transparent to
mouse events, so hit-testing is unchanged.

Everything is square and stepped rather than soft, to match the skin.
"""

from PySide6.QtCore import (
    Property, QEasingCurve, QEvent, QObject, QPropertyAnimation, Qt,
)
from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import QAbstractButton, QWidget

from .theme import Colors, Motion

_ATTR = "_wb_feedback"

# Buttons that already animate their whole face are left alone: a second
# overlay on top of them reads as a double response.
_SKIP_CLASSES = ("Toggle",)
# Buttons whose bottom edge is already spoken for (the gift tiles carry their
# role bar there) get the flash and press shading, but no hover rule.
_NO_RULE_CLASSES = ("_GiftTile", "_MarketGiftTile", "_KeywordTab")


class _Feedback(QWidget):
    """Overlay that paints the hover rule, press shading and click flash."""

    def __init__(self, button: QAbstractButton):
        super().__init__(button)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground, True)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._btn = button
        self._rule = button.__class__.__name__ not in _NO_RULE_CLASSES
        self._hover = 0.0
        self._flash = 0.0
        self._down = False

        self._hover_anim = QPropertyAnimation(self, b"hoverPos", self)
        self._hover_anim.setDuration(Motion.INSTANT)
        self._hover_anim.setEasingCurve(QEasingCurve.Type.OutCubic)

        self._flash_anim = QPropertyAnimation(self, b"flashPos", self)
        self._flash_anim.setDuration(Motion.NORMAL)
        self._flash_anim.setEasingCurve(QEasingCurve.Type.OutCubic)

        self.setGeometry(button.rect())
        self.show()
        self.raise_()

    # --- animated properties ---------------------------------------
    def _get_hover(self):
        return self._hover

    def _set_hover(self, v):
        self._hover = v
        self.update()

    hoverPos = Property(float, _get_hover, _set_hover)

    def _get_flash(self):
        return self._flash

    def _set_flash(self, v):
        self._flash = v
        self.update()

    flashPos = Property(float, _get_flash, _set_flash)

    # --- triggers ---------------------------------------------------
    def _run(self, anim, to):
        anim.stop()
        anim.setStartValue(anim.targetObject().property(
            bytes(anim.propertyName()).decode()))
        anim.setEndValue(to)
        anim.start()

    def hover(self, on: bool):
        self._run(self._hover_anim, 1.0 if on else 0.0)

    def press(self, down: bool):
        self._down = down
        if down:
            self._flash_anim.stop()
            self._flash = 0.55
        self.update()

    def flash(self):
        self._flash_anim.stop()
        self._flash = 1.0
        self._run(self._flash_anim, 0.0)

    # --- paint ------------------------------------------------------
    def paintEvent(self, _e):
        if self._hover <= 0.0 and self._flash <= 0.0 and not self._down:
            return
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, False)
        w, h = self.width(), self.height()

        # Feedback has to read against the button's own fill: accent on an
        # accent-filled button is invisible, so those flip to white.
        light = self._btn.objectName() in ("primaryCta", "splashPrimary")
        tone = "#ffffff" if light else Colors.ACCENT

        if self._down:
            p.fillRect(0, 0, w, h, QColor(0, 0, 0, 60))
            p.fillRect(0, 0, w, 1, QColor(0, 0, 0, 90))
            p.fillRect(0, 0, 1, h, QColor(0, 0, 0, 90))
        if self._flash > 0.0:
            tint = QColor(tone)
            tint.setAlpha(int(110 * min(1.0, self._flash)))
            p.fillRect(0, 0, w, h, tint)
        if self._hover > 0.0 and self._rule:
            rule = QColor(tone)
            rule.setAlpha(210)
            p.fillRect(0, h - 2, int(w * self._hover), 2, rule)
        p.end()


_TRACKED = frozenset((
    QEvent.Type.Enter, QEvent.Type.Leave, QEvent.Type.MouseButtonPress,
    QEvent.Type.MouseButtonRelease, QEvent.Type.Resize, QEvent.Type.Show,
))


class _Watcher(QObject):
    """One application-wide filter. Overlays are created on first contact
    rather than up front: the market gallery alone holds ~380 gift tiles, and
    pre-building an overlay for every one of them costs memory and paint time
    for controls the user may never touch."""

    def eventFilter(self, obj, event):
        et = event.type()
        if et not in _TRACKED:
            return False
        fb = getattr(obj, _ATTR, None)
        if fb is None:
            if et not in (QEvent.Type.Enter, QEvent.Type.MouseButtonPress):
                return False
            fb = attach(obj)
            if fb is None:
                return False
        if et == QEvent.Type.Resize:
            fb.setGeometry(obj.rect())
        elif et == QEvent.Type.Enter:
            fb.hover(True)
        elif et == QEvent.Type.Leave:
            fb.hover(False)
            fb.press(False)
        elif et == QEvent.Type.MouseButtonPress:
            fb.press(True)
        elif et == QEvent.Type.MouseButtonRelease:
            fb.press(False)
            if obj.rect().contains(event.position().toPoint()):
                fb.flash()
        elif et == QEvent.Type.Show:
            fb.setGeometry(obj.rect())
            fb.raise_()
        return False


_watcher = None


def attach(button):
    """Give one button its feedback overlay, or None if it opts out."""
    if not isinstance(button, QAbstractButton):
        return None
    fb = getattr(button, _ATTR, None)
    if fb is not None:
        return fb
    if button.__class__.__name__ in _SKIP_CLASSES:
        return None
    fb = _Feedback(button)
    setattr(button, _ATTR, fb)
    return fb


def install(app):
    """Hook every button in the app, including ones built later. One filter on
    the application covers the lot - no per-button bookkeeping."""
    global _watcher
    if _watcher is not None:
        return
    _watcher = _Watcher(app)
    app.installEventFilter(_watcher)
