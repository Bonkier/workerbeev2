# SPDX-License-Identifier: GPL-3.0-or-later
"""Pipeline factory. build_pipeline() returns (Finder, Mouse, Verifier) wired through one BackendAdapter that satisfies both CaptureFn and InputBackend."""
from __future__ import annotations

from typing import Any, Optional

import numpy as np

from .input import InputBackend, Mouse
from .regionspec import ScreenRect, WindowGeometry
from .vision import CaptureFn, Finder, TelemetryCallback, TemplateLoader
from .verifier import Verifier


class BackendAdapter:
    """Wraps an os_*_backend gui module to satisfy both CaptureFn and InputBackend.

    Translates name mismatches (moveTo/move_to, get_position/position) and
    coerces screenshots to a writable, contiguous, uint8 ndarray - mss/GDI
    frames can otherwise land as read-only views, which breaks cv2.rectangle.
    """

    def __init__(self, gui_module: Any):
        # gui_module is duck-typed; production is os_windows_backend or os_x11_backend.
        self._gui = gui_module

    def __call__(self, rect: ScreenRect) -> np.ndarray:
        frame = self._gui.screenshot(region=rect.as_tuple())
        if not isinstance(frame, np.ndarray):
            frame = np.array(frame)
        return np.ascontiguousarray(frame)

    def move_to(self, x: int, y: int, **kwargs: Any) -> None:
        self._gui.moveTo(x, y, **kwargs)

    def click(
        self,
        x: Optional[int] = None,
        y: Optional[int] = None,
        **kwargs: Any,
    ) -> None:
        self._gui.click(x, y, **kwargs)

    def drag_to(self, x: int, y: int, **kwargs: Any) -> None:
        self._gui.dragTo(x, y, **kwargs)

    def position(self) -> tuple[int, int]:
        return self._gui.get_position()


def build_pipeline(
    window: WindowGeometry,
    gui: Any,
    *,
    loader: Optional[TemplateLoader] = None,
    on_match: Optional[TelemetryCallback] = None,
    default_conf: float = 0.9,
) -> tuple[Finder, Mouse, Verifier]:
    """Build (Finder, Mouse, Verifier) sharing one BackendAdapter. Construct once per app.

    loader=None creates a fresh TemplateLoader; pass TemplateLoader(prefilled=...) to seed.
    on_match=None disables telemetry; pass telemetry.match to wire the overlay channel.
    """
    adapter = BackendAdapter(gui)
    finder = Finder(
        window=window,
        backend=adapter,
        loader=loader or TemplateLoader(),
        on_match=on_match,
        default_conf=default_conf,
    )
    mouse = Mouse(window=window, backend=adapter)
    verifier = Verifier(finder=finder, mouse=mouse)
    return finder, mouse, verifier


__all__ = ["BackendAdapter", "build_pipeline"]
