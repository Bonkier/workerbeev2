# SPDX-License-Identifier: GPL-3.0-or-later
"""The gifts of The Wedge in the Wake of Dawnbreak (19 November 2026) in
the market catalogue. Nobody had a capture of them yet, so their shelf
templates and buy tiles are put together from the wiki's icons on the
frame the real cells share. A template made that way must not be mistaken
for a neighbour: on the owned shelf the scan would name, keep, sell or
fuse the wrong gift.

Sword Laced with Grief, from the same pack, is not in the catalogue: its
cell reads 0.83 on Sword Sharpened with Tears, too near the 0.85 gate."""
import cv2
import numpy as np
import pytest

from gui_v2 import giftart
from wbcore import shop
from wbcore.market_catalog import load_market_catalog
from wbcore.utils.utils import amplify

# name: (keyword, tier) as the wiki's gift table files them.
GIFTS = {
    "Black Tricorne": ("tremor", 2),
    "Backup Body Adaptation Device": ("tremor", 3),
    "Broken Spearhead": ("pierce", 2),
    "White Cravat": ("pierce", 3),
    "Carefully-selected Medicinal Herbs": ("pierce", 3),
    "Role Model": ("keywordless", 3),
    "Hollow Pride": ("keywordless", 1),
    "Pride of the Knight": ("keywordless", 3),
}
# The catalogue's own neighbours sit at 0.74 on each other (median) and
# one in eight at 0.80 or more; a synthesised template gets no closer.
NEAREST = 0.82


def _read(path, flags=cv2.IMREAD_COLOR):
    return cv2.imdecode(np.fromfile(path, np.uint8), flags)


@pytest.fixture(scope="module")
def catalogue():
    return load_market_catalog(refresh=True)


@pytest.mark.parametrize("name", sorted(GIFTS))
def test_a_new_gift_is_filed_with_all_three_images(catalogue, name):
    keyword, tier = GIFTS[name]
    entry = catalogue[name]
    assert (entry["keyword"], entry["tier"]) == (keyword, tier)
    assert _read(entry["sell_path"]).shape[:2] == (89, 88)
    assert _read(entry["buy_path"]).shape[:2] == (48, 48)
    art = giftart.index().get(giftart.norm(name))
    assert art and _read(art, cv2.IMREAD_UNCHANGED).shape == (256, 256, 4)


def _load(catalogue, key, shape, slack):
    """{name: (the image as the shelf shows it, with a few pixels to slide
    in; the template)}, both amplified as the scan has them."""
    out = {}
    for name, entry in catalogue.items():
        raw = _read(entry[key]) if entry.get(key) else None
        if raw is not None and raw.shape[:2] == shape:
            out[name] = (amplify(cv2.copyMakeBorder(raw, slack, slack, slack, slack,
                                                    cv2.BORDER_REPLICATE)), amplify(raw))
    return out


def _banded(image, template):
    mask = np.full(template.shape[:2], 255, np.uint8)
    mask[: int(template.shape[0] * shop._BADGE_BAND), :] = 0
    return shop._ccoeff_best(image, template, mask)[0]


def _nearest(name, images):
    """(score, gift) of the catalogue entry `name` comes closest to, either
    way round, under the shelf scan's two readings: the whole template,
    and its badge band masked out (taken for the twenty closest, the
    masked reading being the slow one)."""
    image, template = images[name]
    whole = sorted(((max(shop._ccoeff_best(other_image, template)[0],
                         shop._ccoeff_best(image, other_template)[0]), other)
                    for other, (other_image, other_template) in images.items() if other != name),
                   reverse=True)
    near = whole[0]
    for _score, other in whole[:20]:
        other_image, other_template = images[other]
        near = max(near, (max(_banded(other_image, template), _banded(image, other_template)), other))
    return near


def test_no_new_template_is_mistaken_for_another_gift(catalogue):
    cells = _load(catalogue, "sell_path", (89, 88), 3)
    assert set(GIFTS) <= set(cells)
    for name in GIFTS:
        image, template = cells[name]
        assert shop._ccoeff_best(image, template)[0] >= 0.99      # it does find itself
        score, other = _nearest(name, cells)
        assert score < NEAREST, (name, other, round(score, 3))


def test_no_new_buy_tile_is_mistaken_for_another_gift(catalogue):
    tiles = _load(catalogue, "buy_path", (48, 48), 2)
    assert set(GIFTS) <= set(tiles)
    for name in GIFTS:
        score, other = _nearest(name, tiles)
        assert score < NEAREST, (name, other, round(score, 3))
