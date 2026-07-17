# SPDX-License-Identifier: GPL-3.0-or-later
"""Catalog of market gift templates.

Two template sets, both kept out of the global PTH (which only walks
ImageAssets/UI):
- ImageAssets/egogifts: less-cropped 89x88 thumbnails. Used for the config UI
  and for sell/fuse identification in the fuse/sell menus.
- ImageAssets/markettemplates: tight 48x48 crops. Used for buy identification
  on the shop's buy shelf.

Indexed by display name, with keyword and tier (I-V). The two sets are unioned;
the egogifts thumbnail is preferred for display where present.
"""
from __future__ import annotations

import os

from .utils.paths import BASE_PATH

_TIERS = {"I": 1, "II": 2, "III": 3, "IV": 4, "V": 5}
_EX_TIER = 6   # the EX (extreme) gift folder, shown above the numbered tiers
_CATALOG = None


def _egogifts_dir() -> str:
    return os.path.join(BASE_PATH, "ImageAssets", "egogifts")


def _market_dir() -> str:
    return os.path.join(BASE_PATH, "ImageAssets", "markettemplates")


def _scan(base: str) -> dict:
    """{name: {keyword, tier, path}} from <base>/<keyword>/<I..V>/<name>.png."""
    out: dict = {}
    if not os.path.isdir(base):
        return out
    for keyword in sorted(os.listdir(base)):
        kw_dir = os.path.join(base, keyword)
        if not os.path.isdir(kw_dir):
            continue
        if keyword == "EX":
            # Extreme gift(s) sit directly in EX/ (no tier subdir); surface them
            # under keywordless at the top "EX" tier.
            for file in sorted(os.listdir(kw_dir)):
                if file.lower().endswith(".png"):
                    name = os.path.splitext(file)[0]
                    out[name] = {
                        "keyword": "keywordless", "tier": _EX_TIER,
                        "path": os.path.join(kw_dir, file).replace("\\", "/"),
                    }
            continue
        for roman, tier in _TIERS.items():
            tier_dir = os.path.join(kw_dir, roman)
            if not os.path.isdir(tier_dir):
                continue
            for file in sorted(os.listdir(tier_dir)):
                if not file.lower().endswith(".png"):
                    continue
                name = os.path.splitext(file)[0]
                out[name] = {
                    "keyword": keyword,
                    "tier": tier,
                    "path": os.path.join(tier_dir, file).replace("\\", "/"),
                }
    return out


def load_market_catalog(refresh: bool = False) -> dict:
    """{name: {keyword, tier, path, sell_path, buy_path}}.

    `path` is the display thumbnail (egogifts where present, else markettemplate).
    `sell_path` is the egogifts template (sell/fuse identification) or None.
    `buy_path` is the markettemplate (buy identification) or None.
    """
    global _CATALOG
    if _CATALOG is not None and not refresh:
        return _CATALOG
    ego = _scan(_egogifts_dir())
    mkt = _scan(_market_dir())
    cat: dict = {}
    for name, info in ego.items():
        cat[name] = {
            "keyword": info["keyword"], "tier": info["tier"],
            "path": info["path"], "sell_path": info["path"],
            "buy_path": (mkt.get(name) or {}).get("path"),
        }
    for name, info in mkt.items():
        if name in cat:
            cat[name]["buy_path"] = info["path"]
        else:
            cat[name] = {
                "keyword": info["keyword"], "tier": info["tier"],
                "path": info["path"], "sell_path": None,
                "buy_path": info["path"],
            }
    _CATALOG = cat
    return cat


def market_gift_names() -> list:
    """All gift display names, ordered by keyword, then tier, then name."""
    cat = load_market_catalog()
    return sorted(
        cat, key=lambda n: (cat[n]["keyword"], cat[n]["tier"], n.lower())
    )


def market_gift_info(name: str):
    """{keyword, tier, path, sell_path, buy_path} for one gift, or None."""
    return load_market_catalog().get(name)


# SAIKAI Market/Fuse starter tags (display names). Seeds the editable
# per-run market config the first time SAIKAI is selected in the UI; the
# user is free to change it from there. Only the two T4s are fuse targets.
SAIKAI_MARKET_KEEP = [
    "Spiderweb Entangled in Red", "Clear Mirror, Calm Water", "Sundered Memory",
    "Endorphin Kit", "Nebulizer", "Stone Tomb", "Emerald Elytra",
]
SAIKAI_MARKET_BUY = SAIKAI_MARKET_KEEP[1:]     # buy priority order
SAIKAI_MARKET_FUSE = SAIKAI_MARKET_KEEP[1:3]   # Clear Mirror, Sundered Memory
SAIKAI_MARKET_ENH2 = [
    "Clear Mirror, Calm Water", "Nebulizer", "Stone Tomb", "Emerald Elytra",
]
SAIKAI_MARKET_TAGS = {
    "keep_fuse": list(SAIKAI_MARKET_KEEP),
    "keep_sell": list(SAIKAI_MARKET_KEEP),
    "fuse": list(SAIKAI_MARKET_FUSE),
    "buy": list(SAIKAI_MARKET_BUY),
    "enhance2": list(SAIKAI_MARKET_ENH2),
}
