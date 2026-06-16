# SPDX-License-Identifier: GPL-3.0-or-later
"""Detection: pure template matching."""
from .matcher import match_all, match_one
from .transforms import apply_color_mode, to_edges, to_grayscale
from .types import ColorMode, Match, MatchMethod

__all__ = [
    "Match",
    "MatchMethod",
    "ColorMode",
    "match_one",
    "match_all",
    "to_grayscale",
    "to_edges",
    "apply_color_mode",
]
