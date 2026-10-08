# SPDX-License-Identifier: GPL-3.0-or-later
"""Error and notice dialogs wear the app's own chrome, not the OS title bar."""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QDialog, QPushButton

from bridge import lghub_check as L
from gui_v2 import dialogs as D
from gui_v2 import lghub_help as H

_app = QApplication.instance() or QApplication([])

_REFUSED = ("BridgeError: open failed (code 1): Unsupported driver version. "
            "[is_open=false;version_check=fail]")


def _frameless(dlg) -> bool:
    return bool(dlg.windowFlags() & Qt.WindowType.FramelessWindowHint)


def test_the_g_hub_notification_has_no_os_title_bar():
    dlg = H.LghubHelpDialog(L.collect(_REFUSED), None, H.STARTUP_INTRO)
    assert _frameless(dlg) and dlg.isModal()
    assert dlg.testAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
    dlg.close()


def test_the_close_button_in_the_header_dismisses_the_dialog():
    dlg = D.NoticeDialog("Something went wrong", "boom")
    close = [b for b in dlg.findChildren(QPushButton)
             if b.objectName() == "titleBarBtnClose"]
    assert len(close) == 1
    seen = []
    dlg.finished.connect(seen.append)
    close[0].click()
    assert seen == [QDialog.DialogCode.Rejected]


def test_a_notice_is_frameless_and_its_text_can_be_copied():
    dlg = D.NoticeDialog("Something went wrong", "line one\nline two")
    assert _frameless(dlg)
    dlg._on_copy()
    assert QApplication.clipboard().text() == "line one\nline two"
    assert dlg._copy.text() == "Copied"
    dlg.close()


def test_the_dialogs_module_stays_ascii():
    import io
    src = io.open(D.__file__, encoding="utf-8").read()
    assert all(ord(ch) < 128 for ch in src)
