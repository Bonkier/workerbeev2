# SPDX-License-Identifier: GPL-3.0-or-later
"""Floor pack selection.

Drives the per-floor "which pack do we pick" loop:

1. Detect the pack-pick screen ("PackChoice").
2. Read the current floor number from the floor banner.
3. Re-compute the effective difficulty (Normal -> Hard cutover for
   custom runs that start Normal and flip on a chosen floor).
4. Scan the visible pack offerings, score them against the configured
   priority and avoid lists, and drag-pick the winner.

For SAIKAI: the run requires a specific mandatory pack on every floor;
if it doesn't appear after the allowed refreshes, fall through to the
Pack Search UI and find it there.
"""
from __future__ import annotations

import logging
import random
import time
from typing import Iterable, Optional

import cv2

from .pack_search_catalog import PACK_SEARCH_KEYS
from .runtime import ops, state
from .teams import HARD as HARD_TEAMS, TEAMS
from .utils import telemetry as tele
from .utils.paths import FLOORS, HARD_FLOORS, PACK_SECTIONS, PTH, REG
from .utils.utils import (
    LocateGray,
    SIFTMatcher,
    dump_template_diag,
    floor_limit,
    format_lvl,
    generate_packs_all,
    generate_packs_av,
    generate_packs_pr,
    screenshot,
    tap_center,
    wait_while_condition,
)


# Pack Search fallback geometry (FHD), tunable from screenshots.
_SAIKAI_PACK_GRID = (835, 300, 960, 565)     # search-window's pack grid
_SAIKAI_PACK_CONFIRM = (1182, 871)            # black "Confirm" fallback coords
_SAIKAI_PACK_CANCEL = (765, 871)              # cancel coords

# Floor-banner animation timing: F5/F10 changeovers run a transition
# longer than the usual frame, so let it settle before we read.
_LONG_TRANSITION_LEVELS = {6, 11}
_LONG_TRANSITION_DELAY = 2.0
# Pack cards slide into place when a floor opens; PackPull can register
# mid-slide, and SIFT scoring a still-moving card maps it to a neighbour's
# slot (wrong pack). Wait this long after detection before scoring x-positions.
_PACK_SETTLE_DELAY = 1.0

# Floor-bar geometry used by both the floor-number OCR and the move
# step that follows the pack pick.
_FLOOR_BAR_POINT = (1617, 62)
_FLOOR_BAR_SIZE = (240, 60)


# ---------------------------------------------------------- region scan

def _region_index_for_x(x: int,
                       regions: Iterable[tuple[int, int, int, int]]) -> Optional[int]:
    """Find which of `regions` horizontally contains `x` (None if none).

    `regions` are `(x, y, w, h)` rectangles in FHD coords; we only care
    about the horizontal extent here because the pack columns are
    side-by-side and all start at the same y.
    """
    for i, (x1, _, w, _) in enumerate(regions):
        if x1 < x < x1 + w:
            return i
    return None


def _drop_pack_from_future_floors(level: int, name: str) -> None:
    """Once a pack has been picked, remove it from every later floor's
    priority list so we don't try to pick it again. Matches the
    historical behaviour of `remove_pack`."""
    names = {name, _SECTION_BASE.get(name)} | set(_PACK_SECTIONS.get(name, ()))
    for upper in range(level, floor_limit()):
        bucket = state.PICK[f"floor{upper}"]
        for nm in names:
            if nm and nm in bucket:
                bucket.remove(nm)


# ------------------------------------------------------- pack sections
# Some packs ship two card arts that differ ONLY in a trailing section
# number and give different fights (Masquerade Line 4 - Section #3 vs #4).
# Each section is its OWN pack in the picker; the key below is not a pack,
# just the shared banner template used to find the cards. Their banners are
# ~95% identical, so SIFT matches either art on either card and the section
# is resolved by pixel-matching the digit crop immediately right of the
# banner's match box.
_PACK_SECTIONS = PACK_SECTIONS
_SECTION_BASE = {v: base for base, vs in _PACK_SECTIONS.items() for v in vs}
# The winning digit must beat the other by this much, and clear this floor,
# or the card stays generic (behaviour then matches the pre-section builds).
_SECTION_MIN_MARGIN = 0.03
_SECTION_MIN_CONF = 0.45


def _classify_section(base: str, box, image=None) -> Optional[str]:
    """Resolve `base`'s section variant from the card located at `box`
    (the base template's match). Returns the variant key, or None when the
    digits cannot be told apart."""
    variants = [v for v in _PACK_SECTIONS.get(base, ()) if v in PTH]
    if len(variants) < 2:
        return None
    x, y, w, h = box
    # Window just right of the base match, padded for the per-slot scale
    # and perspective drift the pack cards have along the floor bar.
    pad = max(6, h // 4)
    reg = (int(x + w - pad), int(y - pad), int(2 * pad + 40), int(h + 2 * pad))
    win = None
    if image is not None:
        # Locate's _prepare_image only honours `region` when it screenshots,
        # so an offline image has to be cropped here to match live behaviour.
        win = image[reg[1]:reg[1] + reg[3], reg[0]:reg[0] + reg[2]]
        if win.size == 0:
            return None
    scores = {}
    for key in variants:
        try:
            scores[key] = LocateGray.get_conf(PTH[key], image=win, region=reg)
        except (cv2.error, ValueError) as exc:
            # Only matcher-level failures degrade to "generic"; anything else
            # is a real bug and must not hide as an ambiguous read.
            logging.warning("Pack sections: %s scoring failed: %s", key, exc)
    if len(scores) < 2:
        return None
    ranked = sorted(scores.items(), key=lambda kv: kv[1], reverse=True)
    (best, best_c), (_second, second_c) = ranked[0], ranked[1]
    if best_c < _SECTION_MIN_CONF or best_c - second_c < _SECTION_MIN_MARGIN:
        logging.info("Pack sections: %s ambiguous (%s) - staying generic.",
                     base, {k: round(v, 3) for k, v in scores.items()})
        return None
    logging.info("Pack sections: %s -> %s (%s).", base, best,
                 {k: round(v, 3) for k, v in scores.items()})
    return best


def _pack_hit(pref: str, packs: dict) -> Optional[str]:
    """The detected pack key that satisfies preference `pref`: itself, or
    one of its section variants (asking for the base accepts either)."""
    if pref in packs:
        return pref
    for variant in _PACK_SECTIONS.get(pref, ()):
        if variant in packs:
            return variant
    return None


def _pack_banned(pack: str, banned) -> bool:
    """A banned base bans its section variants too."""
    return pack in banned or _SECTION_BASE.get(pack) in banned


# Pack Search: the section cards share one art, so the wanted section is
# resolved by the section digit printed at the bottom of the card. Only the
# "#3" digit is templated - with exactly two sections, the card that is NOT
# a 3 is the 4 (elimination), so no second digit asset is needed.
_PS_SECTION_DIGIT = {"Line4": "ps_line4digit3"}
_PS_DIGIT_MATCH = "Line4Sec3"          # the section that digit belongs to
# Digit box relative to the card's top-left (card art is 157x296).
_PS_DIGIT_BOX = (134, 229, 14, 23)
_PS_DIGIT_HIT = 0.80                   # above -> it IS the templated section


def _find_section_card(stem: str, wanted: str):
    """Find the Pack Search card for section `wanted`. Both sections match
    `stem` (shared art), so every hit is scored on its section digit: the
    best score is the templated section, and with two sections the other
    card is the remaining one. Returns a Match, or None."""
    base = _SECTION_BASE.get(wanted)
    digit = _PS_SECTION_DIGIT.get(base)
    hits = ops.find_all(stem, region=_SAIKAI_PACK_GRID, mode="gray")
    if not hits:
        return None
    if not digit or digit not in PTH:
        logging.warning("PackSearch: no section-digit template for %s - "
                        "cannot tell the sections apart, taking the first "
                        "card.", base)
        return hits[0]
    dx, dy, dw, dh = _PS_DIGIT_BOX
    scored = []
    for h in hits:
        try:
            conf = LocateGray.get_conf(PTH[digit],
                                       region=(h.x + dx, h.y + dy, dw, dh))
        except (cv2.error, ValueError):
            conf = 0.0
        scored.append((h, conf))
    logging.info("PackSearch: %d Line-4 card(s), digit scores %s (want %s).",
                 len(scored), [round(c, 2) for _h, c in scored], wanted)
    if wanted == _PS_DIGIT_MATCH:
        hit, conf = max(scored, key=lambda t: t[1])
        return hit if conf >= _PS_DIGIT_HIT else None
    # The other section: the card that is NOT the templated digit.
    hit, conf = min(scored, key=lambda t: t[1])
    return hit if conf < _PS_DIGIT_HIT else None


# After the Pack Search window closes the secured pack IS on the floor bar,
# but the bar animates in. A single early scan used to miss it and settle for
# an unrelated pack, so insist on the secured pack for a few passes first.
_POST_SEARCH_TRIES = 4
_POST_SEARCH_WAIT = 1.0


def _pick_after_search(level, regions, want, searched_ok):
    """Slot for the pack secured by Pack Search, retried while the floor bar
    settles. Falls back to a normal (non-strict) pick only when the secured
    pack really never shows up, or when the search itself failed."""
    if searched_ok and want:
        for attempt in range(_POST_SEARCH_TRIES):
            slot = _evaluate_packs(level, regions, 0, 0, strict=True, only=want)
            if slot is not None:
                return slot
            if attempt < _POST_SEARCH_TRIES - 1:
                time.sleep(_POST_SEARCH_WAIT)
        logging.warning("PackSearch: secured %s but it never appeared on the "
                        "floor bar after %.0fs - taking a normal pick.",
                        want, _POST_SEARCH_TRIES * _POST_SEARCH_WAIT)
    if not _floor_screen_back():
        # Something still covers the floor: a pick here drags on whatever
        # that is. Leave it to the stuck recovery instead.
        logging.warning("PackSearch: the floor screen is not showing after "
                        "Pack Search - no pick made.")
        return None
    return _evaluate_packs(level, regions, 0, 0, strict=False)


def _in_pool(key: str, pool) -> bool:
    """Is `key` offered on this floor? A section base counts as present
    when either of its sections is (the base is not a pack itself)."""
    return key in pool or any(v in pool for v in _PACK_SECTIONS.get(key, ()))


# ---------------------------------------------------------- pack eval

def _evaluate_packs(level: int,
                   regions: list[tuple[int, int, int, int]],
                   skip: int, skips: int,
                   strict: bool = False,
                   only: Optional[str] = None) -> Optional[int]:
    """Score the packs visible on the floor screen and return the index
    of the chosen one (or None to mean "refresh and try again").

    SIFT is used for the per-pack detection because the pack cards are
    scale-variant under the floor bar's slight perspective skew and
    OpenCV's template-match struggles with that; SIFT's keypoint
    descriptors are robust to scale / rotation enough to find the
    pack art reliably across the card width.
    """
    priority = state.PICK[f"floor{level}"]
    banned   = state.IGNORE[f"floor{level}"]
    logging.debug("Pick: %s | Ignore: %s", priority, banned)

    pool = HARD_FLOORS[format_lvl(level)] if state.HARD else FLOORS[format_lvl(level)]
    packs: dict[str, int] = {}

    # Two passes through SIFT so a pack the first pass missed (low key
    # count under noise) still has a chance to be picked up.
    for _ in range(2):
        if len(packs) >= len(regions):
            break
        sift = SIFTMatcher(
            region=(161, 630, 1632, 140),
            nfeatures=3000, contrastThreshold=0.00,
        )
        # Section bases are scanned once per pass, not once per section.
        seen_bases: set[str] = set()
        for pack in pool:
            if len(packs) >= len(regions):
                break
            base = _SECTION_BASE.get(pack)
            if base is not None:
                # Section packs are found through their SHARED banner, once
                # per base: both sections can sit on the floor bar at the same
                # time, so keep locating + masking until every card is seen
                # and classify each by its section digit.
                if base in seen_bases or base not in PTH:
                    continue
                seen_bases.add(base)
                for _dup in range(len(regions)):
                    box = sift.locate(PTH[base])
                    if box is None:
                        break
                    # Classify BEFORE masking: the digit sits just outside the
                    # matched box, but only just.
                    name = _classify_section(base, box) or base
                    sift.mask(box)
                    slot = _region_index_for_x(box[0] + box[2] // 2, regions)
                    if slot is None or slot in packs.values():
                        continue
                    packs[name] = slot
                    if len(packs) >= len(regions):
                        break
                continue
            box = sift.locate(PTH[pack])
            if box is None:
                continue
            x_centre = box[0] + box[2] // 2
            slot = _region_index_for_x(x_centre, regions)
            if slot is not None and slot not in packs.values():
                packs[pack] = slot

    logging.debug("seen packs: %s", packs)

    # Two-pass priority match: first pass = floor-specific pinned
    # picks; on miss in pass 1 (and we still have refreshes left),
    # widen to the global pick-all list and try again.
    # `only` (this floor's configured Pack Search pack) outranks the lot:
    # nothing else may be accepted while we still have refreshes and the
    # search window left, or a merely-prioritised pack that happens to be
    # on offer wins and the configured pack is never hunted.
    candidates = [only] if only else priority
    for pass_idx in (0, 1):
        if not candidates:
            break
        for pref in candidates:
            # A base preference (e.g. Line4) accepts either section variant.
            hit = _pack_hit(pref, packs)
            if hit is not None:
                logging.info("Pack: %s", hit)
                tele.floor(level, hit)
                _drop_pack_from_future_floors(level, hit)
                return packs[hit]
        if only:
            break
        if pass_idx == 0 and skip == skips:
            candidates = state.PICK_ALL[f"floor{level}"]
        else:
            break

    if strict or (skip != skips and priority):
        # SAIKAI strict mode: never settle for a fallback. Signal the
        # caller to fall through to Pack Search.
        return None

    # Filter out the explicitly-banned packs (banning a base bans its sections).
    filtered = {pack: i for pack, i in packs.items()
                if not _pack_banned(pack, banned)}

    if not filtered and skip != skips:
        # All visible packs are banned but we have refreshes left.
        return None

    if not filtered:
        # All visible packs are banned and we've burned every refresh:
        # take whatever is offered, leaving slot 0 alone if a banned
        # pack happens to sit there (historical "May Ayin save us" path).
        if not packs:
            return 0
        ordered = sorted(packs, key=packs.get)
        default_idx = 1 if len(packs) > 1 and 0 in packs.values() else 0
        choice = ordered[default_idx]
        _drop_pack_from_future_floors(level, choice)
        logging.info("Pack: %s", choice)
        tele.floor(level, choice)
        return packs[choice]

    # Best case: score the surviving packs by how many on-screen EGO
    # gift icons each column already has (we want columns LIGHT on
    # gifts, since each pack-pick floor rewards more, and we'd rather
    # take rewards from a column we haven't drained).
    # ops.find_all takes a STEM and resolves it via PTH internally.
    gift_hits = ops.find_all(state.GIFTS[0]["checks"][1])
    owned_xs  = [m.x + m.w for m in ops.find_all("OwnedSmall")]
    fresh_gift_centres = [
        m.center for m in gift_hits
        if all(abs(m.center[0] - ox) >= 25 for ox in owned_xs)
    ]

    slots = sorted(filtered.values())
    slot_regions = [regions[i] for i in slots]
    weight = {i: 0 for i in slots}
    for cx, _ in fresh_gift_centres:
        idx = _region_index_for_x(cx, slot_regions)
        if idx is not None:
            weight[slots[idx]] += 1

    # Pick the lightest column (fewest gifts already there, per the note
    # above); break ties randomly so an all-zero floor (no gifts detected yet)
    # doesn't collapse to slot 0 - and the same pack - every single run.
    min_w = min(weight.values())
    winning_slot = random.choice([s for s, w in weight.items() if w == min_w])
    winning_pack = next(
        (pname for pname, i in filtered.items() if i == winning_slot), None,
    )
    if winning_pack is None:
        return winning_slot

    _drop_pack_from_future_floors(level, winning_pack)
    # Per-pack scoring trace at DEBUG. Shows which slot won and the
    # gift-lightness weight that drove the choice. Quiet at INFO; flip the
    # Logs page to DEBUG to see it.
    if logging.getLogger().isEnabledFor(logging.DEBUG):
        scoreboard = sorted(
            ((p_name, p_slot, weight.get(p_slot, 0))
             for p_name, p_slot in filtered.items()),
            key=lambda t: t[2], reverse=True,
        )
        logging.debug(
            "Pack scoring: %s",
            ", ".join(f"{n}=slot{s}(w{w})" for n, s, w in scoreboard))
    state.RUN_PACKS_PICKED = int(getattr(state, "RUN_PACKS_PICKED", 0) or 0) + 1
    logging.info("Pack: %s (slot %d, run pack-count now %d)",
                 winning_pack, winning_slot, state.RUN_PACKS_PICKED)
    tele.floor(level, winning_pack)
    return winning_slot


# ---------------------------------------------------- floor-number OCR

def _read_floor_number(prev_level: int) -> int:
    """Read the floor-bar digits and return the current floor (1..15).

    Normal and Hard runs stop at floor 5; Extreme goes 1..15 so it
    needs the two-digit OCR path. On ambiguity we fall back to
    `prev_level + 1` (next floor of the same run), then to `prev_level`
    if even that lies outside the run's range.
    """
    digits = list(range(1, 10)) + ([0] if state.EXTREME else [])

    assumed = 0
    best_conf = 0.0
    for digit in digits:
        # ops.find_all takes a template STEM and resolves it via PTH
        # internally; passing the already-resolved path made it KeyError
        # at the template resolver (it tried PTH[full_path]).
        hits = ops.find_all(
            f"lvl{digit}", region=REG["lvl"],
            mode="gray", conf=0.95, nms_threshold=5,
        )
        if len(hits) == 1:
            # The digit appeared once. For non-1 digits we tie-break
            # against the previous best by confidence so the highest-
            # confidence reading wins.
            if digit != 1:
                conf = hits[0].confidence
                if conf < best_conf:
                    continue
                best_conf = conf
                if assumed != 1:
                    assumed //= 10
            assumed = assumed * 10 + digit
        elif len(hits) == 2:
            # Same digit twice => 11 (Extreme-only).
            assumed = 11
            break

    limit = floor_limit()  # 6 Normal, 11 Hard, 16 Extreme
    if assumed in range(1, limit):
        return assumed
    if prev_level + 1 in range(1, limit):
        return prev_level + 1
    return prev_level


# ----------------------------------------------- difficulty cut-over

def _maybe_switch_difficulty(level: int) -> None:
    """Custom runs (e.g. F3-Hard) start Normal and flip to Hard at a
    chosen floor. When we cross that floor, rebuild every per-pack /
    per-team table so the rest of the run reads from the Hard data.
    """
    want_hard = (
        bool(getattr(state, "HARD_TARGET", state.HARD))
        and level >= int(getattr(state, "HARD_FROM_FLOOR", 1))
    )
    if want_hard == state.HARD:
        return

    state.HARD = want_hard
    table = HARD_TEAMS if want_hard else TEAMS
    state.GIFTS = [table[k] for k in state.TEAM]
    if not state.BUFF[3]:
        # No Star Shower this run: trim each team's uptie1 list to a
        # single goal, matching the historical "shorter goal" path.
        state.GIFTS[0]["uptie1"] = {
            k: state.GIFTS[0]["uptie1"][k]
            for k in list(state.GIFTS[0]["uptie1"])[:1]
        }
    logging.info(
        "Difficulty switched to %s on floor %d",
        "HARD" if want_hard else "NORMAL", level,
    )

    # Pack tables differ between Normal and Hard for the remaining
    # floors; rebuild the priority / avoid / pick-all maps.
    state.PICK = generate_packs_pr(state.PRIORITY_INPUT)
    state.IGNORE = generate_packs_av(state.AVOID_INPUT)
    state.PICK_ALL = generate_packs_all(state.PRIORITY_INPUT)


# ----------------------------------------------------- pack search window

# The Pack Search window covers the floor screen, so the floor's PackChoice
# marker coming back is the proof a confirm went through. A confirm that did
# not land used to be logged as "secured" with the window still open; the
# pick that followed dragged on the window and the run stalled there.
_SEARCH_CLOSE_WAIT = 3.0
_SEARCH_CONFIRM_TRIES = 3
_ON_FLOOR = "onfloor"                 # the wanted pack is on the floor bar already
_AVAILABLE_NOTE = (1400, 40, 360, 110)   # "This Theme Pack is already available."
_CARD_BAND = (161, 630, 1632, 140)       # the SIFT band across the five cards
_SEARCH_TAB = (1100, 150, 360, 95)       # the window's NORMAL or HARD tab
_SEARCH_OPEN_WAIT = 3.0
_SEARCH_TAB_WAIT = 1.5
_DIFF = {True: "HARD", False: "NORMAL"}
# The floor screen's Normal/Hard switch, top right: its label reads on the
# left for NORMAL and on the right for HARD.
_PILL = (1230, 28, 265, 84)
_PILL_POINT = (1349, 64)
_PILL_TRIES = 3
_PILL_SETTLE = 0.8


def _wait_cards_still(timeout: float = 4.0, tick: float = 0.25) -> bool:
    """Wait until the pack cards stop moving: two reads of the card band a
    tick apart that agree. True when they did, False at the timeout."""
    deadline = time.time() + timeout
    last = None
    while True:
        try:
            band = cv2.cvtColor(screenshot(region=_CARD_BAND), cv2.COLOR_BGR2GRAY)
        except Exception as exc:
            logging.debug("Pack: card band read failed: %s", exc)
            return False
        if (last is not None and last.shape == band.shape
                and float(cv2.absdiff(last, band).mean()) < 1.5):
            return True
        if time.time() >= deadline:
            return False
        last = band
        time.sleep(tick)


def _cancel_search() -> bool:
    """Close the Pack Search window; True when the floor screen is back.
    With the floor screen showing there is no window to close, and the
    spot of its Cancel button is a gift under a pack there."""
    if _floor_screen_back(0.0):
        return True
    ops.click_at(_SAIKAI_PACK_CANCEL)
    if _floor_screen_back(2.0):
        return True
    ops.press("esc")
    return _floor_screen_back(2.0)


def _search_tab(timeout: float = 0.0) -> Optional[bool]:
    """The difficulty the open search window lists, by its tab: True for
    HARD, False for NORMAL, None when no tab is read within `timeout`."""
    deadline = time.time() + timeout
    while True:
        for name, hard in (("hardpackUI", True), ("normalpackUI", False)):
            if name in PTH and ops.find(name, region=_SEARCH_TAB) is not None:
                return hard
        if time.time() >= deadline:
            return None
        time.sleep(0.2)


def _tab_scores() -> str:
    """How close each tab template comes in the tab's spot, for the log."""
    parts = []
    for name in ("hardpackUI", "normalpackUI"):
        hit = (ops.find(name, region=_SEARCH_TAB, conf=0.0)
               if name in PTH else None)
        score = getattr(hit, "confidence", None)
        parts.append("%s %s" % (name, "n/a" if score is None else "%.2f" % score))
    return ", ".join(parts)


def _search_window_open(timeout: float = 0.0) -> bool:
    """The Pack Search window is up: its Confirm button or its tab shows."""
    deadline = time.time() + timeout
    while True:
        if ("packconfirm" in PTH
                and ops.find("packconfirm", region=(0, 0, 1920, 1080),
                             mode="gray") is not None):
            return True
        if _search_tab() is not None:
            return True
        if time.time() >= deadline:
            return False
        time.sleep(0.2)


def _open_search_window(tag) -> bool:
    """Click Pack Search and see its window open. A click that did not
    land, or one the game took twice, leaves the floor screen up: one more
    click then. A screen that is neither is not clicked on."""
    for attempt in (1, 2):
        # tap_center uses a tight jitter so the click can't slide off a
        # small button onto the surrounding chrome.
        if not tap_center("packsearch", tsize=(60, 24),
                          wait=5 if attempt == 1 else 2):
            logging.error("%s: Pack Search button not located on screen.", tag)
            dump_template_diag("packsearch", "packsearch")
            return False
        if _search_window_open(_SEARCH_OPEN_WAIT):
            return True
        if attempt == 2 or not _floor_screen_back(0.0):
            break
        logging.info("%s: the Pack Search window did not open; clicking "
                     "once more.", tag)
    logging.warning("%s: the Pack Search window did not open; nothing is "
                    "searched.", tag)
    dump_template_diag("packsearch_closed", "packsearch", "packconfirm")
    return False


def _marked_unselectable(hit) -> bool:
    """The grid card at `hit` wears the red Unselectable label: the floor
    bar already offers that pack."""
    if "unselectable" not in PTH:
        return False
    cx, cy = hit.center
    return ops.find("unselectable", region=(cx - 110, cy - 125, 220, 70),
                    mode="gray") is not None


def _already_available() -> bool:
    """The game's note that the clicked pack is already on the floor bar."""
    return ("packavailable" in PTH
            and ops.find("packavailable", region=_AVAILABLE_NOTE,
                         mode="gray") is not None)


def _floor_screen_back(timeout: float = _SEARCH_CLOSE_WAIT) -> bool:
    deadline = time.time() + timeout
    while True:
        if ops.find("PackChoice"):
            return True
        if time.time() >= deadline:
            return False
        time.sleep(0.2)


def _find_search_card(stem, key):
    if key in _SECTION_BASE:
        return _find_section_card(stem, key)
    return ops.find(stem, region=_SAIKAI_PACK_GRID, mode="gray")


def _confirm_search_card(hit):
    ops.click_at(hit.center, tsize=(48, 70))
    time.sleep(0.5)
    if not tap_center("packconfirm", tsize=(60, 22), wait=2):
        ops.click_at(_SAIKAI_PACK_CONFIRM)
    time.sleep(0.5)
    ops.press("enter")
    time.sleep(1.0)


def _secure_search_pick(stem, key, hit, tag):
    """Select the card at `hit`, confirm, and make sure the window closed.
    True: the floor screen is back. _ON_FLOOR: the game said the pack is on
    the floor bar already, so the window was cancelled to take it there.
    False: the pick would not go through and the window was cancelled.
    None: neither the floor nor the window could be recognised (the caller
    carries on as before)."""
    _confirm_search_card(hit)
    if _already_available():
        logging.info("%s: the game says %s is already available on the floor "
                     "bar; cancelling Pack Search to take it there.", tag, key)
        _cancel_search()
        return _ON_FLOOR
    if _floor_screen_back():
        return True
    # A second prompt can come up after the Enter above was already sent.
    ops.press("enter")
    if _floor_screen_back(2.0):
        return True

    window_open = False
    for attempt in range(2, _SEARCH_CONFIRM_TRIES + 1):
        hit = _find_search_card(stem, key)
        if hit is None:
            break
        window_open = True
        logging.warning("%s: Pack Search still open after confirming %s - "
                        "selecting it again (attempt %d of %d).",
                        tag, key, attempt, _SEARCH_CONFIRM_TRIES)
        _confirm_search_card(hit)
        if _floor_screen_back():
            return True

    if not window_open and "packconfirm" in PTH:
        window_open = ops.find("packconfirm", region=(0, 0, 1920, 1080),
                               mode="gray") is not None
    dump_template_diag("packsearch_open", "PackChoice", "packconfirm")
    if not window_open:
        logging.warning("%s: the floor screen did not come back after "
                        "confirming %s, and the search window is not "
                        "recognised either.", tag, key)
        return None

    logging.warning("%s: %s could not be confirmed - cancelling Pack Search.",
                    tag, key)
    _cancel_search()
    return False


def _pack_search_window(level, candidates, tag):
    """Open Pack Search and hunt `candidates` [(template_stem, pack_key)]
    in the grid; click + confirm + enter the first hit. Returns the
    secured pack_key, or None. Shared by the SAIKAI script and the
    user-configured pack-search fallback."""
    if not candidates:
        return None
    if "packsearch" not in PTH:
        logging.warning(
            "%s: packsearch.png missing; add it to "
            "ImageAssets/UI/saikai/ and relaunch.", tag,
        )
        return None

    logging.info(
        "%s: opening Pack Search on floor %d (want one of %s)",
        tag, level, [key for _stem, key in candidates],
    )

    # 1. Open Pack Search, and see it open.
    if not _open_search_window(tag):
        return None

    # 2. The window's tab names the difficulty it lists. The other one
    #    means the floor's switch is wrong: close, set it, open again.
    want_hard = bool(state.HARD)
    tab = _search_tab(_SEARCH_TAB_WAIT)
    if tab is not None and tab != want_hard:
        logging.warning("%s: the search window lists %s packs on a %s "
                        "floor; setting the floor's difficulty and opening "
                        "it again.", tag, _DIFF[tab], _DIFF[want_hard])
        _cancel_search()
        _set_difficulty(want_hard)
        if not _open_search_window(tag):
            return None
        tab = _search_tab(_SEARCH_TAB_WAIT)
        if tab is not None and tab != want_hard:
            logging.warning("%s: it still lists %s packs; no search on "
                            "floor %d.", tag, _DIFF[tab], level)
            _cancel_search()
            return None
    if tab is None:
        logging.warning("%s: the search window's difficulty tab was not "
                        "read (%s); searching it as it is.", tag, _tab_scores())
    # Let the grid finish drawing before the first look at it.
    time.sleep(1.0)

    # 3. Hunt for a wanted pack in the visible grid; scroll down by one
    #    tick and retry up to ten times before giving up.
    grid_x = _SAIKAI_PACK_GRID[0] + _SAIKAI_PACK_GRID[2] // 2
    grid_y = _SAIKAI_PACK_GRID[1] + _SAIKAI_PACK_GRID[3] // 2

    for attempt in range(11):
        for stem, key in candidates:
            hit = _find_search_card(stem, key)
            if hit is None:
                continue
            if _marked_unselectable(hit):
                logging.info("%s: %s is marked Unselectable in Pack Search: the "
                             "floor bar already offers it. Cancelling the "
                             "window to take it there.", tag, key)
                _cancel_search()
                return key
            closed = _secure_search_pick(stem, key, hit, tag)
            if closed == _ON_FLOOR:
                return key
            if closed is False:
                return None
            if closed:
                logging.info("%s: secured %s via Pack Search.", tag, key)
            return key
        if attempt < 10:
            ops.scroll(-3, grid_x, grid_y)
            time.sleep(0.6)

    logging.error(
        "%s: no wanted pack for floor %d found in Pack Search. "
        "Cancelling out.", tag, level,
    )
    _cancel_search()
    return None


def _configured_search_candidates(level):
    """[(template_stem, pack_key)] for the user's configured Pack Search
    pick on this floor (one pack per floor), if it belongs to the current
    difficulty's pool."""
    name = (getattr(state, "PACK_SEARCH_FLOORS", None) or {}).get(level)
    if not name or name not in PACK_SEARCH_KEYS:
        return []
    key = PACK_SEARCH_KEYS[name]
    pool = HARD_FLOORS[format_lvl(level)] if state.HARD else FLOORS[format_lvl(level)]
    if not _in_pool(key, pool):
        return []
    stem = _ps_stem(name, key)
    return [(stem, key)] if stem else []


def _ps_stem(name: str, key: str):
    """Pack Search card template for a configured pick. Sections share the
    base's card art (they differ only by the printed section number), so they
    borrow its template and are separated later by the digit."""
    own = "ps_" + name
    if own in PTH:
        return own
    base = _SECTION_BASE.get(key)
    if base:
        for base_name, base_key in PACK_SEARCH_KEYS.items():
            if base_key == base and ("ps_" + base_name) in PTH:
                return "ps_" + base_name
    return None


def _configured_pack_search(level: int) -> bool:
    """User-configured fallback: hunt the Packs-tab picks via Pack Search.
    On success the secured pack is pushed to the front of this floor's
    priority so the follow-up non-strict evaluate lands on it."""
    key = _pack_search_window(
        level, _configured_search_candidates(level), "PackSearch")
    if key is None:
        return False
    pick_list = state.PICK.setdefault(f"floor{level}", [])
    if key in pick_list:
        pick_list.remove(key)
    pick_list.insert(0, key)
    return True


# ------------------------------------------------- the difficulty switch

def _difficulty_shown() -> Optional[bool]:
    """What the floor screen's Normal/Hard switch reads: True for HARD,
    False for NORMAL, None when it reads as neither or as both."""
    hard = "pillHard" in PTH and ops.find("pillHard", region=_PILL) is not None
    normal = ("pillNormal" in PTH
              and ops.find("pillNormal", region=_PILL) is not None)
    return None if hard == normal else hard


def _set_difficulty(want_hard: bool) -> None:
    """Put the floor screen's Normal/Hard switch where the run wants it.
    The switch is read before and after each click, so a click the game
    took twice, or not at all, is made again. When the switch cannot be
    read the HARD banner under the title decides, with one click."""
    for _ in range(_PILL_TRIES):
        shown = _difficulty_shown()
        if shown is None:
            if bool(ops.find("hardDifficulty")) != want_hard:
                ops.click_at(_PILL_POINT)
            return
        if shown == want_hard:
            return
        logging.info("Pack: the floor is set to %s; switching it to %s.",
                     _DIFF[shown], _DIFF[want_hard])
        ops.click_at(_PILL_POINT)
        time.sleep(_PILL_SETTLE)
    logging.warning("Pack: the difficulty switch still does not read %s.",
                    _DIFF[want_hard])


# ---------------------------------------------------- main entry point

def pack() -> bool:
    """Pick a pack on the current floor. Returns True if a pack was
    selected (we landed on the pack-pull screen), False if there was no
    pack-pick to do this loop tick (e.g. we're on a fight or event node).
    """
    if not ops.find("PackChoice"):
        return False

    state.LVL = _read_floor_number(state.LVL)
    _maybe_switch_difficulty(state.LVL)
    stuck = state.PACK_STUCK
    if stuck["level"] != state.LVL:
        stuck.update(level=state.LVL, fails=0)

    if state.LVL in _LONG_TRANSITION_LEVELS:
        # F5 -> F6 / F10 -> F11 plays a longer transition animation; if
        # we read the floor digits too eagerly the banner is mid-flip
        # and the count comes back wrong.
        time.sleep(_LONG_TRANSITION_DELAY)

    # Up to F5 the pack screen has a Normal/Hard switch: it is put where
    # the run's difficulty for this floor wants it.
    if state.LVL <= 5:
        _set_difficulty(bool(state.HARD))

    # Per-run tally for the dungeon_end recap. Bumped once per
    # pack-choice screen, not per detection, so a re-probe on the same
    # floor doesn't double-count.
    state.RUN_FLOORS_ENTERED = int(
        getattr(state, "RUN_FLOORS_ENTERED", 0) or 0) + 1
    logging.info("Floor %d (run floor-count now %d, %s difficulty)",
                 state.LVL, state.RUN_FLOORS_ENTERED,
                 "HARD" if state.HARD else "NORMAL")

    # Park the cursor over the floor bar; the bar template detection
    # below assumes the cursor isn't covering the read area.
    ops.move_to(_FLOOR_BAR_POINT, tsize=_FLOOR_BAR_SIZE)
    time.sleep(0.2)

    # Read how many pack columns are on screen. Up to five; the
    # leftmost can be narrower so the cap derives from the column's
    # x-extent.
    card_count = 5
    deadline = time.time() + 4.0
    box = None
    while box is None and time.time() < deadline:
        time.sleep(0.2)
        box = ops.find("PackPull", region=REG["PackPull"], mode="gray")
    if box is not None:
        center_x, _ = box.center
        card_count = 5 - min(max(center_x - 21, 1) // 157, 2)

    # Let the cards finish sliding in before SIFT scores their x-positions,
    # otherwise a still-moving card gets mapped to its neighbour's slot.
    time.sleep(_PACK_SETTLE_DELAY)
    _wait_cards_still()

    offset = (5 - card_count) * 161
    regions = [
        (182 + offset + 322 * i, 280, 291, 624)
        for i in range(card_count)
    ]
    refresh_budget = 1 + state.BUFF[2] + int(state.BUFF[2] > 0)
    # "Pack refreshes" (General tab) caps the grace-derived budget; the
    # default 7 sits above any derivable value, so untouched configs keep
    # the historical behaviour.
    refresh_budget = min(refresh_budget,
                         int(getattr(state, "PACK_REFRESHES", 7)))

    logging.info("%d packs", card_count)

    # User-configured Pack Search fallback (Floor Packs/Market tab). SAIKAI honours it
    # like ordinary runs - the script's priorities still steer the pick and
    # the refresh hunt, but the search window opens only when the user
    # configured this floor.
    _cands = _configured_search_candidates(state.LVL)
    if stuck["fails"]:
        # The last pick on this floor did not take: no second round of
        # refreshes and searching, only the pick.
        logging.warning("Pack: the floor screen stayed up after the last "
                        "pick (%d in a row); picking again as it is.",
                        stuck["fails"])
        _cands = []
        refresh_budget = 0
    custom_search = bool(_cands)
    strict = custom_search
    # The configured pack itself: while hunting it (refreshes + the search
    # window) it is the ONLY acceptable pick on this floor.
    want = _cands[0][1] if _cands else None
    if want:
        logging.info("PackSearch: floor %d wants %s - refreshing for it, "
                     "then Pack Search.", state.LVL, want)

    do_search = bool(getattr(state, "PACK_SEARCH", True))

    slot: Optional[int] = None
    if not do_search:
        # Pack search off: one non-refreshing pass. Lands on a configured
        # priority pack if it is on offer, else a ban-filtered fallback;
        # never refreshes. The configured Pack Search fallback still
        # applies: a strict pass first, then the search window on a miss.
        time.sleep(0.2)
        slot = _evaluate_packs(state.LVL, regions, 0, 0, strict=custom_search,
                               only=want)
        if custom_search and slot is None:
            searched = _configured_pack_search(state.LVL)
            if searched:
                time.sleep(1.0)
            slot = _pick_after_search(state.LVL, regions, want, searched)
    else:
        for skip in range(refresh_budget + 1):
            time.sleep(0.2)
            slot = _evaluate_packs(state.LVL, regions, skip, refresh_budget,
                                  strict=strict, only=want)
            if slot is not None:
                break
            if skip != refresh_budget:
                # Click the floor bar's refresh button and let the new
                # pack offering animate in, however long that takes: a
                # read taken mid-slide misses the very pack it hunts.
                ops.click_at(_FLOOR_BAR_POINT, tsize=_FLOOR_BAR_SIZE)
                time.sleep(1.0)
                _wait_cards_still()

        # The configured pack still didn't appear: open Pack Search, then
        # re-evaluate non-strictly (so the pick lands on the now-secured
        # pack); a failed search degrades to a normal pick.
        if slot is None and custom_search:
            searched = _configured_pack_search(state.LVL)
            if searched:
                time.sleep(1.0)
            slot = _pick_after_search(state.LVL, regions, want, searched)

    if slot is not None:
        x_min, y_min, w, h = regions[slot]
        x = x_min + w // 2 + random.randint(-40, 40)
        y = y_min + h // 2 + random.randint(-175, 175)
        # Drag-pull the pack into the centre lane.
        ops.move_to((x, y))
        ops.drag_to((x, y + 300), duration=0.31)

    if wait_while_condition(lambda: ops.find("PackChoice"), interval=0.1):
        stuck.update(level=None, fails=0)
    else:
        stuck["fails"] += 1
        logging.warning("Pack: the floor screen is still up after the pick "
                        "(%d in a row).", stuck["fails"])
        if stuck["fails"] == 2:
            dump_template_diag("pack_pick_stuck", "PackChoice")
    if state.LVL != 1:
        state.MOVE_ANIMATION = True
    else:
        time.sleep(0.5)
    return True


__all__ = ["pack"]
