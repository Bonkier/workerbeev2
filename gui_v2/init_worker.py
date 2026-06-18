# SPDX-License-Identifier: GPL-3.0-or-later
"""Splash-screen init worker + update workers. Update workers run
gui_v2.updater on a QThread and reshape progress callbacks into signals."""

import os
import time
import traceback

from PySide6.QtCore import QObject, QThread, Signal

from . import updater


class InitWorker(QObject):
    """Owned by an InitThread - don't construct directly."""

    progress = Signal(str, int)       # status, percent 0-100
    finished = Signal(bool, str)      # (ok, error_message_if_any)

    # Placeholder pacing until real heavy steps are wired up.
    _DEMO_STEP_DELAY = 0.6

    def run(self):
        try:
            steps = [
                ("Loading paths",          12),
                ("Loading configuration",  30),
                ("Preparing UI theme",     48),
                ("Warming up image cache", 70),
                ("Opening input bridge",   88),
                ("Ready",                  100),
            ]
            for status, pct in steps:
                self.progress.emit(status, pct)
                time.sleep(self._DEMO_STEP_DELAY)
            self.finished.emit(True, "")
        except Exception as exc:
            tb = traceback.format_exc()
            self.finished.emit(False, f"{type(exc).__name__}: {exc}\n{tb}")


class UpdateCheckWorker(QObject):
    """Check GitHub for the latest release. `result` carries the
    updater.check_latest_release dict for the caller to act on."""

    progress = Signal(str, int)
    finished = Signal(bool, str)
    # {"version": "2.0.1", "download_url": "...", "size": 176513811}
    result = Signal(dict)

    def run(self):
        try:
            self.progress.emit("Checking for updates", 6)
            info = updater.check_latest_release()
            self.result.emit(info)
            self.finished.emit(True, "")
        except updater.UpdateError as exc:
            self.finished.emit(False, str(exc))
        except Exception as exc:
            tb = traceback.format_exc()
            self.finished.emit(
                False, f"{type(exc).__name__}: {exc}\n{tb}")


class UpdateApplyWorker(QObject):
    """Download with a byte counter, then spawn the helper batch that
    swaps the install dir and restarts. Raises UpdateError without a URL."""

    progress = Signal(str, int)
    finished = Signal(bool, str)

    def __init__(self, download_url: str = "", version: str = "",
                 parent: QObject | None = None):
        super().__init__(parent)
        self._url = download_url
        self._version = version

    def run(self):
        try:
            if not self._url:
                raise updater.UpdateError(
                    "No download URL was supplied to the update worker."
                )
            if not updater.is_frozen():
                raise updater.UpdateError(
                    "Source-tree runs can't self-update. "
                    "Rebuild via PyInstaller for in-app updates."
                )

            zip_path = updater.staging_zip_path(self._version or "latest")

            def on_progress(done: int, total: int) -> None:
                # 0..85% is download; helper batch handles the rest.
                # Keep ~28 chars so the byte counter fits beside it.
                if total <= 0:
                    pct = 0
                else:
                    pct = max(0, min(85, int(done * 85 / total)))
                done_mb = done / (1024 * 1024)
                if total > 0:
                    total_mb = total / (1024 * 1024)
                    msg = (
                        f"Downloading  {done_mb:.1f} / {total_mb:.1f} MB"
                    )
                else:
                    msg = f"Downloading  {done_mb:.1f} MB"
                self.progress.emit(msg, pct)

            self.progress.emit("Connecting to GitHub", 2)
            updater.download_release(self._url, zip_path, on_progress)

            self.progress.emit("Preparing installer", 90)
            updater.apply_update_and_restart(zip_path)

            # The helper batch now owns the swap and waits for THIS process to
            # release its file locks. We must exit promptly - keeping the
            # parent alive while the helper copies is exactly what raced the
            # swap before. The update lock + the launcher's in-progress guard
            # block any relaunch during the brief window with no window.
            self.progress.emit(
                f"Restarting to v{self._version}  -  "
                f"WorkerBee will reopen itself",
                100,
            )
            time.sleep(1.0)
            self.finished.emit(True, "")

        except updater.UpdateError as exc:
            self.finished.emit(False, str(exc))
        except Exception as exc:
            tb = traceback.format_exc()
            self.finished.emit(
                False, f"{type(exc).__name__}: {exc}\n{tb}")


# Back-compat alias for older imports of UpdateWorker.
class UpdateWorker(UpdateApplyWorker):
    pass


class InitThread(QThread):
    """Runs whichever worker is passed (defaults to InitWorker)."""

    progress = Signal(str, int)
    finished_init = Signal(bool, str)

    def __init__(self, parent=None, worker: QObject | None = None):
        super().__init__(parent)
        self._worker = worker if worker is not None else InitWorker()
        self._worker.moveToThread(self)
        self.started.connect(self._worker.run)
        self._worker.progress.connect(self.progress.emit)
        self._worker.finished.connect(self._on_done)

    def worker(self) -> QObject:
        """Expose the underlying worker for worker-specific signals."""
        return self._worker

    def _on_done(self, ok: bool, err: str):
        self.finished_init.emit(ok, err)
        self.quit()
