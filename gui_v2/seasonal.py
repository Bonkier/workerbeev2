# SPDX-License-Identifier: GPL-3.0-or-later
"""Seasonal dress for the UI.

Halloween runs for the whole of October: WorkerBee becomes EvilBee, the bee
grows bat wings, the palette goes darker and red, page titles turn EVIL and
the loading screen gets a graveyard. It is decided once per launch from the
date; nothing is saved, so on 1 November the app is itself again.

Only names shown as TITLES change (the brand, page and nav titles, the run
names). The names of individual settings and of EGO gifts are left alone.

WORKERBEE_SEASON=halloween forces it on outside October (for looking at it),
and WORKERBEE_SEASON=off forces it off."""

import datetime
import os
import re

HALLOWEEN = "halloween"

# The two fixed colours of the season. The accent swaps to RED; BONE is the
# white the "Bee" half of the wordmark keeps.
RED = "#e01e2f"
BONE = "#f2f2f4"
BACKGROUND = "#050406"

_forced = None      # tests / previews: HALLOWEEN, "off", or None for the date


def force(value):
    """Pin the season regardless of date (None returns to the calendar)."""
    global _forced
    _forced = value


def active() -> str:
    """The season in effect: HALLOWEEN or ""."""
    if _forced is not None:
        return "" if _forced == "off" else str(_forced)
    env = os.environ.get("WORKERBEE_SEASON", "").strip().lower()
    if env in ("off", "none"):
        return ""
    if env == HALLOWEEN:
        return HALLOWEEN
    return HALLOWEEN if datetime.date.today().month == 10 else ""


def is_halloween() -> bool:
    return active() == HALLOWEEN


def brand() -> tuple:
    """The wordmark as (first half, second half)."""
    return ("Evil", "Bee") if is_halloween() else ("Worker", "Bee")


def brand_name() -> str:
    return "".join(brand())


# Longest names first, so "Statistics" is not half-matched as "Stats".
_EVIL = (
    ("Mirror Dungeon", "EVIL Dungeon"),
    ("Luxcavation", "EVILuxcavation"),
    ("Statistics", "EVIL Statistics"),
    ("Dashboard", "EVIL Dashboard"),
    ("Scheduler", "EVIL Scheduler"),
    ("Stats", "EVIL Statistics"),
    ("Logs", "EVIL Logs"),
)


def title(text):
    """A title in its seasonal form: "Mirror Dungeon" -> "EVIL Dungeon",
    "Start Mirror Dungeon" -> "Start EVIL Dungeon". Text with none of the
    renamed words in it, and everything outside Halloween, is returned
    unchanged. An all-caps title stays all caps."""
    if not text or not is_halloween():
        return text
    out = str(text)
    for plain, evil in _EVIL:
        match = re.search(r"\b%s\b" % re.escape(plain), out, re.IGNORECASE)
        if match is None:
            continue
        found = match.group(0)
        swap = evil.upper() if found.isupper() else evil
        return out[:match.start()] + swap + out[match.end():]
    return out


def plain(text):
    """title() undone: "Start EVIL Dungeon" -> "Start Mirror Dungeon". The
    search bar uses it so a feature is found under its everyday name too."""
    if not text or not is_halloween():
        return text
    out = str(text)
    for name, evil in _EVIL:
        match = re.search(re.escape(evil), out, re.IGNORECASE)
        if match is None:
            continue
        found = match.group(0)
        swap = name.upper() if found.isupper() else name
        return out[:match.start()] + swap + out[match.end():]
    return out


# Shown in place of the bee facts on the loading screen. Each is true, and
# short enough for the subtitle slot (about 32 characters).
SPOOKY_TIPS = (
    "Vulture bees feed on dead flesh",
    "Zombie flies hijack bee brains",
    "Intruders are entombed in wax",
    "Undertaker bees haul out corpses",
    "Honey once embalmed the dead",
    "Queens are born killing rivals",
    "Hornets behead bees one by one",
    "Bees cook hornets alive",
    "Mad honey brings hallucinations",
    "A torn-out sting keeps pumping",
    "Drones are thrown out to die",
    "Robber bees loot dying hives",
    "Death's-head moths raid hives",
    "New queens pipe a war cry",
    "Starving hives eat their young",
    "The hive never sleeps",
)
