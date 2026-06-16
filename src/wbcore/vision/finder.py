# SPDX-License-Identifier: GPL-3.0-or-later
"""High-level template finder.

`Finder` composes Detection, RegionSpec, Capture and TemplateLoader
into one call: find a template in a region and return a hit in FHD
coordinates. It deliberately does not click and does not retry - those
are Input and Verifier concerns.
"""
from __future__ import annotations

from typing import Callable, Union

import numpy as np

from ..detection import ColorMode, Match, MatchMethod, match_all, match_one
from ..regionspec import (
    Region,
    WindowGeometry,
    lift_match_to_fhd,
)
from .capture import CaptureFn, capture
from .loader import PathLike, TemplateLoader


# Optional telemetry hook: (template_name, fhd_box) -> None.
TelemetryCallback = Callable[[str, tuple[int, int, int, int]], None]

TemplateRef = Union[PathLike, np.ndarray]


class Finder:
    """Finds templates in the game window. All matches are in FHD coords.

    Construct once at app startup with window geometry, a capture
    backend and a loader.
    """

    def __init__(
        self,
        window: WindowGeometry,
        backend: CaptureFn,
        loader: TemplateLoader | None = None,
        color_mode: ColorMode = ColorMode.RGB,
        method: MatchMethod = MatchMethod.CCOEFF_NORMED,
        default_conf: float = 0.9,
        on_match: TelemetryCallback | None = None,
    ):
        self.window = window
        self.backend = backend
        self.loader = loader or TemplateLoader()
        self.color_mode = color_mode
        self.method = method
        self.default_conf = default_conf
        self.on_match = on_match

    # --- internal helpers --------------------------------------------------

    def _prepare_frame(
        self, frame: np.ndarray | None, region: Region
    ) -> np.ndarray:
        if frame is not None:
            return frame
        return capture(region, self.window, self.backend)

    def _prepare_template(
        self, template: TemplateRef, **load_kwargs
    ) -> np.ndarray:
        # Default to baking in the live window scale (legacy behaviour);
        # callers wanting raw size pass window=None via load_kwargs.
        load_kwargs.setdefault("window", self.window)
        return self.loader.load(template, **load_kwargs)

    def _emit(self, template_name: str, hit: Match | None) -> None:
        if hit is None or self.on_match is None:
            return
        self.on_match(template_name, hit.box)

    def _name_of(self, template: TemplateRef) -> str:
        """Display name for telemetry/overlay: strip directory and extension."""
        if isinstance(template, np.ndarray):
            return "ndarray"
        import os
        base = os.path.basename(str(template))
        stem, _ext = os.path.splitext(base)
        return stem or base

    def _lift(self, raw: Match, region: Region) -> Match:
        x, y, w, h = lift_match_to_fhd(raw.box, region, self.window)
        return Match(
            x=x, y=y, w=w, h=h,
            confidence=raw.confidence,
            template_name=raw.template_name,
        )

    # --- public API --------------------------------------------------------

    def find(
        self,
        template: TemplateRef,
        region: Region | tuple | None = None,
        conf: float | None = None,
        frame: np.ndarray | None = None,
        **load_kwargs,
    ) -> Match | None:
        """Find the single best match. Returns a Match in FHD coords.

        `region` accepts a Region, a legacy `(x, y, w, h)` tuple, or
        None (full FHD frame); tuples are coerced via `Region.coerce`.
        """
        region = Region.coerce(region)
        conf = conf if conf is not None else self.default_conf
        name = self._name_of(template)

        frame = self._prepare_frame(frame, region)
        tmpl = self._prepare_template(template, **load_kwargs)

        raw = match_one(
            frame, tmpl,
            conf=conf, method=self.method, color_mode=self.color_mode,
            template_name=name,
        )
        if raw is None:
            return None
        hit = self._lift(raw, region)
        self._emit(name, hit)
        return hit

    def find_all(
        self,
        template: TemplateRef,
        region: Region | tuple | None = None,
        conf: float | None = None,
        frame: np.ndarray | None = None,
        nms_threshold: int = 8,
        **load_kwargs,
    ) -> list[Match]:
        """Find every match. Returns Matches in FHD coords.

        `region` accepts a `Region`, a legacy `(x, y, w, h)` tuple, or
        `None`. Tuples are coerced via `Region.coerce`.
        """
        region = Region.coerce(region)
        conf = conf if conf is not None else self.default_conf
        name = self._name_of(template)

        frame = self._prepare_frame(frame, region)
        tmpl = self._prepare_template(template, **load_kwargs)

        raw_hits = match_all(
            frame, tmpl,
            conf=conf, method=self.method, color_mode=self.color_mode,
            nms_threshold=nms_threshold, template_name=name,
        )
        lifted = [self._lift(h, region) for h in raw_hits]
        for h in lifted:
            self._emit(name, h)
        return lifted


__all__ = ["Finder", "TelemetryCallback", "TemplateRef"]
