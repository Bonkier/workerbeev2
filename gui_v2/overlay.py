# SPDX-License-Identifier: GPL-3.0-or-later
"""Translucent click-through overlay drawn over the Limbus window during a run.

Three independent layers: HUD (phase/run counter/etc), Vision (labelled boxes
around located templates), Path (cursor target + traced path).

The window is frameless, top-most, input-transparent, and never takes focus.
It pins to params.WINDOW and hides while the WorkerBee window is foreground.

Incoming coords are LOGICAL 1920x1080, scaled to the live window at paint.
"""

import collections
import ctypes
import logging
import math
import random
import re
import time

from PySide6.QtCore import Qt, QTimer, QRectF, QPointF
from PySide6.QtGui import (
    QColor, QFont, QGuiApplication, QPainter, QPen, QPolygonF,
)
from PySide6.QtWidgets import QWidget

from .theme import Colors, Fonts

_LOGICAL_W, _LOGICAL_H = 1920.0, 1080.0
_MATCH_TTL = 1.6   # seconds a 'seen' box lingers before fading out
_SANS = Fonts.FAMILY.split(",")[0].strip()
_MONO = Fonts.FAMILY_MONO.split(",")[0].strip()

_BEE_PHRASES = (
    "pollinating...", "buzzing...", "making honey", "bzzzz",
    "hard at work", "found nectar!", "to the hive!", "tending the grind",
    "beep beep", "so many mirrors", "the grind never stops", "for the swarm",
    "sweet sweet EXP", "just one more run", "clicking away", "stay golden",
    "worker bee reporting", "honey incoming", "zoom zoom", "busy busy busy",
    "another floor down", "nectar acquired", "buzzin' along", "good luck!",
)


def _c(hex_str: str, alpha: int = 255) -> QColor:
    col = QColor(hex_str)
    col.setAlpha(max(0, min(255, alpha)))
    return col


class RunOverlay(QWidget):

    def __init__(self, owner_hwnd_getter=None):
        super().__init__(None)
        self._owner_hwnd = owner_hwnd_getter or (lambda: 0)

        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
            | Qt.WindowType.WindowTransparentForInput
            | Qt.WindowType.WindowDoesNotAcceptFocus
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)

        self._show_hud = True
        self._show_vision = False
        self._show_path = False
        self._run_active = False
        self._capture_excluded = False

        # Capture self-test: SetWindowDisplayAffinity should hide us from
        # the bot's grab, but raw GDI BitBlt doesn't honor it on every
        # Windows build. After first show we paint a magenta sentinel and
        # grab via the bot's capture path - if it shows up, hide.
        # None = not tested; False = safe; True = visible -> stay hidden.
        self._capturable = None
        self._probe_scheduled = False
        self._probe_active = False

        self._phase = "Idle"
        self._floor = None
        self._pack = None
        self._actions = collections.deque(maxlen=5)
        self._run = None            # (i, total)
        self._run_start = None      # time.time() when the current run began
        self._target = None         # (x, y) logical
        self._path = []             # [(x, y)] logical
        self._matches = []          # [(name, (x, y, w, h), t)]
        self._dirty = True

        self._panel_rect = QRectF(16, 16, 330, 120)
        self._bee_t = 0.0
        self._bee_phase = 0.0
        self._bee_speech = None
        self._bee_speech_start = 0.0
        self._bee_speech_until = 0.0
        self._bee_next_speech = time.time() + 3.0
        self._bee_trail = collections.deque(maxlen=18)
        self._bee_face = 1.0          # smoothed facing (-1 left .. +1 right)
        self._bee_face_target = 1.0
        self._bee_tilt = 0.0          # smoothed vertical lean, radians

        self._geo_timer = QTimer(self)
        self._geo_timer.setInterval(150)
        self._geo_timer.timeout.connect(self._track)
        self._geo_timer.start()

        self._paint_timer = QTimer(self)
        self._paint_timer.setInterval(50)   # 20fps; repaints only when needed
        self._paint_timer.timeout.connect(self._tick)
        self._paint_timer.start()

    # --- external API ----------------------------------------------
    def set_toggles(self, hud: bool, vision: bool, path: bool):
        self._show_hud = bool(hud)
        self._show_vision = bool(vision)
        self._show_path = bool(path)
        self._dirty = True

    def set_run_active(self, active: bool):
        self._run_active = bool(active)
        if active:
            self._run_start = time.time()
        else:
            self._matches.clear()
            self._path = []
            self._target = None
            self._bee_trail.clear()
            self._floor = None
            self._pack = None
            self._run_start = None
        self._dirty = True

    def on_event(self, ev: dict):
        """Telemetry events queued from the bot thread."""
        kind = ev.get("kind")
        if kind == "phase":
            self._phase = ev.get("name", "")
        elif kind == "action":
            text = ev.get("text", "")
            if text:
                self._actions.append(text)
                self._derive_from_action(text)
        elif kind == "run":
            new_run = (ev.get("i", 0), ev.get("total", 0))
            if self._run is None or new_run[0] != self._run[0]:
                self._run_start = time.time()
            self._run = new_run
        elif kind == "match":
            self._matches.append(
                (ev.get("name", ""), ev.get("region"), time.time()))
            if len(self._matches) > 40:
                self._matches = self._matches[-40:]
        elif kind == "target":
            x, y = ev.get("x"), ev.get("y")
            self._target = (x, y) if x is not None and y is not None else None
            self._path = ev.get("path", []) or []
        elif kind == "reset":
            self._phase = "Idle"
            self._floor = None
            self._pack = None
            self._actions.clear()
            self._run = None
            self._run_start = None
            self._target = None
            self._path = []
            self._matches.clear()
        self._dirty = True

    def _derive_from_action(self, text: str):
        """Extract phase/floor/pack from the bot's log lines."""
        low = text.lower()
        m = re.search(r"floor\s+(\d+)", low)
        if m:
            self._floor = m.group(1)
            self._phase = f"Floor {m.group(1)}"
        if "pack:" in low:
            self._pack = text.split(":", 1)[1].strip()
            self._phase = "Picking pack"
        elif "boss fight" in low:
            self._phase = "Boss fight"
        elif "entering" in low and "fight" in low:
            self._phase = "Fighting"
        elif "battle is over" in low:
            self._phase = "Battle won"
        elif "entering event" in low:
            self._phase = "Event"
        elif "entering shop" in low:
            self._phase = "Shop"
        elif "run completed" in low:
            self._phase = "Run complete"
        elif "run failed" in low:
            self._phase = "Run failed"

    # --- geometry + visibility -------------------------------------
    def _track(self):
        win = self._game_rect()
        wants = (
            self._run_active
            and (self._show_hud or self._show_vision or self._show_path)
            and win is not None
            and not self._workerbee_focused()
            # Self-test found the bot can see us: stay hidden.
            and self._capturable is not True
        )
        if not wants:
            if self.isVisible():
                self.hide()
            return
        # p.WINDOW is physical px; divide by DPR for scaled displays.
        dpr = self._dpr()
        x, y = round(win[0] / dpr), round(win[1] / dpr)
        w, h = round(win[2] / dpr), round(win[3] / dpr)
        if (self.x(), self.y(), self.width(), self.height()) != (x, y, w, h):
            self.setGeometry(x, y, w, h)
        if not self.isVisible():
            self.show()
        # First time up over the game: schedule the capture self-test
        # (needs the window shown + composited first).
        if self._capturable is None and not self._probe_scheduled:
            self._probe_scheduled = True
            QTimer.singleShot(300, self._run_capture_probe)

    @staticmethod
    def _dpr() -> float:
        try:
            scr = QGuiApplication.primaryScreen()
            d = scr.devicePixelRatio() if scr is not None else 1.0
            return d if d and d > 0 else 1.0
        except Exception:
            return 1.0

    def showEvent(self, event):
        super().showEvent(event)
        # Exclude from capture so the bot's grab doesn't see our drawings.
        if not self._capture_excluded:
            self._capture_excluded = self._exclude_from_capture()

    def _exclude_from_capture(self) -> bool:
        try:
            import ctypes as _ct
            hwnd = int(self.winId())
            # WDA_EXCLUDEFROMCAPTURE (Win10 2004+): honored by DWM-based
            # capture but NOT reliably by raw GDI BitBlt - the self-test
            # guards against that.
            ok = _ct.windll.user32.SetWindowDisplayAffinity(hwnd, 0x11)
            if not ok:
                # WDA_MONITOR fallback for very old builds.
                _ct.windll.user32.SetWindowDisplayAffinity(hwnd, 0x01)
            return True
        except Exception:
            return False

    # --- capture self-test -----------------------------------------
    def _probe_rect(self):
        """Sentinel rect overlapping the HUD and the bot's gate templates.
        Short (150px) so the calibration flash is unobtrusive."""
        from PySide6.QtCore import QRect
        w = min(360, self.width())
        h = min(150, self.height())
        return QRect(0, 0, max(1, w), max(1, h))

    def _run_capture_probe(self):
        # Paint the sentinel, then grab after DWM composites it.
        if self._capturable is not None or not self.isVisible():
            return
        self._probe_active = True
        self.repaint()
        QTimer.singleShot(140, self._finish_capture_probe)

    def _finish_capture_probe(self):
        try:
            seen = self._sentinel_in_bot_capture()
        except Exception as exc:
            # Fail safe: assume the bot can see us.
            logging.warning(
                "RunOverlay: capture self-test errored (%s); hiding overlay "
                "to be safe.", exc)
            seen = True
        self._probe_active = False
        self._capturable = bool(seen)
        if self._capturable:
            logging.warning(
                "RunOverlay: the bot's screen capture CAN see this overlay "
                "(SetWindowDisplayAffinity not honored here) - hiding the "
                "overlay so it cannot occlude template matching.")
            self.hide()
        else:
            logging.info(
                "RunOverlay: capture self-test passed - overlay is excluded "
                "from the bot's capture.")
            self.update()

    def _sentinel_in_bot_capture(self) -> bool:
        """True if the magenta sentinel shows up in the bot's grab."""
        import numpy as np
        from wbcore.utils.os_windows_backend import screenshot as bot_grab

        dpr = self._dpr()
        r = self._probe_rect()
        x = int(round((self.x() + r.x()) * dpr))
        y = int(round((self.y() + r.y()) * dpr))
        w = int(round(r.width() * dpr))
        h = int(round(r.height() * dpr))
        if w <= 0 or h <= 0:
            return False

        arr = bot_grab(region=(x, y, w, h))   # H x W x 3, BGR
        if arr is None or getattr(arr, "size", 0) == 0:
            return False
        b = arr[:, :, 0].astype(np.int16)
        g = arr[:, :, 1].astype(np.int16)
        red = arr[:, :, 2].astype(np.int16)
        # Near-magenta never occurs in the game's reds/golds/browns.
        magenta = (red > 180) & (b > 180) & (g < 90)
        return float(magenta.mean()) > 0.25

    @staticmethod
    def _game_rect():
        try:
            import wbcore.utils.params as p
            win = p.WINDOW
        except Exception:
            return None
        if not win or len(win) != 4:
            return None
        x, y, w, h = (int(win[0]), int(win[1]), int(win[2]), int(win[3]))
        if w <= 1 or h <= 1:
            return None
        return x, y, w, h

    def _workerbee_focused(self) -> bool:
        try:
            fg = ctypes.windll.user32.GetForegroundWindow()
            return int(fg) == int(self._owner_hwnd() or 0)
        except Exception:
            return False

    def _tick(self):
        if not self.isVisible():
            return
        if self._matches:
            now = time.time()
            kept = [m for m in self._matches if now - m[2] <= _MATCH_TTL]
            if len(kept) != len(self._matches):
                self._matches = kept
                self._dirty = True
        if self._show_hud:
            self._step_bee()
        # Repaint when transient content or the bee is animating.
        if (self._dirty or self._matches or self._path or self._target
                or self._show_hud):
            self._dirty = False
            self.update()

    # --- painting --------------------------------------------------
    def paintEvent(self, _event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        if self._probe_active:
            # Calibration frame for the capture self-test.
            painter.fillRect(self._probe_rect(), QColor(255, 0, 255, 255))
            return
        w, h = self.width(), self.height()
        sx, sy = w / _LOGICAL_W, h / _LOGICAL_H
        if self._show_vision:
            self._paint_matches(painter, sx, sy)
        if self._show_path:
            self._paint_path(painter, sx, sy)
        if self._show_hud:
            self._paint_hud(painter)
            self._paint_bee(painter)

    def _paint_matches(self, painter: QPainter, sx: float, sy: float):
        now = time.time()
        font = QFont(_SANS, 9)
        font.setBold(True)
        painter.setFont(font)
        fm = painter.fontMetrics()
        for name, region, t in self._matches:
            if not region:
                continue
            alpha = max(0.0, 1.0 - (now - t) / _MATCH_TTL)
            x, y, ww, hh = region
            box = QRectF(x * sx, y * sy, ww * sx, hh * sy)
            pen = QPen(_c(Colors.ACCENT, int(235 * alpha)))
            pen.setWidth(2)
            painter.setPen(pen)
            painter.setBrush(_c(Colors.ACCENT, int(38 * alpha)))
            painter.drawRect(box)

            label = str(name)
            tw = fm.horizontalAdvance(label) + 12
            th = fm.height() + 4
            lx = box.left()
            ly = box.top() - th - 2
            if ly < 0:
                ly = box.top() + 2
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(_c("#0a0a0b", int(195 * alpha)))
            painter.drawRect(QRectF(lx, ly, tw, th))
            painter.setPen(_c(Colors.ACCENT, int(255 * alpha)))
            painter.drawText(QRectF(lx + 6, ly, tw, th),
                             Qt.AlignmentFlag.AlignVCenter
                             | Qt.AlignmentFlag.AlignLeft, label)

    def _paint_path(self, painter: QPainter, sx: float, sy: float):
        if self._path and len(self._path) >= 2:
            pen = QPen(_c(Colors.INFO, 205))
            pen.setWidth(2)
            painter.setPen(pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawPolyline(
                QPolygonF([QPointF(px * sx, py * sy) for px, py in self._path]))
        if self._target:
            tx = self._target[0] * sx
            ty = self._target[1] * sy
            pen = QPen(_c(Colors.ERROR, 240))
            pen.setWidth(2)
            painter.setPen(pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            radius = 13.0
            painter.drawEllipse(QPointF(tx, ty), radius, radius)
            painter.drawLine(QPointF(tx - radius - 6, ty),
                             QPointF(tx + radius + 6, ty))
            painter.drawLine(QPointF(tx, ty - radius - 6),
                             QPointF(tx, ty + radius + 6))

    def _paint_hud(self, painter: QPainter):
        margin = 16
        pad = 12
        pw = 330
        line_h = 20

        rows = 7  # header, phase, floor, pack, target, tracer, run time
        show_actions = len(self._actions) > 0
        if show_actions:
            rows += 1 + len(self._actions)
        panel_h = 2 * pad + rows * line_h

        panel = QRectF(margin, margin, pw, panel_h)
        self._panel_rect = panel
        painter.setPen(QPen(_c(Colors.ACCENT, 110), 1))
        painter.setBrush(_c("#0c0c0e", 210))
        painter.drawRoundedRect(panel, 10, 10)

        x = margin + pad
        inner_w = pw - 2 * pad
        y = margin + pad

        head = QFont(_SANS, 11)
        head.setBold(True)
        painter.setFont(head)
        painter.setPen(_c(Colors.ACCENT, 255))
        painter.drawText(QRectF(x, y, inner_w, line_h),
                         Qt.AlignmentFlag.AlignVCenter
                         | Qt.AlignmentFlag.AlignLeft, "WorkerBee")
        if self._run:
            painter.setFont(QFont(_MONO, 10))
            painter.setPen(_c(Colors.TEXT_SECONDARY, 255))
            painter.drawText(QRectF(x, y, inner_w, line_h),
                             Qt.AlignmentFlag.AlignVCenter
                             | Qt.AlignmentFlag.AlignRight,
                             f"Run {self._run[0]} / {self._run[1]}")
        y += line_h

        self._hud_row(painter, x, y, inner_w, "Phase",
                      self._phase or "-", Colors.TEXT_PRIMARY)
        y += line_h
        self._hud_row(painter, x, y, inner_w, "Floor",
                      self._floor or "-", Colors.TEXT_PRIMARY, mono=True)
        y += line_h
        self._hud_row(painter, x, y, inner_w, "Pack",
                      self._pack or "-", Colors.ACCENT)
        y += line_h
        target_txt = ("-" if not self._target
                      else f"{int(self._target[0])}, {int(self._target[1])}")
        self._hud_row(painter, x, y, inner_w, "Target",
                      target_txt, Colors.TEXT_PRIMARY, mono=True)
        y += line_h
        tracer_on = self._show_path
        self._hud_row(painter, x, y, inner_w, "Path tracer",
                      "ON" if tracer_on else "OFF",
                      Colors.SUCCESS if tracer_on else Colors.TEXT_TERTIARY)
        y += line_h
        elapsed = ("-" if self._run_start is None
                   else self._fmt_elapsed(time.time() - self._run_start))
        self._hud_row(painter, x, y, inner_w, "Run time",
                      elapsed, Colors.TEXT_PRIMARY, mono=True)
        y += line_h

        if show_actions:
            painter.setFont(QFont(_SANS, 8))
            painter.setPen(_c(Colors.TEXT_TERTIARY, 255))
            painter.drawText(QRectF(x, y, inner_w, line_h),
                             Qt.AlignmentFlag.AlignVCenter
                             | Qt.AlignmentFlag.AlignLeft, "RECENT")
            y += line_h
            painter.setFont(QFont(_SANS, 9))
            for text in self._actions:
                painter.setPen(_c(Colors.TEXT_SECONDARY, 255))
                elided = painter.fontMetrics().elidedText(
                    text, Qt.TextElideMode.ElideRight, int(inner_w))
                painter.drawText(QRectF(x, y, inner_w, line_h),
                                 Qt.AlignmentFlag.AlignVCenter
                                 | Qt.AlignmentFlag.AlignLeft, elided)
                y += line_h

    def _hud_row(self, painter, x, y, w, label, value, value_color,
                 mono=False):
        label_w = 96
        painter.setFont(QFont(_SANS, 9))
        painter.setPen(_c(Colors.TEXT_TERTIARY, 255))
        painter.drawText(QRectF(x, y, label_w, 20),
                         Qt.AlignmentFlag.AlignVCenter
                         | Qt.AlignmentFlag.AlignLeft, label)
        painter.setFont(QFont(_MONO if mono else _SANS, 10))
        painter.setPen(_c(value_color, 255))
        painter.drawText(QRectF(x + label_w, y, w - label_w, 20),
                         Qt.AlignmentFlag.AlignVCenter
                         | Qt.AlignmentFlag.AlignLeft, str(value))

    @staticmethod
    def _fmt_elapsed(secs: float) -> str:
        secs = int(max(0, secs))
        h, rem = divmod(secs, 3600)
        m, s = divmod(rem, 60)
        return f"{h}:{m:02d}:{s:02d}" if h else f"{m:02d}:{s:02d}"

    # --- mascot bee ------------------------------------------------
    def _step_bee(self):
        self._bee_t = (self._bee_t + 0.003) % 1.0
        self._bee_phase += 0.9
        # Smoothed mirror/tilt so corner turns ease in and never flip upside down.
        _, _, dx, dy = self._bee_pos()
        if abs(dx) > 0.1:
            self._bee_face_target = 1.0 if dx > 0 else -1.0
        self._bee_face += (self._bee_face_target - self._bee_face) * 0.1
        tilt_target = max(-0.6, min(0.6, dy * 0.6))
        self._bee_tilt += (tilt_target - self._bee_tilt) * 0.1
        now = time.time()
        if self._bee_speech is not None:
            if now >= self._bee_speech_until:
                self._bee_speech = None
                self._bee_next_speech = now + random.uniform(5.0, 9.0)
        elif now >= self._bee_next_speech:
            self._bee_speech = random.choice(_BEE_PHRASES)
            self._bee_speech_start = now
            self._bee_speech_until = now + 3.2

    def _bee_orbit_rect(self) -> QRectF:
        # Orbit outside the panel, clamped so the sprite never clips edges.
        pad = 24.0
        r = self._panel_rect.adjusted(-14, -14, 14, 14)
        left = max(r.left(), pad)
        top = max(r.top(), pad)
        right = min(r.right(), self.width() - pad)
        bottom = min(r.bottom(), self.height() - pad)
        if right - left < 2:
            right = left + 2
        if bottom - top < 2:
            bottom = top + 2
        return QRectF(left, top, right - left, bottom - top)

    def _bee_pos(self):
        # Walk the orbit perimeter; returns (x, y, dx, dy).
        rect = self._bee_orbit_rect()
        x0, y0 = rect.left(), rect.top()
        w, h = rect.width(), rect.height()
        d = self._bee_t * (2 * (w + h))
        if d < w:
            return x0 + d, y0, 1.0, 0.0
        d -= w
        if d < h:
            return x0 + w, y0 + d, 0.0, 1.0
        d -= h
        if d < w:
            return x0 + w - d, y0 + h, -1.0, 0.0
        d -= w
        return x0, y0 + h - d, 0.0, -1.0

    def _paint_bee(self, painter: QPainter):
        px, py, dx, dy = self._bee_pos()
        # Buzz wobble perpendicular to travel.
        wob = math.sin(self._bee_phase * 0.5) * 3.0
        px += -dy * wob
        py += dx * wob
        # Clamp so the sprite stays inside the overlay.
        px = max(24.0, min(px, self.width() - 24.0))
        py = max(18.0, min(py, self.height() - 18.0))

        self._bee_trail.append((px, py))
        self._draw_trail(painter)

        if self._bee_speech:
            now = time.time()
            alpha = max(0.0, min(1.0,
                                 (now - self._bee_speech_start) / 0.3,
                                 (self._bee_speech_until - now) / 0.5))
            if alpha > 0.0:
                self._draw_speech(painter, px, py, self._bee_speech, alpha)
        self._draw_bee(painter, px, py)

    def _draw_trail(self, painter: QPainter):
        n = len(self._bee_trail)
        if n < 4:
            return
        painter.setPen(Qt.PenStyle.NoPen)
        # Skip the two newest points so it starts just behind the bee.
        for i in range(0, n - 2, 2):
            tx, ty = self._bee_trail[i]
            frac = i / n
            painter.setBrush(_c(Colors.ACCENT, int(95 * frac)))
            r = 1.2 + 0.7 * frac
            painter.drawEllipse(QPointF(tx, ty), r, r)

    def _draw_bee(self, painter: QPainter, x: float, y: float):
        painter.save()
        painter.translate(x, y)
        # scaleX through ~0 reads as the bee turning around.
        sign = 1.0 if self._bee_face >= 0 else -1.0
        painter.rotate(math.degrees(self._bee_tilt) * sign)
        sx = self._bee_face if abs(self._bee_face) > 0.14 else 0.14 * sign
        painter.scale(sx, 1.0)
        painter.setPen(Qt.PenStyle.NoPen)
        flap = 3.0 + 3.0 * abs(math.sin(self._bee_phase))
        painter.setBrush(_c("#ffffff", 150))
        painter.drawEllipse(QPointF(-1, -7), 6.0, flap)
        painter.drawEllipse(QPointF(5, -7), 6.0, flap)
        painter.setBrush(_c("#1a1a1a", 255))
        painter.drawPolygon(QPolygonF([
            QPointF(-10, -2), QPointF(-15, 0), QPointF(-10, 2)]))
        painter.setBrush(_c(Colors.ACCENT, 255))
        painter.drawEllipse(QRectF(-10, -6, 20, 12))
        painter.setBrush(_c("#1a1a1a", 255))
        painter.drawRect(QRectF(-3, -6, 3, 12))
        painter.drawRect(QRectF(3, -6, 3, 12))
        painter.drawEllipse(QRectF(7, -5, 10, 10))
        pen = QPen(_c("#1a1a1a", 255))
        pen.setWidthF(1.2)
        painter.setPen(pen)
        painter.drawLine(QPointF(14, -4), QPointF(18, -10))
        painter.drawLine(QPointF(15, -3), QPointF(20, -8))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(_c("#ffffff", 235))
        painter.drawEllipse(QPointF(13.0, -1.0), 1.6, 1.6)
        painter.restore()

    def _draw_speech(self, painter: QPainter, x: float, y: float, text: str,
                     alpha: float = 1.0):
        font = QFont(_SANS, 9)
        font.setBold(True)
        painter.setFont(font)
        fm = painter.fontMetrics()
        tw = fm.horizontalAdvance(text) + 16
        th = fm.height() + 8
        bx = max(4.0, min(x - tw / 2.0, self.width() - tw - 4.0))
        # Prefer above; flip below when there isn't room (top edge).
        above = y - 20.0 - th
        by = above if above >= 4.0 else (y + 20.0)
        by = min(by, self.height() - th - 4.0)
        bubble = QRectF(bx, by, tw, th)
        painter.setPen(QPen(_c(Colors.ACCENT, int(170 * alpha)), 1))
        painter.setBrush(_c("#0c0c0e", int(235 * alpha)))
        painter.drawRoundedRect(bubble, 8, 8)
        painter.setPen(_c(Colors.ACCENT, int(255 * alpha)))
        painter.drawText(bubble, Qt.AlignmentFlag.AlignCenter, text)
