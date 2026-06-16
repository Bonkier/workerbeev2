# SPDX-License-Identifier: GPL-3.0-or-later
"""Value types for the region/coordinate-translation layer.

Two coordinate spaces: FHD reference (1920 x 1080, the authoring space
for all regions, click targets and template sizes) and screen pixels
(where capture/click happen, differing by `WindowGeometry.scale`).
Distinct types (`Region` vs `ScreenRect`) make space mismatches a type
error instead of a silent forgot-to-scale bug.
"""
from __future__ import annotations

from dataclasses import dataclass


# Authoring reference: every Region is in this space.
FHD_WIDTH = 1920
FHD_HEIGHT = 1080


@dataclass(frozen=True)
class Region:
    """A rectangle in FHD-reference coordinates.

    Independent of the actual window size: a piece of the 1920 x 1080
    canvas the macro thinks in.
    """

    x: int
    y: int
    w: int
    h: int

    @classmethod
    def full(cls) -> Region:
        return cls(0, 0, FHD_WIDTH, FHD_HEIGHT)

    @classmethod
    def coerce(cls, value) -> Region:
        """Lift a Region-like value into a Region.

        Accepts a Region (as-is), a 4-tuple/list (wrapped), or None
        (full FHD frame). String-name lookups go through
        `automation.regions.as_region`; this stays dependency-free.
        """
        if value is None:
            return cls.full()
        if isinstance(value, Region):
            return value
        if isinstance(value, (tuple, list)):
            if len(value) != 4:
                raise ValueError(
                    f"Region tuple must be (x, y, w, h); got {value!r}"
                )
            x, y, w, h = value
            return cls(int(x), int(y), int(w), int(h))
        raise TypeError(
            f"Unsupported region type: {type(value).__name__}"
        )

    @property
    def right(self) -> int:
        return self.x + self.w

    @property
    def bottom(self) -> int:
        return self.y + self.h

    @property
    def center(self) -> tuple[int, int]:
        return (self.x + self.w // 2, self.y + self.h // 2)

    def offset_point(self, x: int, y: int) -> tuple[int, int]:
        """Translate a region-local (x, y) into FHD coordinates."""
        return (self.x + x, self.y + y)


@dataclass(frozen=True)
class ScreenRect:
    """A rectangle in screen-pixel coordinates (output of `region_to_screen`)."""

    x: int
    y: int
    w: int
    h: int

    def as_tuple(self) -> tuple[int, int, int, int]:
        return (self.x, self.y, self.w, self.h)


@dataclass(frozen=True)
class WindowGeometry:
    """Where the game window sits on screen and how big it is.

    `scale` is the window-to-FHD width ratio (1.0 = 1920 wide, 2.0 =
    4K, 0.5 = 960). Scaling is aspect-preserving and width-driven, per
    legacy contract; height is carried for capture bounds only, never
    as a scale source.
    """

    x: int
    y: int
    w: int
    h: int

    def __post_init__(self) -> None:
        if self.w <= 0 or self.h <= 0:
            raise ValueError(
                f"WindowGeometry needs positive size, got w={self.w} h={self.h}"
            )

    @property
    def scale(self) -> float:
        """Multiply an FHD-reference distance by this to get screen pixels."""
        return self.w / FHD_WIDTH

    @property
    def inv_scale(self) -> float:
        """Multiply a screen-pixel distance by this to get FHD reference."""
        return FHD_WIDTH / self.w

    @classmethod
    def identity(cls, x: int = 0, y: int = 0) -> WindowGeometry:
        """A window that exactly matches the FHD reference. Useful in tests."""
        return cls(x, y, FHD_WIDTH, FHD_HEIGHT)
