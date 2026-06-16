# SPDX-License-Identifier: GPL-3.0-or-later
"""Boundary layer: binds the pipeline to live app globals (params.WINDOW, OS gui module, telemetry)."""
from __future__ import annotations

import platform
from typing import Any, Optional

from .callsite import CallSiteBundle, build_call_sites
from .pipeline import build_pipeline
from .regionspec import WindowGeometry
from .vision import Finder, TemplateLoader
from .input import Mouse
from .verifier import Verifier


def _resolve_gui() -> Any:
    """Pick the OS backend for this platform."""
    system = platform.system()
    if system == "Windows":
        from .utils import os_windows_backend as gui
        return gui
    if system == "Linux":
        import os
        if os.environ.get("XDG_SESSION_TYPE") == "x11":
            from .utils import os_x11_backend as gui
            return gui
        raise RuntimeError("Wayland is not supported. Use Plasma (X11).")
    raise RuntimeError(f"Unsupported OS: {system}")


def _resolve_window() -> WindowGeometry:
    """WindowGeometry from the params.WINDOW tuple."""
    from .utils import params as p
    win = getattr(p, "WINDOW", None)
    if win is None:
        raise RuntimeError(
            "params.WINDOW is unset; call gui.set_window() first."
        )
    if len(win) != 4:
        raise RuntimeError(
            f"params.WINDOW has wrong shape: {win!r}"
        )
    return WindowGeometry(x=int(win[0]), y=int(win[1]),
                          w=int(win[2]), h=int(win[3]))


def _resolve_on_match() -> Any:
    """telemetry.match if importable, else None."""
    try:
        from .utils import telemetry as tele
        return tele.match
    except Exception:
        return None


def live_pipeline(
    *,
    prefilled_templates: Optional[dict[str, Any]] = None,
    default_conf: float = 0.9,
) -> tuple[Finder, Mouse, Verifier]:
    """Pipeline bound to live app globals. prefilled_templates seeds the cache (ndarrays only; paths load lazily)."""
    loader = TemplateLoader(prefilled=None)
    if prefilled_templates:
        # Only ndarrays seed; paths load lazily.
        seed: dict[str, Any] = {}
        for name, val in prefilled_templates.items():
            if hasattr(val, "shape"):  # ndarray duck-type
                seed[name] = val
        if seed:
            loader = TemplateLoader(prefilled=seed)

    return build_pipeline(
        window=_resolve_window(),
        gui=_resolve_gui(),
        loader=loader,
        on_match=_resolve_on_match(),
        default_conf=default_conf,
    )


def live_ops(
    *,
    prefilled_templates: Optional[dict[str, Any]] = None,
    default_conf: float = 0.9,
):
    """Ops bound to the live game window. Returns (finder, mouse, verifier, ops); ops carries RGB/gray/edges finders for mode routing."""
    from .detection import ColorMode
    from .input import Mouse
    from .ops import Ops
    from .pipeline import BackendAdapter
    from .verifier import Verifier
    from .vision import Finder, TemplateLoader

    finder, mouse, verifier = live_pipeline(
        prefilled_templates=prefilled_templates,
        default_conf=default_conf,
    )

    # Alternate color modes share the template cache and screenshot pipe.
    finder_gray = Finder(
        window=finder.window, backend=finder.backend,
        loader=finder.loader, on_match=finder.on_match,
        color_mode=ColorMode.GRAY, default_conf=default_conf,
    )
    finder_edges = Finder(
        window=finder.window, backend=finder.backend,
        loader=finder.loader, on_match=finder.on_match,
        color_mode=ColorMode.EDGES, default_conf=default_conf,
    )
    verifier_gray = Verifier(finder=finder_gray, mouse=mouse)
    verifier_edges = Verifier(finder=finder_edges, mouse=mouse)

    ops = Ops(
        finder, mouse, verifier,
        default_conf=default_conf,
        finder_gray=finder_gray,
        finder_edges=finder_edges,
        verifier_gray=verifier_gray,
        verifier_edges=verifier_edges,
    )
    return finder, mouse, verifier, ops


def live_call_sites(
    *,
    prefilled_templates: Optional[dict[str, Any]] = None,
    default_conf: float = 0.9,
) -> tuple[Finder, Mouse, Verifier, CallSiteBundle]:
    """Live pipeline plus the alias bundle (loc / click / now / try_click / now_click)."""
    finder, mouse, verifier = live_pipeline(
        prefilled_templates=prefilled_templates,
        default_conf=default_conf,
    )
    bundle = build_call_sites(
        finder, mouse, verifier,
        default_conf=default_conf,
    )
    return finder, mouse, verifier, bundle


__all__ = ["live_pipeline", "live_call_sites", "live_ops"]
