# SPDX-License-Identifier: GPL-3.0-or-later
"""WorkerBee v2 entry point."""

import os
import sys


def _setup_logging(base: str) -> None:
    """Route logging to game.log in the pipe-separated format the Logs page parses."""
    import logging
    import time
    from logging.handlers import RotatingFileHandler

    root = logging.getLogger()
    if any(getattr(h, "_workerbee_v2", False) for h in root.handlers):
        return  # idempotent
    root.setLevel(logging.INFO)

    class _NoMilliFormatter(logging.Formatter):
        def formatTime(self, record, datefmt=None):
            return time.strftime("%d/%m/%Y %H:%M:%S", time.localtime(record.created))

    fmt = _NoMilliFormatter(
        fmt="%(asctime)s | %(name)s | %(levelname)s | %(funcName)s:%(lineno)d | %(message)s",
    )
    try:
        file_handler = RotatingFileHandler(
            os.path.join(base, "game.log"),
            maxBytes=2 * 1024 * 1024, backupCount=2, encoding="utf-8",
        )
        file_handler.setFormatter(fmt)
        file_handler._workerbee_v2 = True
        root.addHandler(file_handler)
    except OSError as exc:
        print(f"could not open game.log: {exc}")

    # Windowed/packaged builds (pythonw, Nuitka) have no stderr.
    if sys.stderr is not None:
        console = logging.StreamHandler()
        console.setFormatter(fmt)
        console._workerbee_v2 = True
        root.addHandler(console)

    logging.info("WorkerBee v2 started")


def _block_if_update_in_progress() -> bool:
    """Refuse to start while the self-update helper is mid-swap.

    The helper relaunches with `--post-update`, which clears the lock and
    proceeds. Any other launch during the swap window is a stray
    double-click that would race it. Uses native MessageBoxW so we don't
    spin up Qt just for a wait message.
    """
    # Late import: runs before sys.path is set up.
    base = os.path.dirname(os.path.abspath(__file__))
    src = os.path.join(base, "src")
    for p in (base, src):
        if p not in sys.path:
            sys.path.insert(0, p)
    from gui_v2 import updater

    if "--post-update" in sys.argv:
        updater.clear_update_lock()
        return False

    if not updater.is_update_in_progress():
        return False

    # Stray launch mid-swap: tell the user to wait.
    try:
        import ctypes
        ctypes.windll.user32.MessageBoxW(
            0,
            "WorkerBee is finishing an update right now. Give it about "
            "30 seconds and it will reopen itself with the new version.",
            "WorkerBee  -  Update in progress",
            0x40 | 0x0,                     # MB_ICONINFORMATION | MB_OK
        )
    except Exception:
        # No GUI? Silent exit beats racing the swap.
        pass
    return True


def main() -> int:
    if _block_if_update_in_progress():
        return 0

    # Repo root + src/ on sys.path so gui_v2 imports resolve.
    base = os.path.dirname(os.path.abspath(__file__))
    src = os.path.join(base, "src")
    for p in (base, src):
        if p not in sys.path:
            sys.path.insert(0, p)

    # Log into the writable data dir (%LOCALAPPDATA%\WorkerBee when frozen) so
    # game.log/game.csv - and the run statistics derived from them - survive the
    # self-updater's robocopy /MIR instead of being wiped with the old install.
    from wbcore.utils.datadir import wb_data_dir, migrate_legacy_logs
    migrate_legacy_logs()
    _setup_logging(wb_data_dir())

    from PySide6.QtCore import QCoreApplication, Qt
    QCoreApplication.setAttribute(Qt.ApplicationAttribute.AA_DontCreateNativeWidgetSiblings)

    from PySide6.QtWidgets import QApplication

    app = QApplication(sys.argv)
    # Load the saved theme before building the QSS so splash + the rest
    # open in the chosen theme.
    try:
        # Skin first (shape + type tokens), then the theme's colour palette.
        from gui_v2.skins import apply_saved_skin
        apply_saved_skin()
    except Exception:
        pass
    try:
        from gui_v2.themes import apply_saved_theme
        apply_saved_theme()
    except Exception:
        pass
    from gui_v2.style import build_global_qss
    app.setStyleSheet(build_global_qss())

    # Hover/press/click feedback for every button, including ones built later.
    # Installed before the window so the splash gets it too.
    from gui_v2.interact import install as install_feedback
    install_feedback(app)

    # --preview [splash|overlay|all] opens the chrome on its own, with sample
    # state, so the initializer and the run overlay can be looked at without
    # starting a run or waiting on an update check.
    if "--preview" in sys.argv:
        return _run_preview(app, sys.argv)

    # Every launch checks GitHub for a newer release; if already current
    # the splash rolls into normal init silently. Pass --no-update-check
    # to skip the network call (offline dev / source-tree runs).
    mode = "init" if "--no-update-check" in sys.argv else "update"
    from gui_v2.main_window import MainWindow
    win = MainWindow(mode=mode)
    win.show()
    return app.exec()


def _run_preview(app, argv):
    """Show the splash and/or the run overlay, populated, and nothing else."""
    idx = argv.index("--preview")
    target = argv[idx + 1].lower() if len(argv) > idx + 1 else "all"
    if target.startswith("-"):
        target = "all"
    windows = []

    if target in ("all", "splash", "init", "initializer"):
        from gui_v2.splash import SplashWidget
        from gui_v2.theme import Sizing
        sp = SplashWidget()
        sp.setWindowTitle("WorkerBee splash preview")
        sp.resize(Sizing.SPLASH_W, Sizing.SPLASH_H)
        sp.set_status("Loading templates...", 62)
        sp.close_clicked.connect(app.quit)
        sp.show()
        windows.append(sp)

    if target in ("all", "overlay", "hud"):
        from gui_v2.overlay import RunOverlay
        ov = RunOverlay(preview=True)
        ov.load_demo()
        ov.show()
        windows.append(ov)

    if not windows:
        print(f"--preview: unknown target {target!r} "
              f"(use splash, overlay, or all)")
        return 2

    if "--no-reload" not in argv:
        _install_live_reload(app, argv)
    return app.exec()


def _install_live_reload(app, argv):
    """Relaunch the preview whenever a UI source file changes.

    Python cannot swap a class out from under live widgets, so the honest
    way to show an edit is to restart: the window blinks and comes back with
    the change, about a second after the file is saved. Pass --no-reload to
    turn it off.
    """
    import glob
    from PySide6.QtCore import QProcess, QTimer

    here = os.path.dirname(os.path.abspath(__file__))
    patterns = (os.path.join(here, "gui_v2", "*.py"),
                os.path.join(here, "v2_launcher.py"))

    def stamp():
        out = {}
        for pat in patterns:
            for path in glob.glob(pat):
                try:
                    out[path] = os.path.getmtime(path)
                except OSError:
                    pass
        return out

    state = {"seen": stamp()}

    def check():
        now = stamp()
        if now == state["seen"]:
            return
        state["seen"] = now
        print("--preview: sources changed, reloading")
        QProcess.startDetached(sys.executable, argv)
        app.quit()

    timer = QTimer(app)
    timer.setInterval(1000)
    timer.timeout.connect(check)
    timer.start()
    app._wb_reload_timer = timer          # keep it alive
    print("--preview: watching gui_v2 for changes (--no-reload to disable)")


if __name__ == "__main__":
    sys.exit(main())
