# SPDX-License-Identifier: GPL-3.0-or-later
"""Pytest configuration: put the repo root + src/ on sys.path.

The project does not ship an installable package, so without this the
`from src.wbcore.detection import ...` imports in test files would
fail when pytest is invoked from the repo root.

`src/` itself is also added so that the legacy `from bridge.bridge
import Bridge` line inside `os_windows_backend` resolves cleanly when
a test imports anything from `automation.utils.utils`.
"""
from __future__ import annotations

import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
_SRC = _REPO_ROOT / "src"

for entry in (_REPO_ROOT, _SRC):
    s = str(entry)
    if s not in sys.path:
        sys.path.insert(0, s)

import pytest


@pytest.fixture(autouse=True)
def _season_off():
    """Tests must not change with the calendar: the seasonal dress is date
    driven, so it is pinned off here and switched on only by the tests that
    are about it."""
    from gui_v2 import seasonal
    seasonal.force("off")
    yield
    seasonal.force("off")


def destroy(*objects):
    """Delete Qt objects now, in the order given, rather than leaving them
    for the garbage collector. A widget tree that is only reachable through
    a reference cycle (a test lambda closing over its owner is enough) gets
    torn down by the cyclic collector in no particular order, and PySide can
    crash the interpreter doing it, at the very end of the run."""
    from PySide6.QtCore import QCoreApplication, QEvent
    for obj in objects:
        if obj is None:
            continue
        try:
            if hasattr(obj, "close"):
                obj.close()
            obj.deleteLater()
        except RuntimeError:
            pass                    # already deleted with its parent
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)

