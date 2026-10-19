# SPDX-License-Identifier: GPL-3.0-or-later
"""Event choices taken over the E.G.O text rule each have their title
template, and the Sinking-check event's second option is among them."""
import cv2

from wbcore import event as E
from wbcore.utils.paths import PTH


def test_every_favourite_choice_has_its_title_template():
    for fav in E.favorites:
        assert "choice_" + fav in PTH, fav
        img = cv2.imread(PTH["choice_" + fav])
        assert img is not None and img.shape[1] > 150 and 20 < img.shape[0] < 80
    assert "failedprotect" in E.favorites
