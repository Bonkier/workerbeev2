# RegionSpec

Phase 3 of the SOLID refactor. **Pure coordinate translation.**

## Two coordinate spaces

| Space            | Type            | Where it lives                                |
| ---------------- | --------------- | --------------------------------------------- |
| FHD reference    | `Region`, `tuple[int,int]` | Authored regions, click targets, hardcoded slots, template captures |
| Screen pixels    | `ScreenRect`, `tuple[int,int]` | Screen-capture backend input, mouse-event coordinates |

The macro thinks in FHD. The OS thinks in screen pixels. RegionSpec is
the bridge. By giving the two spaces distinct types, we make passing
the wrong space into the wrong function a static error (or, in
duck-typed Python, a much louder runtime mismatch) instead of a silent
2x scale bug.

## What lives here

| File           | Role                                                        |
| -------------- | ----------------------------------------------------------- |
| `types.py`     | `Region`, `ScreenRect`, `WindowGeometry`, `FHD_WIDTH/HEIGHT` |
| `translate.py` | `region_to_screen`, `point_fhd_to_screen`, `point_screen_to_fhd`, `lift_match_to_fhd`, `scale_size` |

## What does NOT live here

- **Screen capture.** That is the Vision layer (Phase 4).
- **Window discovery.** The Windows/X11 backends own `set_window()` and
  produce a `WindowGeometry` value; we just consume one.
- **Mouse input.** That is the Input layer (Phase 5).
- **Detection.** Lives in `automation.detection`; it is also pure.
- **`p.WINDOW`.** RegionSpec is parameter-free. Callers construct a
  `WindowGeometry` from whatever source they have (legacy `p.WINDOW`,
  a test fixture, a multi-monitor backend).

## Why distinct types

The previous code shape was: every region was a 4-tuple, every point
was a 2-tuple, and the type system could not distinguish the
authoring-space `(20, 30, 40, 50)` from the screen-space
`(2580, 1230, 80, 100)`. The `comp = p.WINDOW[2] / 1920` line was
copy-pasted into 12 call sites. Each copy was an opportunity to forget
the inverse, to apply scale twice, or to mix the window origin into
the scaled size. Making `Region` and `ScreenRect` distinct frozen
dataclasses kills that whole class of bug:

```python
gui.screenshot(region)             # static error: gui wants screen px
gui.screenshot(region_to_screen(region, window))   # explicit and obvious
```

## Coexistence with legacy

Nothing in `utils.utils` changes yet. The new module is purely
additive. Call sites move over one at a time once Phase 4 (Vision)
provides a screenshot function that takes a `Region`.
