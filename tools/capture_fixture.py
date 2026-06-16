# SPDX-License-Identifier: GPL-3.0-or-later
"""Save a screenshot of the live game window as a test fixture.

Writes a .npy frame plus a .png preview via the live pipeline, so the
fixture matches what a real Finder call sees.

    python tools/capture_fixture.py FIXTURE_NAME [--region X Y W H]

Requires the game window open with p.WINDOW set; run from the repo root.
"""
from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

import cv2
import numpy as np


def _setup_paths() -> Path:
    """Add repo root to sys.path so `src.wbcore` resolves."""
    here = Path(__file__).resolve()
    repo = here.parent.parent
    if str(repo) not in sys.path:
        sys.path.insert(0, str(repo))
    return repo


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "name",
        help="fixture name (will be saved as <name>.npy + <name>.png)",
    )
    parser.add_argument(
        "--region", nargs=4, type=int, metavar=("X", "Y", "W", "H"),
        default=None,
        help="FHD-reference region (default: full 1920x1080)",
    )
    parser.add_argument(
        "--out", type=Path, default=None,
        help="output directory (default: <repo>/tests/fixtures/)",
    )
    parser.add_argument(
        "--no-png", action="store_true",
        help="skip the .png preview write",
    )
    args = parser.parse_args(argv)

    repo = _setup_paths()
    out_dir = args.out or (repo / "tests" / "fixtures")
    out_dir.mkdir(parents=True, exist_ok=True)

    npy_path = out_dir / f"{args.name}.npy"
    png_path = out_dir / f"{args.name}.png"

    # Needs the bridge + a discovered window.
    try:
        from src.wbcore.live import live_pipeline
        from src.wbcore.regionspec import Region
    except Exception as ex:
        print(f"error: failed to import live pipeline: {ex}", file=sys.stderr)
        print(
            "Make sure the game window is open and `gui.set_window()` has been "
            "called (the bot startup does this automatically).",
            file=sys.stderr,
        )
        return 2

    logging.basicConfig(level=logging.INFO, format="%(message)s")

    try:
        finder, _mouse, _verifier = live_pipeline()
    except Exception as ex:
        print(f"error: live_pipeline() failed: {ex}", file=sys.stderr)
        return 3

    region = Region(*args.region) if args.region else Region.full()

    # Reuse the Finder's capture backend so the frame matches a live find().
    from src.wbcore.vision import capture
    frame = capture(region, finder.window, finder.backend)
    if frame is None or not isinstance(frame, np.ndarray):
        print("error: capture returned no frame", file=sys.stderr)
        return 4

    np.save(npy_path, frame)
    print(f"wrote {npy_path}  shape={frame.shape}  dtype={frame.dtype}")

    if not args.no_png:
        if cv2.imwrite(str(png_path), frame):
            print(f"wrote {png_path} (preview)")
        else:
            print(f"warning: failed to write preview {png_path}", file=sys.stderr)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
