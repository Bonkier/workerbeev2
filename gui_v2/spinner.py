# SPDX-License-Identifier: GPL-3.0-or-later
"""Indeterminate rotating-arc spinner."""

from PySide6.QtCore import Qt, QTimer, QRectF
from PySide6.QtGui import QPainter, QPen, QColor
from PySide6.QtWidgets import QWidget

from .theme import Colors


class Spinner(QWidget):
    def __init__(self, parent=None, size: int = 28, line_width: int = 3):
        super().__init__(parent)
        self.setFixedSize(size, size)
        self._size = size
        self._line_width = line_width
        self._angle = 0
        # ~60 fps.
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._timer.start(16)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)

    def _tick(self):
        # 6 deg/frame ~ 1s full rotation.
        self._angle = (self._angle + 6) % 360
        self.update()

    def stop(self):
        self._timer.stop()

    def paintEvent(self, _event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        pad = self._line_width
        rect = QRectF(pad, pad, self._size - 2 * pad, self._size - 2 * pad)
        # Faint background ring so the arc stays visible on dark bg.
        bg_color = QColor(Colors.ACCENT)
        bg_color.setAlphaF(0.18)
        p.setPen(QPen(bg_color, self._line_width, Qt.PenStyle.SolidLine,
                       Qt.PenCapStyle.RoundCap))
        p.drawArc(rect, 0, 360 * 16)
        # ~90 deg rotating arc.
        p.setPen(QPen(QColor(Colors.ACCENT), self._line_width,
                      Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        # drawArc uses 16ths of a degree; negative span = clockwise.
        p.drawArc(rect, -self._angle * 16, -90 * 16)
        p.end()
