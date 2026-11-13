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


def test_the_plan_replays_the_sessions_own_fusing():
    # A third tier 3 does for the tier 2.
    assert S.plan_fuel({3: 3}, [4]) == (0, {3: 0, 2: 0})
    assert S.plan_fuel({3: 5}, [4, 4]) == (0, {3: 0, 2: 1})
    # A spare tier 4 (a craft that landed on another keyword) takes one
    # tier 3 and any other gift, or two tier 2s.
    assert S.plan_fuel({4: 1, 3: 1, 1: 1}, [4]) == (0, {3: 0, 2: 0})
    assert S.plan_fuel({4: 1, 2: 1, 1: 2}, [4]) == (0, {3: 0, 2: 1})
    assert S.plan_fuel({4: 1}, [4]) == (0, {3: 0, 2: 2})


def test_a_super_shop_plan_counts_its_cheaper_fusions(monkeypatch):
    monkeypatch.setattr(p, "SUPER", "supershop")
    assert S.plan_fuel({3: 2, 1: 1}, [4]) == (0, {3: 0, 2: 0})
    assert S.plan_fuel({2: 4}, [4]) == (0, {3: 0, 2: 0})
    assert S.plan_fuel({}, [4]) == (0, {3: 1, 2: 2})


def test_uptie_costs_follow_the_dialog():
    assert S.uptie_cost(4) == 100 and S.uptie_cost(4, 2) == 300
    assert S.uptie_cost(1) == 50
    assert S.uptie_cost(None) == 100


# --- buying fuel -----------------------------------------------------------

ROCK, MIRROR = "Fragment of Conceit", "Clear Mirror, Calm Water"
DECAY, SENSE = "Fragment of Decay", "Artistic Sense"
T4 = {ROCK: 4, MIRROR: 4, DECAY: 4, SENSE: 4}


@pytest.fixture
def shop_screen(monkeypatch):
    """A shop screen: a cost and one shelf per refresh, {tier: [positions]}
    on sale plus the plan's gifts by name in log["named"]. A purchase
    takes the gift off its shelf and its price (250 unless log["price"]
    says otherwise) off the cost; a position in log["stuck"] will not
    sell. Refreshes cost what the visit's count makes them, and a shelf
    the test does not describe shows one tier 1 gift."""
    log = {"clicks": [], "refresh": 0, "shelves": [], "named": [], "funds": 1000,
           "price": {}, "stuck": set(), "at": 0, "pending": None}

    def shelf():
        while len(log["shelves"]) <= log["at"]:
            log["shelves"].append({1: [(900, 900)], 2: [], 3: []})
        return log["shelves"][log["at"]]

    def named():
        while len(log["named"]) <= log["at"]:
            log["named"].append({})
        return log["named"][log["at"]]

    def click(pos, **k):
        if pos == (1489, 177):
            log["refresh"] += 1
            log["funds"] -= S._refresh_fee()
            log["at"] += 1
        else:
            log["pending"] = pos

    def conf_gift():
        pos, log["pending"] = log["pending"], None
        if pos is None or pos in log["stuck"]:
            return
        log["clicks"].append(pos)
        log["funds"] -= log["price"].get(pos, 250)
        for found in shelf().values():
            if pos in found:
                found.remove(pos)
        for name in [n for n, at in named().items() if at == pos]:
            del named()[name]

    monkeypatch.setattr(S, "update_shelf", lambda: None)
    monkeypatch.setattr(S, "get_shop", lambda _shelf: {t: list(v) for t, v in shelf().items()})
    monkeypatch.setattr(S, "_shelf_gifts", lambda _shelf, names: {
        n: at for n, at in named().items() if n in names})
    monkeypatch.setattr(S, "balance", lambda: log["funds"])
    monkeypatch.setattr(S, "conf_gift", conf_gift)
    monkeypatch.setattr(S, "connection", lambda: None)
    monkeypatch.setattr(S, "close_panel", lambda: None)
    monkeypatch.setattr(S.time, "sleep", lambda s: None)
    monkeypatch.setattr(S, "win_click", lambda *a, **k: click(a[0] if len(a) == 1 else (a[0], a[1]), **k))
    monkeypatch.setattr(p, "SHELF_REFRESHES", 0, raising=False)
    monkeypatch.setattr(p, "BUFF", [0] * 10)
    monkeypatch.setattr(p, "SUPER", "shop")
    monkeypatch.setattr(p, "WISHMAKING", False)
    return log


def _dull(n):
    """Shelves with nothing a tier 4 craft can use."""
    return [{1: [(900, 900)], 2: [], 3: []} for _ in range(n)]


def test_tier_3s_are_bought_first_and_a_tier_2_only_to_finish(shop_screen):
    log = shop_screen
    log["shelves"] = [{1: [], 2: [(10, 10)], 3: [(20, 20)]}]
    have = {3: 1, 2: 0}
    assert S._buy_fuel(have, [ROCK], T4) == (None, [])
    assert log["clicks"] == [(20, 20), (10, 10)]
    assert have == {3: 2, 2: 1} and log["refresh"] == 0 and log["funds"] == 500


def test_a_tier_2_stays_on_the_shelf_while_the_tier_3s_are_short(shop_screen):
    log = shop_screen
    log["shelves"] = [{1: [], 2: [(10, 10)], 3: []},
                      {1: [], 2: [(11, 11)], 3: [(21, 21)]}]
    have = {3: 0, 2: 1}
    short, got = S._buy_fuel(have, [ROCK], T4)
    assert log["clicks"] == [(21, 21)] and have == {3: 1, 2: 1}
    assert short == (ROCK, {3: 1, 2: 0}) and got == []


def test_a_tier_2_that_makes_a_tier_3_of_the_spare_ones_is_bought(shop_screen):
    log = shop_screen
    log["shelves"] = [{1: [], 2: [(10, 10)], 3: []}]
    have = {3: 1, 2: 3}                       # one more tier 2: three for a tier 3, one for the craft
    assert S._buy_fuel(have, [ROCK], T4) == (None, [])
    assert log["clicks"] == [(10, 10)] and have == {3: 1, 2: 4}


def test_a_third_tier_3_finishes_a_craft_when_no_tier_2_shows(shop_screen):
    log = shop_screen
    log["shelves"] = [{1: [], 2: [], 3: [(20, 20)]}]
    have = {3: 2, 2: 0}
    assert S._buy_fuel(have, [ROCK], T4) == (None, [])
    assert log["clicks"] == [(20, 20)] and have[3] == 3


def test_the_free_refresh_comes_first_and_each_paid_one_costs_15_more(shop_screen, monkeypatch):
    log = shop_screen
    monkeypatch.setattr(p, "BUFF", [1] + [0] * 9)        # Star of the Beginning
    assert S._free_refreshes() == 1 and S._refresh_fee() == 0
    log["shelves"] = _dull(3) + [{1: [], 2: [], 3: [(7, 7)]}]
    have = {3: 1, 2: 1}
    assert S._buy_fuel(have, [ROCK], T4) == (None, [])
    assert log["refresh"] == 3 and p.SHELF_REFRESHES == 3
    assert log["funds"] == 1000 - 0 - 15 - 30 - 250
    assert S._refresh_fee() == 45
    monkeypatch.setattr(p, "BUFF", [3] + [0] * 9)        # at ++: two free ones
    assert S._free_refreshes() == 2 and S._refresh_fee() == 30


def test_refreshes_are_paid_for_only_where_the_floor_rule_allows(shop_screen, monkeypatch):
    log = shop_screen
    monkeypatch.setattr(p, "BUFF", [1] + [0] * 9)
    log["shelves"] = _dull(2) + [{1: [], 2: [], 3: [(5, 5)]}]
    have = {3: 1, 2: 1}
    short, _got = S._buy_fuel(have, [ROCK], T4, paid_for=lambda name: False)
    assert short == (ROCK, {3: 1, 2: 0})
    assert log["refresh"] == 1 and log["clicks"] == []       # the free one, no more
    # Paid for the rock, not for the craft ranked after it.
    log["at"], log["refresh"] = 0, 0
    monkeypatch.setattr(p, "SHELF_REFRESHES", 0)
    have = {3: 1, 2: 1}
    short, _got = S._buy_fuel(have, [ROCK, MIRROR], T4,
                              paid_for=lambda name: name == ROCK)
    assert log["clicks"] == [(5, 5)] and log["refresh"] == 2
    assert short == (MIRROR, {3: 2, 2: 1})


def test_buying_leaves_what_is_kept_back_and_stops_when_the_cost_runs_out(shop_screen):
    log = shop_screen
    log["shelves"] = [{1: [], 2: [(10, 10)], 3: [(20, 20), (200, 20)]}]
    log["funds"] = 260                                    # under a tier 3's price
    assert S._buy_fuel({}, [ROCK], T4) == ((ROCK, {3: 2, 2: 1}), [])
    assert log["clicks"] == [] and log["refresh"] == 0
    log["funds"] = 600
    assert S._buy_fuel({}, [ROCK], T4, keep=400)[0] == (ROCK, {3: 2, 2: 1})
    assert log["clicks"] == [] and log["refresh"] == 0
    # A ranked reserve: the first craft spends freely, the next one keeps
    # the uptie ranked before it.
    have = {3: 1, 2: 1}
    short, _got = S._buy_fuel(have, [MIRROR, DECAY], T4, keep={MIRROR: 0, DECAY: 300})
    assert log["clicks"] == [(20, 20)] and log["funds"] == 350
    assert short == (DECAY, {3: 2, 2: 1}) and log["refresh"] == 0


def test_the_trip_goes_on_while_the_cost_holds_out(shop_screen):
    """A floor 5 shop with 1101 cost and one tier 3 short of the last
    craft: the shelf is refreshed until the tier 3 shows, not three
    times; with never a tier 3, until a refresh would leave less than
    one costs."""
    log = shop_screen
    log["funds"] = 1101
    log["shelves"] = _dull(6) + [{1: [], 2: [], 3: [(7, 7)]}]
    have = {3: 1, 2: 1}
    assert S._buy_fuel(have, [SENSE], T4) == (None, [])
    assert log["refresh"] == 6 and log["clicks"] == [(7, 7)]
    assert log["funds"] == 1101 - 15 * (1 + 2 + 3 + 4 + 5 + 6) - 250
    log["shelves"], log["at"], log["refresh"], log["funds"] = [], 0, 0, 1101
    p.SHELF_REFRESHES = 0
    short, _got = S._buy_fuel({3: 1, 2: 1}, [SENSE], T4)       # never a tier 3
    assert short == (SENSE, {3: 1, 2: 0})
    assert log["refresh"] == 9 and log["funds"] == 426         # a tenth would leave 276
    log["at"], log["refresh"], log["funds"] = 0, 0, 330
    p.SHELF_REFRESHES = 0
    S._buy_fuel({3: 1, 2: 1}, [SENSE], T4)
    assert log["refresh"] == 1 and log["funds"] == 315         # a second would leave 285


def test_shelves_with_nothing_end_the_trip(shop_screen, monkeypatch):
    log = shop_screen
    log["funds"] = 5000
    monkeypatch.setattr(S, "_DRY_SHELVES_CAP", 4)
    short, _got = S._buy_fuel({3: 1, 2: 1}, [SENSE], T4)
    assert short == (SENSE, {3: 1, 2: 0}) and log["refresh"] == 4
    # Shelves that show no gift at all are not being read: three, no more.
    log["shelves"] = [{1: [], 2: [], 3: []} for _ in range(8)]
    log["at"], log["refresh"] = 0, 0
    S._buy_fuel({3: 1, 2: 1}, [SENSE], T4)
    assert log["refresh"] == S._BLIND_SHELVES_CAP - 1 == 2


def test_tier_2s_go_towards_a_tier_3_once_the_search_costs_more(shop_screen):
    """One tier 3 short with two tier 2s spare: two more tier 2s make it
    (400). The next three refreshes cost 90 at first, so the shelf is
    refreshed; after two paid ones they cost 180 and the tier 2s win."""
    log = shop_screen
    log["shelves"] = [{1: [], 2: [(10 + 200 * i, 10), (10 + 200 * i, 300)], 3: []}
                      for i in range(4)]
    have = {3: 1, 2: 3}                    # two spare, one for the craft itself
    have[2] -= 1
    assert S._search_fee() == 15 + 30 + 45
    assert S._buy_fuel(have, [ROCK], T4) == (None, [])
    assert log["refresh"] == 2 and log["clicks"] == [(410, 10), (410, 300)]
    assert have == {3: 1, 2: 4}
    # Where the floor spends no cost on refreshes, only a tier 2 that
    # completes a tier 3 at once is bought.
    log["at"], log["refresh"], log["clicks"] = 0, 0, []
    p.SHELF_REFRESHES = 0
    have = {3: 1, 2: 2}
    short, _got = S._buy_fuel(have, [ROCK], T4, paid_for=lambda name: False)
    assert short == (ROCK, {3: 1, 2: 0}) and log["clicks"] == [] and log["refresh"] == 0


def test_a_purchase_counts_only_once_the_cost_has_dropped(shop_screen):
    log = shop_screen
    log["shelves"] = [{1: [], 2: [], 3: [(20, 20), (200, 20)]}]
    log["stuck"] = {(20, 20)}                              # the click does nothing
    have = {3: 1, 2: 1}
    assert S._buy_fuel(have, [ROCK], T4) == (None, [])
    assert log["clicks"] == [(200, 20)] and have[3] == 2
    # Two purchases that will not go through end the trip.
    log["shelves"], log["at"], log["clicks"] = [{1: [], 2: [], 3: [(20, 20), (200, 20)]}], 0, []
    log["stuck"] = {(20, 20), (200, 20)}
    have = {3: 1, 2: 1}
    short, _got = S._buy_fuel(have, [ROCK], T4)
    assert short == (ROCK, {3: 1, 2: 0}) and have[3] == 1
    assert log["clicks"] == [] and log["refresh"] == 0


def test_the_cost_is_read_once_it_has_stopped_changing(monkeypatch):
    readings = [900, 850, 780, 750, 750, 750]
    monkeypatch.setattr(S, "balance", lambda: readings.pop(0))
    monkeypatch.setattr(S.time, "sleep", lambda s: None)
    assert S._settled_cost() == 750 and readings == [750]
    # A purchase is not confirmed by the tail of the last one's drop.
    readings[:] = [700, 700, 700, 700]
    monkeypatch.setattr(S, "win_click", lambda *a, **k: None)
    monkeypatch.setattr(S, "conf_gift", lambda: None)
    monkeypatch.setattr(S, "close_panel", lambda: None)
    assert S._buy_shelf_gift((5, 5), 700) is None
    readings[:] = [640, 450, 450]
    assert S._buy_shelf_gift((5, 5), 700) == 450


def test_a_gift_of_the_plan_on_the_shelf_is_bought_outright(shop_screen):
    log = shop_screen
    log["shelves"] = [{1: [], 2: [], 3: [(20, 20)]}]
    log["named"] = [{MIRROR: (300, 300)}]
    log["price"] = {(300, 300): 390}
    have = {3: 2, 2: 1}                                   # the rock's own fuel is in hand
    assert S._buy_fuel(have, [ROCK, MIRROR], T4) == (None, [MIRROR])
    assert log["clicks"] == [(300, 300)] and log["funds"] == 610
    # Not while the cost is needed for the craft ranked before it.
    log["shelves"] = [{1: [], 2: [(10, 10)], 3: [(20, 20), (200, 20)]}]
    log["named"], log["at"], log["clicks"], log["funds"] = [{MIRROR: (300, 300)}], 0, [], 800
    have = {}
    short, got = S._buy_fuel(have, [ROCK, MIRROR], T4)
    assert got == [] and log["clicks"] == [(20, 20), (200, 20), (10, 10)]
    assert short == (MIRROR, {3: 2, 2: 1}) and log["funds"] == 50


def test_spare_tier_3s_are_stocked_down_to_the_upties_cost(shop_screen):
    log = shop_screen
    log["shelves"] = [{1: [], 2: [(10, 10)], 3: [(20, 20), (200, 20)]}]
    have = {3: 2, 2: 1}
    assert S._buy_fuel(have, [ROCK], T4) == (None, [])
    assert log["clicks"] == []                              # covered, and no stock asked for
    log["funds"] = 900
    assert S._buy_fuel(have, [ROCK], T4, stock=600) == (None, [])
    assert log["clicks"] == [(20, 20)] and have[3] == 3 and log["funds"] == 650
    assert log["refresh"] == 0


def test_tier_1_gifts_no_craft_uses_are_sold_when_the_cost_is_short(shop_screen):
    log = shop_screen
    calls = []

    def raise_cost(target, limit):
        calls.append((target, limit))
        log["funds"] += 75 * limit
    log["funds"] = 200
    log["shelves"] = [{1: [], 2: [], 3: [(20, 20)]}]
    have = {1: 3, 2: 1, 3: 1}
    assert S._buy_fuel(have, [ROCK], T4, raise_cost=raise_cost) == (None, [])
    assert calls == [(250, 3)] and have[1] == 0
    assert log["clicks"] == [(20, 20)]
    # Enough cost: nothing sold. A tier 1 a craft would use is not spare.
    log["funds"], log["at"] = 1000, 0
    log["shelves"] = [{1: [], 2: [], 3: [(20, 20)]}]
    S._buy_fuel({1: 3, 2: 1, 3: 1}, [ROCK], T4, raise_cost=raise_cost)
    assert len(calls) == 1
    # Nor is anything sold for a craft the floor spends no cost on.
    log["funds"], log["at"] = 200, 0
    log["shelves"] = [{1: [], 2: [], 3: []}]
    S._buy_fuel({1: 3, 2: 1, 3: 1}, [MIRROR], T4, raise_cost=raise_cost,
                paid_for=lambda name: name == ROCK)
    assert len(calls) == 1
    assert S._spare_tier1({1: 3, 2: 1, 3: 1}, [4]) == 3
    assert S._spare_tier1({4: 1, 3: 1, 1: 1}, [4, 4]) == 0


def test_sell_takes_only_the_tiers_and_the_number_asked_for(monkeypatch):
    state = {"funds": 100, "passes": []}

    def search(reg, tiers=(2, 1, 3, 4)):
        state["passes"].append(tiers)
        state["funds"] += 75
        return True
    monkeypatch.setattr(S, "balance", lambda: state["funds"])
    monkeypatch.setattr(S, "search_sell", search)
    monkeypatch.setattr(S, "Action", lambda *a, **k: types.SimpleNamespace(execute=lambda *_: None))
    monkeypatch.setattr(S, "close_panel", lambda: None)
    monkeypatch.setattr(S.time, "sleep", lambda s: None)
    assert S.sell({"fuel": 600}, tiers=(1,), limit=2) is False
    assert state["passes"] == [(1,), (1,)] and state["funds"] == 250
    assert S.sell({"fuel": 300}, tiers=(1,), limit=5) is True
    assert state["passes"][-1] == (1,) and state["funds"] == 325
    state["passes"].clear()
    assert S.sell({"all": 400}) is True                       # the old call, the old order
    assert state["passes"] == [(2, 1, 3, 4)]


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

    def actual(tier, pool):
        # The real decision on the menu's own pool: a tier 4 fusion yields
        # the next gift of log["next"], anything lower a tier 3.
        combo, missing = S.decide_fusion(tier, log["pool"])
        if missing:
            return missing
        for t in combo:
            log["pool"][t].pop()
        if tier == 4 and sum(S.item_points[t] for t in combo) >= 25:
            log["crafts"].append(4)
            log["owned"].add(log["next"].pop(0))
        else:
            log["crafts"].append(3)
            log["pool"][3].append((9, 9, 0))
        return None

    monkeypatch.setattr(S, "_open_fuse_menu", open_menu)
    monkeypatch.setattr(S, "_select_fuse_keyword", select)
    monkeypatch.setattr(S, "_shelf_has_catalog", shelf_has)
    monkeypatch.setattr(S, "get_inventory", inventory)
    def buy(have, names, tier_of, **k):
        log["buys"] += 1
        return None, []

    monkeypatch.setattr(S, "actual_fuse", actual)
    monkeypatch.setattr(S, "now", types.SimpleNamespace(button=lambda *a, **k: False))
    monkeypatch.setattr(S, "close_panel", lambda: log.__setitem__("closed", log["closed"] + 1))
    monkeypatch.setattr(S, "_buy_fuel", buy)
    monkeypatch.setattr(S.time, "sleep", lambda s: None)
    monkeypatch.setattr(p, "EXTREME", False)
    monkeypatch.setattr(p, "SUPER", "shop")
    monkeypatch.setattr(p, "WISHMAKING", False)
    monkeypatch.setattr(p, "RUN_SCRIPT", "")
    monkeypatch.setattr(p, "RUN_HELD", set(), raising=False)
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


def test_a_short_pool_sends_the_bot_shopping_once_then_back_in(fuse_menu, monkeypatch):
    log = fuse_menu
    log["pool"] = {1: [], 2: [(1, 1, 0)], 3: [(2, 2, 0)], 4: []}  # one tier 3 short
    log["next"] = ["Fragment of Conceit"]

    def buy(have, names, tier_of, **k):
        log["buys"] += 1
        log["pool"][3].append((3, 3, 0))                   # the shop had one
        return None, []
    monkeypatch.setattr(S, "_buy_fuel", buy)
    done = set()
    S._fuse_session(["Fragment of Conceit"], done, buy_allowed=True)
    assert log["buys"] == 1
    assert log["opens"] == 2 and log["closed"] == 2          # out to buy, back in
    assert log["keywords"] == ["repoise", "repoise"]         # reselected after reopening
    assert done == {"Fragment of Conceit"}


def test_a_craft_that_leaves_the_pool_short_sends_the_bot_shopping_again(fuse_menu, monkeypatch):
    log = fuse_menu
    log["pool"] = {1: [], 2: [(1, 1, 0)], 3: [(2, 2, 0)], 4: []}
    log["next"] = ["Fragment of Conceit", "Clear Mirror, Calm Water"]
    finds = [[(3, 3, 0)], [(3, 3, 0), (3, 3, 0)]]          # the tier 3s each trip finds

    def buy(have, names, tier_of, **k):
        log["buys"] += 1
        log["pool"][3].extend(finds.pop(0))
        if log["buys"] == 2:
            log["pool"][2].append((1, 1, 0))
        return None, []
    monkeypatch.setattr(S, "_buy_fuel", buy)
    done = set()
    S._fuse_session(["Fragment of Conceit", "Clear Mirror, Calm Water"], done,
                    buy_allowed=True)
    assert log["buys"] == 2
    assert done == {"Fragment of Conceit", "Clear Mirror, Calm Water"}


def test_a_trip_that_stops_short_at_a_craft_is_its_last_of_the_visit(fuse_menu, monkeypatch):
    log = fuse_menu
    log["pool"] = {1: [], 2: [(1, 1, 0)], 3: [(2, 2, 0)], 4: []}
    log["next"] = []

    def buy(have, names, tier_of, **k):
        log["buys"] += 1
        return (names[0], {3: 1, 2: 0}), []                # the cost ran out
    monkeypatch.setattr(S, "_buy_fuel", buy)
    done = set()
    S._fuse_session(["Fragment of Conceit", "Clear Mirror, Calm Water"], done,
                    buy_allowed=True)
    assert log["buys"] == 1 and done == set()


def test_a_craft_gone_wrong_is_shopped_for_again_though_a_later_one_was_short(
        fuse_menu, monkeypatch):
    """The trip covered the rock and stopped short at Clear Mirror; the
    rock's fusion then landed on another keyword. The rock ranks before
    the craft the trip stopped at, so the bot goes out again for it."""
    log = fuse_menu
    rock, mirror = "Fragment of Conceit", "Clear Mirror, Calm Water"
    log["pool"] = {1: [], 2: [(1, 1, 0)], 3: [(2, 2, 0)], 4: []}
    log["next"] = ["a Burn gift", rock]

    def buy(have, names, tier_of, **k):
        log["buys"] += 1
        log["pool"][3].append((3, 3, 0))
        if log["buys"] == 2:
            log["pool"][3].append((3, 3, 0))
            log["pool"][2].append((1, 1, 0))
        return (mirror, {3: 2, 2: 1}), []
    monkeypatch.setattr(S, "_buy_fuel", buy)
    done = set()
    S._fuse_session([rock, mirror], done, buy_allowed=True)
    assert log["buys"] == 2 and done == {rock}
    assert log["crafts"] == [4, 4]


def test_a_craft_that_lands_on_the_keywords_other_target_is_recorded_at_once(fuse_menu):
    log = fuse_menu
    rock, mirror = "Fragment of Conceit", "Clear Mirror, Calm Water"
    log["pool"] = {1: [], 2: [(1, 1, 0)], 3: [(2, 2, 0)] * 2, 4: []}
    log["next"] = [mirror]                                 # the Poise fusion gave Clear Mirror
    done = set()
    S._fuse_session([rock, mirror, "Fragment of Decay"], done, buy_allowed=False)
    assert done == {mirror} and log["crafts"] == [4]
    assert log["keywords"] == ["repoise"]                  # no trip to Sinking for nothing


def test_a_gift_bought_off_the_shelf_is_confirmed_like_a_craft(fuse_menu, monkeypatch, caplog):
    log = fuse_menu
    rock, mirror = "Fragment of Conceit", "Clear Mirror, Calm Water"
    log["pool"] = {1: [], 2: [], 3: [], 4: []}
    log["next"] = []

    def buy(have, names, tier_of, **k):
        log["buys"] += 1
        log["owned"].add(mirror)                           # the shelf sold it
        return (rock, {3: 2, 2: 1}), [mirror]
    monkeypatch.setattr(S, "_buy_fuel", buy)
    done = set()
    with caplog.at_level("INFO"):
        S._fuse_session([rock, mirror], done, buy_allowed=True)
    assert done == {mirror} and log["crafts"] == []
    assert "bought 'Clear Mirror, Calm Water'" in caplog.text


def test_the_buying_trips_of_a_visit_are_capped(fuse_menu):
    log = fuse_menu
    log["pool"] = {1: [], 2: [(1, 1, 0)], 3: [(2, 2, 0)], 4: []}
    log["next"] = []                                       # covered, the trip says; the pool is not
    S._fuse_session(["Fragment of Conceit"], set(), buy_allowed=True)
    assert log["buys"] == S._FUEL_TRIPS_CAP == 3


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


def test_the_reserve_skips_upties_of_gifts_not_yet_crafted(monkeypatch):
    import wbcore.market_catalog as MC
    cat = {"Clear Mirror, Calm Water": {"tier": 4}, "Artistic Sense": {"tier": 4}}
    monkeypatch.setattr(MC, "load_market_catalog", lambda: cat)
    targets = [("Clear Mirror, Calm Water", 2), ("Artistic Sense", 2)]
    assert S._uptie_reserve(targets, {}, ["Clear Mirror, Calm Water", "Artistic Sense"]) == 0
    assert S._uptie_reserve(targets, {}, ["Artistic Sense"]) == 300
    # One level bought: the second costs twice the first.
    assert S._uptie_reserve(targets, {"Clear Mirror, Calm Water": 1}, ["Artistic Sense"]) == 200
    assert S.uptie_owed(4, 0, 2) == 300 and S.uptie_owed(4, 1, 2) == 200
    assert S.uptie_owed(4, 2, 2) == 0 and S.uptie_owed(2, 0, 1) == 60
    assert S._uptie_reserve(targets, {}, []) == 600


def test_a_floor_plan_keeps_back_only_the_upties_ranked_before_a_craft(monkeypatch):
    """Poise Rock > CMCW++ > Sinking Rock > Artistic Sense++: Clear Mirror's
    fuel waits for no uptie, the Sinking Rock's waits for Clear Mirror's."""
    import wbcore.market_catalog as MC
    conceit, mirror = "Fragment of Conceit", "Clear Mirror, Calm Water"
    decay, sense = "Fragment of Decay", "Artistic Sense"
    cat = {n: {"tier": 4} for n in (conceit, mirror, decay, sense)}
    cat["Nebulizer"] = {"tier": 2}
    monkeypatch.setattr(MC, "load_market_catalog", lambda: cat)
    plan = {"targets": [conceit, mirror, decay, sense]}
    twice = [(mirror, 2), (sense, 2)]
    # The owner's floor 4 shop: everything crafted but Clear Mirror.
    assert S._ranked_reserve(plan, twice, {}, {conceit, decay, sense}) == {mirror: 0}
    assert S._ranked_reserve(plan, twice, {}, {conceit}) == {
        mirror: 0, decay: 300, sense: 300}
    assert S._ranked_reserve(plan, twice, {mirror: 2}, {conceit, mirror}) == {
        decay: 0, sense: 0}
    assert S._ranked_reserve(plan, twice, {mirror: 1}, {conceit, mirror}) == {
        decay: 200, sense: 200}
    # An uptie tagged on a gift outside the plan is kept throughout.
    extra = twice + [("Nebulizer", 2)]
    assert S._ranked_reserve(plan, extra, {}, {conceit}) == {
        mirror: 180, decay: 480, sense: 480}
    assert S._ranked_reserve({"targets": []}, twice, {}, set()) == {}


def test_a_plan_keeps_its_targets_and_uptie_gifts_whatever_the_tags_say():
    plan = {"protected": ["Torn Bandolier", ROCK], "targets": [ROCK, MIRROR, DECAY],
            "fuse": [MIRROR, DECAY], "enhance1": [], "enhance2": [MIRROR, "Nebulizer"]}
    assert S._plan_kept(plan) == ["Torn Bandolier", ROCK, MIRROR, DECAY, "Nebulizer"]
    assert S._plan_kept({"protected": [ROCK], "fuse": [MIRROR]}) == [ROCK, MIRROR]


def test_a_protected_gift_the_scan_cannot_find_stops_the_fusing(fuse_menu, monkeypatch, caplog):
    """Sharp Needle & Thread came from the gift search and the plan keeps
    it; a shelf scan that does not report it cannot tell it from fuel."""
    log = fuse_menu
    thread = "Sharp Needle & Thread"
    reported = []
    monkeypatch.setattr(p, "RUN_SCRIPT", "hollow")
    monkeypatch.setattr(p, "RUN_HELD", {thread, "Grand Welcome"})
    monkeypatch.setattr(p, "MARKET_GIFTS", {"keep_fuse": [ROCK, thread]})
    monkeypatch.setattr(S, "_report_unseen", lambda names: reported.append(list(names)))
    log["pool"] = {1: [], 2: [(1, 1, 0)], 3: [(2, 2, 0)] * 2, 4: []}
    log["next"] = [ROCK]
    done = set()
    with caplog.at_level("WARNING"):
        S._fuse_session([ROCK], done)
    assert done == set() and log["crafts"] == [] and log["scans"] == 2   # looked twice
    assert reported == [[thread]] and "not recognised" in caplog.text
    # Reported by the scan: the session goes on. Grand Welcome is held but
    # not kept on this floor, so it is not looked for.
    seen = {"kept:" + thread: (5, 5, 0)}
    monkeypatch.setattr(S, "get_inventory", lambda: (log["pool"], log["pool"], seen))
    S._fuse_session([ROCK], done)
    assert done == {ROCK}
    assert S._unseen_kept({}) == [thread]
    monkeypatch.setattr(p, "RUN_SCRIPT", "saikai_ryoshu")
    assert S._unseen_kept({}) == []


def test_team_stems_match_the_plan_names():
    kept = ["Clear Mirror, Calm Water", "Cigarette Holder", "Artistic Sense"]
    assert S._stem_name("clearmirror", kept) == "Clear Mirror, Calm Water"
    assert S._stem_name("grandwelcome", kept) is None
    assert S._stem_name("holder", kept) == "Cigarette Holder"
    assert S._stem_name("artisticsense", kept) == "Artistic Sense"
    assert S._stem_name("conceit", []) is None


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
    monkeypatch.setattr(p, "LVL", 3)
    S.custom_market()
    assert seen["keep"] == plan["protected"]
    from wbcore import hollow as H
    assert seen["kw"]["sequential"] is False and seen["kw"]["stock"] == 0
    assert seen["kw"]["paid_for"] is H.paid_refreshes
    assert p.MARKET_GIFTS is before and "keep_fuse" not in p.MARKET_GIFTS
    sold = []
    monkeypatch.setattr(S, "_plan_sale", lambda plan, gifts, **k: sold.append((gifts, k)))
    seen["kw"]["raise_cost"](700, 2)                         # tier 1 gifts, for the fuel
    assert sold == [({"fuel": 700}, {"tiers": (1,), "limit": 2})]


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


def test_fuel_is_bought_for_the_others_once_the_must_gets_are_done(fuse_menu, monkeypatch):
    log = fuse_menu
    log["pool"] = {1: [], 2: [(1, 1, 0)], 3: [(2, 2, 0)], 4: []}     # one tier 3 short

    def buy(have, names, tier_of, **k):
        log["buys"] += 1
        log["pool"][3].append((3, 3, 0))
        return None, []
    monkeypatch.setattr(S, "_buy_fuel", buy)
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


def test_a_floor_plan_hands_the_fuse_session_its_ranked_reserve(monkeypatch):
    four = ["Fragment of Conceit", "Clear Mirror, Calm Water",
            "Fragment of Decay", "Artistic Sense"]
    plan = {"protected": [], "targets": four, "fuse": four[1:3], "must": four[:2],
            "enhance1": [], "enhance2": [four[1], four[3]]}
    seen = {}
    monkeypatch.setattr(S, "_hollow_plan", lambda: plan)
    monkeypatch.setattr(S, "_held_back", lambda t: t)
    monkeypatch.setattr(S, "_fuse_session", lambda *a, **k: seen.update(k))
    monkeypatch.setattr(S, "_enhance_catalog", lambda t: None)
    monkeypatch.setattr(S, "_hollow_sell", lambda *a: None)
    monkeypatch.setattr(p, "MARKET_GIFTS", {})
    monkeypatch.setattr(p, "CUSTOM_ENHANCE_DONE", {})
    for flag in ("SKIP_EGO_BUYING", "SKIP_EGO_FUSION", "SKIP_EGO_ENHANCING"):
        monkeypatch.setattr(p, flag, False, raising=False)
    # Kept back at the floor 3 shop too, where the upties themselves wait.
    for floor, keep in ((4, {four[1]: 0, four[2]: 300}), (3, {four[1]: 0, four[2]: 300})):
        monkeypatch.setattr(p, "LVL", floor)
        monkeypatch.setattr(p, "CUSTOM_MARKET_DONE", False)
        monkeypatch.setattr(p, "CUSTOM_FUSE_DONE", {four[0], four[3]})
        S.custom_market()
        assert seen["keep"] == keep


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


# --- the floor 4 and 5 shops sell for the upties' cost ----------------------

FOUR = ["Fragment of Conceit", "Fragment of Decay",
        "Clear Mirror, Calm Water", "Artistic Sense"]
TWICE = [(n, 2) for n in FOUR[2:]]


@pytest.fixture
def sell_pass(monkeypatch):
    log = {"funds": 150, "sold": [], "order": [], "keep": None, "tiers": None}

    def sell(gifts, **k):
        log["sold"].append(dict(gifts))
        log["tiers"] = k.get("tiers")
        log["keep"] = list(p.MARKET_GIFTS.get("keep_sell") or [])
        log["order"].append("sell")
        log["funds"] = 900
        return True
    monkeypatch.setattr(S, "sell", sell)
    monkeypatch.setattr(S, "balance", lambda: log["funds"])
    monkeypatch.setattr(S, "close_panel", lambda: None)
    monkeypatch.setattr(p, "RUN_SCRIPT", "hollow")
    monkeypatch.setattr(p, "MARKET_GIFTS", {})
    monkeypatch.setattr(p, "CUSTOM_ENHANCE_DONE", {})
    monkeypatch.setattr(p, "LVL", 4)
    import wbcore.market_catalog as MC
    monkeypatch.setattr(MC, "load_market_catalog",
                        lambda: {n: {"tier": 4} for n in FOUR})
    return log


def test_the_unprotected_gifts_are_sold_for_the_owed_upties(sell_pass):
    log = sell_pass
    plan = {"protected": ["Torn Bandolier"] + FOUR, "fuse": [], "must": FOUR[:2],
            "enhance2": FOUR[2:]}
    p.MARKET_GIFTS["keep_sell"] = ["Grand Welcome"]
    S._hollow_sell(plan, set(FOUR), TWICE)
    assert log["sold"] == [{"upties": 600}]
    assert log["keep"] == ["Torn Bandolier"] + FOUR + ["Grand Welcome"]
    assert p.MARKET_GIFTS["keep_sell"] == ["Grand Welcome"]      # the tab's own, back


def test_the_sell_pass_waits_for_floor_4_and_sells_only_tier_1s_before_every_craft(
        sell_pass, monkeypatch):
    log = sell_pass
    plan = {"protected": FOUR, "targets": FOUR, "fuse": [], "must": FOUR[:2],
            "enhance2": FOUR[2:]}
    monkeypatch.setattr(p, "LVL", 3)
    S._hollow_sell(plan, set(FOUR), TWICE)
    monkeypatch.setattr(p, "LVL", 4)
    S._hollow_sell(None, set(FOUR), TWICE)                    # not a Hollow run
    assert log["sold"] == []
    # Artistic Sense still owed: tier 1 gifts go, for Clear Mirror's ++ only.
    S._hollow_sell(plan, set(FOUR[:3]), TWICE)
    assert log["sold"] == [{"upties": 300}] and log["tiers"] == (1,)
    monkeypatch.setattr(p, "LVL", 5)
    log["funds"] = 150
    S._hollow_sell(plan, set(FOUR), TWICE)
    assert log["sold"][-1] == {"upties": 600} and log["tiers"] is None   # anything unprotected


def test_nothing_is_sold_when_the_cost_already_covers_the_upties(sell_pass):
    log = sell_pass
    plan = {"protected": FOUR, "fuse": [], "must": FOUR[:2], "enhance2": FOUR[2:]}
    log["funds"] = 600
    S._hollow_sell(plan, set(FOUR), TWICE)
    log["funds"] = 150
    p.CUSTOM_ENHANCE_DONE.update({n: 2 for n in FOUR[2:]})   # nothing owed
    S._hollow_sell(plan, set(FOUR), TWICE)
    assert log["sold"] == [] and "keep_sell" not in p.MARKET_GIFTS
    p.CUSTOM_ENHANCE_DONE.update({"Artistic Sense": 1})
    log["funds"] = 200
    S._hollow_sell(plan, set(FOUR), TWICE)                    # 200 covers the second level
    assert log["sold"] == []
    log["funds"] = 150
    S._hollow_sell(plan, set(FOUR), TWICE)
    assert log["sold"] == [{"upties": 200}]


def test_the_floor_4_visit_sells_between_the_fuse_session_and_the_upties(sell_pass, monkeypatch):
    log = sell_pass
    plan = {"protected": FOUR, "fuse": [], "must": FOUR[:2], "enhance2": FOUR[2:]}
    monkeypatch.setattr(S, "_hollow_plan", lambda: plan)
    monkeypatch.setattr(S, "_scripted_order", lambda names: list(names or []))
    monkeypatch.setattr(S, "_fuse_session", lambda *a, **k: log["order"].append("fuse"))
    monkeypatch.setattr(S, "_enhance_catalog", lambda t: log["order"].append("enhance"))
    monkeypatch.setattr(p, "CUSTOM_MARKET_DONE", False)
    monkeypatch.setattr(p, "CUSTOM_FUSE_DONE", set(FOUR))
    for flag in ("SKIP_EGO_BUYING", "SKIP_EGO_FUSION", "SKIP_EGO_ENHANCING"):
        monkeypatch.setattr(p, flag, False, raising=False)
    S.custom_market()
    assert log["order"] == ["sell", "enhance"]                # no fuse: all crafted
    assert log["sold"] == [{"upties": 600}]
    monkeypatch.setattr(p, "CUSTOM_MARKET_DONE", False)
    monkeypatch.setattr(p, "SKIP_EGO_ENHANCING", True)
    log["funds"], log["order"], log["sold"] = 150, [], []
    S.custom_market()
    assert log["order"] == [] and log["sold"] == []           # no upties, no selling


def test_a_sell_error_leaves_the_tags_and_the_upties_intact(sell_pass, monkeypatch):
    log = sell_pass
    plan = {"protected": FOUR, "fuse": [], "must": FOUR[:2], "enhance2": FOUR[2:]}

    def boom(gifts, **k):
        log["order"].append("sell")
        raise RuntimeError("Infinite loop exited")
    monkeypatch.setattr(S, "sell", boom)
    monkeypatch.setattr(S, "_hollow_plan", lambda: plan)
    monkeypatch.setattr(S, "_scripted_order", lambda names: list(names or []))
    monkeypatch.setattr(S, "_fuse_session", lambda *a, **k: None)
    monkeypatch.setattr(S, "_enhance_catalog", lambda t: log["order"].append("enhance"))
    monkeypatch.setattr(p, "CUSTOM_MARKET_DONE", False)
    monkeypatch.setattr(p, "CUSTOM_FUSE_DONE", set(FOUR))
    for flag in ("SKIP_EGO_BUYING", "SKIP_EGO_FUSION", "SKIP_EGO_ENHANCING"):
        monkeypatch.setattr(p, flag, False, raising=False)
    S.custom_market()
    assert log["order"] == ["sell", "enhance"]
    assert "keep_sell" not in p.MARKET_GIFTS
