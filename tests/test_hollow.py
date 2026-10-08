# SPDX-License-Identifier: GPL-3.0-or-later
"""The HOLLOW custom run: the run builder, the start summary, the Settings
and Mirror Dungeon controls, and the parts of the battle script that can be
checked against a drawn screen or with its steps stubbed out."""
import os
import sys

import cv2
import numpy as np
import pytest
from PySide6.QtWidgets import QApplication, QWidget

from gui_v2 import copy as C
from gui_v2 import run_config as RC
from gui_v2 import run_summary as RS
from wbcore import bot as B
from wbcore import hollow as H
from wbcore.utils import params as p
from wbcore.utils import utils as U

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TEMPLATES = ("hollow_aim_ok", "hollow_aim_wrong", "hollow_letrou", "hollow_boucher",
             "hollow_retry", "hollow_map_sp45", "hollow_overclock",
             "hollow_overclock_slot", "hollow_ribcage", "hollow_ribcage2",
             "hollow_skull", "hollow_sp45", "hollow_sp_corroded",
             "hollow_start")


def _rows(sections):
    return {label: value for _cap, rows in sections for label, value in rows}


# --- the module itself ---------------------------------------------------

def test_every_template_ships_and_is_in_the_table():
    for name in TEMPLATES:
        path = os.path.join(ROOT, "ImageAssets", "UI", "hollow", name + ".png")
        assert os.path.isfile(path), name
        assert name in U.PTH, name
        assert cv2.imread(U.PTH[name]) is not None, name


def _bright_saturation(name):
    hsv = cv2.cvtColor(cv2.imread(U.PTH[name]), cv2.COLOR_BGR2HSV)
    bright = hsv[..., 2] >= 120
    return float(hsv[..., 1][bright].mean())


def test_the_two_attack_position_cuts_are_the_states_the_document_shows():
    # The correct state is the white arrows, the wrong one the yellow ones;
    # a swapped pair would pass every other test here, so tell them apart
    # by colour.
    assert _bright_saturation("hollow_aim_ok") < 40
    assert _bright_saturation("hollow_aim_wrong") > 100


def test_the_squad_is_faust_alone_except_on_a_miniboss(monkeypatch):
    monkeypatch.setattr(p, "HOLLOW_FALLBACK",
                        ["YISANG", "GREGOR", "FAUST", "NOBODY"])
    assert H.squad_for("Normal") == ["FAUST"]
    assert H.squad_for("Event") == ["FAUST"]
    assert H.squad_for("Focused") == ["FAUST"]
    assert H.squad_for("") == ["FAUST"]
    assert H.squad_for("Miniboss") == ["FAUST", "YISANG", "GREGOR"]
    assert H.squad_for("Risky") == ["FAUST", "YISANG", "GREGOR"]
    monkeypatch.setattr(p, "HOLLOW_FALLBACK", [])
    assert H.squad_for("Miniboss") == ["FAUST"]


def test_a_new_run_starts_clean(monkeypatch):
    monkeypatch.setattr(p, "HOLLOW_AIM_CHECKED", True)
    monkeypatch.setattr(p, "HOLLOW_CORRODED", True)
    monkeypatch.setattr(p, "HOLLOW_NODE", "Miniboss")
    monkeypatch.setattr(p, "SELECTED", ["YISANG", "FAUST"])
    H.begin_run()
    assert not p.HOLLOW_AIM_CHECKED and not p.HOLLOW_CORRODED
    assert p.HOLLOW_NODE == "" and p.SELECTED == ["FAUST"]
    monkeypatch.setattr(p, "HOLLOW_TURN", 4)
    H.begin_battle()
    assert p.HOLLOW_TURN == 0


def test_who_the_shop_heals(monkeypatch):
    monkeypatch.setattr(p, "HOLLOW_HEAL", "GREGOR")
    monkeypatch.setattr(p, "LVL", 1)
    assert H.ROSTER[H._heal_target_index()] == "GREGOR"
    monkeypatch.setattr(p, "LVL", 2)
    assert H._heal_target_index() is None            # the floor 1 heal keeps
    monkeypatch.setattr(p, "LVL", 3)
    assert H._heal_target_index() is None
    monkeypatch.setattr(p, "LVL", 4)
    assert H.ROSTER[H._heal_target_index()] == "FAUST"
    monkeypatch.setattr(p, "LVL", 5)
    assert H.ROSTER[H._heal_target_index()] == "FAUST"
    # Faust is never the floor 1 target, nor is a name the bot lacks.
    monkeypatch.setattr(p, "LVL", 1)
    monkeypatch.setattr(p, "HOLLOW_HEAL", "FAUST")
    assert H.ROSTER[H._heal_target_index()] == "YISANG"
    monkeypatch.setattr(p, "HOLLOW_HEAL", "")
    assert H.ROSTER[H._heal_target_index()] == "YISANG"


def test_faust_down_ends_the_run_but_a_fallback_down_does_not(monkeypatch):
    strip = (261, 1019, 1391, 41)
    monkeypatch.setattr(p, "HOLLOW_FALLBACK", ["YISANG", "GREGOR"])
    assert H.forfeit_threshold([], strip) == 3
    yi_sang = (300, 1025, 20, 30)                  # column 1 of 12
    faust = (420, 1025, 20, 30)                    # column 2
    assert H.forfeit_threshold([yi_sang], strip) == 3
    assert H.forfeit_threshold([yi_sang, faust], strip) == 1
    monkeypatch.setattr(p, "HOLLOW_FALLBACK", [])
    assert H.forfeit_threshold([], strip) == 1


def test_badge_candidates_cover_both_layouts(monkeypatch):
    opened = []
    monkeypatch.setattr(H, "_portrait_xs", lambda: [816, 969])
    monkeypatch.setattr(H, "_gear_slots", lambda: [830, 952])
    monkeypatch.setattr(H, "_menu_open", lambda: False)
    monkeypatch.setattr(H, "open_ego_menu",
                        lambda x: opened.append(x) or ((1, 2, 3, 4) if x == 830 else None))
    slot, box = H.find_faust()                      # no gears from the fight loop
    assert opened == [830]                          # one hold, at the first column
    assert (slot, box) == (830, (1, 2, 3, 4))
    del opened[:]
    monkeypatch.setattr(H, "open_ego_menu", lambda x: opened.append(x) or None)
    assert H.find_faust() == (None, None)           # no menu: no second try
    assert opened == [830]
    del opened[:]
    monkeypatch.setattr(H, "_gear_slots", lambda: [])
    monkeypatch.setattr(H, "_portrait_xs", lambda: [])
    assert H.find_faust() == (None, None)
    assert opened == [H._SOLO_SLOT_X]               # the solo position when alone
    assert H._spaced([902, 910, 840, 845, 969]) == [902, 840, 969]


def test_the_portrait_frame_is_found_as_a_warm_blob(screen):
    canvas = screen.canvas
    cv2.rectangle(canvas, (797, 948), (890, 1050), (20, 110, 240), 5)   # orange hex
    xs = H._portrait_xs()
    assert any(abs(x - 843) <= 8 for x in xs), xs
    # Only the left half is orange (low HP): the centre is still a half hex in.
    canvas[940:1050, 560:1380] = 30
    cv2.rectangle(canvas, (797, 948), (868, 1050), (20, 110, 240), 5)
    assert abs(H._portrait_xs()[0] - 843) <= 8


def test_slot_centres_follow_the_gears():
    assert H._slot_xs() == [H._SOLO_SLOT_X]
    assert H._slot_xs(None, (900, 845)) == [H._SOLO_SLOT_X]
    three = H._slot_xs((100, 845), (100 + 140 + 115 * 3, 845))
    assert three == [230, 352, 474]
    assert H._slot_xs((100, 845), (100 + 140 + 115, 845)) == [230]


# --- reading a drawn screen ----------------------------------------------

class _Display:
    """The backend the locators capture from: a drawn 1920 x 1080 frame."""

    def __init__(self, canvas):
        self.canvas = canvas

    def screenshot(self, region=(0, 0, 1920, 1080)):
        x, y, w, h = [int(v) for v in region]
        return self.canvas[y:y + h, x:x + w].copy()

    def center(self, box):
        x, y, w, h = box
        return (x + w // 2, y + h // 2)

    def getActiveWindowTitle(self):
        return "LimbusCompany"

    def get_position(self):
        return (0, 0)

    def moveTo(self, *a, **k):
        pass

    click = dragTo = moveTo


@pytest.fixture
def screen(monkeypatch):
    """A 1920 x 1080 frame of faint noise that templates can be pasted
    onto; the detection pipeline is rebuilt to capture from it."""
    rng = np.random.default_rng(7)
    canvas = rng.integers(20, 40, size=(1080, 1920, 3), dtype=np.uint8)
    display = _Display(canvas)

    def paste(name, x, y):
        img = cv2.imread(U.PTH[name])
        h, w = img.shape[:2]
        canvas[y:y + h, x:x + w] = img
        return w, h

    U._reset_pipeline_cache()
    paste.canvas = canvas
    monkeypatch.setattr(p, "WINDOW", (0, 0, 1920, 1080))
    monkeypatch.setattr(U, "gui", display)
    monkeypatch.setattr(H, "screenshot", display.screenshot)
    yield paste
    U._reset_pipeline_cache()


def test_enemy_slots_sit_under_the_icons(screen):
    screen("hollow_ribcage", 700, 300)
    screen("hollow_ribcage", 1100, 320)
    slots = H._enemy_slots()
    assert len(slots) == 2
    (x1, y1), (x2, y2) = slots
    dy = H._ICON_TO_SLOT_DY["hollow_ribcage"]
    assert abs(x1 - 715) <= 2 and abs(y1 - (315 + dy)) <= 2
    assert abs(x2 - 1115) <= 2 and abs(y2 - (335 + dy)) <= 2


def test_the_skull_counts_as_an_enemy_slot_too(screen):
    screen("hollow_skull", 900, 400)
    slots = H._enemy_slots()
    assert len(slots) == 1
    assert abs(slots[0][0] - 915) <= 2
    assert abs(slots[0][1] - (415 + H._ICON_TO_SLOT_DY["hollow_skull"])) <= 2


def test_the_slot_frame_under_an_icon_is_preferred_to_the_fixed_distance(screen):
    screen("hollow_ribcage2", 700, 300)             # icon centre (714, 314)
    screen.canvas[360:400, 684:744] = (20, 150, 240)   # a gold frame band
    slots = H._enemy_slots()
    assert len(slots) == 1
    assert abs(slots[0][0] - 714) <= 2
    assert abs(slots[0][1] - 380) <= 4             # the band's centre


def test_warm_ground_or_a_band_running_off_the_window_falls_back(screen):
    dy = H._ICON_TO_SLOT_DY["hollow_ribcage2"]
    screen("hollow_ribcage2", 700, 300)             # icon centre (714, 314)
    screen.canvas[354:394, 684:744] = (20, 150, 240)   # the frame
    screen.canvas[394:480, 684:744] = (60, 110, 130)   # dull olive ground under it
    slots = H._enemy_slots()
    assert abs(slots[0][1] - (393 - H._SLOT_ABOVE_BOTTOM)) <= 2
    screen.canvas[396:480, 684:744] = (20, 150, 240)   # bright warm all the way down
    slots = H._enemy_slots()
    assert slots[0][1] == 314 + dy                 # the measured distance instead


def test_the_slot_number_above_the_frame_does_not_pull_the_point_up(screen):
    screen("hollow_ribcage2", 700, 300)             # icon centre (714, 314)
    screen.canvas[338:352, 704:724] = (20, 150, 240)   # a thin gold number
    screen.canvas[354:394, 684:744] = (20, 150, 240)   # the frame under it
    slots = H._enemy_slots()
    assert len(slots) == 1
    assert abs(slots[0][1] - 374) <= 3             # the frame's own centre


def test_an_empty_field_gives_no_slots(screen):
    assert H._enemy_slots() == []


def test_the_sp_badge_is_read_beside_the_right_portrait(screen):
    dx, dy, _w, _h = H._SP_BADGE_BOX
    screen("hollow_sp_corroded", H._SHOP_PORTRAIT_X[1] + dx,
           H._SHOP_PORTRAIT_Y + dy)
    assert H._sp_badge(1, "hollow_sp_corroded")
    assert not H._sp_badge(0, "hollow_sp_corroded")
    assert not H._sp_badge(1, "hollow_sp45")


def test_the_starting_gift_is_found_by_its_art(screen, monkeypatch):
    monkeypatch.setattr(H.time, "sleep", lambda s: None)
    assert H.starting_gift_row() is None            # nothing on screen
    art = cv2.imread(U.PTH["holder"])
    big = cv2.resize(art, None, fx=1.35, fy=1.35, interpolation=cv2.INTER_CUBIC)
    h, w = big.shape[:2]
    x, y = 1237 - w // 2, 549 - h // 2              # the middle row's icon
    screen.canvas[y:y + h, x:x + w] = big
    assert H.starting_gift_row() == 1
    screen.canvas[y:y + h, x:x + w] = 30
    screen("holder", 1237 - 45, 703 - 45)           # bottom row, unscaled
    assert H.starting_gift_row() == 2


def test_the_starter_keyword_is_poise():
    team = H.starting_team()
    assert team["checks"][0] == "Poise"
    assert team["checks"][2] == (535, 665)


class _Clicks:
    """Stands in for ClickAction: records the point and the verify key."""
    log = []

    def __init__(self, click, ver=None):
        self.click, self.ver = click, ver

    def execute(self, preset, ver=None):
        _Clicks.log.append((self.click, self.ver))
        return True


@pytest.fixture
def archetype(monkeypatch):
    del _Clicks.log[:]
    monkeypatch.setattr(B, "ClickAction", _Clicks)
    monkeypatch.setattr(p, "GIFTS", [{"checks": ["Burn", "smallBurn", (315, 370),
                                                 "reBurn", "bigBurn", 0]}])
    monkeypatch.setattr(p, "BUFF", [0] * 10)
    return _Clicks.log


def _picked(log):
    return [c for c, v in log if v == "selected!"]


def test_the_archetype_screen_keeps_its_old_picks(archetype):
    B._select_archetype_gifts()
    assert archetype[0] == ((315, 370), "gifts!")
    assert _picked(archetype) == [(1239, 395)]
    assert archetype[-1] == ((1624, 882), None)
    del archetype[:]
    p.GIFTS[0]["checks"][5] = 1
    B._select_archetype_gifts()
    assert _picked(archetype) == [(1239, 549)]
    del archetype[:]
    p.BUFF[3] = 1                                    # Star Shower: two gifts
    B._select_archetype_gifts()
    assert _picked(archetype) == [(1239, 395), (1239, 549)]
    del archetype[:]
    p.BUFF[9] = 1                                    # and a third
    B._select_archetype_gifts()
    assert _picked(archetype) == [(1239, 395), (1239, 549), (1239, 703)]
    del archetype[:]
    p.BUFF[3] = 0
    p.GIFTS[0]["checks"][5] = 0
    B._select_archetype_gifts()
    assert _picked(archetype) == [(1239, 395), (1239, 703)]


def test_hollow_clicks_poise_and_the_row_its_gift_is_on(archetype, monkeypatch):
    B._select_archetype_gifts(H.starting_team(), lambda: 2)
    assert archetype[0] == ((535, 665), "gifts!")
    assert _picked(archetype) == [(1239, 703)]
    del archetype[:]
    B._select_archetype_gifts(H.starting_team(), lambda: None)   # art not seen
    assert _picked(archetype) == [(1239, 549)]                   # Poise's usual row
    del archetype[:]
    p.BUFF[3] = 1
    B._select_archetype_gifts(H.starting_team(), lambda: 0)
    assert _picked(archetype) == [(1239, 395), (1239, 549)]


def test_hollow_searches_the_sheets_two_gifts_and_leaves_a_slot(monkeypatch):
    import types
    seen = {}
    monkeypatch.setattr(B, "_select_archetype_gifts",
                        lambda team=None, row=None: seen.update(team=team, row=row))
    monkeypatch.setattr(B, "gift_search", lambda targets: seen.update(targets=targets))
    monkeypatch.setattr(B, "_starter_get_dialog", lambda timer=3.0: False)
    monkeypatch.setattr(B, "wait_while_condition", lambda *a, **k: True)
    monkeypatch.setattr(B.gui, "press", lambda *a, **k: None)
    monkeypatch.setattr(B.time, "sleep", lambda s: None)
    monkeypatch.setattr(p, "RUN_SCRIPT", "hollow")
    monkeypatch.setattr(p, "GIFT_SEARCH", [])
    B.select_starting_gift()
    assert seen["team"] is H.starting_team() and seen["row"] is H.starting_gift_row
    assert seen["targets"] == ["Grand Welcome", "Sharp Needle & Thread"]
    monkeypatch.setattr(p, "GIFT_SEARCH", ["Grand Welcome", "Equalizer",
                                           "Heishou Bolus - Mao"])
    B.select_starting_gift()
    assert seen["targets"] == ["Grand Welcome", "Sharp Needle & Thread", "Equalizer"]
    # The starter gift is never searched for, even when the picker has it.
    monkeypatch.setattr(p, "GIFT_SEARCH", ["Cigarette Holder", "Equalizer"])
    B.select_starting_gift()
    assert seen["targets"] == ["Grand Welcome", "Sharp Needle & Thread", "Equalizer"]


def test_the_gift_names_exist_in_the_catalog_and_agree_across_modules():
    from wbcore import gift_catalog
    for name in H.SEARCH_GIFTS + (H.STARTING_GIFT,):
        assert gift_catalog.gift_info(name), name
    assert tuple(RC.HOLLOW_SEARCH_GIFTS) == H.SEARCH_GIFTS


def test_the_attack_position_is_left_alone_when_right(screen, monkeypatch):
    clicks = []
    monkeypatch.setattr(H, "win_click", lambda *a, **k: clicks.append(a))
    monkeypatch.setattr(H.time, "sleep", lambda s: None)
    monkeypatch.setattr(p, "HOLLOW_AIM_CHECKED", False)
    screen("hollow_aim_ok", 1743, 38)
    H.check_attack_position()
    assert clicks == [] and p.HOLLOW_AIM_CHECKED
    H.check_attack_position()               # once per run
    assert clicks == []


def test_the_wrong_attack_position_is_cycled(screen, monkeypatch):
    clicks = []
    monkeypatch.setattr(H, "win_click", lambda *a, **k: clicks.append(a[0]))
    monkeypatch.setattr(H.time, "sleep", lambda s: None)
    monkeypatch.setattr(p, "HOLLOW_AIM_CHECKED", False)
    screen("hollow_aim_wrong", 1743, 38)           # the yellow arrows
    H.check_attack_position()
    assert clicks == [H._HUD_AIM_CLICK] * 4


def test_the_attack_position_is_cycled_until_it_is_right(screen, monkeypatch):
    clicks = []
    monkeypatch.setattr(H, "win_click", lambda *a, **k: clicks.append(a[0]))
    monkeypatch.setattr(H.time, "sleep", lambda s: None)
    monkeypatch.setattr(p, "HOLLOW_AIM_CHECKED", False)
    H.check_attack_position()
    assert clicks == [H._HUD_AIM_CLICK] * 4


# --- the turns, with their steps stubbed ---------------------------------

@pytest.fixture
def steps(monkeypatch):
    calls = []
    box = (700, 260, 200, 31)
    state = {"faust": (902, box), "start": True, "aim": (800, 400)}
    monkeypatch.setattr(H, "check_attack_position", lambda: None)
    monkeypatch.setattr(H, "find_faust",
                        lambda *a: calls.append("find") or state["faust"])
    monkeypatch.setattr(H, "overclock",
                        lambda b: calls.append("overclock") or True)
    monkeypatch.setattr(H, "slot_card",
                        lambda b, overclocked: calls.append(
                            "slot:%s" % overclocked) or True)
    monkeypatch.setattr(H, "win_rate", lambda: calls.append("winrate") or True)
    monkeypatch.setattr(H, "execute_and_hold",
                        lambda enter=True: calls.append(
                            "execute" if enter else "hold"))
    monkeypatch.setattr(H, "_aim",
                        lambda sx, attempt: calls.append(
                            "aim%d" % attempt) or state["aim"])
    monkeypatch.setattr(H, "_start_shown", lambda: state["start"])
    monkeypatch.setattr(H, "_swap_in_the_ego",
                        lambda gs, ge, sx: calls.append("swap") or False)
    monkeypatch.setattr(H.time, "sleep", lambda s: None)
    monkeypatch.setattr(p, "HOLLOW_TURN", 0)
    monkeypatch.setattr(p, "HOLLOW_CORRODED", False)
    monkeypatch.setattr(p, "SELECTED", ["FAUST"])
    return calls, state


def test_with_the_fallback_squad_fielded_every_turn_is_win_rate(steps, monkeypatch):
    calls, _ = steps
    monkeypatch.setattr(p, "SELECTED", ["FAUST", "YISANG", "GREGOR"])
    H.chain_turn((100, 845), (355, 845))
    assert calls == ["winrate", "execute"]
    del calls[:]
    H.focused_turn()
    assert calls == ["winrate", "execute"]
    del calls[:]
    monkeypatch.setattr(p, "SELECTED", ["FAUST"])          # alone again
    p.HOLLOW_TURN = 0
    H.chain_turn((100, 845), (355, 845))
    assert calls == ["find", "overclock", "slot:True", "winrate", "swap",
                     "execute"]


def test_a_chain_battle_overclocks_on_turn_one_only(steps):
    calls, _ = steps
    H.chain_turn((100, 845), (355, 845))
    assert calls == ["find", "overclock", "slot:True", "winrate", "swap",
                     "execute"]
    del calls[:]
    H.chain_turn((100, 845), (355, 845))
    assert calls == ["find", "slot:False", "winrate", "swap", "execute"]
    assert p.HOLLOW_TURN == 2


def test_the_floor_1_boss_chains_the_ego_by_drag(steps, monkeypatch):
    calls, state = steps
    monkeypatch.setattr(p, "LVL", 1)
    monkeypatch.setattr(p, "HOLLOW_NODE", "Boss")
    monkeypatch.setattr(H, "_drag_in_the_ego",
                        lambda gs, ge: calls.append("drag") or state.get("dragged", True))
    H.chain_turn((100, 845), (355, 845))
    assert calls == ["find", "overclock", "slot:True", "drag", "hold"]
    del calls[:]
    state["dragged"] = False                                 # the drag missed
    H.chain_turn((100, 845), (355, 845))
    assert calls == ["find", "slot:False", "drag", "winrate", "swap", "execute"]
    del calls[:]
    monkeypatch.setattr(p, "HOLLOW_NODE", "")                 # resumed mid-fight
    H.chain_turn((100, 845), (355, 845))
    assert calls == ["find", "slot:False", "winrate", "swap", "execute"]
    del calls[:]
    monkeypatch.setattr(p, "HOLLOW_NODE", "Boss")
    monkeypatch.setattr(p, "LVL", 2)                          # floor 1 only
    H.chain_turn((100, 845), (355, 845))
    assert calls == ["find", "slot:False", "winrate", "swap", "execute"]
    del calls[:]
    monkeypatch.setattr(p, "LVL", 1)
    monkeypatch.setattr(p, "HOLLOW_CORRODED", True)           # corroded: win rate
    monkeypatch.setattr(p, "HOLLOW_CORRODED_FLOOR", 1)
    H.chain_turn((100, 845), (355, 845))
    assert calls == ["winrate", "swap", "execute"]
    del calls[:]
    monkeypatch.setattr(p, "HOLLOW_CORRODED", False)
    H.chain_turn(None, None)                                  # no gears: no drag
    assert calls == ["find", "slot:False", "winrate", "swap", "execute"]


def test_the_drag_takes_every_column_at_the_bottom_card(monkeypatch):
    import types
    import wbcore.battle as BT
    seen = {}
    monkeypatch.setattr(BT, "chain", lambda gs, ge, band, **k: seen.update(k))
    monkeypatch.setattr(H, "screenshot", lambda region=None: None)
    shown = {"winrate": False}
    monkeypatch.setattr(H, "now", types.SimpleNamespace(
        button=lambda name, *a, **k: shown.get(name, False)))
    monkeypatch.setattr(H.time, "sleep", lambda s: None)
    assert H._drag_in_the_ego((100, 845), (585, 845)) is True      # three columns
    assert seen["execute"] is True
    assert seen["force_offsets"] == {0: 190, 1: 190, 2: 190}
    shown["winrate"] = True                                        # still there
    assert H._drag_in_the_ego((100, 845), (355, 845)) is False
    assert seen["force_offsets"] == {0: 190}


def test_a_corroded_faust_skips_the_menu_on_her_floor_only(steps, monkeypatch):
    calls, _ = steps
    monkeypatch.setattr(p, "LVL", 2)
    p.HOLLOW_CORRODED = True
    monkeypatch.setattr(p, "HOLLOW_CORRODED_FLOOR", 2)
    H.chain_turn((100, 845), (355, 845))
    assert calls == ["winrate", "swap", "execute"]
    # SP resets with the floor: the overclock loop starts over.
    del calls[:]
    monkeypatch.setattr(p, "LVL", 3)
    p.HOLLOW_TURN = 0
    H.chain_turn((100, 845), (355, 845))
    assert calls == ["find", "overclock", "slot:True", "winrate", "swap",
                     "execute"]


def test_two_upties_wait_for_the_floor_3_shop(monkeypatch):
    from wbcore import shop as S
    monkeypatch.setattr(p, "RUN_SCRIPT", "hollow")
    plan = [("Clear Mirror, Calm Water", 2), ("Artistic Sense", 2),
            ("Fragment of Decay", 1)]
    monkeypatch.setattr(p, "LVL", 1)
    assert S._held_back(plan) == [("Fragment of Decay", 1)]
    monkeypatch.setattr(p, "LVL", 2)
    assert S._held_back(plan) == [("Fragment of Decay", 1)]
    monkeypatch.setattr(p, "LVL", 3)
    assert S._held_back(plan) == plan
    monkeypatch.setattr(p, "RUN_SCRIPT", "")
    monkeypatch.setattr(p, "LVL", 1)
    assert S._held_back(plan) == plan                 # other runs untouched


def test_the_upties_are_ready_once_all_four_are_crafted_or_on_floor_4():
    four = ("Fragment of Conceit", "Fragment of Decay",
            "Clear Mirror, Calm Water", "Artistic Sense")
    assert H.enhance_ready(set(four), floor=3) is True
    assert H.enhance_ready(set(four[:3]), floor=3) is False
    assert H.enhance_ready(set(), floor=4) is True
    assert H.enhance_ready(set(), floor=5) is True
    assert H.enhance_ready(set(four), floor=2) is True        # the floor 3 gate is elsewhere


def test_the_market_plan_follows_the_owners_summary(monkeypatch):
    conceit, decay = "Fragment of Conceit", "Fragment of Decay"
    mirror, sense = "Clear Mirror, Calm Water", "Artistic Sense"
    thread, welcome, holder = "Sharp Needle & Thread", "Grand Welcome", "Cigarette Holder"
    f1 = H.market_plan(1)
    assert set(f1["protected"]) == {conceit, decay, welcome, holder, thread, mirror, sense}
    assert f1["fuse"] == [conceit, decay, mirror, sense] and f1["enhance2"] == []
    assert f1["must"] == [conceit, decay]
    f2 = H.market_plan(2)
    assert set(f2["protected"]) == {conceit, decay, holder, thread}
    assert f2["fuse"] == [conceit, decay, mirror, sense] and f2["enhance2"] == []
    f3 = H.market_plan(3)
    assert set(f3["protected"]) == {conceit, decay, holder, thread, mirror, sense}
    for floor in (1, 2, 3, 4, 5):
        assert holder in H.market_plan(floor)["protected"]   # every floor
    assert f3["fuse"] == [conceit, decay, mirror, sense]      # still owed
    assert f3["enhance2"] == [mirror, sense]
    assert H.market_plan(3, crafted={conceit})["fuse"] == [decay, mirror, sense]
    assert H.market_plan(4, crafted={conceit, decay})["fuse"] == [mirror, sense]
    assert H.market_plan(4, crafted={conceit, decay})["must"] == [conceit, decay]
    assert H.market_plan(5, crafted={conceit}) == H.market_plan(3, crafted={conceit})
    from wbcore import shop as S
    monkeypatch.setattr(p, "RUN_SCRIPT", "saikai_ryoshu")
    assert S._hollow_plan() is None
    monkeypatch.setattr(p, "RUN_SCRIPT", "hollow")
    monkeypatch.setattr(p, "LVL", 2)
    monkeypatch.setattr(p, "CUSTOM_FUSE_DONE", set())
    assert S._hollow_plan()["fuse"] == [conceit, decay, mirror, sense]


def test_the_market_works_poise_gifts_first(monkeypatch):
    from wbcore import shop as S
    plan = ["Artistic Sense", "Clear Mirror, Calm Water", "Fragment of Conceit",
            "Fragment of Decay"]
    kw = {"Artistic Sense": "sinking", "Clear Mirror, Calm Water": "poise",
          "Fragment of Conceit": "poise", "Fragment of Decay": "sinking"}
    assert H.market_order(plan, kw.get) == [
        "Clear Mirror, Calm Water", "Fragment of Conceit",
        "Artistic Sense", "Fragment of Decay"]
    assert H.market_order([], kw.get) == []
    monkeypatch.setattr(p, "RUN_SCRIPT", "hollow")
    assert S._scripted_order(plan) == H.market_order(plan, kw.get)   # the catalog agrees
    assert S._scripted_order(None) == []
    monkeypatch.setattr(p, "RUN_SCRIPT", "saikai_ryoshu")
    assert S._scripted_order(plan) == plan                 # other runs untouched


def test_a_card_that_only_highlights_is_clicked_again(monkeypatch):
    import types
    clicks, menu_open = [], [True, False]              # closes on the 2nd look
    monkeypatch.setattr(H, "win_click", lambda x, y, **k: clicks.append((x, y)))
    monkeypatch.setattr(H, "loc", types.SimpleNamespace(
        button=lambda name, *a, **k: not menu_open.pop(0) if menu_open else True))
    closed = []
    monkeypatch.setattr(H, "_close_menu", lambda: closed.append(True))
    monkeypatch.setattr(H.time, "sleep", lambda s: None)
    assert H.slot_card((1107, 502, 200, 31), overclocked=False)
    assert clicks == [(1207, 392)] * 4 and not closed    # two double clicks
    # Never slots: the menu is closed and the caller told.
    del clicks[:]
    monkeypatch.setattr(H, "loc", types.SimpleNamespace(
        button=lambda name, *a, **k: False))
    assert not H.slot_card((1107, 502, 200, 31), overclocked=False)
    assert len(clicks) == 4 and closed == [True]
    # After an overclock hold one click per try is enough.
    del clicks[:]
    menu_open[:] = [False]
    monkeypatch.setattr(H, "loc", types.SimpleNamespace(
        button=lambda name, *a, **k: True))
    monkeypatch.setattr(H, "LocateRGB", types.SimpleNamespace(
        locate=lambda *a, **k: (1, 2, 3, 4)))
    assert H.slot_card((1107, 502, 200, 31), overclocked=True)
    assert clicks == [(1207, 392)]


def test_the_heal_is_judged_by_the_cost_drop(monkeypatch, caplog):
    import logging
    from wbcore import shop as S
    costs = iter([300, 200])
    monkeypatch.setattr(S, "balance", lambda: next(costs))
    monkeypatch.setattr(H, "ClickAction", lambda *a, **k: type(
        "A", (), {"execute": lambda self, preset: True})())
    monkeypatch.setattr(H, "win_click", lambda *a, **k: None)
    monkeypatch.setattr(H, "wait_while_condition", lambda *a, **k: False)
    monkeypatch.setattr(H, "connection", lambda: None)
    monkeypatch.setattr(H, "_at_shop", lambda: True)
    monkeypatch.setattr(H, "_sp_badge", lambda *a, **k: False)
    monkeypatch.setattr(H, "_heal_row_lit", lambda i: True)
    monkeypatch.setattr(H, "_heal_button", lambda name: True)
    monkeypatch.setattr(H.time, "sleep", lambda s: None)
    monkeypatch.setattr(p, "LVL", 4)
    monkeypatch.setattr(p, "HOLLOW_CORRODED", True)
    with caplog.at_level(logging.INFO):
        assert H.shop_visit()
    text = caplog.text
    assert "went through (cost 300 to 200)" in text
    # Her 45 SP badge is proof enough: no second cost read at all.
    caplog.clear()
    monkeypatch.setattr(H, "_sp_badge", lambda i, name, conf=0.8: name == "hollow_sp45")
    reads = []
    monkeypatch.setattr(S, "balance", lambda: reads.append(1) or 300)
    with caplog.at_level(logging.INFO):
        assert H.shop_visit()
    assert reads == [1] and "already reads 45 SP; no heal needed" in caplog.text
    assert "may not have" not in caplog.text
    monkeypatch.setattr(H, "_sp_badge", lambda *a, **k: False)
    assert "did not go through" not in text and "may not have" not in text
    assert p.HOLLOW_CORRODED is False               # Faust was the target
    assert p.HOLLOW_CORRODED_FLOOR == 4
    caplog.clear()
    costs = iter([300, 300])
    monkeypatch.setattr(S, "balance", lambda: next(costs))
    with caplog.at_level(logging.INFO):
        H.shop_visit()
    assert "may not have gone through (cost 300, was 300)" in caplog.text


def _heal_screen(monkeypatch):
    from wbcore import shop as S
    clicks, left = [], []
    monkeypatch.setattr(S, "balance", lambda: 300)
    monkeypatch.setattr(H, "ClickAction", lambda *a, **k: type(
        "A", (), {"execute": lambda self, preset: True})())
    monkeypatch.setattr(H, "win_click", lambda *a, **k: clicks.append(a[:2]))
    monkeypatch.setattr(H, "wait_while_condition", lambda *a, **k: False)
    monkeypatch.setattr(H, "connection", lambda: None)
    monkeypatch.setattr(H, "_sp_badge", lambda *a, **k: False)
    monkeypatch.setattr(H, "_leave_heal_menu", lambda: left.append(True) or True)
    monkeypatch.setattr(H.time, "sleep", lambda s: None)
    monkeypatch.setattr(p, "LVL", 4)
    monkeypatch.setattr(p, "HOLLOW_CORRODED", True)
    return clicks, left


def test_45_sp_on_the_type_list_means_return_not_the_option(monkeypatch, caplog):
    clicks, left = _heal_screen(monkeypatch)
    reads = []
    # The corroded read, then the shop screen misses the 45 badge; the heal
    # screen's type list reads it.
    monkeypatch.setattr(H, "_sp_badge", lambda i, name, conf=0.8: (
        reads.append(name) or (name == "hollow_sp45" and len(reads) > 2)))
    with caplog.at_level("INFO"):
        assert H.shop_visit()
    assert "reads 45 SP on the heal screen" in caplog.text
    assert clicks == [] and left == [True]            # the option was never clicked
    assert p.HOLLOW_CORRODED is False


def test_a_greyed_sinner_is_not_picked_on_the_heal_screen(monkeypatch, caplog):
    clicks, left = _heal_screen(monkeypatch)
    monkeypatch.setattr(H, "_heal_row_lit", lambda i: False)
    with caplog.at_level("WARNING"):
        assert H.shop_visit()
    assert "greyed out on the heal screen" in caplog.text
    assert clicks == [H._SHOP_HEAL_SINGLE]            # the option, then out
    assert left == [True] and p.HOLLOW_CORRODED is False


def test_no_select_means_no_heal_and_a_way_out(monkeypatch, caplog):
    clicks, left = _heal_screen(monkeypatch)
    monkeypatch.setattr(H, "_heal_row_lit", lambda i: True)
    monkeypatch.setattr(H, "_heal_button", lambda name: None)
    with caplog.at_level("WARNING"):
        assert H.shop_visit()
    assert "Select did not come up" in caplog.text
    faust = (H._SHOP_PORTRAIT_X[1], H._SHOP_PORTRAIT_Y)
    assert clicks == [H._SHOP_HEAL_SINGLE, faust] and left == [True]


def test_the_heal_screen_is_left_by_return_leave_or_a_last_resort_heal(monkeypatch, caplog):
    import types
    clicks, presses, returns = [], [], []
    state = {"shop": iter([False, True])}
    monkeypatch.setattr(H, "_at_shop", lambda: next(state["shop"], True))
    monkeypatch.setattr(H, "now", types.SimpleNamespace(button=lambda *a, **k: False))
    monkeypatch.setattr(H, "now_click", types.SimpleNamespace(
        button=lambda name, *a, **k: returns.append(name) or True))
    monkeypatch.setattr(H, "_heal_button", lambda name: None)
    monkeypatch.setattr(H, "win_click", lambda *a, **k: clicks.append(a[:2]))
    monkeypatch.setattr(H.gui, "press", lambda key: presses.append(key))
    monkeypatch.setattr(H, "wait_while_condition", lambda *a, **k: False)
    monkeypatch.setattr(H.time, "sleep", lambda s: None)
    assert H._leave_heal_menu() is True                 # the type list: Return
    assert returns == ["return"] and clicks == [] and presses == []
    # After a heal: Leave at the Select spot.
    state["shop"] = iter([False, True])
    monkeypatch.setattr(H, "_heal_button", lambda name: name == "hollow_heal_leave")
    assert H._leave_heal_menu() is True
    assert clicks == [H._SHOP_CONFIRM]
    # The sinner stage with nothing picked: heal the first lit sinner to get out.
    del clicks[:]
    state["shop"] = iter([False, False, False, True])
    monkeypatch.setattr(H, "now_click", types.SimpleNamespace(button=lambda *a, **k: False))
    monkeypatch.setattr(H, "_heal_row_lit", lambda i: i >= 2)
    monkeypatch.setattr(H, "_heal_button", lambda name: (
        (name == "hollow_heal_select" and len(clicks) == 1)
        or (name == "hollow_heal_leave" and len(clicks) == 2)))
    with caplog.at_level("WARNING"):
        assert H._leave_heal_menu() is True
    assert clicks == [(H._SHOP_PORTRAIT_X[2], H._SHOP_PORTRAIT_Y),
                      H._SHOP_CONFIRM, H._SHOP_CONFIRM]
    assert "no way back" in caplog.text


def test_the_lit_frame_tells_a_healable_sinner_from_a_greyed_one(screen):
    import cv2 as _cv2
    canvas = screen.canvas
    for i, sat in ((1, 20), (2, 190)):
        x, y = H._SHOP_PORTRAIT_X[i], H._SHOP_PORTRAIT_Y
        bgr = _cv2.cvtColor(np.uint8([[[12, sat, 200]]]), _cv2.COLOR_HSV2BGR)[0, 0]
        _cv2.circle(canvas, (x, y), 44, tuple(int(c) for c in bgr), 10)
    assert H._heal_row_lit(1) is False
    assert H._heal_row_lit(2) is True


def test_no_menu_means_the_ego_is_already_chosen(steps):
    calls, state = steps
    state["faust"] = (None, None)
    H.chain_turn((100, 845), (355, 845))
    assert calls == ["find", "winrate", "swap", "execute"]


def test_a_chain_turn_runs_without_gears_on_the_early_floors(steps):
    calls, _ = steps
    H.chain_turn(None, None)
    assert calls == ["find", "overclock", "slot:True", "winrate", "swap",
                     "execute"]
    assert H._swap_in_the_ego(None, None, 902) is False


def test_a_skill_3_on_top_gets_one_click_on_the_bottom_card(monkeypatch):
    from wbcore import battle as BT
    reads = {"cols": [{0}, set()]}
    monkeypatch.setattr(BT, "skill3_columns",
                        lambda band, gs, n: reads["cols"].pop(0) if reads["cols"] else set())
    monkeypatch.setattr(H, "screenshot", lambda region=None: ("frame", region))
    clicks = []
    monkeypatch.setattr(H, "win_click", lambda x, y, **k: clicks.append((x, y)))
    monkeypatch.setattr(H.time, "sleep", lambda s: None)
    assert H._swap_in_the_ego((761, 853), (1042, 838), 902)
    assert clicks == [(902, 853 - 46 + BT._SAIKAI_S3_BOTTOM_OFF)]
    # No Skill 3 chained: nothing is touched.
    del clicks[:]
    reads["cols"] = [set()]
    assert not H._swap_in_the_ego((761, 853), (1042, 838), 902)
    assert clicks == []
    # Gears too close to read: nothing is touched either.
    assert not H._swap_in_the_ego((100, 850), (300, 850), 902)
    assert clicks == []


def test_execute_and_hold_presses_enter_again_when_nothing_started(monkeypatch):
    import types
    keys, seen = [], {"winrate": [True, False]}
    gui = types.SimpleNamespace(
        press=lambda key, *a: keys.append(key), mouseDown=lambda: keys.append("down"),
        mouseUp=lambda: keys.append("up"), getActiveWindowTitle=lambda: p.LIMBUS_NAME)
    monkeypatch.setattr(H, "gui", gui)
    monkeypatch.setattr(H, "now", types.SimpleNamespace(
        button=lambda name: seen["winrate"].pop(0) if name == "winrate" and seen["winrate"] else False))
    monkeypatch.setattr(H, "win_moveTo", lambda *a, **k: None)
    monkeypatch.setattr(H, "_turn_over", lambda: True)
    monkeypatch.setattr(H.time, "sleep", lambda s: None)
    H.execute_and_hold(enter=False)
    assert keys == ["enter", "down", "up"]            # nothing started: one Enter
    del keys[:]
    seen["winrate"] = [False]
    H.execute_and_hold(enter=False)
    assert keys == ["down", "up"]                     # the drag had started it


def test_the_boss_row_is_the_largest_group_at_one_height():
    slots = [(646, 622), (723, 397), (840, 381), (926, 339), (1011, 340),
             (1096, 381), (1167, 624), (1181, 381), (1269, 398)]
    row = H._boss_row(slots)
    assert (646, 622) not in row and (1167, 624) not in row
    assert row[0] == (723, 397) and len(row) == 7
    assert H._boss_row([]) == []
    assert H._boss_row([(1142, 450), (1582, 450)]) == [(1142, 450), (1582, 450)]


def test_the_body_slot_is_the_middle_of_the_row_not_a_candle_at_its_end():
    # The owner's capture: the upper candles' slots at 1160 and 1625 share
    # the Skin Prophet's row of four (1285 to 1500).
    row = [(1160, 245), (1285, 228), (1355, 228), (1425, 228), (1500, 228), (1625, 245)]
    assert H._body_slot(row) in [(1355, 228), (1425, 228)]
    assert H._body_slot([(900, 400), (990, 400), (1080, 400)]) == (990, 400)
    assert H._body_slot([(917, 362)]) == (917, 362)
    assert H._body_slot([]) is None


def test_slots_are_taken_once_two_ticks_agree(monkeypatch):
    readings = [[], [(900, 500)], [(920, 520)], [(921, 522), (1000, 520)],
                [(922, 523), (1001, 521)], [(5, 5)]]
    monkeypatch.setattr(H, "_enemy_slots", lambda: readings.pop(0) if readings else [])
    monkeypatch.setattr(H.time, "sleep", lambda s: None)
    assert H._stable_slots() == [(922, 523), (1001, 521)]
    assert readings == [[(5, 5)]]                    # stopped as soon as it held


def test_a_floor_4_boss_still_up_at_turn_3_is_retried(steps, monkeypatch):
    calls, _ = steps
    retried = []
    monkeypatch.setattr(H, "_retry_stage", lambda: retried.append(True) or True)
    monkeypatch.setattr(p, "LVL", 4)
    monkeypatch.setattr(p, "HOLLOW_NODE", "Boss")
    monkeypatch.setattr(p, "HOLLOW_RETRIES", 0)
    p.HOLLOW_TURN = 2
    H.focused_turn()                                 # this is turn 3
    assert retried == [True] and calls == []
    monkeypatch.setattr(p, "HOLLOW_NODE", "Normal")  # not the boss: no retry
    p.HOLLOW_TURN = 2
    H.focused_turn()
    assert retried == [True] and calls == ["winrate", "execute"]
    monkeypatch.setattr(p, "HOLLOW_RETRIES", 3)      # already retried thrice
    monkeypatch.setattr(p, "HOLLOW_NODE", "Boss")
    p.HOLLOW_TURN = 2
    H.focused_turn()
    assert retried == [True]


def test_the_squad_aims_every_skill_at_the_body(monkeypatch):
    clicks, calls = [], []
    monkeypatch.setattr(H, "check_attack_position", lambda: None)
    monkeypatch.setattr(H, "win_click", lambda x, y, **k: clicks.append((x, y)))
    scans = []
    monkeypatch.setattr(H, "_stable_slots",
                        lambda timeout=4.0: scans.append(timeout) or [(900, 400), (990, 400), (1080, 400)])
    monkeypatch.setattr(H, "_start_shown", lambda: True)
    monkeypatch.setattr(H, "win_rate", lambda: calls.append("winrate"))
    monkeypatch.setattr(H, "execute_and_hold", lambda enter=True: calls.append("execute"))
    monkeypatch.setattr(H.time, "sleep", lambda s: None)
    monkeypatch.setattr(p, "SELECTED", ["FAUST", "YISANG", "GREGOR"])
    monkeypatch.setattr(p, "HOLLOW_TURN", 0)
    H.squad_focused_turn()
    cards = [c for c in clicks if c[1] == H._SQUAD_CARD_Y]
    assert [c[0] for c in cards] == [x + H._X_BIAS for x in H._SQUAD_SLOT_XS[:3]]
    assert clicks.count((990, 400)) == 3             # all three on the middle part
    assert scans == [4.0]                            # one scan: the camera moves once
    assert calls == ["execute"]


def test_the_map_badge_decides_the_next_fight(screen, monkeypatch):
    monkeypatch.setattr(p, "LVL", 3)
    monkeypatch.setattr(p, "HOLLOW_CORRODED", True)
    assert H.read_map_sp() is False
    assert p.HOLLOW_CORRODED is False and p.HOLLOW_CORRODED_FLOOR == 3
    screen("hollow_map_sp45", 440, 1016)
    assert H.read_map_sp() is True
    assert p.HOLLOW_CORRODED is True


def test_a_focused_turn_one_aims_by_hand(steps):
    calls, _ = steps
    H.focused_turn()
    assert calls == ["find", "slot:False", "aim0", "execute"]


def test_a_focused_turn_one_retries_then_falls_back_to_win_rate(steps):
    calls, state = steps
    state["start"] = False
    H.focused_turn()
    assert calls == ["find", "slot:False", "aim0", "aim1", "aim2",
                     "winrate", "execute"]
    del calls[:]
    p.HOLLOW_TURN = 0
    state["start"] = True
    state["aim"] = None
    H.focused_turn()
    assert calls == ["find", "slot:False", "aim0", "aim1", "aim2",
                     "winrate", "execute"]


def test_a_corroded_faust_still_aims_on_the_focused_first_turn(steps):
    calls, state = steps
    state["faust"] = (None, None)                  # no menu: E.G.O already in
    H.focused_turn()
    assert calls == ["find", "aim0", "execute"]
    del calls[:]
    H.focused_turn()                                # turn 2: win rate as before
    assert calls == ["find", "winrate", "execute"]


def test_later_focused_turns_use_win_rate(steps):
    calls, _ = steps
    p.HOLLOW_TURN = 1
    H.focused_turn()
    assert calls == ["find", "slot:False", "winrate", "execute"]
    del calls[:]
    H.focused_turn()
    assert calls == ["winrate", "execute"]
    assert p.HOLLOW_TURN == 3


# --- a held mouse button survives no pause ---------------------------------

@pytest.mark.skipif(sys.platform != "win32", reason="the Windows backend")
def test_a_pause_releases_the_held_button(monkeypatch):
    from wbcore.utils import os_windows_backend as W

    class Bridge:
        def __init__(self):
            self.log = []

        def mouse_press(self, button="left"):
            self.log.append("down:" + button)

        def mouse_release(self, button="left"):
            self.log.append("up:" + button)

    bridge = Bridge()
    title = {"name": p.LIMBUS_NAME}
    monkeypatch.setattr(W, "_bridge", bridge)
    monkeypatch.setattr(W, "_get_bridge", lambda: bridge)
    monkeypatch.setattr(W, "getActiveWindowTitle", lambda: title["name"])
    monkeypatch.setattr(W, "restore_mouse_settings", lambda: None)
    monkeypatch.setattr(W, "_ensure_mouse_settings", lambda: None)
    monkeypatch.setattr(W, "_human_delay", lambda *a, **k: None)
    monkeypatch.setattr(p, "stop_event", None, raising=False)
    W._held_buttons.clear()

    W.mouseDown()
    title["name"] = "Some other window"            # focus lost mid-hold
    with pytest.raises(W.PauseException):
        W.mouseUp()
    assert bridge.log == ["down:left", "up:left"]
    assert not W._held_buttons

    title["name"] = p.LIMBUS_NAME
    W.mouseDown()
    title["name"] = "Some other window"
    with pytest.raises(W.PauseException):
        W._fail_safe_check()                        # any later call lets go
    assert bridge.log[-1] == "up:left"
    assert not W._held_buttons


# --- the run builder -----------------------------------------------------

_MD = {"custom_run": True, "custom_strategy": RC.HOLLOW_LABEL, "run_count": 3,
       "hollow_heal": "Gregor", "hollow_order": ["Faust", "Yi Sang", "Gregor"],
       "hollow_status": "Poise"}


def test_the_builder_pins_the_hollow_run():
    count, teams, settings, hard = RC.build_md_run(dict(_MD), {}, {})
    assert (count, hard) == (3, True)
    assert settings["run_script"] == "hollow"
    assert settings["hard_from_floor"] == 5
    assert settings["winrate"] is False
    assert settings["infinity"] is False
    assert settings["swap_max_energy"] is False
    assert settings["skip_ego_check"] is False
    assert settings["default_market_workflow"] is False
    assert settings["pack_search"] is True
    assert settings["pack_search_floors"] == {
        1: "Flat-broke gamblers", 2: "Hell's Chicken",
        3: "Emotional Seduction", 4: "Hatred and Despair", 5: "Line 2"}
    assert settings["buff"] == [1, 0, 1, 0, 0, 0, 0, 0, 0, 0]
    # The grace panel defaults to four graces on; the sheet's pair is pinned.
    md = dict(_MD, grace={"Star of the Beginning": 1, "Cumulating Starcloud": 1,
                          "Interstellar Travel": 1, "Star Shower": 1})
    assert RC.build_md_run(md, {}, {})[2]["buff"] == [1, 0, 1, 0, 0, 0, 0, 0, 0, 0]
    assert settings["hollow_heal"] == "GREGOR"
    assert settings["hollow_fallback"] == ["YISANG", "GREGOR"]
    team = teams[0]
    assert team["sinners"] == [1]
    assert team["affinity"] == [RC._STATUS_INDEX["Poise"]]
    assert team["priority"][0] == ["FlatbrokeGamblers", "HellsChicken",
                                   "EmotionalSeduction", "EmotionalCraving",
                                   "HatredandDespair", "Line2"]
    assert team["priority"][1] == {"FlatbrokeGamblers": 1, "HellsChicken": 2,
                                   "EmotionalSeduction": 3, "EmotionalCraving": 3,
                                   "HatredandDespair": 4, "Line2": 5}


def test_the_builder_never_heals_faust_and_keeps_the_users_keyword():
    md = dict(_MD, hollow_heal="Faust", hollow_status="Bleed",
              hollow_order=["Faust"])
    _c, teams, settings, _h = RC.build_md_run(md, {}, {})
    assert settings["hollow_heal"] == "YISANG"
    assert settings["hollow_fallback"] == []
    assert teams[0]["affinity"] == [RC._STATUS_INDEX["Bleed"]]
    md = dict(_MD, hollow_heal="Nobody", hollow_status="Nothing")
    _c, teams, settings, _h = RC.build_md_run(md, {}, {})
    assert settings["hollow_heal"] == "YISANG"
    assert teams[0]["affinity"] == [RC._STATUS_INDEX["Poise"]]


def test_hollow_is_only_built_when_chosen(monkeypatch):
    built = []
    monkeypatch.setattr(RC, "_build_hollow_run",
                        lambda md: built.append(md) or (1, {}, {}, True))
    for md in (dict(_MD, custom_run=False),
               dict(_MD, custom_strategy="F3 Hard")):
        try:
            RC.build_md_run(md, {}, {})
        except ValueError:
            pass                        # the plain builder wants real teams
    assert built == []
    RC.build_md_run(dict(_MD), {}, {})
    assert len(built) == 1


# --- the words -------------------------------------------------------------

def test_the_start_summary_describes_the_run():
    md = dict(_MD, behaviour={"winrate": True, "swap_max_energy": True,
                              "skip_ego_check": True, "bonus": True,
                              "pack_search": False},
              pack_refreshes=2)
    rows = _rows(RS.md_summary(md))
    assert rows["Difficulty"] == "Normal, then Hard from floor 5"
    assert rows["Graces"] == "Star of the Beginning, Interstellar Travel"
    assert rows["Squad"] == "Faust alone"
    assert rows["Fallback (miniboss)"] == "Yi Sang, Gregor"      # no Faust
    assert rows["Shop heals"] == "Gregor on floor 1, Faust on floors 4 and 5"
    assert rows["Team keyword"] == "Poise"
    assert rows["Market"].startswith("Heal, then the floor plan")
    assert rows["Pack search"] == "On, one pack per floor, 2 refreshes"
    assert rows["Packs"] == ("Flat-broke gamblers, Hell's Chicken, Emotional "
                             "Seduction, Hatred and Despair, Line 2")
    assert rows["Switched on"] == "Claim bonus"      # the overridden three hidden
    rows = _rows(RS.md_summary({"custom_run": True,
                                "custom_strategy": RC.HOLLOW_LABEL}))
    assert rows["Fallback (miniboss)"] == "None"
    assert rows["Shop heals"].startswith("Yi Sang on floor 1")


def test_the_custom_run_hint_mentions_hollow():
    assert "Hollow" in C.MD_CUSTOM_RUN_HINT
    assert "Le Trou" in C.MD_CUSTOM_RUN_HINT
    assert "IDs. Hollow" in C.MD_CUSTOM_RUN_HINT      # the sentences are spaced


# --- the controls ----------------------------------------------------------

def _quiet(setattr_):
    import importlib
    import pkgutil
    import gui_v2
    for m in pkgutil.iter_modules(gui_v2.__path__):
        if m.name.endswith("_test"):
            continue
        mod = importlib.import_module("gui_v2." + m.name)
        for name in ("save_settings", "save_section"):
            if hasattr(mod, name):
                setattr_(mod, name, lambda *a, **k: None)


@pytest.fixture(scope="module")
def ui():
    from tests.conftest import destroy
    mp = pytest.MonkeyPatch()
    _quiet(mp.setattr)
    QApplication.instance() or QApplication([])
    from gui_v2.main_ui import MainUI
    host = QWidget()
    host.resize(1280, 860)
    main = MainUI(host)
    main.setGeometry(0, 0, 1280, 860)
    yield main
    destroy(main, host)
    mp.undo()


def test_settings_shows_the_heal_pick_for_hollow_only(ui):
    page = ui.page("settings")
    assert "Hollow" in page._stk_seg._buttons
    assert page._stk_heal_row.isHidden()
    assert not page._stk_exclude_box.isHidden()
    page._stk_seg._buttons["Hollow"].click()
    assert page._stk_run == "Hollow"
    assert not page._stk_order._chips["Faust"].isEnabled()
    assert not page._stk_heal_row.isHidden()
    assert page._stk_exclude_box.isHidden()
    assert not hasattr(page, "_stk_order_hint")
    assert page._stk_order_label.text() == "Fallback sinners"
    names = [page._stk_heal.itemText(i) for i in range(page._stk_heal.count())]
    assert "Faust" not in names and "Yi Sang" in names and len(names) == 11

    saikai_before = {k: v for k, v in page.saikai_thrill_config().items()
                     if k.startswith("saikai")}
    page._stk_heal.setCurrentText("Gregor")
    cfg = page.saikai_thrill_config()
    assert cfg["hollow_heal"] == "Gregor"
    # The keyword and order come from the saved config on this machine.
    assert cfg["hollow_status"] == page._stk_states["Hollow"]["keyword"]
    assert cfg["hollow_order"] == page._stk_states["Hollow"]["order"]
    # The SAIKAI entries are untouched by the Hollow pick.
    assert {k: v for k, v in cfg.items()
            if k.startswith("saikai")} == saikai_before

    page._stk_seg._buttons["SAIKAI"].click()
    assert page._stk_order._chips["Faust"].isEnabled()
    assert page._stk_heal_row.isHidden()
    assert not page._stk_exclude_box.isHidden()
    assert page._stk_order_label.text() == "Sinner order"
    assert page.saikai_thrill_config()["hollow_heal"] == "Gregor"


def test_settings_restores_a_saved_hollow_block(ui):
    page = ui.page("settings")
    page._restore_stk({"Hollow": {"order": ["Faust", "Gregor", "Nobody"],
                                  "keyword": "Bleed", "heal": "Faust"}})
    cfg = page.saikai_thrill_config()
    assert cfg["hollow_order"] == ["Gregor"]                # no Faust
    assert cfg["hollow_status"] == "Bleed"
    assert cfg["hollow_heal"] == "Yi Sang"          # Faust is refused
    page._restore_stk({"Hollow": {"heal": "Ishmael"}})
    assert page.saikai_thrill_config()["hollow_heal"] == "Ishmael"
    page._stk_seg._buttons["Hollow"].click()
    assert page._stk_heal.currentText() == "Ishmael"
    page._stk_seg._buttons["SAIKAI"].click()


def test_the_mirror_dungeon_page_pins_the_search_gifts_for_hollow(ui):
    md = ui.page("mirror_dungeon")
    assert "Hollow" in md._custom_strategy._buttons
    md._custom_run.setChecked(True)
    md._custom_strategy._buttons["Hollow"].click()
    assert md.state()["custom_strategy"] == "Hollow"
    # The starter gift comes from the starter screen, not the search picker;
    # the picker pins the two gifts the sheet searches for.
    assert md._gift_gallery._locked == {"Grand Welcome", "Sharp Needle & Thread"}
    assert "Cigarette Holder" not in md.state()["gift_search"]
    assert set(md.state()["gift_search"]) >= {"Grand Welcome",
                                              "Sharp Needle & Thread"}
    from PySide6.QtWidgets import QPushButton
    chips = [c.text() for c in md._gift_gallery._chips_holder.findChildren(QPushButton)]
    assert any(c.startswith("Sharp Needle && Thread") for c in chips), chips
    assert not md._stk_link.isHidden()
    assert md._stk_link.text() == "Go to custom run settings"
    md._custom_strategy._buttons["F3 Hard"].click()
    assert md._gift_gallery._locked == set()
    assert md._stk_link.isHidden()
    md._custom_run.setChecked(False)
