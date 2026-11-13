# SPDX-License-Identifier: GPL-3.0-or-later
"""The starter E.G.O gifts the archetype screen offers: three per keyword,
the one the bot takes when nothing is picked, and finding a picked gift's
row by its art (the rows reorder in game now and then)."""
import logging
import time

from .teams import TEAMS
from .utils.utils import LocateRGB

STARTER_GIFTS = {
    "Burn": ("Hellterfly's Dream", "Fiery Down", "Pain of Stifled Rage"),
    "Bleed": ("Wound Clerid", "Little and To-be-Naughty Plushie", "Awe"),
    "Tremor": ("Oscillating Bracelet", "Reverberation", "Sour Liquor Aroma"),
    "Rupture": ("Barbed Lasso", "Fluorescent Lamp", "Smoking Gunpowder"),
    "Sinking": ("Red Order", "Melted Spring", "Grandeur"),
    "Poise": ("Cigarette Holder", "Stone Tomb", "Old Wooden Doll"),
    "Charge": ("Employee Card", "Portable Battery Socket",
               "Patrolling Flashlight"),
    "Slash": ("Dreaming Electric Sheep", "Short Cane Sword", "Resolution"),
    "Pierce": ("Gathering Skulls", "Plume of Proof", "Torn Bandolier"),
    "Blunt": ("Today\u2019s Expression", "Pocket Flashcards", "Temporal Bridle"),
}

# The archetype screen: the chosen keyword's three gifts, one per row.
ROWS_Y = (395, 549, 703)
ROWS_REGION = (1150, 320, 240, 470)
ART_SCALES = (1.0, 1.2, 1.35, 1.5, 0.85)


def usual_row(keyword: str) -> int:
    """The row the team table takes for a keyword when nothing is picked."""
    team = TEAMS.get(str(keyword).upper())
    return int(team["checks"][5]) if team else 0


def usual_pick(keyword: str) -> str:
    names = STARTER_GIFTS.get(keyword) or ()
    row = usual_row(keyword)
    return names[row] if row < len(names) else ""


def keyword_of(name: str) -> str:
    """The keyword whose starter list holds `name`, or ""."""
    for keyword, names in STARTER_GIFTS.items():
        if name in names:
            return keyword
    return ""


def rows_taken(row: int, star_shower=False, perfected=False) -> list:
    """The rows the archetype screen takes: the pick's, one more of the
    first two with Star Shower, a third with Perfected Possibility."""
    rows = [row]
    if star_shower:
        rows += [i for i in (0, 1) if i not in rows][:1]
    if perfected:
        rows += [i for i in (2, 0, 1) if i not in rows][:1]
    return rows


def taken(pick: str, star_shower=False, perfected=False) -> list:
    """The gifts a run that picks `pick` starts with, the pick first, going
    by the rows as this table lists them."""
    names = STARTER_GIFTS.get(keyword_of(pick)) or ()
    if pick not in names:
        return []
    return [names[i] for i in rows_taken(names.index(pick), star_shower, perfected)]


def find_row(name: str, templates=(), tries: int = 10):
    """Which row shows `name`, found by its art at a few sizes so a reorder
    in the game cannot pick the wrong gift. None when it is not on screen.
    The list is still drawing in when the keyword click returns, so a few
    looks are taken."""
    from . import gift_catalog
    templates = list(templates)
    info = gift_catalog.gift_info(name)
    if info:
        templates.append(info["path"])
    for _ in range(tries):
        for tpl in templates:
            for scale in ART_SCALES:
                try:
                    box = LocateRGB.locate(tpl, region=ROWS_REGION, conf=0.8,
                                           comp=scale)
                except Exception as exc:
                    logging.debug("Starter gift: art of %s @%.2f failed: %s",
                                  name, scale, exc)
                    continue
                if box:
                    cy = box[1] + box[3] / 2
                    row = min(range(len(ROWS_Y)),
                              key=lambda i: abs(ROWS_Y[i] - cy))
                    logging.info("Starter gift: %s is row %d (art at %.2f).",
                                 name, row + 1, scale)
                    return row
        time.sleep(0.15)
    return None
