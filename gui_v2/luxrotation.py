# SPDX-License-Identifier: GPL-3.0-or-later
"""Luxcavation's daily rotations. BOTH modes rotate, on different keys.

Thread Luxcavation opens one stage per day keyed to a SIN AFFINITY, on a fixed
weekly cycle.

EXP Luxcavation stages I-VI are open every day, but from Canto VII the stages
are gated by DAMAGE TYPE: Slash on Mon/Tue, Pierce on Wed/Thu, Blunt on
Fri/Sat, and all three on Sunday.

Sources: https://limbuscompany.wiki.gg/wiki/Thread_Luxcavation
         https://limbuscompany.wiki.gg/wiki/Luxcavation

The day flips on the game's daily reset at 06:00 KST, which is 21:00 UTC the
evening before - NOT UTC midnight - so the label is taken from the UTC clock
shifted forward three hours (UTC+9 for KST, less the 6-hour reset offset).
"""

import datetime as _dt

# Indexed by the shifted date's weekday(): Monday = 0 ... Sunday = 6.
_BY_WEEKDAY = (
    "Lust",       # Monday
    "Sloth",      # Tuesday
    "Gluttony",   # Wednesday
    "Gloom",      # Thursday
    "Pride",      # Friday
    "Envy",       # Saturday
    "Wrath",      # Sunday
)

# EXP Luxcavation, Canto VII+. Indexed by weekday(): Monday = 0 ... Sunday = 6.
# Sunday is the only day all three are open.
_EXP_BY_WEEKDAY = (
    ("Slash",),                      # Monday
    ("Slash",),                      # Tuesday
    ("Pierce",),                     # Wednesday
    ("Pierce",),                     # Thursday
    ("Blunt",),                      # Friday
    ("Blunt",),                      # Saturday
    ("Slash", "Pierce", "Blunt"),    # Sunday
)

# Stages below this are open every day regardless of damage type.
EXP_ALWAYS_OPEN_UPTO = 6

_RESET_SHIFT = _dt.timedelta(hours=3)


def game_day(now: _dt.datetime | None = None) -> _dt.datetime:
    """The datetime whose weekday names the current in-game day."""
    now = now or _dt.datetime.now(_dt.timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=_dt.timezone.utc)
    return now.astimezone(_dt.timezone.utc) + _RESET_SHIFT


def thread_affinity(now: _dt.datetime | None = None) -> str:
    """Sin affinity Thread Luxcavation is running right now."""
    return _BY_WEEKDAY[game_day(now).weekday()]


# Tie-break order when several EXP damage types are open (Sunday).
EXP_PRIORITY = ("Slash", "Pierce", "Blunt")


def preferred_exp_type(types, uses=None) -> str:
    """Which damage type to suggest when more than one is open. The one the
    user has run most; on a tie, Slash first, then Pierce, then Blunt."""
    if not types:
        return EXP_PRIORITY[0]
    uses = uses or {}
    def rank(t):
        order = EXP_PRIORITY.index(t) if t in EXP_PRIORITY else len(EXP_PRIORITY)
        return (-int(uses.get(t, 0) or 0), order)
    return min(types, key=rank)


def exp_types(now: _dt.datetime | None = None) -> tuple:
    """Damage types EXP Luxcavation Canto VII+ is running right now."""
    return _EXP_BY_WEEKDAY[game_day(now).weekday()]


def week() -> list:
    """[(weekday name, affinity, exp types, is_today)] starting from today."""
    today = game_day()
    out = []
    for i in range(7):
        d = today + _dt.timedelta(days=i)
        out.append((d.strftime("%a"), _BY_WEEKDAY[d.weekday()],
                    _EXP_BY_WEEKDAY[d.weekday()], i == 0))
    return out


def next_change(now: _dt.datetime | None = None) -> _dt.timedelta:
    """Time left until the affinity rotates."""
    shifted = game_day(now)
    tomorrow = (shifted + _dt.timedelta(days=1)).replace(
        hour=0, minute=0, second=0, microsecond=0)
    return tomorrow - shifted
