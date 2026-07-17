# SPDX-License-Identifier: GPL-3.0-or-later
"""Catalog of EGO-gift-search thumbnails (ImageAssets/giftsearch).

Deliberately kept out of the global PTH (collect_png_paths): the thumbnails use
human-readable display-name filenames (spaces, capitals) and at least one
("Sunshower") collides with an existing UI template, which would crash the PTH
builder. They are indexed here instead - by display name, with keyword and tier -
for the gift picker UI and the start-of-run gift search.
"""
from __future__ import annotations

import os

from .utils.paths import BASE_PATH

# Folder name (roman) -> numeric tier.
_TIERS = {"I": 1, "II": 2, "III": 3}
_CATALOG = None


def _catalog_dir() -> str:
    return os.path.join(BASE_PATH, "ImageAssets", "giftsearch")


def load_catalog(refresh: bool = False) -> dict:
    """{display_name: {"path", "keyword", "tier"}} for every gift thumbnail.

    Scanned from ImageAssets/giftsearch/<keyword>/<I|II|III>/<name>.png and
    cached after the first call.
    """
    global _CATALOG
    if _CATALOG is not None and not refresh:
        return _CATALOG
    cat: dict = {}
    base = _catalog_dir()
    if os.path.isdir(base):
        for keyword in sorted(os.listdir(base)):
            kw_dir = os.path.join(base, keyword)
            if not os.path.isdir(kw_dir):
                continue
            for roman, tier in _TIERS.items():
                tier_dir = os.path.join(kw_dir, roman)
                if not os.path.isdir(tier_dir):
                    continue
                for file in sorted(os.listdir(tier_dir)):
                    if not file.lower().endswith(".png"):
                        continue
                    name = os.path.splitext(file)[0]
                    cat[name] = {
                        "path": os.path.join(tier_dir, file).replace("\\", "/"),
                        "keyword": keyword,
                        "tier": tier,
                    }
    _CATALOG = cat
    return cat


def gift_names() -> list:
    """All gift display names, ordered by keyword, then tier, then name."""
    cat = load_catalog()
    return sorted(
        cat, key=lambda n: (cat[n]["keyword"], cat[n]["tier"], n.lower())
    )


def gift_info(name: str):
    """{"path", "keyword", "tier"} for one gift, or None if unknown."""
    return load_catalog().get(name)


def tab_path(keyword: str):
    """Path to a keyword filter-tab template (<keyword>/<keyword>tab.png), or None."""
    p = os.path.join(_catalog_dir(), keyword, f"{keyword}tab.png")
    return p.replace("\\", "/") if os.path.isfile(p) else None
