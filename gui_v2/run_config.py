# SPDX-License-Identifier: GPL-3.0-or-later
"""Maps the v2 UI's configuration into the structures the bot expects.

The bot wants:
  settings: dict with bonus/restart/altf4/enkephalin/skip/buff/card/
            wishmaking/winrate/infinity/keywordless
  teams:    int-keyed dict. Keys < 7 are Mirror Dungeon teams; keys >= 7
            are Luxcavation teams (key 7+i selects lux affinity i). Each
            entry: affinity (indices into the 10 status types), affinity_idx,
            duplicates, sinners (indices into the bot's SINNERS order),
            priority/avoid (raw pack-key lists).

Mapping rules:
  - affinity  = the team's status/damage chips (sins are labels only);
                all selected status chips are passed, first = primary.
  - sinners   = the per-team-type sinner selection from Settings, matched
                by the team's primary status; fallback = default six.
  - packs     = per-floor picks flattened and applied to every team.
"""

# Bot status-type order (= teams.py / stats.py key order). Index into this
# is what the bot's `affinity` field stores.
_STATUS_ORDER = (
    "Burn", "Bleed", "Tremor", "Rupture", "Sinking",
    "Poise", "Charge", "Slash", "Pierce", "Blunt",
)
_STATUS_INDEX = {name: i for i, name in enumerate(_STATUS_ORDER)}

# UI sinner display name -> bot SINNERS index. Canonical in-game order:
# YISANG..SINCLAIR, OUTIS, GREGOR (Outis = 10, Gregor = 11). The Settings
# sinner grid and the Thrill exclusion grid both follow this order. Map by
# name, never by position, so a UI reorder cannot drift the click target.
_SINNER_INDEX = {
    "Yi Sang": 0, "Faust": 1, "Don Quixote": 2, "Ryōshū": 3,
    "Meursault": 4, "Hong Lu": 5, "Heathcliff": 6, "Ishmael": 7,
    "Rodion": 8, "Sinclair": 9, "Outis": 10, "Gregor": 11,
}
_DEFAULT_SINNERS = [0, 1, 2, 3, 4, 5]

# Reward-card display order = the bot's canonical index order.
_CARD_ORDER = ("Cost + Gift", "Cost", "Gift", "Resource", "Starlight")
_DEFAULT_CARD = [1, 0, 2, 3, 4]

# Starting-grace order = BUFF index order.
_GRACE_ORDER = (
    "Star of the Beginning", "Cumulating Starcloud", "Interstellar Travel",
    "Star Shower", "Binary Star Shop", "Moon Star Shop",
    "Favor of the Nebula", "Starlight Guidance", "Chance Comet",
    "Perfected Possibility",
)

# Lux affinity order (lux.py's lux_list). Lux team key = 7 + index here.
_LUX_ORDER = (
    "Slash", "Pierce", "Blunt", "Wrath", "Lust",
    "Sloth", "Gluttony", "Gloom", "Pride", "Envy",
)


# --- SAIKAI [Ryoshu] scripted preset ---------------------------------------
# Hand-scripted Ryoshu run. As a custom-run strategy it ignores the page's
# team / difficulty / grace / pack inputs and pins the build below; the
# backend recognises it via settings["run_script"].
SAIKAI_LABEL = "SAIKAI [Ryoshu]"
SAIKAI_SCRIPT = "saikai_ryoshu"
# Graces: Star of the Beginning (0), Interstellar Travel (2), Star Shower (3).
_SAIKAI_BUFF = [1, 0, 1, 1, 0, 0, 0, 0, 0, 0]
# Sinner order (indices into the bot's SINNERS): Ryoshu, Sinclair, Hong Lu,
# Faust, Ishmael, Don Quixote, Yi Sang.
_SAIKAI_SINNERS = [3, 9, 5, 1, 7, 2, 0]
# Provisional primary affinity. Drives in-game team selection (by keyword
# image) and the early gift pool; the run leans on Poise before its Slash T4
# phase. Revisit once tested in-game.
_SAIKAI_AFFINITY = "Poise"

# Mandatory packs per floor. Format matches generate_packs_*:
# (pack_list, {pack: pinned_floor}). FlatbrokeGamblers and HellsChicken are
# pinned because they also appear in other floors' pools; the rest stay
# unpinned so the bot prioritises them in list order on every eligible floor.
_SAIKAI_PRIORITY = (
    ["FlatbrokeGamblers", "HellsChicken", "HatredandDespair", "TobeCleaved",
     "Line2", "Line4", "Line1"],
    {"FlatbrokeGamblers": 1, "HellsChicken": 2},
)
_SAIKAI_AVOID = ([], {"FlatbrokeGamblers": 1, "HellsChicken": 2}, {})


# --- Thrill scripted preset (work in progress) -----------------------------
# Normal-mode Rupture run: swaps in max-energy IDs at squad select, pins
# hard-coded graces + Floor 1-3 packs, crafts the Thrill T4 EGO gift, and
# forfeits after Floor 3. The swap, craft and forfeit are bespoke backend
# logic gated by settings["run_script"] == THRILL_SCRIPT.
THRILL_LABEL = "Thrill"
THRILL_SCRIPT = "thrill"
# Graces: Star of the Beginning (0), Star Shower (3), Perfected Possibility (9).
_THRILL_BUFF = [1, 0, 0, 1, 0, 0, 0, 0, 0, 1]
_THRILL_AFFINITY = "Rupture"
# Floor 1-3 mandatory packs (Normal pools), unpinned so the bot prioritises
# them in list order on every eligible floor.
_THRILL_PRIORITY = (
    ["TheForgotten", "NestWorkshopandTechnology", "FlatbrokeGamblers"],
    {},
)
# Packs never taken: they tank the Rupture-stacking strategy (or, like
# AutomatedFactory, add no synergy and waste a priority slot).
_THRILL_AVOID = (
    ["EmotionalSubservience", "HatredandDespair",
     "EmotionalSeduction", "FaithErosion",
     "EmotionalFlood", "NagelundHammer",
     "AutomatedFactory"],
    {},
    {},
)


def _build_saikai_run(md_state: dict):
    """Fixed (count, teams, settings, hard) for the SAIKAI [Ryoshu] run.

    Pins graces, sinner order, the Normal->Hard-at-F4 difficulty and the
    run_script flag. Squad order is the user's SAIKAI picker order minus
    exclusions, falling back to the scripted _SAIKAI_SINNERS default."""
    settings = build_settings(md_state)
    # Graces: respect the user's BUILD-panel pick (already in settings["buff"]),
    # falling back to the scripted default only when every grace is 0.
    if not any(settings["buff"]):
        settings["buff"] = list(_SAIKAI_BUFF)
    settings["infinity"] = False            # never Extreme
    settings["winrate"] = False             # the battle script decides winrate
    # Default flips Normal -> Hard at F4; "Hard from F1" option runs Hard throughout.
    settings["hard_from_floor"] = (
        1 if md_state.get("saikai_only_hard") else 4
    )
    settings["run_script"] = SAIKAI_SCRIPT

    excluded = set(md_state.get("saikai_exclude") or [])
    order_names = [n for n in (md_state.get("saikai_order") or [])
                   if n not in excluded]
    user_order_idx = [_SINNER_INDEX[n] for n in order_names
                      if n in _SINNER_INDEX]
    sinners = user_order_idx or list(_SAIKAI_SINNERS)

    teams = {0: {
        # Poise primary (drives in-game team select + early gifts), Slash second
        # so the market fuses a Tier-4 Poise gift then a Tier-4 Slash gift.
        # Only Poise is picked in-game (p.TEAM[0]).
        "affinity": [_STATUS_INDEX[_SAIKAI_AFFINITY], _STATUS_INDEX["Slash"]],
        "affinity_idx": 0,
        "duplicates": False,
        "sinners": sinners,
        "priority": _SAIKAI_PRIORITY,        # mandatory per-floor packs
        "avoid": _SAIKAI_AVOID,
    }}
    count = int(md_state.get("run_count", 1) or 1)
    hard = True                              # ultimate difficulty (active from F4)
    return count, teams, settings, hard


def _build_thrill_run(md_state: dict):
    """Fixed (count, teams, settings, hard) for the Thrill run: Normal-mode
    Rupture, hard-coded graces/packs, forfeit after Floor 3. The squad swap
    and EGO-gift craft are backend logic gated by run_script == THRILL_SCRIPT."""
    settings = build_settings(md_state)
    settings["buff"] = list(_THRILL_BUFF)
    settings["infinity"] = False             # Normal mode, never Extreme
    settings["winrate"] = False
    settings["hard_from_floor"] = 99         # never flips to Hard
    settings["forfeit_floor"] = 3            # forfeit after Floor 3
    settings["run_script"] = THRILL_SCRIPT
    # SINNERS indices the swap leaves alone. Capped at 12 (total sinner count).
    settings["thrill_exclude"] = [
        _SINNER_INDEX[n] for n in (md_state.get("thrill_exclude") or [])
        if n in _SINNER_INDEX
    ][:12]

    # Ranked preference: first 6 fill the squad slots, the rest are fallback
    # priority if the team-edit dialog rejects any of the top 6.
    thrill_order_names = md_state.get("thrill_order") or []
    thrill_order_idx = [_SINNER_INDEX[n] for n in thrill_order_names
                        if n in _SINNER_INDEX][:12]

    teams = {0: {
        "affinity": [_STATUS_INDEX[_THRILL_AFFINITY]],
        "affinity_idx": 0,
        "duplicates": False,
        "sinners": thrill_order_idx or list(_DEFAULT_SINNERS),
        "priority": _THRILL_PRIORITY,
        "avoid": _THRILL_AVOID,
    }}
    count = int(md_state.get("run_count", 1) or 1)
    hard = False                             # Normal mode
    return count, teams, settings, hard


def _build_packs(packs: dict, global_packs: dict | None = None):
    """Convert the UI's per-floor + Global pack picks into generate_packs_* shapes:
        priority -> (priority_packs, {pack: floor})
        avoid    -> (avoid_packs, {pack: floor} (priority), {pack: floor} (avoid))

    Per-floor picks pin to their floor; Global picks carry no floor entry, so
    the bot applies them on every eligible floor. A per-floor pick overrides
    the Global default for that floor."""
    pri_packs, avo_packs = [], []
    pri_floor, avo_floor = {}, {}

    # Per-floor explicit picks, pinned to their floor. Floor key 0 is not real.
    for floor_key, floor_packs in (packs or {}).items():
        try:
            floor = int(floor_key)
        except (TypeError, ValueError):
            continue
        if floor <= 0 or not isinstance(floor_packs, dict):
            continue
        for pack, state in floor_packs.items():
            if state == "priority":
                if pack not in pri_packs:
                    pri_packs.append(pack)
                pri_floor[pack] = floor
            elif state == "avoid":
                if pack not in avo_packs:
                    avo_packs.append(pack)
                avo_floor[pack] = floor

    # Global picks: no floor entry. A pack already pinned per-floor keeps its pin.
    for pack, state in (global_packs or {}).items():
        if state == "priority":
            if pack not in pri_packs:
                pri_packs.append(pack)
        elif state == "avoid":
            if pack not in avo_packs:
                avo_packs.append(pack)

    priority = (pri_packs, pri_floor)
    avoid = (avo_packs, pri_floor, avo_floor)
    return priority, avoid


def _sinners_for(team_status: str, sinner_sel: dict) -> list:
    names = (sinner_sel or {}).get(team_status)
    if not names:
        return list(_DEFAULT_SINNERS)
    idx = [_SINNER_INDEX[n] for n in names if n in _SINNER_INDEX]
    return idx or list(_DEFAULT_SINNERS)


def build_settings(md_state: dict) -> dict:
    """Build the bot's `settings` dict from the Mirror Dungeon UI state."""
    beh = md_state.get("behaviour", {}) or {}
    grace = md_state.get("grace", {}) or {}
    difficulty = md_state.get("difficulty", "Hard")

    card_order = md_state.get("card") or list(_CARD_ORDER)
    card = [_CARD_ORDER.index(n) for n in card_order if n in _CARD_ORDER]
    if len(card) != 5:
        card = list(_DEFAULT_CARD)

    # Keywordless EGO gift collection was removed from the UI. Empty map so
    # the backend's p.KEYWORDLESS consumers still get the key and iterate nothing.
    keywordless = {}

    # Skill Replacement (per-sinner shop swap), stored by the MD page as
    #   {"active": [...], "order": {name: [swap_key, ...]},
    #    "repeats": {name: {swap_key: cap_per_run}}}
    # Passed through unchanged; bot.execute_me deep-copies repeats into
    # SKILL_REPLACE_REMAINING so the in-run counter decrements from the cap.
    skill_replace_raw = md_state.get("skill_replace") or {}
    skill_replace = {
        "active":  list(skill_replace_raw.get("active") or []),
        "order":   dict(skill_replace_raw.get("order")  or {}),
        "repeats": dict(skill_replace_raw.get("repeats") or {}),
    }

    return {
        "bonus": bool(beh.get("bonus", True)),
        "restart": bool(beh.get("restart", True)),
        "altf4": (bool(beh.get("altf4", False)), bool(beh.get("altf4", False))),
        "enkephalin": bool(beh.get("enkephalin", True)),
        "skip": bool(beh.get("skip", True)),
        "buff": [int(grace.get(name, 0)) for name in _GRACE_ORDER],
        "card": card,
        "wishmaking": bool(beh.get("wishmaking", False)),
        "winrate": bool(beh.get("winrate", False)),
        "infinity": difficulty == "Extreme",
        "keywordless": keywordless,
        # Floor at which Hard becomes active (1 = whole run). Overridden by
        # build_md_run for custom runs like "F3 Hard".
        "hard_from_floor": 1,
        # Shop / EGO / heal skip flags -> p.SKIP_* in bot.py, gated in shop.py.
        # All default off so the Behaviour panel stays opt-in.
        "skip_restshop":       bool(beh.get("skip_restshop", False)),
        "skip_ego_check":      bool(beh.get("skip_ego_check", False)),
        "skip_ego_fusion":     bool(beh.get("skip_ego_fusion", False)),
        "skip_ego_enhancing":  bool(beh.get("skip_ego_enhancing", False)),
        "skip_ego_buying":     bool(beh.get("skip_ego_buying", False)),
        "skip_sinner_healing": bool(beh.get("skip_sinner_healing", False)),
        "claim_on_defeat":     bool(beh.get("claim_on_defeat", False)),
        "logout_on_finish":    bool(beh.get("logout_on_finish", False)),
        "skill_replace":       skill_replace,
    }


def build_md_run(md_state: dict, sinner_sel: dict):
    """Return (count, teams, settings, hard) for a Mirror Dungeon run, or
    raise ValueError with a user-facing message if config is unusable."""
    # SAIKAI is a fully scripted preset: it ignores the page inputs below.
    if (md_state.get("custom_run") and
            md_state.get("custom_strategy") == SAIKAI_LABEL):
        return _build_saikai_run(md_state)

    # Thrill: scripted Normal-mode Rupture run. The squad max-energy swap is
    # built and runs at team select; the market Thrill-craft and the
    # forfeit-after-Floor-3 logic are still being layered in, so after the swap
    # the run currently proceeds as a standard Rupture run.
    if (md_state.get("custom_run") and
            md_state.get("custom_strategy") == "Thrill"):
        return _build_thrill_run(md_state)

    settings = build_settings(md_state)
    hard = md_state.get("difficulty", "Hard") in ("Hard", "Extreme")

    # "F3 Hard": start Normal, flip to Hard on floor 3. Never Extreme.
    if md_state.get("custom_run") and md_state.get("custom_strategy") == "F3 Hard":
        hard = True
        settings["hard_from_floor"] = 3
        settings["infinity"] = False

    priority, avoid = _build_packs(md_state.get("packs", {}),
                                   md_state.get("global_packs", {}))

    teams = {}
    key = 0
    for team in md_state.get("teams", []) or []:
        status = [a for a in team.get("affinities", []) if a in _STATUS_INDEX]
        if not status:
            continue  # a team with no status affinity can't drive gifts
        teams[key] = {
            "affinity": [_STATUS_INDEX[a] for a in status],
            "affinity_idx": 0,
            "duplicates": False,
            "sinners": _sinners_for(status[0], sinner_sel),
            "priority": priority,
            "avoid": avoid,
        }
        key += 1

    if not teams:
        raise ValueError(
            "No runnable team. Add a team with a status type "
            "(Burn, Rupture, Slash, ...) in Mirror Dungeon."
        )

    count = int(md_state.get("run_count", 1) or 1)
    return count, teams, settings, hard


def build_lux_run(mode: str, lux_state: dict, md_state: dict, sinner_sel: dict):
    """Return (count_exp, count_thd, teams, settings, hard) for a Lux run.
    `mode` is 'exp' or 'thread'. Settings come from the MD state (shared)."""
    settings = build_settings(md_state)
    # Thread difficulty is 20/30/40/50/60 (lv{N}.png); EXP stage is 1..9
    # (stage{N}.png). lux.py reads p.LUX_THD_DIFFICULTY / p.LUX_EXP_STAGE.
    try:
        settings["lux_thd_difficulty"] = int(lux_state.get("thd_diff", 40) or 40)
    except (TypeError, ValueError):
        settings["lux_thd_difficulty"] = 40
    try:
        settings["lux_exp_stage"] = int(lux_state.get("exp_stage", 6) or 6)
    except (TypeError, ValueError):
        settings["lux_exp_stage"] = 6

    if mode == "exp":
        affinity = lux_state.get("exp_team", "Slash")
        runs = int(lux_state.get("exp_runs", 1) or 1)
        count_exp, count_thd = runs, 0
    else:
        affinity = lux_state.get("thd_team", "Slash")
        runs = int(lux_state.get("thd_runs", 1) or 1)
        count_exp, count_thd = 0, runs

    aff_idx = _LUX_ORDER.index(affinity) if affinity in _LUX_ORDER else 0
    # Lux team key encodes the affinity (7 + index); team_setup reads the
    # thread team at the second lux key, so a thread run seeds a placeholder
    # EXP key below it.
    #
    # Look the sinner order up by Lux affinity name. Unconditional, since
    # _sinners_for falls back to defaults when there's no entry - this also
    # covers the seven sin affinities an earlier _STATUS_INDEX gate excluded.
    sinners = _sinners_for(affinity, sinner_sel)
    entry = {
        "affinity": [], "affinity_idx": 0, "duplicates": False,
        "sinners": sinners, "priority": ([], {}), "avoid": ([], {}, {}),
    }
    if mode == "exp":
        teams = {7 + aff_idx: entry}
    else:
        # Two keys so team_setup(index=1) picks the thread team.
        thd_key = 7 + aff_idx if aff_idx > 0 else 8
        teams = {7: dict(entry), thd_key: entry} if thd_key != 7 \
            else {7: entry, 8: dict(entry)}

    hard = False
    return count_exp, count_thd, teams, settings, hard
