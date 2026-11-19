# SPDX-License-Identifier: GPL-3.0-or-later
"""The gift pop-up's Confirm. The key press does not always close it, and a
second press of the same key did no better: a pop-up that ignored the key
held the run on that screen. The button is clicked instead, as
Charge-Grinder does since v3.6.0."""
import pytest

from wbcore import grab as G


@pytest.fixture
def popup(monkeypatch):
    """A pop-up that shows what `shows` says, look after look, and the keys
    and clicks it was sent."""
    def build(shows):
        log = {"shows": list(shows), "keys": [], "clicks": []}

        def look(name):
            assert name == "Confirm"
            return log["shows"].pop(0) if log["shows"] else False

        def click(name):
            found = look(name)
            if found:
                log["clicks"].append(name)
            return found

        monkeypatch.setattr(G, "now", type("Now", (), {"button": staticmethod(look)}))
        monkeypatch.setattr(G, "now_click", type("Click", (), {"button": staticmethod(click)}))
        monkeypatch.setattr(G, "gui", type("Keys", (), {
            "press": staticmethod(lambda key: log["keys"].append(key))}))
        monkeypatch.setattr(G, "time", type("Clock", (), {
            "sleep": staticmethod(lambda seconds: None)}))
        return log
    return build


def test_no_popup_is_left_alone(popup):
    log = popup([False])
    assert G.confirm() is False
    assert log["keys"] == [] and log["clicks"] == []


def test_the_key_closes_the_popup(popup):
    log = popup([True, False])
    assert G.confirm() is True
    assert log["keys"] == ["space"] and log["clicks"] == []


def test_a_popup_the_key_left_up_is_clicked(popup):
    log = popup([True, True])
    assert G.confirm() is True
    assert log["keys"] == ["space"]              # not pressed a second time
    assert log["clicks"] == ["Confirm"]
