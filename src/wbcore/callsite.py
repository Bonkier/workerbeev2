# SPDX-License-Identifier: GPL-3.0-or-later
"""Preset-bound call sites: immutable Finder/Mouse/Verifier wrappers with name-based PTH/REGIONS lookup."""
from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Any, Callable, Optional, Union

from .detection import Match
from .input import Mouse
from .regionspec import Region
from .verifier import Verifier
from .vision import Finder, TemplateRef


_FIND = "find"
_CLICK = "click"


TemplateResolver = Callable[[str], Any]
RegionResolver = Callable[[str], Optional[Region]]


def _default_template_resolver(name: str):
    """Resolve via PTH. Splits on '.' so disambiguated names like "Confirm.1" still hit."""
    from .utils.paths import PTH
    key = name.split('.')[0]
    return PTH[key]


def _default_region_resolver(name: str) -> Optional[Region]:
    """REGIONS lookup. None on miss so callers fall through to the full frame."""
    from .regions import REGIONS
    return REGIONS.get(name)


def _resolve_ver_target(
    ver: Any, region_resolver: RegionResolver
) -> Region:
    """Coerce ver= into a Region. Accepts Region, (x,y,w,h), name, or name ending in '!'."""
    if isinstance(ver, Region):
        return ver
    if isinstance(ver, (tuple, list)):
        return Region.coerce(ver)
    if isinstance(ver, str):
        key = ver.rstrip("!") if ver.endswith("!") else ver
        resolved = region_resolver(key)
        if resolved is None:
            raise KeyError(f"ver={ver!r}: no region named {key!r}")
        return resolved
    raise TypeError(f"Unsupported ver= type: {type(ver).__name__}")


@dataclass(frozen=True)
class CallSite:
    """Preset-bound call site. Immutable; overrides return new copies."""

    finder: Finder
    mouse: Optional[Mouse] = None
    verifier: Optional[Verifier] = None
    action: str = _FIND
    timeout: float = 5.0
    poll: float = 0.1
    conf: Optional[float] = None
    tsize: Optional[tuple[int, int]] = None
    error_on_miss: bool = False
    template_resolver: TemplateResolver = field(
        default=_default_template_resolver
    )
    region_resolver: RegionResolver = field(
        default=_default_region_resolver
    )
    load_kwargs: dict[str, Any] = field(default_factory=dict)

    def __call__(self, **overrides: Any) -> CallSite:
        """Return a new CallSite with overrides merged. Unknown kwargs flow into load_kwargs."""
        known = {
            "finder", "mouse", "verifier", "action", "timeout", "poll",
            "conf", "tsize", "error_on_miss",
            "template_resolver", "region_resolver",
        }
        cls_args: dict[str, Any] = {}
        extra_load: dict[str, Any] = {}
        for k, v in overrides.items():
            if k == "click":
                if v is True:
                    cls_args["action"] = _CLICK
                elif v is False:
                    cls_args["action"] = _FIND
                else:
                    # click-target tuple - stash for .click_at.
                    extra_load["click_at"] = v
                continue
            if k == "wait":
                # 'wait' maps to timeout; False means 0.
                cls_args["timeout"] = 0.0 if v is False else float(v)
                continue
            if k == "error":
                cls_args["error_on_miss"] = bool(v)
                continue
            if k in known:
                cls_args[k] = v
            else:
                extra_load[k] = v

        new_load = dict(self.load_kwargs)
        new_load.update(extra_load)
        cls_args["load_kwargs"] = new_load
        return replace(self, **cls_args)

    def _resolve(self, name_or_template):
        """Resolve a positional arg into (template, region)."""
        if isinstance(name_or_template, str):
            template = self.template_resolver(name_or_template)
            region = self.region_resolver(name_or_template)
        else:
            template = name_or_template
            region = None
        return template, region

    def find(
        self,
        name: Union[str, TemplateRef],
        region: "Region | tuple | None" = None,
        **overrides: Any,
    ) -> Optional[Match]:
        """Find a template. `name` is a PTH/REGIONS key or a direct template ref."""
        cs = self(**overrides) if overrides else self
        template, resolved_region = cs._resolve(name)
        target_region = region if region is not None else resolved_region

        hit = cs.finder.find(
            template,
            region=target_region,
            conf=cs.conf,
            **cs.load_kwargs,
        )
        if hit is None and cs.error_on_miss:
            raise RuntimeError(
                f"CallSite.find({name!r}): not found "
                f"(region={target_region}, conf={cs.conf})"
            )
        return hit

    def wait(
        self,
        name: Union[str, TemplateRef],
        region: "Region | tuple | None" = None,
        **overrides: Any,
    ) -> Optional[Match]:
        """Poll for a template via Verifier. Honors timeout/poll."""
        cs = self(**overrides) if overrides else self
        if cs.verifier is None:
            raise RuntimeError(
                "CallSite.wait requires a Verifier; construct CallSite "
                "with verifier=Verifier(...)"
            )
        template, resolved_region = cs._resolve(name)
        target_region = region if region is not None else resolved_region

        hit = cs.verifier.wait_for(
            template,
            region=target_region,
            conf=cs.conf,
            timeout=cs.timeout,
            poll=cs.poll,
            **cs.load_kwargs,
        )
        if hit is None and cs.error_on_miss:
            raise RuntimeError(
                f"CallSite.wait({name!r}): timed out after {cs.timeout}s"
            )
        return hit

    def click(
        self,
        name: Union[str, TemplateRef],
        region: "Region | tuple | None" = None,
        **overrides: Any,
    ) -> bool:
        """Click a template via Verifier. Returns True if clicked."""
        cs = self(**overrides) if overrides else self
        if cs.verifier is None:
            raise RuntimeError(
                "CallSite.click requires a Verifier; construct CallSite "
                "with verifier=Verifier(...)"
            )
        template, resolved_region = cs._resolve(name)
        target_region = region if region is not None else resolved_region

        # click_at is consumed here, not forwarded to the template loader.
        load_kw = dict(cs.load_kwargs)
        click_at = load_kw.pop("click_at", None)

        ok = cs.verifier.click_when_found(
            template,
            region=target_region,
            conf=cs.conf,
            timeout=cs.timeout,
            poll=cs.poll,
            click_at=click_at,
            tsize=cs.tsize,
            **load_kw,
        )
        if not ok and cs.error_on_miss:
            raise RuntimeError(
                f"CallSite.click({name!r}): not clicked "
                f"(timed out after {cs.timeout}s)"
            )
        return ok

    def button(
        self,
        name: Union[str, TemplateRef],
        region: "Region | tuple | str | None" = None,
        *,
        ver: Union[Region, tuple, str, None] = None,
        **overrides: Any,
    ) -> bool:
        """`<preset>.button(name, [region], ver=...)`.

        ver targets: Region/tuple snapshot; str ending in '!' resolves to REGIONS[name];
        plain str is a template name (region pulled from REGIONS); None skips verification.
        With ver set, any action routes through Verifier.click_and_verify.
        """
        cs = self(**overrides) if overrides else self

        if isinstance(region, str):
            target_region = cs.region_resolver(region)
        else:
            target_region = region

        if ver is None:
            if cs.action == _CLICK:
                return cs.click(name, region=target_region)
            else:
                hit = (
                    cs.wait(name, region=target_region)
                    if cs.verifier is not None and cs.timeout > 0
                    else cs.find(name, region=target_region)
                )
                return bool(hit)

        if cs.verifier is None:
            raise RuntimeError(
                "CallSite.button(ver=...) requires a Verifier"
            )

        verify_region = _resolve_ver_target(ver, cs.region_resolver)

        template, resolved_region = cs._resolve(name)
        effective_region = target_region if target_region is not None else resolved_region

        load_kw = dict(cs.load_kwargs)
        click_at = load_kw.pop("click_at", None)

        return cs.verifier.click_and_verify(
            template,
            verify_region=verify_region,
            region=effective_region,
            conf=cs.conf,
            timeout=cs.timeout,
            poll=cs.poll,
            click_at=click_at,
            tsize=cs.tsize,
            **load_kw,
        )

    def __getitem__(self, name: str) -> Optional[Match]:
        """`cs["Confirm"]` shorthand for the preset's primary action; click raises (use cs.click explicitly)."""
        if self.action == _CLICK:
            raise NotImplementedError(
                "Use cs.click('name') explicitly when action='click'; "
                "indexing returns a Match, which is the wrong type."
            )
        if self.timeout > 0 and self.verifier is not None:
            return self.wait(name)
        return self.find(name)


@dataclass(frozen=True)
class CallSiteBundle:
    """Alias bundle: loc / click / now / try_click / now_click."""
    loc: CallSite
    click: CallSite
    now: CallSite
    try_click: CallSite
    now_click: CallSite


def build_call_sites(
    finder: Finder,
    mouse: Optional[Mouse] = None,
    verifier: Optional[Verifier] = None,
    *,
    default_conf: Optional[float] = None,
) -> CallSiteBundle:
    """Standard preset bundle: loc (5s wait), click, now (timeout=0), try_click (raise), now_click."""
    base = CallSite(
        finder=finder,
        mouse=mouse,
        verifier=verifier,
        conf=default_conf,
    )
    return CallSiteBundle(
        loc=base,
        click=base(click=True),
        now=base(wait=False),
        try_click=base(click=True, error=True),
        now_click=base(click=True, wait=False),
    )


__all__ = [
    "CallSite",
    "CallSiteBundle",
    "build_call_sites",
    "TemplateResolver",
    "RegionResolver",
]
