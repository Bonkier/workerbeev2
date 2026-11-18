# SPDX-License-Identifier: GPL-3.0-or-later
"""The Logs page's DEBUG view sets the root logger to DEBUG. Two libraries
then wrote a line per call (the capture library on every COM release, the
Discord client on every websocket frame), thousands a minute, and a user's
game.log held ninety seconds of a run."""
import logging


def test_library_chatter_stays_out_of_the_log_on_debug():
    import v2_launcher
    root = logging.getLogger()
    before = root.level
    saved = {name: logging.getLogger(name).level for name in ("comtypes", "discord", "asyncio")}
    try:
        root.setLevel(logging.DEBUG)             # the Logs page's DEBUG view
        v2_launcher._quiet_libraries()
        assert not logging.getLogger("comtypes._post_coinit.unknwn").isEnabledFor(logging.DEBUG)
        assert not logging.getLogger("comtypes").isEnabledFor(logging.INFO)
        assert not logging.getLogger("discord.gateway").isEnabledFor(logging.DEBUG)
        assert logging.getLogger("discord.client").isEnabledFor(logging.INFO)
        assert logging.getLogger("wbcore.utils.paths").isEnabledFor(logging.DEBUG)
    finally:
        root.setLevel(before)
        for name, level in saved.items():
            logging.getLogger(name).setLevel(level)
