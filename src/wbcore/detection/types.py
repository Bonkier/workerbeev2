# SPDX-License-Identifier: GPL-3.0-or-later
"""Detection-layer value types.

No cv2/np at import time - cv2 constants are looked up lazily so this
imports fine where opencv is unavailable (e.g. doc tooling).
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class MatchMethod(str, Enum):
    """Template-matching method selector.

    Value is the cv2.TM_* constant name, resolved at use time so import
    does not require opencv. String-valued so Match objects pickle/json
    round-trip cleanly for telemetry and fixtures.
    """

    CCOEFF_NORMED = "TM_CCOEFF_NORMED"
    CCORR_NORMED = "TM_CCORR_NORMED"
    SQDIFF_NORMED = "TM_SQDIFF_NORMED"


class ColorMode(str, Enum):
    """How frame and template are reduced before matching.

    - RGB: use as-is (BGR, OpenCV native).
    - GRAY: collapse to single channel.
    - EDGES: Canny over grayscale. Robust to color/lighting drift but
      expensive (two Canny passes per locate).
    """

    RGB = "rgb"
    GRAY = "gray"
    EDGES = "edges"


@dataclass(frozen=True)
class Match:
    """A located rectangle in image-local coordinates.

    `confidence` is normalized to [0, 1] (higher is better) regardless
    of MatchMethod, so callers need not remember that SQDIFF inverts or
    CCOEFF lives in [-1, 1]. `template_name` is best-effort metadata for
    telemetry/tests.
    """

    x: int
    y: int
    w: int
    h: int
    confidence: float
    template_name: str = ""

    @property
    def center(self) -> tuple[int, int]:
        return (self.x + self.w // 2, self.y + self.h // 2)

    @property
    def box(self) -> tuple[int, int, int, int]:
        return (self.x, self.y, self.w, self.h)
