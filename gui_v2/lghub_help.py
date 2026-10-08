# SPDX-License-Identifier: GPL-3.0-or-later
"""G Hub troubleshooting UI: the findings list shown in Settings, and the
dialog raised when a run cannot reach G Hub. Both render what
bridge.lghub_check.findings() concluded, as steps the user can follow."""

import logging
import os
import sys
import threading

from PySide6.QtCore import QObject, QThread, Qt, QTimer, Signal, Slot
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import (
    QFrame, QGridLayout, QHBoxLayout, QLabel, QScrollArea,
    QVBoxLayout, QWidget,
)

from .dialogs import FramelessDialog
from .theme import Colors, Sizing
from .widgets import GhostButton, PrimaryButton

_LEVEL_COLOR = {"fail": "ERROR", "warn": "WARNING", "ok": "SUCCESS"}

RUN_INTRO = (
    "WorkerBee sends its clicks and key presses through G HUB, and the "
    "connection failed, so the run could not start.")
STARTUP_INTRO = "G HUB open but not detected. Follow debug steps below."

# One notification per session is enough: the launch check and a failed run
# would otherwise both raise it for the same cause.
_shown = False


def notification_shown() -> bool:
    return _shown


def _lghub_check():
    base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    for p in (base, os.path.join(base, "src")):
        if p not in sys.path:
            sys.path.insert(0, p)
    from bridge import lghub_check
    return lghub_check


def level_color(level: str) -> str:
    return getattr(Colors, _LEVEL_COLOR.get(level, "WARNING"))


def headline(found: list) -> dict | None:
    """The finding that names the state: the first failure, else the first
    warning, else whatever is left."""
    for level in ("fail", "warn"):
        for f in found:
            if f["level"] == level:
                return f
    return found[0] if found else None


def is_bridge_failure(msg: str) -> bool:
    text = str(msg or "")
    return "Bridge initialization failed" in text or "BridgeError" in text


def bridge_error_line(msg: str) -> str:
    """The one line of a run warning that carries the bridge's own error and
    diagnose() string; the rest is traceback."""
    lines = [ln.strip() for ln in str(msg or "").splitlines() if ln.strip()]
    for ln in lines:
        if "Bridge initialization failed" in ln:
            return ln
    return lines[0] if lines else ""


def copy_report(report: dict) -> str:
    text = _lghub_check().format_report(report)
    QGuiApplication.clipboard().setText(text)
    return text


def diagnose() -> dict:
    """Open the bridge and report everything lghub_check can read. Blocks for
    as long as open() does, so never call it on the GUI thread."""
    check = _lghub_check()
    error, diag, b = "", "", None
    try:
        from bridge.bridge import Bridge
        b = Bridge(auto_open=False)
        b.open()
    except Exception as exc:
        error = f"{type(exc).__name__}: {exc}"
    try:
        diag = b.diagnose() if b is not None else ""
    except Exception:
        diag = ""
    try:
        return check.collect(error, diag)
    except Exception as exc:
        logging.warning("LGHub diagnosis failed: %s", exc)
        return {}


class DiagnoseWorker(QObject):
    """diagnose() on a QThread, for the Check connection buttons."""

    done = Signal(dict)

    @Slot()
    def run(self):
        self.done.emit(diagnose())


class StartupCheck(QObject):
    """One look shortly after launch. G Hub open but refusing the bridge is
    the one state the user cannot see for themselves until a run fails on
    it, so it is raised straight away. G Hub simply not running is left
    alone: it may be started later, and open() can block without it."""

    problem = Signal(dict)

    def start(self):
        # A daemon thread, not a QThread: if open() hangs it must not hold
        # the app open at exit.
        threading.Thread(target=self._run, name="lghub-startup-check",
                         daemon=True).start()

    def _run(self):
        try:
            check = _lghub_check()
            if not check.lghub_running():
                return
            report = diagnose()
            if not report:
                return
            if report["bridge"].get("is_open") == "true":
                # One line in every log: what was connected to, and proof
                # that the versions can be read on this machine.
                logging.info(
                    "LGHub: connected. G HUB %s, driver %s.",
                    report.get("version") or "version unreadable",
                    ", ".join(check.driver_versions(report))
                    or "version unreadable")
                return
            for line in check.format_report(report).splitlines():
                logging.warning("LGHub: %s", line)
            self.problem.emit(report)
        except Exception as exc:
            logging.warning("LGHub startup check failed: %s", exc)


class FindingsView(QWidget):
    """Each finding as a coloured title, a line of why, and numbered steps."""

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self._col = QVBoxLayout(self)
        self._col.setContentsMargins(0, 0, 0, 0)
        self._col.setSpacing(Sizing.SPACE_LG)
        self.setVisible(False)

    def set_findings(self, found: list, rows: list | None = None):
        while self._col.count():
            item = self._col.takeAt(0)
            w = item.widget()
            if w is not None:
                w.deleteLater()
        for f in found:
            self._col.addWidget(self._block(f))
        if found and rows:
            self._col.addWidget(self._checks(rows))
        self.setVisible(bool(found))

    def _checks(self, rows: list) -> QWidget:
        """The facts behind the findings: each thing looked at and what it
        read, green when fine, red when it is part of the problem."""
        box = QWidget(self)
        col = QVBoxLayout(box)
        col.setContentsMargins(0, 0, 0, 0)
        col.setSpacing(Sizing.SPACE_XS)
        col.addWidget(QLabel("WHAT WORKERBEE CHECKED", box,
                             objectName="sectionLabel"))
        grid = QGridLayout()
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setHorizontalSpacing(Sizing.SPACE_LG)
        grid.setVerticalSpacing(Sizing.SPACE_XXS)
        grid.setColumnStretch(1, 1)
        tone = {True: Colors.SUCCESS, False: Colors.ERROR,
                None: Colors.TEXT_SECONDARY}
        for i, (label, value, ok) in enumerate(rows):
            name = QLabel(label, box, objectName="inlineHint")
            grid.addWidget(name, i, 0)
            val = QLabel(str(value), box)
            val.setWordWrap(True)
            val.setTextInteractionFlags(
                Qt.TextInteractionFlag.TextSelectableByMouse)
            val.setStyleSheet(f"color: {tone[ok]};")
            grid.addWidget(val, i, 1)
        col.addLayout(grid)
        return box

    def _block(self, f: dict) -> QWidget:
        box = QWidget(self)
        col = QVBoxLayout(box)
        col.setContentsMargins(0, 0, 0, 0)
        col.setSpacing(Sizing.SPACE_XS)

        title = QLabel(f["title"], box, objectName="settingTitle")
        title.setWordWrap(True)
        title.setStyleSheet(f"color: {level_color(f['level'])};")
        col.addWidget(title)

        if f.get("detail"):
            detail = QLabel(f["detail"], box, objectName="inlineHint")
            detail.setWordWrap(True)
            col.addWidget(detail)

        for i, step in enumerate(f.get("steps") or [], 1):
            row = QHBoxLayout()
            row.setContentsMargins(0, 0, 0, 0)
            row.setSpacing(Sizing.SPACE_SM)
            num = QLabel(f"{i}.", box)
            num.setFixedWidth(20)
            num.setAlignment(Qt.AlignmentFlag.AlignRight
                             | Qt.AlignmentFlag.AlignTop)
            num.setStyleSheet(f"color: {Colors.ACCENT};")
            row.addWidget(num)
            text = QLabel(step, box)
            text.setWordWrap(True)
            text.setTextInteractionFlags(
                Qt.TextInteractionFlag.TextSelectableByMouse)
            text.setStyleSheet(f"color: {Colors.TEXT_PRIMARY};")
            row.addWidget(text, stretch=1)
            col.addLayout(row)
        return box


class LghubHelpDialog(FramelessDialog):
    """Raised when a run cannot reach G Hub: what is wrong, the steps that
    fix it, and a report to paste into Discord if they do not."""

    def __init__(self, report: dict, parent: QWidget | None = None,
                 intro: str = RUN_INTRO):
        super().__init__("Cannot reach Logitech G HUB", parent)
        self.resize(660, 660)
        self._report = report
        self._thread = None
        self._worker = None

        col = self.body
        lead = QLabel(intro, self, objectName="inlineHint")
        lead.setWordWrap(True)
        col.addWidget(lead)

        scroll = QScrollArea(self)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setStyleSheet("QScrollArea { background: transparent; }")
        host = QWidget(scroll)
        host.setStyleSheet("background: transparent;")
        host_col = QVBoxLayout(host)
        host_col.setContentsMargins(0, 0, Sizing.SPACE_SM, 0)
        self._view = FindingsView(host)
        host_col.addWidget(self._view)
        host_col.addStretch(1)
        scroll.setWidget(host)
        col.addWidget(scroll, stretch=1)

        tail = QLabel(
            "Still stuck? Press Copy report and paste it in the WorkerBee "
            "Discord.", self, objectName="inlineHint")
        tail.setWordWrap(True)
        col.addWidget(tail)

        row = QHBoxLayout()
        row.setSpacing(Sizing.SPACE_SM)
        self._copy = GhostButton("Copy report", self)
        self._copy.clicked.connect(self._on_copy)
        row.addWidget(self._copy)
        self._again = GhostButton("Check again", self)
        self._again.clicked.connect(self._check_again)
        row.addWidget(self._again)
        row.addStretch(1)
        close = PrimaryButton("Close", self)
        close.clicked.connect(self.accept)
        row.addWidget(close)
        col.addLayout(row)

        self._render()

    def _render(self):
        check = _lghub_check()
        found = check.findings(self._report) if self._report else []
        found = [f for f in found if f["level"] != "ok"] or found
        if not found:
            found = [{
                "level": "fail", "title": "Could not connect to G HUB",
                "detail": "",
                "steps": ["Quit G HUB from the system tray and start it "
                          "again.", "Restart the PC."],
            }]
        rows = check.checks(self._report) if self._report else []
        self._view.set_findings(found, rows)

    def _on_copy(self):
        if not self._report:
            return
        copy_report(self._report)
        self._copy.setText("Copied")
        QTimer.singleShot(1500, self,
                          lambda: self._copy.setText("Copy report"))

    def _check_again(self):
        if self._thread is not None:
            return
        self._again.setEnabled(False)
        self._again.setText("Checking...")
        self._thread = QThread(self)
        self._worker = DiagnoseWorker()
        self._worker.moveToThread(self._thread)
        self._worker.done.connect(self._on_checked)
        self._thread.started.connect(self._worker.run)
        self._thread.start()

    def _on_checked(self, report: dict):
        self._stop_thread()
        if report:
            self._report = report
            self._render()
        self._again.setEnabled(True)
        self._again.setText("Check again")

    def _stop_thread(self):
        if self._thread is not None:
            self._thread.quit()
            self._thread.wait()
            self._thread.deleteLater()
        self._thread = None
        self._worker = None

    def done(self, result):
        self._stop_thread()
        super().done(result)


def show_lghub_help(parent, bridge_error: str = "", report: dict | None = None,
                    intro: str = RUN_INTRO):
    """Raise the notification. Pass the report when one is in hand; otherwise
    it is built from the error a failed run reported, without reopening the
    bridge (the error already carries its state)."""
    global _shown
    if report is None:
        try:
            report = _lghub_check().collect(bridge_error_line(bridge_error))
        except Exception as exc:
            logging.warning("LGHub diagnosis failed: %s", exc)
            report = {}
    _shown = True
    dlg = LghubHelpDialog(report, parent, intro)
    dlg.exec()
