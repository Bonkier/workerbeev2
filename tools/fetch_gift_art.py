# SPDX-License-Identifier: GPL-3.0-or-later
"""Fetch full-resolution E.G.O gift art from the Limbus wiki for the config
UI. The bundled ImageAssets are tight in-game crops sized for template
matching; the pickers want the whole illustration.

Writes ImageAssets/giftart/<display name>.png, keyed by the market catalog's
display names so the UI can look art up by the name it already has. Skips
files it already has, so re-running only fetches what is missing.
"""
from __future__ import annotations

import json
import os
import re
import sys
import time
import urllib.parse
import urllib.request

WIKI = "https://limbuscompany.wiki.gg"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120 Safari/537.36")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "ImageAssets", "giftart")


def _get(url: str, binary: bool = False):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read() if binary else json.loads(r.read().decode("utf-8"))


def wiki_gift_images() -> dict:
    """{normalised gift name: image url} for every '<name> Gift.png' on the
    wiki. Paged through the allimages API."""
    out, cont = {}, None
    while True:
        q = {"action": "query", "list": "allimages", "ailimit": "500",
             "format": "json"}
        if cont:
            q["aicontinue"] = cont
        data = _get(f"{WIKI}/api.php?" + urllib.parse.urlencode(q))
        for img in data.get("query", {}).get("allimages", []):
            name = img.get("name", "")
            if not name.endswith("_Gift.png"):
                continue
            gift = name[: -len("_Gift.png")].replace("_", " ")
            out[_norm(gift)] = img.get("url", "").split("?")[0]
        cont = (data.get("continue") or {}).get("aicontinue")
        if not cont:
            return out


def _norm(s: str) -> str:
    """Strip everything the wiki and the game disagree about: punctuation,
    spacing and case. The wiki writes "Artwork: Pulsation" (filename
    "Artwork-_Pulsation") where the catalog says "Artwork Pulsation", so a
    whitespace-only fold misses it. Written with code points so the source
    stays plain ASCII."""
    fold = {
        0x2018: "'", 0x2019: "'",          # curly single quotes
        0x201C: '"', 0x201D: '"',          # curly double quotes
        0x2013: "-", 0x2014: "-",          # en / em dash
    }
    return re.sub(r"[^a-z0-9]", "", s.translate(fold).lower())


def _resolve(index: dict, display: str) -> str:
    """Exact normalised hit, else a unique entry whose name ENDS with ours
    ("E-Type Dimensional Dagger" for "Dimensional Dagger")."""
    key = _norm(display)
    if key in index:
        return index[key]
    tail = [v for k, v in index.items() if k.endswith(key) and len(key) >= 8]
    return tail[0] if len(tail) == 1 else ""


def main() -> int:
    sys.path.insert(0, os.path.join(ROOT, "src"))
    from wbcore.market_catalog import load_market_catalog

    os.makedirs(OUT, exist_ok=True)
    catalog = list(load_market_catalog())
    print(f"catalog gifts: {len(catalog)}")
    print("indexing wiki images...")
    index = wiki_gift_images()
    print(f"wiki gift images: {len(index)}")

    got = missed = skipped = 0
    misses = []
    for display in catalog:
        dest = os.path.join(OUT, display + ".png")
        if os.path.exists(dest) and os.path.getsize(dest) > 0:
            skipped += 1
            continue
        url = _resolve(index, display)
        if not url:
            misses.append(display)
            missed += 1
            continue
        try:
            blob = _get(url, binary=True)
        except Exception as exc:                      # network / 404
            print(f"  ! {display}: {exc}")
            missed += 1
            misses.append(display)
            continue
        with open(dest, "wb") as fh:
            fh.write(blob)
        got += 1
        if got % 25 == 0:
            print(f"  {got} downloaded...")
        time.sleep(0.05)                              # be gentle on the wiki

    print(f"\ndownloaded {got}, already had {skipped}, missing {missed}")
    if misses:
        print("no wiki art for:")
        for m in misses[:40]:
            print("   ", m)
        if len(misses) > 40:
            print(f"    ... and {len(misses) - 40} more")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
