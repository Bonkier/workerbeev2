# SPDX-License-Identifier: GPL-3.0-or-later
"""Bridge between the v2 GUI and the bot backend (src/wbcore/).

The bot runs on a background QThread and calls back via
QMetaObject.invokeMethod (slots here) and the `warning` callable
(forwarded as a Qt signal).
"""

import ctypes
import os
import sys
import threading

from PySide6.QtCore import QMetaObject, QObject, QThread, QTimer, Qt, Signal, Slot


def _ensure_paths():
    """Defensive sys.path setup for non-launcher contexts (e.g. tests)."""
    here = os.path.dirname(os.path.abspath(__file__))
    base = os.path.dirname(here)
    for p in (base, os.path.join(base, "src")):
        if p not in sys.path:
            sys.path.insert(0, p)


class AutomationController(QObject):
    """Qt-side controller; the bot worker invokes its slots."""

    bot_started = Signal()
    bot_stopped = Signal()
    bot_warning = Signal(str)
    bot_paused = Signal()

    _LIMBUS = "LimbusCompany"

    def __init__(self, parent: QObject | None = None):
        super().__init__(parent)
        self._thread: QThread | None = None
        self._worker: "BotWorker | None" = None
        self._params = None  # wbcore.utils.params, once a run starts
        self._finishing = False  # guards stop_execution against double-fire
        # Re-sets pause_event once Limbus regains focus, so the run resumes.
        self._focus_timer = QTimer(self)
        self._focus_timer.setInterval(600)
        self._focus_timer.timeout.connect(self._resume_if_focused)

    def is_running(self) -> bool:
        return self._thread is not None

    # --- bot -> GUI callbacks (invoked from the worker thread) ------
    @Slot()
    def stop_execution(self):
        """Teardown when the bot halts. Idempotent: the worker's finally
        and the bot's success path can both reach here."""
        if self._finishing:
            return
        self._finishing = True
        self._focus_timer.stop()
        self.bot_stopped.emit()
        if self._thread is not None:
            self._thread.quit()

    @Slot()
    def to_pause(self):
        """Bot lost focus and is waiting; reflect in the UI."""
        self.bot_paused.emit()

    @Slot()
    def lux_hide(self):
        """Hook fired after the lux phase."""
        pass

    # --- GUI -> bot controls (safe to call from any thread) ---------
    def stop(self):
        """Halt at the next checkpoint, releasing any pause wait."""
        if self._params is not None:
            try:
                self._params.stop_event.set()
                self._params.pause_event.set()
            except Exception:
                pass

    def pause(self):
        if self._params is not None:
            try:
                self._params.pause_event.clear()
            except Exception:
                pass

    def resume(self):
        if self._params is not None:
            try:
                self._params.pause_event.set()
            except Exception:
                pass

    def _setup_run_state(self):
        """Install the threading events the bot's pause/stop logic uses."""
        import wbcore.utils.params as params
        self._params = params
        params.pause_event = threading.Event()
        params.pause_event.set()
        params.stop_event = threading.Event()

    @staticmethod
    def _active_window_title() -> str:
        try:
            u = ctypes.windll.user32
            hwnd = u.GetForegroundWindow()
            n = u.GetWindowTextLengthW(hwnd)
            buf = ctypes.create_unicode_buffer(n + 1)
            u.GetWindowTextW(hwnd, buf, n + 1)
            return buf.value
        except Exception:
            return ""

    def _resume_if_focused(self):
        if self._params is None:
            return
        if self._LIMBUS in self._active_window_title():
            try:
                self._params.pause_event.set()
            except Exception:
                pass

    def start_run(self, *, teams, settings, hard, count: int = 1,
                  count_exp: int = 0, count_thd: int = 0):
        """Spawn the bot worker on a background thread."""
        if self._thread is not None:
            raise RuntimeError("Bot is already running")
        _ensure_paths()
        self._finishing = False
        self._setup_run_state()
        self._focus_timer.start()

        self._thread = QThread()
        self._worker = BotWorker(
            controller=self,
            count=count,
            count_exp=count_exp,
            count_thd=count_thd,
            teams=teams,
            settings=settings,
            hard=hard,
        )
        self._worker.moveToThread(self._thread)
        self._thread.started.connect(self._worker.run)
        self._thread.finished.connect(self._cleanup_thread)
        # Emit start before launching so the alert + UI flip land just
        # before the bot's first action.
        self.bot_started.emit()
        self._thread.start()

    def start_convert(self):
        """One-shot Convert Enkephalin worker for the scheduler."""
        if self._thread is not None:
            raise RuntimeError("Bot is already running")
        _ensure_paths()
        self._finishing = False
        self._setup_run_state()
        self._focus_timer.start()

        self._thread = QThread()
        self._worker = ConvertWorker(controller=self)
        self._worker.moveToThread(self._thread)
        self._thread.started.connect(self._worker.run)
        self._thread.finished.connect(self._cleanup_thread)
        self.bot_started.emit()
        self._thread.start()

    def _cleanup_thread(self):
        self._focus_timer.stop()
        self._params = None
        self._worker = None
        if self._thread is not None:
            self._thread.deleteLater()
            self._thread = None


class BotWorker(QObject):
    """Calls wbcore.bot.execute_me on the background QThread."""

    def __init__(self, *, controller: AutomationController, count: int,
                 count_exp: int, count_thd: int, teams, settings, hard: bool):
        super().__init__()
        self._controller = controller
        self._count = count
        self._count_exp = count_exp
        self._count_thd = count_thd
        self._teams = teams
        self._settings = settings
        self._hard = hard

    @Slot()
    def run(self):
        _ensure_paths()
        from wbcore.bot import execute_me
        try:
            execute_me(
                count=self._count,
                count_exp=self._count_exp,
                count_thd=self._count_thd,
                teams=self._teams,
                settings=self._settings,
                hard=self._hard,
                app=self._controller,
                warning=self._emit_warning,
            )
        except Exception as exc:
            import traceback
            self._emit_warning(f"{type(exc).__name__}: {exc}\n{traceback.format_exc()}")
        finally:
            # User-stop returns without calling stop_execution; always
            # notify here. The controller's guard handles duplicates.
            QMetaObject.invokeMethod(
                self._controller, "stop_execution",
                Qt.ConnectionType.QueuedConnection)

    def _emit_warning(self, msg: str):
        self._controller.bot_warning.emit(str(msg))


class ConvertWorker(QObject):
    """One-shot worker for the scheduler's Convert Enkephalin task."""

    def __init__(self, *, controller: AutomationController):
        super().__init__()
        self._controller = controller

    @Slot()
    def run(self):
        _ensure_paths()
        from wbcore.bot import convert_enkephalin_only
        try:
            convert_enkephalin_only(
                app=self._controller,
                warning=self._emit_warning,
            )
        except Exception as exc:
            import traceback
            self._emit_warning(
                f"{type(exc).__name__}: {exc}\n{traceback.format_exc()}")
        finally:
            QMetaObject.invokeMethod(
                self._controller, "stop_execution",
                Qt.ConnectionType.QueuedConnection)

    def _emit_warning(self, msg: str):
        self._controller.bot_warning.emit(str(msg))
