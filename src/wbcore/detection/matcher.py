# SPDX-License-Identifier: GPL-3.0-or-later
"""Pure template matching.

Frame and template are numpy arrays in OpenCV's native BGR order.
Returned coordinates are image-local; screen offsets, window scaling
and FHD references are handled elsewhere. Kept pure so it is testable
from saved fixtures and never racy.
"""
from __future__ import annotations

from typing import Iterable

import cv2
import numpy as np

from .transforms import apply_color_mode
from .types import ColorMode, Match, MatchMethod


def _resolve_method(method: MatchMethod) -> int:
    return getattr(cv2, method.value)


def _normalize_score(raw: float, method: MatchMethod) -> float:
    """Project the raw cv2 score into [0, 1] where higher is always better.

    CCORR is already [0, 1]; CCOEFF is [-1, 1] so we shift+scale;
    SQDIFF is distance so we invert. Clipped because cv2 occasionally
    returns values a hair outside [0, 1] on degenerate inputs.
    """
    if method is MatchMethod.CCORR_NORMED:
        score = raw
    elif method is MatchMethod.CCOEFF_NORMED:
        score = (raw + 1.0) * 0.5
    elif method is MatchMethod.SQDIFF_NORMED:
        score = 1.0 - raw
    else:
        raise ValueError(f"Unsupported method: {method!r}")
    return float(max(0.0, min(1.0, score)))


def _passing_locations(
    result: np.ndarray, conf: float, method: MatchMethod
) -> Iterable[tuple[int, int, float]]:
    """Yield (x, y, normalized_score) for every result-grid cell at or above conf."""
    if method is MatchMethod.SQDIFF_NORMED:
        # Lower-is-better: distance below 1 - conf.
        ys, xs = np.where(result <= 1.0 - conf)
    elif method is MatchMethod.CCOEFF_NORMED:
        # Convert conf into CCOEFF's [-1, 1] raw domain.
        ys, xs = np.where(result >= (2.0 * conf - 1.0))
    elif method is MatchMethod.CCORR_NORMED:
        ys, xs = np.where(result >= conf)
    else:
        raise ValueError(f"Unsupported method: {method!r}")
    for x, y in zip(xs.tolist(), ys.tolist()):
        yield int(x), int(y), _normalize_score(float(result[y, x]), method)


def _prepare(
    frame: np.ndarray, template: np.ndarray, color_mode: ColorMode
) -> tuple[np.ndarray, np.ndarray]:
    """Coerce both arrays to uint8 and apply the color mode."""
    f = np.ascontiguousarray(frame, dtype=np.uint8)
    t = np.ascontiguousarray(template, dtype=np.uint8)
    f = apply_color_mode(f, color_mode)
    t = apply_color_mode(t, color_mode)
    return f, t


def match_one(
    frame: np.ndarray,
    template: np.ndarray,
    conf: float = 0.9,
    method: MatchMethod = MatchMethod.CCOEFF_NORMED,
    color_mode: ColorMode = ColorMode.RGB,
    template_name: str = "",
) -> Match | None:
    """Return the single best match at or above `conf`, or None.

    Best is per-method: highest score for CCOEFF/CCORR, lowest raw
    distance for SQDIFF. Coordinates are image-local (top-left of the
    matched rectangle inside `frame`).
    """
    f, t = _prepare(frame, template, color_mode)
    cv_method = _resolve_method(method)
    result = cv2.matchTemplate(f, t, cv_method)
    min_val, max_val, min_loc, max_loc = cv2.minMaxLoc(result)

    if method is MatchMethod.SQDIFF_NORMED:
        raw, loc = min_val, min_loc
    else:
        raw, loc = max_val, max_loc

    score = _normalize_score(raw, method)
    if score < conf:
        return None

    h, w = t.shape[:2]
    return Match(
        x=int(loc[0]),
        y=int(loc[1]),
        w=int(w),
        h=int(h),
        confidence=score,
        template_name=template_name,
    )


def match_all(
    frame: np.ndarray,
    template: np.ndarray,
    conf: float = 0.9,
    method: MatchMethod = MatchMethod.CCOEFF_NORMED,
    color_mode: ColorMode = ColorMode.RGB,
    nms_threshold: int = 8,
    template_name: str = "",
) -> list[Match]:
    """Return every match at or above `conf`, with cheap NMS.

    `nms_threshold` is the pixel radius within which two passing cells
    count as the same hit; default 8 matches legacy Locate.locate_all
    so call sites swap over without re-tuning. Sorted by confidence
    descending so [:N] keeps the strongest hits.
    """
    f, t = _prepare(frame, template, color_mode)
    cv_method = _resolve_method(method)
    result = cv2.matchTemplate(f, t, cv_method)

    h, w = t.shape[:2]
    raw_hits = sorted(
        _passing_locations(result, conf, method),
        key=lambda hit: hit[2],
        reverse=True,
    )

    kept: list[Match] = []
    for x, y, score in raw_hits:
        if any(
            abs(x - m.x) <= nms_threshold and abs(y - m.y) <= nms_threshold
            for m in kept
        ):
            continue
        kept.append(
            Match(
                x=x,
                y=y,
                w=int(w),
                h=int(h),
                confidence=score,
                template_name=template_name,
            )
        )
    return kept
