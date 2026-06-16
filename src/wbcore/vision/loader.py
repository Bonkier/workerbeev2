# SPDX-License-Identifier: GPL-3.0-or-later
"""Template loading + transform pipeline.

Raw loads (path -> ndarray) are cached because `cv2.imread` is the
hottest blocking IO in the macro; transforms (scale, compression,
distortion) run per call from the cached raw, so the cache stays small.
Window scale is an explicit `window` arg, not baked in: pass
`WindowGeometry.identity()` for raw size, the live window to line up
with the captured frame.
"""
from __future__ import annotations

from pathlib import Path
from typing import Union

import cv2
import numpy as np

from ..regionspec import FHD_WIDTH, WindowGeometry


PathLike = Union[str, Path]


def _distort(image: np.ndarray, w: int, h: int, shift: int) -> np.ndarray:
    """Perspective tilt + recentering. Lifted from legacy Locate._distort."""
    src = np.float32([[0, 0], [w - 1, 0], [w - 1, h - 1], [0, h - 1]])
    dst = np.float32(
        [
            [0 + shift, 0],
            [w - 1 + shift, 0],
            [w - 1 - shift, h - 1],
            [0 - shift, h - 1],
        ]
    )
    perspective = cv2.getPerspectiveTransform(src, dst)
    translation = np.array(
        [[1, 0, -shift // 2], [0, 1, 0], [0, 0, 1]], dtype=np.float32
    )
    combined = translation @ perspective
    return cv2.warpPerspective(image, combined, (w + 1, h))


class TemplateLoader:
    """Loads template PNGs from disk, optionally caching the raw bytes.

    Construct at app startup, pass to a `Finder`. Tests can pass
    `cache=False` or a pre-seeded `prefilled` dict to avoid disk.
    `track_usage=True` records per-path load counts for an unused-asset
    audit (see `usage_report`).
    """

    def __init__(
        self,
        cache: bool = True,
        prefilled: dict[str, np.ndarray] | None = None,
        track_usage: bool = False,
    ):
        self._enabled = cache
        self._raw: dict[str, np.ndarray] = dict(prefilled or {})
        self._track = bool(track_usage)
        self._usage: dict[str, int] = {}

    def _imread(self, path: PathLike) -> np.ndarray:
        key = str(path)
        if self._enabled and key in self._raw:
            return self._raw[key]
        img = cv2.imread(key)
        if img is None:
            raise FileNotFoundError(f"Template not found or unreadable: {key}")
        if self._enabled:
            self._raw[key] = img
        return img

    def load(
        self,
        template: PathLike | np.ndarray,
        comp: float = 1.0,
        v_comp: float | None = None,
        h_comp: float | None = None,
        distort: float | None = None,
        window: WindowGeometry | None = None,
    ) -> np.ndarray:
        """Return the template ready to feed `detection.match_one/all`.

        - `comp`: uniform scale, on top of the window scale.
        - `v_comp`: vertical-only compression in (0, 1].
        - `h_comp`: horizontal-only scale in (0, inf).
        - `distort`: perspective shear fraction (e.g. 0.05).
        - `window`: when given, baked-in. Pass
          `WindowGeometry.identity()` (or omit) for the raw size.
        """
        if isinstance(template, np.ndarray):
            tmpl = template
        else:
            if self._track:
                key = str(template)
                self._usage[key] = self._usage.get(key, 0) + 1
            tmpl = self._imread(template)

        # Window scale multiplies the explicit comp factor (legacy semantics).
        if window is not None:
            effective_comp = comp * window.scale
        else:
            effective_comp = comp

        if effective_comp != 1.0:
            tmpl = cv2.resize(
                tmpl, None, fx=effective_comp, fy=effective_comp,
                interpolation=cv2.INTER_AREA,
            )

        if v_comp is not None:
            if not (0 < v_comp <= 1):
                raise ValueError(
                    f"Invalid vertical compression value: {v_comp!r}"
                )
            new_size = (int(tmpl.shape[1]), int(tmpl.shape[0] * v_comp))
            tmpl = cv2.resize(tmpl, new_size, interpolation=cv2.INTER_AREA)

        if h_comp is not None:
            if not (0 < h_comp):
                raise ValueError(
                    f"Invalid horizontal compression value: {h_comp!r}"
                )
            new_size = (int(tmpl.shape[1] * h_comp), int(tmpl.shape[0]))
            tmpl = cv2.resize(tmpl, new_size, interpolation=cv2.INTER_CUBIC)

        if distort is not None:
            h, w = tmpl.shape[:2]
            shift = int(w * distort)
            tmpl = _distort(tmpl, w, h, shift)

        return tmpl

    # --- Cache management --------------------------------------------------

    def clear(self) -> None:
        self._raw.clear()

    def cache_size(self) -> int:
        return len(self._raw)

    def is_cached(self, path: PathLike) -> bool:
        return str(path) in self._raw

    # --- Usage tracking ---------------------------------------------------

    def usage_report(self) -> list[tuple[int, str]]:
        """Per-path load counts, sorted descending. Empty when tracking is off.

        Run a full session with tracking on; paths absent from the
        report are candidates for deletion from `ImageAssets/`.
        """
        return sorted(
            ((count, path) for path, count in self._usage.items()),
            key=lambda pair: (-pair[0], pair[1]),
        )

    def usage_total(self) -> int:
        """Sum of all per-path counts. 0 when tracking is off."""
        return sum(self._usage.values())

    def reset_usage(self) -> None:
        """Drop the usage counters. Cache is untouched."""
        self._usage.clear()


__all__ = ["TemplateLoader", "PathLike"]
