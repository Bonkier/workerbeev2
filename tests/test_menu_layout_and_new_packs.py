# SPDX-License-Identifier: GPL-3.0-or-later
"""The game laid its main menu out again on 19 November 2026: the Mirror
Dungeons and Luxcavation entries moved and read on one line each, so the
old templates no longer found them and no run could start. Five theme packs
were unknown to the bot as well. Templates, regions and the pack table
follow Charge-Grinder v3.6.1."""
import cv2
import pytest

from gui_v2.widgets import humanize_pack
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


def test_the_menu_entries_read_on_one_line():
    # The old Mirror Dungeons template was the two-line label, 57 px tall.
    assert cv2.imread(PTH["MD"]).shape[0] < 45
    assert cv2.imread(PTH["Lux"]).shape[0] < 45


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
