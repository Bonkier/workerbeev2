# The SOLID Pipeline

The WorkerBee detection-click loop is split into five pure-ish layers,
each in its own submodule of `src/wbcore/`. They compose left to
right; nothing on the left ever imports anything on its right.

```
RegionSpec  ->  Detection  ->  Vision  ->  Input  ->  Verifier
   pure         pure          IO here   IO here    composer
```

| Phase | Module        | Responsibility                                     | Test count |
| ----- | ------------- | -------------------------------------------------- | ---------- |
| 2     | `detection`   | Pure template matching (numpy/cv2 only)            | 12         |
| 3     | `regionspec`  | Coordinate translation FHD <-> screen pixels        | 26         |
| 4     | `vision`      | Screen capture + template loading + Finder         | 18         |
| 5     | `input`       | FHD-aware mouse driving via injected backend       | 16         |
| 6     | `verifier`    | Retry-until-found + click composition              | 14         |
| 7     | `pipeline`    | Production factory + BackendAdapter                | 17         |
| 8     | `live`        | Boundary layer binding pipeline to legacy globals  | 5          |
| 9     | `regions`     | Typed REGIONS dict + as_region helper + Region.coerce on Finder | 20 |
| 10    | `callsite`    | Preset wrappers (loc/click/now/try_click/now_click) for legacy alias migration | 25 |
| 11    | `verifier.click_and_verify` + `callsite.button` | Verified-click flow (legacy `.button(ver=...)`) | 13 |
| 12    | `utils.utils` shim layer | Legacy `Locate*` / `LocatePreset` / `win_*` / `screenshot` route through the new pipeline; **zero call-site changes in live `.py` files** | 17 |
| Vision usage tracker | (inside Phase 4) | Opt-in template-usage counter for asset audit | 5 |
| `tools/`     | Migration tooling | Static auditor + fixture capture helper            | 21         |
| **Total** |           |                                                    | **209**    |

All 209 tests run in ~0.8s. No display, no game window, no
`os_windows_backend`, no `bridge/`. Any machine with `numpy`,
`opencv-python` and `pytest` can run them.

For the migration playbook (every legacy call pattern -> new
equivalent), see [`MIGRATION.md`](MIGRATION.md). For tooling that helps
the migration (static auditor, fixture capture), see
[`../tools/README.md`](../../tools/README.md).

## How a single call site decomposes

The legacy spelling:

```python
if LocateRGB.check(PTH["confirm"], region=REG["confirm"],
                   click=True, wait=5, conf=0.9):
    ...
```

does six things at once: capture, scale, find, lift coords, click,
retry. After the refactor:

```python
# At app startup (once):
from wbcore.pipeline import build_pipeline
from wbcore.regionspec import WindowGeometry
from wbcore.utils import os_windows_backend as gui  # or os_x11_backend

finder, mouse, verifier = build_pipeline(
    window=WindowGeometry(*p.WINDOW),
    gui=gui,
    on_match=telemetry.match,    # optional
)

# At call site:
if verifier.click_when_found(PTH["confirm"], region=REG["confirm"],
                              conf=0.9, timeout=5):
    ...
```

`build_pipeline` constructs one `BackendAdapter` and uses it for both
capture and input, so a single `gui` module reference propagates
through the whole pipeline. The adapter satisfies `CaptureFn` (via
`__call__`) and `InputBackend` (via the four mouse methods), and
handles the legacy method-name shims (`moveTo` -> `move_to`,
`get_position` -> `position`, screenshot tuple unpacking).

The verifier owns retry. The Finder owns capture + match + lift. The
Mouse owns scale + click. Each is independently testable; each has a
fake; each has no global state.

## What is NOT migrated (intentionally)

- The 270+ existing legacy call sites. They keep using `Locate*` from
  `utils.utils` until somebody migrates them one at a time. The new
  modules are purely additive.
- `os_windows_backend` and `os_x11_backend`. They already satisfy the
  shape we need; production code instantiates Vision and Input with
  them directly.
- `p.WINDOW`, `p.LIMBUS_NAME`, the rest of params. These are app-level
  state that callers translate into a `WindowGeometry` at app start.
- Hardcoded regions/click targets/slot positions in `bot.py`,
  `battle.py`, `shop.py`. Those are authored constants; they should be
  expressed as `Region` / FHD-tuples but not moved.

## Migration recipe

For a single legacy `Locate*.check(...)` call:

1. Decide: does it click? -> `verifier.click_when_found`. Does it
   retry but never click? -> `verifier.wait_for`. Single attempt? ->
   `finder.find`.
2. Wrap the template path with the same `PTH[...]` lookup; the new
   API accepts strings, Paths, and ndarrays identically.
3. Convert the region tuple into `Region(*tuple)` (or reach for the
   typed constant once `REG` itself is migrated to use `Region`).
4. Replace any `gui.center(res)` + `win_click(...)` afterwards with
   nothing: the new API gives you a `Match` in FHD coords, so click
   targets are `hit.center` and clicks go through `mouse.click(...)`.

That is the entire mechanical change. Nothing should think harder
than a 1:1 swap.

## Layer rules

- **No layer ever imports `params`.** All app state arrives as
  constructor parameters.
- **Detection and RegionSpec are pure.** They never read disk, never
  read the screen, never sleep.
- **Vision and Input are the only IO layers.** Both accept their IO
  backend as a callable so tests can swap a fake.
- **Verifier sleeps.** That is the only place a wall-clock wait
  belongs. Sleep is injected so tests run instantly.
- **Telemetry is a callback, not an import.** Finder takes an optional
  `on_match`; Verifier inherits it transitively. Nothing in the
  pipeline imports `automation.utils.telemetry`.

## File layout

```
src/wbcore/
    detection/
        __init__.py
        README.md
        types.py        # Match, MatchMethod, ColorMode
        transforms.py   # to_grayscale, to_edges, apply_color_mode
        matcher.py      # match_one, match_all
    regionspec/
        __init__.py
        README.md
        types.py        # Region, ScreenRect, WindowGeometry
        translate.py    # region_to_screen, lift_match_to_fhd, etc.
    vision/
        __init__.py
        README.md
        capture.py      # CaptureFn protocol, capture()
        loader.py       # TemplateLoader
        finder.py       # Finder
    input/
        __init__.py
        README.md
        types.py        # InputBackend protocol
        mouse.py        # Mouse
    verifier/
        __init__.py
        README.md
        verifier.py     # Verifier (wait_for, click_when_found)
    pipeline.py         # BackendAdapter + build_pipeline factory
    live.py             # Boundary layer: live_pipeline / live_call_sites
    regions.py          # REGIONS dict + as_region (typed wrappers over REG)
    callsite.py         # CallSite preset + build_call_sites bundle
    MIGRATION.md        # Per-call-site playbook

tests/
    __init__.py
    conftest.py         # Adds repo root to sys.path
    test_detection.py
    test_regionspec.py
    test_vision.py
    test_input.py
    test_verifier.py
    test_pipeline.py
    test_live.py
    test_regions.py
    test_callsite.py
    test_click_and_verify.py
    test_legacy_shim.py
    test_audit_migrations.py

tools/
    README.md
    audit_migrations.py  # Static migration-suggestion scanner
    capture_fixture.py   # Save live screenshots as .npy fixtures
```

209 tests, ~0.8s. Run with:

```
pytest tests/
```

from the repo root.
