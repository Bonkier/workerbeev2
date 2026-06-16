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

from .runtime import ops, state
from .teams import HARD as HARD_TEAMS, TEAMS
from .utils import telemetry as tele
from .utils.paths import FLOORS, HARD_FLOORS, PTH, REG
from .utils.utils import (
    SIFTMatcher,
    dump_template_diag,
    floor_limit,
    format_lvl,
    generate_packs_all,
    generate_packs_av,
    generate_packs_pr,
    tap_center,
    wait_while_condition,
)


# Pack Search fallback geometry (FHD), tunable from screenshots.
_SAIKAI_PACK_GRID = (835, 300, 960, 565)     # search-window's pack grid
_SAIKAI_PACK_CONFIRM = (1182, 871)            # black "Confirm" fallback coords
_SAIKAI_PACK_CANCEL = (765, 871)              # cancel coords
# Test toggle: skip the on-screen scan and go straight to Pack Search.
_SAIKAI_FORCE_SEARCH = False

# Floor-banner animation timing: F5/F10 changeovers run a transition
# longer than the usual frame, so let it settle before we read.
_LONG_TRANSITION_LEVELS = {6, 11}
_LONG_TRANSITION_DELAY = 2.0

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
    for upper in range(level, floor_limit()):
        bucket = state.PICK[f"floor{upper}"]
        if name in bucket:
            bucket.remove(name)


# ---------------------------------------------------------- pack eval

def _evaluate_packs(level: int,
                   regions: list[tuple[int, int, int, int]],
                   skip: int, skips: int,
                   strict: bool = False) -> Optional[int]:
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
        for pack in pool:
            if len(packs) >= len(regions):
                break
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
    candidates = priority
    for pass_idx in (0, 1):
        if not candidates:
            break
        for pref in candidates:
            if pref in packs:
                logging.info("Pack: %s", pref)
                tele.floor(level, pref)
                _drop_pack_from_future_floors(level, pref)
                return packs[pref]
        if pass_idx == 0 and skip == skips:
            candidates = state.PICK_ALL[f"floor{level}"]
        else:
            break

    if strict or (skip != skips and priority):
        # SAIKAI strict mode: never settle for a fallback. Signal the
        # caller to fall through to Pack Search.
        return None

    # Filter out the explicitly-banned packs.
    filtered = {pack: i for pack, i in packs.items() if pack not in banned}

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

    winning_slot = max(weight, key=weight.get)
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


# ----------------------------------------------------- SAIKAI pack search

def _saikai_pack_search(level: int) -> bool:
    """SAIKAI fallback: open Pack Search, hunt for the floor's mandatory
    pack, click + confirm + enter. Returns True if a wanted pack was
    secured (so the caller can fall through to the regular pack-pick
    eval and land on it)."""
    wanted = state.PICK.get(f"floor{level}", [])
    if not wanted:
        return False
    if "packsearch" not in PTH:
        logging.warning(
            "SAIKAI: packsearch.png missing; add it to "
            "ImageAssets/UI/saikai/ and relaunch.",
        )
        return False

    logging.info(
        "SAIKAI: opening Pack Search on floor %d (want one of %s)",
        level, wanted,
    )

    # 1. Open Pack Search. tap_center uses a tight jitter so the click
    #    can't slide off a small button onto the surrounding chrome.
    #    wait=5 (was 3) gives the button's entry animation more time to
    #    finish on slower machines before we declare it missing.
    if not tap_center("packsearch", tsize=(60, 24), wait=5):
        # The template matches a fully-rendered pack screen at ~0.9999,
        # so a miss here means the button was covered / mid-animation /
        # off-resolution at poll time. Capture exactly what the bot saw
        # so the next report has hard evidence instead of a guess.
        logging.error("SAIKAI: Pack Search button not located on screen.")
        dump_template_diag("packsearch", "packsearch")
        return False
    time.sleep(0.8)

    # 2. Refresh the offerings (the red logo above the packs).
    if "packrefresh" in PTH:
        tap_center("packrefresh", tsize=(24, 24), wait=3)
        time.sleep(1.0)

    # 2b. Verify we are in the right difficulty UI now (NORMAL banner
    #     on F1-3, HARD banner on F4-5). Best-effort; logged but not
    #     fatal because the banner template can be flaky.
    banner = "hardpackUI" if state.HARD else "normalpackUI"
    if banner in PTH and not ops.find(banner, region=(0, 0, 1920, 1080),
                                       timeout=2):
        logging.warning(
            "SAIKAI: %s banner not detected after refresh; pack UI "
            "or difficulty may be wrong.",
            banner,
        )

    # 3. Hunt for the floor's required pack in the visible grid; scroll
    #    down by one tick and retry up to ten times before giving up.
    grid_x = _SAIKAI_PACK_GRID[0] + _SAIKAI_PACK_GRID[2] // 2
    grid_y = _SAIKAI_PACK_GRID[1] + _SAIKAI_PACK_GRID[3] // 2
    findable = [pk for pk in wanted if ("find" + pk) in PTH]

    for attempt in range(11):
        for pack_name in findable:
            hit = ops.find(
                "find" + pack_name,
                region=_SAIKAI_PACK_GRID,
                mode="gray",
            )
            if hit is None:
                continue
            ops.click_at(hit.center, tsize=(48, 70))
            time.sleep(0.5)
            if not tap_center("packconfirm", tsize=(60, 22), wait=2):
                ops.click_at(_SAIKAI_PACK_CONFIRM)
            time.sleep(0.5)
            ops.press("enter")
            time.sleep(1.0)
            logging.info("SAIKAI: secured %s via Pack Search.", pack_name)
            return True
        if attempt < 10:
            ops.scroll(-3, grid_x, grid_y)
            time.sleep(0.6)

    logging.error(
        "SAIKAI: required pack for floor %d not found in Pack Search; "
        "run compromised. Cancelling out.", level,
    )
    ops.click_at(_SAIKAI_PACK_CANCEL)
    time.sleep(0.5)
    return False


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

    if state.LVL in _LONG_TRANSITION_LEVELS:
        # F5 -> F6 / F10 -> F11 plays a longer transition animation; if
        # we read the floor digits too eagerly the banner is mid-flip
        # and the count comes back wrong.
        time.sleep(_LONG_TRANSITION_DELAY)

    # Hard / Normal toggle on the pack-pick screen. Up to F5 the UI
    # exposes a "Hard" pill at (1349, 64): if the run's effective
    # difficulty doesn't match the pill's current visual state, click
    # to flip it. The `at=` kwarg used to ride on the old `now.button`
    # call as a fallback-click coordinate; the new ops.find rejects it
    # (it would cascade into loader.load() and TypeError), so we do
    # the find-then-click pattern explicitly here.
    if state.LVL <= 5:
        if state.HARD:
            # Need Hard ON: if the marker isn't visible, click to turn it on.
            if not ops.find("hardDifficulty"):
                ops.click_at((1349, 64))
        else:
            # Need Hard OFF: if the marker IS visible, click to turn it off.
            if ops.find("hardDifficulty"):
                ops.click_at((1349, 64))

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

    offset = (5 - card_count) * 161
    regions = [
        (182 + offset + 322 * i, 280, 291, 624)
        for i in range(card_count)
    ]
    refresh_budget = 1 + state.BUFF[2] + int(state.BUFF[2] > 0)

    logging.info("%d packs", card_count)

    strict = (
        state.RUN_SCRIPT == "saikai_ryoshu"
        and bool(state.PICK.get(f"floor{state.LVL}"))
    )

    slot: Optional[int] = None
    if strict and _SAIKAI_FORCE_SEARCH:
        # Testing path: bypass the on-screen scan entirely.
        if _saikai_pack_search(state.LVL):
            time.sleep(1.0)
            slot = _evaluate_packs(state.LVL, regions, 0, 0, strict=False)
    else:
        for skip in range(refresh_budget + 1):
            time.sleep(0.2)
            slot = _evaluate_packs(state.LVL, regions, skip, refresh_budget,
                                  strict=strict)
            if slot is not None:
                break
            if skip != refresh_budget:
                # Click the floor bar's refresh button and let the new
                # pack offering animate in.
                ops.click_at(_FLOOR_BAR_POINT, tsize=_FLOOR_BAR_SIZE)
                time.sleep(2.0)

        # SAIKAI strict + the pack still didn't appear: open Pack
        # Search, then re-evaluate the pack screen non-strictly (so it
        # actually lands on the now-secured pack).
        if strict and slot is None and _saikai_pack_search(state.LVL):
            time.sleep(1.0)
            slot = _evaluate_packs(state.LVL, regions, 0, 0, strict=False)

    if slot is not None:
        x_min, y_min, w, h = regions[slot]
        x = x_min + w // 2 + random.randint(-40, 40)
        y = y_min + h // 2 + random.randint(-175, 175)
        # Drag-pull the pack into the centre lane.
        ops.move_to((x, y))
        ops.drag_to((x, y + 300), duration=0.31)

    wait_while_condition(lambda: ops.find("PackChoice"), interval=0.1)
    if state.LVL != 1:
        state.MOVE_ANIMATION = True
    else:
        time.sleep(0.5)
    return True


__all__ = ["pack"]
