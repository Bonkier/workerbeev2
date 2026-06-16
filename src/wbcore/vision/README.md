# Vision

Phase 4 of the SOLID refactor. **Screen capture, template loading, and
the high-level `Finder` that composes Detection + RegionSpec.**

## What lives here

| File         | Role                                                  |
| ------------ | ----------------------------------------------------- |
| `capture.py` | `CaptureFn` protocol + thin `capture` function       |
| `loader.py`  | `TemplateLoader`: cached cv2.imread + transforms     |
| `finder.py`  | `Finder`: composes Detection + RegionSpec + IO       |

## What is special about this layer

Vision is the **only** part of the pipeline that touches IO at all.
Detection and RegionSpec are arithmetic; Input and Verifier produce
events. Vision reads the screen and reads disk.

That makes it the natural place for a leak: imports of `gui`,
`params`, `cv2.imread`. We hold the leak at arm's length by

1. Taking the capture backend as a **callable parameter** (`CaptureFn`),
   not an imported module. The Windows/X11 backends both happen to
   satisfy the protocol with a one-line adapter.
2. Taking the template loader as a **constructor parameter**. Tests
   pass a `TemplateLoader(prefilled={...})` and never touch disk.
3. Taking the window geometry as a **constructor parameter**. Vision
   does not know what `p.WINDOW` is.

So `automation.vision` is importable in pytest without a display, a
game window, or the bridge plugin. The tests prove it.

## Public API

```python
from wbcore.vision import Finder, TemplateLoader, capture, CaptureFn

# At app startup:
finder = Finder(
    window=WindowGeometry(*p.WINDOW),
    backend=lambda rect: gui.screenshot(region=rect.as_tuple()),
    loader=TemplateLoader(),
    on_match=telemetry.match,    # optional
)

# At call sites:
hit = finder.find("ImageAssets/UI/Confirm.png", region=REG["confirm"], conf=0.9)
if hit:
    print(hit.center)   # FHD coordinates, ready for the Input layer
```

`Finder.find` returns a `detection.Match` whose coordinates are in
**FHD space**, lifted via `regionspec.lift_match_to_fhd`. That is the
same coordinate space the click helpers expect, so the migration of a
single call site is mechanical:

```python
# Legacy
res = LocateRGB.locate(PTH["confirm"], region=REG["confirm"], conf=0.9)
if res:
    win_click(gui.center(res))

# New
hit = finder.find(PTH["confirm"], region=REG["confirm"], conf=0.9)
if hit:
    win_click(hit.center)
```

## What does NOT live here

- **Mouse input.** Phase 5 (Input).
- **Retry-until-found loops.** Phase 6 (Verifier).
- **Hardcoded regions, slot positions, click targets.** Those are
  authored constants; they should not move at all, only be referenced
  through the new types.

## Coexistence with legacy

The legacy `Locate*` classes and the 270+ call sites that use them
keep working. New code uses `Finder`. Migration happens one call site
at a time once Phases 5-6 land.
