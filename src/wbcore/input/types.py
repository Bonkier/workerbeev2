# SPDX-License-Identifier: GPL-3.0-or-later
"""Input-layer protocols.

`InputBackend` is the contract for anything that can move a mouse,
click, drag and report position. Both os_windows_backend and
os_x11_backend fit with a thin adapter; tests use a recording fake.
"""
from __future__ import annotations

from typing import Any, Optional, Protocol


class InputBackend(Protocol):
    """The minimal mouse contract. All coordinates are screen pixels.

    The Mouse class converts FHD-reference coordinates to screen pixels
    via `regionspec.point_fhd_to_screen` before calling these.
    """

    def move_to(self, x: int, y: int, **kwargs: Any) -> None: ...

    def click(
        self,
        x: Optional[int] = None,
        y: Optional[int] = None,
        **kwargs: Any,
    ) -> None: ...

    def drag_to(self, x: int, y: int, **kwargs: Any) -> None: ...

    def position(self) -> tuple[int, int]: ...


__all__ = ["InputBackend"]
