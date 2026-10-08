# SPDX-License-Identifier: GPL-3.0-or-later
"""Dialogs drawn in the app's own chrome.

The main window is frameless, so a dialog wearing the operating system's
title bar reads as a different program popping up over it. FramelessDialog
gives error and notice popups the same edge, title face and close button as
the window they belong to."""

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import (
    QDialog, QFrame, QHBoxLayout, QLabel, QScrollArea, QVBoxLayout, QWidget,
)

from .theme import Colors, Sizing
from .widgets import GhostButton, PrimaryButton, _title_label


def _voxel() -> bool:
    try:
        from .skins import is_voxel
        return is_voxel()
    except Exception:
        return False


class FramelessDialog(QDialog):
    """A modal dialog with no OS title bar: a 1px-edged panel, a header that
    carries the title and a close button, and dragging by that header.
    Subclasses add their content to `self.body`."""

    def __init__(self, title: str, parent: QWidget | None = None):
        super().__init__(parent)
        self.setWindowTitle("WorkerBee")            # taskbar / alt-tab only
        self.setWindowFlags(Qt.WindowType.Dialog
                            | Qt.WindowType.FramelessWindowHint)
        # Translucent so the legacy skin's rounded corners are not squared
        # off by an opaque window rectangle behind the panel.
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setModal(True)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        self._frame = QFrame(self)
        self._frame.setObjectName("dialogFrame")
        self._frame.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        outer.addWidget(self._frame)

        from .style import voxel_panel_color
        voxel = _voxel()
        self._frame.setStyleSheet(
            "QFrame#dialogFrame { background-color: %s; border: 1px solid %s;"
            " border-radius: %dpx; }" % (
                voxel_panel_color() if voxel else Colors.BG_RAISED,
                Colors.ACCENT_MUTED, Sizing.RADIUS_LG))

        col = QVBoxLayout(self._frame)
        col.setContentsMargins(Sizing.SPACE_XL, Sizing.SPACE_MD,
                               Sizing.SPACE_XL, Sizing.SPACE_LG)
        col.setSpacing(Sizing.SPACE_MD)

        self._header = QWidget(self._frame)
        head = QHBoxLayout(self._header)
        head.setContentsMargins(0, Sizing.SPACE_SM, 0, 0)
        head.setSpacing(Sizing.SPACE_MD)
        if voxel:
            head.addWidget(_title_label(title, self._header, pixel=3,
                                        section=False),
                           0, Qt.AlignmentFlag.AlignVCenter)
        else:
            head.addWidget(QLabel(title, self._header,
                                  objectName="dialogTitle"))
        head.addStretch(1)
        from .main_window import _WinButton
        close = _WinButton("close", chr(0x2715), self._header)
        close.setObjectName("titleBarBtnClose")
        close.setCursor(Qt.CursorShape.PointingHandCursor)
        close.setToolTip("Close")
        close.clicked.connect(self.reject)
        head.addWidget(close, 0, Qt.AlignmentFlag.AlignTop)
        col.addWidget(self._header)

        self.body = col

    # The header is the drag handle, as a title bar would be.
    def mousePressEvent(self, event):
        if (event.button() == Qt.MouseButton.LeftButton
                and self._header.geometry().contains(
                    self._frame.mapFrom(self, event.position().toPoint()))):
            handle = self.windowHandle()
            if handle is not None and handle.startSystemMove():
                event.accept()
                return
        super().mousePressEvent(event)


class NoticeDialog(FramelessDialog):
    """A message with an OK button: the frameless stand-in for a message box.
    Long text (a traceback) scrolls instead of stretching the dialog."""

    def __init__(self, title: str, text: str, parent: QWidget | None = None):
        super().__init__(title, parent)
        self._text = str(text or "")
        self.setMinimumWidth(460)

        label = QLabel(self._text, self._frame)
        label.setWordWrap(True)
        label.setTextFormat(Qt.TextFormat.PlainText)
        label.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse)
        label.setStyleSheet(f"color: {Colors.TEXT_PRIMARY};"
                            " background: transparent;")
        label.setAlignment(Qt.AlignmentFlag.AlignLeft
                           | Qt.AlignmentFlag.AlignTop)

        scroll = QScrollArea(self._frame)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setStyleSheet("QScrollArea { background: transparent; }")
        host = QWidget(scroll)
        host.setStyleSheet("background: transparent;")
        host_col = QVBoxLayout(host)
        host_col.setContentsMargins(0, 0, Sizing.SPACE_SM, 0)
        host_col.addWidget(label)
        host_col.addStretch(1)
        scroll.setWidget(host)
        # Grow with the message up to a point, then scroll.
        lines = self._text.count("\n") + 1 + len(self._text) // 70
        scroll.setMinimumHeight(min(320, max(60, lines * 18)))
        self.body.addWidget(scroll, stretch=1)

        row = QHBoxLayout()
        row.setSpacing(Sizing.SPACE_SM)
        self._copy = GhostButton("Copy", self._frame)
        self._copy.clicked.connect(self._on_copy)
        row.addWidget(self._copy)
        row.addStretch(1)
        ok = PrimaryButton("OK", self._frame)
        ok.setDefault(True)
        ok.clicked.connect(self.accept)
        row.addWidget(ok)
        self.body.addLayout(row)

    def _on_copy(self):
        QGuiApplication.clipboard().setText(self._text)
        self._copy.setText("Copied")
        QTimer.singleShot(1500, self, lambda: self._copy.setText("Copy"))


class ChoiceDialog(FramelessDialog):
    """A question with two answers: the primary one accepts, the other
    rejects. Closing the dialog is neither."""

    def __init__(self, title: str, text: str, primary: str, secondary: str,
                 parent: QWidget | None = None):
        super().__init__(title, parent)
        self.choice = None
        self.setMinimumWidth(460)
        label = QLabel(str(text or ""), self._frame)
        label.setWordWrap(True)
        label.setTextFormat(Qt.TextFormat.PlainText)
        label.setStyleSheet(f"color: {Colors.TEXT_PRIMARY};"
                            " background: transparent;")
        self.body.addWidget(label)
        row = QHBoxLayout()
        row.setSpacing(Sizing.SPACE_SM)
        other = GhostButton(secondary, self._frame)
        other.clicked.connect(lambda: self._pick("secondary"))
        row.addWidget(other)
        row.addStretch(1)
        main = PrimaryButton(primary, self._frame)
        main.setDefault(True)
        main.clicked.connect(lambda: self._pick("primary"))
        row.addWidget(main)
        self.body.addLayout(row)

    def _pick(self, which):
        self.choice = which
        self.accept() if which == "primary" else self.reject()


def ask_choice(parent, text: str, title: str, primary: str, secondary: str):
    """Blocking question. Returns "primary", "secondary", or None when the
    dialog was closed instead."""
    dlg = ChoiceDialog(title, text, primary, secondary, parent)
    dlg.exec()
    return dlg.choice


def show_notice(parent, text: str, title: str = "Something went wrong"):
    """Blocking notice, for a failure the user has to see."""
    NoticeDialog(title, text, parent).exec()


def show_advisory(parent, text: str, title: str = "Heads up"):
    """Non-blocking notice that never takes focus: for advice raised while
    the bot may be driving the game, where a focus change pauses the run."""
    dlg = NoticeDialog(title, text, parent)
    dlg.setModal(False)
    dlg.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)
    dlg.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, True)
    dlg.setWindowFlag(Qt.WindowType.WindowDoesNotAcceptFocus, True)
    dlg.show()
    return dlg
