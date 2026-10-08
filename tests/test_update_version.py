# SPDX-License-Identifier: GPL-3.0-or-later
"""Version comparison for the updater. A release can carry an edition letter
(v2.4.2e); the letter must not change how the number compares, or installed
copies either never update or update forever."""

import pytest

from gui_v2 import updater as U


@pytest.mark.parametrize("text, parsed", [
    ("2.4.1", (2, 4, 1)),
    ("v2.4.2", (2, 4, 2)),
    ("v2.4.2e", (2, 4, 2)),
    ("2.4.2e", (2, 4, 2)),
    ("2.10.0", (2, 10, 0)),
    ("v2.4.2e\n", (2, 4, 2)),
    ("dev", (0,)),
    ("2.x.1", (2, 0, 1)),
])
def test_versions_parse_by_their_leading_digits(text, parsed):
    assert U._parse_version(text) == parsed


def test_an_edition_letter_neither_blocks_nor_loops_the_update():
    # Installed 2.4.1 sees the 2.4.2 tag and updates.
    assert U.is_newer("2.4.2", "2.4.1")
    # Once on 2.4.2e, the same tag is not offered again.
    assert not U.is_newer("2.4.2", "2.4.2e")
    assert not U.is_newer("2.4.2e", "2.4.2e")
    # The next release still is.
    assert U.is_newer("2.4.3", "2.4.2e")
    assert not U.is_newer("2.4.1", "2.4.2e")
