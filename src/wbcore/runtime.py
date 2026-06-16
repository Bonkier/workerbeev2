# SPDX-License-Identifier: GPL-3.0-or-later
"""Shared lazy Ops + state alias for game-flow modules. `ops` resolves to a real Ops on first access (after params.WINDOW is set); `state` is wbcore.utils.params under a friendlier name."""
from __future__ import annotations

from typing import Any


class _LazyOps:
    """Proxy that resolves to a real Ops on first attribute access. Lazy so module-level imports work before params.WINDOW is set."""

    __slots__ = ("_resolved",)

    def __init__(self) -> None:
        object.__setattr__(self, "_resolved", None)

    def _resolve(self):
        cached = object.__getattribute__(self, "_resolved")
        if cached is None:
            from .live import live_ops
            from .utils.paths import PTH
            _, _, _, ops_obj = live_ops(prefilled_templates=PTH)
            object.__setattr__(self, "_resolved", ops_obj)
            return ops_obj
        return cached

    def __getattr__(self, name: str) -> Any:
        return getattr(self._resolve(), name)

    def __setattr__(self, name: str, value: Any) -> None:
        if name in self.__slots__:
            object.__setattr__(self, name, value)
        else:
            setattr(self._resolve(), name, value)

    def reset(self) -> None:
        """Drop the cached Ops. Tests + window rediscovery use this."""
        object.__setattr__(self, "_resolved", None)


ops = _LazyOps()

from .utils import params as state             # noqa: E402


__all__ = ["ops", "state"]
