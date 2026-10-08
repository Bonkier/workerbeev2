# SPDX-License-Identifier: GPL-3.0-or-later
"""Voxel brand art for the v2.4 skin: an animated voxel bee and a pixel
wordmark. Both are painted from data (no image or font assets), so they stay
crisp at any DPI and cannot go missing from a build."""

from __future__ import annotations

import math

from PySide6.QtCore import QPointF, QRectF, Qt, QTimer
from PySide6.QtGui import QColor, QPainter, QPen, QPolygonF
from PySide6.QtWidgets import QVBoxLayout, QWidget

from . import seasonal
from .theme import Colors

# --- voxel model -----------------------------------------------------------
# (x, y, z, tone). x right, y up, z back. Tones resolve against the palette
# below so the bee follows the accent colour.
_BODY = "body"      # accent (brand yellow)
_DARK = "dark"      # stripe / stinger
_HEAD = "head"      # slightly lighter than the stripes so it reads separately
_WING = "wing"      # translucent wing
_EYE = "eye"

def _bee_voxels():
    """The bee as (x, y, z, tone) cubes: a solid 3x3 cuboid body in accent /
    dark bands, a solid head block, eyes and a stinger. Chunky on purpose so
    it still reads as a bee at 34px."""
    out = []
    # Abdomen: a full 3 x 3 x 4 cuboid, banded front-to-back.
    for i, z in enumerate((0, 1, 2, 3)):
        tone = _BODY if i % 2 == 0 else _DARK
        for x in (-1, 0, 1):
            for y in (-1, 0, 1):
                out.append((x, y, z, tone))
    # Head: a solid 3 x 3 block on the front of the body, with the eyes set
    # INTO the face rather than stuck on it (protruding cubes read as feet
    # from behind).
    for x in (-1, 0, 1):
        for y in (-1, 0, 1):
            tone = _EYE if (abs(x) == 1 and y == 0) else _HEAD
            out.append((x, y, -1, tone))
    # Stinger, one cube off the tail.
    out.append((0, 0, 4, _DARK))
    return out


# Bat wings for October: a leading edge four cubes long with a scalloped
# trailing edge behind it, on each side.
_BAT_WING_VOXELS = [
    (sx * x, 1, z) for sx in (-1, 1)
    for x, z in ((2, 1), (3, 1), (4, 1), (5, 1),
                 (2, 2), (3, 2), (4, 2), (2, 3), (4, 3))
]

# Wings sit on the top edge of the body and flap.
_WING_VOXELS = [(-2, 1, 1), (-3, 1, 1), (-2, 1, 2),
                (2, 1, 1), (3, 1, 1), (2, 1, 2)]

# Cube face corner offsets, per axis, as (normal, [4 corners]).
_HALF = 0.5
_FACES = (
    ((0, 1, 0), ((-_HALF, _HALF, -_HALF), (_HALF, _HALF, -_HALF),
                 (_HALF, _HALF, _HALF), (-_HALF, _HALF, _HALF))),
    ((0, -1, 0), ((-_HALF, -_HALF, -_HALF), (_HALF, -_HALF, -_HALF),
                  (_HALF, -_HALF, _HALF), (-_HALF, -_HALF, _HALF))),
    ((1, 0, 0), ((_HALF, -_HALF, -_HALF), (_HALF, _HALF, -_HALF),
                 (_HALF, _HALF, _HALF), (_HALF, -_HALF, _HALF))),
    ((-1, 0, 0), ((-_HALF, -_HALF, -_HALF), (-_HALF, _HALF, -_HALF),
                  (-_HALF, _HALF, _HALF), (-_HALF, -_HALF, _HALF))),
    ((0, 0, 1), ((-_HALF, -_HALF, _HALF), (_HALF, -_HALF, _HALF),
                 (_HALF, _HALF, _HALF), (-_HALF, _HALF, _HALF))),
    ((0, 0, -1), ((-_HALF, -_HALF, -_HALF), (_HALF, -_HALF, -_HALF),
                  (_HALF, _HALF, -_HALF), (-_HALF, _HALF, -_HALF))),
)

# Per-face shading: top bright, sides progressively darker. Keeps the cubes
# reading as 3D without any lighting maths.
_FACE_SHADE = {(0, 1, 0): 1.00, (0, -1, 0): 0.45,
               (1, 0, 0): 0.72, (-1, 0, 0): 0.72,
               (0, 0, 1): 0.58, (0, 0, -1): 0.86}

_PITCH = math.radians(30.0)      # fixed isometric-ish tilt


class VoxelLogo(QWidget):
    """The WorkerBee mark as a slowly turning voxel bee: continuous yaw, a
    gentle hover bob and flapping wings. Repaints only while visible."""

    def __init__(self, size: int = 34, parent: QWidget | None = None):
        super().__init__(parent)
        self._px = size
        self.setFixedSize(size, size)
        self._voxels = _bee_voxels()
        self._t = 0.0
        self._timer = QTimer(self)
        self._timer.setInterval(50)          # 20fps is plenty for this motion
        self._timer.timeout.connect(self._tick)

    # Animate only while on screen so a hidden page costs nothing.
    def showEvent(self, e):
        self._timer.start()
        super().showEvent(e)

    def hideEvent(self, e):
        self._timer.stop()
        super().hideEvent(e)

    def _tick(self):
        self._t += 0.05
        self.update()

    def refresh_theme(self):
        """Called by themes._restyle_running_app after a palette change."""
        self.update()

    def _palette(self):
        if seasonal.is_halloween():
            return {
                _BODY: QColor(seasonal.RED),
                # "Black" is lifted a little: true black disappears into
                # the October background and leaves only the red bands.
                _DARK: QColor("#30141b"),
                _HEAD: QColor("#3a1a22"),
                _EYE: QColor("#ffb000"),
                _WING: QColor("#96202f"),
            }
        return {
            _BODY: QColor(Colors.ACCENT),
            _DARK: QColor(Colors.BG_PRESSED),
            _HEAD: QColor(Colors.BORDER_STRONG),
            _EYE: QColor(Colors.TEXT_PRIMARY),
            _WING: QColor(Colors.INFO),
        }

    def paintEvent(self, _e):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, False)  # crisp voxels
        yaw = self._t * 0.6
        bob = math.sin(self._t * 1.6) * 0.18
        flap = math.sin(self._t * 6.0) * 0.45
        cos_y, sin_y = math.cos(yaw), math.sin(yaw)
        cos_p, sin_p = math.cos(_PITCH), math.sin(_PITCH)
        bat = seasonal.is_halloween()
        # The bat wings reach further out, so the model is drawn smaller.
        scale = self._px / (11.0 if bat else 9.0)
        cx, cy = self.width() / 2.0, self.height() / 2.0
        pal = self._palette()

        def project(x, y, z):
            """World -> screen, plus `near`: how close the point is to the
            camera (larger = nearer). Screen y grows downward, so a bigger
            rz sits lower on screen, i.e. toward the viewer; height adds to
            nearness through the camera's tilt."""
            rx = x * cos_y - z * sin_y
            rz = x * sin_y + z * cos_y
            sx = cx + rx * scale
            sy = cy - (y + bob) * cos_p * scale + rz * sin_p * scale
            near = rz * cos_p + (y + bob) * sin_p
            return sx, sy, near

        # Body voxels plus the (animated) wings.
        cubes = [(x, y, z, tone) for x, y, z, tone in self._voxels]
        if bat:
            # Beat from the shoulder: the tips travel furthest.
            for wx, wy, wz in _BAT_WING_VOXELS:
                cubes.append((wx, wy + flap * (abs(wx) - 1) / 2.0, wz,
                              _WING))
        else:
            for wx, wy, wz in _WING_VOXELS:
                cubes.append((wx, wy + flap, wz, _WING))

        # Farthest cubes first so nearer ones paint over them.
        cubes.sort(key=lambda c: project(c[0], c[1], c[2])[2])

        for x, y, z, tone in cubes:
            base = pal[tone]
            _sx, _sy, cube_near = project(x, y, z)
            faces = []
            for normal, corners in _FACES:
                fx = x + normal[0] * _HALF
                fy = y + normal[1] * _HALF
                fz = z + normal[2] * _HALF
                _px_, _py_, fnear = project(fx, fy, fz)
                if fnear <= cube_near:
                    continue                 # face points away from the camera
                faces.append((fnear, normal, corners))
            faces.sort(key=lambda f: f[0])   # far face first within the cube
            for _fn, normal, corners in faces:
                poly = QPolygonF()
                for ox, oy, oz in corners:
                    sx, sy, _d = project(x + ox, y + oy, z + oz)
                    poly.append(QPointF(sx, sy))
                shade = _FACE_SHADE[normal]
                col = QColor(int(base.red() * shade),
                             int(base.green() * shade),
                             int(base.blue() * shade))
                if tone == _WING:
                    col.setAlpha(235 if bat else 150)
                p.setBrush(col)
                p.setPen(Qt.PenStyle.NoPen)
                p.drawPolygon(poly)
        p.end()


# --- pixel font ------------------------------------------------------------
# A 5x7 bitmap face drawn as squares: true pixel type at any size, with no
# font file to ship or license. Used for the wordmark and every panel header,
# which is what makes the UI read as pixel art rather than a dark theme with
# square corners.
_GLYPHS = {
    "A": (".###.", "#...#", "#...#", "#####", "#...#", "#...#", "#...#"),
    "B": ("####.", "#...#", "#...#", "####.", "#...#", "#...#", "####."),
    "C": (".###.", "#...#", "#....", "#....", "#....", "#...#", ".###."),
    "D": ("####.", "#...#", "#...#", "#...#", "#...#", "#...#", "####."),
    "E": ("#####", "#....", "#....", "###..", "#....", "#....", "#####"),
    "F": ("#####", "#....", "#....", "###..", "#....", "#....", "#...."),
    "G": (".###.", "#...#", "#....", "#.###", "#...#", "#...#", ".###."),
    "H": ("#...#", "#...#", "#...#", "#####", "#...#", "#...#", "#...#"),
    "I": (".###.", "..#..", "..#..", "..#..", "..#..", "..#..", ".###."),
    "J": ("..###", "...#.", "...#.", "...#.", "...#.", "#..#.", ".##.."),
    "K": ("#...#", "#..#.", "#.#..", "##...", "#.#..", "#..#.", "#...#"),
    "L": ("#....", "#....", "#....", "#....", "#....", "#....", "#####"),
    "M": ("#...#", "##.##", "#.#.#", "#.#.#", "#...#", "#...#", "#...#"),
    "N": ("#...#", "##..#", "#.#.#", "#..##", "#...#", "#...#", "#...#"),
    "O": (".###.", "#...#", "#...#", "#...#", "#...#", "#...#", ".###."),
    "P": ("####.", "#...#", "#...#", "####.", "#....", "#....", "#...."),
    "Q": (".###.", "#...#", "#...#", "#...#", "#.#.#", "#..#.", ".##.#"),
    "R": ("####.", "#...#", "#...#", "####.", "#.#..", "#..#.", "#...#"),
    "S": (".####", "#....", "#....", ".###.", "....#", "....#", "####."),
    "T": ("#####", "..#..", "..#..", "..#..", "..#..", "..#..", "..#.."),
    "U": ("#...#", "#...#", "#...#", "#...#", "#...#", "#...#", ".###."),
    "V": ("#...#", "#...#", "#...#", "#...#", "#...#", ".#.#.", "..#.."),
    "W": ("#...#", "#...#", "#...#", "#.#.#", "#.#.#", "##.##", "#...#"),
    "X": ("#...#", "#...#", ".#.#.", "..#..", ".#.#.", "#...#", "#...#"),
    "Y": ("#...#", "#...#", ".#.#.", "..#..", "..#..", "..#..", "..#.."),
    "Z": ("#####", "....#", "...#.", "..#..", ".#...", "#....", "#####"),
    "0": (".###.", "#...#", "#..##", "#.#.#", "##..#", "#...#", ".###."),
    "1": ("..#..", ".##..", "..#..", "..#..", "..#..", "..#..", ".###."),
    "2": (".###.", "#...#", "....#", "...#.", "..#..", ".#...", "#####"),
    "3": ("#####", "...#.", "..#..", "...#.", "....#", "#...#", ".###."),
    "4": ("...#.", "..##.", ".#.#.", "#..#.", "#####", "...#.", "...#."),
    "5": ("#####", "#....", "####.", "....#", "....#", "#...#", ".###."),
    "6": ("..##.", ".#...", "#....", "####.", "#...#", "#...#", ".###."),
    "7": ("#####", "....#", "...#.", "..#..", ".#...", ".#...", ".#..."),
    "8": (".###.", "#...#", "#...#", ".###.", "#...#", "#...#", ".###."),
    "9": (".###.", "#...#", "#...#", ".####", "....#", "...#.", ".##.."),
    " ": (".....", ".....", ".....", ".....", ".....", ".....", "....."),
    ".": (".....", ".....", ".....", ".....", ".....", ".##..", ".##.."),
    ",": (".....", ".....", ".....", ".....", ".##..", ".##..", ".#..."),
    ":": (".....", ".##..", ".##..", ".....", ".##..", ".##..", "....."),
    "-": (".....", ".....", ".....", "#####", ".....", ".....", "....."),
    "/": ("....#", "....#", "...#.", "..#..", ".#...", "#....", "#...."),
    "'": ("..#..", "..#..", ".....", ".....", ".....", ".....", "....."),
    "&": (".##..", "#..#.", "#.#..", ".#...", "#.#.#", "#..#.", ".##.#"),
    "(": ("...#.", "..#..", ".#...", ".#...", ".#...", "..#..", "...#."),
    ")": (".#...", "..#..", "...#.", "...#.", "...#.", "..#..", ".#..."),
    "!": ("..#..", "..#..", "..#..", "..#..", "..#..", ".....", "..#.."),
    "?": (".###.", "#...#", "....#", "...#.", "..#..", ".....", "..#.."),
    "+": (".....", "..#..", "..#..", "#####", "..#..", "..#..", "....."),
    "%": ("##..#", "##..#", "...#.", "..#..", ".#...", "#..##", "#..##"),
    "o": (".....", ".....", ".###.", "#...#", "#...#", "#...#", ".###."),
    "r": (".....", ".....", "#.##.", "##..#", "#....", "#....", "#...."),
    "k": ("#....", "#....", "#..#.", "#.#..", "##...", "#.#..", "#..#."),
    "e": (".....", ".....", ".###.", "#...#", "#####", "#....", ".###."),
    # The rest of "Evil", for the October wordmark.
    "v": (".....", ".....", "#...#", "#...#", "#...#", ".#.#.", "..#.."),
    "i": ("..#..", ".....", ".##..", "..#..", "..#..", "..#..", ".###."),
    "l": (".##..", "..#..", "..#..", "..#..", "..#..", "..#..", ".###."),
}
_GLYPH_W, _GLYPH_H = 5, 7


def pixel_text_width(text: str, pixel: int = 2) -> int:
    """Width the 5x7 face needs for `text` at this pixel size."""
    n = len(text or "")
    return max(0, n * (_GLYPH_W + 1) * pixel - pixel)


def draw_pixel_text(painter, x, y, text: str, pixel: int = 2,
                    color=None, upper: bool = True) -> int:
    """Draw one line of the 5x7 face straight onto a painter and return the
    width used. Widgets use PixelLabel; anything painting its own surface -
    the run overlay HUD - needs the glyphs without a widget wrapped round
    them, and both must come from the same table or the faces drift."""
    text = (text or "").upper() if upper else (text or "")
    if color is not None:
        painter.setBrush(QColor(color))
    painter.setPen(Qt.PenStyle.NoPen)
    x0 = x
    for ch in text:
        rows = _GLYPHS.get(ch)
        if rows:
            for ry, row in enumerate(rows):
                for rx, cell in enumerate(row):
                    if cell == "#":
                        painter.drawRect(QRectF(x0 + rx * pixel,
                                                y + ry * pixel,
                                                pixel, pixel))
        x0 += (_GLYPH_W + 1) * pixel
    return pixel_text_width(text, pixel)


class PixelLabel(QWidget):
    """A line of text rendered in the 5x7 pixel face. Uppercases by default
    (the face is an uppercase one) and falls back to blanks for anything it
    has no glyph for, so it can never raise on unexpected copy."""

    def __init__(self, text: str = "", pixel: int = 2, color: str = "",
                 parent: QWidget | None = None, upper: bool = True,
                 inset: tuple = (0, 0, 0, 0)):
        super().__init__(parent)
        self._pixel = max(1, int(pixel))
        self._color = color
        self._upper = upper
        # (left, top, right, bottom) reserved INSIDE the widget so a
        # stylesheet background or border has somewhere to sit: this widget
        # is fixed to its glyph box, which leaves QSS padding nowhere to go.
        self._inset = tuple(int(v) for v in inset)
        if any(self._inset):
            self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self._text = ""
        self.setText(text)

    def setText(self, text: str):
        self._text = (text or "").upper() if self._upper else (text or "")
        gap = 1
        cols = max(0, len(self._text) * (_GLYPH_W + gap) - gap)
        li, ti, ri, bi = self._inset
        self.setFixedSize(cols * self._pixel + li + ri,
                          _GLYPH_H * self._pixel + ti + bi)
        self.update()

    def text(self) -> str:
        return self._text

    def refresh_theme(self):
        self.update()

    def paintEvent(self, _e):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, False)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(self._color or Colors.TEXT_PRIMARY))
        draw_pixel_text(p, self._inset[0], self._inset[1], self._text,
                        self._pixel, upper=False)
        p.end()


class PixelBlock(QWidget):
    """Multi-line pixel text, wrapped to a maximum width.

    PixelLabel is a single fixed-size line, so anything that must not be
    truncated needs wrapping done here: the face has no font metrics to hand
    to a layout, but its advance is exactly (glyph + gap) * pixel, so the line
    length is a character count."""

    def __init__(self, text: str = "", pixel: int = 2, color: str = "",
                 max_width: int = 0, parent: QWidget | None = None):
        super().__init__(parent)
        self._pixel = max(1, int(pixel))
        self._color = color
        self._max = int(max_width)
        col = QVBoxLayout(self)
        col.setContentsMargins(0, 0, 0, 0)
        col.setSpacing(self._pixel)
        self._col = col
        self._text = ""
        self.setText(text)

    def _per_line(self) -> int:
        advance = (_GLYPH_W + 1) * self._pixel
        if self._max <= 0:
            return 0
        return max(1, (self._max + self._pixel) // advance)

    def _wrap(self, text: str) -> list:
        per = self._per_line()
        if not per:
            return [text]
        out, cur = [], ""
        for word in (text or "").split():
            while len(word) > per:          # longer than a whole line
                out.append(word[:per])
                word = word[per:]
            if not cur:
                cur = word
            elif len(cur) + 1 + len(word) <= per:
                cur += " " + word
            else:
                out.append(cur)
                cur = word
        if cur:
            out.append(cur)
        return out or [""]

    def setText(self, text: str):
        self._text = text or ""
        while self._col.count():
            w = self._col.takeAt(0).widget()
            if w is not None:
                w.setParent(None)
                w.deleteLater()
        for line in self._wrap(self._text):
            lbl = PixelLabel(line, pixel=self._pixel, color=self._color,
                             parent=self)
            lbl.show()
            self._col.addWidget(lbl, 0, Qt.AlignmentFlag.AlignHCenter)

    def text(self) -> str:
        return self._text

    def line_count(self) -> int:
        return self._col.count()

    def level_to(self, lines: int):
        """Centre this block inside a slot `lines` tall. The spare height is
        split above and below rather than all going to one side, so a
        one-line label sits in the middle of a two-line slot instead of
        hanging off its top or bottom edge. Done with margins, not blank
        lines, so an odd remainder can still be halved."""
        per_line = _GLYPH_H * self._pixel + self._pixel
        extra = max(0, lines - self._col.count()) * per_line
        top = extra // 2
        self._col.setContentsMargins(0, top, 0, extra - top)

    def refresh_theme(self):
        self.update()


class PixelWordmark(QWidget):
    """The brand in a pixel font: "Worker" white and "Bee" in the accent, or
    in October "Evil" in red and "Bee" in white."""

    def __init__(self, pixel: int = 3, parent: QWidget | None = None):
        super().__init__(parent)
        self._pixel = pixel
        first, second = seasonal.brand()
        self._text = first + second
        self._split = len(first)
        self._evil = seasonal.is_halloween()
        gap = 1
        cols = len(self._text) * (_GLYPH_W + gap) - gap
        self.setFixedSize(cols * pixel, _GLYPH_H * pixel)

    def refresh_theme(self):
        self.update()

    def paintEvent(self, _e):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, False)
        p.setPen(Qt.PenStyle.NoPen)
        px = self._pixel
        if self._evil:
            first, second = QColor(seasonal.RED), QColor(seasonal.BONE)
        else:
            first = QColor(Colors.TEXT_PRIMARY)
            second = QColor(Colors.ACCENT)
        x0 = 0
        for i, ch in enumerate(self._text):
            rows = _GLYPHS.get(ch)
            col = first if i < self._split else second
            if rows:
                p.setBrush(col)
                for ry, row in enumerate(rows):
                    for rx, cell in enumerate(row):
                        if cell == "#":
                            p.drawRect(QRectF(x0 + rx * px, ry * px, px, px))
            x0 += (_GLYPH_W + 1) * px
        p.end()


__all__ = ["VoxelLogo", "PixelWordmark"]
