# SPDX-License-Identifier: GPL-3.0-or-later
"""The wrong-resolution notice.

A run raises "Game window (W x H) is not 16:9" when the Limbus window has
the wrong shape. On its own that names the problem and stops; this works out
why from the window and the displays, and lists what to try, in order, before
the user takes it to Discord."""

import logging
import math
import platform
import re

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import QHBoxLayout, QLabel, QWidget

from .dialogs import FramelessDialog, show_advisory
from .theme import Sizing
from .widgets import GhostButton, PrimaryButton

PREFIX = "Game window ("
RECOMMENDED = ((1920, 1080), (1280, 720))

_SIZE = re.compile(r"Game window \((\d+) x (\d+)\)")
_SHAPES = (
    (16 / 9, "16:9"), (16 / 10, "16:10"), (4 / 3, "4:3"), (5 / 4, "5:4"),
    (3 / 2, "3:2"), (21 / 9, "21:9"), (2.37, "21:9"), (32 / 9, "32:9"),
)
# A window this close to 16:9 was 16:9 once and has been squeezed or dragged.
_NEAR = 0.04

_open = None        # the notice on screen, so a second size replaces it


def parse_size(message: str):
    """(width, height) from the run's warning text, or None."""
    m = _SIZE.search(str(message or ""))
    if not m:
        return None
    w, h = int(m.group(1)), int(m.group(2))
    return (w, h) if w > 0 and h > 0 else None


def is_16_9(w: int, h: int) -> bool:
    """The same test the capture backend applies."""
    return int(w / 16) == int(h / 9)


def shape_name(w: int, h: int) -> str:
    if is_16_9(w, h):
        return "16:9"
    value = w / h
    if abs(value - 16 / 9) / (16 / 9) < _NEAR:
        return "almost 16:9"
    best = min(_SHAPES[1:], key=lambda s: abs(s[0] - value))
    if abs(best[0] - value) / best[0] < 0.025:
        return best[1]
    g = math.gcd(w, h)
    if w // g <= 40:
        return "%d:%d" % (w // g, h // g)
    return "%.2f:1" % value


def used_area(w: int, h: int):
    """The centred 16:9 part of the window the bot falls back to."""
    if w / h > 16 / 9:
        return int(h * 16 / 9), h
    return w, int(w * 9 / 16)


def read_displays() -> list:
    """Every display in real pixels: {index, width, height, primary}."""
    out = []
    try:
        primary = QGuiApplication.primaryScreen()
        for i, screen in enumerate(QGuiApplication.screens(), 1):
            size = screen.geometry().size() * screen.devicePixelRatio()
            out.append({"index": i, "width": int(round(size.width())),
                        "height": int(round(size.height())),
                        "primary": screen is primary})
    except Exception as exc:
        logging.warning("Resolution help: could not read displays: %s", exc)
    return out


def collect(width: int, height: int, displays=None) -> dict:
    displays = (read_displays() if displays is None
                else [dict(d) for d in displays])
    # Qt only knows a display's scaled size, so at 150% or 175% scaling the
    # pixel size worked back from it can be a pixel or two out.
    filled = next((d for d in displays
                   if abs(d["width"] - width) <= 2
                   and abs(d["height"] - height) <= 2), None)
    if filled is not None:
        filled["width"], filled["height"] = width, height
    return {
        "width": width, "height": height,
        "shape": shape_name(width, height),
        "used": used_area(width, height),
        "displays": displays,
        "fills": filled,
        "version": _version(),
        "os": "%s %s" % (platform.system(), platform.version()),
    }


def _version() -> str:
    try:
        from .splash import _read_version
        return str(_read_version()).lstrip("v")
    except Exception:
        return "unknown"


def _display_text(d: dict) -> str:
    return "%d x %d (%s)" % (d["width"], d["height"],
                             shape_name(d["width"], d["height"]))


def _fits(size, display) -> bool:
    # A window also needs room for its title bar and the taskbar.
    return (display is None or
            (size[0] <= display["width"] and size[1] < display["height"]))


def _recommend(host) -> str:
    """The sizes worth trying on `host`, with the mode each needs there.
    Both are offered wherever the display can show both."""
    full_hd = RECOMMENDED[0]
    if _fits(full_hd, host):
        return "1920 x 1080 or 1280 x 720"
    if (host["width"] >= full_hd[0] and host["height"] >= full_hd[1]
            and is_16_9(host["width"], host["height"])):
        return "1920 x 1080 (in Fullscreen) or 1280 x 720 (Windowed)"
    return "1280 x 720"


def findings(report: dict) -> dict:
    """What is wrong, why, and the steps to try, most likely fix first."""
    w, h = report["width"], report["height"]
    fills = report.get("fills")
    displays = report.get("displays") or []
    host = fills or next((d for d in displays if d.get("primary")), None)
    target = _recommend(host)
    steps = []

    if fills is not None:
        detail = ("The game fills display %d, which is %s. Fullscreen on "
                  "that display can never be 16:9." % (
                      fills["index"], _display_text(fills)))
        steps.append("In Limbus Company, open Settings > Graphics and, "
                     "under Resolution, select Windowed.")
        steps.append("In the same Resolution setting, pick %s from the "
                     "list." % target)
        other = next((d for d in displays if d is not fills
                      and is_16_9(d["width"], d["height"])), None)
        if other is not None:
            steps.append("Or keep fullscreen and move the game to display "
                         "%d (%d x %d), which is 16:9." % (
                             other["index"], other["width"], other["height"]))
    elif report["shape"] == "almost 16:9":
        want_h = int(round(w * 9 / 16))
        detail = ("The window is %d px too %s: at this width 16:9 is "
                  "%d x %d. That is what a window looks like after it has "
                  "been dragged by an edge, maximised, or squeezed to fit "
                  "the screen." % (abs(h - want_h),
                                   "tall" if h > want_h else "short",
                                   w, want_h))
        steps.append("In Limbus Company, open Settings > Graphics and pick "
                     "the resolution again to snap the window back: %s."
                     % target)
        steps.append("Do not maximise the game window or drag its edges. "
                     "Change its size only from the game's own settings.")
        if host is not None and not _fits(RECOMMENDED[0], host):
            steps.append("A 1920 x 1080 window does not fit on a %d x %d "
                         "display once the title bar and taskbar are "
                         "counted. Use 1280 x 720 windowed%s."
                         % (host["width"], host["height"],
                            ", or Fullscreen" if is_16_9(
                                host["width"], host["height"]) else ""))
    else:
        detail = ("The game is running in a window that is %s, so its "
                  "resolution is set to something other than 16:9."
                  % report["shape"])
        steps.append("In Limbus Company, open Settings > Graphics and set "
                     "the resolution to %s." % target)
        steps.append("Do not maximise the game window or drag its edges. "
                     "Change its size only from the game's own settings.")

    steps.append("Stop the run and start it again. WorkerBee measures the "
                 "window when a run starts, and this notice returns if the "
                 "size is still wrong.")
    steps.append("If the size will not stick, close Limbus Company "
                 "completely, start it again and repeat step 1.")
    return {
        "level": "warn",
        "title": "The game window is %d x %d (%s). WorkerBee needs 16:9."
                 % (w, h, report["shape"]),
        "detail": detail,
        "steps": steps,
    }


def checks(report: dict) -> list:
    """(label, value, ok) rows: the facts the advice is based on."""
    used_w, used_h = report["used"]
    rows = [
        ("Game window", "%d x %d (%s)" % (report["width"], report["height"],
                                          report["shape"]), False),
        ("Needed", "16:9, for example 1920 x 1080 or 1280 x 720", None),
        ("Used meanwhile", "the centred %d x %d of the window. Runs can "
         "still work, but buttons near the edges may be missed."
         % (used_w, used_h), None),
    ]
    fills = report.get("fills")
    for d in report.get("displays") or []:
        text = _display_text(d)
        if d is fills:
            text += ", filled by the game"
        ok = None if d is not fills else False
        rows.append(("Display %d" % d["index"], text, ok))
    return rows


def format_report(report: dict) -> str:
    """Plain text for Discord: what was measured and what was advised."""
    lines = ["WorkerBee resolution report",
             "WorkerBee %s on %s" % (report.get("version", "unknown"),
                                     report.get("os", "unknown"))]
    for label, value, _ok in checks(report):
        lines.append("%s: %s" % (label, value))
    found = findings(report)
    lines.append("")
    lines.append(found["detail"])
    lines.append("Steps shown:")
    lines += ["%d. %s" % (i, s) for i, s in enumerate(found["steps"], 1)]
    return "\n".join(lines)


_SIZE_TEXT = re.compile(r"(\d+) x (\d+)")
_NBSP = chr(0xA0)


def _no_break(text: str) -> str:
    """Keep "1920 x 1080" on one line where the dialog wraps its text. For
    display only: the copied report keeps ordinary spaces."""
    return _SIZE_TEXT.sub(lambda m: "%s%sx%s%s" % (
        m.group(1), _NBSP, _NBSP, m.group(2)), str(text))


class ResolutionHelpDialog(FramelessDialog):
    """What the window is, why that is wrong, and the fixes to try."""

    def __init__(self, report: dict, parent: QWidget | None = None):
        super().__init__("Game window is not 16:9", parent)
        self._report = report
        self.setFixedWidth(600)

        from .lghub_help import FindingsView
        col = self.body
        view = FindingsView(self)
        found = findings(report)
        view.set_findings(
            [dict(found, title=_no_break(found["title"]),
                  detail=_no_break(found["detail"]),
                  steps=[_no_break(s) for s in found["steps"]])],
            [(label, _no_break(value), ok)
             for label, value, ok in checks(report)])
        col.addWidget(view)

        tail = QLabel(
            "Tried all of these and it still shows? Press Copy report and "
            "post it in the WorkerBee Discord with a screenshot of your "
            "Limbus graphics settings.", self, objectName="inlineHint")
        tail.setWordWrap(True)
        col.addWidget(tail)

        row = QHBoxLayout()
        row.setSpacing(Sizing.SPACE_SM)
        self._copy = GhostButton("Copy report", self)
        self._copy.clicked.connect(self._on_copy)
        row.addWidget(self._copy)
        row.addStretch(1)
        ok = PrimaryButton("OK", self)
        ok.clicked.connect(self.accept)
        row.addWidget(ok)
        col.addLayout(row)

    def showEvent(self, event):
        super().showEvent(event)
        # Wrapped text reports a height for a narrower column than it gets,
        # which leaves the panel taller than its content.
        height = self.layout().totalHeightForWidth(self.width())
        if height > 0:
            self.resize(self.width(), height)

    def _on_copy(self):
        QGuiApplication.clipboard().setText(format_report(self._report))
        self._copy.setText("Copied")
        QTimer.singleShot(1500, self,
                          lambda: self._copy.setText("Copy report"))


def show_resolution_help(parent, message: str, displays=None):
    """Raise the notice for a run's size warning. It never blocks and never
    takes focus: the bot may be driving the game, and a focus change pauses
    the run. Text that carries no size falls back to the plain advisory."""
    global _open
    size = parse_size(message)
    if size is None:
        return show_advisory(parent, message)
    report = collect(size[0], size[1], displays)
    for line in format_report(report).splitlines():
        if line:
            logging.info("Resolution: %s", line)
    if _open is not None:
        try:
            _open.close()
        except RuntimeError:
            pass                    # already deleted
    dlg = ResolutionHelpDialog(report, parent)
    dlg.setModal(False)
    dlg.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)
    dlg.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, True)
    dlg.setWindowFlag(Qt.WindowType.WindowDoesNotAcceptFocus, True)
    _open = dlg
    dlg.show()
    return dlg
