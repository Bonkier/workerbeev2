# SPDX-License-Identifier: GPL-3.0-or-later
"""Vision: screen capture + template loading + Finder composition.

The only pipeline layer that touches IO; the IO is injected so the
module stays importable under pytest.
"""
from .capture import CaptureFn, capture
from .finder import Finder, TelemetryCallback, TemplateRef
from .loader import PathLike, TemplateLoader

__all__ = [
    "CaptureFn",
    "capture",
    "TemplateLoader",
    "PathLike",
    "Finder",
    "TelemetryCallback",
    "TemplateRef",
]
