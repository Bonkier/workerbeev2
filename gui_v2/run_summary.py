# SPDX-License-Identifier: GPL-3.0-or-later
"""What a run is about to do, as rows of text for the start overlay.

Pure functions of the page state dicts: no widgets, no settings I/O, so the
wording can be tested without a window. Each returns a list of sections,
[(caption, [(label, value), ...]), ...]."""

from .run_config import (HOLLOW_LABEL, HOLLOW_PACK_NAMES, SAIKAI_LABEL,
                         THRILL_LABEL, _GRACE_ORDER)

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
_HOLLOW_DEFAULT_GRACES = ("Star of the Beginning, Interstellar Travel "
                          "(none picked, so the sheet's)")


def _graces(md):
    """The BUILD panel's graces with their tiers; Hollow falls back to the
    sheet's pair when none is picked."""
    grace = md.get("grace") or {}
    picked = []
    for name in _GRACE_ORDER:
        try:
            state = int(grace.get(name, 0) or 0)
        except (TypeError, ValueError):
            state = 0
        if state:
            picked.append(name + _GRACE_SUFFIX[min(state, 3)])
    return _join(picked, _HOLLOW_DEFAULT_GRACES, limit=10)


def _difficulty(md, saikai, thrill, hollow=False):
    if thrill:
        return "Normal, forfeit after floor 3"
    if hollow:
        return "Normal, then Hard from floor 5"
    if saikai:
        if md.get("saikai_full_normal"):
            text = "Normal on every floor"
        elif md.get("saikai_only_hard"):
            text = "Hard on every floor"
        else:
            text = "Normal, then Hard from floor 4"
        if md.get("saikai_floor10"):
            text += ", leaving after floor 10"
        return text
    return str(md.get("difficulty") or "Hard")


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


def md_summary(md: dict, app: dict | None = None) -> list:
    """Sections for a Mirror Dungeon start. `md` is the MD page state with
    the SAIKAI/Thrill team keys merged in; `app` is the Settings state."""
    md = md or {}
    app = app or {}
    custom = bool(md.get("custom_run"))
    strategy = str(md.get("custom_strategy") or "") if custom else ""
    saikai = strategy == SAIKAI_LABEL
    thrill = strategy == THRILL_LABEL
    hollow = strategy == HOLLOW_LABEL

    runs = int(md.get("run_count", 1) or 1)
    retries = int(md.get("retry_count", 0) or 0)
    run = [
        ("Runs", "Loop forever" if runs >= 9999 else str(runs)),
        ("Difficulty", _difficulty(md, saikai, thrill, hollow)),
        ("Retries on defeat", "Unlimited" if retries == 0 else str(retries)),
    ]

    if hollow:
        run.append(("Graces", _graces(md)))
        team = [
            ("Team keyword", str(md.get("hollow_status") or "Poise")),
            ("Squad", "Faust alone"),
            ("Fallback (miniboss)", _join(
                [n for n in (md.get("hollow_order") or []) if n != "Faust"],
                "None")),
            ("Shop heals", "%s on floor 1, Faust on floors 4 and 5"
             % (md.get("hollow_heal") or "Yi Sang")),
        ]
        if (md.get("behaviour") or {}).get("swap_max_energy"):
            team.append(("Swap exclusion", _join(md.get("hollow_exclude"), "None")))
    elif saikai or thrill:
        key = "saikai" if saikai else "thrill"
        default = "Poise" if saikai else "Rupture"
        team = [
            ("Team keyword", str(md.get(key + "_status") or default)),
            ("Sinner order", _join(md.get(key + "_order"), "Default")),
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
    active = (md.get("skill_replace") or {}).get("active") or []
    refreshes = int(md.get("pack_refreshes", 0) or 0)
    shop = [
        ("Market", "Heal, then the floor plan (Conceit, then Decay; Clear "
                   "Mirror and Artistic Sense after, uptied once all four are "
                   "crafted, floor 4 at the latest)" if hollow
         else _market(md, saikai)),
        ("Skill replacement", _join(active, "Off")),
        ("Pack search", "%s, %d refresh%s" % (
            "Off" if not behaviour.get("pack_search", True)
            else "On, one pack per floor" if hollow else "On",
            refreshes, "" if refreshes == 1 else "es")),
        ("Packs", _join(HOLLOW_PACK_NAMES) if hollow
         else "%d prioritised, %d avoided" % (
            _count_states(md.get("packs"), md.get("global_packs"), "priority"),
            _count_states(md.get("packs"), md.get("global_packs"), "avoid"))),
    ]

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
    controls = md.get("market_controls") or {}
    if saikai or hollow or not controls.get("default_market_workflow", True):
        tags = md.get("market_gifts_saikai" if saikai
                      else "market_gifts_hollow" if hollow
                      else "market_gifts") or {}
        names = []
        for key in ("buy", "fuse", "enhance1", "enhance2"):
            for n in tags.get(key) or []:
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
