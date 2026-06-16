# Verifier

Phase 6 of the SOLID refactor (final phase). **Retry-until-found and
click composition.**

## What lives here

| File          | Role                                                       |
| ------------- | ---------------------------------------------------------- |
| `verifier.py` | `Verifier` class: `wait_for` + `click_when_found`         |

## Public API

```python
from wbcore.verifier import Verifier

verifier = Verifier(finder=finder, mouse=mouse)

# Wait for a template to appear, get the Match back (no click).
hit = verifier.wait_for(PTH["confirm"], region=REG["confirm"], timeout=5)

# Wait + click in one call. Returns True if it clicked.
ok = verifier.click_when_found(PTH["confirm"], region=REG["confirm"], timeout=5)

# Wait + click at a fixed FHD point (legacy `check(click=(x, y))`).
ok = verifier.click_when_found(
    PTH["confirm"], region=REG["confirm"], timeout=5,
    click_at=(1690, 897),
)
```

## Why this is its own layer

The legacy `Locate.check` did six things in one method: locate,
report telemetry, click, jitter, retry, raise on failure. Each of
those is a separate axis of "what changed if the test fails":

- Locate -> Vision
- Telemetry -> Finder's `on_match` callback
- Click -> Input (`Mouse`)
- Jitter -> Mouse's `tsize` arg
- Retry -> **Verifier**
- Raise on failure -> caller's choice (we return None/False)

By splitting them the call site is honest about what it wants. A
function that "waits for X to appear" is `wait_for`. A function that
"clicks X when X appears" is `click_when_found`. A function that
"clicks X if X is there right now, else moves on" is just
`finder.find(...)` followed by `mouse.click(hit.center)`. None of
those have to retry, schedule, or own a sleep.

## What does NOT live here

- **Decision making.** Verifier polls; it does not branch on which
  template to look for next. Bot logic stays in `bot.py`.
- **Failure escalation.** `Locate.check(error=True)` would raise
  RuntimeError on timeout. We return None/False and let the caller
  decide. (Bot policy varies by call site; embedding it here would
  rebuild the conflation we just disentangled.)
- **Pause/stop integration.** The legacy `pause()` machinery lives
  in `utils.utils`; it stays put for now. Hooking a `should_stop`
  callable into Verifier is a clean follow-up.

## Sleep injection

`Verifier(..., sleep=lambda _: None)` runs at zero wall time. Tests
use this to exercise the poll schedule without burning a second per
case.

## Coexistence with legacy

Nothing in `utils.utils` changes. Migration is one call site at a
time. Typical legacy -> new mapping:

```python
# Legacy
if LocateRGB.check(PTH["confirm"], region=REG["confirm"], click=True, wait=5):
    ...

# New
if verifier.click_when_found(PTH["confirm"], region=REG["confirm"], timeout=5):
    ...
```
