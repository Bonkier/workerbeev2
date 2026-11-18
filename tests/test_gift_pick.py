# SPDX-License-Identifier: GPL-3.0-or-later
"""The gift reward screen. One report: four gifts on offer, two to take
("Select 0/2"), one of them free of a Max HP trial. Hollow took that one,
then fell back to "the first gift whose trial leaves Max HP alone" for the
second pick, which was the same card: the click put the gift back and the
run sat at 0/2, taking and returning it every five seconds."""
import numpy as np
import pytest

from wbcore import grab as G
from wbcore.utils import params as p

# The reported screen: four cards and the x of each trial label.
CARDS = (362, 759, 1156, 1553)
TRIALS = {415: "Growth", 812: "Resilient", 1187: "Keen", 1609: "Headstrong"}


def _card_of(x):
    return min(CARDS, key=lambda c: abs(c - x))


@pytest.fixture
def screen(monkeypatch):
    """The strip get_gift reads, a get_gift that takes the first card it
    can still see (or none, with `knows` off) and the clicks made."""
    log = {"clicks": [], "knows": True}
    monkeypatch.setattr(p, "WINDOW", (0, 0, 1920, 1080))
    monkeypatch.setattr(G, "trial_columns", lambda image: dict(TRIALS))
    monkeypatch.setattr(G.LocateRGB, "locate_all", lambda *a, **k: [0] * len(CARDS))

    def get_gift(image, owned_x):
        if not log["knows"]:
            return image
        for x in CARDS:
            if image[:, x - 20:x + 20].any():
                log["clicks"].append(x)
                return G.rectangle(image, (x - 100, 0), (x + 100, 110), (0, 0, 0), -1)
        return image
    monkeypatch.setattr(G, "get_gift", get_gift)
    monkeypatch.setattr(G, "win_click", lambda x, y, **k: log["clicks"].append(x))
    log["image"] = np.full((110, 1920, 3), 90, np.uint8)
    return log


def test_two_picks_land_on_two_cards(screen):
    taken = []
    image = G.get_gift_hp_free(screen["image"], [], None, None, taken=taken)
    G.get_gift_hp_free(image, [], None, None, taken=taken)
    cards = [_card_of(x) for x in screen["clicks"]]
    assert cards[0] == 1553                      # the one free of a Max HP trial
    assert len(cards) == 2 and cards[0] != cards[1]


def test_the_fallback_does_not_click_the_card_it_took(screen):
    # Nothing the priority knows on the screen: the first pick is the
    # fallback's, and the second used to be the same fallback again.
    screen["knows"] = False
    taken = []
    image = G.get_gift_hp_free(screen["image"], [], None, None, taken=taken)
    G.get_gift_hp_free(image, [], None, None, taken=taken)
    cards = [_card_of(x) for x in screen["clicks"]]
    assert cards == [1553, 362]


def test_one_pick_still_avoids_the_max_hp_trials(screen):
    G.get_gift_hp_free(screen["image"], [], None, None)
    assert [_card_of(x) for x in screen["clicks"]] == [1553]


def test_only_max_hp_trials_on_offer_is_the_usual_pick(screen, monkeypatch):
    monkeypatch.setattr(G, "trial_columns",
                        lambda image: {415: "Growth", 812: "Resilient", 1187: "Keen"})
    monkeypatch.setattr(G.LocateRGB, "locate_all", lambda *a, **k: [0] * 3)
    G.get_gift_hp_free(screen["image"], [], None, None)
    assert [_card_of(x) for x in screen["clicks"]] == [362]


# --- the screen that stays up ------------------------------------------------

@pytest.fixture
def stuck_screen(screen, monkeypatch):
    """grab_EGO on a screen that does not close: it wants one gift more
    than the run takes."""
    class Now:
        @staticmethod
        def button(key, *a, **k):
            return key == "EGObin"
    monkeypatch.setattr(G, "now", Now)
    monkeypatch.setattr(G, "now_click", Now)
    monkeypatch.setattr(G.LocateRGB, "locate_all", lambda *a, **k: [])   # no Owned tags
    monkeypatch.setattr(G, "screenshot", lambda region=None: screen["image"].copy())
    monkeypatch.setattr(G, "wait_while_condition", lambda *a, **k: screen.get("closes", False))
    monkeypatch.setattr(G.time, "sleep", lambda s: None)
    monkeypatch.setattr(p, "RUN_SCRIPT", "")
    monkeypatch.setattr(p, "HARD", False)
    monkeypatch.setattr(p, "BUFF", [0] * 10)
    monkeypatch.setattr(G, "_PICKS", {"at": 0.0, "taken": []})
    return screen


def test_a_screen_that_stays_gets_another_gift_not_the_same_one(stuck_screen):
    assert G.grab_EGO() is True
    assert G.grab_EGO() is True
    assert G.grab_EGO() is True
    assert [_card_of(x) for x in stuck_screen["clicks"]] == [362, 759, 1156]


def test_a_screen_that_closed_is_forgotten(stuck_screen):
    stuck_screen["closes"] = True
    G.grab_EGO()
    G.grab_EGO()                                  # the next reward screen
    assert [_card_of(x) for x in stuck_screen["clicks"]] == [362, 362]


def test_an_old_screen_is_not_taken_for_this_one(stuck_screen, monkeypatch):
    G.grab_EGO()
    monkeypatch.setattr(G, "_SAME_SCREEN_S", -1.0)
    G.grab_EGO()
    assert [_card_of(x) for x in stuck_screen["clicks"]] == [362, 362]


def test_a_confirm_that_lands_late_takes_no_extra_gift(stuck_screen, monkeypatch):
    G.grab_EGO()                                  # picked, the screen still up
    monkeypatch.setattr(G, "wait_while_condition", lambda *a, **k: True)
    assert G.grab_EGO() is True                   # confirmed again: it closes
    assert [_card_of(x) for x in stuck_screen["clicks"]] == [362]
    assert G._PICKS["taken"] == []


def test_a_screen_with_nothing_left_to_add_starts_over(stuck_screen, monkeypatch):
    dumps = []
    monkeypatch.setattr(G, "dump_template_diag", lambda tag, *names: dumps.append(tag))
    monkeypatch.setattr(G, "_LAST_STUCK_DIAG", 0.0)
    for _ in range(len(CARDS)):
        G.grab_EGO()                              # one card more each time
    assert len(G._PICKS["taken"]) == len(CARDS)
    G.grab_EGO()                                  # nothing left to add
    assert G._PICKS["taken"] == [] and dumps == ["gift_pick_stuck"]
    G.grab_EGO()                                  # from the top again
    assert [_card_of(x) for x in stuck_screen["clicks"]][-1] == 362
