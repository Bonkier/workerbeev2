# SPDX-License-Identifier: GPL-3.0-or-later
"""Fetch the status/damage-type icons the gift pickers tab by.

The bundled keyword tabs are in-game crops with the keyword's name already
printed inside them, so the picker ends up showing the word twice - once baked
into the image and once as the tab's own label. The wiki publishes each status
as a clean transparent icon; this pulls those into ImageAssets/keywordart.

Skips what it already has, so re-running only fetches what is missing.
"""
from __future__ import annotations

import os
import sys
import time
import urllib.parse

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from fetch_gift_art import UA, WIKI, _get   # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "ImageAssets", "keywordart")

# keyword -> the wiki file name to try, best first. "keywordless" has no
# status of its own and keeps the bundled tab.
WANTED = {
    "burn": ("Burn.png",),
    "bleed": ("Bleed.png",),
    "tremor": ("Tremor.png",),
    "rupture": ("Rupture.png",),
    "sinking": ("Sinking.png",),
    "poise": ("Poise.png",),
    "charge": ("Charge.png",),
    "slash": ("Slash.png", "Slash_Damage.png", "Attack_Type_Slash.png"),
    "pierce": ("Pierce.png", "Pierce_Damage.png", "Attack_Type_Pierce.png"),
    "blunt": ("Blunt.png", "Blunt_Damage.png", "Attack_Type_Blunt.png"),
    # Sin affinities: the Thread Luxcavation rotation is keyed to these.
    "wrath": ("Wrath.png",),
    "lust": ("Lust.png",),
    "sloth": ("Sloth.png",),
    "gluttony": ("Gluttony.png",),
    "gloom": ("Gloom.png",),
    "pride": ("Pride.png",),
    "envy": ("Envy.png",),
}


def _url_for(filename: str) -> str:
    q = {"action": "query", "titles": "File:" + filename,
         "prop": "imageinfo", "iiprop": "url", "format": "json"}
    data = _get(f"{WIKI}/api.php?" + urllib.parse.urlencode(q))
    for page in (data.get("query", {}).get("pages") or {}).values():
        for info in page.get("imageinfo") or []:
            if info.get("url"):
                return info["url"].split("?")[0]
    return ""


def main() -> int:
    os.makedirs(OUT, exist_ok=True)
    got = missed = skipped = 0
    for kw, candidates in WANTED.items():
        dest = os.path.join(OUT, kw + ".png")
        if os.path.exists(dest) and os.path.getsize(dest) > 0:
            skipped += 1
            continue
        url = ""
        for name in candidates:
            url = _url_for(name)
            if url:
                print(f"  {kw:12} <- {name}")
                break
        if not url:
            print(f"  ! {kw}: no wiki icon for any of {candidates}")
            missed += 1
            continue
        try:
            blob = _get(url, binary=True)
        except Exception as exc:                      # network / 404
            print(f"  ! {kw}: {exc}")
            missed += 1
            continue
        with open(dest, "wb") as fh:
            fh.write(blob)
        got += 1
        time.sleep(0.05)                              # be gentle on the wiki

    print(f"\ndownloaded {got}, already had {skipped}, missing {missed}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
