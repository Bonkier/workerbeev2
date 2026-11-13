# SPDX-License-Identifier: GPL-3.0-or-later
"""The run sheet of a Basic view preset, opened from its card: the run at a
glance in a ledger of facts, then the owner's words and the roster, each unit with
its card, the requirement on it and the sheet's notes."""

from html import escape

from PySide6.QtCore import QRectF, Qt, Signal
from PySide6.QtGui import QColor, QPainter, QPen, QPixmap
from PySide6.QtWidgets import (
    QFrame, QGridLayout, QHBoxLayout, QLabel, QScrollArea, QVBoxLayout,
    QWidget,
)

from . import giftart
from .dialogs import FramelessDialog
from .grace_info import GRACES
from .theme import Colors, Sizing
from .widgets import FlowLayout, GhostButton, PrimaryButton, _rad, _title_label

_ART = 72


def _rich(text: str) -> str:
    """Sheet text as rich text: a blank line starts a new paragraph, and a
    line that starts with "- " is a bullet line with a hanging indent."""
    out = []
    blocks = [b for b in str(text or "").split("\n\n") if b.strip()]
    for bi, block in enumerate(blocks):
        paras = []
        for ln in (ln.strip() for ln in block.split("\n") if ln.strip()):
            if ln.startswith("- "):
                paras.append(("\u2022 " + escape(ln[2:].strip()), True))
            elif paras and not paras[-1][1]:
                paras[-1] = (paras[-1][0] + " " + escape(ln), False)
            else:
                paras.append((escape(ln), False))
        for pi, (html, bullet) in enumerate(paras):
            gap = 8 if bi < len(blocks) - 1 and pi == len(paras) - 1 else 0
            style = "margin:0 0 %dpx %dpx;" % (gap, 12 if bullet else 0)
            if bullet:
                style += " text-indent:-12px;"
            out.append("<p style=\"%s\">%s</p>" % (style, html))
    return "".join(out)


def _notes_html(text: str) -> str:
    """The sheet's notes on a unit, a line each, led by a small accent
    square rather than a bullet."""
    out = []
    for ln in (ln.strip() for ln in str(text or "").split("\n") if ln.strip()):
        if ln.startswith("- "):
            ln = ln[2:].strip()
        out.append("<p style=\"margin:0 0 2px 11px; text-indent:-11px;\">"
                   "<span style=\"color:%s\">\u25aa</span>&nbsp;%s</p>"
                   % (Colors.ACCENT, escape(ln)))
    return "".join(out)


def _heading(text: str, parent):
    """A section heading in the sheet: the section face, flush with the text
    under it. The page's version keeps room for a band the sheet never
    paints, which would leave the heading a few pixels to the right."""
    try:
        from .skins import is_voxel
        if is_voxel():
            from .voxel import PixelLabel
            lbl = PixelLabel(text, pixel=2, color=Colors.TEXT_SECONDARY,
                             parent=parent, inset=(0, 5, 0, 5))
            lbl.setObjectName("sheetHeading")
            return lbl
    except Exception:
        pass
    return _title_label(text, parent, pixel=2, section=True)


def _team(preset: dict) -> tuple:
    """The run and the team a preset writes to the Custom run teams card."""
    for run, team in (preset.get("teams") or {}).items():
        return str(run), dict(team or {})
    return "", {}


def _tagged(tags: dict) -> list:
    """Each tagged market gift with its tags in the rows' order, a buy with
    its place: [(name, [(key, number), ...]), ...]."""
    from .mirror_dungeon_page import _MARKET_MODE_KEYS
    out = {}
    for key in _MARKET_MODE_KEYS:
        for i, name in enumerate(tags.get(key) or [], 1):
            out.setdefault(str(name), []).append((key, i if key == "buy" else 0))
    return list(out.items())


def _facts(preset: dict) -> list:
    """What the run does, as (label, value) pairs for the ledger: text, or
    a list of the art items a row shows instead (("grace", name),
    ("gift", name), ("pack", floor, name), ("tagged", name, marks))."""
    from .presets import floor_code
    m = preset["mirror"]
    facts = []
    code = floor_code(m)
    if "N" in code and "H" in code:
        detail = "Hard from floor %d" % int(m.get("hard_from_floor"))
    else:
        detail = str(m.get("difficulty") or "Normal")
    facts.append(("Difficulty", "%s \u00b7 %s" % (code, detail)))
    _run, team = _team(preset)
    if team.get("keyword"):
        facts.append(("Team keyword", str(team["keyword"])))
    if team.get("heal"):
        facts.append(("Sinner to heal", str(team["heal"])))
    if team.get("s3_only"):
        facts.append(("Skill 3 only", "On"))
    graces = [name for name, on in (m.get("grace") or {}).items() if on]
    facts.append(("Graces", [("grace", n) for n in graces] if graces else "None"))
    from wbcore.starter_gifts import taken
    starters = taken(str(m.get("starter_gift") or ""),
                     "Star Shower" in graces, "Perfected Possibility" in graces)
    if starters:
        facts.append(("Starting gifts", [("gift", n) for n in starters]))
    search = [str(n) for n in (m.get("gift_search") or [])]
    facts.append(("Gift search", [("gift", n) for n in search] if search else "Off"))
    floors = (m.get("pack_search_cfg") or {}).get("floors") or {}
    packs = [("pack", int(fl), str(cfg.get("pack")))
             for fl, cfg in sorted(floors.items(), key=lambda kv: int(kv[0]))
             if cfg.get("enabled") and cfg.get("pack")]
    facts.append(("Pack search", packs if packs else "Off"))
    tags = None
    for key in ("market_gifts_hollow", "market_gifts_saikai", "market_gifts"):
        if key in m:
            tags = m[key]
            tags = tags() if callable(tags) else tags
            break
    tagged = _tagged(tags or {})
    facts.append(("Market", [("tagged", n, marks) for n, marks in tagged]
                  if tagged else "Default behaviour"))
    return facts


def _gift_path(name: str) -> str:
    """A gift's art: the wiki illustration, else the search thumbnail."""
    path = giftart.art_path(name)
    if path:
        return path
    try:
        from wbcore.gift_catalog import load_catalog
        return (load_catalog().get(name) or {}).get("path") or ""
    except Exception:
        return ""


def _fact_label(text: str, parent) -> QWidget:
    """A ledger row's name: the pixel face on voxel, a step dimmer than the
    headings; small tracked capitals on legacy."""
    try:
        from .skins import is_voxel
        if is_voxel():
            from .voxel import PixelLabel
            lbl = PixelLabel(text, pixel=2, color=Colors.TEXT_TERTIARY,
                             parent=parent)
            lbl.setObjectName("specLabel")
            return lbl
    except Exception:
        pass
    return QLabel(text.upper(), parent, objectName="specLabel")


class _ArtChip(QWidget):
    """Art on a small plate; what it is comes up on hover."""

    _PAD = 3

    def __init__(self, path: str, tip: str, box=(40, 40), parent=None):
        super().__init__(parent)
        self.name = tip
        w, h = box
        pm = QPixmap(path) if path else QPixmap()
        self._pix = (pm.scaled(w - 2 * self._PAD, h - 2 * self._PAD,
                               Qt.AspectRatioMode.KeepAspectRatio,
                               Qt.TransformationMode.SmoothTransformation)
                     if not pm.isNull() else pm)
        self.setFixedSize(w, h)
        self.setToolTip(tip)

    def paintEvent(self, _e):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        p.setPen(QPen(QColor(Colors.BORDER_SUBTLE), 1))
        p.setBrush(QColor(Colors.BG_OVERLAY))
        p.drawRoundedRect(r, _rad(4), _rad(4))
        if not self._pix.isNull():
            p.drawPixmap((self.width() - self._pix.width()) // 2,
                         (self.height() - self._pix.height()) // 2, self._pix)
        p.end()


class _TagMark(QWidget):
    """One of a market gift's tags as its mark alone; the tag's name, and a
    buy's place, come up on hover."""

    SIZE = 16

    def __init__(self, key: str, number: int = 0, parent=None):
        super().__init__(parent)
        from .mirror_dungeon_page import _MARKET_MODES
        self.key = key
        self.number = int(number)
        label = dict(_MARKET_MODES).get(key, key)
        self.setToolTip("%s #%d" % (label, self.number)
                        if key == "buy" and self.number else label)
        self.setFixedSize(self.SIZE, self.SIZE)

    def paintEvent(self, _e):
        from .mirror_dungeon_page import _draw_tag_glyph
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        ink = (Colors.ACCENT if self.key == "buy" and self.number
               else Colors.TEXT_SECONDARY)
        _draw_tag_glyph(p, 1, 1, self.SIZE - 2, self.key, ink, self.number,
                        halo=Colors.BG_BASE)
        p.end()


class _TaggedGift(QWidget):
    """A market gift: its art over the marks of its tags, two to a row so
    the marks stay within the art's width."""

    _ACROSS = 2

    def __init__(self, name: str, marks, parent=None):
        super().__init__(parent)
        self.name = name
        col = QVBoxLayout(self)
        col.setContentsMargins(0, 0, 0, 0)
        col.setSpacing(Sizing.SPACE_XXS)
        self.art = _ArtChip(_gift_path(name), name, parent=self)
        col.addWidget(self.art, 0, Qt.AlignmentFlag.AlignHCenter)
        grid = QGridLayout()
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setSpacing(Sizing.SPACE_XXS)
        self.marks = [_TagMark(key, number, self) for key, number in marks]
        for i, mark in enumerate(self.marks):
            grid.addWidget(mark, i // self._ACROSS, i % self._ACROSS)
        col.addLayout(grid)
        col.setAlignment(grid, Qt.AlignmentFlag.AlignHCenter)


class _FloorPack(QWidget):
    """A floor's pack search: the floor over the pack's card."""

    def __init__(self, floor: int, name: str, parent=None):
        super().__init__(parent)
        self.floor = int(floor)
        self.name = name
        try:
            from wbcore.pack_search_catalog import PACK_SEARCH_KEYS
            key = PACK_SEARCH_KEYS.get(name, name)
        except Exception:
            key = name
        col = QVBoxLayout(self)
        col.setContentsMargins(0, 0, 0, 0)
        col.setSpacing(Sizing.SPACE_XXS)
        col.addWidget(QLabel("F%d" % self.floor, self, objectName="plateNum"),
                      0, Qt.AlignmentFlag.AlignHCenter)
        self.art = _ArtChip(giftart.pack_icon(key), name, (46, 80), self)
        col.addWidget(self.art, 0, Qt.AlignmentFlag.AlignHCenter)


class _ChipRow(QWidget):
    """A fact's art items in a row that wraps when it must; market gifts,
    each a column of art and marks, stand a little further apart."""

    def __init__(self, items, parent=None):
        super().__init__(parent)
        tagged = bool(items) and items[0][0] == "tagged"
        flow = FlowLayout(self, spacing=Sizing.SPACE_SM if tagged else Sizing.SPACE_XS)
        flow.setContentsMargins(0, 0, 0, 0)
        self.chips = []
        for item in items:
            kind = item[0]
            if kind == "grace":
                chip = _ArtChip(giftart.grace_icon(item[1]),
                                (GRACES.get(item[1]) or {}).get("title") or item[1],
                                parent=self)
                chip.name = item[1]
            elif kind == "gift":
                chip = _ArtChip(_gift_path(item[1]), item[1], parent=self)
            elif kind == "pack":
                chip = _FloorPack(item[1], item[2], self)
            else:
                chip = _TaggedGift(item[1], item[2], self)
            flow.addWidget(chip)
            self.chips.append(chip)


class _FactRow:
    """One fact in the ledger: its name for the label column and its value,
    text or a row of art, for the value column."""

    def __init__(self, label: str, value, parent):
        self.label = _fact_label(label, parent)
        self.value = None
        self.chips = []
        if isinstance(value, str):
            self.value = QLabel(value, parent, objectName="specValue")
            self.body = self.value
        else:
            self.body = _ChipRow(value, parent)
            self.chips = self.body.chips


class _Ledger(QWidget):
    """The run's facts as a ledger: one row each, the names in a column at
    the left, a hairline between rows."""

    def __init__(self, facts, parent=None):
        super().__init__(parent)
        self._grid = QGridLayout(self)
        self._grid.setContentsMargins(0, 0, 0, 0)
        self._grid.setHorizontalSpacing(Sizing.SPACE_XL)
        self._grid.setVerticalSpacing(Sizing.SPACE_MD)
        self._grid.setColumnStretch(1, 1)
        self.rows = []
        for i, (label, value) in enumerate(facts):
            row = _FactRow(label, value, self)
            self._grid.addWidget(row.label, i, 0,
                                 Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
            self._grid.addWidget(row.body, i, 1, Qt.AlignmentFlag.AlignVCenter)
            self.rows.append(row)

    def paintEvent(self, _e):
        p = QPainter(self)
        p.setPen(QPen(QColor(Colors.BORDER_SUBTLE), 1))
        for above, below in zip(self.rows, self.rows[1:]):
            floor = max(above.label.geometry().bottom(), above.body.geometry().bottom())
            ceiling = min(below.label.geometry().top(), below.body.geometry().top())
            y = (floor + ceiling) // 2
            p.drawLine(0, y, self.width(), y)
        p.end()


class _SinnerPlate(QFrame):
    """A sinner in the order or the exclusions: the place, then the name."""

    def __init__(self, name: str, number: int = 0, parent=None):
        super().__init__(parent)
        self.setObjectName("sinnerPlate")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.name = name
        self.number = int(number)
        row = QHBoxLayout(self)
        row.setContentsMargins(Sizing.SPACE_SM, Sizing.SPACE_XS,
                               Sizing.SPACE_MD, Sizing.SPACE_XS)
        row.setSpacing(Sizing.SPACE_SM)
        if self.number:
            row.addWidget(QLabel("%02d" % self.number, self, objectName="plateNum"))
        row.addWidget(QLabel(name, self, objectName="sinnerName"))


def _sinner_row(names, numbered: bool, parent) -> tuple:
    """A flow of sinner plates, numbered in order or bare."""
    host = QWidget(parent)
    flow = FlowLayout(host, spacing=Sizing.SPACE_SM)
    plates = []
    for i, name in enumerate(names, 1):
        plate = _SinnerPlate(str(name), i if numbered else 0, host)
        flow.addWidget(plate)
        plates.append(plate)
    return host, plates


class _UnitRow(QWidget):
    """One unit of the roster: its card, its name, the requirement on it
    and the sheet's notes."""

    def __init__(self, pic: dict, parent=None):
        super().__init__(parent)
        from .giftart import preset_portrait
        self.stem = pic["stem"]
        row = QHBoxLayout(self)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(Sizing.SPACE_MD)
        self.art = QLabel(self)
        self.art.setFixedSize(_ART, _ART)
        self.art.setAlignment(Qt.AlignmentFlag.AlignCenter)
        pm = QPixmap(preset_portrait(self.stem))
        if not pm.isNull():
            self.art.setPixmap(pm.scaled(
                _ART, _ART, Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation))
        row.addWidget(self.art, 0, Qt.AlignmentFlag.AlignTop)
        col = QVBoxLayout()
        col.setSpacing(Sizing.SPACE_XS)
        self.caption = QLabel(pic["name"], self, objectName="unitName")
        self.caption.setWordWrap(True)
        col.addWidget(self.caption)
        self.req = QLabel(pic.get("req", ""), self, objectName="unitReq")
        self.req.setVisible(bool(pic.get("req")))
        col.addWidget(self.req, 0, Qt.AlignmentFlag.AlignLeft)
        self.notes = QLabel(self, objectName="unitNote")
        self.notes.setTextFormat(Qt.TextFormat.RichText)
        self.notes.setWordWrap(True)
        self.notes.setText(_notes_html(pic.get("notes", "")))
        self.notes.setVisible(bool(pic.get("notes")))
        col.addWidget(self.notes)
        col.addStretch(1)
        row.addLayout(col, 1)


class PresetDetailsDialog(FramelessDialog):
    """A preset's whole sheet in a window of its own, with Apply config at
    the foot so the run can be taken from here as well."""

    apply_requested = Signal(str)

    def __init__(self, preset: dict, parent=None):
        super().__init__("%s run sheet" % preset["title"], parent)
        self.key = preset["key"]
        self.setMinimumWidth(640)
        self.resize(840, 700)

        content = QWidget()
        content.setStyleSheet("background: transparent;")
        col = QVBoxLayout(content)
        col.setContentsMargins(0, 0, Sizing.SPACE_MD, 0)
        col.setSpacing(Sizing.SPACE_LG)

        self.lede = QLabel(content, objectName="ledeText")
        self.lede.setTextFormat(Qt.TextFormat.RichText)
        self.lede.setWordWrap(True)
        self.lede.setText(_rich(preset["tagline"]))
        col.addWidget(self.lede)

        ledger = _Ledger(_facts(preset), content)
        self.facts = ledger.rows
        col.addWidget(ledger)
        col.addSpacing(Sizing.SPACE_SM)

        self.headers = []
        self.units = []
        self.order = []
        self.excluded = []
        run, team = _team(preset)
        note = ("What Apply config puts on the Custom run teams card for %s. "
                "Change any of it there." % run)
        for label, names, numbered in (("SINNER ORDER", team.get("order"), True),
                                       ("SINNER SWAP EXCLUSION", team.get("exclude"), False)):
            if not names:
                continue
            head = _heading(label, content)
            self.headers.append(head)
            col.addWidget(head, 0, Qt.AlignmentFlag.AlignLeft)
            if note:
                body = QLabel(note, content, objectName="sectionText")
                body.setWordWrap(True)
                col.addWidget(body)
                note = ""
            host, plates = _sinner_row(names, numbered, content)
            col.addWidget(host)
            if numbered:
                self.order = plates
            else:
                self.excluded = plates
        for label, text, pics in preset["needs"]:
            head = _heading(label.upper(), content)
            self.headers.append(head)
            col.addWidget(head, 0, Qt.AlignmentFlag.AlignLeft)
            if text:
                body = QLabel(content, objectName="sectionText")
                body.setTextFormat(Qt.TextFormat.RichText)
                body.setWordWrap(True)
                body.setText(_rich(text))
                col.addWidget(body)
            if not pics:
                continue
            grid = QGridLayout()
            grid.setHorizontalSpacing(Sizing.SPACE_XL)
            grid.setVerticalSpacing(Sizing.SPACE_MD)
            for i, pic in enumerate(pics):
                unit = _UnitRow(pic, content)
                grid.addWidget(unit, i // 2, i % 2)
                self.units.append(unit)
            grid.setColumnStretch(0, 1)
            grid.setColumnStretch(1, 1)
            col.addLayout(grid)
        col.addStretch(1)

        scroll = QScrollArea(self._frame)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setStyleSheet("QScrollArea { background: transparent; }")
        scroll.setWidget(content)
        self.body.addWidget(scroll, stretch=1)

        row = QHBoxLayout()
        row.setSpacing(Sizing.SPACE_SM)
        close = GhostButton("Close", self._frame)
        close.clicked.connect(self.reject)
        row.addWidget(close)
        row.addStretch(1)
        self.apply = PrimaryButton("Apply config", self._frame)
        self.apply.setDefault(True)
        self.apply.clicked.connect(self._on_apply)
        row.addWidget(self.apply)
        self.body.addLayout(row)

    def _on_apply(self):
        self.accept()                 # the prompt that follows stands alone
        self.apply_requested.emit(self.key)
