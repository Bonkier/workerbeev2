# SPDX-License-Identifier: GPL-3.0-or-later
"""The game laid its main menu out again on 19 November 2026: the Mirror
Dungeons and Luxcavation entries moved and read on one line each, so the
old templates no longer found them and no run could start. Five theme packs
were unknown to the bot as well. A week later the Mirror Dungeons label
was back on two lines, in the place it had moved to. Templates, regions
and the pack table follow Charge-Grinder v3.6.2."""
import types

import cv2
import numpy as np
import pytest

from gui_v2.widgets import humanize_pack
from wbcore.utils import params as p
from wbcore.utils import utils as U
from wbcore.utils.paths import FLOORS, HARD_FLOORS, PACKS, PTH, REG

NEW_PACKS = {
    "TheWedgeDawnbreak": ((5,), (5,)),
    "StorefrontCampout": ((3, 4), (3, 4)),
    "AnAnarchyofColors": ((), (4, 5)),
    "CreedofPreservation": ((), (4, 5)),
    "ReadventofGluttony": ((), (4, 5)),
}


def test_the_menu_entries_are_looked_for_where_they_moved_to():
    assert REG["MD"] == (539, 266, 247, 126)
    assert REG["Lux"] == (543, 123, 240, 124)


@pytest.mark.parametrize("name", ["MD", "Lux", "projection", "check"])
def test_a_template_fits_the_region_it_is_looked_for_in(name):
    template = cv2.imread(PTH[name])
    _x, _y, w, h = REG[name]
    assert template is not None
    assert template.shape[1] <= w and template.shape[0] <= h


def test_luxcavation_reads_on_one_line():
    assert cv2.imread(PTH["Lux"]).shape[0] < 45


def test_mirror_dungeons_reads_on_two_lines():
    # 196 x 33 on one line from 19 November; two lines again from 26
    # November, in smaller type than the 137 x 57 label of before the move.
    height, width = cv2.imread(PTH["MD"]).shape[:2]
    assert 45 <= height < 57 and width < 137


def _screen_with(label, at):
    frame = np.full((1080, 1920, 3), 25, np.uint8)
    h, w = label.shape[:2]
    frame[at[1]:at[1] + h, at[0]:at[0] + w] = label
    return types.SimpleNamespace(
        screenshot=lambda region=(0, 0, 1920, 1080): frame[
            region[1]:region[1] + region[3], region[0]:region[0] + region[2]].copy(),
        center=lambda box: (box[0] + box[2] // 2, box[1] + box[3] // 2),
        getActiveWindowTitle=lambda: "LimbusCompany", get_position=lambda: (0, 0),
        moveTo=lambda *a, **k: None, click=lambda *a, **k: None,
        dragTo=lambda *a, **k: None)


@pytest.mark.parametrize("at, found", [((600, 300), True), ((560, 270), True),
                                       ((900, 300), False)])
def test_the_start_chain_sees_the_entry_only_in_its_place(monkeypatch, at, found):
    display = _screen_with(cv2.imread(PTH["MD"]), at)
    U._reset_pipeline_cache()
    monkeypatch.setattr(p, "WINDOW", (0, 0, 1920, 1080))
    monkeypatch.setattr(U, "gui", display)
    monkeypatch.setattr(U, "screenshot", display.screenshot)
    try:
        assert bool(U.now.button("MD")) is found
    finally:
        U._reset_pipeline_cache()


@pytest.mark.parametrize("key", sorted(NEW_PACKS))
def test_a_new_pack_has_its_template_and_its_floors(key):
    assert key in PTH and cv2.imread(PTH[key]) is not None
    normal, hard = NEW_PACKS[key]
    assert PACKS[key] == (normal, hard)
    for floor in normal:
        assert key in FLOORS[floor]
    for floor in hard:
        assert key in HARD_FLOORS[floor]


def test_the_new_packs_read_by_their_in_game_names():
    assert humanize_pack("TheWedgeDawnbreak") == "The Wedge in the Wake of Dawnbreak"
    assert humanize_pack("StorefrontCampout") == "Storefront Campout"
    assert humanize_pack("AnAnarchyofColors") == "An Anarchy of Colors"
    assert humanize_pack("CreedofPreservation") == "Creed of Preservation"
    assert humanize_pack("ReadventofGluttony") == "Readvent of Gluttony"
