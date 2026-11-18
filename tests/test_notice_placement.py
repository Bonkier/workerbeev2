# SPDX-License-Identifier: GPL-3.0-or-later
"""A notice raised while the bot drives the game (a Detection check, the
wrong-resolution help) is shown without taking focus. A window shown that
way still lands on top of an ordinary window: over a windowed game it hid
part of the screen from the bot's reads and took the clicks meant for the
game, until someone closed it. It is slid under the game window."""


class _User32:
    """Just enough of user32: the game's window, the one in front, and the
    calls that would restack a window."""

    def __init__(self, game=0x501, front=0x501):
        self.game, self.front = game, front
        self.moved = []

    def FindWindowW(self, cls, title):
        assert title == "LimbusCompany"
        return self.game

    def GetForegroundWindow(self):
        return self.front

    def SetWindowPos(self, hwnd, after, x, y, w, h, flags):
        self.moved.append((hwnd, after, flags))
        return 1


class _Notice:
    def winId(self):
        return 0x777


def test_a_notice_is_slid_under_the_game_when_the_game_is_in_front():
    from gui_v2.dialogs import keep_behind_game
    user32 = _User32()
    assert keep_behind_game(_Notice(), user32=user32) is True
    hwnd, after, flags = user32.moved[0]
    assert (hwnd, after) == (0x777, 0x501)
    assert flags == 0x0001 | 0x0002 | 0x0010     # no resize, no move, no focus


def test_a_notice_is_left_where_it_is_otherwise():
    from gui_v2.dialogs import keep_behind_game
    reading = _User32(front=0x900)               # the user is on WorkerBee
    assert keep_behind_game(_Notice(), user32=reading) is False
    closed = _User32(game=0)                     # the game is not running
    assert keep_behind_game(_Notice(), user32=closed) is False
    assert reading.moved == [] and closed.moved == []
