# SPDX-License-Identifier: GPL-3.0-or-later
"""Typed Region accessors over the legacy REG tuple dict. REG (utils.paths) stays the source of truth; this is a thin wrapper."""
from __future__ import annotations

from typing import Mapping, Union

from .regionspec import Region


_RegionLike = Union[Region, tuple, str, None]


def _build_regions() -> dict[str, Region]:
    """Lift the legacy REG 4-tuple dict into a Region dict. Lazy: utils.paths walks ImageAssets, so defer."""
    from .utils.paths import REG
    out: dict[str, Region] = {}
    for name, value in REG.items():
        if not (isinstance(value, tuple) and len(value) == 4):
            # Skip non-rectangle metadata REG may hold in the future.
            continue
        x, y, w, h = value
        out[name] = Region(int(x), int(y), int(w), int(h))
    return out


# Lazy: avoid the PTH disk walk on module load.
_REGIONS_CACHE: dict[str, Region] | None = None


def _regions() -> dict[str, Region]:
    global _REGIONS_CACHE
    if _REGIONS_CACHE is None:
        _REGIONS_CACHE = _build_regions()
    return _REGIONS_CACHE


class _RegionsProxy(Mapping[str, Region]):
    """Read-only dict-like proxy. Defers utils.paths import until first access."""

    def __getitem__(self, key: str) -> Region:
        return _regions()[key]

    def __iter__(self):
        return iter(_regions())

    def __len__(self) -> int:
        return len(_regions())

    def __contains__(self, key: object) -> bool:
        return key in _regions()

    def get(self, key: str, default: Region | None = None) -> Region | None:
        return _regions().get(key, default)


REGIONS: Mapping[str, Region] = _RegionsProxy()


def as_region(value: _RegionLike) -> Region:
    """Coerce to Region. Accepts Region, (x,y,w,h), name str (KeyError on miss), or None (full frame)."""
    if value is None:
        return Region.full()
    if isinstance(value, Region):
        return value
    if isinstance(value, str):
        return REGIONS[value]
    if isinstance(value, (tuple, list)):
        if len(value) != 4:
            raise ValueError(
                f"Region tuple must be (x, y, w, h); got {value!r}"
            )
        x, y, w, h = value
        return Region(int(x), int(y), int(w), int(h))
    raise TypeError(f"Unsupported region type: {type(value).__name__}")


def reset_cache() -> None:
    """Drop the cached REGIONS dict. Tests use this to force a rebuild."""
    global _REGIONS_CACHE
    _REGIONS_CACHE = None


__all__ = ["REGIONS", "as_region", "reset_cache"]
