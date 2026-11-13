# SPDX-License-Identifier: GPL-3.0-or-later
"""Pixel-art glyphs for setting rows and controls: 9x9 bitmaps drawn in a
theme colour at the pixel face's scale, so a row's icon sits with the
pixel headings instead of beside them."""

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QPainter, QPixmap

from .theme import Colors

_GLYPHS = {
    "gift": (
        "...#.#...",
        "..#.#.#..",
        ".#######.",
        ".#..#..#.",
        "#########",
        "#...#...#",
        "#...#...#",
        "#...#...#",
        "#########",
    ),
    "one": (
        ".........",
        "....#....",
        "...##....",
        "..#.#....",
        "....#....",
        "....#....",
        "....#....",
        "....#....",
        "..#####..",
    ),
    "bolt": (
        "....###..",
        "...##....",
        "..##.....",
        ".######..",
        "....##...",
        "...##....",
        "..##.....",
        ".##......",
        "##.......",
    ),
    "skip": (
        ".........",
        "#....#...",
        "##...##..",
        "###..###.",
        "####.####",
        "###..###.",
        "##...##..",
        "#....#...",
        ".........",
    ),
    "trophy": (
        "#########",
        "#.#####.#",
        "#.#####.#",
        "#.#####.#",
        ".#.###.#.",
        "...###...",
        "....#....",
        "..#####..",
        "..#####..",
    ),
    "swap": (
        "..#......",
        ".##......",
        "#########",
        ".##......",
        "..#...#..",
        "......##.",
        "#########",
        "......##.",
        "......#..",
    ),
    "sparkle": (
        "....#....",
        "....#....",
        ".#..#..#.",
        "..#.#.#..",
        "#########",
        "..#.#.#..",
        ".#..#..#.",
        "....#....",
        "....#....",
    ),
    "loop": (
        "..###.###",
        ".#....###",
        "#......#.",
        "#........",
        "#........",
        "#........",
        ".#......#",
        "..#....#.",
        "...####..",
    ),
    "chest": (
        ".........",
        ".#######.",
        "#.......#",
        "#########",
        "#...#...#",
        "#..###..#",
        "#...#...#",
        "#.......#",
        ".#######.",
    ),
    "close": (
        "#########",
        "#########",
        "#.......#",
        "#.#...#.#",
        "#..#.#..#",
        "#...#...#",
        "#..#.#..#",
        "#.#...#.#",
        "#########",
    ),
    "hash": (
        ".........",
        "..#...#..",
        "..#...#..",
        "#########",
        "..#...#..",
        "..#...#..",
        "#########",
        "..#...#..",
        "..#...#..",
    ),
    "dice": (
        ".#######.",
        "#.......#",
        "#.##....#",
        "#.##....#",
        "#...##..#",
        "#...##..#",
        "#....##.#",
        "#....##.#",
        ".#######.",
    ),
}


def pixel_icon(name: str, color: str = "", pixel: int = 2) -> QPixmap:
    """`name`'s glyph as a pixmap, or an empty one for a name not drawn."""
    rows = _GLYPHS.get(name)
    if rows is None:
        return QPixmap()
    pm = QPixmap(len(rows[0]) * pixel, len(rows) * pixel)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QColor(color or Colors.TEXT_SECONDARY))
    for y, row in enumerate(rows):
        for x, cell in enumerate(row):
            if cell == "#":
                p.drawRect(x * pixel, y * pixel, pixel, pixel)
    p.end()
    return pm
