# Detection

Phase 2 of the SOLID refactor. **Pure template matching, nothing else.**

## What lives here

| File           | Role                                                  |
| -------------- | ----------------------------------------------------- |
| `types.py`     | `Match` dataclass, `MatchMethod` and `ColorMode` enums |
| `transforms.py`| `to_grayscale`, `to_edges`, `apply_color_mode`         |
| `matcher.py`   | `match_one`, `match_all`                              |

## What does NOT live here

| Concern                               | Owner                                |
| ------------------------------------- | ------------------------------------ |
| Screen capture / region cropping      | Vision + RegionSpec (Phase 3-4)      |
| Coordinate scaling (window vs 1920)   | RegionSpec (Phase 3)                 |
| Template file loading / disk paths    | Vision (Phase 4)                     |
| Mouse movement, clicks                | Input (Phase 5)                      |
| Post-click verification, retries      | Verifier (Phase 6)                   |
| Telemetry side effects                | Caller, via Vision                   |

Detection takes numpy arrays in, returns `Match` objects out. The
coordinates in those `Match` objects are local to the frame that was
passed in. If the frame was a region crop, callers must translate the
match into screen space themselves; that translation is exactly the
RegionSpec job.

## Design rules

1. No global state. No `cls.region`, no `Locate.tsize`, no module-level
   caches. Every call is a pure function of its arguments.
2. No IO. Detection never touches disk, screen, mouse or keyboard.
3. No `params` import. The matcher does not know what `p.WINDOW` is and
   does not need to.
4. Confidence is always normalized to `[0, 1]` regardless of method.
   Callers compare `match.confidence` against `conf` without worrying
   that SQDIFF inverts or that CCOEFF lives in `[-1, 1]`.

## Coexistence with legacy `Locate`

`utils.utils.Locate*` is untouched. The 270+ call sites that use it
keep working. New code (and call sites we migrate one at a time)
imports from `automation.detection` instead. Once every call site
moves, the legacy classes become a thin compat shim and finally go
away.

## Test fixtures

`tests/test_detection.py` exercises the module against synthetic
checkerboard images and a real `ImageAssets/` PNG (self-match). No
screenshot is required; the tests run on any machine with numpy +
opencv-python installed.
