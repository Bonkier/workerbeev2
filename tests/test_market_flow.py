# SPDX-License-Identifier: GPL-3.0-or-later
"""The custom market as one visit: the fuel plan in gifts, the buy loop,
the single fuse session and the enhance dialog, with the screen stubbed."""
import types

import pytest

from wbcore import shop as S
from wbcore.utils import params as p


# --- the fuel plan ---------------------------------------------------------

def test_a_tier_4_needs_two_tier_3_and_a_tier_2():
    assert S.plan_fuel({}, [4]) == (0, {3: 2, 2: 1})
    assert S.plan_fuel({3: 2, 2: 1}, [4]) == (0, {3: 0, 2: 0})
    assert S.plan_fuel({3: 2}, [4]) == (0, {3: 0, 2: 1})
    assert S.plan_fuel({3: 1, 2: 1}, [4]) == (0, {3: 1, 2: 0})


def test_spare_tier_2s_become_tier_3s_before_buying():
    # The owner's example: one tier 3 and four tier 2 make a tier 4.
    assert S.plan_fuel({3: 1, 2: 4}, [4]) == (1, {3: 0, 2: 0})
    # Six tier 2: one craft, still a tier 3 short.
    assert S.plan_fuel({2: 6}, [4]) == (1, {3: 1, 2: 0})
    # Seven tier 2: two crafts, nothing to buy.
    assert S.plan_fuel({2: 7}, [4]) == (2, {3: 0, 2: 0})


def test_the_plan_covers_every_pending_target():
    assert S.plan_fuel({3: 2, 2: 1}, [4, 4]) == (0, {3: 2, 2: 1})
    assert S.plan_fuel({2: 3}, [3]) == (0, {3: 0, 2: 0})
    assert S.plan_fuel({3: 4, 2: 2}, [4, 4, 3]) == (0, {3: 0, 2: 3})


def test_uptie_costs_follow_the_dialog():
    assert S.uptie_cost(4) == 100 and S.uptie_cost(4, 2) == 300
    assert S.uptie_cost(1) == 50
    assert S.uptie_cost(None) == 100


# --- buying fuel -----------------------------------------------------------

@pytest.fixture
def shop_screen(monkeypatch):
    log = {"clicks": [], "refresh": 0, "shelves": [], "funds": 1000}

    def get_shop(_shelf):
        return log["shelves"].pop(0) if log["shelves"] else {1: [], 2: [], 3: []}

    monkeypatch.setattr(S, "update_shelf", lambda: None)
    monkeypatch.setattr(S, "get_shop", get_shop)
    monkeypatch.setattr(S, "balance", lambda: log["funds"])
    monkeypatch.setattr(S, "conf_gift", lambda: None)
    monkeypatch.setattr(S, "connection", lambda: None)
    monkeypatch.setattr(S.time, "sleep", lambda s: None)

    def click(pos, *a, **k):
        if pos == (1489, 177):
            log["refresh"] += 1
        else:
            log["clicks"].append(pos)

    monkeypatch.setattr(S, "win_click", lambda *a, **k: click(a[0] if len(a) == 1 else (a[0], a[1]), **k))
    monkeypatch.setattr(S, "_MARKET_REFRESH_CAP", 3)
    monkeypatch.setattr(S, "_FUEL_REFRESH_CAP", 3)
    return log


def test_tier_3s_are_bought_first_and_tier_2s_only_to_complete(shop_screen):
    log = shop_screen
    log["shelves"] = [
        {1: [], 2: [(10, 10)], 3: [(20, 20)]},     # a tier 2 is skipped while a tier 3 is short
        {1: [], 2: [(10, 10)], 3: []},
        {1: [], 2: [(10, 10)], 3: []},
    ]
    have = {3: 1, 2: 0}
    left = S._buy_fuel_plan(have, [4])
    assert left == {3: 0, 2: 0}
    assert log["clicks"] == [(20, 20), (10, 10)]
    assert have == {3: 2, 2: 1}
    assert log["refresh"] == 0


def test_the_shelf_is_refreshed_while_something_is_short(shop_screen):
    log = shop_screen
    log["shelves"] = [{1: [], 2: [], 3: []}, {1: [], 2: [], 3: []},
                      {1: [], 2: [], 3: [(5, 5)]}, {1: [], 2: [], 3: [(6, 6)]}]
    have = {3: 0, 2: 1}
    assert S._buy_fuel_plan(have, [4]) == {3: 0, 2: 0}
    assert log["refresh"] == 2 and log["clicks"] == [(5, 5), (6, 6)]


def test_buying_stops_at_the_cost_floor_and_the_refresh_cap(shop_screen):
    log = shop_screen
    log["funds"] = 150
    assert S._buy_fuel_plan({}, [4]) == {3: 2, 2: 1}
    assert log["clicks"] == [] and log["refresh"] == 0
    log["funds"] = 1000
    assert S._buy_fuel_plan({}, [4]) == {3: 2, 2: 1}       # empty shelves: cap
    assert log["refresh"] == 3
    # The reserve for the upties is kept untouched.
    log["funds"] = 350
    log["refresh"] = 0
    assert S._buy_fuel_plan({}, [4], keep=200) == {3: 2, 2: 1}
    assert log["refresh"] == 0


# --- the fuse session ---------------------------------------------------------

@pytest.fixture
def fuse_menu(monkeypatch):
    log = {"opens": 0, "keywords": [], "crafts": [], "closed": 0, "buys": 0,
           "owned": set(), "pool": {1: [], 2: [], 3: [], 4: []}, "scans": 0}
    cat = {
        "Fragment of Conceit": {"tier": 4, "keyword": "poise", "sell_path": "x"},
        "Clear Mirror, Calm Water": {"tier": 4, "keyword": "poise", "sell_path": "x"},
        "Artistic Sense": {"tier": 4, "keyword": "sinking", "sell_path": "x"},
        "Fragment of Decay": {"tier": 4, "keyword": "sinking", "sell_path": "x"},
        "Grand Welcome": {"tier": 3, "keyword": "keywordless", "sell_path": "x"},
    }
    monkeypatch.setattr(S, "load_market_catalog", lambda: cat, raising=False)
    import wbcore.market_catalog as MC
    monkeypatch.setattr(MC, "load_market_catalog", lambda: cat)
    monkeypatch.setattr(S, "_keyword_checks", lambda kw: ["x", "y", (0, 0), "re" + kw, "big", 0])

    def open_menu():
        log["opens"] += 1
        return True

    def select(checks):
        log["keywords"].append(checks[3])
        return True

    def shelf_has(name):
        return (1, 1) if name in log["owned"] else None

    def inventory():
        log["scans"] += 1
        pool = {t: list(v) for t, v in log["pool"].items()}
        return pool, pool, {}

    def craftable(tier, pool):
        n2, n3, n4 = len(pool[2]), len(pool[3]), len(pool.get(4) or [])
        if tier == 4:
            return (n3 >= 2 and n2 >= 1) or (n4 >= 1 and n2 >= 2)
        return n2 >= 3

    def decide(tier, pool):
        return None, ({} if craftable(tier, pool) else {tier: 1})

    def actual(tier, pool):
        if not craftable(tier, log["pool"]):
            return {tier: 1}
        log["crafts"].append(tier)
        # A craft consumes the fuel and, for a tier 4, yields the target.
        if tier == 4:
            if len(log["pool"][3]) >= 2:
                for _ in range(2):
                    log["pool"][3].pop()
                log["pool"][2].pop()
            else:
                log["pool"][4].pop()
                for _ in range(2):
                    log["pool"][2].pop()
            log["owned"].add(log["next"].pop(0))
        else:
            for _ in range(3):
                log["pool"][2].pop()
            log["pool"][3].append((9, 9, 0))
        return None

    monkeypatch.setattr(S, "_open_fuse_menu", open_menu)
    monkeypatch.setattr(S, "_select_fuse_keyword", select)
    monkeypatch.setattr(S, "_shelf_has_catalog", shelf_has)
    monkeypatch.setattr(S, "get_inventory", inventory)
    monkeypatch.setattr(S, "actual_fuse", actual)
    monkeypatch.setattr(S, "decide_fusion", decide)
    monkeypatch.setattr(S, "now", types.SimpleNamespace(button=lambda *a, **k: False))
    monkeypatch.setattr(S, "close_panel", lambda: log.__setitem__("closed", log["closed"] + 1))
    monkeypatch.setattr(S, "_buy_fuel_plan", lambda have, tiers, keep=0, **k: log.__setitem__("buys", log["buys"] + 1))
    monkeypatch.setattr(S.time, "sleep", lambda s: None)
    monkeypatch.setattr(p, "EXTREME", False)
    return log


def test_one_open_menu_crafts_every_target_keyword_by_keyword(fuse_menu):
    log = fuse_menu
    log["pool"] = {1: [], 2: [(1, 1, 0)] * 4, 3: [(2, 2, 0)] * 8, 4: []}
    log["next"] = ["Fragment of Conceit", "Clear Mirror, Calm Water",
                   "Artistic Sense", "Fragment of Decay"]
    done = set()
    S._fuse_session(["Fragment of Conceit", "Clear Mirror, Calm Water",
                     "Artistic Sense", "Fragment of Decay"], done)
    assert log["opens"] == 1 and log["closed"] == 1
    assert log["keywords"] == ["repoise", "resinking"]      # switched in place
    assert log["crafts"] == [4, 4, 4, 4]
    assert done == {"Fragment of Conceit", "Clear Mirror, Calm Water",
                    "Artistic Sense", "Fragment of Decay"}
    assert log["buys"] == 0


def test_the_first_target_keyword_leads_even_when_smaller(fuse_menu):
    log = fuse_menu
    log["pool"] = {1: [], 2: [(1, 1, 0)] * 3, 3: [(2, 2, 0)] * 6, 4: []}
    log["next"] = ["Fragment of Conceit", "Artistic Sense", "Fragment of Decay"]
    S._fuse_session(["Fragment of Conceit", "Artistic Sense", "Fragment of Decay"], set())
    assert log["keywords"] == ["repoise", "resinking"]


def test_a_short_pool_sends_the_bot_shopping_once_then_back_in(fuse_menu):
    log = fuse_menu
    log["pool"] = {1: [], 2: [(1, 1, 0)], 3: [(2, 2, 0)], 4: []}  # one tier 3 short
    log["next"] = ["Fragment of Conceit"]

    def buy(have, tiers, keep=0, **k):
        log["buys"] += 1
        log["pool"][3].append((3, 3, 0))                   # the shop had one
    S._buy_fuel_plan = buy
    done = set()
    S._fuse_session(["Fragment of Conceit"], done, buy_allowed=True)
    assert log["buys"] == 1
    assert log["opens"] == 2 and log["closed"] == 2          # out to buy, back in
    assert log["keywords"] == ["repoise", "repoise"]         # reselected after reopening
    assert done == {"Fragment of Conceit"}


def test_spare_tier_2s_are_crafted_into_a_tier_3_first(fuse_menu):
    log = fuse_menu
    log["pool"] = {1: [], 2: [(1, 1, 0)] * 4, 3: [(2, 2, 0)], 4: []}
    log["next"] = ["Fragment of Conceit"]
    S._fuse_session(["Fragment of Conceit"], set(), buy_allowed=False)
    assert log["crafts"] == [3, 4]
    assert log["buys"] == 0


def test_without_buying_a_short_target_is_left_for_the_next_shop(fuse_menu):
    log = fuse_menu
    log["pool"] = {1: [], 2: [], 3: [(2, 2, 0)], 4: []}
    log["next"] = []
    monkeypatch_actual = S.actual_fuse
    S.actual_fuse = lambda tier, pool: {3: 1, 2: 1}
    done = set()
    S._fuse_session(["Fragment of Conceit"], done, buy_allowed=False)
    S.actual_fuse = monkeypatch_actual
    assert done == set() and log["buys"] == 0 and log["closed"] == 1


# --- the enhance dialog --------------------------------------------------------

@pytest.fixture
def dialog(monkeypatch):
    state = {"confirm2": True, "power": True, "lit": True, "plus": True,
             "plusplus": True, "chosen": None, "clicks": []}
    monkeypatch.setattr(S, "now", types.SimpleNamespace(
        button=lambda name, *a, **k: state.get({"Confirm.2": "confirm2", "power": "power"}.get(name, ""), False)))
    monkeypatch.setattr(S, "wait_while_condition",
                        lambda cond, action=None, interval=0.5, timer=20: not cond())
    monkeypatch.setattr(S, "_confirm_lit", lambda: state["lit"])
    monkeypatch.setattr(S, "_tier_glyph_available",
                        lambda double: state["plusplus"] if double else state["plus"])
    monkeypatch.setattr(S, "_tier_glyph_chosen",
                        lambda double: state["chosen"] == ("pp" if double else "p"))

    def click(x, y, **k):
        state["clicks"].append((x, y))
        if (x, y) == (1546, 766) and state["plusplus"]:
            state["chosen"] = "pp"
        elif (x, y) == (1361, 766) and state["plus"]:
            state["chosen"] = "p"

    monkeypatch.setattr(S, "win_click", click)
    monkeypatch.setattr(S.gui, "press", lambda *a, **k: None)
    monkeypatch.setattr(S.time, "sleep", lambda s: None)
    return state


def test_two_owed_levels_take_the_double_button(dialog):
    assert S._enhance_dialog(2) == 2
    assert dialog["clicks"] == [(1546, 766), (1183, 876)]


def test_one_owed_level_clicks_the_single_button_itself(dialog):
    assert S._enhance_dialog(1) == 1
    assert dialog["clicks"] == [(1361, 766), (1183, 876)]


def test_one_owed_level_overrides_a_remembered_double(dialog):
    dialog["chosen"] = "pp"
    assert S._enhance_dialog(1) == 1
    assert dialog["clicks"] == [(1361, 766), (1183, 876)]


def test_a_gift_already_at_plus_takes_the_double_as_its_one_level(dialog):
    dialog["plus"] = False
    assert S._enhance_dialog(1) == 1
    assert dialog["clicks"] == [(1361, 766), (1546, 766), (1183, 876)]


def test_a_greyed_double_falls_back_to_one_level(dialog):
    dialog["plusplus"] = False
    assert S._enhance_dialog(2) == 1
    assert dialog["clicks"] == [(1546, 766), (1361, 766), (1183, 876)]


def test_a_greyed_confirm_cancels_and_buys_nothing(dialog):
    dialog["lit"] = False
    dialog["plus"] = False
    dialog["plusplus"] = False
    assert S._enhance_dialog(2) == 0
    assert dialog["clicks"][-1] == (733, 876)
    dialog["confirm2"] = False                               # no dialog at all
    dialog["clicks"].clear()
    assert S._enhance_dialog(1) == 0 and dialog["clicks"] == []


# --- the verification round ------------------------------------------------

def test_the_menu_counts_as_open_under_its_own_keyword_dialog(monkeypatch):
    shown = {"keywordSel"}
    monkeypatch.setattr(S, "chain_actions", lambda *a, **k: None)
    monkeypatch.setattr(S, "Action", lambda *a, **k: None)
    monkeypatch.setattr(S, "now", types.SimpleNamespace(
        button=lambda name, *a, **k: name in shown))
    assert S._open_fuse_menu()
    shown.clear()
    assert not S._open_fuse_menu()
    shown.add("fuse")
    assert S._open_fuse_menu()


def test_tier_2s_are_bought_towards_a_missing_tier_3_after_a_refresh(shop_screen):
    log = shop_screen
    log["shelves"] = [
        {1: [], 2: [(10, 10)], 3: []},       # no tier 3: refresh first
        {1: [], 2: [(11, 11)], 3: []},       # still none: tier 2s may go
        {1: [], 2: [(12, 12)], 3: []},
        {1: [], 2: [(13, 13)], 3: []},
    ]
    have = {3: 1, 2: 1}
    assert S._buy_fuel_plan(have, [4]) == {3: 0, 2: 0}
    assert log["refresh"] == 1
    assert log["clicks"] == [(11, 11), (12, 12), (13, 13)]
    assert have == {3: 1, 2: 4}


def test_spare_tier_3s_are_stocked_only_for_a_floor_plan(shop_screen):
    log = shop_screen
    log["shelves"] = [{1: [], 2: [(10, 10)], 3: [(20, 20)]}]
    assert S._buy_fuel_plan({3: 2, 2: 1}, [4]) == {3: 0, 2: 0}
    assert log["clicks"] == [] and log["shelves"]          # not even read
    log["shelves"] = [{1: [], 2: [(10, 10)], 3: [(20, 20)]},
                      {1: [], 2: [(10, 10)], 3: [(21, 21)]},
                      {1: [], 2: [(10, 10)], 3: []}]
    have = {3: 2, 2: 1}
    assert S._buy_fuel_plan(have, [4], stock=True) == {3: 0, 2: 0}
    assert log["clicks"] == [(20, 20), (21, 21)] and have[3] == 4
    assert log["refresh"] == 0


def test_the_tab_order_stops_at_the_first_short_target(fuse_menu):
    log = fuse_menu
    log["pool"] = {1: [], 2: [(1, 1, 0)] * 3, 3: [(2, 2, 0)], 4: []}
    log["next"] = []
    S._fuse_session(["Fragment of Conceit", "Grand Welcome"], set(),
                    buy_allowed=False, sequential=True)
    assert log["crafts"] == []
    assert log["keywords"] == ["repoise"]
    log["pool"] = {1: [], 2: [(1, 1, 0)] * 3, 3: [(2, 2, 0)], 4: []}
    S._fuse_session(["Fragment of Conceit", "Grand Welcome"], set(),
                    buy_allowed=False)
    assert log["crafts"] == [3]                              # the plan goes on


def test_a_target_craftable_from_the_pool_is_not_shopped_for(fuse_menu):
    log = fuse_menu
    log["pool"] = {1: [], 2: [(1, 1, 0)] * 2, 3: [], 4: [(5, 5, 0)]}
    log["next"] = ["Fragment of Conceit"]
    done = set()
    S._fuse_session(["Fragment of Conceit"], done, buy_allowed=True)
    assert log["buys"] == 0 and log["crafts"] == [4]
    assert done == {"Fragment of Conceit"}


def test_a_craft_on_the_last_attempt_is_still_recorded(fuse_menu, monkeypatch):
    log = fuse_menu
    monkeypatch.setattr(S, "_CUSTOM_FUSE_CAP", 1)
    log["pool"] = {1: [], 2: [(1, 1, 0)], 3: [(2, 2, 0)] * 2, 4: []}
    log["next"] = ["Fragment of Conceit"]
    done = set()
    S._fuse_session(["Fragment of Conceit"], done)
    assert log["crafts"] == [4] and done == {"Fragment of Conceit"}


def test_a_keyword_dialog_left_open_is_dealt_with_before_scanning(fuse_menu, monkeypatch):
    log = fuse_menu
    shown = iter([False, True])
    monkeypatch.setattr(S, "now", types.SimpleNamespace(
        button=lambda name, *a, **k: name == "keywordSel" and next(shown, False)))
    log["pool"] = {1: [], 2: [(1, 1, 0)] * 2, 3: [(2, 2, 0)] * 4, 4: []}
    log["next"] = ["Fragment of Conceit", "Clear Mirror, Calm Water"]
    S._fuse_session(["Fragment of Conceit", "Clear Mirror, Calm Water"], set())
    assert log["keywords"] == ["repoise", "repoise"]


def test_the_session_flags_its_scans(fuse_menu, monkeypatch):
    log = fuse_menu
    seen = []
    log["pool"] = {1: [], 2: [(1, 1, 0)], 3: [(2, 2, 0)] * 2, 4: []}
    log["next"] = ["Fragment of Conceit"]
    monkeypatch.setattr(S, "get_inventory", lambda: (seen.append(p.CUSTOM_FUSE_ACTIVE),
                                                       log["pool"], log["pool"], {})[1:])
    S._fuse_session(["Fragment of Conceit"], set())
    assert seen == [True] and p.CUSTOM_FUSE_ACTIVE is False


def test_the_reserve_skips_upties_of_gifts_not_yet_crafted(monkeypatch):
    import wbcore.market_catalog as MC
    cat = {"Clear Mirror, Calm Water": {"tier": 4}, "Artistic Sense": {"tier": 4}}
    monkeypatch.setattr(MC, "load_market_catalog", lambda: cat)
    targets = [("Clear Mirror, Calm Water", 2), ("Artistic Sense", 2)]
    assert S._uptie_reserve(targets, {}, ["Clear Mirror, Calm Water", "Artistic Sense"]) == 0
    assert S._uptie_reserve(targets, {}, ["Artistic Sense"]) == 300
    assert S._uptie_reserve(targets, {"Clear Mirror, Calm Water": 1}, ["Artistic Sense"]) == 100
    assert S._uptie_reserve(targets, {}, []) == 600


def test_team_stems_match_the_plan_names():
    kept = ["Clear Mirror, Calm Water", "Cigarette Holder", "Artistic Sense"]
    assert S._stem_named("clearmirror", kept)
    assert S._stem_named("holder", kept)
    assert S._stem_named("artisticsense", kept)
    assert not S._stem_named("grandwelcome", kept)
    assert not S._stem_named("conceit", [])


def test_the_plan_protections_reach_the_scan_when_the_tab_is_empty(monkeypatch):
    plan = {"protected": ["Fragment of Conceit", "Cigarette Holder"],
            "fuse": ["Fragment of Conceit"], "enhance2": []}
    seen = {}
    monkeypatch.setattr(S, "_hollow_plan", lambda: plan)
    monkeypatch.setattr(S, "_scripted_order", lambda names: list(names or []))
    monkeypatch.setattr(S, "_held_back", lambda t: t)
    monkeypatch.setattr(S, "_fuse_session", lambda *a, **k: seen.update(
        keep=list(p.MARKET_GIFTS.get("keep_fuse") or []), kw=dict(k)))
    monkeypatch.setattr(S, "_enhance_catalog", lambda t: None)
    monkeypatch.setattr(p, "MARKET_GIFTS", {})
    monkeypatch.setattr(p, "CUSTOM_MARKET_DONE", False)
    monkeypatch.setattr(p, "CUSTOM_FUSE_DONE", set())
    for flag in ("SKIP_EGO_BUYING", "SKIP_EGO_FUSION", "SKIP_EGO_ENHANCING"):
        monkeypatch.setattr(p, flag, False, raising=False)
    before = p.MARKET_GIFTS
    S.custom_market()
    assert seen["keep"] == plan["protected"]
    assert seen["kw"]["sequential"] is False and seen["kw"]["stock"] is True
    assert p.MARKET_GIFTS is before and "keep_fuse" not in p.MARKET_GIFTS


# --- must-gets before the others -------------------------------------------

def test_the_must_gets_go_first_whatever_their_keyword(fuse_menu):
    log = fuse_menu
    log["pool"] = {1: [], 2: [(1, 1, 0)] * 4, 3: [(2, 2, 0)] * 8, 4: []}
    names = ["Fragment of Conceit", "Fragment of Decay",
             "Clear Mirror, Calm Water", "Artistic Sense"]
    log["next"] = list(names)
    done = set()
    S._fuse_session(names, done, must=names[:2])
    assert log["keywords"] == ["repoise", "resinking", "repoise", "resinking"]
    assert log["crafts"] == [4, 4, 4, 4] and done == set(names)
    assert log["opens"] == 1


def test_fuel_is_bought_for_the_others_once_the_must_gets_are_done(fuse_menu):
    log = fuse_menu
    log["pool"] = {1: [], 2: [(1, 1, 0)], 3: [(2, 2, 0)], 4: []}     # one tier 3 short

    def buy(have, tiers, keep=0, **k):
        log["buys"] += 1
        log["pool"][3].append((3, 3, 0))
    S._buy_fuel_plan = buy
    log["next"] = ["Clear Mirror, Calm Water"]
    done = set()
    S._fuse_session(["Clear Mirror, Calm Water"], done, buy_allowed=True,
                    must=["Fragment of Conceit", "Fragment of Decay"])   # both done
    assert log["buys"] == 1 and done == {"Clear Mirror, Calm Water"}
    log["pool"] = {1: [], 2: [(1, 1, 0)], 3: [(2, 2, 0)], 4: []}
    log["next"] = ["Fragment of Decay"]
    done = set()
    S._fuse_session(["Fragment of Decay", "Clear Mirror, Calm Water"], done,
                    buy_allowed=True, must=["Fragment of Decay"])
    assert log["buys"] == 2 and "Fragment of Decay" in done


# --- one short tier 4 ends the hunt for the others -------------------------

def test_a_short_tier_4_leaves_the_other_tier_4s_for_the_next_shop(fuse_menu):
    log = fuse_menu
    log["pool"] = {1: [], 2: [(1, 1, 0)], 3: [(2, 2, 0)], 4: []}
    log["next"] = []
    names = ["Fragment of Conceit", "Fragment of Decay",
             "Clear Mirror, Calm Water", "Artistic Sense"]
    S._fuse_session(names, set(), buy_allowed=False, must=names[:2])
    assert log["keywords"] == ["repoise"]                    # no flip-flop
    assert log["scans"] == 1 and log["crafts"] == []
    # A lower tier after a short tier 4 is still tried (3 tier 2s make it).
    log["pool"] = {1: [], 2: [(1, 1, 0)] * 3, 3: [(2, 2, 0)], 4: []}
    S._fuse_session(["Fragment of Conceit", "Grand Welcome"], set(), buy_allowed=False)
    assert log["crafts"] == [3]


# --- the upties wait for every craft ---------------------------------------

def _market_visit(monkeypatch, plan, done_fuse, floor):
    seen = {"enhanced": None}
    monkeypatch.setattr(S, "_hollow_plan", lambda: plan)
    monkeypatch.setattr(S, "_scripted_order", lambda names: list(names or []))
    monkeypatch.setattr(S, "_held_back", lambda t: t)
    monkeypatch.setattr(S, "_fuse_session", lambda *a, **k: None)
    monkeypatch.setattr(S, "_uptie_reserve", lambda *a, **k: 0)
    monkeypatch.setattr(S, "_enhance_catalog", lambda t: seen.__setitem__("enhanced", list(t)))
    monkeypatch.setattr(p, "MARKET_GIFTS", {})
    monkeypatch.setattr(p, "CUSTOM_MARKET_DONE", False)
    monkeypatch.setattr(p, "CUSTOM_FUSE_DONE", set(done_fuse))
    monkeypatch.setattr(p, "CUSTOM_ENHANCE_DONE", {})
    monkeypatch.setattr(p, "LVL", floor)
    for flag in ("SKIP_EGO_BUYING", "SKIP_EGO_FUSION", "SKIP_EGO_ENHANCING"):
        monkeypatch.setattr(p, flag, False, raising=False)
    S.custom_market()
    return seen["enhanced"]


def test_the_upties_wait_until_every_gift_is_crafted(monkeypatch):
    four = ["Fragment of Conceit", "Fragment of Decay",
            "Clear Mirror, Calm Water", "Artistic Sense"]
    plan = {"protected": [], "fuse": ["Fragment of Decay"], "must": four[:2],
            "enhance2": four[2:]}
    assert _market_visit(monkeypatch, plan, four[:1] + four[2:], 3) is None
    plan_done = dict(plan, fuse=[])
    assert _market_visit(monkeypatch, plan_done, four, 3) == [(n, 2) for n in four[2:]]
    assert _market_visit(monkeypatch, plan, four[:1] + four[2:], 4) == [(n, 2) for n in four[2:]]


def test_an_unscanned_shelf_ends_the_session_with_a_warning(fuse_menu, monkeypatch, caplog):
    log = fuse_menu
    monkeypatch.setattr(S, "get_inventory", lambda: ({}, {}, {}))   # Skip EGO check
    names = ["Fragment of Conceit", "Fragment of Decay"]
    with caplog.at_level("WARNING"):
        S._fuse_session(names, set(), must=names)
    assert log["keywords"] == ["repoise"] and log["crafts"] == []
    assert "Skip EGO check" in caplog.text
