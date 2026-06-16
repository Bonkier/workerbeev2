# SPDX-License-Identifier: GPL-3.0-or-later
"""Pure color transforms used by the matcher."""
from __future__ import annotations

import cv2
import numpy as np

from .types import ColorMode


def to_grayscale(img: np.ndarray) -> np.ndarray:
    """Single-channel uint8. Pass-through if the image is already 2D."""
    if img.ndim == 2:
        return img
    return cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)


def to_edges(img: np.ndarray, th1: float = 300, th2: float = 300) -> np.ndarray:
    """Canny edges over the grayscale form of `img`.

    Threshold defaults match legacy LocateEdges so this is a drop-in.
    """
    gray = to_grayscale(img)
    return cv2.Canny(gray, th1, th2)


def apply_color_mode(img: np.ndarray, mode: ColorMode) -> np.ndarray:
    """Reduce `img` according to the requested matching mode."""
    if mode is ColorMode.RGB:
        return img
    if mode is ColorMode.GRAY:
        return to_grayscale(img)
    if mode is ColorMode.EDGES:
        return to_edges(img)
    raise ValueError(f"Unknown color mode: {mode!r}")
