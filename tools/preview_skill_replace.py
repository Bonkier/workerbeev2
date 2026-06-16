# SPDX-License-Identifier: GPL-3.0-or-later
"""Offscreen PNG render of the Mirror Dungeon SHOP: SKILL REPLACEMENT card."""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--out", default="tools/preview_skill_replace.png",
        help="output PNG path (default: tools/preview_skill_replace.png)",
    )
    args = parser.parse_args()

    repo = Path(__file__).resolve().parents[1]
    for p in (repo, repo / "src"):
        if str(p) not in sys.path:
            sys.path.insert(0, str(p))

    # Offscreen Qt: never paint to a real window.
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

    from PySide6.QtCore import QSize
    from PySide6.QtGui import QPixmap
    from PySide6.QtWidgets import QApplication

    app = QApplication.instance() or QApplication(sys.argv)

    # Match the live page's dark background.
    try:
        from gui_v2.themes import apply_saved_theme
        apply_saved_theme()
    except Exception:
        pass

    # Replicate the launcher's global QSS.
    try:
        from gui_v2.style import qss
        app.setStyleSheet(qss())
    except Exception:
        pass

    from gui_v2.mirror_dungeon_page import MirrorDungeonPage

    # Build inside a real QMainWindow so QSS cascade + parenting match live.
    from PySide6.QtWidgets import QMainWindow
    page = MirrorDungeonPage()
    page.setObjectName("root")

    win = QMainWindow()
    win.setCentralWidget(page)
    win.resize(900, 1800)
    win.show()
    app.processEvents()

    # Walk up to the constructor-built Card; rebuilding would detach signals.
    card = getattr(page, "_skill_details", None)
    while card is not None and type(card).__name__ != "Card":
        card = card.parentWidget()
    if card is None:
        card = page  # fallback
    card.adjustSize()
    app.processEvents()

    # grab() uses the real-screen paint pipeline; render() comes out blank
    # under the offscreen platform.
    pm = card.grab()

    out_path = repo / args.out if not Path(args.out).is_absolute() else Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    if not pm.save(str(out_path), "PNG"):
        print(f"failed to save: {out_path}", file=sys.stderr)
        return 1
    print(f"wrote {out_path}  {pm.width()}x{pm.height()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
