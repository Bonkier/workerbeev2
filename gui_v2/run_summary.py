# SPDX-License-Identifier: GPL-3.0-or-later
"""What a run is about to do, as rows of text for the start overlay.

Pure functions of the page state dicts: no widgets, no settings I/O, so the
wording can be tested without a window. Each returns a list of sections,
[(caption, [(label, value), ...]), ...]."""

from .run_config import (HOLLOW_LABEL, PRESET_GRACES, SAIKAI_LABEL,
                         _GRACE_ORDER, floors_phrase, hollow_pack_names,
                         skip_floor_set)

# Behaviour toggles by state key. pack_search is left out: it is reported
# with the pack settings instead of as a bare toggle.
BEHAVIOUR_LABELS = {
    "bonus": "Claim bonus",
    "bonus_one": "One weekly bonus per run",
    "restart": "Restart on failure",
    "claim_on_defeat": "Claim rewards on defeat",
    "enkephalin": "Convert enkephalin",
    "skip": "Skip dialogue",
    "winrate": "Always pick winrate",
    "swap_max_energy": "Swap for max energy",
    "wishmaking": "Wishmaking",
    "skip_restshop": "Skip rest shop",
    "skip_ego_check": "Skip EGO check",
    "skip_ego_fusion": "Skip EGO fusion",
    "skip_ego_enhancing": "Skip EGO enhancing",
    "skip_ego_buying": "Skip EGO buying",
    "skip_sinner_healing": "Skip sinner healing",
    "altf4": "Close Limbus when finished",
    "logout_on_finish": "Log out of Windows when finished",
}


def _join(names, empty="None", limit=6):
    names = [str(n) for n in (names or []) if n]
    if not names:
        return empty
    if len(names) > limit:
        return ", ".join(names[:limit]) + " +%d more" % (len(names) - limit)
    return ", ".join(names)


def _count_states(packs, global_packs, state):
    seen = {pk for pk, st in (global_packs or {}).items() if st == state}
    for floor_packs in (packs or {}).values():
        if isinstance(floor_packs, dict):
            seen |= {pk for pk, st in floor_packs.items() if st == state}
    return len(seen)


_GRACE_SUFFIX = ("", "", " +", " ++")


def _starter_gift(md, saikai=False, hollow=False):
    """The BUILD panel's starter pick with its keyword; nothing picked takes
    the team keyword's usual one, Torn Bandolier for Hollow."""
    from wbcore.starter_gifts import keyword_of, usual_pick
    pick = str(md.get("starter_gift") or "")
    if pick:
        return "%s: %s" % (keyword_of(pick) or "Unknown", pick)
    if hollow:
        from wbcore.hollow import STARTING_GIFT, STARTING_KEYWORD
        return "%s: %s (the run's own)" % (STARTING_KEYWORD.title(),
                                           STARTING_GIFT)
    if saikai:
        keyword = str(md.get("saikai_status") or "Poise")
        usual = usual_pick(keyword)
        if usual:
            return "%s: %s (the usual pick)" % (keyword, usual)
    return "The team keyword's usual pick"


def _graces(md, fallback=None):
    """The BUILD panel's graces with their tiers; a scripted run falls back
    to its own preset when none is picked."""
    grace = md.get("grace") or {}
    picked = []
    for name in _GRACE_ORDER:
        try:
            state = int(grace.get(name, 0) or 0)
        except (TypeError, ValueError):
            state = 0
        if state:
            picked.append(name + _GRACE_SUFFIX[min(state, 3)])
    if picked:
        return _join(picked, "None", limit=10)
    if fallback:
        return _join(list(fallback), "None") + " (none picked, so the run's own)"
    return "None"


def _flip_text(flip, default):
    """The difficulty line from the Floor Packs/Market tab's Hard flip, or the run's own
    when the state carries none."""
    n = default if flip is None else flip
    if not n or n >= 99:
        return "Normal on every floor"
    if n == 1:
        return "Hard on every floor"
    return "Normal, then Hard from floor %d" % n


def _difficulty(md, saikai, hollow=False):
    from .run_config import _page_flip
    flip = _page_flip(md)
    if hollow:
        return _flip_text(flip, 5)
    if saikai:
        return _flip_text(flip, 4)
    diff = str(md.get("difficulty") or "Hard")
    if diff == "Normal" and flip:
        return "Normal, then Hard from floor %d" % flip
    return diff


def _pack_search(md, hollow, saikai):
    refreshes = int(md.get("pack_refreshes", 0) or 0)
    tail = ", %d refresh%s" % (refreshes, "" if refreshes == 1 else "es")
    if hollow:
        return "One pack per floor" + tail
    if saikai:
        return "The run's own packs" + tail
    floors = ((md.get("pack_search_cfg") or {}).get("floors") or {})
    on = sorted(int(k) for k, ent in floors.items()
                if isinstance(ent, dict) and ent.get("enabled") and ent.get("pack")
                and str(k).isdigit())
    if not on:
        return "No floor configured" + tail
    names = ["Floor %d" % f for f in on] if len(on) == 1 else [str(f) for f in on]
    listed = names[0] if len(on) == 1 else "Floors " + ", ".join(names[:-1]) + " and " + names[-1]
    return listed + tail


def _market(md, saikai):
    controls = md.get("market_controls") or {}
    tags = md.get("market_gifts_saikai" if saikai else "market_gifts") or {}
    custom = saikai or not controls.get("default_market_workflow", True)
    if not custom:
        return "Default workflow"
    buy = len(tags.get("buy") or [])
    fuse = len(tags.get("fuse") or [])
    uptie = len(set(tags.get("enhance1") or []) | set(tags.get("enhance2") or []))
    return "Custom: buy %d, fuse %d, uptie %d" % (buy, fuse, uptie)


_STEP_WORDS = {
    "skip_restshop": "rest shop", "skip_ego_check": "gift check",
    "skip_ego_fusion": "fusion", "skip_ego_enhancing": "upties",
    "skip_ego_buying": "buying", "skip_sinner_healing": "healing",
}


def _hollow_market(md):
    """Hollow's shop plan; Torn Bandolier's first uptie only when it is the
    starter gift taken."""
    from wbcore.hollow import STARTING_GIFT
    pick = str(md.get("starter_gift") or "")
    first = ("%s uptied first on floor 1, then the heal and " % STARTING_GIFT
             if pick in ("", STARTING_GIFT) else "The heal, then ")
    return first + ("the floor plan (Poise Rock, Clear Mirror ++, Sinking "
                    "Rock, Artistic Sense ++, in that order; the free shelf "
                    "refresh on every floor, paid ones for the Poise Rock "
                    "on any floor and for the rest from floor 4, with tier 1 "
                    "gifts sold when that cost is short; from the floor 4 "
                    "shop the unprotected gifts are sold for the upties "
                    "once all four are crafted)")


def _floor_settings(md, slot):
    """What the floors set for themselves on Floor Packs/Market, or ""."""
    floors = (md.get("market_floors") or {}).get(slot) or {}
    parts = []
    for key in sorted(floors, key=lambda k: int(k) if str(k).isdigit() else 99):
        ent = floors[key] if isinstance(floors[key], dict) else {}
        tags = ent.get("tags") or {}
        bits = ["%s %d" % (mode, len(tags.get(mode) or []))
                for mode in ("buy", "fuse", "sell") if tags.get(mode)]
        upties = set(tags.get("enhance1") or []) | set(tags.get("enhance2") or [])
        if upties:
            bits.append("uptie %d" % len(upties))
        kept = set(tags.get("keep_fuse") or []) | set(tags.get("keep_sell") or [])
        if kept:
            bits.append("keep %d" % len(kept))
        for k, skip in (ent.get("steps") or {}).items():
            if k in _STEP_WORDS:
                bits.append(("no " if skip else "") + _STEP_WORDS[k])
        if bits:
            parts.append("Floor %s: %s" % (key, ", ".join(bits)))
    return "; ".join(parts)


def md_summary(md: dict, app: dict | None = None) -> list:
    """Sections for a Mirror Dungeon start. `md` is the MD page state with
    the SAIKAI/Hollow team keys merged in; `app` is the Settings state."""
    md = md or {}
    app = app or {}
    custom = bool(md.get("custom_run"))
    strategy = str(md.get("custom_strategy") or "") if custom else ""
    saikai = strategy == SAIKAI_LABEL
    hollow = strategy == HOLLOW_LABEL

    runs = int(md.get("run_count", 1) or 1)
    retries = int(md.get("retry_count", 0) or 0)
    run = [
        ("Runs", "Loop forever" if runs >= 9999 else str(runs)),
        ("Difficulty", _difficulty(md, saikai, hollow)),
        ("Retries on defeat", "Unlimited" if retries == 0 else str(retries)),
        ("Graces", _graces(md, PRESET_GRACES.get(strategy))),
    ]
    run.append(("Starter gift", _starter_gift(md, saikai, hollow)))

    if hollow:
        team = [
            ("Team keyword", str(md.get("hollow_status") or "Poise")),
            ("Squad", "Faust alone"),
            ("Fallback (miniboss)", _join(
                [n for n in (md.get("hollow_order") or []) if n != "Faust"],
                "None")),
            ("Shop heals", "%s on floor 1, Faust on floors 4 and 5 (twice "
                           "when one heal leaves her under 45 SP)"
             % (md.get("hollow_heal") or "Yi Sang")),
        ]
        if (md.get("behaviour") or {}).get("swap_max_energy"):
            team.append(("Swap exclusion", _join(md.get("hollow_exclude"), "None")))
    elif saikai:
        team = [
            ("Team keyword", str(md.get("saikai_status") or "Poise")),
            ("Sinner order", _join(md.get("saikai_order"), "Default")),
        ]
    else:
        names = []
        for t in md.get("teams") or []:
            if not isinstance(t, dict):
                continue
            affs = _join(t.get("affinities"), "")
            name = str(t.get("name") or "Team")
            names.append("%s (%s)" % (name, affs) if affs else name)
        team = [("Team rotation" if len(names) > 1 else "Team",
                 _join(names, "None set", limit=4))]

    behaviour = md.get("behaviour") or {}
    skill = md.get("skill_replace") or {}
    active = skill.get("active") or []
    swaps = _join(active, "Off")
    skipped = skip_floor_set(skill.get("skip_floors"))
    if active and skipped:
        swaps += " on %s" % floors_phrase(set(range(1, 6)) - skipped)
    shop = [
        ("Market", _hollow_market(md) if hollow else _market(md, saikai)),
        ("Skill replacement", swaps),
        ("Pack search", _pack_search(md, hollow, saikai)),
        ("Packs", _join(hollow_pack_names(md)) if hollow
         else "%d prioritised, %d avoided" % (
            _count_states(md.get("packs"), md.get("global_packs"), "priority"),
            _count_states(md.get("packs"), md.get("global_packs"), "avoid"))),
    ]
    floors = _floor_settings(md, "saikai" if saikai else "hollow" if hollow
                             else "normal")
    if floors:
        shop.append(("Floor settings", floors))

    # Hollow decides win rate itself and always scans the owned shelf for
    # its plan, so those two toggles do not apply to it.
    overridden = {"winrate", "skip_ego_check"} if hollow else set()
    if not behaviour.get("bonus", True):
        overridden = overridden | {"bonus_one"}    # no charge is spent at all
    on = [label for key, label in BEHAVIOUR_LABELS.items()
          if behaviour.get(key) and key not in overridden]
    options = [("Switched on", _join(on, "Nothing", limit=99))]
    if app:
        options.append(("Mouse", "%d%% speed, %s profile" % (
            int(app.get("mouse_speed", 100) or 100),
            app.get("macro_profile", "Safe"))))

    return [("RUN", run), ("TEAM", team), ("SHOP AND PACKS", shop),
            ("BEHAVIOUR", options)]


def strategy_label(md: dict) -> str:
    """The run script in use: a custom strategy's name, or a standard run."""
    md = md or {}
    if md.get("custom_run") and md.get("custom_strategy"):
        return str(md["custom_strategy"])
    return "Standard run"


def md_gifts(md: dict) -> list:
    """Gift art groups for the overlay: the gifts searched for at the start
    and, on a custom market, the gifts it is set to buy, fuse or uptie."""
    md = md or {}
    saikai = (bool(md.get("custom_run"))
              and md.get("custom_strategy") == SAIKAI_LABEL)
    groups = [{"caption": "GIFT SEARCH", "named": True,
               "names": [str(n) for n in (md.get("gift_search") or []) if n]}]
    hollow = (bool(md.get("custom_run"))
              and md.get("custom_strategy") == HOLLOW_LABEL)
    pick = str(md.get("starter_gift") or "")
    if hollow and not pick:
        from wbcore.hollow import STARTING_GIFT
        pick = STARTING_GIFT
    if pick:
        groups.insert(0, {"caption": "STARTER GIFT", "named": True,
                          "names": [pick]})
    controls = md.get("market_controls") or {}
    if saikai or hollow or not controls.get("default_market_workflow", True):
        tags = md.get("market_gifts_saikai" if saikai
                      else "market_gifts_hollow" if hollow
                      else "market_gifts") or {}
        floors = (md.get("market_floors") or {}).get(
            "saikai" if saikai else "hollow" if hollow else "normal") or {}
        names = []
        if hollow:
            from .run_config import hollow_slot_tags
            tags = hollow_slot_tags(tags)
        for t in [tags] + [ent.get("tags") or {} for ent in floors.values()
                           if isinstance(ent, dict)]:
            for key in ("buy", "fuse", "enhance1", "enhance2"):
                for n in t.get(key) or []:
                    if n and n not in names:
                        names.append(str(n))
        groups.append({"caption": "MARKET TARGETS", "named": False,
                       "names": names})
    return groups


def md_start(md: dict, app: dict | None = None) -> dict:
    """Everything the start overlay shows for a Mirror Dungeon run."""
    return {"title": run_title("md"), "subtitle": strategy_label(md),
            "sections": md_summary(md, app), "gifts": md_gifts(md)}


def lux_start(mode: str, lux: dict, app: dict | None = None) -> dict:
    """Everything the start overlay shows for a Luxcavation run."""
    return {"title": run_title(mode), "subtitle": "",
            "sections": lux_summary(mode, lux, app), "gifts": []}


def lux_summary(mode: str, lux: dict, app: dict | None = None) -> list:
    """Sections for a Luxcavation start. `mode` is "exp" or "thread"."""
    lux = lux or {}
    app = app or {}
    if mode == "exp":
        run = [
            ("Runs", str(int(lux.get("exp_runs", 1) or 1))),
            ("Stage", str(lux.get("exp_stage") or "-")),
            ("Team", str(lux.get("exp_team") or "-")),
        ]
    else:
        run = [
            ("Runs", str(int(lux.get("thd_runs", 1) or 1))),
            ("Difficulty", str(lux.get("thd_diff") or "-")),
            ("Team", str(lux.get("thd_team") or "-")),
        ]
    sections = [("RUN", run)]
    if app:
        sections.append(("INPUT", [("Mouse", "%d%% speed, %s profile" % (
            int(app.get("mouse_speed", 100) or 100),
            app.get("macro_profile", "Safe")))]))
    return sections


def run_title(kind: str) -> str:
    from . import seasonal
    return seasonal.title(
        {"md": "Mirror Dungeon", "exp": "EXP Luxcavation",
         "thread": "Thread Luxcavation"}.get(kind, "Run"))
