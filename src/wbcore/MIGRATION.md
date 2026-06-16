# Migration Playbook

How to move individual call sites from legacy `Locate*` / `win_*` to
the new SOLID pipeline. The legacy code is untouched; this is for
people opting in one file at a time.

## One-time setup

Once per bot startup (e.g. at the top of `bot.py:execute_me` after
`gui.set_window()` is called):

```python
from wbcore.live import live_call_sites

finder, mouse, verifier, cs = live_call_sites(
    prefilled_templates=PTH,        # optional pre-seed
)
# cs is a CallSiteBundle: cs.loc / cs.click / cs.now / cs.try_click / cs.now_click
```

If you don't want the preset bundle, use `live_pipeline()` instead;
it returns just `(finder, mouse, verifier)`.

That single call:
- reads `params.WINDOW` -> `WindowGeometry`
- picks the right OS backend by platform
- wires `telemetry.match` into `Finder.on_match`
- pre-seeds the template cache from `PTH`
- builds the legacy-alias bundle (loc / click / now / try_click / now_click)

After that, the returned objects are the entire surface area the
migrated code needs.

## Migration mapping (legacy -> new)

| Legacy                                          | New                                                  |
| ----------------------------------------------- | ---------------------------------------------------- |
| `LocateRGB.check(t, region=R, click=True, wait=5)` | `verifier.click_when_found(t, region=R, timeout=5)` |
| `LocateRGB.check(t, region=R, wait=5)`            | `verifier.wait_for(t, region=R, timeout=5) is not None` |
| `LocateRGB.check(t, region=R, click=(x, y), wait=5)` | `verifier.click_when_found(t, region=R, click_at=(x, y), timeout=5)` |
| `LocateRGB.locate(t, region=R)`                   | `finder.find(t, region=R)`                          |
| `LocateRGB.try_locate(t, region=R)`               | `hit = finder.find(t, region=R); assert hit` (caller raises) |
| `LocateRGB.locate_all(t, region=R, threshold=8)`  | `finder.find_all(t, region=R, nms_threshold=8)`     |
| `LocateGray.check(...)`                           | Build a `gray_finder` with `color_mode=ColorMode.GRAY` |
| `LocateEdges.check(...)`                          | Build an `edges_finder` with `color_mode=ColorMode.EDGES` |
| `win_click((x, y), tsize=(5,5))`                  | `mouse.click((x, y), tsize=(5, 5))`                 |
| `win_click()` (click in place)                    | `mouse.click()`                                     |
| `win_moveTo((x, y))`                              | `mouse.move_to((x, y))`                             |
| `win_dragTo((x, y))`                              | `mouse.drag_to((x, y))`                             |
| `win_get_position()`                              | `mouse.position()`                                  |
| `screenshot(region=(x, y, w, h))`                 | `capture(Region(x, y, w, h), window, backend)` (rare; use Finder instead) |

## Worked examples

### 1. Click-when-found (the dominant pattern)

```python
# Legacy
if LocateRGB.check(PTH["Confirm"], region=REG["confirm"],
                   click=True, wait=5, conf=0.9):
    logging.info("confirmed")

# New (option A: legacy tuple shape; Finder coerces automatically)
if verifier.click_when_found(PTH["Confirm"], region=REG["confirm"],
                              conf=0.9, timeout=5):
    logging.info("confirmed")

# New (option B: typed Region for cleaner downstream code)
from wbcore.regions import REGIONS
if verifier.click_when_found(PTH["Confirm"], region=REGIONS["confirm"],
                              conf=0.9, timeout=5):
    logging.info("confirmed")
```

Both forms work. Option A means migration is literally
`LocateRGB.check(...)` -> `verifier.click_when_found(...)` with no
other change; `region=REG["confirm"]` keeps working because
`Finder.find` coerces tuples via `Region.coerce`. Option B is the
preferred shape for code that reads the result downstream.

### 2. Click at a fixed coordinate after finding

```python
# Legacy (used in THRILL_FAIL sequence)
LocateRGB.check(PTH["ClaimInvert"], click=(1315, 818), wait=2)

# New
verifier.click_when_found(
    PTH["ClaimInvert"], click_at=(1315, 818), timeout=2,
)
```

### 3. Wait without clicking

```python
# Legacy
if LocateRGB.check(PTH["loading"], region=REG["loading"], wait=10):
    handle_load_screen()

# New (region tuple accepted directly)
if verifier.wait_for(PTH["loading"],
                     region=REG["loading"],
                     timeout=10) is not None:
    handle_load_screen()
```

### 4. Multi-template scan

```python
# Legacy
boxes = LocateGray.locate_all(
    PTH[name], image=mask, region=(0, 820, 1920, 100),
    threshold=20, comp=comp, conf=0.8,
)

# New (with a gray finder)
gray_finder = Finder(
    window=window,
    backend=adapter,
    loader=loader,
    color_mode=ColorMode.GRAY,
)
hits = gray_finder.find_all(
    PTH[name], region=Region(0, 820, 1920, 100),
    conf=0.8, nms_threshold=20,
    frame=mask,       # explicit frame -> skips capture
    comp=comp,        # template scale kwarg passes through to loader
)
```

### 5. Locate returning the box for downstream click

```python
# Legacy
res = LocateRGB.locate(PTH["Confirm"], region=REG["confirm"], conf=0.9)
if res is not None:
    win_click(gui.center(res))

# New (tuple shape accepted; hit.center replaces gui.center(res))
hit = finder.find(PTH["Confirm"], region=REG["confirm"], conf=0.9)
if hit is not None:
    mouse.click(hit.center)
```

### 6. Color-mode-specific finders

The legacy code had three classes (`LocateRGB`, `LocateGray`,
`LocateEdges`). Under the new pipeline you build three Finders, one
per color mode, and share the rest of the wiring:

```python
from wbcore.detection import ColorMode
from wbcore.live import live_pipeline
from wbcore.vision import Finder

finder_rgb, mouse, verifier = live_pipeline(prefilled_templates=PTH)

# Reuse the loader, backend and window; only the color_mode differs.
finder_gray = Finder(
    window=finder_rgb.window,
    backend=finder_rgb.backend,
    loader=finder_rgb.loader,
    on_match=finder_rgb.on_match,
    color_mode=ColorMode.GRAY,
)
finder_edges = Finder(
    window=finder_rgb.window,
    backend=finder_rgb.backend,
    loader=finder_rgb.loader,
    on_match=finder_rgb.on_match,
    color_mode=ColorMode.EDGES,
)
```

## Preset aliases (legacy now / click / try_click / now_click / loc)

The legacy code in `utils.utils` exposes module-level singletons:

```python
# Legacy
from wbcore.utils.utils import now, click, try_click, now_click, loc
now("Confirm")               # one-shot find, no wait
click("Start")               # find + click with default 5s wait
try_click("ConfirmTeam")     # click + raise on miss
now_click("EventEffect")     # click with timeout=0
loc("Confirm")               # find with default 5s wait, no click
```

Under the new pipeline these become methods on a `CallSiteBundle`:

```python
# New
finder, mouse, verifier, cs = live_call_sites(prefilled_templates=PTH)

cs.now.find("Confirm")            # equivalent to legacy now("Confirm")
cs.click.click("Start")           # equivalent to legacy click("Start")
cs.try_click.click("ConfirmTeam") # equivalent to legacy try_click("ConfirmTeam")
cs.now_click.click("EventEffect") # equivalent to legacy now_click("EventEffect")
cs.loc.wait("Confirm")            # equivalent to legacy loc("Confirm")
```

Each `cs.<preset>` is a `CallSite`. The `.find` / `.wait` / `.click`
methods take a template name and look up `PTH[name]` + `REGIONS[name]`
automatically -- matching the legacy one-arg shape exactly. Per-call
overrides chain via `__call__`:

```python
# Legacy
click("Confirm", conf=0.85, wait=3)

# New
cs.click(conf=0.85, wait=3).click("Confirm")
```

If you prefer the explicit `verifier.click_when_found(...)` shape for
new code, that still works -- the preset is purely sugar for the
mechanical migration of code that already uses the legacy aliases.

### Migration table for preset call sites

| Legacy                          | New                                     |
| ------------------------------- | --------------------------------------- |
| `now("Confirm")`                | `cs.now.find("Confirm")`                |
| `click("Confirm")`              | `cs.click.click("Confirm")`             |
| `try_click("Confirm")`          | `cs.try_click.click("Confirm")`         |
| `now_click("Confirm")`          | `cs.now_click.click("Confirm")`         |
| `loc("Confirm")`                | `cs.loc.wait("Confirm")`                |
| `now("Confirm.1")`              | `cs.now.find("Confirm.1")` (handles legacy dotted names) |
| `click("X", region=R)`          | `cs.click.click("X", region=R)`         |
| `click("X", click=(1690, 897))` | `cs.click(click=(1690, 897)).click("X")` (chain the override) |
| `now("X", conf=0.85)`           | `cs.now(conf=0.85).find("X")`           |
| `loc.button("X")`               | `cs.loc.button("X")`                    |
| `click.button("X")`             | `cs.click.button("X")`                  |
| `try_click.button("X")`         | `cs.try_click.button("X")`              |
| `now.button("X")`               | `cs.now.button("X")`                    |
| `now_click.button("X")`         | `cs.now_click.button("X")`              |
| `click.button("X", ver="Y!")`   | `cs.click.button("X", ver="Y!")` (verified click) |
| `click.button("X", ver=(x,y,w,h))` | `cs.click.button("X", ver=(x,y,w,h))` |

### Verified clicks (`ver=`)

The legacy `<preset>.button(name, ver=...)` flow snapshots a region
before clicking and watches it for change. If unchanged after the
post-click wait, it retries up to 3 times. `CallSite.button` preserves
this exactly, delegating to `Verifier.click_and_verify` under the hood.

Three accepted shapes for `ver=` (all match the legacy spelling):

- `ver=Region(...)` or `ver=(x, y, w, h)` -> raw rectangle in FHD coords.
- `ver="Confirm"` -> look up `REGIONS["Confirm"]`.
- `ver="something!"` -> strip the `!` suffix, then look up.

The `.find / .wait / .click` choice in the new spelling is explicit;
the legacy code had it implicit in which alias you picked. Pick the
new method by what behavior you actually want:

- `.find` -> single attempt, no retry, no click. Returns Match|None.
- `.wait` -> poll Verifier on a schedule. Returns Match|None.
- `.click` -> wait + click. Returns True/False.

## Things that look like they need migration but do not

- **Hardcoded slot positions** (`_THRILL_FOCUSED_HARDCODED_SLOTS`,
  chain bar geometry, etc). These are FHD constants and stay where
  they are. They become `mouse.click(slot)` calls at the migration site.
- **`p.WINDOW` reads inside the legacy backend modules**
  (`os_windows_backend`, `os_x11_backend`). Those are window
  discovery internals; the new code never touches them.
- **`PTH` dict construction**. The path map stays. It is passed to
  `live_pipeline(prefilled_templates=PTH)` to seed the cache.

## Safety considerations

1. **Migrate one call site at a time.** The legacy `Locate*` classes
   still work; nothing is force-removed.
2. **Verify visually after migration.** Run the macro on a non-Thrill
   path (Lux Cavation is the safest) and confirm telemetry events
   still show up in the overlay. The Finder's `on_match` callback
   feeds the same vision channel the legacy code did.
3. **PTH is built at startup.** Any template change still requires a
   relaunch. The new TemplateLoader cache respects this.
4. **Do not migrate THRILL paths first.** Thrill is the active feature
   and is the riskiest place to introduce a regression. Migrate
   stable paths (Confirm dialogs, loading-screen waits, SAIKAI Normal
   floors) before touching anything Thrill-specific.

## Telemetry parity check

Migrated call sites should produce the same `match` events the legacy
code did. To verify in dev:

```python
# Quick sanity at startup:
finder, _, _ = live_pipeline(prefilled_templates=PTH)
assert finder.on_match is not None, "telemetry not wired"
```

After migrating a call site, walk through the path on screen and
confirm overlay highlights appear at the same templates the legacy
code highlighted.

## Rollback

A migrated call site can be reverted by restoring the legacy line
verbatim. The legacy classes never go away (until the last call site
moves, which can take as long as it takes). There is no flag day.
