# SPDX-License-Identifier: GPL-3.0-or-later
"""PyInstaller runtime hook: prepend bundle root + src/ to sys.path so the
import shape matches the source tree."""
from __future__ import annotations

import os
import sys


def _patch_paths() -> None:
    base = getattr(sys, "_MEIPASS", None)
    if not base:
        return
    candidates = [
        base,
        os.path.join(base, "src"),
    ]
    for path in candidates:
        if path and os.path.isdir(path) and path not in sys.path:
            sys.path.insert(0, path)


_patch_paths()
