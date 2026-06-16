# tools/

Standalone helper scripts for the SOLID-pipeline migration.

| Script                  | Purpose                                                          |
| ----------------------- | ---------------------------------------------------------------- |
| `audit_migrations.py`   | Scan `src/wbcore` for legacy `Locate*` / `win_*` call sites and print a per-line migration suggestion. |
| `capture_fixture.py`    | Save a screenshot of the live game window as a `.npy` test fixture for use in regression tests. |

## Quick start

```sh
# Get a checklist of every call site that needs to be migrated.
python tools/audit_migrations.py

# Save it as CSV for spreadsheet tracking.
python tools/audit_migrations.py --csv > migrations.csv

# Audit a single file (useful when working through one module at a time).
python tools/audit_migrations.py --file src/wbcore/lux.py

# Save a real-game frame as a test fixture (requires live game window).
python tools/capture_fixture.py lux_confirm_dialog
python tools/capture_fixture.py confirm_button --region 1605 870 200 80
```

## What is NOT in tools/

- The actual SOLID modules. Those live under `src/wbcore/`.
- The PyInstaller spec. That stays at the repo root.
- The legacy game state migrations. Those are not in scope.

These scripts have no side effects beyond reading source files and
(for `capture_fixture.py`) writing one `.npy` + `.png` per invocation.
The auditor in particular is safe to run any time, it modifies
nothing.
