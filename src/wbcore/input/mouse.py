# SPDX-License-Identifier: GPL-3.0-or-later
"""Mouse: FHD-aware wrapper around an InputBackend.

Window geometry and backend are injected via the constructor (no
module-level globals). Every method takes a point in FHD reference and
translates to screen pixels internally; `tsize` is in FHD units and
scaled on the way out.
"""
from __future__ import annotations

from typing import Any, Optional

from ..regionspec import (
    WindowGeometry,
    point_fhd_to_screen,
    point_screen_to_fhd,
    scale_size,
)
from .types import InputBackend


Point = tuple[int, int]


class Mouse:
    """FHD-aware mouse driver.

    Construct once per app, share. Stateless beyond the
    (window, backend) it was built with.
    """

    def __init__(self, window: WindowGeometry, backend: InputBackend):
        self.window = window
        self.backend = backend

    # --- internal ----------------------------------------------------------

    def _scale_kwargs(self, kwargs: dict[str, Any]) -> dict[str, Any]:
        """Scale FHD-unit sizes inside backend kwargs (currently only `tsize`)."""
        if "tsize" in kwargs and kwargs["tsize"] is not None:
            kwargs = dict(kwargs)
            kwargs["tsize"] = scale_size(tuple(kwargs["tsize"]), self.window)
        return kwargs

    # --- click -------------------------------------------------------------

    def click(
        self,
        point: Optional[Point] = None,
        **kwargs: Any,
    ) -> None:
        """Click at `point` in FHD coords, or the current position if None."""
        kwargs = self._scale_kwargs(kwargs)
        if point is None:
            self.backend.click(None, None, **kwargs)
            return
        x, y = point_fhd_to_screen(point, self.window)
        self.backend.click(x, y, **kwargs)

    # --- move --------------------------------------------------------------

    def move_to(self, point: Point, **kwargs: Any) -> None:
        kwargs = self._scale_kwargs(kwargs)
        x, y = point_fhd_to_screen(point, self.window)
        self.backend.move_to(x, y, **kwargs)

    # --- drag --------------------------------------------------------------

    def drag_to(self, point: Point, **kwargs: Any) -> None:
        kwargs = self._scale_kwargs(kwargs)
        x, y = point_fhd_to_screen(point, self.window)
        self.backend.drag_to(x, y, **kwargs)

    # --- position ----------------------------------------------------------

    def position(self) -> Point:
        """Cursor position in FHD coords (translated from screen pixels)."""
        screen_pt = self.backend.position()
        return point_screen_to_fhd(screen_pt, self.window)


__all__ = ["Mouse", "Point"]
