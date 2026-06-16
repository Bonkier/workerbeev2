# SPDX-License-Identifier: GPL-3.0-or-later
"""Wires the v2 UI to the automation controller.

Owns one AutomationController. Connects the pages' start/stop signals to
it (building the bot's run config from the current UI state via
run_config), reflects bot state back into the UI (button enable/disable,
warnings), and registers global hotkeys so the user can start/stop while
the Limbus window is focused.
"""

import logging
import os
import sys
import threading
import time

from PySide6.QtCore import QObject, Signal, Qt
from PySide6.QtWidgets import QMessageBox

from .automation_controller import AutomationController
from .overlay import RunOverlay
from .run_config import build_md_run, build_lux_run
from .settings import load_section

# Default global hotkeys (match v1). Wired to the `keyboard` library if it
# imports; otherwise hotkeys are simply unavailable (buttons still work).
_HOTKEYS = {
    "mirror": "ctrl+q",
    "exp": "ctrl+e",
    "thread": "ctrl+r",
    "stop": "f2",
}


class RunCoordinator(QObject):
    # Emitted from the keyboard-hook thread; queued to the GUI thread.
    _hk_md = Signal()
    _hk_exp = Signal()
    _hk_thread = Signal()
    _hk_stop = Signal()
    # Bot-thread telemetry, marshalled to the GUI thread for the overlay.
    _tele_event = Signal(dict)

    def __init__(self, main_ui, parent: QObject | None = None):
        super().__init__(parent)
        self._ui = main_ui
        self._controller = AutomationController(self)
        self._audio_lock = threading.Lock()
        # Live in-progress state (Discord stats + future dashboard cards).
        # Initialised here so attribute access before the first bot start
        # never blows up (`_discord_stats` may be polled while idle).
        self._reset_live_state()

        self._md = main_ui.page("mirror_dungeon")
        self._lux = main_ui.page("luxcavation")
        self._settings = main_ui.page("settings")
        self._scheduler = main_ui.page("scheduler")

        # Scheduler runtime: queue of pending tasks, current task index,
        # and a QTimer for the Wait task type. The scheduler walks the
        # queue top-to-bottom, advancing to the next task on bot_stopped
        # (for run-type tasks) or on the timer's timeout (Wait).
        self._sched_queue: list[dict] = []
        self._sched_idx = 0
        self._sched_active = False
        # QTimer for the Wait task - created lazily so we don't pull it
        # in when the scheduler is never used. Single-shot.
        from PySide6.QtCore import QTimer as _QTimer
        self._wait_timer = _QTimer(self)
        self._wait_timer.setSingleShot(True)
        self._wait_timer.timeout.connect(self._sched_advance)

        # Button-start countdown: gives the user time to tab into Limbus
        # before the bot grabs input. Hotkeys skip this since the user is
        # already in the game when they trigger them.
        self._countdown_timer = _QTimer(self)
        self._countdown_timer.setInterval(1000)
        self._countdown_timer.timeout.connect(self._on_countdown_tick)
        self._countdown_remaining = 0
        self._countdown_action = None
        self._countdown_page = None
        self._BUTTON_START_DELAY_S = 5

        # Page -> controller.
        main_ui.start_requested.connect(
            lambda: self._arm_button_start(self._start_md, self._md))
        main_ui.stop_requested.connect(self._stop)
        if self._lux is not None:
            self._lux.start_exp_requested.connect(
                lambda: self._arm_button_start(
                    lambda: self._start_lux("exp"), self._lux))
            self._lux.start_thread_requested.connect(
                lambda: self._arm_button_start(
                    lambda: self._start_lux("thread"), self._lux))
            self._lux.stop_requested.connect(self._stop)
        if self._scheduler is not None:
            self._scheduler.run_requested.connect(self._scheduler_start)
            self._scheduler.stop_requested.connect(self._scheduler_stop)

        # Controller -> UI.
        self._controller.bot_started.connect(self._on_started)
        self._controller.bot_stopped.connect(self._on_stopped)
        self._controller.bot_warning.connect(self._on_warning)

        # Hotkeys -> GUI thread (queued).
        # Start hotkeys toggle (press to start, press again to stop), as in
        # v1; F2 always stops. The Start/Stop buttons stay explicit.
        self._hk_md.connect(self._toggle_md)
        self._hk_exp.connect(lambda: self._toggle_lux("exp"))
        self._hk_thread.connect(lambda: self._toggle_lux("thread"))
        self._hk_stop.connect(self._stop)
        self._install_hotkeys()
        self._prewarm_audio()

        # Run overlay (HUD + debug visualizers).
        self._overlay = None
        self._tele = None
        self._setup_overlay()

        # Give the Settings page the control/stats/screenshot hooks the
        # Discord bot needs (it owns the config UI but not the controls).
        self._wire_discord()

    # --- starting ---------------------------------------------------
    def _inject_global_settings(self, settings: dict) -> None:
        """Fold Settings-page globals (mouse speed, movement profile, rhythm)
        into the run's settings dict so the bot applies them via execute_me.
        These live on the Settings page (section 'app_settings'), not the
        per-run MD/Lux pages."""
        app = load_section("app_settings") or {}
        settings["mouse_speed"] = int(app.get("mouse_speed", 100) or 100)
        prof = app.get("macro_profile", "Safe")
        settings["macro_profile"] = (
            prof if prof in ("Safe", "Fast", "Chaotic") else "Safe")
        settings["rhythm"] = bool(app.get("rhythm", True))

    def _start_md(self):
        if self._controller.is_running():
            return
        try:
            sinners = self._settings.sinner_selection() if self._settings else {}
            count, teams, settings, hard = build_md_run(self._md.state(), sinners)
        except ValueError as exc:
            self._on_warning(str(exc))
            return
        except Exception as exc:  # never let a config bug crash the click
            self._on_warning(f"Could not build run: {exc}")
            return
        self._inject_global_settings(settings)
        logging.info("Mirror Dungeon run requested (%s run(s), %s)",
                     count, "hard" if hard else "normal")
        self._controller.start_run(teams=teams, settings=settings, hard=hard,
                                   count=count)

    def _start_lux(self, mode: str):
        if self._controller.is_running() or self._lux is None:
            return
        try:
            sinners = self._settings.sinner_selection() if self._settings else {}
            ce, ct, teams, settings, hard = build_lux_run(
                mode, self._lux.state(), self._md.state(), sinners)
        except Exception as exc:
            self._on_warning(f"Could not build Lux run: {exc}")
            return
        self._inject_global_settings(settings)
        logging.info("Luxcavation %s run requested", mode)
        self._controller.start_run(teams=teams, settings=settings, hard=hard,
                                   count=0, count_exp=ce, count_thd=ct)

    def _stop(self):
        if self._countdown_timer.isActive():
            self._cancel_countdown()
            return
        if self._controller.is_running():
            logging.info("Stop requested by user")
        self._controller.stop()

    def _toggle_md(self):
        """Hotkey: start Mirror Dungeon, or stop if a run is already active."""
        if self._countdown_timer.isActive():
            self._cancel_countdown()
            return
        if self._controller.is_running():
            self._stop()
        else:
            self._start_md()

    def _toggle_lux(self, mode: str):
        """Hotkey: start the given Lux mode, or stop if a run is active."""
        if self._countdown_timer.isActive():
            self._cancel_countdown()
            return
        if self._controller.is_running():
            self._stop()
        else:
            self._start_lux(mode)

    # --- button-start countdown ------------------------------------------
    def _arm_button_start(self, start_callable, page):
        """Arm a delayed start so the user can tab into Limbus first."""
        if self._controller.is_running() or self._countdown_timer.isActive():
            return
        self._countdown_action = start_callable
        self._countdown_page = page
        self._countdown_remaining = self._BUTTON_START_DELAY_S
        self._apply_arming(self._countdown_remaining)
        self._countdown_timer.start()

    def _on_countdown_tick(self):
        self._countdown_remaining -= 1
        if self._countdown_remaining <= 0:
            self._fire_pending_start()
        else:
            self._apply_arming(self._countdown_remaining)

    def _fire_pending_start(self):
        self._countdown_timer.stop()
        action = self._countdown_action
        self._apply_arming(0)
        self._countdown_action = None
        self._countdown_page = None
        if action:
            action()

    def _cancel_countdown(self):
        if not self._countdown_timer.isActive():
            return
        self._countdown_timer.stop()
        self._apply_arming(0)
        self._countdown_action = None
        self._countdown_page = None
        logging.info("Pending start cancelled")

    def _apply_arming(self, seconds: int):
        page = self._countdown_page
        if page is not None and hasattr(page, "set_arming"):
            page.set_arming(seconds)

    # --- scheduler ------------------------------------------------------
    # The scheduler page emits `run_requested(list)` with the full task
    # queue when the user clicks Run. We walk it top-to-bottom, advancing
    # to the next task on `bot_stopped` for run-type tasks or on the
    # wait-timer's timeout for Wait. Convert Enkephalin runs as a
    # one-shot bot worker.

    _SCHED_LABELS = {
        "md": "Mirror Dungeon", "exp": "EXP Luxcavation",
        "thread": "Thread Luxcavation", "wait": "Wait",
        "convert": "Convert Enkephalin",
    }

    def _scheduler_start(self, tasks: list):
        if self._sched_active:
            return
        if self._controller.is_running():
            self._on_warning("Cannot start scheduler: a run is already active.")
            return
        runnable = [t for t in tasks
                    if isinstance(t, dict) and t.get("enabled", True)]
        if not runnable:
            self._on_warning("Scheduler has no enabled tasks.")
            return
        self._sched_queue = runnable
        self._sched_idx = 0
        self._sched_active = True
        logging.info("Scheduler: queue of %d task(s) starting", len(runnable))
        if self._scheduler is not None:
            self._scheduler.set_running(True)
        self._sched_run_current()

    def _scheduler_stop(self):
        """User-requested halt. Stops the active task (if any), aborts the
        wait timer, and clears the queue so no further tasks fire."""
        if not self._sched_active:
            return
        logging.info("Scheduler: stop requested")
        self._sched_active = False
        self._wait_timer.stop()
        self._sched_queue = []
        self._sched_idx = 0
        if self._controller.is_running():
            self._controller.stop()
        if self._scheduler is not None:
            self._scheduler.set_running(False)

    def _sched_run_current(self):
        """Dispatch the task at `self._sched_idx`. For run-type tasks we
        spin up the bot and wait for bot_stopped; for Wait we arm the
        timer; for Convert we spawn the convert worker."""
        if not self._sched_active or self._sched_idx >= len(self._sched_queue):
            self._scheduler_done()
            return
        task = self._sched_queue[self._sched_idx]
        kind = task.get("type", "")
        label = self._SCHED_LABELS.get(kind, kind)
        logging.info(
            "Scheduler: task %d/%d - %s",
            self._sched_idx + 1, len(self._sched_queue), label)

        try:
            if kind == "md":
                self._sched_run_md(task)
            elif kind == "exp":
                self._sched_run_lux(task, mode="exp")
            elif kind == "thread":
                self._sched_run_lux(task, mode="thread")
            elif kind == "wait":
                self._sched_run_wait(task)
            elif kind == "convert":
                self._sched_run_convert(task)
            else:
                logging.warning(
                    "Scheduler: unknown task type %r - skipping", kind)
                self._sched_advance()
        except Exception as exc:
            self._on_warning(f"Scheduler task '{label}' failed: {exc}")
            self._scheduler_done()

    def _sched_run_md(self, task: dict):
        try:
            sinners = self._settings.sinner_selection() if self._settings else {}
            count, teams, settings, hard = build_md_run(
                self._md.state(), sinners)
        except Exception as exc:
            self._on_warning(f"Scheduler MD config error: {exc}")
            self._scheduler_done()
            return
        # Scheduler-task run count overrides the MD page's value so each
        # task fires its own configured number of runs.
        count = int(task.get("runs", count) or count)
        self._inject_global_settings(settings)
        self._controller.start_run(
            teams=teams, settings=settings, hard=hard, count=count)

    def _sched_run_lux(self, task: dict, *, mode: str):
        try:
            sinners = self._settings.sinner_selection() if self._settings else {}
            ce, ct, teams, settings, hard = build_lux_run(
                mode, self._lux.state(), self._md.state(), sinners)
        except Exception as exc:
            self._on_warning(f"Scheduler Lux config error: {exc}")
            self._scheduler_done()
            return
        runs = int(task.get("runs", 1) or 1)
        if mode == "exp":
            ce = runs
        else:
            ct = runs
        # Per-task skip flag. Reset between scheduler tasks so an earlier
        # skip task doesn't leak into a later non-skip one.
        settings["lux_skip_exp"] = bool(task.get("skip", False)) if mode == "exp" else False
        settings["lux_skip_thd"] = bool(task.get("skip", False)) if mode == "thread" else False
        self._inject_global_settings(settings)
        self._controller.start_run(
            teams=teams, settings=settings, hard=hard,
            count=0, count_exp=ce, count_thd=ct)

    def _sched_run_wait(self, task: dict):
        """Wait task: arm the single-shot timer for `duration` HH:MM:SS.
        Timer's timeout fires `_sched_advance` which moves on."""
        secs = self._parse_duration(task.get("duration", "00:00:00"))
        secs = max(1, secs)   # guard against accidental 0-length waits
        logging.info("Scheduler: waiting %d seconds", secs)
        self._wait_timer.start(secs * 1000)

    def _sched_run_convert(self, task: dict):
        # Convert uses the same controller pipeline, but a one-shot worker.
        # Inject global settings so the mouse-speed / rhythm profile is
        # applied to the conversion clicks too.
        settings: dict = {}
        self._inject_global_settings(settings)
        # Stash on params so the convert worker picks them up.
        try:
            from wbcore.utils import params as p
            p.MOUSE_SPEED = int(settings.get("mouse_speed", 100) or 100)
            p.MACRO_PROFILE = str(settings.get("macro_profile", "SAFE")).upper()
            p.MACRO_RHYTHM = bool(settings.get("rhythm", True))
            p.NETZACH = True       # gate the convert flow on
        except Exception:
            pass
        self._controller.start_convert()

    @staticmethod
    def _parse_duration(text: str) -> int:
        try:
            parts = [int(x) for x in str(text).split(":")]
        except (TypeError, ValueError):
            return 0
        if len(parts) == 3:
            h, m, s = parts
        elif len(parts) == 2:
            h, m, s = 0, parts[0], parts[1]
        else:
            return 0
        return max(0, h * 3600 + m * 60 + s)

    def _sched_advance(self):
        """Move on to the next task in the queue. Called from `bot_stopped`
        when a run-type task finishes, or from `_wait_timer.timeout` when
        a Wait task elapses."""
        if not self._sched_active:
            return
        self._sched_idx += 1
        if self._sched_idx >= len(self._sched_queue):
            self._scheduler_done()
            return
        self._sched_run_current()

    def _scheduler_done(self):
        """Queue exhausted (or aborted). Cleans up state and flips the
        scheduler page back to idle."""
        if not self._sched_active and not self._sched_queue:
            return
        logging.info("Scheduler: queue finished")
        self._sched_active = False
        self._wait_timer.stop()
        self._sched_queue = []
        self._sched_idx = 0
        if self._scheduler is not None:
            self._scheduler.set_running(False)

    # --- live run state (for Discord + dashboard mid-run reporting) -
    def _reset_live_state(self):
        self._run_start_ts = None        # set on bot_started
        self._cur_phase = ""             # last "phase" event
        self._cur_floor = 0              # last "floor" event
        self._cur_pack = ""               # last "floor" event's pack
        self._last_action = ""           # last "action" event
        self._run_index = 0              # last "run" event's iteration index
        self._run_total = 0              # last "run" event's total count

    # --- controller feedback ---------------------------------------
    def _on_started(self):
        logging.info("Automation started")
        self._reset_live_state()
        self._run_start_ts = time.time()
        self._play_alert("on")
        self._overlay_run(True)
        for page in (self._md, self._lux):
            if page is not None and hasattr(page, "set_running"):
                page.set_running(True)

    def _on_stopped(self):
        logging.info("Automation stopped")
        self._play_alert("off")
        self._overlay_run(False)
        for page in (self._md, self._lux):
            if page is not None and hasattr(page, "set_running"):
                page.set_running(False)
        # Snapshot final live state for the post-stop Discord ping, then
        # clear so a fresh start doesn't inherit stale fields.
        self._reset_live_state()
        self._refresh_stats()
        # If a scheduler queue is active, advance to the next task. The
        # current task was a run-type one (MD / EXP / THD / Convert) and
        # the bot has just stopped - either by completing or by failing,
        # both of which should pop the queue forward.
        if self._sched_active:
            self._sched_advance()

    def _on_warning(self, msg: str):
        logging.warning("%s", msg)
        QMessageBox.warning(self._ui, "WorkerBee", msg)

    # --- run stats -------------------------------------------------
    def _on_tele_for_stats(self, event: dict):
        """Record a finished run and refresh the stat displays. Invoked on
        the GUI thread (the telemetry signal is queued), so touching the
        stats file and the widgets here is safe. Independent of the overlay
        so stats update even when the overlay is off."""
        if not isinstance(event, dict):
            return
        kind = event.get("kind")
        # Live state mirrors (used by _discord_stats while a run is in
        # progress so Discord reports useful info even before any run has
        # completed).
        if kind == "phase":
            self._cur_phase = str(event.get("name", ""))
            return
        if kind == "action":
            self._last_action = str(event.get("text", ""))
            return
        if kind == "run":
            self._run_index = int(event.get("i", 0) or 0)
            self._run_total = int(event.get("total", 0) or 0)
            return
        if kind == "floor":
            # Buffer each floor's pack pick, timestamped on receipt so the gaps
            # between consecutive picks become per-floor clear times.
            buf = getattr(self, "_cur_floors", None)
            if buf is None:
                buf = self._cur_floors = []
            buf.append({"floor": int(event.get("floor", 0) or 0),
                        "pack": str(event.get("pack", "")),
                        "ts": time.time()})
            self._cur_floor = int(event.get("floor", 0) or 0)
            self._cur_pack = str(event.get("pack", ""))
            return
        if kind == "restart":
            # A run was aborted partway (e.g. THRILL F1 forfeit). Stash
            # the elapsed time so it shows up as a "Restart - MM:SS"
            # entry on the NEXT completed run's floor breakdown. Also
            # clears the current floors buffer because those floor picks
            # belong to the aborted attempt, not the next one.
            restarts = getattr(self, "_pending_restarts", None)
            if restarts is None:
                restarts = self._pending_restarts = []
            restarts.append({
                "floor": 0,
                "pack": "Restart",
                "duration": float(event.get("duration", 0) or 0),
            })
            self._cur_floors = []
            return
        if kind != "run_result":
            return
        completed = bool(event.get("completed"))
        try:
            from . import stats
            stats.record_run(
                completed=completed,
                duration=float(event.get("duration", 0) or 0),
                team=str(event.get("team", "")),
                mode=str(event.get("mode", "mirror")),
                floors=self._finalize_floors(),
            )
        except Exception:
            pass
        # Clear the per-run live cursor so a fresh start within the same
        # session reports F0 (idle between runs) until the next floor event.
        self._cur_floor = 0
        self._cur_pack = ""
        # Bump the start time so "elapsed" reflects the NEXT run, not the
        # last finished one. The bot resumes immediately for multi-run
        # configs; this prevents the elapsed clock from drifting forever.
        self._run_start_ts = time.time()
        self._refresh_stats()

    def _finalize_floors(self) -> list:
        """Turn the buffered per-floor pack picks into [{floor, pack,
        duration}] (each floor's duration = gap to the next pick, or to now
        for the last) and clear the buffer for the next run. Pending
        Restart entries from aborted earlier attempts (THRILL F1 forfeit)
        are prepended in order so the next completed run's floor list
        reads e.g. 'Restart - 5:32 / F1 - FlatbrokeGamblers - 6:32 / ...'."""
        buf = getattr(self, "_cur_floors", None) or []
        self._cur_floors = []
        restarts = getattr(self, "_pending_restarts", None) or []
        self._pending_restarts = []
        end = time.time()
        out = list(restarts)
        for i, f in enumerate(buf):
            nxt = buf[i + 1]["ts"] if i + 1 < len(buf) else end
            out.append({"floor": f["floor"], "pack": f["pack"],
                        "duration": max(0.0, nxt - f["ts"])})
        return out

    def _refresh_stats(self):
        """Pull the new aggregates into the Dashboard and Stats pages."""
        for key in ("dashboard", "stats"):
            page = self._ui.page(key)
            if page is not None and hasattr(page, "refresh_stats"):
                try:
                    page.refresh_stats()
                except Exception:
                    pass

    # --- run overlay -----------------------------------------------
    def _setup_overlay(self):
        """Create the over-the-game overlay, route bot telemetry to it,
        feed it the log stream as the 'recent actions', and keep its
        toggles synced with Settings. Best effort: a failure here leaves
        the overlay off without affecting runs."""
        try:
            from wbcore.utils import telemetry as tele
        except Exception:
            return
        self._tele = tele
        # Bot thread -> GUI: telemetry events via a queued signal. Wire the
        # stats recorder and the sink FIRST so run statistics are captured
        # even if the overlay widget below fails to create or is turned off.
        self._tele_event.connect(self._on_tele_for_stats)
        tele.set_sink(self._tele_event.emit)
        try:
            self._overlay = RunOverlay(owner_hwnd_getter=self._owner_hwnd)
        except Exception:
            self._overlay = None
        if self._overlay is not None:
            self._tele_event.connect(self._overlay.on_event)
        self._attach_log_feed()
        if self._settings is not None and hasattr(self._settings, "overlay_changed"):
            self._settings.overlay_changed.connect(self._apply_overlay_toggles)
        # Sync telemetry flags + overlay layers to the persisted toggles.
        self._apply_overlay_toggles(self._current_overlay_cfg())

    def _owner_hwnd(self) -> int:
        try:
            win = self._ui.window()
            return int(win.winId()) if win is not None else 0
        except Exception:
            return 0

    def _attach_log_feed(self):
        """Forward log records to the overlay's 'recent actions'. The bot
        already logs its meaningful steps, so this reuses them instead of
        instrumenting every action by hand."""
        coordinator = self

        class _OverlayLogFeed(logging.Handler):
            def emit(self, record):
                if coordinator._tele is None:
                    return
                try:
                    coordinator._tele.action(record.getMessage())
                except Exception:
                    pass

        handler = _OverlayLogFeed()
        handler.setLevel(logging.INFO)
        logging.getLogger().addHandler(handler)

    def _current_overlay_cfg(self) -> dict:
        if self._settings is not None and hasattr(self._settings, "overlay_settings"):
            try:
                return self._settings.overlay_settings()
            except Exception:
                pass
        return (load_section("app_settings") or {}).get("overlay") or {}

    def _apply_overlay_toggles(self, cfg: dict):
        cfg = cfg or {}
        hud = bool(cfg.get("hud", True))
        vision = bool(cfg.get("vision", False))
        path = bool(cfg.get("path", False))
        if self._tele is not None:
            self._tele.set_enabled(hud=hud, vision=vision, path=path)
        if self._overlay is not None:
            self._overlay.set_toggles(hud, vision, path)

    def _overlay_run(self, active: bool):
        if self._overlay is None:
            return
        if active:
            self._apply_overlay_toggles(self._current_overlay_cfg())
            self._overlay.on_event({"kind": "reset"})
        self._overlay.set_run_active(active)

    # --- discord ---------------------------------------------------
    def _wire_discord(self):
        """Hand the Settings page the callbacks/providers the Discord bot
        constructor requires. The bot's control buttons route through our
        existing hotkey signals (which marshal to the GUI thread), and the
        screenshot/stats are pulled live."""
        if self._settings is None or not hasattr(self._settings, "set_discord_hooks"):
            return
        base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        self._settings.set_discord_hooks({
            "callbacks": {
                "start_mirror": lambda: self._disc_start(self._hk_md,
                                                         "Mirror Dungeon started"),
                "start_exp": lambda: self._disc_start(self._hk_exp,
                                                      "EXP run started"),
                "start_threads": lambda: self._disc_start(self._hk_thread,
                                                          "Thread run started"),
                "start_chain": lambda: (False, "Chaining is not available in v2"),
                "stop_all": self._disc_stop,
            },
            "get_stats": self._discord_stats,
            "get_screenshot": self._discord_screenshot,
            "log_path": os.path.join(base, "game.log"),
        })

    def _disc_start(self, signal, message):
        if self._controller.is_running():
            return (False, "A run is already in progress")
        signal.emit()   # thread-safe: queued to the GUI thread
        return (True, message)

    def _disc_stop(self):
        running = self._controller.is_running()
        self._hk_stop.emit()
        return (True, "Stop requested" if running else "Nothing was running")

    def _discord_stats(self) -> dict:
        """Stats payload for the Discord status embed.

        Layout:
            Status               Running | Idle
            (running only) Phase         <high-level activity>
            (running only) Current floor F<n>: <pack>
            (running only) Elapsed       Mm Ss
            (running only) Run           i / total
            (running only) Last action   <truncated log line>
            Runs completed       N
            Failed runs          N
            Success rate         X%
            Total grind time     Hh Mm

        Live fields are only emitted when a run is active. They use data
        captured from the in-flight telemetry stream (phase, floor,
        action, run iteration) so Discord reports something useful even
        before the first run finishes - which was the case for any
        session shorter than a single Thrill (~13 min) or Mirror Dungeon
        (~30+ min) run.
        """
        running = self._controller.is_running()
        out = {"Status": "Running" if running else "Idle"}
        if running:
            # Live in-progress fields. Each is optional - we only add
            # populated ones so empty rows do not clutter the embed.
            if self._cur_phase:
                out["Phase"] = self._cur_phase
            if self._cur_floor:
                pack = self._cur_pack or "(picking)"
                out["Current floor"] = f"F{self._cur_floor}: {pack}"
            if self._run_start_ts:
                elapsed = max(0.0, time.time() - self._run_start_ts)
                try:
                    from . import stats
                    out["Elapsed"] = stats.fmt_duration(elapsed)
                except Exception:
                    pass
            if self._run_total:
                out["Run"] = f"{max(1, self._run_index)} / {self._run_total}"
            if self._last_action:
                # Keep it tidy: Discord fields wrap, but a single embedded
                # row reading the whole log line is noisy.
                msg = self._last_action
                if len(msg) > 60:
                    msg = msg[:57] + "..."
                out["Last action"] = msg
        try:
            from . import stats
            agg = stats.aggregate()
            out["Runs completed"] = str(agg["completed"])
            out["Failed runs"] = str(agg["failed"])
            out["Success rate"] = f"{agg['success_rate']:.0f}%"
            out["Total grind time"] = stats.fmt_total(agg["total_time"])
        except Exception:
            pass
        return out

    def _discord_screenshot(self):
        """Live PNG of the game window, or None when no run is active."""
        if not self._controller.is_running():
            return None
        try:
            import cv2
            import wbcore.utils.params as p
            from wbcore.utils import os_windows_backend as gui
            win = p.WINDOW
            if not win or win[2] <= 1:
                return None
            arr = gui.screenshot(region=(int(win[0]), int(win[1]),
                                         int(win[2]), int(win[3])))
            ok, buf = cv2.imencode(".png", arr)
            return buf.tobytes() if ok else None
        except Exception:
            return None

    # --- audio ------------------------------------------------------
    def _audio_manager(self):
        """Import and lazily initialize the shared AudioManager. Safe to
        call from the prewarm thread and the GUI thread at once (the lock
        serializes the one-time pygame init)."""
        base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        for p in (base, os.path.join(base, "src")):
            if p not in sys.path:
                sys.path.insert(0, p)
        from audio_manager import AudioManager
        mgr = AudioManager()
        if not getattr(mgr, "initialized", False):
            with self._audio_lock:
                if not getattr(mgr, "initialized", False):
                    mgr.initialize(base)
        return mgr

    def _prewarm_audio(self):
        """Initialize audio off the GUI thread at startup. pygame's first
        init costs ~1-2s; doing it lazily on the first run made the start
        cue lag behind the bot. Warming it now means the first play is
        instant."""
        def _warm():
            try:
                self._audio_manager()
            except Exception:
                pass
        threading.Thread(target=_warm, name="AudioPrewarm",
                         daemon=True).start()

    def _play_alert(self, name: str):
        """Play the start ('on') / stop ('off') alert through the shared
        AudioManager, honoring the Settings audio toggle + volume. Best
        effort: silently no-ops if audio alerts are off or unavailable."""
        cfg = load_section("app_settings") or {}
        if not cfg.get("audio_alerts", True):
            return
        volume = int(cfg.get("volume", 70))
        try:
            self._audio_manager().play_sound(name, volume / 100.0, force=True)
        except Exception as exc:
            print(f"alert sound failed: {exc}")

    # --- hotkeys ----------------------------------------------------
    def _install_hotkeys(self):
        try:
            import keyboard
        except Exception:
            return
        emitters = {
            "mirror": self._hk_md.emit,
            "exp": self._hk_exp.emit,
            "thread": self._hk_thread.emit,
            "stop": self._hk_stop.emit,
        }
        for action, combo in _HOTKEYS.items():
            try:
                keyboard.add_hotkey(combo, emitters[action])
            except Exception:
                pass
