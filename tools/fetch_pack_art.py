# SPDX-License-Identifier: GPL-3.0-or-later
"""Fetch Mirror Dungeon theme-pack art from the wiki.

The bundled ImageAssets/UI/pack crops are template-match images with the pack
name printed inside them at varying sizes, so they cannot be used as icons
beside a label. The wiki publishes each pack as "<Name>_Theme_Pack.png", with
an "_MD5_" variant where the pack was reworked for Mirror Dungeon 5.

Writes ImageAssets/packart/<pack key>.png, keyed by the key the app uses.
"""
from __future__ import annotations

import os
import re
import sys
import time
import urllib.parse

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from fetch_gift_art import WIKI, _get   # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "ImageAssets", "packart")

# Pack keys whose wiki title differs by more than punctuation.
ALIASES = {
    "MidspringDream2": "A Midspring Night's Dream 2",
    "SEA": "Sea",
    "The_BE": "The B.E.",
    # The app shortens these; the wiki carries the full in-game title.
    "toClaimTheirBones": "Yield My Flesh to Claim Their Bones",
    "toClaimTheirBonesBokGak": "Yield My Flesh to Claim Their Bones Bok Gak",
    "WARPExpressBokGak": "Murder on the WARP Express Bok Gak",
    "NCorp": "N Corp, New League of Nine Littrateurs",
    "Bloodfiends": "Who Couldn't Be Bloodfiends",
    "BeautifulVoice": "A Beautiful Voice",
    "TheGreenDawn": "The Dawn of Green",
    "CertainLibrary": "Into a Certain Library's Book",
    "IchthyicOdor": "Blood-tinged Ichthyic Odor",
    "CompleteExtermination": "Complete, Total Extermination",
    "LaManchaMaster": "The Master of La Manchaland",
}


def _norm(s: str) -> str:
    return re.sub(r"[^a-z0-9]", "", s.lower())


def wiki_packs() -> dict:
    """{normalised pack name: url}, preferring the MD5 rework where present."""
    plain, md5, cont = {}, {}, None
    while True:
        q = {"action": "query", "list": "allimages", "ailimit": "500",
             "format": "json"}
        if cont:
            q["aicontinue"] = cont
        data = _get(f"{WIKI}/api.php?" + urllib.parse.urlencode(q))
        for img in data.get("query", {}).get("allimages", []):
            name = img.get("name", "")
            if not name.endswith("_Theme_Pack.png"):
                continue
            url = img.get("url", "").split("?")[0]
            base = name[: -len("_Theme_Pack.png")]
            if base.endswith("_MD5"):
                md5[_norm(base[:-4])] = url
            else:
                plain[_norm(base)] = url
        cont = (data.get("continue") or {}).get("aicontinue")
        if not cont:
            break
    plain.update(md5)          # MD5 art wins where both exist
    return plain


def main() -> int:
    sys.path.insert(0, os.path.join(ROOT, "src"))
    sys.path.insert(0, ROOT)
    from wbcore.utils.paths import PACKS
    from gui_v2.widgets import humanize_pack

    os.makedirs(OUT, exist_ok=True)
    index = wiki_packs()
    print(f"wiki theme-pack images: {len(index)}")

    got = skipped = 0
    misses = []
    for key in PACKS:
        dest = os.path.join(OUT, key + ".png")
        if os.path.exists(dest) and os.path.getsize(dest) > 0:
            skipped += 1
            continue
        label = ALIASES.get(key) or humanize_pack(key)
        url = index.get(_norm(label))
        if not url:
            # "X Bok Gak" is a variant of the base pack; fall back to it.
            stripped = re.sub(r"bokgak$", "", _norm(label))
            url = index.get(stripped)
        if not url:
            misses.append((key, label))
            continue
        try:
            blob = _get(url, binary=True)
        except Exception as exc:                      # network / 404
            print(f"  ! {key}: {exc}")
            misses.append((key, label))
            continue
        with open(dest, "wb") as fh:
            fh.write(blob)
        got += 1
        time.sleep(0.05)

    print(f"\ndownloaded {got}, already had {skipped}, missing {len(misses)}")
    for key, label in misses:
        print(f"    {key}  ({label})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
