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
import ctypes.wintypes
import logging
import math
import random
import re
import time

from PySide6.QtCore import Qt, QTimer, QRectF, QPointF
from PySide6.QtGui import (
    QColor, QFont, QFontMetricsF, QGuiApplication, QLinearGradient,
    QPainter, QPen, QPolygonF,
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

    def __init__(self, owner_hwnd_getter=None, preview: bool = False):
        super().__init__(None)
        self._owner_hwnd = owner_hwnd_getter or (lambda: 0)
        # Preview: an ordinary window with a backdrop, so the HUD can be looked
        # at without starting a run and without a game to pin to.
        self._preview = bool(preview)

        if preview:
            self.setWindowTitle("WorkerBee overlay preview")
            self.resize(900, 560)
        else:
            self.setWindowFlags(
                Qt.WindowType.FramelessWindowHint
                | Qt.WindowType.WindowStaysOnTopHint
                | Qt.WindowType.Tool
                | Qt.WindowType.WindowTransparentForInput
                | Qt.WindowType.WindowDoesNotAcceptFocus
            )
            self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
            self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)
            self.setAttribute(
                Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)

        self._show_hud = True
        self._show_vision = False
        self._show_path = False
        self._run_active = False
        # A start that is counting down: {summary, remaining,
        # cancel_key}. Drawn over the game so the summary and the time
        # left follow the user when they tab into it.
        self._pending = None
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

        self._alpha_cache = 218
        self._refresh_alpha()
        self._alpha_timer = QTimer(self)
        self._alpha_timer.setInterval(1500)
        self._alpha_timer.timeout.connect(self._refresh_alpha)
        self._alpha_timer.start()

        self._geo_timer = QTimer(self)
        self._geo_timer.setInterval(150)
        self._geo_timer.timeout.connect(self._track)
        self._geo_timer.start()

        self._paint_timer = QTimer(self)
        self._paint_timer.setInterval(50)   # 20fps; repaints only when needed
        self._paint_timer.timeout.connect(self._tick)
        self._paint_timer.start()

    def _panel_alpha(self) -> int:
        """Panel opacity, 0-255, from Settings. Cached: paint runs at 20fps and
        this would otherwise be a file read per frame. Refreshed on a slow
        timer so moving the slider still reaches the live overlay."""
        return self._alpha_cache

    # Fade profile for the panel: full strength behind the wordmark, thinning
    # toward the last row. Stepped rather than smoothly interpolated, so it
    # reads as pixel art like everything else on the HUD, and the steps land
    # on the row grid so each readout line sits on one flat tint.
    _FADE_FLOOR = 0.34      # bottom edge keeps this much of the set opacity
    _FADE_CURVE = 1.5       # >1 holds the top strong, then drops away

    def _fade(self, rect, top_alpha: float, hex_str: str = "#0e1013",
              head_h: float = 0.0, pitch: float = 0.0):
        """Top-to-bottom banded fade of one colour across rect.

        head_h is a first band held at full strength (the wordmark row);
        pitch is the height of each band after it. With pitch 0 the whole
        rect is one band, i.e. the old flat fill."""
        grad = QLinearGradient(rect.left(), rect.top(),
                               rect.left(), rect.bottom())
        h = max(1.0, rect.height())
        edges = [0.0]
        if pitch > 0.0:
            y = head_h
            while y < h - 0.5:
                edges.append(min(y / h, 1.0))
                y += pitch
        edges.append(1.0)

        n = max(1, len(edges) - 1)
        for i in range(n):
            t = 0.0 if n == 1 else i / (n - 1.0)
            k = 1.0 - (1.0 - self._FADE_FLOOR) * (t ** self._FADE_CURVE)
            col = _c(hex_str, int(round(top_alpha * k)))
            # Two stops per band so the step is hard, not interpolated.
            grad.setColorAt(edges[i], col)
            grad.setColorAt(max(edges[i], edges[i + 1] - 0.0001), col)
        return grad

    def _refresh_alpha(self):
        try:
            from .settings import load_settings
            pct = (load_settings().get("app_settings") or {}).get(
                "overlay_opacity", 85)
            value = max(20, min(255, int(round(float(pct) * 2.55))))
        except Exception:
            value = 218
        if value != self._alpha_cache:
            self._alpha_cache = value
            self._dirty = True

    def load_demo(self):
        """Plausible sample state, so the preview shows a populated HUD."""
        self._phase = "Floor 3"
        self._floor = "3"
        self._pack = "Hatred and Despair"
        self._run = (2, 5)
        self._run_start = time.time() - 754
        self._target = (1284, 622)
        self._actions.clear()
        for text in ("Picked pack: Hatred and Despair",
                     "Skill 2 -> Skill 3 (Ryoshu)",
                     "Won clash 4/4", "Claimed floor bonus",
                     "Entering Floor 3"):
            self._actions.append(text)
        self._show_hud = True
        self._dirty = True

    # --- external API ----------------------------------------------
    def set_toggles(self, hud: bool, vision: bool, path: bool):
        self._show_hud = bool(hud)
        self._show_vision = bool(vision)
        self._show_path = bool(path)
        self._dirty = True

    def set_pending(self, summary, seconds, cancel_key="F2"):
        """A start is counting down: show what will run and the time left.
        `summary` is the dict run_summary.md_start / lux_start builds."""
        self._pending = {"summary": dict(summary or {}),
                         "remaining": int(seconds),
                         "cancel_key": str(cancel_key or "F2")}
        self._dirty = True
        self._track()
        self.update()

    def set_pending_remaining(self, seconds: int):
        if self._pending is not None:
            self._pending["remaining"] = int(seconds)
            self._dirty = True
            self.update()

    def clear_pending(self):
        if self._pending is not None:
            self._pending = None
            self._dirty = True
            self._track()
            self.update()

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
        if self._preview:
            return        # no game window to pin to
        pending = self._pending is not None
        if pending:
            # No run has started, so p.WINDOW is unset or stale: read the
            # game window live, and only cover it while it has focus.
            win = self._live_game_rect() if self._game_focused() else None
            wants = win is not None
        else:
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
        # Not while a start is pending: the probe flashes a sentinel block.
        if (self._capturable is None and not self._probe_scheduled
                and not pending):
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

    @staticmethod
    def _game_hwnd() -> int:
        try:
            import wbcore.utils.params as p
            return int(ctypes.windll.user32.FindWindowW(None, p.LIMBUS_NAME)
                       or 0)
        except Exception:
            return 0

    def _game_focused(self) -> bool:
        try:
            hwnd = self._game_hwnd()
            return bool(hwnd) and int(
                ctypes.windll.user32.GetForegroundWindow()) == hwnd
        except Exception:
            return False

    def _live_game_rect(self):
        """The game's client area in physical px, read from the window
        itself. Unlike _game_rect this needs no run to have set p.WINDOW."""
        try:
            user32 = ctypes.windll.user32
            hwnd = self._game_hwnd()
            if not hwnd or user32.IsIconic(hwnd):
                return None
            rect = ctypes.wintypes.RECT()
            user32.GetClientRect(hwnd, ctypes.byref(rect))
            pt = ctypes.wintypes.POINT(0, 0)
            user32.ClientToScreen(hwnd, ctypes.byref(pt))
            w, h = rect.right - rect.left, rect.bottom - rect.top
            if w <= 1 or h <= 1:
                return None
            return int(pt.x), int(pt.y), int(w), int(h)
        except Exception:
            return None

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
        if self._preview:
            # Stand-in for the game behind the HUD, so the panel's translucency
            # and edge can actually be judged. It carries a bright band because
            # a flat dark backdrop is within a few values of the panel's own
            # fill, which hides exactly what this is here to show.
            back = QLinearGradient(0, 0, w * 0.25, h)
            back.setColorAt(0.0, QColor("#141014"))
            back.setColorAt(0.55, QColor("#3b352c"))
            back.setColorAt(1.0, QColor("#6a5c44"))
            painter.fillRect(0, 0, w, h, back)
            for gx in range(0, w, 32):
                painter.fillRect(gx, 0, 1, h, QColor(255, 255, 255, 8))
            for gy in range(0, h, 32):
                painter.fillRect(0, gy, w, 1, QColor(255, 255, 255, 8))
        sx, sy = w / _LOGICAL_W, h / _LOGICAL_H
        if self._pending is not None:
            # Nothing is running yet: the summary stands alone.
            self._paint_pending(painter)
            return
        if self._show_vision:
            self._paint_matches(painter, sx, sy)
        if self._show_path:
            self._paint_path(painter, sx, sy)
        if self._show_hud:
            self._paint_hud(painter)
            self._paint_bee(painter)

    def _pending_rows(self, painter, sections, x, y, width) -> float:
        """Lay the summary out in two columns and return its height. With
        painter None it only measures, so the panel can be sized first."""
        from .voxel import draw_pixel_text
        gap, label_w = 30.0, 132.0
        col_w = (width - gap) / 2.0
        font = QFont(_SANS, 10)
        fm = QFontMetricsF(font)
        wrap = int(Qt.TextFlag.TextWordWrap | Qt.AlignmentFlag.AlignLeft
                   | Qt.AlignmentFlag.AlignTop)
        def section(paint, cx, cy, caption, rows) -> float:
            if paint is not None:
                draw_pixel_text(paint, cx, cy, str(caption).upper(), 2,
                                Colors.TEXT_TERTIARY)
            used = 14.0 + 7.0
            for label, value in rows:
                value = str(value)
                need = fm.boundingRect(
                    QRectF(0, 0, col_w - label_w, 2000), wrap, value)
                rh = max(fm.height(), need.height())
                if paint is not None:
                    paint.setFont(font)
                    paint.setPen(QColor(Colors.TEXT_SECONDARY))
                    paint.drawText(QRectF(cx, cy + used, label_w, rh),
                                   wrap, str(label))
                    paint.setPen(QColor(Colors.TEXT_PRIMARY))
                    paint.drawText(
                        QRectF(cx + label_w, cy + used, col_w - label_w, rh),
                        wrap, value)
                used += rh + 3.0
            return used

        # Sections pair up across the two columns, and each pair starts on
        # the same line however tall the one beside it is.
        per_col = max(1, (len(sections) + 1) // 2)
        total = 0.0
        for r in range(per_col):
            pair = [sections[i] for i in (r, r + per_col) if i < len(sections)]
            if r:
                total += 16.0
            tall = max(section(None, 0, 0, cap, rows) for cap, rows in pair)
            if painter is not None:
                for c, (cap, rows) in enumerate(pair):
                    section(painter, x + c * (col_w + gap), y + total,
                            cap, rows)
            total += tall
        return total

    def _pending_gifts(self, painter, groups, x, y, width) -> float:
        """The gift art row: named tiles for the gifts searched for, bare
        thumbnails for market targets. Returns its height; with painter None
        it only measures."""
        from .voxel import draw_pixel_text
        from .start_overlay import (GIFT_THUMB, GIFT_TILE, GIFT_TILE_W,
                                    gift_image)
        gap = 30.0
        col_w = (width - gap) / 2.0
        font = QFont(_SANS, 9)
        fm = QFontMetricsF(font)
        centre = int(Qt.TextFlag.TextWordWrap | Qt.AlignmentFlag.AlignHCenter
                     | Qt.AlignmentFlag.AlignTop)
        tallest = 0.0
        for c, group in enumerate(groups[:2]):
            cx = x + c * (col_w + gap)
            if painter is not None:
                draw_pixel_text(painter, cx, y, str(group.get("caption", "")),
                                2, Colors.TEXT_TERTIARY)
                painter.setFont(font)
            top = y + 14.0 + 7.0
            names = list(group.get("names") or [])
            named = bool(group.get("named"))
            if not names:
                if painter is not None:
                    painter.setPen(QColor(Colors.TEXT_SECONDARY))
                    painter.drawText(QRectF(cx, top, col_w, fm.height()),
                                     int(Qt.AlignmentFlag.AlignLeft), "None")
                tallest = max(tallest, 21.0 + fm.height())
                continue

            size = GIFT_TILE if named else GIFT_THUMB
            step = (GIFT_TILE_W + 8) if named else (GIFT_THUMB + 6)
            limit = 3 if named else 8
            text_h = 0.0
            for i, name in enumerate(names[:limit]):
                tx = cx + i * step
                ax = tx + ((GIFT_TILE_W - size) / 2.0 if named else 0.0)
                if painter is not None:
                    art = gift_image(name, size)
                    if art is not None:
                        painter.drawImage(
                            int(ax + (size - art.width()) / 2),
                            int(top + (size - art.height()) / 2), art)
                    else:
                        painter.setPen(QPen(QColor(Colors.BORDER_STRONG), 1))
                        painter.setBrush(Qt.BrushStyle.NoBrush)
                        painter.drawRect(QRectF(ax + 0.5, top + 0.5,
                                                size - 1, size - 1))
                if named:
                    box = QRectF(tx, top + size + 4, GIFT_TILE_W, 2000)
                    need = fm.boundingRect(box, centre, name).height()
                    text_h = max(text_h, need)
                    if painter is not None:
                        painter.setPen(QColor(Colors.TEXT_PRIMARY))
                        painter.drawText(
                            QRectF(tx, top + size + 4, GIFT_TILE_W, need),
                            centre, name)
            if len(names) > limit and painter is not None:
                painter.setPen(QColor(Colors.TEXT_SECONDARY))
                painter.drawText(
                    QRectF(cx + limit * step, top, 60, size),
                    int(Qt.AlignmentFlag.AlignLeft
                        | Qt.AlignmentFlag.AlignVCenter),
                    "+%d" % (len(names) - limit))
            tallest = max(tallest,
                          21.0 + size + ((4 + text_h) if named else 0.0))
        return tallest

    def _paint_pending(self, painter: QPainter):
        """The start overlay, over the game: the same summary and countdown
        the WorkerBee window shows, for a user who has already tabbed in.
        It cannot take clicks (the overlay is input-transparent), so the
        way out it names is the stop hotkey."""
        from .voxel import draw_pixel_text, pixel_text_width
        from .start_overlay import pixel_safe
        pend = self._pending
        summary = pend["summary"]
        title = pixel_safe(summary.get("title", "")).upper()
        sub = pixel_safe(summary.get("subtitle") or "").upper()
        gifts = list(summary.get("gifts") or [])[:2]
        sections = list(summary.get("sections") or [])
        w, h = self.width(), self.height()
        if not self._preview:
            painter.fillRect(0, 0, w, h, QColor(0, 0, 0, 96))

        pad = 24.0
        # Wide enough that values rarely wrap, never wider than the game.
        pw = float(min(max(780, w * 0.46), 900, w - 40))
        inner = pw - 2 * pad

        # The kind of run is the largest text on the panel: the countdown
        # is a size down, and the title only shrinks if it would not fit.
        count = str(max(0, int(pend["remaining"])))
        count_px = 5
        count_w = pixel_text_width("00", count_px)
        title_px = next((px for px in (6, 5, 4)
                         if pixel_text_width(title, px)
                         <= inner - count_w - 24), 4)
        title_h, sub_h, hint_h = 7.0 * title_px, 21.0, 20.0
        head_h = 14 + 10 + title_h + ((10 + sub_h) if sub else 0)
        gifts_h = (self._pending_gifts(None, gifts, 0, 0, inner)
                   if gifts else 0.0)
        body_h = self._pending_rows(None, sections, 0, 0, inner)
        ph = (pad + head_h + 12 + hint_h + ((14 + gifts_h) if gifts else 0)
              + 16 + body_h + pad)
        px, py = round((w - pw) / 2.0), round((h - ph) / 2.0)

        painter.setPen(QPen(_c(Colors.ACCENT, 170), 1))
        painter.setBrush(_c("#0e1013", 240))
        painter.drawRect(QRectF(px + 0.5, py + 0.5, pw - 1, ph - 1))

        x, y = px + pad, py + pad
        draw_pixel_text(painter, x, y, "STARTING IN", 2, Colors.TEXT_SECONDARY)
        draw_pixel_text(painter, x, y + 14 + 10, title, title_px,
                        Colors.TEXT_PRIMARY)
        if sub:
            draw_pixel_text(painter, x, y + 14 + 10 + title_h + 10, sub, 3,
                            Colors.ACCENT)
        draw_pixel_text(painter,
                        px + pw - pad - pixel_text_width(count, count_px),
                        y, count, count_px, Colors.ACCENT)

        y += head_h + 12
        painter.setFont(QFont(_SANS, 10))
        painter.setPen(QColor(Colors.TEXT_SECONDARY))
        painter.drawText(
            QRectF(x, y, inner, hint_h),
            int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter),
            "The run starts when the countdown ends. Press %s to cancel."
            % pend["cancel_key"])
        y += hint_h
        if gifts:
            y += 14
            self._pending_gifts(painter, gifts, x, y, inner)
            y += gifts_h
        self._pending_rows(painter, sections, x, y + 16, inner)

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
        """Square panel, 1px edge, a filled header band with the wordmark in
        the 5x7 pixel face: the same shapes the app itself uses, so the HUD
        does not read as a different program sitting on the game."""
        margin = 16
        pad = 10
        pw = 330
        line_h = 20
        band_h = 22

        rows = 6  # phase, floor, pack, target, tracer, run time
        show_actions = len(self._actions) > 0
        if show_actions:
            rows += 1 + len(self._actions)
        panel_h = pad + band_h + rows * line_h + pad

        panel = QRectF(margin, margin, pw, panel_h)
        self._panel_rect = panel
        painter.setPen(Qt.PenStyle.NoPen)
        head_h = pad + band_h
        painter.setBrush(self._fade(panel, self._panel_alpha(),
                                    head_h=head_h, pitch=line_h))
        painter.drawRect(panel)

        # No header band: the wordmark sits straight on the panel, with the
        # run counter opposite it.
        from .voxel import draw_pixel_text, pixel_text_width
        head_y = panel.y() + pad
        from . import seasonal
        if seasonal.is_halloween():
            used = draw_pixel_text(painter, panel.x() + pad, head_y,
                                   "EVIL", 2, seasonal.RED)
            draw_pixel_text(painter, panel.x() + pad + used + 2, head_y,
                            "BEE", 2, seasonal.BONE)
        else:
            draw_pixel_text(painter, panel.x() + pad, head_y,
                            "WORKERBEE", 2, Colors.TEXT_PRIMARY)
        if self._run:
            run_txt = f"RUN {self._run[0]}/{self._run[1]}"
            draw_pixel_text(
                painter,
                panel.right() - pad - pixel_text_width(run_txt, 2),
                head_y, run_txt, 2, Colors.ACCENT)

        # 1px edge last, so it sits over the fill.
        painter.setBrush(Qt.BrushStyle.NoBrush)
        edge = panel.adjusted(0.5, 0.5, -0.5, -0.5)
        painter.setPen(QPen(self._fade(edge, 235, "#2b323a",
                                       head_h=head_h, pitch=line_h), 1))
        painter.drawRect(edge)

        x = margin + pad
        inner_w = pw - 2 * pad
        y = margin + pad + band_h

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
            draw_pixel_text(painter, x, y + 4, "RECENT", 2,
                            Colors.TEXT_TERTIARY)
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

    # Bee sprite on a block grid, drawn from a bitmap so it stays square at
    # any scale. Columns run tail -> head; "." is empty.
    _BEE_ROWS = (
        "....WW.WW....",
        "...WWWWWWW...",
        ".SBBYYBBYYHH.",
        "SSBBYYBBYYHE.",
        ".SBBYYBBYYHH.",
    )
    _BEE_PAL = {
        "Y": Colors.ACCENT,     # stripe
        "B": "#1a1608",         # stripe
        "H": "#1a1608",         # head
        "E": "#ffffff",         # eye, so the black head still reads
        "S": "#1a1608",         # stinger
        "W": "#dbe9ff",         # wing
    }
    # October: red and black, under a pair of scalloped bat wings.
    _BAT_ROWS = (
        "..W.W.W.W.W..",
        "..WWWWWWWWW..",
        ".SBBYYBBYYHH.",
        "SSBBYYBBYYHE.",
        ".SBBYYBBYYHH.",
    )
    _BAT_PAL = {
        "Y": "#e01e2f", "B": "#14060a", "H": "#14060a",
        "E": "#ffb000", "S": "#14060a", "W": "#7a1422",
    }
    _BEE_UNIT = 3

    def _draw_bee(self, painter: QPainter, x: float, y: float):
        painter.save()
        painter.translate(x, y)
        # scaleX through ~0 reads as the bee turning around.
        sign = 1.0 if self._bee_face >= 0 else -1.0
        painter.rotate(math.degrees(self._bee_tilt) * sign)
        sx = self._bee_face if abs(self._bee_face) > 0.14 else 0.14 * sign
        painter.scale(sx, 1.0)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, False)
        painter.setPen(Qt.PenStyle.NoPen)

        from . import seasonal
        evil = seasonal.is_halloween()
        u = self._BEE_UNIT
        rows = self._BAT_ROWS if evil else self._BEE_ROWS
        pal = self._BAT_PAL if evil else self._BEE_PAL
        w = len(rows[0]) * u
        h = len(rows) * u
        ox, oy = -w / 2.0, -h / 2.0
        # Wings beat: the top and bottom rows only show on alternate frames.
        beat = math.sin(self._bee_phase) > 0
        for ry, row in enumerate(rows):
            for rx, ch in enumerate(row):
                if ch == ".":
                    continue
                if ch == "W":
                    # Wings sit above the body only; the outer row drops on
                    # alternate frames so they read as a beat.
                    if ry == 0 and not beat:
                        continue
                    painter.setBrush(_c(pal["W"], 235 if evil else 165))
                else:
                    painter.setBrush(_c(pal[ch], 255))
                painter.drawRect(QRectF(ox + rx * u, oy + ry * u, u, u))
        painter.restore()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)

    _SPEECH_U = 3          # block size of the bubble border

    def _draw_speech(self, painter: QPainter, x: float, y: float, text: str,
                     alpha: float = 1.0):
        """Classic pixel speech bubble: a blocky outline with stepped corners
        and a stepped tail, text in the same 5x7 face as everything else. Not
        a rounded rect - a rounded rect at this scale is exactly what the rest
        of the skin was built to avoid."""
        from .voxel import draw_pixel_text, pixel_text_width

        u = self._SPEECH_U
        pixel = 2
        text = text.upper()
        tw = pixel_text_width(text, pixel)
        th = 7 * pixel
        pad = 2 * u
        bw = tw + 2 * pad + 2 * u
        bh = th + 2 * pad + 2 * u
        tail_h = 3 * u

        bx = max(4.0, min(x - bw / 2.0, self.width() - bw - 4.0))
        gap = 12.0
        above = y - gap - bh - tail_h
        below = above < 4.0
        by = (y + gap + tail_h) if below else above
        by = min(by, self.height() - bh - tail_h - 4.0)

        ink = _c("#0e1013", int(255 * alpha))
        face = _c("#f2f2f4", int(240 * alpha))

        def blk(px, py, pw, ph, col):
            painter.fillRect(int(px), int(py), int(pw), int(ph), col)

        painter.setPen(Qt.PenStyle.NoPen)
        # Face first, inset by one block so the corners can step.
        blk(bx + u, by, bw - 2 * u, bh, face)
        blk(bx, by + u, bw, bh - 2 * u, face)
        # Border: each side short by one block at both ends, then the four
        # corner blocks placed diagonally - that step is what makes it read
        # as drawn on a pixel grid rather than a rectangle with a stroke.
        blk(bx + u, by, bw - 2 * u, u, ink)                    # top
        blk(bx + u, by + bh - u, bw - 2 * u, u, ink)           # bottom
        blk(bx, by + u, u, bh - 2 * u, ink)                    # left
        blk(bx + bw - u, by + u, u, bh - 2 * u, ink)           # right
        for cx, cy in ((bx + u, by + u), (bx + bw - 2 * u, by + u),
                       (bx + u, by + bh - 2 * u),
                       (bx + bw - 2 * u, by + bh - 2 * u)):
            blk(cx, cy, u, u, ink)

        # Tail: a stepped wedge from the bubble edge toward the bee. Anchored
        # near the bee's x so it points at whoever is talking.
        tail_x = bx + max(u * 2, min(x - bx - u * 1.5, bw - u * 5))
        for i in range(3):
            width = (3 - i) * u
            ty = (by - (i + 1) * u) if below else (by + bh + i * u)
            blk(tail_x, ty, width, u, ink)

        draw_pixel_text(painter, bx + u + pad, by + u + pad, text, pixel,
                        "#0e1013")
