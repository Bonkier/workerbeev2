# SPDX-License-Identifier: GPL-3.0-or-later
"""Single source of truth for WorkerBee's writable data directory.

Frozen builds write under %LOCALAPPDATA%\\WorkerBee - outside the install dir,
so the self-updater's `robocopy /MIR` never purges it (the config/ dir and
click_memory.json already live here). game.log / game.csv go here too, so run
statistics survive updates instead of being wiped with the old install.

Source runs use the repo root so dev logs/stats stay next to the tree. Kept
dependency-free (os + sys only) so the launcher can import it before anything
heavy is on the path."""
from __future__ import annotations

import os
import sys


def wb_data_dir() -> str:
    """The writable data dir: %LOCALAPPDATA%\\WorkerBee when frozen, repo root in dev."""
    if getattr(sys, "frozen", False):
        base = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~")
        path = os.path.join(base, "WorkerBee")
    else:
        # .../<repo>/src/wbcore/utils/datadir.py -> up 4 -> <repo> (the 'all data' root)
        path = os.path.dirname(os.path.dirname(os.path.dirname(
            os.path.dirname(os.path.abspath(__file__)))))
    try:
        os.makedirs(path, exist_ok=True)
    except OSError:
        pass
    return path


def game_log_path() -> str:
    return os.path.join(wb_data_dir(), "game.log")


def migrate_legacy_logs() -> None:
    """One-time: pull a pre-existing install-dir game.log into the new data dir.

    Older builds wrote game.log inside the install folder; moving it to
    %LOCALAPPDATA% would otherwise look like a history reset on first launch
    after the change. Idempotent - only copies when the new file is absent.
    """
    if not getattr(sys, "frozen", False):
        return
    dst = game_log_path()
    if os.path.exists(dst):
        return
    candidates = []
    try:
        candidates.append(os.path.dirname(os.path.abspath(sys.executable)))
    except Exception:
        pass
    mei = getattr(sys, "_MEIPASS", None)
    if mei:
        candidates.append(mei)
    for folder in candidates:
        old = os.path.join(folder, "game.log")
        if os.path.isfile(old):
            try:
                import shutil
                shutil.copy2(old, dst)
            except OSError:
                pass
            return
