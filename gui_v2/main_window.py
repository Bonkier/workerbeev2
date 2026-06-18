# SPDX-License-Identifier: GPL-3.0-or-later
"""Frameless main window: splash morphs into the main UI on init complete."""

import ctypes
import os
import sys

from PySide6.QtCore import (
    QEasingCurve, QPropertyAnimation, QRect, Qt, QPoint,
    QParallelAnimationGroup,
)
from PySide6.QtGui import QCursor, QGuiApplication, QIcon
from PySide6.QtWidgets import (
    QFrame, QGraphicsOpacityEffect, QHBoxLayout, QLabel, QMainWindow,
    QPushButton, QStackedWidget, QVBoxLayout, QWidget,
)

from .init_worker import (
    InitThread, InitWorker, UpdateCheckWorker, UpdateApplyWorker,
)
from .main_ui import MainUI
from .run_coordinator import RunCoordinator
from .settings import get_splash_size
from .splash import SplashWidget, _read_version
from .theme import Motion, Sizing


# Edge margin (px) where dragging triggers a resize.
_RESIZE_MARGIN = 8

# Windows 11 DWM rounded-corner constants; no-op pre-Win11.
_DWMWA_WINDOW_CORNER_PREFERENCE = 33
_DWMWCP_ROUND = 2

_QWIDGETSIZE_MAX = 16777215

# Win32 hit-test codes; returning these from WM_NCHITTEST lets Windows
# drive the frameless resize over child widgets.
_WM_NCHITTEST = 0x0084
_HTLEFT, _HTRIGHT, _HTTOP, _HTTOPLEFT, _HTTOPRIGHT = 10, 11, 12, 13, 14
_HTBOTTOM, _HTBOTTOMLEFT, _HTBOTTOMRIGHT = 15, 16, 17

_EDGE_LEFT   = 1 << 0
_EDGE_RIGHT  = 1 << 1
_EDGE_TOP    = 1 << 2
_EDGE_BOTTOM = 1 << 3


class _TitleBar(QFrame):
    """Custom title bar: the native one flashes white on DWM repaint."""

    def __init__(self, parent_window: QMainWindow):
        super().__init__(parent_window)
        self.setObjectName("titleBar")
        self.setFixedHeight(Sizing.TITLEBAR_HEIGHT)
        self._win = parent_window
        self._drag_origin: QPoint | None = None

        layout = QHBoxLayout(self)
        layout.setContentsMargins(Sizing.SPACE_MD, 0, 0, 0)
        layout.setSpacing(0)

        # No title text - the sidebar shows the brand.
        layout.addStretch(1)

        # Unicode glyphs so we don't ship icon files.
        self._mk_btn(layout, "–", self._win.showMinimized, close=False)
        self._mk_btn(layout, "□", self._toggle_max, close=False)
        self._mk_btn(layout, "×", self._win.close, close=True)

    def _mk_btn(self, layout, glyph, handler, close: bool):
        b = QPushButton(glyph, self)
        b.setObjectName("titleBarBtnClose" if close else "titleBarBtn")
        b.setProperty("class", "titleBarBtn")
        b.clicked.connect(handler)
        b.setCursor(Qt.CursorShape.PointingHandCursor)
        layout.addWidget(b)

    def _toggle_max(self):
        if self._win.isMaximized():
            self._win.showNormal()
        else:
            self._win.showMaximized()

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_origin = event.globalPosition().toPoint() - self._win.frameGeometry().topLeft()
            event.accept()

    def mouseMoveEvent(self, event):
        if self._drag_origin is not None and event.buttons() & Qt.MouseButton.LeftButton:
            self._win.move(event.globalPosition().toPoint() - self._drag_origin)
            event.accept()

    def mouseReleaseEvent(self, _event):
        self._drag_origin = None

    def mouseDoubleClickEvent(self, _event):
        self._toggle_max()


class MainWindow(QMainWindow):
    def __init__(self, mode: str = "init"):
        """mode = 'init' (normal launch) or 'update' (run update flow first)."""
        super().__init__()
        self.setWindowTitle("WorkerBee")
        icon_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "app_icon.ico",
        )
        if os.path.exists(icon_path):
            self.setWindowIcon(QIcon(icon_path))
        # Frameless: avoids the white flash on resize. We paint our own bar.
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint)
        # WA_TranslucentBackground blocks the DWM shadow and flickers; opaque
        # paint event with a solid background avoids the flash.
        self.setAttribute(Qt.WidgetAttribute.WA_OpaquePaintEvent, True)

        self._mode = mode
        self._on_splash = True

        self._resize_edge = 0
        self._resize_start_geo: QRect | None = None
        self._resize_start_mouse: QPoint | None = None

        # Track mouse globally so the cursor updates near an edge even when
        # the splash widget is on top.
        self.setMouseTracking(True)

        self._build_ui()
        self._size_to_splash()
        self._start_init()

    def _build_ui(self):
        root = QWidget(self)
        root.setObjectName("root")
        self.setCentralWidget(root)
        self._root = root

        v = QVBoxLayout(root)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(0)

        # Splash at index 0, main UI at 1. The title bar is not a layout
        # row - it floats as a transparent overlay (see _position_titlebar).
        self._stack = QStackedWidget(root)
        v.addWidget(self._stack, stretch=1)

        self._titlebar = _TitleBar(self)
        self._titlebar.setParent(root)
        # Hidden during splash; fades in during the morph to the main UI.
        self._titlebar.hide()

        self._splash = SplashWidget(self._stack)
        self._splash.close_clicked.connect(self.close)
        # Main UI is created but NOT yet added to the stack: doing so would
        # make the QStackedWidget sizeHint max(splash, main) and force the
        # window taller than the splash. Added in _morph_to_main.
        self._main = MainUI(self._stack)
        self._coordinator = RunCoordinator(self._main, self)
        self._stack.addWidget(self._splash)
        self._stack.setCurrentWidget(self._splash)

        # Pre-install opacity effects to avoid a flicker on first animation.
        self._splash_opacity = QGraphicsOpacityEffect(self._splash)
        self._splash_opacity.setOpacity(1.0)
        self._splash.setGraphicsEffect(self._splash_opacity)

        self._main_opacity = QGraphicsOpacityEffect(self._main)
        self._main_opacity.setOpacity(0.0)
        self._main.setGraphicsEffect(self._main_opacity)

        self._titlebar_opacity = QGraphicsOpacityEffect(self._titlebar)
        self._titlebar_opacity.setOpacity(0.0)
        self._titlebar.setGraphicsEffect(self._titlebar_opacity)

    def _clamp_to_screen(self, target_w: int, target_h: int) -> tuple[int, int]:
        """Cap dimensions at MAX_SCREEN_FRACTION so the window always fits."""
        screen = QGuiApplication.primaryScreen().availableGeometry()
        max_w = int(screen.width() * Sizing.MAX_SCREEN_FRACTION)
        max_h = int(screen.height() * Sizing.MAX_SCREEN_FRACTION)
        return min(target_w, max_w), min(target_h, max_h)

    def _centered_rect(self, w: int, h: int) -> QRect:
        screen = QGuiApplication.primaryScreen().availableGeometry()
        return QRect(
            screen.center().x() - w // 2,
            screen.center().y() - h // 2,
            w, h,
        )

    def _size_to_splash(self):
        # Clamped so a stale config can't push the window off a small screen.
        saved_w, saved_h = get_splash_size(Sizing.SPLASH_W, Sizing.SPLASH_H)
        saved_w = max(saved_w, 320)
        saved_h = max(saved_h, 160)
        w, h = self._clamp_to_screen(saved_w, saved_h)
        self.setGeometry(self._centered_rect(w, h))
        # Lock size so rotating tips with different widths don't resize.
        self.setFixedSize(w, h)

    # --- Frameless-window resize-by-edge -----------------------------
    def _hit_test_edge(self, pos: QPoint) -> int:
        """Return an _EDGE_* bitmask for edges within _RESIZE_MARGIN of pos."""
        edge = 0
        if pos.x() <= _RESIZE_MARGIN:
            edge |= _EDGE_LEFT
        if pos.x() >= self.width() - _RESIZE_MARGIN:
            edge |= _EDGE_RIGHT
        if pos.y() <= _RESIZE_MARGIN:
            edge |= _EDGE_TOP
        if pos.y() >= self.height() - _RESIZE_MARGIN:
            edge |= _EDGE_BOTTOM
        return edge

    @staticmethod
    def _cursor_for_edge(edge: int) -> Qt.CursorShape:
        if edge in (_EDGE_LEFT | _EDGE_TOP, _EDGE_RIGHT | _EDGE_BOTTOM):
            return Qt.CursorShape.SizeFDiagCursor
        if edge in (_EDGE_RIGHT | _EDGE_TOP, _EDGE_LEFT | _EDGE_BOTTOM):
            return Qt.CursorShape.SizeBDiagCursor
        if edge & (_EDGE_LEFT | _EDGE_RIGHT):
            return Qt.CursorShape.SizeHorCursor
        if edge & (_EDGE_TOP | _EDGE_BOTTOM):
            return Qt.CursorShape.SizeVerCursor
        return Qt.CursorShape.ArrowCursor

    def mouseMoveEvent(self, event):
        pos = event.position().toPoint()
        if self._resize_edge:
            self._apply_resize(event.globalPosition().toPoint())
            event.accept()
            return
        if self.isMaximized():
            self.unsetCursor()
        else:
            edge = self._hit_test_edge(pos)
            self.setCursor(self._cursor_for_edge(edge))
        super().mouseMoveEvent(event)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton and not self.isMaximized():
            edge = self._hit_test_edge(event.position().toPoint())
            if edge:
                self._resize_edge = edge
                self._resize_start_geo = QRect(self.geometry())
                self._resize_start_mouse = event.globalPosition().toPoint()
                event.accept()
                return
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event):
        if self._resize_edge and event.button() == Qt.MouseButton.LeftButton:
            self._resize_edge = 0
            self._resize_start_geo = None
            self._resize_start_mouse = None
            # Splash size is intentionally not persisted here.
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def _apply_resize(self, global_pos: QPoint):
        if self._resize_start_geo is None or self._resize_start_mouse is None:
            return
        start = self._resize_start_geo
        delta = global_pos - self._resize_start_mouse
        new_geo = QRect(start)
        min_w, min_h = 320, 160

        if self._resize_edge & _EDGE_RIGHT:
            new_geo.setRight(max(start.left() + min_w - 1, start.right() + delta.x()))
        if self._resize_edge & _EDGE_LEFT:
            new_geo.setLeft(min(start.right() - min_w + 1, start.left() + delta.x()))
        if self._resize_edge & _EDGE_BOTTOM:
            new_geo.setBottom(max(start.top() + min_h - 1, start.bottom() + delta.y()))
        if self._resize_edge & _EDGE_TOP:
            new_geo.setTop(min(start.bottom() - min_h + 1, start.top() + delta.y()))

        self.setGeometry(new_geo)

    def showEvent(self, event):
        super().showEvent(event)
        self._position_titlebar()
        if not getattr(self, "_corners_applied", False):
            self._apply_rounded_corners()
            self._corners_applied = True

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._position_titlebar()

    def _position_titlebar(self):
        bar = getattr(self, "_titlebar", None)
        if bar is not None:
            bar.setGeometry(0, 0, self._root.width(), Sizing.TITLEBAR_HEIGHT)
            bar.raise_()

    def _apply_rounded_corners(self):
        """Windows 11 DWM rounded outer corners; no-op elsewhere."""
        if not sys.platform.startswith("win"):
            return
        try:
            hwnd = int(self.winId())
            pref = ctypes.c_int(_DWMWCP_ROUND)
            ctypes.windll.dwmapi.DwmSetWindowAttribute(
                hwnd, _DWMWA_WINDOW_CORNER_PREFERENCE,
                ctypes.byref(pref), ctypes.sizeof(pref),
            )
        except (OSError, AttributeError):
            pass

    def nativeEvent(self, event_type, message):
        """Frameless resize via WM_NCHITTEST. Resolving at the window level
        lets any edge/corner drag resize through child widgets, and gets the
        correct resize cursors + Aero snap. Non-border hits fall through."""
        if sys.platform == "win32" and event_type == "windows_generic_MSG":
            try:
                from ctypes import wintypes
                msg = wintypes.MSG.from_address(int(message))
            except Exception:
                return super().nativeEvent(event_type, message)
            if msg.message == _WM_NCHITTEST and not self.isMaximized():
                pos = self.mapFromGlobal(QCursor.pos())
                x, y = pos.x(), pos.y()
                w, h = self.width(), self.height()
                m = _RESIZE_MARGIN
                left, right = x < m, x >= w - m
                top, bottom = y < m, y >= h - m
                code = 0
                if top and left:
                    code = _HTTOPLEFT
                elif top and right:
                    code = _HTTOPRIGHT
                elif bottom and left:
                    code = _HTBOTTOMLEFT
                elif bottom and right:
                    code = _HTBOTTOMRIGHT
                elif left:
                    code = _HTLEFT
                elif right:
                    code = _HTRIGHT
                elif top:
                    code = _HTTOP
                elif bottom:
                    code = _HTBOTTOM
                if code:
                    return True, code
        return super().nativeEvent(event_type, message)

    def closeEvent(self, event):
        super().closeEvent(event)

    def _start_init(self):
        if self._mode == "update":
            self._run_update_check_phase()
        else:
            self._run_normal_init()

    def _run_normal_init(self):
        self._splash.show_loading()
        self._init_thread = InitThread(self, worker=InitWorker())
        self._init_thread.progress.connect(
            lambda msg, pct: self._splash.set_status(msg, pct)
        )
        self._init_thread.finished_init.connect(self._on_init_done)
        self._init_thread.start()

    def _run_update_check_phase(self):
        self._splash.set_subtitle("CHECKING FOR UPDATES")
        check_worker = UpdateCheckWorker()
        self._check_thread = InitThread(self, worker=check_worker)
        self._check_thread.progress.connect(
            lambda msg, pct: self._splash.set_status(msg, pct)
        )
        # InitThread only forwards (ok, err); the worker hands us the
        # release dict via its own signal. Stash it for the prompt + apply.
        self._pending_update: dict | None = None
        check_worker.result.connect(self._on_check_result)
        self._check_thread.finished_init.connect(self._on_check_done)
        self._check_thread.start()

    def _on_check_result(self, info: dict):
        self._pending_update = info if isinstance(info, dict) else None

    def _on_check_done(self, ok: bool, err: str):
        if not ok:
            # A failed/blocked/timed-out update check must never strand the
            # splash - fall through to a normal launch.
            self._splash.set_status("Update check skipped")
            self._run_normal_init()
            return
        current = _read_version().lstrip("v")
        info = self._pending_update or {}
        remote = str(info.get("version", "")).lstrip("v")
        if not remote:
            self._splash.set_status("Update check returned no version.")
            return
        # Already current: skip prompt, roll into normal init.
        from . import updater
        if not updater.is_newer(remote, current):
            self._splash.set_status(f"Up to date (v{current}).")
            self._run_normal_init()
            return

        size_mb = int(int(info.get("size") or 0) // (1024 * 1024))
        self._splash.show_update_prompt(
            current=current, new=remote, size_mb=size_mb,
        )
        self._splash.update_now.connect(self._on_update_yes)
        self._splash.update_skip.connect(self._on_update_no)
        # Test hook (unset in production): auto-accept so the update chain can
        # be exercised end-to-end headlessly by tools/simulate_update_chain.py.
        if os.environ.get("WORKERBEE_TEST_AUTO_ACCEPT"):
            from PySide6.QtCore import QTimer as _QTimer
            _QTimer.singleShot(800, self._on_update_yes)

    def _on_update_yes(self):
        # Disconnect so the buttons can't double-fire if the user mashes
        # both during the brief window they're visible.
        try:
            self._splash.update_now.disconnect(self._on_update_yes)
            self._splash.update_skip.disconnect(self._on_update_no)
        except (RuntimeError, TypeError):
            pass
        info = getattr(self, "_pending_update", None) or {}
        remote = str(info.get("version", "")).lstrip("v")
        url = str(info.get("download_url", ""))
        if not url:
            self._splash.set_status("Update lost its download link; aborting.")
            return
        self._splash.set_subtitle(
            f"UPDATING  -  v{_read_version().lstrip('v')}  →  v{remote}"
        )
        self._splash.show_loading()
        self._apply_thread = InitThread(
            self, worker=UpdateApplyWorker(download_url=url, version=remote))
        self._apply_thread.progress.connect(
            lambda msg, pct: self._splash.set_status(msg, pct)
        )
        # The apply worker spawns a helper .bat and returns; we MUST exit
        # so the helper can take file locks and robocopy /MIR the install
        # dir. Route to quit-on-success rather than the normal morph path.
        self._apply_thread.finished_init.connect(self._on_apply_done)
        self._apply_thread.start()

    def _on_update_no(self):
        try:
            self._splash.update_now.disconnect(self._on_update_yes)
            self._splash.update_skip.disconnect(self._on_update_no)
        except (RuntimeError, TypeError):
            pass
        self._run_normal_init()

    def _on_init_done(self, ok: bool, err: str):
        if not ok:
            self._splash.set_status("Initialization failed")
            self._splash.set_subtle(err.splitlines()[0] if err else "")
            self._splash.stop_spinner()
            return
        self._splash.set_status("Ready")
        self._morph_to_main()

    def _on_apply_done(self, ok: bool, err: str):
        """On success the helper batch is waiting for this process to
        exit so it can take file locks - quit Qt rather than morph."""
        if not ok:
            self._splash.set_status("Update failed")
            self._splash.set_subtle(err.splitlines()[0] if err else "")
            self._splash.stop_spinner()
            return
        self._splash.set_status("Restarting...")
        # Keep the event loop ticking one more frame so the status paints
        # before we exit.
        from PySide6.QtCore import QTimer
        from PySide6.QtWidgets import QApplication
        QTimer.singleShot(200, lambda: (
            QApplication.instance() and QApplication.instance().quit()
        ))

    def _morph_to_main(self):
        # Release the splash-phase size lock so the geometry tween can grow.
        self.setMinimumSize(0, 0)
        self.setMaximumSize(_QWIDGETSIZE_MAX, _QWIDGETSIZE_MAX)

        # Geometry: splash size -> main size, centred and clamped to fit.
        w, h = self._clamp_to_screen(Sizing.MAIN_W, Sizing.MAIN_H)
        target_rect = self._centered_rect(w, h)

        geom = QPropertyAnimation(self, b"geometry", self)
        geom.setDuration(Motion.HERO)
        geom.setStartValue(self.geometry())
        geom.setEndValue(target_rect)
        geom.setEasingCurve(QEasingCurve.Type.OutCubic)

        # Crossfade splash -> main alongside the geometry tween.
        fade_out = QPropertyAnimation(self._splash_opacity, b"opacity", self)
        fade_out.setDuration(Motion.NORMAL)
        fade_out.setStartValue(1.0)
        fade_out.setEndValue(0.0)
        fade_out.setEasingCurve(QEasingCurve.Type.InCubic)

        fade_in = QPropertyAnimation(self._main_opacity, b"opacity", self)
        fade_in.setDuration(Motion.SLOW)
        fade_in.setStartValue(0.0)
        fade_in.setEndValue(1.0)
        fade_in.setEasingCurve(QEasingCurve.Type.OutCubic)

        self._titlebar.show()
        self._position_titlebar()
        title_fade = QPropertyAnimation(self._titlebar_opacity, b"opacity", self)
        title_fade.setDuration(Motion.SLOW)
        title_fade.setStartValue(0.0)
        title_fade.setEndValue(1.0)
        title_fade.setEasingCurve(QEasingCurve.Type.OutCubic)

        # Lazily attach main now (see _build_ui for why not earlier).
        if self._stack.indexOf(self._main) < 0:
            self._stack.addWidget(self._main)
        self._stack.setCurrentWidget(self._main)
        # Splash is kept visible via its opacity effect so fade_out reveals
        # main underneath; raise it so it actually paints on top.
        self._splash.raise_()

        self._morph_group = QParallelAnimationGroup(self)
        self._morph_group.addAnimation(geom)
        self._morph_group.addAnimation(fade_out)
        self._morph_group.addAnimation(fade_in)
        self._morph_group.addAnimation(title_fade)
        self._morph_group.finished.connect(self._morph_finished)
        self._morph_group.start()

    def _morph_finished(self):
        self._splash.stop_spinner()
        self._stack.setCurrentWidget(self._main)
        self._main.setGraphicsEffect(None)
        self._splash.deleteLater()
        # Below this size the content starts cropping; kept under 1280x800
        # so it still fits smaller displays.
        self.setMinimumSize(960, 600)
        self._on_splash = False
