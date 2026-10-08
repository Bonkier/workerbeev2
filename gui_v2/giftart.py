# SPDX-License-Identifier: GPL-3.0-or-later
"""Gift artwork lookup shared by the config pickers and the run history.

ImageAssets/giftart holds the full wiki illustration for every gift, keyed by
display name. Callers ask by whatever name they happen to hold - a catalog
display name, or the internal stem run history records for team gifts - so the
index is keyed on a stripped-down form of the name rather than the filename.
Falling through to the bundled ImageAssets template is the last resort: those
are in-game screenshot crops with the inventory slot's dark frame baked in,
which look nothing like the clean art beside them."""

import os
import re

_INDEX = None
_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "ImageAssets", "giftart")


def norm(s) -> str:
    return re.sub(r"[^a-z0-9]", "", str(s).lower())


def index() -> dict:
    global _INDEX
    if _INDEX is None:
        idx = {}
        try:
            for f in sorted(os.listdir(_DIR)):
                if f.lower().endswith(".png"):
                    idx.setdefault(norm(f[:-4]), os.path.join(_DIR, f))
        except OSError:
            pass
        _INDEX = idx
    return _INDEX


# Status/damage keywords share the naming space with gifts ("Charge" would
# prefix-match "Charge-type Gloves"), so they never take the fuzzy path.
_KEYWORDS = frozenset((
    "burn", "bleed", "tremor", "rupture", "sinking", "poise", "charge",
    "slash", "pierce", "blunt",
))


# Team gift stems the prefix rule cannot reach, because the stem is not the
# start of the wiki name ("bloodsack" -> "Ruptured Blood Sac"). Every entry was
# confirmed by rendering the bundled template beside the candidate wiki art and
# comparing the subject's shape and colour, not by name similarity: many gifts
# are small dark objects and near-names are not evidence. Stems with no
# convincing match are deliberately absent and fall back to their template.
_STEM_ALIASES = {
    "angel": "angelscut",
    "apocalypse": "shardofapocalypse",
    "ash": "ashestoashes",
    "bamboohat": "raggedbamboohat",
    "battery": "standarddutybattery",
    "batterysocket": "portablebatterysocket",
    "biovial": "biovenomvial",
    "bloodsack": "rupturedbloodsac",
    "bluntmemory": "crushedmemory",
    "bolt": "t1boctagonalbolt",
    "bracelet": "oscillatingbracelet",
    "breast": "drytothebonebreast",
    "brooch": "ebonybrooch",
    "bundle": "talismanbundle",
    "clerid": "woundclerid",
    "clover": "fourleafclover",
    "cogs": "interlockedcogs",
    "compass": "brokencompass",
    "crumbs": "skeletalcrumbs",
    "devil": "devilsshare",
    "disk": "charreddisk",
    "dust": "dusttodust",
    "effigy": "eerieeffigy",
    "eyeball": "meltedeyeball",
    "fiery": "fierydown",
    "forcefield": "materialinterferenceforcefield",
    "gloves": "chargetypegloves",
    "gossypium": "whitegossypium",
    "gun": "brokenrevolver",
    "hearthflame": "decamillennialhearthflame",
    "holder": "cigaretteholder",
    "horseshoe": "ornamentalhorseshoe",
    "hymn": "arrestedhymn",
    "intellect": "burningintellect",
    "ironstake": "grimyironstake",
    "lamp": "fluorescentlamp",
    "lasso": "barbedlasso",
    "minitelepole": "miniaturetelepole",
    "musicsheet": "blacksheetmusic",
    "muzzle": "rustedmuzzle",
    "nixie": "nixiedivergence",
    "overcoat": "fadedovercoat",
    "paraffin": "meltedparaffin",
    "piercememory": "puncturedmemory",
    "plumeproof": "plumeofproof",
    "redmist": "bloodymist",
    "rod": "lightningrod",
    "rope": "thornyropecuffs",
    "rustedknife": "rustedcuttingknife",
    "scripture": "nagelundhammerscriptures",
    "slashmemory": "sunderedmemory",
    "smokeswires": "smokesandwires",
    "spanner": "oilgunkedspanner",
    "stew": "decamillennialstewpot",
    "stone0": "fragmentofhellfire",
    "stone1": "fragmentofallurement",
    "stone2": "fragmentofinertia",
    "stone3": "fragmentofdesire",
    "stone4": "fragmentofdecay",
    "stone5": "fragmentofconceit",
    "stone6": "fragmentoffriction",
    "synaesthesia": "mirrortactilesynaesthesia",
    "trance": "enrapturingtrance",
    "truthbell": "belloftruth",
    "umbrella": "raggedumbrella",
    "ups": "upssystem",
    "vibrobell": "omnivibrooctovectibell",
    "vitae": "curriculumvitae",
    "wing": "hotnjuicydrumstick",
    "wolf": "littleandtobenaughtyplushie",
}


def art_path(name: str) -> str:
    """Wiki art for a gift, or "" if there is none.

    Run history records team gifts under a shortened internal stem
    ("clearmirror") rather than the catalog display name ("Clear Mirror, Calm
    Water"), so an exact miss falls back to a UNIQUE prefix match. Ambiguous
    prefixes are refused rather than guessed at."""
    key = norm(name)
    idx = index()
    key = _STEM_ALIASES.get(key, key)
    hit = idx.get(key)
    if hit:
        return hit
    if len(key) < 6 or key in _KEYWORDS:
        return ""
    matches = [v for k, v in idx.items() if k.startswith(key)]
    return matches[0] if len(matches) == 1 else ""


_PACK_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "ImageAssets", "packart")


def pack_icon(key: str) -> str:
    """The in-game theme-pack card for a Mirror Dungeon pack key, or ""."""
    p = os.path.join(_PACK_DIR, str(key) + ".png")
    return p if os.path.isfile(p) else ""


_KW_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "ImageAssets", "keywordart")


def keyword_icon(keyword: str) -> str:
    """Clean wiki status icon for a keyword, or "". The bundled tab crops have
    the keyword's name printed inside them, so the picker showed the word
    twice - once in the image, once as the tab's own label."""
    p = os.path.join(_KW_DIR, norm(keyword) + ".png")
    return p if os.path.isfile(p) else ""
