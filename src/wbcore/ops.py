# SPDX-License-Identifier: GPL-3.0-or-later
"""Shop-floor operations API.

The entry point most game-flow code uses: find this template, click that
one, wait for the screen to settle, verify the click took. Consolidates the
old module-level helpers (now, click, try_click, now_click, loc, loc_rgb)
into a single `Ops` object whose methods take explicit kwargs for timing
and error semantics:

- "find now, no waiting"        -> ops.find("X")
- "click and wait up to 5s"     -> ops.click("X")
- "click or die"                -> ops.click("X", strict=True)

`Ops` is a thin facade over the pipeline primitives (Finder.find,
Verifier.wait_for / click_when_found / click_and_verify, Mouse.click); it
re-implements none of them. Construct one at app start via
`Ops.from_pipeline(...)` (or `live_ops()` in `wbcore.live`) and share it.
"""
from __future__ import annotations

from typing import Any, Callable, Optional

import numpy as np

from .detection import Match
from .input import Mouse
from .regionspec import Region
from .verifier import Verifier
from .vision import Finder


TemplateRef = Any        # str path, np.ndarray, Path
TemplateResolver = Callable[[str], TemplateRef]
RegionResolver = Callable[[str], Optional[Region]]


def _default_template_resolver(name: str) -> TemplateRef:
    """`PTH[name.split('.')[0]]`, handling the dotted-name convention (`Confirm.1` -> `Confirm`)."""
    from .utils.paths import PTH
    return PTH[name.split(".")[0]]


def _default_region_resolver(name: str) -> Optional[Region]:
    """`REGIONS.get(name)`; None on miss so the caller falls through to the full FHD frame."""
    from .regions import REGIONS
    return REGIONS.get(name)


class _OpFailure(RuntimeError):
    """Raised by strict-mode ops when the underlying action missed.

    Subclasses RuntimeError so existing broad `except RuntimeError:` blocks
    still catch it, while staying identifiable for callers that want to."""


class Ops:
    """High-level shop-floor operations bound to a pipeline.

    All methods take a `name` (template-name string looked up in PTH/REGIONS)
    or a raw template ref. Coordinate overrides (`at`, `region`) accept FHD
    tuples or Regions interchangeably; the Finder coerces.

    Uniform time/error behaviour:
    - timeout (default 5.0 for click, 0.0 for find): 0 = single check; >0 = poll the verifier.
    - strict (default False): on miss, raise _OpFailure instead of returning False/None.
    - verify (default None): template/region to snapshot before the click and watch for change after; triggers the Verifier.click_and_verify retry loop.
    """

    OpFailure = _OpFailure

    def __init__(
        self,
        finder: Finder,
        mouse: Mouse,
        verifier: Verifier,
        *,
        template_resolver: TemplateResolver = _default_template_resolver,
        region_resolver: RegionResolver = _default_region_resolver,
        default_conf: Optional[float] = None,
        finder_gray: Optional[Finder] = None,
        finder_edges: Optional[Finder] = None,
        verifier_gray: Optional[Verifier] = None,
        verifier_edges: Optional[Verifier] = None,
    ):
        self.finder = finder
        self.mouse = mouse
        self.verifier = verifier
        self._template = template_resolver
        self._region = region_resolver
        self._default_conf = default_conf
        # Optional per-color-mode finders/verifiers. When None, `mode=` falls
        # back to the RGB finder (correct for most templates, but without the
        # robustness boost gray/edge matching gives).
        self._finder_gray = finder_gray
        self._finder_edges = finder_edges
        self._verifier_gray = verifier_gray
        self._verifier_edges = verifier_edges

    def _pick(self, mode: str) -> tuple[Finder, Verifier]:
        """Resolve the (finder, verifier) pair for `mode`. Unknown modes fall back to RGB so a typo doesn't crash the macro mid-run."""
        if mode == "gray" and self._finder_gray is not None:
            return self._finder_gray, (self._verifier_gray or self.verifier)
        if mode == "edges" and self._finder_edges is not None:
            return self._finder_edges, (self._verifier_edges or self.verifier)
        return self.finder, self.verifier

    @classmethod
    def from_pipeline(
        cls,
        finder: Finder,
        mouse: Mouse,
        verifier: Verifier,
        **kwargs,
    ) -> "Ops":
        """Mirror the `build_pipeline` triple. Same as `Ops(finder, mouse, verifier, **kwargs)`; kept for symmetry with `live_ops()`."""
        return cls(finder, mouse, verifier, **kwargs)

    # -------------------------------------------------------------- find

    def find(
        self,
        name: TemplateRef,
        region: Optional[Region | tuple] = None,
        *,
        timeout: float = 0.0,
        poll: float = 0.1,
        conf: Optional[float] = None,
        strict: bool = False,
        mode: str = "rgb",
        **load_kwargs: Any,
    ) -> Optional[Match]:
        """Locate `name`. Returns the Match, or None on miss.

        timeout=0 does one instantaneous check; timeout>0 polls the verifier.
        strict=True raises on miss. mode="gray"|"edges" switches the color
        reduction (default RGB).
        """
        template, target_region = self._resolve(name, region)
        effective_conf = conf if conf is not None else self._default_conf
        finder, verifier = self._pick(mode)

        if timeout > 0:
            hit = verifier.wait_for(
                template, region=target_region, conf=effective_conf,
                timeout=timeout, poll=poll, **load_kwargs,
            )
        else:
            hit = finder.find(
                template, region=target_region, conf=effective_conf,
                **load_kwargs,
            )

        if hit is None and strict:
            raise _OpFailure(f"Ops.find({name!r}) returned no match")
        return hit

    # ------------------------------------------------------------- click

    def click(
        self,
        name: TemplateRef,
        region: Optional[Region | tuple] = None,
        *,
        timeout: float = 5.0,
        poll: float = 0.1,
        conf: Optional[float] = None,
        at: Optional[tuple[int, int]] = None,
        tsize: Optional[tuple[int, int]] = None,
        verify: Optional[str | Region | tuple] = None,
        verify_timeout: float = 3.0,
        max_retries: int = 3,
        strict: bool = False,
        **load_kwargs: Any,
    ) -> bool:
        """Wait for `name`, then click it. Returns True on success.

        - at=(x, y): click those coordinates instead of the matched centre.
        - tsize=(w, h): jitter box size for the click, in FHD units.
        - verify=<name|region>: snapshot that area before clicking and re-click
          if it stays the same after; runs Verifier.click_and_verify.
        - strict=True: raise Ops.OpFailure on miss.
        - timeout=0: try once.
        """
        template, target_region = self._resolve(name, region)
        effective_conf = conf if conf is not None else self._default_conf

        if verify is not None:
            verify_region = self._coerce_region_like(verify)
            ok = self.verifier.click_and_verify(
                template, verify_region=verify_region,
                region=target_region, conf=effective_conf,
                timeout=timeout, poll=poll,
                click_at=at, tsize=tsize,
                verify_timeout=verify_timeout, max_retries=max_retries,
                **load_kwargs,
            )
        else:
            ok = self.verifier.click_when_found(
                template, region=target_region, conf=effective_conf,
                timeout=timeout, poll=poll,
                click_at=at, tsize=tsize,
                **load_kwargs,
            )

        if not ok and strict:
            raise _OpFailure(f"Ops.click({name!r}) did not land")
        return ok

    # ---------------------------------------------------------- wait_gone

    def wait_gone(
        self,
        name: TemplateRef,
        region: Optional[Region | tuple] = None,
        *,
        timeout: float = 5.0,
        poll: float = 0.1,
        conf: Optional[float] = None,
        strict: bool = False,
        **load_kwargs: Any,
    ) -> bool:
        """Poll until `name` disappears. True on disappearance, False on timeout."""
        import time
        attempts = max(1, int(timeout / poll))
        for i in range(attempts):
            hit = self.find(name, region=region, conf=conf, **load_kwargs)
            if hit is None:
                return True
            if i < attempts - 1:
                time.sleep(poll)
        if strict:
            raise _OpFailure(
                f"Ops.wait_gone({name!r}) never disappeared within {timeout}s")
        return False

    # -------------------------------------------------- multi-match find

    def find_all(
        self,
        name: TemplateRef,
        region: Optional[Region | tuple] = None,
        *,
        conf: Optional[float] = None,
        nms_threshold: int = 8,
        max_hits: Optional[int] = None,
        mode: str = "rgb",
        **load_kwargs: Any,
    ) -> list[Match]:
        """Locate every match of `name`. Returns the list (possibly empty)."""
        template, target_region = self._resolve(name, region)
        effective_conf = conf if conf is not None else self._default_conf
        finder, _ = self._pick(mode)
        hits = finder.find_all(
            template, region=target_region, conf=effective_conf,
            nms_threshold=nms_threshold, **load_kwargs,
        )
        if max_hits is not None:
            hits = hits[:max_hits]
        return hits

    # -------------------------------------------------- raw screenshot

    def snapshot(
        self,
        region: Optional[Region | tuple] = None,
    ) -> np.ndarray:
        """Fresh capture of `region` (or the full frame if None), for callers that crunch raw pixels (inventory OCR, gif extraction). Returns a contiguous writable copy."""
        from .vision import capture
        region_obj = Region.coerce(region)
        return capture(region_obj, self.finder.window, self.finder.backend)

    # ----------------------------------------------------- raw mouse ops

    def move_to(self, point: tuple[int, int], **kwargs: Any) -> None:
        """Move the cursor to `point` in FHD coords."""
        self.mouse.move_to(point, **kwargs)

    def click_at(
        self,
        point: Optional[tuple[int, int]] = None,
        **kwargs: Any,
    ) -> None:
        """Direct click at the given FHD point, no template detection."""
        self.mouse.click(point, **kwargs)

    def drag_to(self, point: tuple[int, int], **kwargs: Any) -> None:
        """Drag the cursor to `point` in FHD coords."""
        self.mouse.drag_to(point, **kwargs)

    def cursor(self) -> tuple[int, int]:
        """Current cursor position in FHD coords."""
        return self.mouse.position()

    # -------------------------------------- keyboard / scroll passthroughs

    def press(self, key: str, **kwargs: Any) -> None:
        """Tap a key via the input backend, so callers don't import the platform backend directly."""
        adapter = self.mouse.backend
        gui = getattr(adapter, "_gui", adapter)
        gui.press(key, **kwargs)

    def scroll(
        self,
        amount: int,
        x: Optional[int] = None,
        y: Optional[int] = None,
    ) -> None:
        """Scroll the wheel by `amount` (positive up, negative down)
        at the given FHD point (or wherever the cursor is)."""
        adapter = self.mouse.backend
        gui = getattr(adapter, "_gui", adapter)
        # The platform backends accept screen-pixel coords; reuse the
        # same FHD->screen translation Mouse.click does.
        if x is not None and y is not None:
            from .regionspec import point_fhd_to_screen
            sx, sy = point_fhd_to_screen((x, y), self.mouse.window)
            gui.scroll(amount, sx, sy)
        else:
            gui.scroll(amount)

    def active_window_title(self) -> str:
        """Window title of the currently focused OS window. Used by the
        legacy pause-on-defocus check."""
        adapter = self.mouse.backend
        gui = getattr(adapter, "_gui", adapter)
        return gui.getActiveWindowTitle()

    # ---------------------------------------------------------- internals

    def _resolve(
        self,
        name_or_template: TemplateRef,
        explicit_region: Optional[Region | tuple],
    ) -> tuple[TemplateRef, Optional[Region]]:
        """Turn (name, region) into (template, resolved_region).

        - Strings go through the template_resolver and the matching
          region_resolver entry (so `name="Confirm"` resolves both
          `PTH["Confirm"]` and `REGIONS["Confirm"]`).
        - ndarrays / Paths are templates; no region lookup is
          attempted unless `explicit_region` is supplied.
        - `explicit_region` always wins when provided.
        """
        if isinstance(name_or_template, str):
            template = self._template(name_or_template)
            resolved_region = self._region(name_or_template)
        elif isinstance(name_or_template, np.ndarray):
            template = name_or_template
            resolved_region = None
        else:
            template = name_or_template
            resolved_region = None

        target_region = (
            explicit_region if explicit_region is not None else resolved_region
        )
        return template, target_region

    def _coerce_region_like(
        self,
        value: str | Region | tuple,
    ) -> Region:
        """Used by `verify=`; accepts a name (looked up in REGIONS),
        a Region, or a 4-tuple."""
        if isinstance(value, str):
            key = value.rstrip("!") if value.endswith("!") else value
            resolved = self._region(key)
            if resolved is None:
                raise KeyError(f"verify={value!r}: no region named {key!r}")
            return resolved
        return Region.coerce(value)


__all__ = ["Ops"]
