# SPDX-License-Identifier: GPL-3.0-or-later
"""Verifier: poll-until-found + click-when-found.

Splits the two concerns legacy `Locate.check` conflated: `wait_for`
returns a Match when a template appears (or None on timeout), and
`click_when_found` composes that with Mouse.click. `timeout`/`poll`
are in seconds; `sleep` is injected so tests run at zero wall time.
The Verifier composes the Finder and Mouse rather than owning them.
"""
from __future__ import annotations

import time
from typing import Any, Callable, Optional

import numpy as np

from ..detection import Match, MatchMethod, match_one
from ..input import Mouse
from ..regionspec import Region
from ..vision import Finder, TemplateRef, capture


SleepFn = Callable[[float], None]


# click_and_verify target shapes:
# - str ending "!": region-name reference (name lives in REGIONS)
# - str otherwise: template name that must change/disappear post-click
# - Region|tuple: raw region to snapshot and watch
VerifyTarget = Any


class Verifier:
    """Poll-until-found wrapper around a Finder, plus click composition."""

    def __init__(
        self,
        finder: Finder,
        mouse: Optional[Mouse] = None,
        sleep: SleepFn = time.sleep,
        memory: Any = None,
    ):
        self.finder = finder
        self.mouse = mouse
        self.sleep = sleep
        # Optional click muscle-memory (ClickMemory). None = disabled, which is
        # the default, so existing callers/tests behave exactly as before.
        self.memory = memory

    # --- wait_for ---------------------------------------------------------

    def wait_for(
        self,
        template: TemplateRef,
        region: "Region | tuple | None" = None,
        conf: Optional[float] = None,
        timeout: float = 5.0,
        poll: float = 0.1,
        on_first_miss: Optional[Callable[[], None]] = None,
        **load_kwargs: Any,
    ) -> Optional[Match]:
        """Poll the Finder for `template` until found or `timeout` elapses.

        Returns the Match on first hit, or None on timeout. Always
        attempts at least once (even at timeout 0) and sleeps between
        attempts, not before the first. `on_first_miss` (if given) is
        called once, after the first failed attempt, before sleeping -
        used to kick off an anticipatory pre-move while we keep polling.
        """
        if timeout <= 0:
            return self.finder.find(
                template, region=region, conf=conf, **load_kwargs
            )

        attempts = max(1, int(timeout / poll))
        for i in range(attempts):
            hit = self.finder.find(
                template, region=region, conf=conf, **load_kwargs
            )
            if hit is not None:
                return hit
            # Pre-move only when we'll actually keep polling - never on a
            # single-attempt (now_click-style) probe where it can't help.
            if i == 0 and attempts > 1 and on_first_miss is not None:
                on_first_miss()
            if i < attempts - 1:
                self.sleep(poll)
        return None

    # --- click_when_found -------------------------------------------------

    def click_when_found(
        self,
        template: TemplateRef,
        region: "Region | tuple | None" = None,
        conf: Optional[float] = None,
        timeout: float = 5.0,
        poll: float = 0.1,
        click_at: Optional[tuple[int, int]] = None,
        tsize: Optional[tuple[int, int]] = None,
        **load_kwargs: Any,
    ) -> bool:
        """Wait for `template`, then click. Returns True if clicked.

        - `click_at`: fixed FHD point to click regardless of where the
          template landed; overrides the match center.
        - `tsize`: FHD-unit jitter target size, passed to Mouse.click.
        """
        if self.mouse is None:
            raise RuntimeError(
                "click_when_found requires a Mouse; "
                "construct Verifier with mouse=Mouse(...)"
            )

        key, premove = self._memory_hook(template)
        started = time.monotonic()
        hit = self.wait_for(
            template,
            region=region,
            conf=conf,
            timeout=timeout,
            poll=poll,
            on_first_miss=premove,
            **load_kwargs,
        )
        if hit is None:
            return False

        target = click_at if click_at is not None else hit.center
        if tsize is not None:
            self.mouse.click(target, tsize=tsize)
        else:
            self.mouse.click(target)
        # Learn the real location only when we clicked the match (not a fixed
        # click_at override); pre-move never affects the click target above.
        if key is not None and click_at is None:
            self._remember(key, hit.center, time.monotonic() - started)
        return True

    # --- click muscle-memory helpers -------------------------------------

    def _memory_hook(self, template):
        """Return (key, on_first_miss) for the pre-move, or (None, None) when
        memory is disabled. The callback moves toward the learned spot while we
        keep polling; the real match is still what gets clicked."""
        mem = self.memory
        if mem is None or not getattr(mem, "enabled", False):
            return None, None
        try:
            from ..input.click_memory import key_for
            key = key_for(template)
        except Exception:
            return None, None

        def premove():
            try:
                point = mem.predict(key)
                if point is not None and self.mouse is not None:
                    self.mouse.move_to(point)
            except Exception:
                pass

        return key, premove

    def _remember(self, key, center, lead):
        try:
            self.memory.record(key, center, lead)
        except Exception:
            pass

    # --- click_and_verify ------------------------------------------------

    def _snapshot_region(self, verify_region: Region) -> np.ndarray:
        """Capture the verify region via the Finder's backend (same coord space)."""
        return capture(verify_region, self.finder.window, self.finder.backend)

    def _verify_unchanged(
        self,
        snapshot: np.ndarray,
        verify_region: Region,
        threshold: float = 0.98,
    ) -> bool:
        """True if verify_region still matches `snapshot` >= threshold.

        Detects "the click did nothing": an unchanged region means the
        action did not take effect.
        """
        current = self._snapshot_region(verify_region)
        # SQDIFF at high conf gives the cleanest "did it shift" signal.
        hit = match_one(
            current,
            snapshot,
            conf=threshold,
            method=MatchMethod.SQDIFF_NORMED,
        )
        return hit is not None

    def click_and_verify(
        self,
        template: TemplateRef,
        verify_region: "Region | tuple",
        region: "Region | tuple | None" = None,
        conf: Optional[float] = None,
        timeout: float = 5.0,
        poll: float = 0.1,
        click_at: Optional[tuple[int, int]] = None,
        tsize: Optional[tuple[int, int]] = None,
        verify_timeout: float = 3.0,
        verify_poll: float = 0.1,
        max_retries: int = 3,
        change_threshold: float = 0.98,
        **load_kwargs: Any,
    ) -> bool:
        """Find a template, click it, then verify the click took effect.

        Snapshots `verify_region` before clicking, then polls it for up
        to `verify_timeout`; if it stays unchanged (matches the snapshot
        above `change_threshold`) the click had no effect, so re-find
        and re-click up to `max_retries`. Returns True on a verified
        click; raises RuntimeError on exhausted retries.
        """
        if self.mouse is None:
            raise RuntimeError(
                "click_and_verify requires a Mouse; "
                "construct Verifier with mouse=Mouse(...)"
            )

        verify_region_obj = Region.coerce(verify_region)
        target_region = region
        key, premove = self._memory_hook(template)
        started = time.monotonic()

        for attempt in range(max_retries):
            # Re-locate on retries in case the template moved slightly.
            hit = self.wait_for(
                template,
                region=target_region,
                conf=conf,
                timeout=timeout if attempt == 0 else 0.0,
                poll=poll,
                on_first_miss=premove if attempt == 0 else None,
                **load_kwargs,
            )
            if hit is None:
                if attempt == 0:
                    return False  # initial find failed; nothing to retry
                raise RuntimeError(
                    f"click_and_verify: template disappeared between retries"
                )

            snapshot = self._snapshot_region(verify_region_obj)

            target = click_at if click_at is not None else hit.center
            if tsize is not None:
                self.mouse.click(target, tsize=tsize)
            else:
                self.mouse.click(target)

            verify_attempts = max(1, int(verify_timeout / verify_poll))
            verified = False
            for i in range(verify_attempts):
                if not self._verify_unchanged(
                    snapshot, verify_region_obj, threshold=change_threshold,
                ):
                    verified = True
                    break
                if i < verify_attempts - 1:
                    self.sleep(verify_poll)

            if verified:
                if key is not None and click_at is None:
                    self._remember(key, hit.center, time.monotonic() - started)
                return True
            # Region unchanged: retry the whole sequence.

        raise RuntimeError(
            f"click_and_verify: verification failed after {max_retries} retries"
        )


__all__ = ["Verifier", "SleepFn", "VerifyTarget"]
