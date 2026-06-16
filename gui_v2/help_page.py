# SPDX-License-Identifier: GPL-3.0-or-later
"""Help page - renders Help.txt as titled sections, plus an About
block and a Join Discord button."""

import logging
import os
import webbrowser

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QHBoxLayout, QLabel, QMessageBox, QProgressDialog, QVBoxLayout, QWidget,
)

from .splash import _read_version
from .theme import Sizing
from .widgets import Card, GhostButton, PageHeader

_log = logging.getLogger(__name__)


_DISCORD_INVITE = "https://discord.gg/8z9npH2Q2B"


def _help_path() -> str:
    base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, "Help.txt")


def _parse_sections(text: str):
    """Split on blank lines into (title, body) blocks; a block's first
    line is the title if it ends with ':'."""
    sections = []
    for block in text.split("\n\n"):
        lines = [ln for ln in block.splitlines() if ln.strip()]
        if not lines:
            continue
        if lines[0].rstrip().endswith(":"):
            title = lines[0].rstrip().rstrip(":")
            body = "\n".join(lines[1:])
        else:
            title = ""
            body = "\n".join(lines)
        sections.append((title, body))
    return sections


class HelpPage(QWidget):

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("root")
        self._build()

    def _build(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(
            Sizing.SPACE_XXL, Sizing.SPACE_XL,
            Sizing.SPACE_XXL, Sizing.SPACE_XL,
        )
        outer.setSpacing(Sizing.SPACE_LG)

        outer.addWidget(PageHeader("Help", self))

        try:
            with open(_help_path(), "r", encoding="utf-8") as f:
                text = f.read()
        except OSError:
            text = ""

        for title, body in _parse_sections(text):
            section = Card(title.upper() if title else "GUIDE", self)
            lbl = QLabel(body, section, objectName="helpBody")
            lbl.setWordWrap(True)
            section.body.addWidget(lbl)
            outer.addWidget(section)

        from .copy import HELP_ABOUT_BODY
        about = Card("ABOUT", self)
        about_lbl = QLabel(
            HELP_ABOUT_BODY.format(version=_read_version().lstrip('v')),
            self, objectName="helpBody",
        )
        about_lbl.setWordWrap(True)
        about.body.addWidget(about_lbl)
        about.body.addSpacing(Sizing.SPACE_SM)
        btn_row = QHBoxLayout()
        btn_row.setSpacing(Sizing.SPACE_SM)

        update_btn = GhostButton("Update now", self)
        update_btn.clicked.connect(self._on_update_now)
        btn_row.addWidget(update_btn)

        discord = GhostButton("Join Discord", self)
        discord.clicked.connect(lambda: webbrowser.open(_DISCORD_INVITE))
        btn_row.addWidget(discord)
        btn_row.addStretch(1)
        about.body.addLayout(btn_row)
        outer.addWidget(about)

        outer.addStretch(1)

    # --- One-click update flow -------------------------------------
    def _on_update_now(self):
        """Check GitHub, prompt with version + size, then download +
        install + restart. Configs survive the swap (they live in
        %LOCALAPPDATA% outside the install dir)."""
        from . import updater
        from .init_worker import InitThread, UpdateApplyWorker

        if not updater.is_frozen():
            QMessageBox.information(
                self, "Update",
                "This is a source-tree run. Rebuild the exe via "
                "PyInstaller to get in-app updates."
            )
            return

        current = _read_version().lstrip("v")
        # Synchronous: the check is one tiny GitHub API call, so a brief
        # blocking tick is fine and lets us use a simple QMessageBox.
        try:
            info = updater.check_latest_release()
        except updater.UpdateError as exc:
            QMessageBox.warning(self, "Update", str(exc))
            return
        except Exception as exc:                # network nonsense
            _log.warning("update check exception: %s", exc)
            QMessageBox.warning(self, "Update",
                                f"Couldn't check for updates: {exc}")
            return

        remote = str(info.get("version", "")).lstrip("v")
        url = str(info.get("download_url", ""))
        size = int(info.get("size") or 0)

        if not remote or not url:
            QMessageBox.warning(self, "Update",
                                "GitHub didn't return a download link.")
            return

        if not updater.is_newer(remote, current):
            QMessageBox.information(
                self, "Update",
                f"You're already on the latest version (v{current})."
            )
            return

        size_mb = max(1, size // (1024 * 1024)) if size else 0
        size_blurb = f"  ·  {size_mb} MB" if size else ""
        choice = QMessageBox.question(
            self, "Update available",
            f"v{current}  →  v{remote}{size_blurb}\n\n"
            "The app will download the new version, replace itself, "
            "and restart. Your settings are preserved.\n\n"
            "Update now?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.Yes,
        )
        if choice != QMessageBox.StandardButton.Yes:
            return

        # Progress dialog drives the download bar; UpdateApplyWorker
        # spawns the install helper and quits Qt once it's up.
        progress = QProgressDialog(
            "Connecting to GitHub...", "Cancel", 0, 100, self)
        progress.setWindowTitle("Updating")
        progress.setMinimumDuration(0)
        progress.setAutoClose(False)
        progress.setAutoReset(False)
        progress.setValue(0)

        worker = UpdateApplyWorker(download_url=url, version=remote)
        thread = InitThread(self, worker=worker)

        def _on_progress(msg: str, pct: int):
            progress.setLabelText(msg)
            progress.setValue(max(0, min(100, int(pct))))

        def _on_done(ok: bool, err: str):
            if not ok:
                progress.cancel()
                QMessageBox.warning(self, "Update failed", err)

        thread.progress.connect(_on_progress)
        thread.finished_init.connect(_on_done)
        # Cancel can't abort the urllib read mid-stream without more
        # plumbing, so it just hides progress and lets the worker finish
        # or fail naturally. The restart-and-replace step is fast anyway.
        progress.canceled.connect(progress.hide)
        thread.start()
