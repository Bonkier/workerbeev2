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

    _setup_logging(base)

    from PySide6.QtCore import QCoreApplication, Qt
    QCoreApplication.setAttribute(Qt.ApplicationAttribute.AA_DontCreateNativeWidgetSiblings)

    from PySide6.QtWidgets import QApplication

    app = QApplication(sys.argv)
    # Load the saved theme before building the QSS so splash + the rest
    # open in the chosen theme.
    try:
        from gui_v2.themes import apply_saved_theme
        apply_saved_theme()
    except Exception:
        pass
    from gui_v2.style import build_global_qss
    app.setStyleSheet(build_global_qss())

    # `--update` is the production trigger; the env var is the simulation
    # back-channel - the helper relaunches with no args, so an inherited
    # env var is the only way to carry the mode through the chain.
    mode = (
        "update"
        if ("--update" in sys.argv
            or os.environ.get("WORKERBEE_FORCE_UPDATE_CHECK"))
        else "init"
    )
    from gui_v2.main_window import MainWindow
    win = MainWindow(mode=mode)
    win.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
