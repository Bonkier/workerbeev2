# SPDX-License-Identifier: GPL-3.0-or-later
"""Screen capture, with the backend injected.

`capture` takes a `CaptureFn` mapping `ScreenRect -> ndarray`, so the
real `os_windows_backend.screenshot` is just one implementation and
tests can pass a fake. Nothing here imports a live-window module, so
the tree stays importable under pytest.
"""
from __future__ import annotations

from typing import Callable

import numpy as np

from ..regionspec import Region, ScreenRect, WindowGeometry, region_to_screen


# Maps a screen-pixel rectangle to a uint8 BGR ndarray.
CaptureFn = Callable[[ScreenRect], np.ndarray]


def capture(
    region: Region | None,
    window: WindowGeometry,
    backend: CaptureFn,
) -> np.ndarray:
    """Capture `region` (FHD reference) from the window using `backend`.

    Translates to screen pixels via `region_to_screen`; `region=None`
    means the full FHD frame. Returns the backend's ndarray as-is -
    cropping/scaling/color-convert are detection-level transforms.
    """
    if region is None:
        region = Region.full()
    screen_rect = region_to_screen(region, window)
    frame = backend(screen_rect)
    if not isinstance(frame, np.ndarray):
        raise TypeError(
            f"CaptureFn returned {type(frame).__name__}, expected np.ndarray"
        )
    return frame


__all__ = ["CaptureFn", "capture"]
