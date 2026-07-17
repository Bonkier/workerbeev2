# SPDX-License-Identifier: GPL-3.0-or-later
"""High-level template finder.

`Finder` composes Detection, RegionSpec, Capture and TemplateLoader
into one call: find a template in a region and return a hit in FHD
coordinates. It deliberately does not click and does not retry - those
are Input and Verifier concerns.
"""
from __future__ import annotations

from typing import Callable, Union

import cv2
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

# Below FHD, shrinking a detailed template to window scale loses correlation;
# upscaling the capture to FHD and matching at native size recovers it. The
# confidence floor is deliberately NOT relaxed here - a uniform relaxation
# lowers every gate and caused false matches that broke the event handler.
# Callers matching detailed art (gift icons, ~0.86 even upscaled) pass their
# own lower conf instead.
# Scales this close to 1.0 are treated as FHD: no upscale.
_FHD_SCALE_EPS = 0.999


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

    def _lift(
        self, raw: Match, region: Region, window: WindowGeometry | None = None
    ) -> Match:
        x, y, w, h = lift_match_to_fhd(raw.box, region, window or self.window)
        return Match(
            x=x, y=y, w=w, h=h,
            confidence=raw.confidence,
            template_name=raw.template_name,
        )

    def _prepare_inputs(
        self,
        template: TemplateRef,
        region: Region,
        conf: float,
        frame: np.ndarray | None,
        load_kwargs: dict,
    ) -> tuple[np.ndarray, np.ndarray, float, WindowGeometry]:
        """Capture/scale the frame and load the template for matching.

        Returns (frame, template, conf, lift_window). Below FHD, when we
        capture the frame ourselves, upscale it to FHD and match the template
        at native size; the match then lifts with an identity window since the
        frame is already FHD-scale. The confidence floor is left untouched.
        Callers that pass their own frame or an explicit `window` keep the
        legacy shrink-the-template behaviour.
        """
        captured = frame is None
        frame = self._prepare_frame(frame, region)
        upscale = (
            captured
            and self.window.scale < _FHD_SCALE_EPS
            and "window" not in load_kwargs
        )
        if not upscale:
            tmpl = self._prepare_template(template, **load_kwargs)
            return frame, tmpl, conf, self.window
        inv = self.window.inv_scale
        frame = cv2.resize(
            frame, None, fx=inv, fy=inv, interpolation=cv2.INTER_CUBIC
        )
        tmpl = self.loader.load(template, window=None, **load_kwargs)
        return frame, tmpl, conf, WindowGeometry.identity()

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

        frame, tmpl, conf, lift_window = self._prepare_inputs(
            template, region, conf, frame, load_kwargs
        )

        raw = match_one(
            frame, tmpl,
            conf=conf, method=self.method, color_mode=self.color_mode,
            template_name=name,
        )
        if raw is None:
            return None
        hit = self._lift(raw, region, lift_window)
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

        frame, tmpl, conf, lift_window = self._prepare_inputs(
            template, region, conf, frame, load_kwargs
        )

        raw_hits = match_all(
            frame, tmpl,
            conf=conf, method=self.method, color_mode=self.color_mode,
            nms_threshold=nms_threshold, template_name=name,
        )
        lifted = [self._lift(h, region, lift_window) for h in raw_hits]
        for h in lifted:
            self._emit(name, h)
        return lifted


__all__ = ["Finder", "TelemetryCallback", "TemplateRef"]
