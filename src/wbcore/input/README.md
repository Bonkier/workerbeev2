# Input

Phase 5 of the SOLID refactor. **FHD-aware mouse driving.**

## What lives here

| File        | Role                                                   |
| ----------- | ------------------------------------------------------ |
| `types.py`  | `InputBackend` protocol (move_to / click / drag_to / position) |
| `mouse.py`  | `Mouse`: FHD-aware wrapper around an InputBackend      |

## Public API

```python
from wbcore.input import Mouse

mouse = Mouse(
    window=WindowGeometry(*p.WINDOW),
    backend=gui,            # os_windows_backend or os_x11_backend
)

mouse.click((1315, 818))                         # FHD coords
mouse.click(hit.center, tsize=(5, 5))            # tsize is FHD too
mouse.move_to((960, 540))                        # center of FHD canvas
mouse.drag_to((100, 100))
where = mouse.position()                          # returns FHD coords
```

## Why this layer is small

The mouse layer is thin on purpose. The legacy `win_click`,
`win_moveTo`, `win_dragTo`, `win_get_position` helpers in
`utils.utils` together amount to about 30 lines of arithmetic plus
delegation; this module is the same 30 lines reorganized so the
arithmetic lives in RegionSpec and the IO lives behind a swappable
protocol.

The real win is **testability**: the click pipeline can be exercised
without a mouse, a monitor, or pyautogui. A `RecordingInputBackend`
in the tests records the screen-pixel calls it received, which is
enough to assert that FHD translation and `tsize` scaling are
correct under any window geometry.

## What does NOT live here

- **Retry-until-found.** That is the Verifier (Phase 6).
- **Where to click.** That is the Vision Finder (already extracted).
- **Window discovery.** The backend stays where it is; we just
  consume its protocol.

## Backend adapter

The Windows backend already exposes the right shape. A production
adapter is two lines:

```python
import wbcore.utils.os_windows_backend as _gui

class _BackendAdapter:
    move_to = staticmethod(_gui.moveTo)
    click = staticmethod(_gui.click)
    drag_to = staticmethod(_gui.dragTo)
    position = staticmethod(_gui.get_position)

mouse = Mouse(window, _BackendAdapter())
```

(In practice the existing module already satisfies the protocol via
duck typing; the adapter is only needed if method names diverge.)
