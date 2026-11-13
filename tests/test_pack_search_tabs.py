# SPDX-License-Identifier: GPL-3.0-or-later
"""The Pack Search window names the difficulty it lists on a tab: NORMAL in
blue, HARD in purple. Each template has to find its own tab and not the
other's, or the check made after opening the window says nothing."""

import cv2
import numpy as np
import pytest

from wbcore.detection import ColorMode
from wbcore.regionspec import WindowGeometry
from wbcore.utils.paths import PTH
from wbcore.vision.finder import Finder

TABS = ("normalpackUI", "hardpackUI")
SPOT = (1143, 177)          # the inside of the tab at 1920x1080


def _finder_on(shown):
    frame = np.zeros((1080, 1920, 3), np.uint8)
    tab = cv2.imread(PTH[shown])
    h, w = tab.shape[:2]
    frame[SPOT[1]:SPOT[1] + h, SPOT[0]:SPOT[0] + w] = tab
    return Finder(window=WindowGeometry.identity(),
                  backend=lambda r: frame[r.y:r.y + r.h, r.x:r.x + r.w],
                  color_mode=ColorMode.RGB)


@pytest.mark.parametrize("shown", TABS)
def test_each_tab_is_found_and_the_other_is_not(shown):
    finder = _finder_on(shown)
    other = TABS[1 - TABS.index(shown)]
    hit = finder.find(PTH[shown], region=(0, 0, 1920, 1080))
    assert hit is not None and (hit.x, hit.y) == SPOT
    assert finder.find(PTH[other], region=(0, 0, 1920, 1080)) is None


def test_the_tabs_are_cut_from_the_same_box():
    sizes = {cv2.imread(PTH[name]).shape for name in TABS}
    assert len(sizes) == 1
