# SPDX-License-Identifier: GPL-3.0-or-later
"""Help page - renders Help.txt as titled sections, plus an About
block and a Join Discord button."""

import logging
import os
import re
import webbrowser
from html import escape

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFrame, QHBoxLayout, QLabel, QMessageBox, QProgressDialog, QVBoxLayout,
    QWidget,
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
    """Help.txt as (title, blocks) sections. A line ending with ":" at the
    top of a blank-line-separated block opens a section, and every block up
    to the next such line belongs to it. Within a block, lines starting
    with "- " are the items of a list (an indented line continues the item
    above) and the other lines run together into a paragraph."""
    sections = []
    for block in text.split("\n\n"):
        lines = [ln.rstrip() for ln in block.splitlines() if ln.strip()]
        if not lines:
            continue
        if lines[0].endswith(":") and not lines[0].startswith("- "):
            sections.append((lines[0].rstrip(":"), []))
            lines = lines[1:]
        if not sections:
            sections.append(("", []))
        blocks = sections[-1][1]
        kind, items = None, []

        def flush():
            if kind == "list" and items:
                blocks.append(("list", list(items)))
            elif kind == "text" and items:
                blocks.append(("text", " ".join(items)))

        for ln in lines:
            if ln.startswith("- "):
                if kind != "list":
                    flush()
                    kind, items = "list", []
                items.append(ln[2:].strip())
            elif ln.startswith(" ") and kind == "list":
                items[-1] += " " + ln.strip()
            else:
                if kind != "text":
                    flush()
                    kind, items = "text", []
                items.append(ln.strip())
        flush()
    return sections


_LEAD = re.compile(r"^([^:]{2,40}):\s+(.+)$", re.S)


def _rich(text: str, lead: bool = False) -> str:
    """Body text as Qt rich text; a list item's short lead term before a
    colon is set bold."""
    m = _LEAD.match(text) if lead else None
    if m:
        return "<b>%s</b>: %s" % (escape(m.group(1)), escape(m.group(2)))
    return escape(text)


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

        for title, blocks in _parse_sections(text):
            section = Card(title.upper() if title else "GUIDE", self)
            section.body.setSpacing(Sizing.SPACE_SM)
            for kind, payload in blocks:
                if kind == "list":
                    section.body.addLayout(self._bullets(payload, section))
                else:
                    section.body.addWidget(self._body(_rich(payload), section))
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

    @staticmethod
    def _body(rich: str, host: QWidget) -> QLabel:
        lbl = QLabel(rich, host, objectName="helpBody")
        lbl.setTextFormat(Qt.TextFormat.RichText)
        lbl.setWordWrap(True)
        return lbl

    def _bullets(self, items, host: QWidget) -> QVBoxLayout:
        """A list: an accent square ahead of each item, its lead term bold."""
        col = QVBoxLayout()
        col.setContentsMargins(0, 0, 0, 0)
        col.setSpacing(Sizing.SPACE_XS)
        for item in items:
            row = QHBoxLayout()
            row.setContentsMargins(0, 0, 0, 0)
            row.setSpacing(Sizing.SPACE_SM)
            mark_col = QVBoxLayout()
            mark_col.setContentsMargins(0, 7, 0, 0)
            mark = QFrame(host, objectName="helpBullet")
            mark.setFixedSize(6, 6)
            mark_col.addWidget(mark)
            mark_col.addStretch(1)
            row.addLayout(mark_col)
            row.addWidget(self._body(_rich(item, lead=True), host), 1)
            col.addLayout(row)
        return col

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
                return
            # Success: the helper batch is waiting for THIS process to exit so
            # it can take the file locks and swap the install dir. We MUST quit
            # (the splash auto-update path does the same). Without this the exe
            # stays locked, robocopy can't replace it, and nothing restarts.
            progress.setLabelText("Restarting to apply update...")
            from PySide6.QtCore import QTimer
            from PySide6.QtWidgets import QApplication
            QTimer.singleShot(300, lambda: (
                QApplication.instance() and QApplication.instance().quit()))

        thread.progress.connect(_on_progress)
        thread.finished_init.connect(_on_done)
        # Cancel can't abort the urllib read mid-stream without more
        # plumbing, so it just hides progress and lets the worker finish
        # or fail naturally. The restart-and-replace step is fast anyway.
        progress.canceled.connect(progress.hide)
        thread.start()
