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
