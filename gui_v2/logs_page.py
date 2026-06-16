# SPDX-License-Identifier: GPL-3.0-or-later
"""Logs page - tails the backend's game.log with a level filter.

Rich pipe-separated format (module, level, location, message) with a
time-ago annotation, smart-scroll tail, and auto-refresh while visible.
Lines are color-coded per level.
"""

import logging
import os
import re
from datetime import datetime

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QColor, QFont, QTextCharFormat, QTextCursor
from PySide6.QtWidgets import (
    QHBoxLayout, QLabel, QPlainTextEdit, QVBoxLayout, QWidget,
)

from .theme import Colors, Fonts, Sizing
from .widgets import GhostButton, PageHeader, Segmented


# Canonical level names; "ALL" shows everything.
_LEVELS = ("ALL", "DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL")


# Per-level hex color from the global palette.
_LEVEL_COLOR = {
    "DEBUG":    Colors.TEXT_TERTIARY,    # dim
    "INFO":     Colors.TEXT_SECONDARY,   # base body color
    "WARNING":  Colors.WARNING,
    "ERROR":    Colors.ERROR,
    "CRITICAL": Colors.ERROR,            # same red, bold below
}

# Highlight color for the timestamp + module + location columns.
_TIMESTAMP_COLOR = Colors.TEXT_TERTIARY
_MODULE_COLOR    = Colors.INFO          # subtle blue tint for the source
_LOC_COLOR       = Colors.TEXT_TERTIARY

# Logger names -> friendly module labels.
_MODULE_ALIASES = {
    "src.wbcore.bot":      "Bot",
    "src.wbcore.battle":   "Battle",
    "src.wbcore.shop":     "Shop",
    "src.wbcore.move":     "Move",
    "src.wbcore.grab":     "Grab",
    "src.wbcore.event":    "Event",
    "src.wbcore.lux":      "Lux",
    "src.wbcore.pack":     "Pack",
    "src.wbcore.teams":    "Teams",
    "src.wbcore.stats":    "Stats",
    "src.wbcore.cache":    "Cache",
    "src.wbcore.utils.utils":        "Utils",
    "src.wbcore.utils.telemetry":    "Telemetry",
    "src.wbcore.utils.profiles":     "Profile",
    "src.wbcore.utils.params":       "Params",
    "src.wbcore.utils.paths":        "Paths",
    "src.wbcore.utils.log_config":   "Log",
    "wbcore.bot":     "Bot",
    "wbcore.battle":  "Battle",
    "wbcore.shop":    "Shop",
    "wbcore.move":    "Move",
    "wbcore.grab":    "Grab",
    "wbcore.event":   "Event",
    "wbcore.lux":     "Lux",
    "wbcore.pack":    "Pack",
}

# Pipe format: ts | name | LEVEL | funcName:lineno | message
# Legacy:      ts - LEVEL - message   (kept for pre-update lines)
_PIPE_RE = re.compile(
    r"^(?P<ts>\d{2}/\d{2}/\d{4} \d{2}:\d{2}:\d{2})"
    r" \| (?P<name>[^|]*?) \| (?P<level>[A-Z]+) \| "
    r"(?P<loc>[^|]*?) \| (?P<msg>.*)$",
    re.DOTALL,
)
_LEGACY_RE = re.compile(
    r"^(?P<ts>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}(?:,\d+)?)"
    r" - (?P<level>[A-Z]+) - (?P<msg>.*)$",
    re.DOTALL,
)


def _candidate_log_paths() -> list[str]:
    base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return [
        os.path.join(base, "game.log"),
        os.path.join(base, "src", "game.log"),
        os.path.join(base, "logs", "game.log"),
    ]


def _module_label(name: str) -> str:
    """Short, human-friendly label for a logger name."""
    if not name:
        return ""
    if name in _MODULE_ALIASES:
        return _MODULE_ALIASES[name]
    # Fall back to the last dotted segment.
    tail = name.rsplit(".", 1)[-1]
    return tail or name


def _parse_pipe_ts(ts: str) -> datetime | None:
    try:
        return datetime.strptime(ts, "%d/%m/%Y %H:%M:%S")
    except ValueError:
        return None


def _parse_legacy_ts(ts: str) -> datetime | None:
    head = ts.split(",", 1)[0]
    try:
        return datetime.strptime(head, "%Y-%m-%d %H:%M:%S")
    except ValueError:
        return None


def _time_ago(when: datetime, now: datetime) -> str:
    diff = (now - when).total_seconds()
    if diff < 0:
        return "now"
    if diff < 60:
        return "just now"
    if diff < 3600:
        return f"{int(diff // 60)}m ago"
    if diff < 86400:
        return f"{int(diff // 3600)}h ago"
    return f"{int(diff // 86400)}d ago"


class _ParsedLine:
    """Parsed log line; plain attrs so the renderer can colour each
    field without re-parsing."""

    __slots__ = ("ts", "level", "module", "loc", "message", "raw")

    def __init__(self, ts, level, module, loc, message, raw):
        self.ts = ts
        self.level = level
        self.module = module
        self.loc = loc
        self.message = message
        self.raw = raw


def _parse(line: str) -> _ParsedLine | None:
    """Try pipe format, then legacy ' - ' format, then a raw line."""
    line = line.rstrip("\n")
    if not line:
        return None
    m = _PIPE_RE.match(line)
    if m:
        return _ParsedLine(
            ts=_parse_pipe_ts(m.group("ts")),
            level=m.group("level"),
            module=_module_label(m.group("name").strip()),
            loc=m.group("loc").strip(),
            message=m.group("msg"),
            raw=line,
        )
    m = _LEGACY_RE.match(line)
    if m:
        return _ParsedLine(
            ts=_parse_legacy_ts(m.group("ts")),
            level=m.group("level"),
            module="",
            loc="",
            message=m.group("msg"),
            raw=line,
        )
    # Unparseable - treat as a raw continuation line at INFO color.
    return _ParsedLine(ts=None, level="INFO", module="",
                       loc="", message=line, raw=line)


class LogsPage(QWidget):

    # The log view scrolls internally; don't let the shell wrap us.
    manages_scroll = True

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("root")
        # Default to DEBUG so verbose dev lines are visible out of the box.
        # Applied to the root logger at construction so DEBUG lines land in
        # game.log immediately, not just after the user touches the filter.
        self._level = "DEBUG"
        self._last_text = None
        self._build()
        self._apply_log_level()

        self._timer = QTimer(self)
        self._timer.setInterval(1500)
        self._timer.timeout.connect(self._reload)

    # --- layout ----------------------------------------------------------

    def _build(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(
            Sizing.SPACE_XXL, Sizing.SPACE_XL,
            Sizing.SPACE_XXL, Sizing.SPACE_XL,
        )
        outer.setSpacing(Sizing.SPACE_MD)

        header = PageHeader("Logs", self)
        reload_btn = GhostButton("Reload", self)
        reload_btn.clicked.connect(self._reload)
        header.add_action(reload_btn)
        clear_btn = GhostButton("Clear view", self)
        clear_btn.clicked.connect(self._clear_view)
        header.add_action(clear_btn)
        clear_file_btn = GhostButton("Clear file", self)
        clear_file_btn.setProperty("danger", "true")
        clear_file_btn.clicked.connect(self._clear_file)
        header.add_action(clear_file_btn)
        outer.addWidget(header)

        filt = QHBoxLayout()
        filt.setSpacing(Sizing.SPACE_SM)
        self._filter = Segmented(list(_LEVELS), default="DEBUG", parent=self)
        self._filter.selection_changed.connect(self._on_level)
        filt.addWidget(self._filter)
        from .copy import LOGS_VERBOSE_HINT
        self._dev_hint = QLabel(
            LOGS_VERBOSE_HINT, self, objectName="inlineHint")
        # Visible at launch since DEBUG is the default level.
        self._dev_hint.setVisible(True)
        filt.addWidget(self._dev_hint)
        filt.addStretch(1)
        self._path_lbl = QLabel("", self, objectName="inlineHint")
        filt.addWidget(self._path_lbl)
        outer.addLayout(filt)

        self._view = QPlainTextEdit(self)
        self._view.setObjectName("logView")
        self._view.setReadOnly(True)
        self._view.setFont(QFont(Fonts.FAMILY_MONO.split(",")[0].strip(),
                                 Fonts.SIZE_SM))
        self._view.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        outer.addWidget(self._view, stretch=1)

        self._reload()

    # --- event handlers --------------------------------------------------

    def _on_level(self, level: str):
        self._level = level
        # Show the verbose hint only when DEBUG is selected.
        self._dev_hint.setVisible(level == "DEBUG")
        self._apply_log_level()
        # Force a rebuild even if file content is unchanged: the filter
        # changed, so the displayed subset must too.
        self._last_text = None
        self._reload()

    def _apply_log_level(self):
        """DEBUG flips the root logger to DEBUG so verbose backend
        diagnostics get written; other views stay at INFO to keep
        game.log clean."""
        logging.getLogger().setLevel(
            logging.DEBUG if self._level == "DEBUG" else logging.INFO)

    def _clear_view(self):
        self._view.clear()
        self._last_text = None

    def _clear_file(self):
        path = self._current_path()
        if path is None:
            return
        try:
            with open(path, "w", encoding="utf-8"):
                pass
        except OSError as exc:
            self._view.setPlainText(f"Could not clear log: {exc}")
            return
        self._view.clear()
        self._last_text = None
        self._reload()

    def _current_path(self) -> str | None:
        for path in _candidate_log_paths():
            if os.path.isfile(path):
                return path
        return None

    # --- render ----------------------------------------------------------

    def _reload(self):
        path = self._current_path()
        if path is None:
            self._path_lbl.setText("no game.log yet")
            self._view.setPlainText(
                "No logs yet. Entries appear here once a run starts."
            )
            self._last_text = None
            return
        self._path_lbl.setText(path)
        try:
            with open(path, "r", encoding="utf-8", errors="replace") as f:
                lines = f.readlines()
        except OSError as exc:
            self._view.setPlainText(f"Could not read log: {exc}")
            self._last_text = None
            return

        # ALL shows everything except DEBUG (DEBUG is opt-in via its own
        # pick); picking DEBUG shows DEBUG and above.
        if self._level == "ALL":
            keep = {"INFO", "WARNING", "ERROR", "CRITICAL"}
        elif self._level == "DEBUG":
            keep = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
        else:
            keep = {self._level}

        parsed = []
        for ln in lines[-4000:]:    # tail-only; 4000 lines is plenty
            p = _parse(ln)
            if p is None:
                continue
            if p.level in keep:
                parsed.append(p)
        # Keep the visible tail tight enough for QPlainTextEdit.
        parsed = parsed[-2000:]

        # Hash for change detection (avoid repainting if nothing moved).
        key = (self._level, len(parsed),
               parsed[-1].raw if parsed else "")
        if key == self._last_text:
            return
        self._last_text = key

        sb = self._view.verticalScrollBar()
        at_bottom = sb.value() >= sb.maximum() - 4
        prev = sb.value()

        self._render(parsed)

        sb.setValue(sb.maximum() if at_bottom else min(prev, sb.maximum()))

    def _render(self, parsed: list[_ParsedLine]):
        """Paint the visible tail with per-field color formats."""
        self._view.clear()
        cursor = self._view.textCursor()
        now = datetime.now()

        ts_fmt    = self._fmt(_TIMESTAMP_COLOR)
        mod_fmt   = self._fmt(_MODULE_COLOR, bold=False)
        loc_fmt   = self._fmt(_LOC_COLOR)
        crit_fmt  = self._fmt(Colors.ERROR, bold=True)

        for p in parsed:
            if p.ts is not None:
                cursor.insertText(p.ts.strftime("%d/%m/%Y %H:%M:%S"), ts_fmt)
                cursor.insertText(
                    f"  ({_time_ago(p.ts, now)})", self._fmt(Colors.TEXT_DISABLED)
                )
                cursor.insertText("  ", ts_fmt)

            level_color = _LEVEL_COLOR.get(p.level, Colors.TEXT_SECONDARY)
            lvl_fmt = self._fmt(level_color, bold=True)
            cursor.insertText(f"{p.level:<8}", lvl_fmt)

            if p.module:
                cursor.insertText("  ", ts_fmt)
                cursor.insertText(p.module, mod_fmt)
            if p.loc:
                cursor.insertText("  ", ts_fmt)
                cursor.insertText(p.loc, loc_fmt)

            cursor.insertText("  ", ts_fmt)
            msg_fmt = crit_fmt if p.level == "CRITICAL" else self._fmt(level_color)
            cursor.insertText(p.message, msg_fmt)
            cursor.insertText("\n", ts_fmt)

    @staticmethod
    def _fmt(color_hex: str, bold: bool = False) -> QTextCharFormat:
        fmt = QTextCharFormat()
        fmt.setForeground(QColor(color_hex))
        if bold:
            font = QFont()
            font.setBold(True)
            fmt.setFontWeight(QFont.Weight.Bold)
        return fmt

    # --- visibility-aware refresh ---------------------------------------

    def showEvent(self, event):
        super().showEvent(event)
        self._apply_log_level()   # re-arm DEBUG verbosity if it's selected
        self._reload()
        self._timer.start()

    def hideEvent(self, event):
        super().hideEvent(event)
        self._timer.stop()
        # Drop back to INFO when the page isn't visible so DEBUG never
        # floods game.log in the background.
        logging.getLogger().setLevel(logging.INFO)
