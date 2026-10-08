# SPDX-License-Identifier: GPL-3.0-or-later
"""HOLLOW: Faust alone, with the Hollow E.G.O (Le Trou).

Floors 1 to 4 run on Normal, floor 5 on Hard. On floors 1 to 3 every fight
is one turn: open Faust's E.G.O menu from her portrait, hold on Le Trou until
it overclocks, slot it, win rate, Enter, and keep the mouse held so the
animation runs fast. At -45 SP she corrodes and the E.G.O is already in the
slot, so the menu step is skipped. The floor 4 and 5 bosses are focused
fights: Le Trou is slotted without the overclock and aimed at an enemy skill
slot on turn 1, then win rate from turn 2. SP resets with every floor, so
a corroded reading holds for its floor only and the overclock loop starts
over on the next. Shops heal first (a chosen sinner once on floor 1, since
they never fight and the 45 SP keeps for the skill checks; Faust herself on
floors 4 and 5) and then follow the Market/Fuse tab's plan, except that
Clear Mirror, Calm Water and Artistic Sense are not uptied before the
floor 3 shop. The starter gift is Cigarette Holder from the Poise list;
Grand Welcome and Sharp Needle & Thread come from the E.G.O Gift Search.

Every step is gated by run_script == HOLLOW_SCRIPT and called from the
generic fight/shop/move loops."""

import logging
import time

import cv2
import numpy as np

from .utils.utils import *               # noqa: F401,F403 (bot module style)
from .utils import params as p
from .teams import TEAMS as _TEAM_TABLE

HOLLOW_SCRIPT = "hollow"
FAUST = "FAUST"
STARTING_GIFT = "Cigarette Holder"
STARTING_KEYWORD = "POISE"               # the starter screen keyword it is under
SEARCH_GIFTS = ("Grand Welcome", "Sharp Needle & Thread")
# Upties the owner wants left alone until this floor's shop.
ENHANCE_FROM_FLOOR = {"Clear Mirror, Calm Water": 3, "Artistic Sense": 3}
# The market works the Poise gifts before the rest (the Sinking ones wait).
MARKET_KEYWORD_FIRST = "poise"
# The market plan (owner's summary, 2026-10-07, priority of 2026-10-08):
# the gifts kept out of the fuel pool per floor (floor 3 stands for every
# later one), the fuse targets and the upties (from the floor 3 shop, see
# ENHANCE_FROM_FLOOR).
_CONCEIT = "Fragment of Conceit"
_DECAY = "Fragment of Decay"
_WELCOME = "Grand Welcome"
_THREAD = "Sharp Needle & Thread"
_MIRROR = "Clear Mirror, Calm Water"
_SENSE = "Artistic Sense"
MARKET_PROTECTED = {
    1: (_CONCEIT, _DECAY, _WELCOME, STARTING_GIFT, _THREAD, _MIRROR, _SENSE),
    2: (_CONCEIT, _DECAY, STARTING_GIFT, _THREAD),
    3: (_CONCEIT, _DECAY, STARTING_GIFT, _THREAD, _MIRROR, _SENSE),
}
# The two the run must get, in this order, with fuel bought for them; the
# others only from what the pool allows once those are done.
MARKET_MUST = (_CONCEIT, _DECAY)
MARKET_OTHERS = (_MIRROR, _SENSE)
MARKET_ENHANCE_TWICE = (_MIRROR, _SENSE)
ENHANCE_ALL_BY_FLOOR = 4          # upties wait for every craft until this floor

# --- geometry (FHD) ----------------------------------------------------
_PORTRAIT_Y = 990                 # the sinner badge under the chain bar
_SOLO_SLOT_X = 902                # Faust's single skill slot, both modes
_SLOT_Y = 845
_CARD_DX, _CARD_PITCH = 130, 122  # chain bar card centres from the left gear
_PORTRAIT_BAND = (560, 940, 820, 110)
_EGO_MENU_REGION = (0, 150, 1920, 420)
_HUD_AIM_REGION = (1700, 15, 130, 90)
_HUD_AIM_CLICK = (1766, 58)
_ENEMY_BAND = (300, 150, 1320, 500)
# The enemy slot frame sits under its icon; how far depends on the boss, so
# each icon cut carries the distance measured on its own capture, and the
# frame itself is looked for around that distance.
_ICON_TO_SLOT_DY = {"hollow_ribcage": 96, "hollow_skull": 96,
                    "hollow_ribcage2": 61}
_ICON_SCALES = (1.0, 0.85, 0.75, 1.15)
_SLOT_SEARCH = 45                 # px either side of the expected distance
_SLOT_ABOVE_BOTTOM = 18           # click this far above the frame's bottom edge
_SLOT_MAX_HEIGHT = 80             # taller than any slot frame: not a frame
_SHOP_HEAL_BUTTON = (293, 705)
_SHOP_HEAL_SINGLE = (1530, 320)
_SHOP_PORTRAIT_Y = 970
_SHOP_PORTRAIT_X = (148, 263, 379, 494, 609, 724, 840, 955, 1070, 1185,
                    1301, 1416)   # hex frames 115.3 px apart
_SHOP_CONFIRM = (1705, 967)       # Select, then Leave, same place
_HEAL_BUTTON_REGION = (1500, 900, 400, 140)   # Select, Leave or Return
_SP_BADGE_BOX = (-2, 20, 50, 36)   # SP number box, relative to a portrait

# Starter-gift screen: the chosen keyword's three gifts, one per row.
_STARTER_ROWS_Y = (395, 549, 703)
_STARTER_ROWS_REGION = (1150, 320, 240, 470)
_STARTER_ART_SCALES = (1.0, 1.2, 1.35, 1.5, 0.85)
_HOLD_PARK = (960, 160)           # harmless place to hold the mouse down
_X_BIAS = 4                       # the cursor lands a touch left of the mark
_DRAG_CHAIN_FLOORS = (1,)         # boss fights chained by hand, not win rate
_PLATES = ("hollow_letrou", "hollow_boucher")   # the card's two names
_SP_CONF = 0.975                  # -45 against -42 is one digit: exact only
_MAP_SP_REGION = (425, 1005, 80, 60)   # Faust's SP badge in the map strip
_RETRY_COG = (1850, 60)
_SQUAD_CARD_Y = 986 - 118         # a sinner's skill card above the hex row
_SQUAD_SLOT_XS = (548, 670, 792, 914, 1036, 1158, 1280)
_TURN_HOLD_MAX = 90.0
_OVERCLOCK_MAX = 4.5
_MENU_OPEN_MAX = 2.5

_EXIT = ("loading", "Move", "EGObin", "encounterreward", "victory", "defeat",
         "PackChoice")

# The portrait row in the shop and in the deploy screen is the roster order.
ROSTER = ("YISANG", "FAUST", "DONQUIXOTE", "RYOSHU", "MEURSAULT", "HONGLU",
          "HEATHCLIFF", "ISHMAEL", "RODION", "SINCLAIR", "OUTIS", "GREGOR")


def active() -> bool:
    return getattr(p, "RUN_SCRIPT", "") == HOLLOW_SCRIPT


# --- squad ---------------------------------------------------------------

def squad_for(node: str) -> list:
    """Who to deploy: Faust alone, plus the fallback sinners on a miniboss.
    Focused fights (the floor bosses) are hers alone: the E.G.O is aimed by
    hand there, which the script only does for one slot."""
    squad = [FAUST]
    if str(node) in ("Miniboss", "Risky"):
        for name in getattr(p, "HOLLOW_FALLBACK", None) or []:
            if name in ROSTER and name not in squad:
                squad.append(name)
    return squad


def forfeit_threshold(dead_boxes, strip) -> int:
    """How many dead sinners end the run: one when Faust herself is among
    them (her column of the map's sinner strip shows a 0), otherwise the
    whole squad she can field, so a fallback sinner lost in a miniboss does
    not end it."""
    x0, _y, w, _h = strip
    col = w / len(ROSTER)
    faust = ROSTER.index(FAUST)
    for x, _y, bw, _bh in dead_boxes:
        if int((x + bw / 2 - x0) // col) == faust:
            logging.info("HOLLOW: Faust is down; the run cannot go on.")
            return 1
    return 1 + len(getattr(p, "HOLLOW_FALLBACK", None) or [])


# --- the starting gift ---------------------------------------------------

def starting_team() -> dict:
    """The team-table entry whose keyword is clicked on the starter screen:
    always Poise, where Cigarette Holder is listed."""
    return _TEAM_TABLE[STARTING_KEYWORD]


def starting_gift_row():
    """Which row of the keyword's starter gifts shows Cigarette Holder,
    found by its art at a few sizes so a reorder in the game cannot pick
    the wrong gift. None when the art is not on screen."""
    from . import gift_catalog
    templates = [PTH["holder"]] if "holder" in PTH else []
    info = gift_catalog.gift_info(STARTING_GIFT)
    if info:
        templates.append(info["path"])
    # The list is still drawing in when the keyword click returns: look
    # for a short while before giving up.
    for _ in range(10):
        for tpl in templates:
            for scale in _STARTER_ART_SCALES:
                try:
                    box = LocateRGB.locate(tpl, region=_STARTER_ROWS_REGION,
                                           conf=0.8, comp=scale)
                except Exception as exc:
                    logging.debug("HOLLOW: starter art @%.2f failed: %s",
                                  scale, exc)
                    continue
                if box:
                    cy = box[1] + box[3] / 2
                    row = min(range(len(_STARTER_ROWS_Y)),
                              key=lambda i: abs(_STARTER_ROWS_Y[i] - cy))
                    logging.info("HOLLOW: %s is starter row %d (art at %.2f).",
                                 STARTING_GIFT, row + 1, scale)
                    return row
        time.sleep(0.15)
    usual = starting_team()["checks"][5] + 1
    logging.warning("HOLLOW: %s not seen among the %s starter gifts; taking "
                    "row %d, that keyword's usual pick, which is probably "
                    "not it. Check the gift on the first shop screen.",
                    STARTING_GIFT, STARTING_KEYWORD.title(), usual)
    return None


def enhance_allowed(name: str) -> bool:
    """Whether the market may uptie this gift on the current floor."""
    floor = int(getattr(p, "LVL", 1) or 1)
    return floor >= ENHANCE_FROM_FLOOR.get(name, 1)


def enhance_ready(crafted, floor=None) -> bool:
    """Whether the upties may start: every gift of the plan crafted, or
    floor 4 reached with some still missing."""
    floor = int(floor or getattr(p, "LVL", 1) or 1)
    if floor >= ENHANCE_ALL_BY_FLOOR:
        return True
    return all(n in (crafted or ()) for n in MARKET_MUST + MARKET_OTHERS)


def market_plan(floor=None, crafted=()) -> dict:
    """The shop plan for a floor: protected gifts, the fuse targets still
    owed (the must-gets first, in their order, then the others) and the
    upties allowed on that floor."""
    floor = int(floor or getattr(p, "LVL", 1) or 1)
    key = min(max(floor, 1), 3)
    crafted = set(crafted or ())
    fuse = [n for n in MARKET_MUST + MARKET_OTHERS if n not in crafted]
    enhance2 = [n for n in MARKET_ENHANCE_TWICE
                if floor >= ENHANCE_FROM_FLOOR.get(n, 1)]
    return {"protected": list(MARKET_PROTECTED[key]), "fuse": fuse,
            "must": list(MARKET_MUST), "enhance2": enhance2}


def market_order(names, keyword_of) -> list:
    """The market plan's names with the Poise gifts first; the order is
    otherwise kept, so the owner's own ranking still applies within each
    group. `keyword_of` maps a gift name to its catalog keyword."""
    return sorted(names, key=lambda n: 0 if keyword_of(n) == MARKET_KEYWORD_FIRST
                  else 1)


def _with_fallback() -> bool:
    """True when the fallback sinners are on the field with Faust: those
    fights (minibosses) are plain win rate, not the E.G.O loop."""
    return len(getattr(p, "SELECTED", None) or []) > 1


def read_map_sp() -> bool:
    """On the map: does Faust's badge in the sinner strip read -45? That
    decides the next fight (corroded: the E.G.O is already chosen, plain win
    rate; otherwise the full menu and overclock loop). Exact match only, -42
    looks almost the same."""
    if "hollow_map_sp45" not in PTH:
        return False
    corroded = bool(LocateRGB.locate(PTH["hollow_map_sp45"],
                                     region=_MAP_SP_REGION, conf=_SP_CONF))
    was = bool(getattr(p, "HOLLOW_CORRODED", False))
    p.HOLLOW_CORRODED = corroded
    p.HOLLOW_CORRODED_FLOOR = int(getattr(p, "LVL", 1) or 1)
    if corroded != was:
        logging.info("HOLLOW: map reads Faust %s.",
                     "at -45 SP (corroded)" if corroded else "not at -45 SP")
    return corroded


def _corroded_now() -> bool:
    """The shop's -45 SP reading holds for the rest of its floor only."""
    return (bool(getattr(p, "HOLLOW_CORRODED", False))
            and int(getattr(p, "HOLLOW_CORRODED_FLOOR", 0) or 0)
            == int(getattr(p, "LVL", 1) or 1))


def begin_run():
    p.HOLLOW_AIM_CHECKED = False
    p.HOLLOW_CORRODED = False
    p.HOLLOW_CORRODED_FLOOR = 0
    p.HOLLOW_NODE = ""
    p.SELECTED = [FAUST]


def begin_battle():
    p.HOLLOW_TURN = 0
    p.HOLLOW_RETRIES = 0
    p.HOLLOW_MENU_DUMPED = False


def _tpl(name) -> bool:
    if name in PTH:
        return True
    logging.warning("HOLLOW: template %s missing (ImageAssets/UI/hollow).", name)
    return False


def _frame(region):
    """The region as an FHD-sized BGR frame, whatever the window size, so
    pixel arithmetic on it is in the same units as the regions."""
    x, y, w, h = region
    img = screenshot(region=region)
    if img.shape[1] != w or img.shape[0] != h:
        img = cv2.resize(img, (w, h), interpolation=cv2.INTER_LINEAR)
    return img


# --- the attack position setting ----------------------------------------

def check_attack_position():
    """First battle of the run: the HUD's attack position must show the white
    arrows (the document's correct state). The yellow spread arrows are the
    wrong state and look alike to the matcher, so both are scored and the
    higher wins. Clicking the icon cycles the setting."""
    if getattr(p, "HOLLOW_AIM_CHECKED", False):
        return
    p.HOLLOW_AIM_CHECKED = True
    if not _tpl("hollow_aim_ok"):
        return
    for attempt in range(4):
        ok = _hud_conf("hollow_aim_ok")
        bad = _hud_conf("hollow_aim_wrong") if "hollow_aim_wrong" in PTH else 0.0
        if ok >= 0.82 and ok > bad:
            logging.info("HOLLOW: attack position is set correctly%s "
                         "(%.2f vs %.2f).",
                         " after %d click(s)" % attempt if attempt else "",
                         ok, bad)
            return
        win_click(_HUD_AIM_CLICK, tsize=(10, 10))
        time.sleep(0.6)
    logging.warning("HOLLOW: could not set the attack position to the "
                    "white arrows; the E.G.O may miss targets.")


def _hud_conf(name) -> float:
    try:
        return float(LocateRGB.get_conf(PTH[name], region=_HUD_AIM_REGION))
    except Exception as exc:
        logging.debug("HOLLOW: %s score failed: %s", name, exc)
        return 0.0


# --- finding Faust -------------------------------------------------------

def _portrait_xs() -> list:
    """X of each sinner badge under the chain bar, found by the orange hex
    frame (the art inside differs per identity): the columns the frame
    fills, then any sizeable warm blob as a further candidate, since a low
    HP frame goes half red and shows up as a narrower shape."""
    x0, y0, w, h = _PORTRAIT_BAND
    img = _frame(_PORTRAIT_BAND)
    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
    mask = cv2.inRange(hsv, np.array([5, 150, 150]), np.array([22, 255, 255]))
    cols = (mask.sum(axis=0) // 255)
    xs, run = [], []
    for i, v in enumerate(cols):
        if v >= 12:
            run.append(i)
        elif run:
            if len(run) >= 30:
                xs.append(x0 + (run[0] + run[-1]) // 2)
            run = []
    if run and len(run) >= 30:
        xs.append(x0 + (run[0] + run[-1]) // 2)
    hue, sat, val = hsv[..., 0], hsv[..., 1], hsv[..., 2]
    warm = (((hue <= 25) | (hue >= 172)) & (sat >= 120) & (val >= 120))
    closed = cv2.morphologyEx(warm.astype(np.uint8) * 255, cv2.MORPH_CLOSE,
                              np.ones((7, 7), np.uint8))
    _n, _lab, stats, _cent = cv2.connectedComponentsWithStats(closed)
    # The hex is about 92 px wide and over 100 tall; the bar's decorations
    # are shorter. A blob under 85 px wide is the orange half of a low HP
    # hex, whose centre sits a half hex in from its left edge.
    blobs = []
    for sx, _sy, sw, sh, _area in sorted(stats[1:], key=lambda s: s[0]):
        if sw >= 60 and sh >= 100:
            blobs.append(x0 + sx + (sw // 2 if sw >= 85 else 46))
    return _spaced(blobs + xs, gap=20)


def _spaced(xs, gap=30) -> list:
    """The candidates in order, without near duplicates."""
    out = []
    for x in xs:
        x = int(x)
        if all(abs(x - o) > gap for o in out):
            out.append(x)
    return out


def _gear_slots() -> list:
    """Slot x positions from the chain gears, found with a softer match
    than the fight loop uses (busy boss arenas hide them from it)."""
    try:
        g1 = LocateEdges.locate(PTH["gear"], region=(0, 761, 900, 179), conf=0.55)
        g2 = LocateEdges.locate(PTH["gear2"], region=(350, 730, 1570, 232),
                                conf=0.55)
    except Exception as exc:
        logging.debug("HOLLOW: soft gear match failed: %s", exc)
        return []
    if not g1 or not g2:
        return []
    gs, ge = gui.center(g1), gui.center(g2)
    if ge[0] - gs[0] < 250:
        return []
    return _slot_xs(gs, ge)


def _slot_xs(gear_start=None, gear_end=None) -> list:
    """Skill slot centres: from the gears in a chain battle, otherwise the
    one place a solo slot sits."""
    if gear_start is not None and gear_end is not None:
        n = max(1, int(round((gear_end[0] - gear_start[0] - 140) / 115)))
        return [int(gear_start[0] + _CARD_DX + i * _CARD_PITCH)
                for i in range(n)]
    return [_SOLO_SLOT_X]


def _close_menu():
    win_click(1888, 901)
    time.sleep(0.3)


def _menu_open() -> bool:
    """The E.G.O menu covers the chain bar, so its buttons disappear."""
    return not now.button("winrate")


def _find_plate(conf=0.86):
    """The card's name plate in the open menu: Le Trou, or Boucher un trou
    once an Ashen Bullet is up (turn 2 on)."""
    for name in _PLATES:
        if name in PTH:
            box = LocateRGB.locate(PTH[name], region=_EGO_MENU_REGION, conf=conf)
            if box:
                return box
    return None


def open_ego_menu(x: int):
    """Hold the badge at `x` until the E.G.O menu shows the card. Returns
    its name plate box, or None (no menu, or not Faust's). A menu that opens
    without a readable plate is matched again at a softer floor and
    captured once per battle for the log."""
    if not _tpl("hollow_letrou"):
        return None
    win_moveTo(x, _PORTRAIT_Y)
    time.sleep(0.1)
    gui.mouseDown()
    box = None
    start = time.time()
    try:
        while time.time() - start < _MENU_OPEN_MAX:
            time.sleep(0.15)
            box = _find_plate()
            if box:
                break
    finally:
        gui.mouseUp()
    time.sleep(0.3)
    if not box:
        box = _find_plate()
    if not box and _menu_open():
        best = 0.0
        for name in _PLATES:
            if name in PTH:
                try:
                    best = max(best, float(LocateRGB.get_conf(
                        PTH[name], region=_EGO_MENU_REGION)))
                except Exception:
                    pass
        logging.info("HOLLOW: a menu opened at x=%d but the card's plate did "
                     "not match (best %.2f).", x, best)
        if not getattr(p, "HOLLOW_MENU_DUMPED", False):
            p.HOLLOW_MENU_DUMPED = True
            dump_template_diag("hollow_menu", *_PLATES)
        if best >= 0.72:
            box = _find_plate(conf=0.72)
    elif not box:
        logging.info("HOLLOW: no menu opened from x=%d.", x)
    if box:
        logging.info("HOLLOW: the card found at %s.", tuple(box))
    return box


def find_faust(gear_start=None, gear_end=None):
    """Open Faust's E.G.O menu with ONE hold, at the best guess for her
    badge: her first slot column (from the gears the fight loop saw, or a
    softer gear match), else the orange frame, else the solo position. No
    menu means win rate, as the owner asked. Returns (slot_x, plate_box) or
    (None, None)."""
    if gear_start is not None and gear_end is not None:
        slots = _slot_xs(gear_start, gear_end)
    else:
        slots = _gear_slots()
    candidates = _spaced(list(slots) + _portrait_xs() + [_SOLO_SLOT_X])
    x = candidates[0]
    logging.info("HOLLOW: holding the badge at x=%d (slots %s).", x, slots)
    box = open_ego_menu(x)
    if box:
        slot = min(slots, key=lambda sx: abs(sx - x)) if slots else _SOLO_SLOT_X
        return slot, box
    if _menu_open():
        _close_menu()
    return None, None


def _card_centre(name_box):
    x, y, w, h = name_box
    return (int(x + w // 2), int(y - 110))      # art sits above the plate


def overclock(name_box) -> bool:
    """Hold on the Le Trou card until it shows the overclock warning."""
    if not _tpl("hollow_overclock"):
        return False
    cx, cy = _card_centre(name_box)
    win_moveTo(cx, cy)
    time.sleep(0.1)
    gui.mouseDown()
    seen = False
    start = time.time()
    try:
        while time.time() - start < _OVERCLOCK_MAX:
            time.sleep(0.15)
            if LocateRGB.locate(PTH["hollow_overclock"],
                                region=(cx - 170, cy - 170, 340, 340),
                                conf=0.8):
                seen = True
                break
    finally:
        gui.mouseUp()
    logging.info("HOLLOW: overclock %s after %.1fs.",
                 "shown" if seen else "NOT shown", time.time() - start)
    time.sleep(0.3)
    return seen


def slot_card(name_box, overclocked: bool) -> bool:
    """Put the card into Faust's skill slot. After an overclock hold one
    click does it; a card that was not held needs a double click. The menu
    closing is the proof it slotted."""
    cx, cy = _card_centre(name_box)
    for attempt in range(2):
        win_click(cx, cy, tsize=(20, 20))
        if not overclocked:
            time.sleep(0.08)
            win_click(cx, cy, tsize=(20, 20), delay=0)
        time.sleep(0.6)
        if loc.button("winrate", wait=1.5):
            break
        logging.info("HOLLOW: the E.G.O menu is still open after click %d; "
                     "clicking the card again.", attempt + 1)
    else:
        logging.warning("HOLLOW: the card would not slot; closing the menu.")
        _close_menu()
        return False
    if overclocked and "hollow_overclock_slot" in PTH:
        ok = bool(LocateRGB.locate(PTH["hollow_overclock_slot"],
                                   region=(600, 760, 720, 200), conf=0.8))
        logging.info("HOLLOW: overclocked E.G.O %s in the slot.",
                     "is" if ok else "not seen")
        return ok
    return True


# --- executing a turn ----------------------------------------------------

def win_rate():
    """Toggle win rate on, by key first, the mouse if the key is ignored."""
    gui.press("p", 1, 0.1)
    time.sleep(0.5)
    if loc.button("winrate_on", "winrate", wait=1.5,
                  method=cv2.TM_SQDIFF_NORMED):
        return True
    gui.hotkey("ctrl", "p")
    time.sleep(0.5)
    if loc.button("winrate_on", "winrate", wait=1.5,
                  method=cv2.TM_SQDIFF_NORMED):
        return True
    win_click(1385, 930)
    time.sleep(0.4)
    return bool(loc.button("winrate_on", "winrate", wait=1,
                           method=cv2.TM_SQDIFF_NORMED))


def _turn_over() -> bool:
    if now.button("winrate"):
        return True
    return any(now.button(k) for k in _EXIT)


def execute_and_hold(enter=True):
    """Start the turn with Enter (unless the chain drag already did), press
    it once more if nothing started, then keep the mouse held so the E.G.O
    animation runs at full speed, until the next turn or the end of the
    battle."""
    if enter:
        gui.press("enter", 1, 0.1)
    time.sleep(1.2)
    if now.button("winrate"):
        logging.info("HOLLOW: the turn did not start; pressing Enter.")
        gui.press("enter", 1, 0.1)
        time.sleep(1.2)
    win_moveTo(*_HOLD_PARK)
    gui.mouseDown()
    start = time.time()
    try:
        while time.time() - start < _TURN_HOLD_MAX:
            if _turn_over():
                break
            if p.LIMBUS_NAME not in gui.getActiveWindowTitle():
                break
            stop = getattr(p, "stop_event", None)
            if stop is not None and stop.is_set():
                break
            time.sleep(0.3)
    finally:
        gui.mouseUp()
    logging.info("HOLLOW: turn executed, held %.0fs.", time.time() - start)
    time.sleep(0.5)


# --- the two kinds of turn -------------------------------------------------

def _swap_in_the_ego(gear_start, gear_end, slot_x):
    """After win rate: the E.G.O sits in the bottom card of Faust's column
    and win rate sometimes chains the Skill 3 on top instead. When the
    project's own Skill 3 detection sees an S3 chained on her column, one
    click on her bottom card swaps the E.G.O in. The chain's start gear is
    never touched: a drag from it resets the whole chain."""
    if gear_start is None or gear_end is None:
        return False                      # no gears seen: nothing to read
    from .battle import (skill3_columns, _skill_count, _slot_to_column,
                         _SAIKAI_S3_BOTTOM_OFF)
    width = int(round(gear_end[0] - gear_start[0] - 200))
    if width < 33:
        return False
    columns = max(1, _skill_count(gear_start, gear_end))
    column = _slot_to_column(slot_x, gear_start, columns) if columns > 1 else 0

    def s3_on_top():
        try:
            band = screenshot(region=(int(round(gear_start[0] + 100)), 775,
                                      width, 10))
            return column in skill3_columns(band, gear_start, columns)
        except Exception as exc:
            logging.debug("HOLLOW: skill 3 read failed: %s", exc)
            return False

    if not s3_on_top():
        return False
    bottom_y = int(gear_start[1] - 46 + _SAIKAI_S3_BOTTOM_OFF)
    win_click(slot_x, bottom_y, tsize=(20, 20))
    time.sleep(0.6)
    still = s3_on_top()
    logging.info("HOLLOW: Skill 3 was chained on Faust's column; clicked her "
                 "bottom card (%d, %d) for the E.G.O%s.", slot_x, bottom_y,
                 " but the Skill 3 still shows" if still else "")
    return True


def _drag_chain_due() -> bool:
    """The floor 1 boss: the turn is chained by hand, not by win rate. (A
    run resumed inside a fight has no node name and win rates.)"""
    return (int(getattr(p, "LVL", 1) or 1) in _DRAG_CHAIN_FLOORS
            and getattr(p, "HOLLOW_NODE", "") == "Boss")


def _drag_in_the_ego(gear_start, gear_end) -> bool:
    """Chain the turn the way SAIKAI picks a skill: one drag from the start
    gear through every column, each taken at its BOTTOM card (where the
    E.G.O always sits), out past the end gear, which starts the turn. True
    when the turn started."""
    from .battle import chain, _skill_count, _SAIKAI_S3_BOTTOM_OFF
    columns = max(1, _skill_count(gear_start, gear_end))
    width = max(1, int(round(gear_end[0] - gear_start[0] - 200)))
    band = screenshot(region=(int(round(gear_start[0] + 100)), 775, width, 10))
    chain(gear_start, gear_end, band, execute=True,
          force_offsets={col: _SAIKAI_S3_BOTTOM_OFF for col in range(columns)})
    time.sleep(1.0)
    started = not now.button("winrate")
    logging.info("HOLLOW: chained %d column%s through the bottom card; the "
                 "turn %s.", columns, "" if columns == 1 else "s",
                 "started" if started else "did not start, win rate then")
    return started


def chain_turn(gear_start, gear_end):
    """A non-focused turn: overclock Le Trou, slot it, then win rate and the
    swap click if a Skill 3 was chained instead, go. The floor 1 boss is
    chained by the bottom-card drag instead of win rate (with win rate as
    the fallback). The gears may be None when they were not seen (floors 1
    to 3 run this turn regardless)."""
    p.HOLLOW_TURN = int(getattr(p, "HOLLOW_TURN", 0) or 0) + 1
    check_attack_position()
    if _retry_if_due():
        return
    if _with_fallback():
        logging.info("HOLLOW: the fallback squad is fielded; win rate.")
        win_rate()
        execute_and_hold()
        return
    slot, menu = None, False
    if _corroded_now():
        logging.info("HOLLOW: Faust corroded (shop read -45 SP this floor); "
                     "E.G.O is already chosen.")
    else:
        slot, box = find_faust(gear_start, gear_end)
        if box is None:
            logging.info("HOLLOW: no E.G.O menu for Faust; taking her as "
                         "corroded with the E.G.O already chosen.")
        else:
            menu = True
            if p.HOLLOW_TURN == 1:
                overclock(box)
            slot_card(box, overclocked=(p.HOLLOW_TURN == 1))
    if (menu and gear_start is not None and gear_end is not None
            and _drag_chain_due() and _drag_in_the_ego(gear_start, gear_end)):
        execute_and_hold(enter=False)
        return
    win_rate()
    _swap_in_the_ego(gear_start, gear_end, slot or _SOLO_SLOT_X)
    execute_and_hold()


def _runs(flags, min_len):
    """[start, end] index runs of consecutive true flags, min_len or longer."""
    runs, start = [], None
    for i, on in enumerate(flags):
        if on and start is None:
            start = i
        elif not on and start is not None:
            runs.append([start, i - 1])
            start = None
    if start is not None:
        runs.append([start, len(flags) - 1])
    return [r for r in runs if r[1] - r[0] + 1 >= min_len]


def _slot_below(cx, cy, expected):
    """Y to click for the enemy slot under an icon, or None. The slot frame
    is the saturated warm (gold or red) band of rows found around the
    expected distance; its bottom edge is sharp, so the point sits 18 px
    above that, inside the frame whatever its height and whatever warm
    number sits above it. A band that runs out of the window or is taller
    than any frame has swallowed something else, and None lets the caller
    take the measured distance instead."""
    top = cy + expected - _SLOT_SEARCH
    try:
        strip = _frame((cx - 30, top, 60, 2 * _SLOT_SEARCH))
    except Exception as exc:
        logging.debug("HOLLOW: slot strip under (%d, %d) failed: %s", cx, cy, exc)
        return None
    hsv = cv2.cvtColor(strip, cv2.COLOR_BGR2HSV)
    hue, sat, val = hsv[..., 0], hsv[..., 1], hsv[..., 2]
    # Saturation 130 keeps the frames (gold or red, 150 and up) and drops
    # the dull warm ground some arenas have.
    warm = (((hue <= 38) | (hue >= 170)) & (sat >= 130) & (val >= 80)).sum(axis=1)
    merged = []
    for band in _runs(warm >= 12, 1):
        if merged and band[0] - merged[-1][1] < 10:
            merged[-1][1] = band[1]
        else:
            merged.append(band)
    merged = [b for b in merged if b[1] - b[0] + 1 >= 20]
    if not merged:
        return None
    a, b = min(merged, key=lambda b: abs((b[0] + b[1]) / 2 - _SLOT_SEARCH))
    if b >= len(warm) - 1 or b - a + 1 > _SLOT_MAX_HEIGHT:
        return None
    return int(top + b - _SLOT_ABOVE_BOTTOM)


def _enemy_slots():
    """Centres of the enemy skill slots, found by the icon above each at a
    few camera zooms; the icon cut that sees the most icons decides, and
    each slot frame is then looked for under its icon."""
    best, best_name, best_scale = [], None, 1.0
    for name in _ICON_TO_SLOT_DY:
        if name not in PTH:
            continue
        for scale in _ICON_SCALES:
            try:
                boxes = LocateGray.locate_all(PTH[name], region=_ENEMY_BAND,
                                              conf=0.84, comp=scale)
            except Exception as exc:
                logging.debug("HOLLOW: %s @%.2f failed: %s", name, scale, exc)
                continue
            icons = []
            for x, y, w, h in boxes:
                cx, cy = int(x + w / 2), int(y + h / 2)
                if all(abs(cx - fx) > 25 or abs(cy - fy) > 25
                       for fx, fy in icons):
                    icons.append((cx, cy))
            if len(icons) > len(best):
                best, best_name, best_scale = icons, name, scale
            if icons:
                break
    found = []
    for cx, cy in best:
        expected = int(_ICON_TO_SLOT_DY[best_name] * best_scale)
        sy = _slot_below(cx, cy, expected)
        if sy is None:
            sy = cy + expected
            logging.debug("HOLLOW: no slot frame under (%d, %d); %d px down.",
                          cx, cy, expected)
        found.append((cx, sy))
    found.sort()
    if found:
        logging.info("HOLLOW: %d enemy slot(s) by %s at %.2f: %s",
                     len(found), best_name, best_scale, found)
    return found


def _wait_still():
    try:
        from .battle import _thrill_wait_for_still
        _thrill_wait_for_still()
    except Exception:
        time.sleep(1.2)


def _boss_row(slots) -> list:
    """The enemy slots that make up the main body's row: the largest group
    at one height (the Skin Prophet's two candles sit lower, on their own,
    and have endless HP). Ties go to the higher row."""
    if not slots:
        return []
    rows = []
    for x, y in sorted(slots, key=lambda s: s[1]):
        for row in rows:
            if abs(row[0][1] - y) <= 60:        # the row may be a shallow arc
                row.append((x, y))
                break
        else:
            rows.append([(x, y)])
    best = max(rows, key=lambda row: (len(row), -row[0][1]))
    return sorted(best)


def _body_slot(row):
    """The slot to aim at: the one nearest the row's middle. A candle's
    slot sits at the row's end (the Skin Prophet's upper candles share the
    boss's height), the body's slots in between."""
    if not row:
        return None
    mid = (row[0][0] + row[-1][0]) / 2
    return min(row, key=lambda s: abs(s[0] - mid))


def _stable_slots(timeout=4.0, tick=0.2) -> list:
    """Scan for the enemy slots every tick until two readings in a row
    agree (the camera has stopped), then return the boss row. On timeout
    the last reading that found anything."""
    start = time.time()
    prev, last = None, []
    while time.time() - start < timeout:
        cur = _enemy_slots()
        if cur:
            last = cur
            if prev and len(prev) == len(cur) and all(
                    abs(a[0] - b[0]) <= 6 and abs(a[1] - b[1]) <= 6
                    for a, b in zip(sorted(prev), sorted(cur))):
                return _boss_row(cur)
        prev = cur
        time.sleep(tick)
    return _boss_row(last)


def _aim(slot_x: int, attempt: int):
    """Pick the E.G.O up from Faust's slot, wait for the enemy slots to
    hold still, and put it on one of the main body's slots: click then
    click, as the document has it, with a drag as the last resort. Returns
    the target, or None when no slot icon was found."""
    win_click(slot_x + _X_BIAS, _SLOT_Y, tsize=(16, 16), delay=0)
    targets = _stable_slots()
    if not targets:
        logging.warning("HOLLOW: no enemy slot icons found (try %d).",
                        attempt + 1)
        return None
    tx, ty = targets[attempt % len(targets)]
    if attempt == 1:
        ty -= 10                  # a touch higher, towards the frame's middle
    if attempt == 2:
        win_moveTo(slot_x + _X_BIAS, _SLOT_Y)
        time.sleep(0.15)
        win_dragTo((tx, ty), duration=0.45)
    else:
        win_click(tx, ty, tsize=(16, 16), delay=0)
    time.sleep(0.6)
    return (tx, ty)


def _start_shown() -> bool:
    if "hollow_start" not in PTH:
        return True
    return bool(loc.button("hollow_start", (0, 0, 1920, 1080), wait=2))


def _retry_stage() -> bool:
    """Floor 4 and 5 bosses must fall by turn 2: open the pause menu from
    the cog, take Retry Stage, confirm, and start the fight over."""
    if "hollow_retry" not in PTH:
        return False
    win_click(*_RETRY_COG, tsize=(20, 20))
    box = None
    for _ in range(15):
        time.sleep(0.2)
        box = LocateRGB.locate(PTH["hollow_retry"], region=(700, 480, 520, 110),
                               conf=0.85)
        if box:
            break
    if not box:
        logging.warning("HOLLOW: the pause menu did not show Retry Stage.")
        gui.press("esc")
        return False
    win_click(*gui.center(box), tsize=(120, 20))
    wait_while_condition(lambda: not now.button("Confirm_retry",
                                                method=cv2.TM_SQDIFF_NORMED),
                         interval=0.3, timer=4)
    gui.press("space")
    loading_halt()
    p.HOLLOW_TURN = 0
    p.HOLLOW_RETRIES = int(getattr(p, "HOLLOW_RETRIES", 0) or 0) + 1
    logging.info("HOLLOW: boss not down by turn 2; stage retried (%d).",
                 p.HOLLOW_RETRIES)
    return True


def _retry_if_due() -> bool:
    """A floor 4 or 5 boss still standing at turn 3 is retried (three
    times at most per fight)."""
    floor = int(getattr(p, "LVL", 1) or 1)
    if (floor >= 4 and getattr(p, "HOLLOW_NODE", "") == "Boss"
            and int(getattr(p, "HOLLOW_TURN", 0) or 0) >= 3
            and int(getattr(p, "HOLLOW_RETRIES", 0) or 0) < 3):
        return _retry_stage()
    return False


def squad_focused_turn():
    """The fallback squad in a fight with per-skill targeting (the floor 3
    Skin Prophet: win rate would hit its endless candles). Each sinner's
    skill card is picked up and put on the main body's middle slot; all of
    them on one part is fine. The first pick moves the camera, so the slots
    are scanned once, after it, and that body part serves every card."""
    p.HOLLOW_TURN = int(getattr(p, "HOLLOW_TURN", 0) or 0) + 1
    check_attack_position()
    count = min(len(getattr(p, "SELECTED", None) or []), len(_SQUAD_SLOT_XS))
    placed = 0
    target = None
    for i in range(count):
        x = _SQUAD_SLOT_XS[i]
        win_click(x + _X_BIAS, _SQUAD_CARD_Y, tsize=(16, 16), delay=0)
        if target is None:
            target = _body_slot(_stable_slots(timeout=4.0))
            if target is None:
                logging.warning("HOLLOW: no body part found for sinner %d.",
                                i + 1)
                continue
        else:
            time.sleep(0.15)
        win_click(target[0], target[1], tsize=(16, 16), delay=0)
        placed += 1
        time.sleep(0.15)
    if placed and _start_shown():
        logging.info("HOLLOW: %d skill(s) aimed at the body part %s.",
                     placed, target)
    else:
        logging.warning("HOLLOW: could not aim the squad's skills; win rate.")
        win_rate()
    execute_and_hold()


def focused_turn():
    """A focused boss turn. Turn 1: Le Trou into the slot (no overclock) and
    aimed at an enemy slot until START shows. Later turns: win rate. On
    floors 4 and 5 a boss still up at turn 3 is retried."""
    p.HOLLOW_TURN = int(getattr(p, "HOLLOW_TURN", 0) or 0) + 1
    check_attack_position()
    if _retry_if_due():
        return
    turn = p.HOLLOW_TURN
    if turn > 2 or _with_fallback():
        win_rate()
        execute_and_hold()
        return
    slot, box = find_faust()
    if box is None and turn >= 2:
        logging.info("HOLLOW: no E.G.O menu on focused turn %d; win rate.",
                     turn)
        win_rate()
        execute_and_hold()
        return
    if box is None:
        # Corroded: the E.G.O is already in her slot, and in a focused
        # fight it still has to be aimed by hand.
        logging.info("HOLLOW: no E.G.O menu on focused turn 1; aiming the "
                     "slot as it is.")
    else:
        slot_card(box, overclocked=False)
        if turn >= 2:
            win_rate()
            execute_and_hold()
            return
    placed = False
    for attempt in range(3):
        target = _aim(slot or _SOLO_SLOT_X, attempt)
        if target is None:
            time.sleep(0.8)
            continue
        if _start_shown():
            placed = True
            logging.info("HOLLOW: E.G.O aimed at enemy slot %s.", target)
            break
        logging.info("HOLLOW: START not shown after try %d; again.",
                     attempt + 1)
    if not placed:
        logging.warning("HOLLOW: could not aim the E.G.O; win rate instead.")
        win_rate()
    execute_and_hold()


# --- shop ----------------------------------------------------------------

def _heal_target_index():
    """Roster position of the sinner to heal on this floor, or None for no
    heal: Faust on floors 4 and 5, the chosen sinner on floor 1 only."""
    floor = int(getattr(p, "LVL", 1) or 1)
    if floor >= 4:
        return ROSTER.index(FAUST)
    if floor != 1:
        return None
    name = str(getattr(p, "HOLLOW_HEAL", "") or "")
    if name in ROSTER and name != FAUST:
        return ROSTER.index(name)
    return ROSTER.index("YISANG")


def _sp_badge(portrait_index: int, name: str, conf=0.8) -> bool:
    x = _SHOP_PORTRAIT_X[portrait_index]
    dx, dy, w, h = _SP_BADGE_BOX
    return bool(LocateRGB.locate(PTH[name], region=(x + dx, _SHOP_PORTRAIT_Y + dy,
                                                     w, h), conf=conf))


def _at_shop() -> bool:
    return bool(now.button("shop") or now.button("supershop"))


def _heal_row_lit(index: int) -> bool:
    """Whether the sinner's portrait on the heal screen is lit (orange
    frame, can be healed) rather than greyed out (full already). The frame
    ring reads about 190 saturation lit and under 20 greyed."""
    x, y = _SHOP_PORTRAIT_X[index], _SHOP_PORTRAIT_Y
    try:
        patch = _frame((x - 52, y - 52, 104, 92))
    except Exception as exc:
        logging.debug("HOLLOW: heal row read failed: %s", exc)
        return True
    hsv = cv2.cvtColor(patch, cv2.COLOR_BGR2HSV)
    yy, xx = np.mgrid[0:patch.shape[0], 0:patch.shape[1]]
    dist = np.hypot(xx - 52, yy - 52)
    ring = (dist > 38) & (dist < 50) & (hsv[..., 2] > 70)
    if not ring.any():
        return True
    return int(np.median(hsv[..., 1][ring])) >= 100


def _heal_button(name: str):
    """Select, Leave or Return at the heal screen's bottom right."""
    if name not in PTH:
        return None
    return LocateGray.locate(PTH[name], region=_HEAL_BUTTON_REGION, conf=0.9)


def _badge_reads(index: int, name: str, tries: int = 3) -> bool:
    """A badge read repeated over a second: reading it once is proof, a
    single miss on a settling screen is not."""
    for i in range(tries):
        if _sp_badge(index, name, conf=0.9):
            return True
        if i < tries - 1:
            time.sleep(0.3)
    return False


def _leave_heal_menu() -> bool:
    """From the heal screen back to the shop: Return on the type list,
    Leave after a heal. The sinner stage offers no way back at all, so
    there, as the last resort, a sinner who can be healed is picked (100
    cost) to bring Select and then Leave up. True when the shop shows."""
    for _ in range(5):
        if _at_shop():
            return True
        if now.button("ConfirmInvert"):
            gui.press("esc")               # the shop's own Leave was pressed
        elif _heal_button("hollow_heal_leave") or _heal_button("hollow_heal_select"):
            win_click(*_SHOP_CONFIRM, tsize=(80, 20))
        elif now_click.button("return"):
            pass
        else:
            lit = next((i for i in range(len(_SHOP_PORTRAIT_X)) if _heal_row_lit(i)), None)
            if lit is None:
                break
            logging.warning("HOLLOW: the heal screen has no way back; healing "
                            "%s (100 cost) to get out of it.", ROSTER[lit])
            win_click(_SHOP_PORTRAIT_X[lit], _SHOP_PORTRAIT_Y, tsize=(20, 20))
        wait_while_condition(lambda: not (_at_shop() or now.button("return")
                                          or _heal_button("hollow_heal_select")
                                          or _heal_button("hollow_heal_leave")),
                             interval=0.3, timer=2.5)
        time.sleep(0.3)
    return _at_shop()


def shop_visit() -> bool:
    """The heal part of the shop for this run: read Faust's SP, heal one
    sinner when the floor calls for it, and come back to the shop screen
    for the market plan. The heal is judged by the cost dropping. True
    when handled."""
    faust = ROSTER.index(FAUST)
    floor = int(getattr(p, "LVL", 1) or 1)
    if "hollow_sp_corroded" in PTH:
        p.HOLLOW_CORRODED = _sp_badge(faust, "hollow_sp_corroded", conf=_SP_CONF)
        p.HOLLOW_CORRODED_FLOOR = floor
        logging.info("HOLLOW: shop reads Faust %s.",
                     "at -45 SP (corroded)" if p.HOLLOW_CORRODED else "not corroded")
    target = _heal_target_index()
    if target is None:
        logging.info("HOLLOW: no heal on floor %d.", floor)
        return True
    from .shop import balance
    try:
        before = balance()
    except RuntimeError:
        logging.warning("HOLLOW: could not read the cost; no heal this shop.")
        return True
    if before < 100:
        logging.info("HOLLOW: under 100 cost, no heal this shop.")
        return True
    if "hollow_sp45" in PTH and _sp_badge(target, "hollow_sp45", conf=0.9):
        logging.info("HOLLOW: %s already reads 45 SP; no heal needed.",
                     ROSTER[target])
        if target == faust:
            p.HOLLOW_CORRODED = False
        return True
    ClickAction(_SHOP_HEAL_BUTTON, ver="return").execute(click)
    time.sleep(0.4)
    # The type list still has Return and shows every badge; the sinner
    # stage past it cannot be left without healing someone, so the 45 SP
    # question is settled here.
    if "hollow_sp45" in PTH and _badge_reads(target, "hollow_sp45"):
        logging.info("HOLLOW: %s reads 45 SP on the heal screen; nothing to "
                     "heal, Return.", ROSTER[target])
        if target == faust:
            p.HOLLOW_CORRODED = False
        _leave_heal_menu()
        return True
    logging.info("HOLLOW: healing %s (floor %d).", ROSTER[target], floor)
    win_click(*_SHOP_HEAL_SINGLE, tsize=(60, 20))
    time.sleep(0.8)
    if not _heal_row_lit(target):
        # Greyed out: full already, so no Select would ever come for the
        # pick, and this stage has no way back.
        logging.warning("HOLLOW: %s is greyed out on the heal screen (nothing "
                        "to heal).", ROSTER[target])
        if target == faust:
            p.HOLLOW_CORRODED = False
        _leave_heal_menu()
        return True
    win_click(_SHOP_PORTRAIT_X[target], _SHOP_PORTRAIT_Y, tsize=(20, 20))
    wait_while_condition(lambda: not _heal_button("hollow_heal_select"),
                         interval=0.2, timer=2.5)
    if not _heal_button("hollow_heal_select"):
        logging.warning("HOLLOW: Select did not come up for %s; leaving the "
                        "heal screen.", ROSTER[target])
        _leave_heal_menu()
        return True
    # One Select. Clicking that spot again would press Leave on the result
    # screen and then the shop's own Leave.
    win_click(*_SHOP_CONFIRM, tsize=(80, 20))
    if not wait_while_condition(lambda: not now.button("connecting")
                                and not _at_shop(), interval=0.3, timer=4):
        logging.debug("HOLLOW: no connecting flash seen after Select.")
    connection()
    time.sleep(0.6)
    confirmed = False
    if target == faust:
        p.HOLLOW_CORRODED = False
        if "hollow_sp45" in PTH:
            # The 45 badge is close to the 0 and 20 ones; only a tight
            # match means anything. Reading it is proof enough; not reading
            # it is not proof of failure (an event may have cost her SP).
            confirmed = _sp_badge(faust, "hollow_sp45", conf=0.9)
            logging.info("HOLLOW: Faust's badge %s 45 SP after the heal.",
                         "reads" if confirmed else "does not read")
    _leave_heal_menu()
    if confirmed:
        return True
    try:
        after = balance()
    except RuntimeError:
        after = None
    if after is not None and after < before:
        logging.info("HOLLOW: the heal went through (cost %d to %d).", before, after)
    else:
        logging.warning("HOLLOW: the heal may not have gone through (cost %s, "
                        "was %d).", after, before)
    return True
