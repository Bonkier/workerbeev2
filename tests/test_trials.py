# SPDX-License-Identifier: GPL-3.0-or-later
"""The Hollow run and the Mounting Trials on the gift reward screen: the
gifts whose trial raises the enemies' Max HP are kept out of the pick."""
import cv2
import numpy as np
import pytest

from wbcore import grab as G
from wbcore.utils import params as p
from wbcore.utils import utils as U


def _row(height, *pastes):
    """A dark 1920-wide strip with templates pasted at x centres."""
    canvas = np.full((height, 1920, 3), 12, np.uint8)
    for name, cx in pastes:
        img = cv2.imread(U.PTH[name])
        h, w = img.shape[:2]
        y = (height - h) // 2
        canvas[y:y + h, cx - w // 2:cx - w // 2 + w] = img
    return canvas


@pytest.fixture
def screen(monkeypatch):
    """`get_gift` stands in: it records what it was shown and, unless told
    it knows nothing there, blacks out the column it would have clicked."""
    monkeypatch.setattr(p, "WINDOW", (0, 0, 1920, 1080))
    picks = type("Picks", (list,), {})()
    picks.pick_x = 1010

    def get_gift(image, owned):
        picks.append(image.copy())
        if picks.pick_x is not None:
            cv2.rectangle(image, (picks.pick_x - 100, 0), (picks.pick_x + 100, 110), (0, 0, 0), -1)
        return image
    monkeypatch.setattr(G, "get_gift", get_gift)
    monkeypatch.setattr(G, "win_click", lambda *a, **k: picks.append(("click",) + tuple(a)))
    return picks


def test_every_trial_label_on_the_row_is_read():
    row = _row(52, ("trial_Keen", 584), ("trial_Headstrong", 1010), ("trial_BasePower", 1352))
    cols = G.trial_columns(row)
    assert {cols[x] for x in cols} == {"Keen", "Headstrong", "BasePower"}
    assert sorted(cols) == pytest.approx([584, 1010, 1352], abs=4)


def test_the_max_hp_trials_are_blacked_out_before_the_pick(screen):
    picks = screen
    gifts = np.full((110, 1920, 3), 200, np.uint8)
    trials = _row(52, ("trial_Keen", 584), ("trial_Headstrong", 1010), ("trial_BasePower", 1352))
    labels = _row(55, ("trials", 584), ("trials", 1010), ("trials", 1352))
    G.get_gift_hp_free(gifts, [], trials, labels)
    shown = picks[0]
    assert shown[50, 584].max() == 0 and shown[50, 1352].max() == 0
    assert shown[50, 1010].max() == 200                       # Headstrong stays
    assert not any(isinstance(x, tuple) for x in picks)       # no fallback click


def test_when_every_trial_raises_max_hp_the_usual_pick_runs(screen):
    picks = screen
    gifts = np.full((110, 1920, 3), 200, np.uint8)
    trials = _row(52, ("trial_Keen", 584), ("trial_Growth", 1010), ("trial_Resilient", 1352))
    labels = _row(55, ("trials", 584), ("trials", 1010), ("trials", 1352))
    assert G.get_gift_hp_free(gifts, [], trials, labels) is gifts
    assert len(picks) == 1 and picks[0][50, 584].max() == 200  # nothing masked


def test_a_gift_the_priority_does_not_know_is_still_taken_for_its_trial(screen):
    picks = screen
    gifts = np.full((110, 1920, 3), 200, np.uint8)
    trials = _row(52, ("trial_Keen", 584), ("trial_Headstrong", 1010))
    labels = _row(55, ("trials", 584), ("trials", 1010))
    picks.pick_x = None                                       # the priority knows neither
    out = G.get_gift_hp_free(gifts, [], trials, labels)
    clicks = [x for x in picks if isinstance(x, tuple)]
    assert clicks == [("click", 1010, 600)]                   # the Headstrong gift
    assert out[50, 1010].max() == 0                           # and it is spent


def test_the_hp_trial_list_matches_the_wiki():
    assert set(G.HP_TRIALS) == {"Keen", "Growth", "Resilient", "BodyUp",
                                "BasePower", "ClashPower", "FinalPower"}
    assert not {"Headstrong", "Brutality", "DefenseLevelUp", "DefenseSkillUp",
                "OffenseLevelUp", "TakeLessDamage"} & set(G.HP_TRIALS)
    assert all(f"trial_{n}" in U.PTH for n in G.mounting_trials)
