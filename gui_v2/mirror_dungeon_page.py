# SPDX-License-Identifier: GPL-3.0-or-later
"""Mirror Dungeon page - the full run-config surface."""


from PySide6.QtCore import (
    Property, QEasingCurve, QEvent, QMimeData, QPoint, QPointF,
    QPropertyAnimation, QRect, QRectF, QSize, Qt, QTimer, Signal,
)
from PySide6.QtGui import (
    QColor, QCursor, QDrag, QFont, QFontMetrics, QIcon, QPainter,
    QPainterPath, QPen, QPixmap,
)
from PySide6.QtWidgets import (
    QAbstractButton, QApplication, QCompleter, QDialog, QDialogButtonBox,
    QFrame, QGridLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QScrollArea, QSizePolicy, QSpinBox, QStackedWidget,
    QVBoxLayout, QWidget,
)

from .run_config import (HOLLOW_GRACE_SEED, HOLLOW_LABEL, RUN_SEARCH_GIFTS,
                         SAIKAI_LABEL, floors_phrase, skip_floor_set)
from .grace_info import GRACES

from .settings import load_section, save_section
from . import stats
from .copy import MD_PRESET_APPLIED_TEXT, MD_PRESET_APPLIED_TITLE
from . import seasonal
from .theme import Colors, Fonts, Motion, Sizing
from .widgets import (
    AnimatedStack, Card, FloorPacks, FlowLayout,
    GhostButton, HRule, IconlessTabBar, LinkButton, OrderedList,
    CollapsibleSection, PageHeader, PrimaryButton, Segmented, SettingRow,
    StackPage, Toggle, _rad, _title_label, page_fill_qss,
    ui_font,
)
from .dialogs import ask_choice
from .preset_details import PresetDetailsDialog

_SECTION = "mirror"
# Which config the settings are: the saved config last loaded or saved, by
# name and by a fingerprint of the settings it held.
_IDENTITY_SECTION = "md_config"
# Lists whose order is the setting; every other list compares as a set.
_ORDERED_KEYS = ("buy", "card")
_EMPTY = (None, False, 0, "", [], {})


def _norm(value, key=""):
    """A setting as the identity check compares it: dict keys as strings,
    the empty and switched-off entries dropped, lists sorted unless their
    order is the setting. Empty comes back as None, whatever it was."""
    if isinstance(value, dict):
        out = {}
        for k, v in value.items():
            nv = _norm(v, str(k))
            if nv is not None:
                out[str(k)] = nv
        value = out
    elif isinstance(value, (list, tuple)):
        items = [_norm(v, key) for v in value]
        value = items if key in _ORDERED_KEYS else sorted(items, key=repr)
    return None if value in _EMPTY else value
_VIEW_SECTION = "md_view"

# Width cap on a behaviour row, so every switch lands on the same vertical
# rail rather than the panel's right edge.
_BEHAVIOUR_RAIL = 340

# Statuses with a confirmed Mirror Dungeon team-select icon ({status}_team).


_GIFT_TIER_ROMAN = {1: "I", 2: "II", 3: "III", 4: "IV", 5: "V", 6: "EX"}

# Full-resolution gift illustrations (tools/fetch_gift_art.py). The bundled
# ImageAssets are tight in-game crops sized for template matching, which look
# chopped in the pickers; fall back to them when art is missing.
def _gift_art(name: str, info: dict) -> str:
    """Picker image for a gift: the full wiki illustration when present, else
    the cropped template the bot matches with (which carries the game's dark
    inventory frame, so it reads as a black box next to the clean art)."""
    from .giftart import art_path
    return art_path(name) or info.get("path") or ""
# Keyword display order within each tier (status order, keywordless last).
_GIFT_KW_ORDER = (
    "burn", "bleed", "tremor", "rupture", "sinking", "poise",
    "charge", "slash", "pierce", "blunt", "keywordless",
)


class _GiftTile(QAbstractButton):
    """Clickable EGO-gift thumbnail; draws an accent border + check when picked."""

    _SIZE = 58

    def __init__(self, name, info, parent=None):
        super().__init__(parent)
        self._name = name
        self._selected = False
        self._hover = False
        self.setFixedSize(self._SIZE + 8, self._SIZE + 8)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setToolTip(
            f"{name}\n{info['keyword'].title()}  -  Tier "
            f"{_GIFT_TIER_ROMAN.get(info['tier'], '?')}")
        pm = QPixmap(_gift_art(name, info))
        self._pix = (pm.scaled(self._SIZE, self._SIZE,
                               Qt.AspectRatioMode.KeepAspectRatio,
                               Qt.TransformationMode.SmoothTransformation)
                     if not pm.isNull() else pm)

    def set_selected(self, on):
        on = bool(on)
        if on != self._selected:
            self._selected = on
            self.update()

    def enterEvent(self, e):
        self._hover = True
        self.update()
        super().enterEvent(e)

    def leaveEvent(self, e):
        self._hover = False
        self.update()
        super().leaveEvent(e)

    def paintEvent(self, _e):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = QRectF(self.rect()).adjusted(1, 1, -1, -1)
        # The thumbnail carries its own in-game frame, so no flat fill - only a
        # soft backing on hover, otherwise it reads as a grey box.
        if self._hover:
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(Colors.BG_OVERLAY))
            p.drawRoundedRect(r, _rad(8), _rad(8))
        if not self._pix.isNull():
            x = int((self.width() - self._pix.width()) / 2)
            y = int((self.height() - self._pix.height()) / 2)
            p.drawPixmap(x, y, self._pix)
        if self._selected:
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.setPen(QPen(QColor(Colors.ACCENT), 2))
            p.drawRoundedRect(r, _rad(8), _rad(8))
            self._draw_badge(p)
        elif self._hover:
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.setPen(QPen(QColor(Colors.BORDER_STRONG), 1))
            p.drawRoundedRect(r, _rad(8), _rad(8))
        p.end()

    def _draw_badge(self, p):
        b = 16
        cx, cy = self.width() - b / 2.0 - 3, b / 2.0 + 3
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(Colors.ACCENT))
        if _rad(b):
            p.drawEllipse(int(cx - b / 2), int(cy - b / 2), b, b)
        else:
            p.drawRect(int(cx - b / 2), int(cy - b / 2), b, b)
        p.setPen(QPen(QColor("#0e0e10"), 2))
        p.drawLine(int(cx - 4), int(cy + 1), int(cx - 1), int(cy + 3))
        p.drawLine(int(cx - 1), int(cy + 3), int(cx + 4), int(cy - 3))


class _PickChip(QAbstractButton):
    """A picked gift above the search: its art, its name and the x that
    unpicks it."""

    _H = 32
    _ART = 24
    _PAD = 6
    _MARK = 12

    def __init__(self, name, pix, parent=None):
        super().__init__(parent)
        self._name = name
        self._hover = False
        self._font = ui_font(Fonts.SIZE_SM, QFont.Weight.Medium)
        self._pix = (pix.scaled(self._ART, self._ART,
                                Qt.AspectRatioMode.KeepAspectRatio,
                                Qt.TransformationMode.SmoothTransformation)
                     if pix is not None and not pix.isNull() else QPixmap())
        text_w = QFontMetrics(self._font).horizontalAdvance(name)
        self.setFixedSize(self._PAD * 4 + self._ART + text_w + self._MARK, self._H)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setToolTip("%s\nClick to remove" % name)

    def name(self):
        return self._name

    def enterEvent(self, e):
        self._hover = True
        self.update()
        super().enterEvent(e)

    def leaveEvent(self, e):
        self._hover = False
        self.update()
        super().leaveEvent(e)

    def paintEvent(self, _e):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        edge = Colors.BORDER_STRONG if self._hover else Colors.BORDER_SUBTLE
        p.setPen(QPen(QColor(edge), 1))
        p.setBrush(QColor(Colors.BG_OVERLAY))
        p.drawRoundedRect(r, _rad(4), _rad(4))
        x = self._PAD
        if not self._pix.isNull():
            p.drawPixmap(x + (self._ART - self._pix.width()) // 2,
                         (self.height() - self._pix.height()) // 2, self._pix)
        x += self._ART + self._PAD
        p.setFont(self._font)
        p.setPen(QColor(Colors.TEXT_PRIMARY))
        p.drawText(QRect(x, 0, self.width() - x - self._MARK - self._PAD * 2,
                         self.height()),
                   int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter),
                   self._name)
        mx = self.width() - self._PAD - self._MARK
        my = (self.height() - self._MARK) // 2
        p.setPen(QPen(QColor(Colors.TEXT_PRIMARY if self._hover
                             else Colors.TEXT_TERTIARY), 1.5))
        p.drawLine(mx + 2, my + 2, mx + self._MARK - 2, my + self._MARK - 2)
        p.drawLine(mx + 2, my + self._MARK - 2, mx + self._MARK - 2, my + 2)
        p.end()


class _KeywordTab(QAbstractButton):
    """Keyword filter tab (icon + name), mirroring the in-game gift-search tabs."""

    def __init__(self, keyword, icon_path, parent=None):
        super().__init__(parent)
        self._kw = keyword
        self._hover = False
        self.setCheckable(True)
        self.setAutoExclusive(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setToolTip(keyword.title())
        self.setFixedSize(64, 60)
        # Prefer the wiki status icon: the bundled tab crop has the keyword
        # printed inside it, which doubled up with this tab's own label.
        from .giftart import keyword_icon
        # No bundled-crop fallback: those have the keyword printed inside them,
        # so a tab without a wiki icon reads better as a plain text tab.
        src = keyword_icon(keyword)
        pm = QPixmap(src) if src else QPixmap()
        self._pix = (pm.scaled(30, 30, Qt.AspectRatioMode.KeepAspectRatio,
                               Qt.TransformationMode.SmoothTransformation)
                     if not pm.isNull() else pm)

    def enterEvent(self, e):
        self._hover = True
        self.update()
        super().enterEvent(e)

    def leaveEvent(self, e):
        self._hover = False
        self.update()
        super().leaveEvent(e)

    def paintEvent(self, _e):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = QRectF(self.rect()).adjusted(1, 1, -1, -1)
        checked = self.isChecked()
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(Colors.BG_OVERLAY if (checked or self._hover)
                          else Colors.BG_RAISED))
        p.drawRoundedRect(r, _rad(8), _rad(8))
        if not self._pix.isNull():
            p.drawPixmap(int((self.width() - self._pix.width()) / 2), 7, self._pix)
        f = QFont(self.font())
        f.setPointSizeF(7.5)
        p.setFont(f)
        p.setPen(QColor(Colors.TEXT_PRIMARY if checked else Colors.TEXT_TERTIARY))
        # Iconless tabs centre their label instead of leaving a gap above it.
        label = (QRect(2, 40, self.width() - 4, 16) if not self._pix.isNull()
                 else QRect(2, 0, self.width() - 4, self.height()))
        align = (Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop
                 if not self._pix.isNull()
                 else Qt.AlignmentFlag.AlignCenter)
        p.drawText(label, int(align), self._kw.title())
        if checked:
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.setPen(QPen(QColor(Colors.ACCENT), 2))
            p.drawRoundedRect(r, _rad(8), _rad(8))
        p.end()


class _GraceCard(QAbstractButton):
    """One Grace of the Sisyphean Star card: the wiki icon, the in-game title
    and the starlight cost, with the + and ++ buttons under them like the
    in-game card. The state is the BUFF value: 0 skip, 1 take, 2 take at +,
    3 take at ++."""

    state_changed = Signal(str, int)
    _ICON = 40
    _LEVELS = ((2, "+"), (3, "++"))

    def __init__(self, name: str, parent=None):
        super().__init__(parent)
        self._name = name
        self._info = GRACES.get(name) or {"title": name, "cost": 0,
                                          "effects": ((), (), ())}
        self._state = 0
        self._hover = False
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setSizePolicy(QSizePolicy.Policy.Expanding,
                           QSizePolicy.Policy.Fixed)
        self.setMinimumWidth(96)
        self.setFixedHeight(150)
        from .giftart import grace_icon, reward_icon
        pm = QPixmap(grace_icon(name))
        self._pix = (pm.scaled(self._ICON, self._ICON,
                               Qt.AspectRatioMode.KeepAspectRatio,
                               Qt.TransformationMode.SmoothTransformation)
                     if not pm.isNull() else pm)
        star = QPixmap(reward_icon("Starlight"))
        self._star = (star.scaled(12, 12, Qt.AspectRatioMode.KeepAspectRatio,
                                  Qt.TransformationMode.SmoothTransformation)
                      if not star.isNull() else star)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(8, 112, 8, 8)
        lay.setSpacing(0)
        row = QHBoxLayout()
        row.setSpacing(4)
        self._levels = {}
        for level, text in self._LEVELS:
            btn = QPushButton(text, self, objectName="graceLevel")
            btn.setCheckable(True)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            btn.clicked.connect(lambda _c=False, lv=level: self._level(lv))
            row.addWidget(btn, 1)
            self._levels[level] = btn
        lay.addLayout(row)
        self.clicked.connect(self._toggle)
        self._sync()

    def name(self) -> str:
        return self._name

    def state(self) -> int:
        return self._state

    def set_state(self, idx: int):
        if 0 <= idx <= 3:
            self._state = int(idx)
            self._sync()

    def _toggle(self):
        self._change(0 if self._state else 1)

    def _level(self, level: int):
        self._change(1 if self._state == level else level)

    def _change(self, idx: int):
        if idx != self._state:
            self._state = idx
            self._sync()
            self.state_changed.emit(self._name, idx)

    def _sync(self):
        for level, btn in self._levels.items():
            btn.setChecked(self._state == level)
        self.setToolTip(self._tooltip())
        self.update()

    def _tooltip(self) -> str:
        info = self._info
        cost = int(info["cost"])
        tier = max(0, self._state - 1)
        effects = info["effects"][tier] if tier < len(info["effects"]) else ()
        lines = ["<b>%s</b>" % info["title"],
                 "%d starlight, %d at +, %d at ++" % (cost, cost * 2, cost * 3),
                 "", "<b>%s</b>" % ("Base", "+", "++")[tier]]
        lines += ["\u00b7 " + e for e in effects]
        return "<br>".join(lines)

    def enterEvent(self, e):
        self._hover = True
        self.update()
        super().enterEvent(e)

    def leaveEvent(self, e):
        self._hover = False
        self.update()
        super().leaveEvent(e)

    def paintEvent(self, _e):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        on = self._state > 0
        bg = QColor(Colors.BG_OVERLAY if (on or self._hover)
                    else Colors.BG_RAISED)
        if self._hover:
            bg = bg.lighter(112)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(bg)
        p.drawRoundedRect(r, _rad(8), _rad(8))
        line = (Colors.ACCENT if on else
                Colors.BORDER_STRONG if self._hover else Colors.BORDER_SUBTLE)
        p.setPen(QPen(QColor(line), 1.5 if on else 1.0))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawRoundedRect(r, _rad(8), _rad(8))
        f = QFont(self.font())
        f.setPointSizeF(8.5)
        f.setWeight(QFont.Weight.DemiBold)
        p.setFont(f)
        cost = str(int(self._info["cost"]) * max(1, self._state))
        tw = p.fontMetrics().horizontalAdvance(cost)
        x = self.width() - 10 - tw
        p.setPen(QColor(Colors.ACCENT if on else Colors.TEXT_TERTIARY))
        p.drawText(QRect(x, 7, tw + 2, 14),
                   int(Qt.AlignmentFlag.AlignRight
                       | Qt.AlignmentFlag.AlignVCenter), cost)
        p.setOpacity(1.0 if on else 0.45)
        if not self._star.isNull():
            p.drawPixmap(x - 15, 8, self._star)
        if not self._pix.isNull():
            p.drawPixmap(int((self.width() - self._pix.width()) / 2), 22,
                         self._pix)
        p.setOpacity(1.0)
        f.setPointSizeF(9.5)
        p.setFont(f)
        p.setPen(QColor(Colors.TEXT_PRIMARY if on else Colors.TEXT_SECONDARY))
        p.drawText(QRect(6, 66, self.width() - 12, 40),
                   int(Qt.AlignmentFlag.AlignHCenter
                       | Qt.AlignmentFlag.AlignVCenter
                       | Qt.TextFlag.TextWordWrap), self._info["title"])
        p.end()


class _GiftGallery(QWidget):
    """In-game-style EGO gift picker: keyword tabs, the active keyword's gifts
    grouped by tier, pick up to `max_picks`, search across all keywords, reset.
    Emits `changed` on any selection change."""

    changed = Signal()

    def __init__(self, max_picks=3, parent=None):
        super().__init__(parent)
        self._max = max_picks
        self._order = []          # selected names, in pick order
        self._tiles = {}          # name -> _GiftTile
        self._panels = {}         # keyword -> panel widget
        self._sections = {}       # keyword -> [(tier, tier_hdr, holder, [names])]
        self._kw_header = {}      # keyword -> label (shown only while searching)
        self._tabs = {}           # keyword -> _KeywordTab
        try:
            from wbcore.gift_catalog import load_catalog, tab_path
            self._cat = load_catalog()
        except Exception:
            self._cat, tab_path = {}, (lambda *_a: None)

        present = [kw for kw in _GIFT_KW_ORDER
                   if any(v.get("keyword") == kw for v in self._cat.values())]
        self._active_kw = present[0] if present else None

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(Sizing.SPACE_SM)

        # Keyword tab bar (icons are the in-game keyword tabs).
        tabholder = QWidget(self)
        tabrow = FlowLayout(tabholder, spacing=4)
        for kw in present:
            tab = _KeywordTab(kw, tab_path(kw), tabholder)
            tab.clicked.connect(lambda _=False, k=kw: self._on_tab(k))
            self._tabs[kw] = tab
            tabrow.addWidget(tab)
        outer.addWidget(tabholder)

        # Search + count + reset.
        head = QHBoxLayout()
        head.setSpacing(Sizing.SPACE_MD)
        self._search = QLineEdit(self)
        self._search.setObjectName("textField")
        self._search.setPlaceholderText("Search all EGO gifts by name...")
        self._search.setClearButtonEnabled(True)
        self._search.textChanged.connect(self._refresh_view)
        head.addWidget(self._search, 1)
        self._count = QLabel(self, objectName="inlineMeta")
        head.addWidget(self._count)
        self._reset_btn = GhostButton("Reset", self)
        self._reset_btn.clicked.connect(self.reset)
        head.addWidget(self._reset_btn)
        outer.addLayout(head)

        # Selected chips.
        self._chips_holder = QWidget(self)
        self._chips = QHBoxLayout(self._chips_holder)
        self._chips.setContentsMargins(0, 0, 0, 0)
        self._chips.setSpacing(Sizing.SPACE_XS)
        outer.addWidget(self._chips_holder)

        # Per-keyword panels: that keyword's gifts grouped by tier (III..I).
        sa = QScrollArea(self)
        sa.setObjectName("pageScroll")     # transparent bg, matches the page
        sa.setWidgetResizable(True)
        sa.setFrameShape(QScrollArea.Shape.NoFrame)
        sa.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        inner = QWidget()
        body = QVBoxLayout(inner)
        body.setContentsMargins(0, 0, 0, Sizing.SPACE_MD)
        body.setSpacing(Sizing.SPACE_SM)
        for kw in present:
            panel = QWidget(inner)
            pcol = QVBoxLayout(panel)
            pcol.setContentsMargins(0, 0, 0, 0)
            pcol.setSpacing(Sizing.SPACE_SM)
            kwhdr = QLabel(kw.title(), panel, objectName="sectionLabel")
            pcol.addWidget(kwhdr)
            self._kw_header[kw] = kwhdr
            secs = []
            for tier in (3, 2, 1):
                names = sorted(
                    [n for n, v in self._cat.items()
                     if v.get("keyword") == kw and v.get("tier") == tier],
                    key=lambda n: n.lower())
                if not names:
                    continue
                thdr = _title_label(f"Tier {_GIFT_TIER_ROMAN[tier]}", panel,
                                    pixel=2, section=True)
                pcol.addWidget(thdr)
                holder = QWidget(panel)
                flow = FlowLayout(holder, spacing=6)
                for n in names:
                    tile = _GiftTile(n, self._cat[n], holder)
                    tile.clicked.connect(lambda _=False, nm=n: self._toggle(nm))
                    self._tiles[n] = tile
                    flow.addWidget(tile)
                pcol.addWidget(holder)
                secs.append((tier, thdr, holder, names))
            self._panels[kw] = panel
            self._sections[kw] = secs
            body.addWidget(panel)
        body.addStretch(1)
        sa.setWidget(inner)
        outer.addWidget(sa, 1)

        if self._active_kw is not None:
            self._tabs[self._active_kw].setChecked(True)
        self._refresh()
        self._refresh_view()

    def _on_tab(self, kw):
        self._active_kw = kw
        self._tabs[kw].setChecked(True)
        if self._search.text():
            self._search.blockSignals(True)
            self._search.clear()
            self._search.blockSignals(False)
        self._refresh_view()

    def _toggle(self, name):
        if name in self._order:
            self._order.remove(name)
        elif len(self._order) < self._max:
            self._order.append(name)
        else:
            return
        self._refresh()
        self.changed.emit()

    def reset(self):
        if not self._order:
            return
        self._order = []
        self._refresh()
        self.changed.emit()

    def selected(self):
        return list(self._order)

    def set_selected(self, names):
        order = []
        for n in (names or []):
            if n in self._tiles and n not in order and len(order) < self._max:
                order.append(n)
        self._order = order
        self._refresh()

    def _refresh(self):
        for n, tile in self._tiles.items():
            tile.set_selected(n in self._order)
        self._count.setText(f"{len(self._order)} / {self._max} selected")
        self._reset_btn.setEnabled(bool(self._order))
        self._rebuild_chips()

    def _rebuild_chips(self):
        while self._chips.count():
            it = self._chips.takeAt(0)
            w = it.widget() if it else None
            if w is not None:
                w.setParent(None)
                w.deleteLater()
        for name in self._order:
            chip = _PickChip(name, QPixmap(_gift_art(name, self._cat.get(name) or {})),
                             self._chips_holder)
            chip.clicked.connect(lambda _=False, nm=name: self._toggle(nm))
            self._chips.addWidget(chip)
        self._chips.addStretch(1)
        self._chips_holder.setVisible(bool(self._order))

    def _refresh_view(self, *_):
        """Browse (active keyword only) when the search box is empty; otherwise
        show every gift matching the query across all keywords."""
        q = self._search.text().strip().lower()
        searching = bool(q)
        for kw, panel in self._panels.items():
            if searching:
                p_any = False
                for _tier, thdr, holder, names in self._sections[kw]:
                    t_any = False
                    for n in names:
                        vis = q in n.lower()
                        self._tiles[n].setVisible(vis)
                        t_any = t_any or vis
                    thdr.setVisible(t_any)
                    holder.setVisible(t_any)
                    p_any = p_any or t_any
                self._kw_header[kw].setVisible(p_any)
                panel.setVisible(p_any)
            else:
                active = (kw == self._active_kw)
                panel.setVisible(active)
                self._kw_header[kw].setVisible(False)
                for _tier, thdr, holder, names in self._sections[kw]:
                    thdr.setVisible(active)
                    holder.setVisible(active)
                    if active:
                        for n in names:
                            self._tiles[n].setVisible(True)


# The tags a gift can carry, in the order its popover and the rows list them.
_MARKET_MODES = (
    ("keep_fuse", "Keep · no fuse"),
    ("keep_sell", "Keep · no sell"),
    ("sell", "Sell"),
    ("buy", "Buy priority"),
    ("fuse", "Fuse target"),
    ("enhance1", "Enhance once"),
    ("enhance2", "Enhance twice"),
)
_MARKET_MODE_KEYS = tuple(k for k, _label in _MARKET_MODES)
_MARKET_SLOTS = ("normal", "saikai", "hollow")

# The shop steps, by the behaviour key that skips each one. Shown as what
# the macro does, stored the way the backend has always read them.
_SHOP_STEPS = (
    ("skip_restshop", "Visit the rest shop"),
    ("skip_ego_check", "Check owned gifts"),
    ("skip_ego_fusion", "Fuse gifts"),
    ("skip_ego_enhancing", "Enhance gifts"),
    ("skip_ego_buying", "Buy gifts"),
    ("skip_sinner_healing", "Heal sinners"),
)
_SHOP_STEP_KEYS = tuple(k for k, _t in _SHOP_STEPS)


def _clean_market_floors(raw) -> dict:
    """{slot: {floor: {"tags": {...}, "steps": {...}}}} from a saved
    market_floors, keeping only floors 1..5 with something set."""
    out = {slot: {} for slot in _MARKET_SLOTS}
    if not isinstance(raw, dict):
        return out
    for slot, floors in raw.items():
        if slot not in out or not isinstance(floors, dict):
            continue
        for key, ent in floors.items():
            try:
                fl = int(key)
            except (TypeError, ValueError):
                continue
            if not 1 <= fl <= 5 or not isinstance(ent, dict):
                continue
            clean = {}
            tags = ent.get("tags")
            if isinstance(tags, dict) and any(tags.get(m) for m in _MARKET_MODE_KEYS):
                clean["tags"] = {m: [n for n in (tags.get(m) or [])
                                     if isinstance(n, str)]
                                 for m in _MARKET_MODE_KEYS}
            steps = ent.get("steps")
            if isinstance(steps, dict):
                picked = {k: v for k, v in steps.items()
                          if k in _SHOP_STEP_KEYS and isinstance(v, bool)}
                if picked:
                    clean["steps"] = picked
            if clean:
                out[slot][fl] = clean
    return out


_TAG_GLYPH = 16          # the mark a tag puts on its row head and check row


def _draw_tag_glyph(p, x, y, size, key, color, number=0, halo=None):
    """One tag's mark in a `size` square at (x, y), told by shape alone:
    two squares merging into one for a fuse and the cost coin for a sale,
    each struck through for the Keep that forbids it, a price tag for a buy
    (its place in the order once it has one) and + or ++ for the upties.
    One colour: the gift's own art carries the colour. `halo` is the plate
    the mark sits on, so the stroke of a Keep cuts through its glyph."""
    p.save()
    p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    s = float(size)
    col = QColor(color)
    pen = QPen(col, max(1.3, s / 11.0))
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    p.setPen(pen)
    p.setBrush(Qt.BrushStyle.NoBrush)
    cx, cy = x + s / 2, y + s / 2
    if key in ("fuse", "keep_fuse"):
        a = s * 0.32
        p.drawRect(QRectF(x + s * 0.10, y + s * 0.56, a, a))
        p.drawRect(QRectF(x + s * 0.58, y + s * 0.56, a, a))
        p.setBrush(col)
        p.drawRect(QRectF(cx - a / 2, y + s * 0.10, a, a))
    elif key in ("sell", "keep_sell"):
        r = s * 0.36
        p.drawEllipse(QRectF(cx - r, cy - r, 2 * r, 2 * r))
        d = s * 0.15
        gem = QPainterPath()
        gem.moveTo(cx, cy - d)
        gem.lineTo(cx + d, cy)
        gem.lineTo(cx, cy + d)
        gem.lineTo(cx - d, cy)
        gem.closeSubpath()
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(col)
        p.drawPath(gem)
        p.setPen(pen)
    elif key == "buy" and number:
        p.setFont(ui_font(max(6, int(round(s * 0.5))), QFont.Weight.Bold))
        p.drawText(QRectF(x, y, s, s), int(Qt.AlignmentFlag.AlignCenter),
                   str(number))
    elif key == "buy":
        tag = QPainterPath()
        tag.moveTo(x + s * 0.14, y + s * 0.14)
        tag.lineTo(x + s * 0.54, y + s * 0.14)
        tag.lineTo(x + s * 0.86, y + s * 0.46)
        tag.lineTo(x + s * 0.46, y + s * 0.86)
        tag.lineTo(x + s * 0.14, y + s * 0.54)
        tag.closeSubpath()
        p.drawPath(tag)
        p.setBrush(col)
        p.drawEllipse(QPointF(x + s * 0.32, y + s * 0.32), s * 0.07, s * 0.07)
    elif key in ("enhance1", "enhance2"):
        once = key == "enhance1"
        p.setFont(ui_font(max(6, int(round(s * (0.62 if once else 0.5)))),
                          QFont.Weight.Bold))
        p.drawText(QRectF(x, y, s, s), int(Qt.AlignmentFlag.AlignCenter),
                   "+" if once else "++")
    if key in ("keep_fuse", "keep_sell"):
        a = QPointF(x + s * 0.14, y + s * 0.86)
        b = QPointF(x + s * 0.86, y + s * 0.14)
        if halo is not None:
            p.setPen(QPen(QColor(halo), pen.widthF() + 2.4,
                          Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
            p.drawLine(a, b)
        p.setPen(QPen(col, pen.widthF() + 0.3, Qt.PenStyle.SolidLine,
                      Qt.PenCapStyle.RoundCap))
        p.drawLine(a, b)
    p.restore()


def _draw_tag_plate(p, x, y, size, key, number=0):
    """A tag's mark on a small dark plate, as a chip wears a buy's place."""
    p.save()
    p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    p.setPen(QPen(QColor(Colors.BORDER_STRONG), 1))
    p.setBrush(QColor(Colors.BG_BASE))
    p.drawRoundedRect(QRectF(x + 0.5, y + 0.5, size - 1, size - 1),
                      _rad(3), _rad(3))
    p.restore()
    ink = Colors.ACCENT if key == "buy" and number else Colors.TEXT_PRIMARY
    _draw_tag_glyph(p, x + 2, y + 2, size - 4, key, ink, number,
                    halo=Colors.BG_BASE)


def _tag_label_font():
    """Small tracked capitals for the row heads."""
    f = ui_font(Fonts.SIZE_XS, QFont.Weight.DemiBold)
    f.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, 1.1)
    return f


class _TagRowHead(QWidget):
    """A tag's name at the head of its row: its mark, then the name in small
    tracked capitals, every head as wide as the longest of the seven so the
    rows line up and none is cut short."""

    _GAP = 8

    def __init__(self, key, label, parent=None):
        super().__init__(parent)
        self._key = key
        self._label = label.upper()
        self._font = _tag_label_font()
        fm = QFontMetrics(self._font)
        widest = max(fm.horizontalAdvance(lbl.upper()) for _k, lbl in _MARKET_MODES)
        self.setFixedSize(_TAG_GLYPH + self._GAP + widest + 8, _TagGiftChip.SIZE)
        self.setToolTip(label)

    def key(self):
        return self._key

    def paintEvent(self, _e):
        p = QPainter(self)
        gy = (self.height() - _TAG_GLYPH) // 2
        _draw_tag_glyph(p, 0, gy, _TAG_GLYPH, self._key, Colors.TEXT_SECONDARY)
        p.setFont(self._font)
        p.setPen(QColor(Colors.TEXT_SECONDARY))
        tx = _TAG_GLYPH + self._GAP
        p.drawText(QRect(tx, 0, self.width() - tx, self.height()),
                   int(Qt.AlignmentFlag.AlignLeft
                       | Qt.AlignmentFlag.AlignVCenter), self._label)
        p.end()


class _TagGiftChip(QAbstractButton):
    """A gift in a tag's row, shown as its art: hover it for the name and
    the x that takes the tag off. A buy wears its place in the order."""

    SIZE = 40
    _ART = 34

    def __init__(self, name, pix, number=0, parent=None):
        super().__init__(parent)
        self._name = name
        self._number = int(number)
        self._hover = False
        self._pix = (pix.scaled(self._ART, self._ART,
                                Qt.AspectRatioMode.KeepAspectRatio,
                                Qt.TransformationMode.SmoothTransformation)
                     if pix is not None and not pix.isNull() else QPixmap())
        self.setFixedSize(self.SIZE, self.SIZE)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setToolTip("%s\nClick to remove" % name)

    def name(self):
        return self._name

    def enterEvent(self, e):
        self._hover = True
        self.update()
        super().enterEvent(e)

    def leaveEvent(self, e):
        self._hover = False
        self.update()
        super().leaveEvent(e)

    def paintEvent(self, _e):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        p.setPen(QPen(QColor(Colors.BORDER_STRONG if self._hover
                             else Colors.BORDER_SUBTLE), 1))
        p.setBrush(QColor(Colors.BG_OVERLAY))
        p.drawRoundedRect(r, _rad(4), _rad(4))
        if not self._pix.isNull():
            p.drawPixmap((self.width() - self._pix.width()) // 2,
                         (self.height() - self._pix.height()) // 2, self._pix)
        if self._hover:
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(0, 0, 0, 150))
            p.drawRoundedRect(r, _rad(4), _rad(4))
            p.setPen(QPen(QColor(Colors.TEXT_PRIMARY), 2))
            c = self.width() // 2
            p.drawLine(c - 5, c - 5, c + 5, c + 5)
            p.drawLine(c - 5, c + 5, c + 5, c - 5)
        if self._number:
            _draw_tag_plate(p, self.width() - 18, self.height() - 18, 16,
                            "buy", self._number)
        p.end()


class _TagAddButton(QAbstractButton):
    """The + at the end of a tag's row: opens the gift search that adds to
    that tag."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._hover = False
        self.setFixedSize(_TagGiftChip.SIZE, _TagGiftChip.SIZE)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setToolTip("Add a gift by name")

    def enterEvent(self, e):
        self._hover = True
        self.update()
        super().enterEvent(e)

    def leaveEvent(self, e):
        self._hover = False
        self.update()
        super().leaveEvent(e)

    def paintEvent(self, _e):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        p.setPen(QPen(QColor(Colors.BORDER_STRONG if self._hover
                             else Colors.BORDER_SUBTLE), 1))
        p.setBrush(QColor(Colors.BG_OVERLAY) if self._hover
                   else Qt.BrushStyle.NoBrush)
        p.drawRoundedRect(r, _rad(4), _rad(4))
        p.setPen(QPen(QColor(Colors.TEXT_PRIMARY if self._hover
                             else Colors.TEXT_TERTIARY), 1.6))
        c = self.width() / 2
        p.drawLine(QPointF(c - 6, c), QPointF(c + 6, c))
        p.drawLine(QPointF(c, c - 6), QPointF(c, c + 6))
        p.end()


class _TagRow(QWidget):
    """One tag's line of the ledger: its head, its gifts and the +, with a
    hairline under it."""

    def __init__(self, key, label, parent=None):
        super().__init__(parent)
        self._last = False
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, Sizing.SPACE_XS, 0, Sizing.SPACE_XS + 1)
        lay.setSpacing(Sizing.SPACE_MD)
        self.head = _TagRowHead(key, label, self)
        lay.addWidget(self.head, 0, Qt.AlignmentFlag.AlignTop)
        self.chips = QWidget(self)
        self.flow = FlowLayout(self.chips, spacing=Sizing.SPACE_XS)
        self.add = _TagAddButton(self.chips)
        self.flow.addWidget(self.add)
        lay.addWidget(self.chips, 1)

    def set_last(self, last):
        self._last = bool(last)
        self.update()

    def paintEvent(self, _e):
        if self._last:
            return
        p = QPainter(self)
        p.setPen(QPen(QColor(Colors.BORDER_SUBTLE), 1))
        y = self.height() - 1
        p.drawLine(0, y, self.width(), y)
        p.end()


class _TagCheckRow(QAbstractButton):
    """One tag in a gift's popover: a check square, the tag's mark and its
    name. A buy says its place in the order."""

    _H = 32
    _BOX = 16
    _PAD = 10

    def __init__(self, key, label, parent=None):
        super().__init__(parent)
        self._key = key
        self._label = label
        self._on = False
        self._note = ""
        self._hover = False
        self._font = ui_font(Fonts.SIZE_SM)
        self._note_font = ui_font(Fonts.SIZE_XS, QFont.Weight.DemiBold)
        widest = max(QFontMetrics(self._font).horizontalAdvance(lbl)
                     for _k, lbl in _MARKET_MODES)
        note_w = QFontMetrics(self._note_font).horizontalAdvance("#12")
        self.setFixedHeight(self._H)
        self.setMinimumWidth(2 * self._PAD + self._BOX + 10 + _TAG_GLYPH + 8
                             + widest + 16 + note_w)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def key(self):
        return self._key

    def is_on(self):
        return self._on

    def set_state(self, on, note=""):
        self._on = bool(on)
        self._note = str(note or "")
        self.update()

    def enterEvent(self, e):
        self._hover = True
        self.update()
        super().enterEvent(e)

    def leaveEvent(self, e):
        self._hover = False
        self.update()
        super().leaveEvent(e)

    def paintEvent(self, _e):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        if self._hover:
            p.fillRect(self.rect(), QColor(Colors.BG_OVERLAY))
        bx, by = self._PAD, (self.height() - self._BOX) // 2
        box = QRectF(bx + 0.5, by + 0.5, self._BOX - 1, self._BOX - 1)
        if self._on:
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(Colors.ACCENT))
            p.drawRoundedRect(box, _rad(3), _rad(3))
            p.setPen(QPen(QColor("#0e0e10"), 2))
            p.drawLine(bx + 4, by + 8, bx + 7, by + 11)
            p.drawLine(bx + 7, by + 11, bx + 12, by + 5)
        else:
            p.setPen(QPen(QColor(Colors.BORDER_STRONG), 1.5))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawRoundedRect(box, _rad(3), _rad(3))
        gx = bx + self._BOX + 10
        _draw_tag_glyph(p, gx, (self.height() - _TAG_GLYPH) // 2, _TAG_GLYPH,
                        self._key,
                        Colors.ACCENT if self._on else Colors.TEXT_TERTIARY)
        p.setFont(self._font)
        p.setPen(QColor(Colors.TEXT_PRIMARY if self._on
                        else Colors.TEXT_SECONDARY))
        tx = gx + _TAG_GLYPH + 8
        p.drawText(QRect(tx, 0, self.width() - tx - self._PAD, self.height()),
                   int(Qt.AlignmentFlag.AlignLeft
                       | Qt.AlignmentFlag.AlignVCenter), self._label)
        if self._note:
            p.setFont(self._note_font)
            p.setPen(QColor(Colors.ACCENT))
            p.drawText(QRect(0, 0, self.width() - self._PAD, self.height()),
                       int(Qt.AlignmentFlag.AlignRight
                           | Qt.AlignmentFlag.AlignVCenter), self._note)
        p.end()


def _popup_frame(popup, name):
    popup.setObjectName(name)
    popup.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
    popup.setStyleSheet("QFrame#%s{background:%s;border:1px solid %s;}"
                        % (name, Colors.BG_RAISED, Colors.BORDER_STRONG))


class _GiftTagPopup(QFrame):
    """The tags of one gift, opened by clicking its tile: the gift's art and
    name, then a check row per tag. Clicks tick the tags in place; a click
    anywhere else closes it."""

    def __init__(self, gallery, name, info, pix):
        super().__init__(gallery, Qt.WindowType.Popup
                         | Qt.WindowType.FramelessWindowHint)
        _popup_frame(self, "tagPopup")
        self._gallery = gallery
        self.name = name
        self.setFixedWidth(340)
        col = QVBoxLayout(self)
        col.setContentsMargins(1, 1, 1, Sizing.SPACE_XS)
        col.setSpacing(0)
        head = QWidget(self)
        hl = QHBoxLayout(head)
        hl.setContentsMargins(Sizing.SPACE_MD, Sizing.SPACE_SM,
                              Sizing.SPACE_MD, Sizing.SPACE_SM)
        hl.setSpacing(Sizing.SPACE_SM)
        art = QLabel(head)
        art.setFixedSize(44, 44)
        art.setAlignment(Qt.AlignmentFlag.AlignCenter)
        if pix is not None and not pix.isNull():
            art.setPixmap(pix.scaled(44, 44, Qt.AspectRatioMode.KeepAspectRatio,
                                     Qt.TransformationMode.SmoothTransformation))
        hl.addWidget(art, 0, Qt.AlignmentFlag.AlignTop)
        text = QVBoxLayout()
        text.setSpacing(0)
        title = QLabel(name, head, objectName="settingTitle")
        title.setWordWrap(True)
        text.addWidget(title)
        text.addWidget(QLabel("%s  ·  Tier %s" % (
            info["keyword"].title(), _GIFT_TIER_ROMAN.get(info["tier"], "?")),
            head, objectName="inlineMeta"))
        hl.addLayout(text, 1)
        col.addWidget(head)
        col.addWidget(HRule(self))
        self.rows = {}
        for key, label in _MARKET_MODES:
            row = _TagCheckRow(key, label, self)
            row.clicked.connect(
                lambda _c=False, k=key: self._gallery.toggle_tag(k, self.name))
            self.rows[key] = row
            col.addWidget(row)
        self.refresh()

    def refresh(self):
        g = self._gallery
        pos = {n: i + 1 for i, n in enumerate(g._buy)}
        for key, row in self.rows.items():
            note = ("#%d" % pos[self.name]
                    if key == "buy" and self.name in pos else "")
            row.set_state(g.has_tag(key, self.name), note)

    def hideEvent(self, event):
        super().hideEvent(event)
        self._gallery._popup_closed(self)


class _GiftPickRow(QAbstractButton):
    """A gift in the add-by-name list: its art, its name, its keyword and
    tier, and a check once the tag is on it."""

    _H = 36
    _ART = 28

    def __init__(self, name, info, pix, parent=None):
        super().__init__(parent)
        self.name = name
        self._sub = "%s · Tier %s" % (info["keyword"].title(),
                                      _GIFT_TIER_ROMAN.get(info["tier"], "?"))
        self._pix = (pix.scaled(self._ART, self._ART,
                                Qt.AspectRatioMode.KeepAspectRatio,
                                Qt.TransformationMode.SmoothTransformation)
                     if pix is not None and not pix.isNull() else QPixmap())
        self._on = False
        self._hover = False
        self._font = ui_font(Fonts.SIZE_SM)
        self._sub_font = ui_font(Fonts.SIZE_XS)
        self.setFixedHeight(self._H)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def is_on(self):
        return self._on

    def set_state(self, on):
        self._on = bool(on)
        self.update()

    def enterEvent(self, e):
        self._hover = True
        self.update()
        super().enterEvent(e)

    def leaveEvent(self, e):
        self._hover = False
        self.update()
        super().leaveEvent(e)

    def paintEvent(self, _e):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        if self._hover:
            p.fillRect(self.rect(), QColor(Colors.BG_OVERLAY))
        x = Sizing.SPACE_MD
        if not self._pix.isNull():
            p.drawPixmap(x, (self.height() - self._pix.height()) // 2, self._pix)
        x += self._ART + Sizing.SPACE_SM
        right = self.width() - Sizing.SPACE_MD
        if self._on:
            cy = self.height() // 2
            p.setPen(QPen(QColor(Colors.ACCENT), 2))
            p.drawLine(right - 12, cy, right - 8, cy + 4)
            p.drawLine(right - 8, cy + 4, right - 1, cy - 4)
            right -= 20
        sub_w = QFontMetrics(self._sub_font).horizontalAdvance(self._sub)
        p.setFont(self._sub_font)
        p.setPen(QColor(Colors.TEXT_TERTIARY))
        p.drawText(QRect(right - sub_w, 0, sub_w, self.height()),
                   int(Qt.AlignmentFlag.AlignRight
                       | Qt.AlignmentFlag.AlignVCenter), self._sub)
        name_w = right - sub_w - Sizing.SPACE_SM - x
        p.setFont(self._font)
        p.setPen(QColor(Colors.ACCENT if self._on else Colors.TEXT_PRIMARY))
        shown = QFontMetrics(self._font).elidedText(
            self.name, Qt.TextElideMode.ElideRight, name_w)
        p.drawText(QRect(x, 0, name_w, self.height()),
                   int(Qt.AlignmentFlag.AlignLeft
                       | Qt.AlignmentFlag.AlignVCenter), shown)
        p.end()


class _GiftPickPopup(QFrame):
    """The + of a tag's row: a search box over every gift, by name and
    art. Clicking a gift puts the tag on it (or takes it off again); typing
    narrows the list and Enter takes the first match."""

    _ROWS = 8

    def __init__(self, gallery, key):
        super().__init__(gallery, Qt.WindowType.Popup
                         | Qt.WindowType.FramelessWindowHint)
        _popup_frame(self, "tagPopup")
        self._gallery = gallery
        self.key = key
        self.setFixedWidth(380)
        col = QVBoxLayout(self)
        col.setContentsMargins(1, 1, 1, 1)
        col.setSpacing(0)
        head = QHBoxLayout()
        head.setContentsMargins(Sizing.SPACE_MD, Sizing.SPACE_SM,
                                Sizing.SPACE_MD, Sizing.SPACE_SM)
        head.setSpacing(Sizing.SPACE_SM)
        head.addWidget(_TagRowHead(key, dict(_MARKET_MODES)[key], self))
        self.search = QLineEdit(self)
        self.search.setObjectName("textField")
        self.search.setPlaceholderText("Search gifts by name...")
        self.search.setClearButtonEnabled(True)
        self.search.textChanged.connect(self._filter)
        self.search.returnPressed.connect(self._take_first)
        head.addWidget(self.search, 1)
        col.addLayout(head)
        col.addWidget(HRule(self))
        lst = QWidget()
        lcol = QVBoxLayout(lst)
        lcol.setContentsMargins(0, Sizing.SPACE_XS, 0, Sizing.SPACE_XS)
        lcol.setSpacing(0)
        self._empty = QLabel("No gift by that name", lst, objectName="inlineHint")
        self._empty.setContentsMargins(Sizing.SPACE_MD, Sizing.SPACE_SM,
                                       Sizing.SPACE_MD, Sizing.SPACE_SM)
        self._empty.hide()
        lcol.addWidget(self._empty)
        self.rows = {}
        for name in sorted(gallery._tiles, key=str.lower):
            row = _GiftPickRow(name, gallery._cat[name],
                               gallery._tiles[name]._pix, lst)
            row.clicked.connect(
                lambda _c=False, n=name: self._gallery.toggle_tag(self.key, n))
            self.rows[name] = row
            lcol.addWidget(row)
        lcol.addStretch(1)
        self._scroll = QScrollArea(self)
        self._scroll.setObjectName("pageScroll")
        self._scroll.setWidgetResizable(True)
        self._scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        self._scroll.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._scroll.setWidget(lst)
        self._scroll.setFixedHeight(self._ROWS * _GiftPickRow._H
                                    + 2 * Sizing.SPACE_XS)
        col.addWidget(self._scroll)
        self.refresh()

    def refresh(self):
        g = self._gallery
        for name, row in self.rows.items():
            row.set_state(g.has_tag(self.key, name))

    def _filter(self, text):
        q = text.strip().lower()
        shown = False
        for name, row in self.rows.items():
            hit = q in name.lower()
            row.setVisible(hit)
            shown = shown or hit
        self._empty.setVisible(not shown)
        self._scroll.verticalScrollBar().setValue(0)

    def _take_first(self):
        for row in self.rows.values():
            if not row.isHidden():
                self._gallery.toggle_tag(self.key, row.name)
                return

    def showEvent(self, event):
        super().showEvent(event)
        self.search.setFocus()

    def hideEvent(self, event):
        super().hideEvent(event)
        self._gallery._popup_closed(self)


class _MarketGiftTile(QAbstractButton):
    """Market-config gift thumbnail. Wears its tags' marks in a bar along
    its bottom edge and an accent border while its tag popover is open."""

    _SIZE = 58

    def __init__(self, name, info, parent=None):
        super().__init__(parent)
        self._name = name
        self._keep_fuse = False
        self._keep_sell = False
        self._sell = False
        self._buy = 0          # 0 = not in buy order, else 1-based priority
        self._fuse = False
        self._enh1 = False
        self._enh2 = False
        self._active = False
        self._hover = False
        self.setFixedSize(self._SIZE + 8, self._SIZE + 8)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setToolTip(
            f"{name}\n{info['keyword'].title()}  -  Tier "
            f"{_GIFT_TIER_ROMAN.get(info['tier'], '?')}")
        pm = QPixmap(_gift_art(name, info))
        self._pix = (pm.scaled(self._SIZE, self._SIZE,
                               Qt.AspectRatioMode.KeepAspectRatio,
                               Qt.TransformationMode.SmoothTransformation)
                     if not pm.isNull() else pm)

    def set_state(self, keep_fuse, keep_sell, sell, buy, fuse, enh1, enh2):
        kf, ks, s, b = bool(keep_fuse), bool(keep_sell), bool(sell), int(buy)
        fu, e1, e2 = bool(fuse), bool(enh1), bool(enh2)
        if (kf, ks, s, b, fu, e1, e2) != (self._keep_fuse, self._keep_sell,
                                          self._sell, self._buy,
                                          self._fuse, self._enh1, self._enh2):
            (self._keep_fuse, self._keep_sell, self._sell, self._buy,
             self._fuse, self._enh1, self._enh2) = kf, ks, s, b, fu, e1, e2
            self.update()

    def set_active(self, on):
        on = bool(on)
        if on != self._active:
            self._active = on
            self.update()

    def enterEvent(self, e):
        self._hover = True
        self.update()
        super().enterEvent(e)

    def leaveEvent(self, e):
        self._hover = False
        self.update()
        super().leaveEvent(e)

    def _configured(self):
        return (self._keep_fuse or self._keep_sell or self._sell
                or self._buy > 0 or self._fuse or self._enh1 or self._enh2)

    def _badges(self):
        """The tags on this gift as (tag, buy place), in the rows' order."""
        out = []
        if self._keep_fuse:
            out.append(("keep_fuse", 0))
        if self._keep_sell:
            out.append(("keep_sell", 0))
        if self._sell:
            out.append(("sell", 0))
        if self._buy > 0:
            out.append(("buy", self._buy))
        if self._fuse:
            out.append(("fuse", 0))
        if self._enh1:
            out.append(("enhance1", 0))
        if self._enh2:
            out.append(("enhance2", 0))
        return out

    def paintEvent(self, _e):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = QRectF(self.rect()).adjusted(1, 1, -1, -1)
        if self._hover:
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(Colors.BG_OVERLAY))
            p.drawRoundedRect(r, _rad(8), _rad(8))
        if not self._pix.isNull():
            x = int((self.width() - self._pix.width()) / 2)
            y = int((self.height() - self._pix.height()) / 2)
            p.drawPixmap(x, y, self._pix)
        # The tags read as ONE bar across the bottom edge, a mark per tag,
        # rather than a scatter of stickers floating on the artwork. It
        # cannot wrap or overflow however many tags are set.
        badges = self._badges()
        if badges:
            bar_h = 15
            bx0 = int(r.left()) + 1
            bw = int(r.width()) - 2
            by0 = int(r.bottom()) - bar_h
            # Clip to the frame so the square bar cannot poke out past the
            # legacy skin's rounded bottom corners.
            clip = QPainterPath()
            clip.addRoundedRect(r, _rad(8), _rad(8))
            p.save()
            p.setClipPath(clip)
            scrim = "#08080a"
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(8, 8, 10, 215))
            p.drawRect(bx0, by0 - 1, bw, bar_h + 1)
            seg = bw / float(len(badges))
            g = min(12, bar_h - 3)
            for i, (key, number) in enumerate(badges):
                sx = bx0 + int(round(i * seg))
                sw = bx0 + int(round((i + 1) * seg)) - sx
                if i:
                    p.setPen(QPen(QColor(Colors.BORDER_STRONG), 1))
                    p.drawLine(sx, by0 + 2, sx, by0 + bar_h - 2)
                ink = Colors.ACCENT if key == "buy" else Colors.TEXT_PRIMARY
                _draw_tag_glyph(p, sx + (sw - g) / 2.0, by0 + (bar_h - g) / 2.0,
                                g, key, ink, number, halo=scrim)
            p.restore()
        if self._active:
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.setPen(QPen(QColor(Colors.ACCENT), 2))
            p.drawRoundedRect(r, _rad(8), _rad(8))
        elif self._configured():
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.setPen(QPen(QColor(Colors.BORDER_STRONG), 1.5))
            p.drawRoundedRect(r, _rad(8), _rad(8))
        elif self._hover:
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.setPen(QPen(QColor(Colors.BORDER_STRONG), 1))
            p.drawRoundedRect(r, _rad(8), _rad(8))
        p.end()


class _MarketGiftGallery(QWidget):
    """Market gift config. A row per tag lists its gifts as their art, with
    a + that adds one by name; under them, keyword tabs and the active
    keyword's gifts by tier (IV..I), and clicking a gift opens its tags.
    Emits `changed` on any config change."""

    changed = Signal()

    def __init__(self, parent=None, scrollable=True):
        super().__init__(parent)
        self._keep_fuse = set()  # names to keep out of fusion fuel
        self._keep_sell = set()  # names to never sell
        self._sell = set()       # names to sell
        self._buy = []           # names to buy, in priority (click) order
        self._fuse = set()       # names to craft via fusion
        self._enh1 = set()       # names to enhance once
        self._enh2 = set()       # names to enhance twice
        self._popup = None       # the open tag popover or add-by-name list
        self._loading = False
        self._tiles = {}
        self._panels = {}
        self._sections = {}
        self._kw_header = {}
        self._tabs = {}
        try:
            from wbcore.market_catalog import load_market_catalog
            from wbcore.gift_catalog import tab_path
            self._cat = load_market_catalog()
        except Exception:
            self._cat, tab_path = {}, (lambda *_a: None)

        present = [kw for kw in _GIFT_KW_ORDER
                   if any(v.get("keyword") == kw for v in self._cat.values())]
        self._active_kw = present[0] if present else None

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(Sizing.SPACE_SM)

        head = QHBoxLayout()
        head.setSpacing(Sizing.SPACE_MD)
        self._count = QLabel(self, objectName="inlineMeta")
        head.addWidget(self._count)
        head.addStretch(1)
        self._reset_btn = GhostButton("Clear all", self)
        self._reset_btn.clicked.connect(self.reset)
        head.addWidget(self._reset_btn)
        outer.addLayout(head)

        # One row per tag: its gifts as art chips, then a + that adds one
        # by name. Every row is there, so a tag with nothing on it yet
        # still has its +.
        self._rows_holder = QWidget(self)
        rows = QVBoxLayout(self._rows_holder)
        rows.setContentsMargins(0, 0, 0, 0)
        rows.setSpacing(0)
        self._tag_rows = {}
        self._add_btns = {}
        for key, label in _MARKET_MODES:
            row = _TagRow(key, label, self._rows_holder)
            row.add.clicked.connect(lambda _=False, k=key: self._open_picker(k))
            self._tag_rows[key] = row.flow
            self._add_btns[key] = row.add
            rows.addWidget(row)
        row.set_last(True)
        outer.addWidget(self._rows_holder)

        self._search = QLineEdit(self)
        self._search.setObjectName("textField")
        self._search.setPlaceholderText("Search all gifts by name...")
        self._search.setClearButtonEnabled(True)
        self._search.textChanged.connect(self._refresh_view)
        outer.addWidget(self._search)

        tabholder = QWidget(self)
        tabrow = FlowLayout(tabholder, spacing=4)
        for kw in present:
            tab = _KeywordTab(kw, tab_path(kw), tabholder)
            tab.clicked.connect(lambda _=False, k=kw: self._on_tab(k))
            self._tabs[kw] = tab
            tabrow.addWidget(tab)
        outer.addWidget(tabholder)

        inner = QWidget()
        body = QVBoxLayout(inner)
        body.setContentsMargins(0, 0, 0, Sizing.SPACE_MD)
        body.setSpacing(Sizing.SPACE_SM)
        for kw in present:
            panel = QWidget(inner)
            pcol = QVBoxLayout(panel)
            pcol.setContentsMargins(0, 0, 0, 0)
            pcol.setSpacing(Sizing.SPACE_SM)
            kwhdr = QLabel(kw.title(), panel, objectName="sectionLabel")
            pcol.addWidget(kwhdr)
            self._kw_header[kw] = kwhdr
            secs = []
            for tier in (6, 5, 4, 3, 2, 1):
                names = sorted(
                    [n for n, v in self._cat.items()
                     if v.get("keyword") == kw and v.get("tier") == tier],
                    key=lambda n: n.lower())
                if not names:
                    continue
                thdr = _title_label(f"Tier {_GIFT_TIER_ROMAN[tier]}", panel,
                                    pixel=2, section=True)
                pcol.addWidget(thdr)
                holder = QWidget(panel)
                flow = FlowLayout(holder, spacing=6)
                for n in names:
                    tile = _MarketGiftTile(n, self._cat[n], holder)
                    tile.clicked.connect(lambda _=False, nm=n: self._on_tile(nm))
                    self._tiles[n] = tile
                    flow.addWidget(tile)
                pcol.addWidget(holder)
                secs.append((tier, thdr, holder, names))
            self._panels[kw] = panel
            self._sections[kw] = secs
            body.addWidget(panel)
        if scrollable:
            body.addStretch(1)
            sa = QScrollArea(self)
            sa.setObjectName("pageScroll")
            sa.setWidgetResizable(True)
            sa.setFrameShape(QScrollArea.Shape.NoFrame)
            sa.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
            sa.setWidget(inner)
            outer.addWidget(sa, 1)
        else:
            outer.addWidget(inner)

        if self._active_kw is not None:
            self._tabs[self._active_kw].setChecked(True)
        self._refresh_counts()
        self._refresh_view()

    def _on_tab(self, kw):
        self._active_kw = kw
        self._tabs[kw].setChecked(True)
        if self._search.text():
            self._search.blockSignals(True)
            self._search.clear()
            self._search.blockSignals(False)
        self._refresh_view()

    def _names(self, key):
        return {"keep_fuse": self._keep_fuse, "keep_sell": self._keep_sell,
                "sell": self._sell, "buy": self._buy, "fuse": self._fuse,
                "enhance1": self._enh1, "enhance2": self._enh2}[key]

    def has_tag(self, key, name) -> bool:
        return name in self._names(key)

    def _open_picker(self, key):
        self._close_popup()
        self._popup = _GiftPickPopup(self, key)
        self._place_popup(self._popup, self._add_btns[key])

    def _close_popup(self):
        if self._popup is not None:
            self._popup.hide()                  # its hideEvent lets go of it
            self._popup = None

    def _popup_closed(self, popup):
        try:
            if popup is self._popup:
                self._popup = None
            popup.deleteLater()
            for tile in self._tiles.values():
                tile.set_active(False)
        except RuntimeError:
            pass                                # torn down with the page

    @staticmethod
    def _place_popup(popup, anchor):
        """Under the anchor, kept on the screen it is on."""
        popup.adjustSize()
        pos = anchor.mapToGlobal(QPoint(0, anchor.height() + 4))
        screen = QApplication.screenAt(pos) or QApplication.primaryScreen()
        if screen is not None:
            avail = screen.availableGeometry()
            if pos.x() + popup.width() > avail.right():
                pos.setX(max(avail.left(), avail.right() - popup.width()))
            if pos.y() + popup.height() > avail.bottom():
                above = anchor.mapToGlobal(QPoint(0, 0)).y() - popup.height() - 4
                pos.setY(max(avail.top(), above))
        popup.move(pos)
        popup.show()

    def _on_tile(self, name):
        """A gift's tile opens its tags, under the tile."""
        tile = self._tiles.get(name)
        if tile is None:
            return
        self._close_popup()
        self._popup = _GiftTagPopup(self, name, self._cat[name], tile._pix)
        tile.set_active(True)
        self._place_popup(self._popup, tile)

    def toggle_tag(self, key, name):
        """Put a tag on a gift, or take it off again. The tag's exclusive
        pair comes off with it."""
        if key not in _MARKET_MODE_KEYS or name not in self._tiles:
            return
        if key == "keep_fuse":
            if name in self._keep_fuse:
                self._keep_fuse.discard(name)
            else:
                self._keep_fuse.add(name)
        elif key == "keep_sell":
            if name in self._keep_sell:
                self._keep_sell.discard(name)
            else:
                self._keep_sell.add(name)
                self._sell.discard(name)            # keep-no-sell excludes sell
        elif key == "sell":
            if name in self._sell:
                self._sell.discard(name)
            else:
                self._sell.add(name)
                self._keep_sell.discard(name)        # sell excludes keep-no-sell
        elif key == "buy":
            if name in self._buy:
                self._buy.remove(name)
            else:
                self._buy.append(name)
        elif key == "fuse":
            if name in self._fuse:
                self._fuse.discard(name)
            else:
                self._fuse.add(name)
        elif key == "enhance1":
            if name in self._enh1:
                self._enh1.discard(name)
            else:
                self._enh1.add(name)
                self._enh2.discard(name)             # one enhance level only
        elif key == "enhance2":
            if name in self._enh2:
                self._enh2.discard(name)
            else:
                self._enh2.add(name)
                self._enh1.discard(name)             # one enhance level only
        self._refresh_all_badges()
        self._refresh_counts()
        self.changed.emit()

    def _refresh_all_badges(self):
        pos = {n: i + 1 for i, n in enumerate(self._buy)}
        for n, t in self._tiles.items():
            t.set_state(n in self._keep_fuse, n in self._keep_sell,
                        n in self._sell, pos.get(n, 0),
                        n in self._fuse, n in self._enh1, n in self._enh2)

    @staticmethod
    def _clear_layout(lay, keep=None):
        while lay.count():
            item = lay.takeAt(0)
            w = item.widget()
            if w is not None and w is not keep:
                w.setParent(None)
                w.deleteLater()

    def _rebuild_rows(self):
        """Each tag's row: its gifts as art chips (a buy numbered), then
        the + to add one by name."""
        if not hasattr(self, "_tag_rows"):
            return
        pos = {n: i + 1 for i, n in enumerate(self._buy)}
        for key, flow in self._tag_rows.items():
            add = self._add_btns[key]
            self._clear_layout(flow, keep=add)
            names = (list(self._buy) if key == "buy"
                     else sorted(self._names(key), key=str.lower))
            for name in names:
                tile = self._tiles.get(name)
                chip = _TagGiftChip(
                    name, tile._pix if tile is not None else None,
                    number=pos.get(name, 0) if key == "buy" else 0,
                    parent=add.parentWidget())
                chip.clicked.connect(
                    lambda _=False, k=key, nm=name: self._remove_tag(k, nm))
                flow.addWidget(chip)
            flow.addWidget(add)
            flow.invalidate()
        self._rows_holder.updateGeometry()

    def _remove_tag(self, key, name):
        if key == "keep_fuse":
            self._keep_fuse.discard(name)
        elif key == "keep_sell":
            self._keep_sell.discard(name)
        elif key == "sell":
            self._sell.discard(name)
        elif key == "buy" and name in self._buy:
            self._buy.remove(name)
        elif key == "fuse":
            self._fuse.discard(name)
        elif key == "enhance1":
            self._enh1.discard(name)
        elif key == "enhance2":
            self._enh2.discard(name)
        self._refresh_all_badges()
        self._refresh_counts()
        self.changed.emit()

    def _refresh_counts(self):
        total = len({n for names in self.config().values() for n in names})
        self._count.setText("%d configured" % total)
        self._reset_btn.setEnabled(total > 0)
        self._rebuild_rows()
        if self._popup is not None:
            self._popup.refresh()

    def reset(self):
        if not any(self.config().values()):
            return
        self.set_config({})
        self.changed.emit()

    def config(self) -> dict:
        return {"keep_fuse": sorted(self._keep_fuse),
                "keep_sell": sorted(self._keep_sell),
                "sell": sorted(self._sell),
                "buy": list(self._buy),
                "fuse": sorted(self._fuse),
                "enhance1": sorted(self._enh1),
                "enhance2": sorted(self._enh2)}

    def set_config(self, cfg):
        cfg = cfg or {}

        def valid(key):
            return {n for n in (cfg.get(key) or []) if n in self._tiles}

        self._keep_fuse = valid("keep_fuse")
        self._keep_sell = valid("keep_sell")
        self._sell = valid("sell") - self._keep_sell
        self._fuse = valid("fuse")
        self._enh1 = valid("enhance1")
        self._enh2 = valid("enhance2") - self._enh1
        seen = set()
        self._buy = [n for n in (cfg.get("buy") or [])
                     if n in self._tiles and not (n in seen or seen.add(n))]
        self._refresh_all_badges()
        self._refresh_counts()

    def _refresh_view(self, *_):
        q = self._search.text().strip().lower()
        searching = bool(q)
        for kw, panel in self._panels.items():
            if searching:
                p_any = False
                for _tier, thdr, holder, names in self._sections[kw]:
                    t_any = False
                    for n in names:
                        vis = q in n.lower()
                        self._tiles[n].setVisible(vis)
                        t_any = t_any or vis
                    thdr.setVisible(t_any)
                    holder.setVisible(t_any)
                    p_any = p_any or t_any
                self._kw_header[kw].setVisible(p_any)
                panel.setVisible(p_any)
            else:
                active = (kw == self._active_kw)
                panel.setVisible(active)
                self._kw_header[kw].setVisible(False)
                for _tier, thdr, holder, names in self._sections[kw]:
                    thdr.setVisible(active)
                    holder.setVisible(active)
                    if active:
                        for n in names:
                            self._tiles[n].setVisible(True)


# Falls back to empty dicts if the import fails so the page still builds.
try:
    from wbcore.utils.paths import (
        FLOORS, HARD_FLOORS, BANNED, HARD_BANNED,
    )
except Exception:
    FLOORS, HARD_FLOORS, BANNED, HARD_BANNED = {}, {}, [], []


_KEYWORDS = (
    "Slash", "Pierce", "Blunt",
    "Burn", "Bleed", "Tremor", "Rupture", "Sinking", "Poise", "Charge",
    "Wrath", "Lust", "Sloth", "Glut.", "Gloom", "Pride", "Envy",
)


# Drag-reorder card stack for Shop Skill Replacement. Hand-built QFrame
# cards with QDrag because QListWidget's delegate clipped the spinbox and
# collapsed row heights.
_SKILL_CARD_MIME = "application/x-workerbee-skill-swap"


# The per-sinner block is capped at this width: at full card width a row's
# count sat a whole screen away from the swap it belongs to.
_SKILL_BLOCK_W = 460
# Twelve sinners as 4 x 3: three name rows, level with the three swap rows.
_SKILL_CHIP_COLS = 4


def _skill_row_h() -> int:
    """Height shared by a swap row and a sinner chip, so the two columns
    of the block stay on the same lines."""
    from .skins import is_voxel
    return 34 if is_voxel() else 48


class _SkillGrip(QWidget):
    """Drag handle: a 2x3 block of square dots, painted so it matches the
    pixel look instead of borrowing a braille glyph from the text font."""

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setFixedSize(7, 12)

    def paintEvent(self, _event):
        p = QPainter(self)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(Colors.TEXT_TERTIARY))
        for cx in range(2):
            for cy in range(3):
                p.drawRect(cx * 5, cy * 5, 2, 2)
        p.end()


class _SwapMark(QWidget):
    """A swap as the in-game skill slots: the slot given up, an arrow, the
    slot taken, each slot a small card with its number in the pixel face."""

    _CARD_W, _CARD_H, _GAP, _ARROW_W = 16, 22, 5, 10
    _INK = {1: Colors.TEXT_SECONDARY, 2: Colors.INFO, 3: Colors.ACCENT}

    def __init__(self, swap_key: str, parent: QWidget | None = None):
        super().__init__(parent)
        a, _, b = str(swap_key).partition(">")
        self._slots = (int(a or 1), int(b or 3))
        self.setFixedSize(2 * self._CARD_W + 2 * self._GAP + self._ARROW_W,
                          self._CARD_H)
        self.setToolTip("Skill %d is replaced by Skill %d" % self._slots)

    def paintEvent(self, _e):
        from .voxel import draw_pixel_text
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, False)
        x = 0
        for i, slot in enumerate(self._slots):
            ink = QColor(self._INK.get(slot, Colors.TEXT_SECONDARY))
            fill = QColor(ink)
            fill.setAlpha(28)
            p.setPen(QPen(ink, 1))
            p.setBrush(fill)
            p.drawRect(x, 0, self._CARD_W - 1, self._CARD_H - 1)
            draw_pixel_text(p, x + (self._CARD_W - 10) // 2,
                            (self._CARD_H - 14) // 2, str(slot), 2, ink)
            x += self._CARD_W + self._GAP
            if i == 0:
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(QColor(Colors.TEXT_TERTIARY))
                top = (self._CARD_H - 10) // 2
                for ry, row in enumerate(("..#..", "...#.", "#####", "...#.", "..#..")):
                    for rx, cell in enumerate(row):
                        if cell == "#":
                            p.drawRect(x + rx * 2, top + ry * 2, 2, 2)
                x += self._ARROW_W + self._GAP
        p.end()


class _SkillSwapCard(QFrame):
    """Drag-reorderable row: rank | grip | slots | label | repeats spinbox."""

    repeats_changed = Signal(str, int)

    def __init__(self, swap_key: str, label: str, repeats: int,
                 parent: QWidget | None = None):
        super().__init__(parent)
        from .skins import is_voxel
        self._swap = swap_key
        self._drag_press: QPoint | None = None
        self.setObjectName("skillSwapCard")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setCursor(Qt.CursorShape.OpenHandCursor)
        voxel = is_voxel()
        # setFixedHeight (not min-height) prevents QVBoxLayout collapsing.
        self.setFixedHeight(_skill_row_h())
        h = QHBoxLayout(self)
        h.setContentsMargins(Sizing.SPACE_MD, 0, Sizing.SPACE_XS + 1, 0)
        h.setSpacing(Sizing.SPACE_MD)

        # Place in the priority order; the stack renumbers it after a drop.
        self._rank = QLabel("", self)
        self._rank.setFixedWidth(10)
        self._rank.setAlignment(Qt.AlignmentFlag.AlignCenter)
        h.addWidget(self._rank)
        h.addWidget(_SkillGrip(self))
        h.addWidget(_SwapMark(swap_key, self))

        self._text = QLabel(label, self, objectName="settingTitle")
        h.addWidget(self._text)
        h.addStretch(1)

        self._spin = QSpinBox(self)
        self._spin.setObjectName("runCount")
        self._spin.setRange(0, 99)
        self._spin.setValue(int(repeats or 0))
        self._spin.setFixedSize(*((58, 24) if voxel else (84, 34)))
        self._spin.setToolTip("How many times to take this swap in a run")
        self._spin.valueChanged.connect(
            lambda v: self.repeats_changed.emit(self._swap, int(v)))
        h.addWidget(self._spin, 0, Qt.AlignmentFlag.AlignVCenter)

        self.set_dim(False)

    def set_rank(self, rank: int):
        self._rank.setText(str(rank))

    def set_dim(self, dim: bool):
        """Read as inactive without disabling: the row stays editable."""
        plain = "background: transparent; border: none;"
        rank = Colors.TEXT_TERTIARY if dim else Colors.ACCENT
        self._rank.setStyleSheet(
            f"color: {rank}; font-weight: 700; {plain}")
        self._text.setStyleSheet(
            (f"color: {Colors.TEXT_TERTIARY}; " if dim else "") + plain)
        self._spin.setStyleSheet(
            f"color: {Colors.TEXT_TERTIARY};" if dim else "")

    def swap(self) -> str:
        return self._swap

    def repeats(self) -> int:
        return self._spin.value()

    # --- drag plumbing ---------------------------------------------------
    def mousePressEvent(self, event):
        super().mousePressEvent(event)
        if event.button() == Qt.MouseButton.LeftButton:
            # Don't start a drag if the press lands on the spinbox.
            child = self.childAt(event.position().toPoint())
            if child is self._spin or (child is not None and
                                       self._spin.isAncestorOf(child)):
                return
            self._drag_press = event.position().toPoint()
            self.setCursor(Qt.CursorShape.ClosedHandCursor)

    def mouseMoveEvent(self, event):
        super().mouseMoveEvent(event)
        if self._drag_press is None:
            return
        if (event.position().toPoint() - self._drag_press).manhattanLength() \
                < QApplication.startDragDistance():
            return
        drag = QDrag(self)
        mime = QMimeData()
        mime.setData(_SKILL_CARD_MIME, self._swap.encode("utf-8"))
        drag.setMimeData(mime)
        pm = self.grab()
        drag.setPixmap(pm)
        drag.setHotSpot(self._drag_press)
        drag.exec(Qt.DropAction.MoveAction)
        self._drag_press = None
        self.setCursor(Qt.CursorShape.OpenHandCursor)

    def mouseReleaseEvent(self, event):
        super().mouseReleaseEvent(event)
        self._drag_press = None
        self.setCursor(Qt.CursorShape.OpenHandCursor)


class _SkillPriorityStack(QWidget):
    """Vertical stack of `_SkillSwapCard` widgets with drag-reorder."""

    order_changed = Signal(list)
    repeats_changed = Signal(str, int)

    def __init__(self, items: list[tuple[str, str, int]],
                 parent: QWidget | None = None):
        super().__init__(parent)
        self.setAcceptDrops(True)
        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._layout.setSpacing(Sizing.SPACE_XS)
        self._cards: list[_SkillSwapCard] = []
        for swap_key, label, repeats in items:
            card = _SkillSwapCard(swap_key, label, repeats, self)
            card.repeats_changed.connect(self.repeats_changed.emit)
            self._cards.append(card)
            self._layout.addWidget(card)
        self._renumber()

    def _renumber(self):
        for i, card in enumerate(self._cards, 1):
            card.set_rank(i)

    def set_dim(self, dim: bool):
        for card in self._cards:
            card.set_dim(dim)

    def order(self) -> list[str]:
        return [c.swap() for c in self._cards]

    def dragEnterEvent(self, event):
        if event.mimeData().hasFormat(_SKILL_CARD_MIME):
            event.acceptProposedAction()

    def dragMoveEvent(self, event):
        if event.mimeData().hasFormat(_SKILL_CARD_MIME):
            event.acceptProposedAction()

    def dropEvent(self, event):
        if not event.mimeData().hasFormat(_SKILL_CARD_MIME):
            return
        source_key = bytes(event.mimeData().data(_SKILL_CARD_MIME)).decode("utf-8")
        source = next((c for c in self._cards if c.swap() == source_key), None)
        if source is None:
            return

        drop_y = event.position().toPoint().y()
        # Insert before the first card whose midpoint is past drop_y.
        target_index = len(self._cards) - 1
        for card in self._cards:
            if card is source:
                continue
            if drop_y < card.geometry().center().y():
                target_index = self._cards.index(card)
                break

        self._cards.remove(source)
        if target_index > len(self._cards):
            target_index = len(self._cards)
        self._cards.insert(target_index, source)

        # Repopulate the layout; widgets stay alive (parented to self).
        while self._layout.count() > 0:
            self._layout.takeAt(0)
        for card in self._cards:
            self._layout.addWidget(card)
        self._renumber()

        event.acceptProposedAction()
        self.order_changed.emit(self.order())


# Sinner chip used by the Shop Skill Replacement section.
from .widgets import _AnimatedChip


class _SinnerSkillChip(_AnimatedChip):
    """Chip with the sinner's emblem and two independent states: `selected`
    (yellow outline, exclusive) and `active` (an accent mark in the corner,
    any number).

    Click emits `selected`; double-click emits `toggled_active`.
    """

    selected = Signal(str)
    toggled_active = Signal(str)
    _ICON = 22

    def __init__(self, name: str, parent: QWidget | None = None):
        super().__init__(name, parent)
        self._name = name
        self._is_selected = False
        self._is_active = False
        from .giftart import sinner_icon
        pm = QPixmap(sinner_icon(name))
        self._emblem = (pm.scaled(self._ICON, self._ICON,
                                  Qt.AspectRatioMode.KeepAspectRatio,
                                  Qt.TransformationMode.SmoothTransformation)
                        if not pm.isNull() else pm)
        # Apply the initial colour state immediately.
        self._apply_state(animate=False)
        # `selected` fires instantly on press; a double-click's first
        # release also emits `selected` (cheap extra render, snappy feel).

    # --- public API ---------------------------------------------------
    def name(self) -> str:
        return self._name

    def is_active(self) -> bool:
        return self._is_active

    def set_active(self, on: bool):
        self._is_active = bool(on)
        self._apply_state()

    def set_selected(self, on: bool):
        self._is_selected = bool(on)
        self._apply_state()

    def sizeHint(self) -> QSize:
        hint = super().sizeHint()
        if not self._emblem.isNull():
            hint.setWidth(hint.width() + self._ICON + Sizing.SPACE_SM)
        return hint

    def _paint_label(self, p, rect):
        if self._emblem.isNull():
            super()._paint_label(p, rect)
        else:
            p.drawPixmap(rect.left() + self._HPAD,
                         rect.top() + (rect.height() - self._emblem.height()) // 2,
                         self._emblem)
            f = self.font()
            f.setWeight(QFont.Weight.DemiBold if self._bold
                        else QFont.Weight.Medium)
            p.setFont(f)
            p.setPen(self._fg)
            p.drawText(rect.adjusted(self._HPAD + self._ICON + Sizing.SPACE_SM,
                                     0, -self._HPAD, 0),
                       int(Qt.AlignmentFlag.AlignLeft
                           | Qt.AlignmentFlag.AlignVCenter), self.text())
        if self._is_active:
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(Colors.ACCENT))
            p.drawRect(rect.right() - 9, rect.top() + 4, 5, 5)

    # --- mouse events -------------------------------------------------
    def mouseReleaseEvent(self, event):
        super().mouseReleaseEvent(event)
        if event.button() == Qt.MouseButton.LeftButton:
            self.selected.emit(self._name)

    def mouseDoubleClickEvent(self, event):
        super().mouseDoubleClickEvent(event)
        if event.button() == Qt.MouseButton.LeftButton:
            self.toggled_active.emit(self._name)

    # --- visual -------------------------------------------------------
    def _current_colors(self):
        # Called by the base class on theme refresh.
        return self._state_colors()

    def _state_colors(self):
        if self._is_selected:
            return (Colors.BG_HOVER, Colors.ACCENT,
                    Colors.TEXT_PRIMARY, True)
        if self._is_active:
            return (Colors.BG_OVERLAY, Colors.ACCENT_MUTED,
                    Colors.TEXT_PRIMARY, False)
        return (Colors.BG_OVERLAY, Colors.BORDER_SUBTLE,
                Colors.TEXT_SECONDARY, False)

    def _apply_state(self, animate: bool = True):
        cols = self._state_colors()
        if animate:
            self._go(*cols)
        else:
            self._set(*cols)

# Starting-grace names (BUFF[0..9]). Each grace state maps to a BUFF
# value: 0 skip, 1 select, 2 left (+), 3 right (++).
_GRACE_NAMES = (
    "Star of the Beginning", "Cumulating Starcloud", "Interstellar Travel",
    "Star Shower", "Binary Star Shop", "Moon Star Shop",
    "Favor of the Nebula", "Starlight Guidance", "Chance Comet",
    "Perfected Possibility",
)
# Reward-card types in priority order (card0..card4).
_CARD_NAMES = (
    "Cost + Gift", "Cost", "Gift", "Resource", "Starlight",
)


def _floors_for_picker(data: dict, max_floor: int) -> dict:
    """Floor->packs for the picker, mirroring the bot's format_lvl mapping:
    floors 1-5 use their own pool, 6-10 reuse floor 5, 11-15 reuse floor 15."""
    def source(f: int) -> int:
        if f <= 5:
            return f
        if f <= 10:
            return 5
        return 15
    return {f: list(data.get(source(f), []))
            for f in range(1, max_floor + 1)}


class _EvenColumn(QWidget):
    """A column that asks for no width of its own, so the columns of a row
    split it evenly however tall each one's cards are."""

    def sizeHint(self) -> QSize:
        return QSize(0, super().sizeHint().height())


class _FloorCells(QWidget):
    """The five floors as pixel-lettered cells, lit in the accent where the
    subclass says the floor is on. The hover tip and the click go through
    its hooks."""

    _CELL_W, _CELL_H, _GAP = 38, 24, 4

    def __init__(self, floors=(1, 2, 3, 4, 5), parent: QWidget | None = None):
        super().__init__(parent)
        self._floors = tuple(floors)
        self._hover = None
        self.setMouseTracking(True)
        n = len(self._floors)
        self.setFixedSize(n * self._CELL_W + (n - 1) * self._GAP, self._CELL_H)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def _lit(self, floor: int) -> bool:
        return False

    def _locked(self, floor: int) -> bool:
        return False

    def _tip(self, floor: int) -> str:
        return ""

    def _clicked(self, floor: int):
        pass

    def _cell_at(self, x: int):
        pitch = self._CELL_W + self._GAP
        i = x // pitch
        if 0 <= i < len(self._floors) and x - i * pitch < self._CELL_W:
            return self._floors[i]
        return None

    def mouseMoveEvent(self, e):
        floor = self._cell_at(int(e.position().x()))
        if floor != self._hover:
            self._hover = floor
            self.update()
            self.setToolTip("" if floor is None else self._tip(floor))
        super().mouseMoveEvent(e)

    def leaveEvent(self, e):
        self._hover = None
        self.update()
        super().leaveEvent(e)

    def mouseReleaseEvent(self, e):
        floor = self._cell_at(int(e.position().x()))
        if (floor is not None and e.button() == Qt.MouseButton.LeftButton
                and not self._locked(floor)):
            self._clicked(floor)
        super().mouseReleaseEvent(e)

    def paintEvent(self, _e):
        from .voxel import draw_pixel_text, pixel_text_width
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, False)
        for i, floor in enumerate(self._floors):
            x = i * (self._CELL_W + self._GAP)
            lit, locked = self._lit(floor), self._locked(floor)
            if lit:
                fill = QColor(Colors.ACCENT)
                if locked:
                    fill.setAlpha(160)
                ink = QColor(Colors.BG_BASE)
                edge = fill
            else:
                fill = QColor(Colors.BG_OVERLAY)
                ink = QColor(Colors.TEXT_SECONDARY)
                edge = QColor(Colors.BORDER_SUBTLE)
            if self._hover == floor and not locked:
                fill = fill.lighter(112)
                ink = QColor(Colors.BG_BASE if lit else Colors.TEXT_PRIMARY)
            p.setPen(QPen(edge, 1))
            p.setBrush(fill)
            p.drawRect(x, 0, self._CELL_W - 1, self._CELL_H - 1)
            text = "F%d" % floor
            draw_pixel_text(p, x + (self._CELL_W - pixel_text_width(text, 2)) // 2,
                            (self._CELL_H - 14) // 2, text, 2, ink)
        p.end()


class _FloorStrip(_FloorCells):
    """The Difficulty card's floors, lit where the run is Hard. A click on
    a Normal floor flips the run to Hard from there; a click on the flip
    floor goes back to Normal throughout. The floors after the flip are
    Hard by consequence and take no click."""

    floor_clicked = Signal(int)

    def __init__(self, floors=(1, 2, 3, 4, 5), parent: QWidget | None = None):
        super().__init__(floors, parent)
        self._hard_from = None

    def set_hard_from(self, floor):
        self._hard_from = floor
        self.update()

    def _is_hard(self, floor: int) -> bool:
        return self._hard_from is not None and floor >= self._hard_from

    def _is_locked(self, floor: int) -> bool:
        return self._hard_from is not None and floor > self._hard_from

    _lit = _is_hard
    _locked = _is_locked

    def _tip(self, floor: int) -> str:
        if self._is_locked(floor):
            return ("Hard from floor %d; click that floor to run Normal "
                    "again." % self._hard_from)
        if self._is_hard(floor):
            return "Hard from floor %d. Click to run Normal throughout." % floor
        return "Click to run Hard from floor %d." % floor

    def _clicked(self, floor: int):
        self.floor_clicked.emit(floor)


class _FloorPicks(_FloorCells):
    """Floors as switches, each cell on or off on its own: lit where the
    shop's skill offers are taken."""

    floor_toggled = Signal(int, bool)

    def __init__(self, floors=(1, 2, 3, 4, 5), parent: QWidget | None = None):
        super().__init__(floors, parent)
        self._on = set(self._floors)

    def set_floors(self, floors):
        self._on = {f for f in floors if f in self._floors}
        self.update()

    def floors(self) -> set:
        return set(self._on)

    def _lit(self, floor: int) -> bool:
        return floor in self._on

    def _tip(self, floor: int) -> str:
        if floor in self._on:
            return "Skills will be swapped on floor %d. Click to leave them." % floor
        return "Click to swap skills on floor %d too." % floor

    def _clicked(self, floor: int):
        self.floor_toggled.emit(floor, floor not in self._on)


class _TeamRow(QFrame):
    """Row in the team-rotation list: name + affinities + Edit/Remove."""

    edit_requested = Signal(str)
    remove_requested = Signal(str)

    def __init__(self, name: str, affinities: list[str],
                 parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("teamRow")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self._name = name

        row = QHBoxLayout(self)
        row.setContentsMargins(
            Sizing.SPACE_SM, Sizing.SPACE_SM,
            Sizing.SPACE_SM, Sizing.SPACE_SM,
        )
        row.setSpacing(Sizing.SPACE_MD)

        col = QVBoxLayout()
        col.setSpacing(2)
        name_lbl = QLabel(name, self)
        name_lbl.setObjectName("teamRowName")
        col.addWidget(name_lbl)

        aff = QHBoxLayout()
        aff.setContentsMargins(0, 0, 0, 0)
        aff.setSpacing(Sizing.SPACE_XS)
        from .giftart import keyword_icon
        for keyword in affinities:
            pm = QPixmap(keyword_icon(keyword))
            if pm.isNull():
                continue
            art = QLabel(self)
            art.setFixedSize(16, 16)
            art.setPixmap(pm.scaled(16, 16, Qt.AspectRatioMode.KeepAspectRatio,
                                    Qt.TransformationMode.SmoothTransformation))
            aff.addWidget(art)
        aff_lbl = QLabel("  ·  ".join(affinities), self)
        aff_lbl.setObjectName("teamRowAffinities")
        aff.addWidget(aff_lbl)
        aff.addStretch(1)
        col.addLayout(aff)
        row.addLayout(col, stretch=1)

        edit = LinkButton("Edit", self)
        edit.clicked.connect(lambda: self.edit_requested.emit(self._name))
        row.addWidget(edit)

        remove = LinkButton("Remove", self)
        remove.setProperty("danger", "true")
        remove.clicked.connect(lambda: self.remove_requested.emit(self._name))
        row.addWidget(remove)


class TeamEditDialog(QDialog):
    """Edit a rotation team: name + 1-2 affinity keywords. Returns
    {name, affinities} via team()."""

    def __init__(self, team: dict | None = None,
                 parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("dialog")
        self.setWindowTitle("Edit team" if team else "Add team")
        self.setModal(True)
        self.setMinimumWidth(440)
        team = team or {}

        col = QVBoxLayout(self)
        col.setContentsMargins(
            Sizing.SPACE_XL, Sizing.SPACE_XL,
            Sizing.SPACE_XL, Sizing.SPACE_LG,
        )
        col.setSpacing(Sizing.SPACE_MD)

        title = QLabel("Edit team" if team else "Add team", self,
                       objectName="dialogTitle")
        col.addWidget(title)

        col.addWidget(QLabel("NAME", self, objectName="sectionLabel"))
        self._name = QLineEdit(team.get("name", ""), self)
        self._name.setObjectName("textField")
        self._name.setPlaceholderText("e.g. Burn")
        col.addWidget(self._name)

        col.addSpacing(Sizing.SPACE_SM)
        col.addWidget(QLabel("AFFINITIES (pick up to 2)", self,
                             objectName="sectionLabel"))
        chosen = set(team.get("affinities", []))
        flow_host = QWidget(self)
        flow = FlowLayout(flow_host, spacing=Sizing.SPACE_XS)
        self._aff_chips = {}
        for kw in _KEYWORDS:
            chip = QPushButton(kw, flow_host)
            chip.setObjectName("chip")
            chip.setCheckable(True)
            chip.setChecked(kw in chosen)
            chip.setCursor(Qt.CursorShape.PointingHandCursor)
            chip.clicked.connect(self._enforce_limit)
            flow.addWidget(chip)
            self._aff_chips[kw] = chip
        col.addWidget(flow_host)

        col.addStretch(1)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok
            | QDialogButtonBox.StandardButton.Cancel,
            parent=self,
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        col.addWidget(buttons)

    def _enforce_limit(self):
        checked = [k for k, c in self._aff_chips.items() if c.isChecked()]
        if len(checked) > 2:
            # Uncheck the just-clicked one if it pushes past 2.
            sender = self.sender()
            if sender is not None:
                sender.setChecked(False)

    def team(self) -> dict:
        affinities = [k for k, c in self._aff_chips.items() if c.isChecked()]
        name = self._name.text().strip() or (affinities[0] if affinities else "Team")
        return {"name": name, "affinities": affinities}


def _pack_search_names_for_floor(floor: int) -> list:
    """Display names of the packs Pack Search can hunt on `floor`
    (either difficulty's pool)."""
    try:
        from wbcore.pack_search_catalog import PACK_SEARCH_KEYS
        from wbcore.utils.paths import pack_in_floor
        # pack_in_floor resolves section bases (e.g. Masquerade Line 4, which
        # is searchable but is not itself a pack - its sections are).
        return sorted(n for n, k in PACK_SEARCH_KEYS.items()
                      if pack_in_floor(k, floor))
    except Exception:
        return []


class _PackPlate(QWidget):
    """The configured pack's card beside its field; an empty plate with a
    question mark until a pack is named."""

    _W, _H, _PAD = 46, 80, 3

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self._pix = QPixmap()
        self.setFixedSize(self._W, self._H)
        self.set_pack("")

    def set_pack(self, name: str):
        path = ""
        if name:
            try:
                from wbcore.pack_search_catalog import PACK_SEARCH_KEYS
                from .giftart import pack_icon
                path = pack_icon(PACK_SEARCH_KEYS.get(name, name))
            except Exception:
                path = ""
        pm = QPixmap(path) if path else QPixmap()
        self._pix = (pm.scaled(self._W - 2 * self._PAD, self._H - 2 * self._PAD,
                               Qt.AspectRatioMode.KeepAspectRatio,
                               Qt.TransformationMode.SmoothTransformation)
                     if not pm.isNull() else QPixmap())
        self.setToolTip(name or "No pack configured")
        self.update()

    def paintEvent(self, _e):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        p.setPen(QPen(QColor(Colors.BORDER_SUBTLE), 1))
        p.setBrush(QColor(Colors.BG_OVERLAY))
        p.drawRoundedRect(r, _rad(4), _rad(4))
        if self._pix.isNull():
            from .voxel import draw_pixel_text, pixel_text_width
            p.setRenderHint(QPainter.RenderHint.Antialiasing, False)
            draw_pixel_text(p, (self._W - pixel_text_width("?", 2)) // 2,
                            (self._H - 14) // 2, "?", 2,
                            QColor(Colors.TEXT_TERTIARY))
        else:
            p.drawPixmap((self._W - self._pix.width()) // 2,
                         (self._H - self._pix.height()) // 2, self._pix)
        p.end()


class _PackSearchEdit(QLineEdit):
    """Line edit whose Tab key accepts the inline completion instead of
    moving focus."""

    def keyPressEvent(self, ev):
        if ev.key() == Qt.Key.Key_Tab:
            comp = self.completer()
            done = comp.currentCompletion() if comp is not None else ""
            if done:
                self.setText(done)
                self.end(False)
                return
        super().keyPressEvent(ev)


def _preset_title(text, parent):
    """A preset's name, a step above its section headers."""
    lbl = _title_label(text.upper(), parent, pixel=3, section=False)
    lbl.setObjectName("presetTitle")
    return lbl


def _preset_meta(preset: dict) -> str:
    """The run at a glance under a card's portraits: the floors as players
    write them (4N1H) and the team's keyword."""
    from .presets import floor_code
    parts = [floor_code(preset["mirror"])]
    for team in (preset.get("teams") or {}).values():
        if team.get("keyword"):
            parts.append("%s team" % team["keyword"])
        break
    return "  \u00b7  ".join(parts)


class _MiniPortrait(QWidget):
    """An identity on a preset card, by its in-game card alone; its name and
    the requirement on it come up on hover."""

    SIZE = 56

    def __init__(self, pic: dict, parent=None):
        super().__init__(parent)
        from .giftart import preset_portrait
        self.stem = pic["stem"]
        self.name = pic["name"]
        pm = QPixmap(preset_portrait(self.stem))
        self._pix = (pm.scaled(self.SIZE - 2, self.SIZE - 2,
                               Qt.AspectRatioMode.KeepAspectRatio,
                               Qt.TransformationMode.SmoothTransformation)
                     if not pm.isNull() else QPixmap())
        self.setFixedSize(self.SIZE, self.SIZE)
        req = pic.get("req") or ""
        self.setToolTip(self.name + ("\n" + req if req else ""))

    def paintEvent(self, _e):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        p.setPen(QPen(QColor(Colors.BORDER_STRONG), 1))
        p.setBrush(QColor(Colors.BG_BASE))
        p.drawRoundedRect(r, _rad(4), _rad(4))
        if not self._pix.isNull():
            p.drawPixmap((self.width() - self._pix.width()) // 2,
                         (self.height() - self._pix.height()) // 2, self._pix)
        p.end()


class _PresetCard(QFrame):
    """One ready-made setup, compact: its name, the identities it fields and
    the run at a glance. Hovering (or focusing) it unfolds More details and
    Apply config; a click on the face opens the details. An accent frame
    says the settings are this preset's, to the letter."""

    details_requested = Signal(str)
    apply_requested = Signal(str)
    W = 480

    def __init__(self, preset: dict, parent=None):
        super().__init__(parent)
        self.key = preset["key"]
        self.title = preset["title"]
        self.setObjectName("presetCard")
        self.setFixedWidth(self.W)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self._hover = False
        self._keyed = False
        self._active = False
        self._open = 0.0
        col = QVBoxLayout(self)
        col.setContentsMargins(Sizing.SPACE_LG, Sizing.SPACE_MD,
                               Sizing.SPACE_LG, Sizing.SPACE_MD)
        col.setSpacing(Sizing.SPACE_SM)
        head = QHBoxLayout()
        head.setSpacing(Sizing.SPACE_MD)
        self._title = _preset_title(self.title, self)
        head.addWidget(self._title)
        self.mark = QLabel("In use", self, objectName="presetMark")
        self.mark.setVisible(False)
        head.addWidget(self.mark)
        head.addStretch(1)
        col.addLayout(head)
        row = QHBoxLayout()
        row.setSpacing(6)
        self.portraits = []
        _label, _text, pics = preset["needs"][0]
        for pic in pics:
            tile = _MiniPortrait(pic, self)
            tile.installEventFilter(self)
            row.addWidget(tile)
            self.portraits.append(tile)
        row.addStretch(1)
        col.addLayout(row)
        self.meta = QLabel(_preset_meta(preset), self, objectName="inlineMeta")
        col.addWidget(self.meta)
        self.actions = QWidget(self)
        arow = QHBoxLayout(self.actions)
        arow.setContentsMargins(0, Sizing.SPACE_XS, 0, 0)
        arow.setSpacing(Sizing.SPACE_SM)
        self.details = GhostButton("More details", self.actions)
        self.details.search_skip = True      # one per card, the card is the feature
        self.details.clicked.connect(
            lambda: self.details_requested.emit(self.key))
        self.apply = PrimaryButton("Apply config", self.actions)
        self.apply.search_skip = True
        self.apply.clicked.connect(lambda: self.apply_requested.emit(self.key))
        for btn in (self.details, self.apply):
            btn.installEventFilter(self)
            arow.addWidget(btn)
        arow.addStretch(1)
        self.actions.setMaximumHeight(0)
        self.actions.setVisible(False)
        col.addWidget(self.actions)
        for w in (self._title, self.mark, self.meta):
            w.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self._anim = QPropertyAnimation(self, b"unfold", self)
        self._anim.setDuration(Motion.QUICK)
        self._anim.setEasingCurve(QEasingCurve.Type.OutCubic)

    # --- the unfolding actions row ---------------------------------
    def _get_open(self):
        return self._open

    def _set_open(self, v):
        self._open = max(0.0, min(1.0, float(v)))
        self.actions.setVisible(self._open > 0.0)
        self.actions.setMaximumHeight(
            int(round(self.actions.sizeHint().height() * self._open)))
        self.updateGeometry()

    unfold = Property(float, _get_open, _set_open)

    def is_open(self) -> bool:
        return self._open >= 1.0

    def set_open(self, on: bool, animate: bool = True):
        self._anim.stop()
        if not animate:
            self._set_open(1.0 if on else 0.0)
            return
        self._anim.setStartValue(self._open)
        self._anim.setEndValue(1.0 if on else 0.0)
        self._anim.start()

    def _pointer_inside(self) -> bool:
        return (self.isVisible()
                and self.rect().contains(self.mapFromGlobal(QCursor.pos())))

    @staticmethod
    def _by_key(event) -> bool:
        return event.reason() in (Qt.FocusReason.TabFocusReason,
                                  Qt.FocusReason.BacktabFocusReason,
                                  Qt.FocusReason.ShortcutFocusReason)

    def _settle(self):
        """Fold once neither the pointer nor a keyboard focus is on the
        card. A click focuses the card too, and a closed details window
        hands the focus back, so only focus that arrived by key holds the
        card open, until the focus moves on within the window."""
        try:
            fw = QApplication.focusWidget()
            if (fw is not None and fw.window() is self.window()
                    and not (fw is self or self.isAncestorOf(fw))):
                self._keyed = False
            if self._keyed or self._pointer_inside():
                return
            self._hover = False
            self.set_open(False)
            self.update()
        except RuntimeError:
            pass

    def _focused(self, event):
        """Focus that came by key opens the card and holds it; any other
        focus leaves the pointer to decide."""
        if self._by_key(event):
            self._keyed = True
            self.set_open(True)
        self.update()
        QTimer.singleShot(0, self._settle)

    def enterEvent(self, event):
        self._hover = True
        self.set_open(True)
        self.update()
        super().enterEvent(event)

    def leaveEvent(self, event):
        self._hover = False
        self.update()
        QTimer.singleShot(0, self._settle)
        super().leaveEvent(event)

    def focusInEvent(self, event):
        self._focused(event)
        super().focusInEvent(event)

    def focusOutEvent(self, event):
        self.update()
        QTimer.singleShot(0, self._settle)
        super().focusOutEvent(event)

    def event(self, e):
        if e.type() == QEvent.Type.WindowActivate:
            QTimer.singleShot(0, self._settle)   # the pointer moved on meanwhile
        return super().event(e)

    def eventFilter(self, obj, event):
        et = event.type()
        if et == QEvent.Type.FocusIn:
            self._focused(event)
        elif et == QEvent.Type.FocusOut:
            QTimer.singleShot(0, self._settle)
        elif (et == QEvent.Type.MouseButtonRelease
              and isinstance(obj, _MiniPortrait)
              and event.button() == Qt.MouseButton.LeftButton
              and obj.rect().contains(event.position().toPoint())):
            self.details_requested.emit(self.key)
            return True
        return super().eventFilter(obj, event)

    # --- the face ---------------------------------------------------
    def mouseReleaseEvent(self, event):
        if (event.button() == Qt.MouseButton.LeftButton
                and self.rect().contains(event.position().toPoint())):
            self.details_requested.emit(self.key)
        super().mouseReleaseEvent(event)

    def keyPressEvent(self, event):
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter,
                           Qt.Key.Key_Space):
            self.details_requested.emit(self.key)
            return
        super().keyPressEvent(event)

    def set_active(self, on: bool):
        self._active = bool(on)
        self.mark.setVisible(self._active)
        self.update()

    def is_active(self) -> bool:
        return self._active

    def paintEvent(self, _e):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        r = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        rad = _rad(Sizing.RADIUS_MD)
        lit = self._hover or self._keyed
        if self._active:
            fill = QColor(Colors.ACCENT)
            fill.setAlpha(22)
            pen = QPen(QColor(Colors.ACCENT), 2)
            r = r.adjusted(0.5, 0.5, -0.5, -0.5)
        else:
            fill = QColor(Colors.BG_OVERLAY)
            pen = QPen(QColor(Colors.BORDER_STRONG if lit
                              else Colors.BORDER_SUBTLE), 1)
        p.setPen(pen)
        p.setBrush(fill)
        p.drawRoundedRect(r, rad, rad)
        p.end()


class _ConfigPlate(QWidget):
    """Beside the page title: the name of the config the settings match, a
    preset's or a saved one's, or CUSTOM when they match none."""

    _H = 24
    _PAD = 10
    _MAX = 24
    _TIPS = {
        "preset": ("The settings are the %s preset's. Change any of them "
                   "and the run is Custom."),
        "saved": ("The settings are your saved config '%s'. Change any of "
                  "them and the run is Custom."),
        "custom": ("No preset or saved config matches these settings. Apply "
                   "a preset or load a config to name the run."),
    }

    def __init__(self, parent=None):
        super().__init__(parent)
        self.kind = "custom"
        self.name = "Custom"
        self._shown = ""
        self._font = ui_font(Fonts.SIZE_XS, QFont.Weight.DemiBold)
        self._font.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, 1.2)
        self.setFixedHeight(self._H)
        self.set_identity("custom", "Custom")

    @staticmethod
    def _voxel() -> bool:
        try:
            from .skins import is_voxel
            return is_voxel()
        except Exception:
            return False

    def set_identity(self, kind: str, name: str):
        self.kind = kind if kind in self._TIPS else "custom"
        self.name = str(name or "Custom")
        self._shown = self.name[:self._MAX].upper()
        if self._voxel():
            from .voxel import pixel_text_width
            w = pixel_text_width(self._shown, 2)
        else:
            w = QFontMetrics(self._font).horizontalAdvance(self._shown)
        self.setFixedWidth(w + 2 * self._PAD)
        tip = self._TIPS[self.kind]
        self.setToolTip(tip % self.name if "%s" in tip else tip)
        self.update()

    def text(self) -> str:
        return self._shown

    def paintEvent(self, _e):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        r = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        named = self.kind != "custom"
        ink = Colors.ACCENT if named else Colors.TEXT_TERTIARY
        p.setPen(QPen(QColor(Colors.ACCENT_MUTED if named
                             else Colors.BORDER_STRONG), 1))
        if named:
            fill = QColor(Colors.ACCENT)
            fill.setAlpha(18)
            p.setBrush(fill)
        else:
            p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawRoundedRect(r, _rad(4), _rad(4))
        if self._voxel():
            from .voxel import draw_pixel_text, pixel_text_width
            tw = pixel_text_width(self._shown, 2)
            draw_pixel_text(p, (self.width() - tw) / 2.0,
                            (self.height() - 14) / 2.0, self._shown,
                            pixel=2, color=ink)
        else:
            p.setFont(self._font)
            p.setPen(QColor(ink))
            p.drawText(self.rect(), int(Qt.AlignmentFlag.AlignCenter),
                       self._shown)
        p.end()


class _StarterHead(QWidget):
    """A keyword's row label on the Starting gifts card: its icon and
    name."""

    def __init__(self, keyword: str, parent=None):
        super().__init__(parent)
        from .giftart import keyword_icon
        self._keyword = keyword
        pm = QPixmap(keyword_icon(keyword))
        self._pix = (pm.scaled(24, 24, Qt.AspectRatioMode.KeepAspectRatio,
                               Qt.TransformationMode.SmoothTransformation)
                     if not pm.isNull() else pm)
        self.setFixedWidth(120)
        self.setMinimumHeight(_StarterTile._H)

    def paintEvent(self, _e):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        x = Sizing.SPACE_XS
        if not self._pix.isNull():
            p.drawPixmap(x, (self.height() - self._pix.height()) // 2, self._pix)
        x += 24 + Sizing.SPACE_SM
        f = QFont(self.font())
        f.setWeight(QFont.Weight.DemiBold)
        p.setFont(f)
        p.setPen(QColor(Colors.TEXT_PRIMARY))
        p.drawText(QRect(x, 0, self.width() - x, self.height()),
                   int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter),
                   self._keyword)
        p.end()


class _StarterTile(QAbstractButton):
    """One starter E.G.O gift on the BUILD panel: its art and name, "usual
    pick" on the one the bot takes when nothing is picked, and an accent
    frame on the pick."""

    _ART = 44
    _H = 60
    _PAD = 8

    def __init__(self, name: str, usual: bool, parent=None):
        super().__init__(parent)
        self._name = name
        self._usual = bool(usual)
        self._hover = False
        self.setText(name)
        self.setCheckable(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setSizePolicy(QSizePolicy.Policy.Expanding,
                           QSizePolicy.Policy.Fixed)
        self.setMinimumWidth(220)
        self.setFixedHeight(self._H)
        self.setToolTip(name + (" (the usual pick)" if usual else ""))
        from .giftart import art_path
        pm = QPixmap(art_path(name))
        self._pix = (pm.scaled(self._ART, self._ART,
                               Qt.AspectRatioMode.KeepAspectRatio,
                               Qt.TransformationMode.SmoothTransformation)
                     if not pm.isNull() else pm)

    def name(self) -> str:
        return self._name

    def nextCheckState(self):
        pass                    # the page decides which tile is the pick

    def enterEvent(self, e):
        self._hover = True
        self.update()
        super().enterEvent(e)

    def leaveEvent(self, e):
        self._hover = False
        self.update()
        super().leaveEvent(e)

    def paintEvent(self, _e):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        r = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        on = self.isChecked()
        hover = self._hover
        bg = QColor(Colors.BG_OVERLAY if (on or hover)
                    else Colors.BG_RAISED)
        if hover:
            bg = bg.lighter(112)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(bg)
        p.drawRoundedRect(r, _rad(8), _rad(8))
        line = (Colors.ACCENT if on else
                Colors.BORDER_STRONG if hover else Colors.BORDER_SUBTLE)
        p.setPen(QPen(QColor(line), 1.5 if on else 1.0))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawRoundedRect(r, _rad(8), _rad(8))
        x = self._PAD
        if not self._pix.isNull():
            p.drawPixmap(x, (self._H - self._pix.height()) // 2, self._pix)
        x += self._ART + self._PAD
        width = self.width() - x - self._PAD
        tag = 14 if self._usual else 0
        f = QFont(self.font())
        f.setWeight(QFont.Weight.DemiBold if on else QFont.Weight.Medium)
        p.setFont(f)
        p.setPen(QColor(Colors.TEXT_PRIMARY if on else Colors.TEXT_SECONDARY))
        p.drawText(QRect(x, 5, width, self._H - 10 - tag),
                   int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter
                       | Qt.TextFlag.TextWordWrap), self._name)
        if self._usual:
            f.setPointSizeF(8.0)
            f.setWeight(QFont.Weight.Medium)
            p.setFont(f)
            p.setPen(QColor(Colors.ACCENT if on else Colors.TEXT_TERTIARY))
            p.drawText(QRect(x, self._H - 5 - tag, width, tag),
                       int(Qt.AlignmentFlag.AlignLeft
                           | Qt.AlignmentFlag.AlignVCenter), "usual pick")
        p.end()


class MirrorDungeonPage(QWidget):

    # Header + tab bar are pinned; each tab scrolls independently.
    manages_scroll = True

    start_requested = Signal()
    stop_requested = Signal()
    # Emitted by the "Go to custom run settings" link with the run whose
    # Settings card to show (SAIKAI or Hollow); the shell navigates there.
    open_team_settings = Signal(str)
    # The Basic view loaded a config or a preset: the shell re-reads every
    # page. And its link to the configs under Settings.
    config_loaded = Signal()
    open_settings = Signal()

    _TABS = ("General", "Build", "Floor Packs/Market", "EGO Gift Search")
    _VIEWS = ("Basic", "Advanced")

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("root")
        self._loading = False
        self._origin = {}            # the saved config the settings came from
        self._details = None         # the open run sheet, if any
        self._build()
        self._connect_persistence()
        self._restore_state()
        self._init_view()

    def refresh_theme(self):
        """Re-apply the per-widget stylesheets that bake tokens in at build
        time. themes._restyle_running_app rebuilds the GLOBAL sheet on a skin
        or theme switch, but a string already stored on a widget keeps its old
        values until the app restarts - which is how pockets of the previous
        look survived a live switch."""
        from .widgets import page_fill_qss
        for name in ("egoGiftsPage", "floorPage"):
            w = self.findChild(QWidget, name)
            if w is not None:
                w.setStyleSheet(f"QWidget#{name} {{ {page_fill_qss()} }}")

    def _build(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(
            Sizing.SPACE_XXL, Sizing.SPACE_XL, Sizing.SPACE_XXL, 0,
        )
        root.setSpacing(Sizing.SPACE_MD)

        # Pinned header: the Basic/Advanced switch, then Start and Stop.
        self._header = PageHeader("Mirror Dungeon", self)
        self._config_plate = _ConfigPlate(self._header)
        self._header.add_badge(self._config_plate)
        self._view = Segmented(list(self._VIEWS), default="Advanced", parent=self)
        self._view.selection_changed.connect(self._on_view)
        self._header.add_action(self._view)
        self._start_btn = PrimaryButton(
            seasonal.title("Start Mirror Dungeon"), self)
        self._start_btn.clicked.connect(self.start_requested.emit)
        self._header.add_action(self._start_btn)
        self._stop_btn = GhostButton("Stop", self)
        self._stop_btn.setEnabled(False)
        self._stop_btn.clicked.connect(self.stop_requested.emit)
        self._header.add_action(self._stop_btn)
        root.addWidget(self._header)

        # Pinned tab bar; the Advanced view only, with its rule.
        self._tabbar = IconlessTabBar(list(self._TABS), default="General", parent=self)
        self._tabbar.selection_changed.connect(self._on_tab)
        root.addWidget(self._tabbar)
        self._rule = HRule(self)
        root.addWidget(self._rule)

        # Which floors take the shop's skill offers: the General card's
        # strip, the All floors strip and each floor's switch share it.
        self._swap_floors = set(self._PS_FLOORS)
        self._swap_strips = []
        self._swap_labels = []
        self._swap_rows = {}
        self._syncing_swap = False

        # Tab content - each tab scrolls on its own.
        self._tab_stack = AnimatedStack(self)
        self._tab_stack.controller = self._tabbar
        # No explicit surface: AnimatedStack keeps the snapshot's alpha and
        # leaves the overlay clear on voxel, so the page backdrop (grid and
        # twinkle) stays visible under a sliding tab. Forcing a flat colour
        # here is what made the background vanish mid-transition.
        self._tab_stack.addWidget(self._scroll(self._build_general_tab()))
        self._tab_stack.addWidget(self._scroll(self._build_build_tab()))
        # The floor tab pins its floor bar and scrolls the rest itself.
        self._tab_stack.addWidget(self._build_floor_tab())
        # The EGO gift gallery manages its own internal scroll (pinned search/reset).
        self._tab_stack.addWidget(self._build_egogifts_tab())

        # Basic or Advanced: the presets and the saved configs, or the tabs.
        self._view_stack = QStackedWidget(self)
        self._view_stack.controller = self._view
        self._view_stack.addWidget(self._scroll(self._build_basic_view()))
        self._view_stack.addWidget(self._tab_stack)
        root.addWidget(self._view_stack, stretch=1)

    def _scroll(self, content: QWidget) -> QScrollArea:
        sa = QScrollArea(self)
        sa.setObjectName("pageScroll")
        sa.setWidgetResizable(True)
        sa.setFrameShape(QScrollArea.Shape.NoFrame)
        sa.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        sa.setWidget(content)
        return sa

    def _on_tab(self, label: str):
        if label in self._TABS:
            self._show_view("Advanced")         # the tabs are the Advanced view
            self._tab_stack.setCurrentIndex(self._TABS.index(label))

    # --- Basic / Advanced ------------------------------------------
    def _on_view(self, label: str):
        self._show_view(label)
        if not self._loading:
            save_section(_VIEW_SECTION, {"mode": label.lower()})

    def _show_view(self, label: str):
        advanced = label != "Basic"
        self._tabbar.setVisible(advanced)
        self._rule.setVisible(advanced)
        self._view_stack.setCurrentIndex(1 if advanced else 0)
        if self._view.selected() != label:
            self._view.set_selected(label)

    def _init_view(self):
        """Basic on a fresh install, else the view used last: an update
        leaves everyone where they were."""
        mode = (load_section(_VIEW_SECTION) or {}).get("mode")
        if mode not in ("basic", "advanced"):
            mode = "advanced" if load_section(_SECTION) else "basic"
        self._show_view(mode.capitalize())

    # --- Tabs ------------------------------------------------------
    def _build_general_tab(self) -> QWidget:
        page = QWidget()
        page.setObjectName("root")
        col = QVBoxLayout(page)
        col.setContentsMargins(0, Sizing.SPACE_LG, Sizing.SPACE_LG, Sizing.SPACE_XL)
        col.setSpacing(Sizing.SPACE_LG)

        # Two even columns of stacked cards: what to run on the left, how
        # to run it on the right. Each column packs its own cards, so a
        # short card never leaves a gap under a taller neighbour the way
        # the old 2x2 grid did.
        run, team = self._build_run_section(), self._build_team_section()
        difficulty = self._build_difficulty_section()
        custom = self._build_custom_run_section()
        row = QHBoxLayout()
        row.setSpacing(Sizing.SPACE_XXL)
        for cards in ((run, team), (difficulty, custom)):
            colw = _EvenColumn(page)
            stack = QVBoxLayout(colw)
            stack.setContentsMargins(0, 0, 0, 0)
            stack.setSpacing(Sizing.SPACE_LG)
            for card in cards:
                stack.addWidget(card)
            stack.addStretch(1)
            row.addWidget(colw, 1)
        col.addLayout(row)

        col.addWidget(self._build_behaviour_section())
        col.addWidget(self._build_skill_replace_section())
        col.addStretch(1)
        return page

    def _build_build_tab(self) -> QWidget:
        page = QWidget()
        page.setObjectName("root")
        col = QVBoxLayout(page)
        col.setContentsMargins(0, Sizing.SPACE_LG, Sizing.SPACE_LG, Sizing.SPACE_XL)
        col.setSpacing(Sizing.SPACE_LG)

        # Two filled columns: Starting Grace (wide) | Card Priority (narrow).
        side = QHBoxLayout()
        side.setSpacing(Sizing.SPACE_XXL)

        left = QVBoxLayout()
        left.setContentsMargins(0, 0, 0, 0)
        left.setSpacing(Sizing.SPACE_LG)
        left.addWidget(self._build_grace_section())
        left.addStretch(1)
        side.addLayout(left, stretch=3)

        right = QVBoxLayout()
        right.setContentsMargins(0, 0, 0, 0)
        right.setSpacing(Sizing.SPACE_LG)
        cards = self._build_cards_section()
        cards.setMinimumWidth(220)
        cards.setMaximumWidth(440)
        right.addWidget(cards)
        right.addStretch(1)
        side.addLayout(right, stretch=1)

        col.addLayout(side)
        col.addWidget(self._build_starter_section())
        col.addStretch(1)
        return page

    # --- Starting gifts -------------------------------------------
    def _build_starter_section(self) -> QWidget:
        from wbcore.starter_gifts import STARTER_GIFTS, usual_pick
        section = Card("STARTING GIFTS", self)
        host = QWidget(section)
        grid = QGridLayout(host)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setHorizontalSpacing(Sizing.SPACE_SM)
        grid.setVerticalSpacing(Sizing.SPACE_SM)
        self._starter_tiles = {}
        self._starter_pick = ""
        for r, (keyword, names) in enumerate(STARTER_GIFTS.items()):
            grid.addWidget(_StarterHead(keyword, host), r, 0)
            usual = usual_pick(keyword)
            self._starter_tiles[keyword] = {}
            for c, name in enumerate(names):
                tile = _StarterTile(name, name == usual, host)
                tile.clicked.connect(
                    lambda _c=False, n=name: self._on_starter(n))
                grid.addWidget(tile, r, 1 + c)
                self._starter_tiles[keyword][name] = tile
        for c in (1, 2, 3):
            grid.setColumnStretch(c, 1)
        section.body.addWidget(host)
        self._starter_card = section
        return section

    def showEvent(self, event):
        super().showEvent(event)
        self._refresh_team_warning()

    def _on_starter(self, name: str):
        # One pick in all, from any keyword's list; a second click clears it.
        self._set_starter_pick("" if self._starter_pick == name else name)
        self._save_state()

    def _set_starter_pick(self, name):
        name = str(name or "")
        tiles = [t for row in self._starter_tiles.values() for t in row.values()]
        self._starter_pick = name if any(t.name() == name for t in tiles) else ""
        for tile in tiles:
            tile.setChecked(tile.name() == self._starter_pick)

    # --- Floor Packs/Market ---------------------------------------
    _FLOOR_LABELS = ("All floors", "Floor 1", "Floor 2", "Floor 3",
                     "Floor 4", "Floor 5")
    _STEP_CHOICES = ("Default", "On", "Off")

    def _build_floor_tab(self) -> QWidget:
        """The shop and the packs in one tab. A pinned floor bar picks All
        floors (the run-wide market controls and shop steps) or one floor
        (its pack search, Hard switch and shop steps); the pack preferences
        and the market gift tags below follow the floor picked."""
        page = QWidget()
        page.setObjectName("floorPage")
        page.setStyleSheet(f"QWidget#floorPage {{ {page_fill_qss()} }}")
        outer = QVBoxLayout(page)
        outer.setContentsMargins(0, Sizing.SPACE_LG, 0, 0)
        outer.setSpacing(Sizing.SPACE_SM)
        self._floor_bar = IconlessTabBar(list(self._FLOOR_LABELS),
                                         default="All floors", parent=page)
        self._floor_bar.selection_changed.connect(self._on_floor)
        outer.addWidget(self._floor_bar)
        outer.addWidget(HRule(page))

        content = QWidget()
        content.setObjectName("root")
        col = QVBoxLayout(content)
        col.setContentsMargins(0, Sizing.SPACE_LG, Sizing.SPACE_LG, Sizing.SPACE_XL)
        col.setSpacing(Sizing.SPACE_LG)
        self._market_floor = None
        self._step_rows = {}
        self._ps_rows = {}
        self._ps_valid = {}
        self._ps_art = {}
        self._hard_rows = {}
        self._floor_stack = QStackedWidget(content)
        self._floor_stack.controller = self._floor_bar   # for the search
        self._floor_stack.addWidget(self._build_all_floors_page())
        for fl in self._PS_FLOORS:
            self._floor_stack.addWidget(self._build_floor_page(fl))
        self._apply_hard_switches()
        col.addWidget(self._floor_stack)
        col.addWidget(self._build_packs_section())
        col.addWidget(self._build_market_section())
        col.addStretch(1)
        outer.addWidget(self._scroll(content), 1)
        self._show_floor_page(None)
        return page

    def _build_all_floors_page(self) -> QWidget:
        page = StackPage()
        col = QVBoxLayout(page)
        col.setContentsMargins(0, 0, 0, 0)
        col.setSpacing(Sizing.SPACE_LG)
        col.addWidget(self._build_market_controls_section())
        col.addWidget(self._build_shop_steps_section())
        col.addWidget(self._build_swap_floors_section())
        col.addStretch(1)
        return page

    def _build_floor_page(self, fl: int) -> QWidget:
        page = StackPage()
        # The search names one PACK SEARCH panel: floor 1's.
        page.search_skip = fl != 1
        col = QVBoxLayout(page)
        col.setContentsMargins(0, 0, 0, 0)
        col.setSpacing(Sizing.SPACE_LG)
        col.addWidget(self._build_pack_search_section(fl))
        col.addWidget(self._build_floor_steps_section(fl))
        col.addWidget(self._build_floor_swap_section(fl))
        col.addStretch(1)
        return page

    def _two_columns(self, section, make_row, fixed=True):
        """Two columns of three shop step rows: on the behaviour rail, or
        sharing the width (a selector is wider than a switch, and a long
        title on the rail would squeeze it)."""
        cols = QHBoxLayout()
        cols.setSpacing(Sizing.SPACE_XXL)
        for half in (_SHOP_STEPS[:3], _SHOP_STEPS[3:]):
            colw = QWidget(section)
            if fixed:
                colw.setFixedWidth(_BEHAVIOUR_RAIL)
            else:
                colw.setMinimumWidth(_BEHAVIOUR_RAIL)
            col = QVBoxLayout(colw)
            col.setContentsMargins(0, 0, 0, 0)
            col.setSpacing(0)
            for key, title in half:
                col.addWidget(make_row(key, title))
            col.addStretch(1)
            cols.addWidget(colw, 0 if fixed else 1, Qt.AlignmentFlag.AlignTop)
        if fixed:
            cols.addStretch(1)
        return cols

    def _build_shop_steps_section(self) -> QWidget:
        section = Card("SHOP STEPS", self)
        self._shop_steps = {}

        def row(key, title):
            tog = Toggle(default=True, parent=section)
            self._shop_steps[key] = tog
            return SettingRow(title, tog, parent=section, rail=_BEHAVIOUR_RAIL)

        section.body.addLayout(self._two_columns(section, row))
        return section

    def _build_floor_steps_section(self, fl: int) -> QWidget:
        section = Card("SHOP STEPS", self)
        section.search_skip = True          # the All floors card is the feature
        rows = self._step_rows[fl] = {}

        def row(key, title):
            seg = Segmented(list(self._STEP_CHOICES), default="Default",
                            parent=section)
            seg.selection_changed.connect(self._save_state)
            rows[key] = seg
            return SettingRow(title, seg, parent=section)

        section.body.addLayout(self._two_columns(section, row, fixed=False))
        return section

    # --- Skill swap floors ----------------------------------------
    def _build_swap_floors_section(self) -> QWidget:
        section = Card("SKILL SWAP FLOORS", self)
        section.body.addLayout(self._swap_floors_row(section))
        return section

    def _build_floor_swap_section(self, fl: int) -> QWidget:
        section = Card("SKILL SWAP", self)
        section.search_skip = True          # the All floors card is the feature
        tog = Toggle(default=fl in self._swap_floors, parent=section)
        tog.toggled.connect(lambda on, f=fl: self._on_swap_row(f, on))
        self._swap_rows[fl] = tog
        section.body.addWidget(SettingRow(
            "Swap skills on this floor", tog, parent=section))
        return section

    def _swap_floors_row(self, parent) -> QHBoxLayout:
        """The five floors as switches, lit where the shop's skill offers
        are taken, and a line saying so."""
        row = QHBoxLayout()
        row.setSpacing(Sizing.SPACE_MD)
        picks = _FloorPicks(self._PS_FLOORS, parent=parent)
        picks.floor_toggled.connect(self._set_swap_floor)
        label = QLabel("", parent, objectName="inlineMeta")
        label.setWordWrap(True)
        self._swap_strips.append(picks)
        self._swap_labels.append(label)
        row.addWidget(picks)
        row.addWidget(label, 1)
        self._sync_swap_floors()
        return row

    def _on_swap_row(self, floor: int, on: bool):
        if self._syncing_swap:
            return
        self._set_swap_floor(floor, on)

    def _set_swap_floor(self, floor: int, on: bool):
        if on:
            self._swap_floors.add(int(floor))
        else:
            self._swap_floors.discard(int(floor))
        self._sync_swap_floors()
        self._save_state()

    def _sync_swap_floors(self):
        on = set(self._swap_floors)
        for picks in self._swap_strips:
            picks.set_floors(on)
        text = self._swap_floors_text()
        for label in self._swap_labels:
            label.setText(text)
        self._syncing_swap = True
        try:
            for fl, tog in self._swap_rows.items():
                tog.setChecked(fl in on)
        finally:
            self._syncing_swap = False

    def _swap_floors_text(self) -> str:
        on = set(self._swap_floors)
        if on == set(self._PS_FLOORS):
            return "Skills will be swapped on every shop."
        if not on:
            return "No floor picked: skills will not be swapped."
        return "Skills will be swapped on %s." % floors_phrase(on)

    def _on_floor(self, label: str):
        digits = "".join(ch for ch in label if ch.isdigit())
        floor = int(digits) if digits else None
        if floor == self._market_floor:
            return
        self._stash_floor_views()
        self._market_floor = floor
        self._show_floor_page(floor)
        if hasattr(self, "_floor_packs"):
            self._floor_packs.show_floor(floor)
        self._market_gallery.set_config(self._floor_tags(self._market_slot, floor))
        self._refresh_floor_captions()

    def _show_floor_page(self, floor):
        """Only the shown page counts for the stack's height, so a short
        floor page is not padded to the All floors page."""
        idx = 0 if floor is None else int(floor)
        for i in range(self._floor_stack.count()):
            pol = (QSizePolicy.Policy.Preferred if i == idx
                   else QSizePolicy.Policy.Ignored)
            self._floor_stack.widget(i).setSizePolicy(pol, pol)
        self._floor_stack.setCurrentIndex(idx)
        self._floor_stack.updateGeometry()

    def _refresh_floor_captions(self):
        fl = self._market_floor
        self._market_scope.setText("All floors" if fl is None else "Floor %d" % fl)

    def _floor_tags(self, slot, floor) -> dict:
        """The stored tags of `slot` for a floor (None = the run-wide ones)."""
        if floor is None:
            return dict(self._market_slots.get(slot) or {})
        ent = (self._market_floors.get(slot) or {}).get(floor) or {}
        return dict(ent.get("tags") or {})

    def _stash_floor_views(self):
        """Copy what the shared gallery and the floor pages show into the
        active slot's store, so another floor or slot can take them over."""
        if not hasattr(self, "_market_gallery"):
            return
        slot, floor = self._market_slot, self._market_floor
        cfg = self._market_gallery.config()
        floors = self._market_floors.setdefault(slot, {})
        if floor is None:
            self._market_slots[slot] = cfg
        else:
            ent = floors.setdefault(floor, {})
            if any(cfg.get(m) for m in _MARKET_MODE_KEYS):
                ent["tags"] = cfg
            else:
                ent.pop("tags", None)
        for fl, segs in self._step_rows.items():
            steps = {key: seg.selected() == "Off"
                     for key, seg in segs.items() if seg.selected() != "Default"}
            ent = floors.setdefault(fl, {})
            if steps:
                ent["steps"] = steps
            else:
                ent.pop("steps", None)
        for fl in [f for f, ent in floors.items() if not ent]:
            floors.pop(fl)

    def _load_floor_views(self):
        """Show the active slot: the gallery for the current floor and every
        floor page's shop steps."""
        slot = self._market_slot
        self._market_gallery.set_config(self._floor_tags(slot, self._market_floor))
        floors = self._market_floors.get(slot) or {}
        for fl, segs in self._step_rows.items():
            steps = (floors.get(fl) or {}).get("steps") or {}
            for key, seg in segs.items():
                val = steps.get(key)
                seg.set_selected("Default" if val is None else "Off" if val else "On")

    def _market_floors_state(self) -> dict:
        """Per-floor market tags and shop steps by slot, floors as strings
        for JSON; slots and floors with nothing set are left out."""
        if not hasattr(self, "_market_gallery"):
            return {}
        self._stash_floor_views()
        out = {}
        for slot, floors in self._market_floors.items():
            if floors:
                out[slot] = {
                    str(fl): {k: ({m: list(v.get(m) or []) for m in _MARKET_MODE_KEYS}
                                  if k == "tags" else dict(v))
                              for k, v in ent.items()}
                    for fl, ent in sorted(floors.items())}
        return out

    # --- Difficulty -----------------------------------------------
    def _build_difficulty_section(self) -> QWidget:
        section = Card("DIFFICULTY", self, collapsible=True)
        self._difficulty = Segmented(
            ["Normal", "Hard", "Extreme"], default="Hard", parent=section,
        )
        self._difficulty.set_locked("Extreme", "Extreme is work in progress.")
        self._difficulty.selection_changed.connect(self._on_difficulty)
        # The floor the run flips to Hard on (None: Normal throughout). The
        # Difficulty control mirrors it: Hard is a flip on floor 1.
        self._hard_from = 1
        self._syncing_difficulty = False
        # Pin the segmented to its natural width (left-aligned).
        row = QHBoxLayout()
        row.addWidget(self._difficulty)
        row.addStretch(1)
        section.body.addLayout(row)

        # The five floors, lit where the run is Hard; a click flips the run
        # there, the same as the floor's Hard switch under Floor Packs/Market.
        floors = QHBoxLayout()
        floors.setSpacing(Sizing.SPACE_MD)
        self._floor_strip = _FloorStrip(parent=section)
        self._floor_strip.floor_clicked.connect(
            lambda f: self._on_hard_switch(f, not self._floor_is_hard(f)))
        floors.addWidget(self._floor_strip)
        self._hard_from_label = QLabel("", section, objectName="inlineMeta")
        floors.addWidget(self._hard_from_label)
        floors.addStretch(1)
        section.body.addSpacing(Sizing.SPACE_XS)
        section.body.addLayout(floors)
        self._sync_floor_strip()
        return section

    def _sync_floor_strip(self):
        strip = getattr(self, "_floor_strip", None)
        if strip is None:
            return
        strip.set_hard_from(self._hard_from)
        if self._hard_from is None:
            text = "Normal throughout"
        elif self._hard_from == 1:
            text = "Hard throughout"
        else:
            text = "Normal, then Hard from floor %d" % self._hard_from
        self._hard_from_label.setText(text)

    def _on_difficulty(self, label: str):
        if self._syncing_difficulty:
            return
        # Hard is a flip on floor 1; Normal starts over with no flip, the
        # floor switches set one again.
        if label == "Hard":
            self._hard_from = 1
        elif label == "Normal":
            self._hard_from = None
        self._apply_hard_switches()
        self._refresh_pools()

    # --- Hard from a floor ---------------------------------------
    def _floor_is_hard(self, floor: int) -> bool:
        return self._hard_from is not None and floor >= self._hard_from

    def _seed_flip(self, label=None):
        """A custom run picked: its switches start from the run's own flip
        (Hollow and SAIKAI by their sheets) and stay the user's to change."""
        if getattr(self, "_loading", False) or not self._custom_run.isChecked():
            return
        seeds = {HOLLOW_LABEL: 5, SAIKAI_LABEL: 4}
        label = label or self._custom_strategy.selected()
        if label not in seeds:
            return
        self._hard_from = seeds[label]
        self._apply_hard_switches()
        self._refresh_pools()
        self._save_state()

    def _apply_hard_switches(self):
        """Every floor from the flip on reads Hard; the floors after the
        flip are locked (Hard cannot go back to Normal), the flip floor and
        the ones before it are free. The Difficulty control follows."""
        self._sync_floor_strip()
        rows = getattr(self, "_hard_rows", None)
        if not rows:
            return
        # The toggle slides its knob from its own toggled signal, so the
        # signals stay on and the handler sits out this pass.
        self._applying_hard = True
        try:
            for floor, tog in rows.items():
                tog.setChecked(self._floor_is_hard(floor))
        finally:
            self._applying_hard = False
        for floor, tog in rows.items():
            free = self._hard_from is None or floor <= self._hard_from
            tog.setEnabled(free)
            tog.setToolTip("" if free else "Hard from floor %d; switch that floor "
                           "off first." % self._hard_from)
        want = "Hard" if self._hard_from == 1 else "Normal"
        if self._difficulty.selected() != want:
            self._syncing_difficulty = True
            try:
                self._difficulty.set_selected(want)
            finally:
                self._syncing_difficulty = False

    def _on_hard_switch(self, floor: int, on: bool):
        if getattr(self, "_applying_hard", False):
            return
        if on:
            if self._hard_from is None or floor < self._hard_from:
                self._hard_from = floor
        elif floor == self._hard_from:
            self._hard_from = None
        self._apply_hard_switches()
        self._refresh_pools()
        self._save_state()

    def _refresh_pools(self):
        """Each floor lists the packs of its own difficulty."""
        if not hasattr(self, "_floor_packs"):
            return
        data, banned = {}, {}
        for floor in range(1, 6):
            hard = self._floor_is_hard(floor)
            data[floor] = list((HARD_FLOORS if hard else FLOORS).get(floor, []))
            banned[floor] = HARD_BANNED if hard else BANNED
        self._floor_packs.set_data(data, banned_by_floor=banned)
        self._floor_packs.show_floor(getattr(self, "_market_floor", None))

    # --- Custom run -----------------------------------------------
    def _build_custom_run_section(self) -> QWidget:
        # On/off lives in the card header (top-right).
        self._custom_run = Toggle(default=False, parent=self)
        self._custom_run.toggled.connect(self._on_custom_run)
        section = Card("CUSTOM RUN", self, trailing=self._custom_run,
                       collapsible=True)

        self._custom_strategy = Segmented(
            [SAIKAI_LABEL, HOLLOW_LABEL],
            default=SAIKAI_LABEL, parent=section)
        # Each run wears the emblem of the sinner it is built around.
        from .giftart import sinner_icon
        for label, icon in ((SAIKAI_LABEL, QIcon(sinner_icon("Ryōshū"))),
                            (HOLLOW_LABEL, QIcon(sinner_icon("Faust")))):
            btn = self._custom_strategy._buttons[label]
            btn.setIcon(icon)
            btn.setIconSize(QSize(18, 18))
        section.body.addWidget(self._custom_strategy)

        self._team_link = LinkButton("Go to custom run settings", section)
        self._team_link.clicked.connect(self._open_team_settings)
        self._team_link.setVisible(False)
        section.body.addWidget(self._team_link)

        # Exactly one of {difficulty, custom strategy} is interactive.
        self._apply_custom_run(self._custom_run.isChecked())
        return section

    def _on_custom_run(self, on: bool):
        self._apply_custom_run(on)
        self._save_state()

    def _apply_custom_run(self, on: bool):
        """Grey out whichever selector is not in charge."""
        if hasattr(self, "_difficulty"):
            self._difficulty.set_interactive(not on)
        if hasattr(self, "_custom_strategy"):
            self._custom_strategy.set_interactive(on)
        self._sync_run()

    def _open_team_settings(self, *_):
        hollow = self._custom_strategy.selected() == HOLLOW_LABEL
        self.open_team_settings.emit("Hollow" if hollow else "SAIKAI")

    def _sync_run(self, *_):
        """The page follows the custom run picked: its team link, its own
        market tag and grace slots and, on a pick made by hand, the gifts
        its sheet searches for (SAIKAI's Spiderweb ahead of the picks,
        Hollow's two in place of them, so no earlier config bleeds into its
        run; Hollow's Torn Bandolier comes from the starter screen). They
        are ordinary picks from there, and a run left takes its own off."""
        if hasattr(self, "_team_link"):
            self._team_link.setVisible(
                self._custom_run.isChecked()
                and self._custom_strategy.selected() in (
                    SAIKAI_LABEL, HOLLOW_LABEL))
        saikai = (self._custom_run.isChecked()
                  and self._custom_strategy.selected() == SAIKAI_LABEL)
        hollow = (self._custom_run.isChecked()
                  and self._custom_strategy.selected() == HOLLOW_LABEL)
        self._refresh_team_warning()
        if hasattr(self, "_market_gallery"):
            # Swap the gallery and the floor pages to the strategy's slot
            # (state() serializes the inactive slots from the stores, so no
            # save is needed here). Hollow's slot starts as the sheet's plan.
            want = "saikai" if saikai else "hollow" if hollow else "normal"
            if want != self._market_slot:
                self._stash_floor_views()
                self._market_slot = want
                if want == "saikai" and self._market_slots.get("saikai") is None:
                    self._market_slots["saikai"] = self._saikai_market_seed()
                if want == "hollow":
                    self._seed_hollow_slot()
                self._load_floor_views()
        if hasattr(self, "_grace_chips") and not self._loading:
            # Hollow keeps its own graces, seeded with the sheet's pair, so
            # the other runs' picks survive a switch either way.
            slot = "hollow" if hollow else "normal"
            if slot != self._grace_slot:
                self._grace_slots[self._grace_slot] = {
                    n: c.state() for n, c in self._grace_chips.items()}
                self._grace_slot = slot
                picks = self._grace_slots.get(slot)
                if picks is None and slot == "hollow":
                    picks = dict(HOLLOW_GRACE_SEED)
                if picks is not None:
                    for n, c in self._grace_chips.items():
                        c.set_state(int(picks.get(n, 0) or 0))
                self._refresh_grace_controls()
        if not hasattr(self, "_gift_gallery"):
            return
        strategy = (SAIKAI_LABEL if saikai else HOLLOW_LABEL if hollow
                    else None)
        before = getattr(self, "_gift_run", None)
        if strategy != before and not self._loading:
            left = RUN_SEARCH_GIFTS.get(before, ())
            picks = [] if hollow else [n for n in self._gift_gallery.selected()
                                       if n not in left]
            self._gift_gallery.set_selected(
                list(RUN_SEARCH_GIFTS.get(strategy, ())) + picks)
        self._gift_run = strategy

    # --- Team rotation --------------------------------------------
    def _build_team_section(self) -> QWidget:
        add_btn = LinkButton("+ Add team", self)
        add_btn.clicked.connect(self._add_team)
        section = Card("TEAM ROTATION", self, trailing=add_btn,
                       collapsible=True)
        self._team_section = section

        self._teams = [
            {"name": "Burn", "affinities": ["Burn", "Wrath"]},
            {"name": "Rupture", "affinities": ["Rupture", "Envy"]},
            {"name": "Slash", "affinities": ["Slash"]},
        ]
        self._team_rows_container = QVBoxLayout()
        self._team_rows_container.setContentsMargins(0, 0, 0, 0)
        self._team_rows_container.setSpacing(Sizing.SPACE_XXS)
        section.body.addLayout(self._team_rows_container)
        self._rebuild_team_rows()
        return section

    def _rebuild_team_rows(self):
        while self._team_rows_container.count():
            item = self._team_rows_container.takeAt(0)
            w = item.widget()
            if w is not None:
                w.setParent(None)
                w.deleteLater()
        for i, team in enumerate(self._teams):
            row = _TeamRow(team["name"], team.get("affinities", []),
                           parent=self._team_section)
            row.edit_requested.connect(
                lambda _n, idx=i: self._edit_team(idx))
            row.remove_requested.connect(
                lambda _n, idx=i: self._remove_team(idx))
            self._team_rows_container.addWidget(row)

    def _add_team(self):
        dlg = TeamEditDialog(parent=self)
        if dlg.exec():
            self._teams.append(dlg.team())
            self._rebuild_team_rows()
            self._save_state()

    def _edit_team(self, idx: int):
        if not (0 <= idx < len(self._teams)):
            return
        dlg = TeamEditDialog(self._teams[idx], parent=self)
        if dlg.exec():
            self._teams[idx] = dlg.team()
            self._rebuild_team_rows()
            self._save_state()

    def _remove_team(self, idx: int):
        if 0 <= idx < len(self._teams):
            self._teams.pop(idx)
            self._rebuild_team_rows()
            self._save_state()

    # --- Persistence ---------------------------------------------
    def _connect_persistence(self):
        self._difficulty.selection_changed.connect(self._save_state)
        # custom_run saves via _on_custom_run.
        self._custom_strategy.selection_changed.connect(self._sync_run)
        self._custom_strategy.selection_changed.connect(self._save_state)
        self._custom_strategy.selection_changed.connect(
            lambda label: self._seed_flip(label))
        self._custom_run.toggled.connect(
            lambda on: self._seed_flip() if on else None)
        for sb in (self._run_count, self._retry_count, self._pack_refreshes):
            sb.valueChanged.connect(self._save_state)
        for tog in self._behaviour.values():
            tog.toggled.connect(self._save_state)
        for tog in self._shop_steps.values():
            tog.toggled.connect(self._save_state)
        for chip in self._grace_chips.values():
            chip.state_changed.connect(self._save_state)
        self._card_priority.changed.connect(self._save_state)
        self._floor_packs.changed.connect(self._save_state)

    def state(self) -> dict:
        """Current Mirror Dungeon config as a dict (persisted and consumed
        by run_config)."""
        return {
            "difficulty": self._difficulty.selected(),
            "hard_from_floor": int(self._hard_from or 0),
            "custom_run": self._custom_run.isChecked(),
            "custom_strategy": self._custom_strategy.selected(),
            "gift_search": self._gift_search_selection(),
            "market_gifts": self._market_slot_cfg("normal"),
            "market_gifts_saikai": self._market_slot_cfg("saikai"),
            "market_gifts_hollow": self._market_slot_cfg("hollow"),
            "market_controls": self._market_controls_config(),
            "market_floors": self._market_floors_state(),
            "skill_replace": {
                "active":  sorted(self._skill_active),
                "order":   {n: list(order)
                            for n, order in self._skill_order.items()},
                "repeats": {n: dict(rep)
                            for n, rep in self._skill_repeats.items()},
                "skip_floors": sorted(set(self._PS_FLOORS) - self._swap_floors),
            },
            "run_count": self._run_count.value(),
            "retry_count": self._retry_count.value(),
            "pack_refreshes": self._pack_refreshes.value(),
            # The shop steps are stored as the skips the backend reads.
            "behaviour": {
                **{k: t.isChecked() for k, t in self._behaviour.items()},
                **{k: not t.isChecked() for k, t in self._shop_steps.items()},
            },
            "teams": self._teams,
            "grace": {n: c.state() for n, c in self._grace_chips.items()},
            "starter_gift": self._starter_pick,
            "grace_slots": {
                **{k: v for k, v in self._grace_slots.items() if v is not None},
                self._grace_slot: {n: c.state() for n, c in self._grace_chips.items()},
            },
            "card": self._card_priority.order(),
            "packs": self._floor_packs.state(),
            "global_packs": self._floor_packs.global_state(),
            "pack_search_cfg": {
                "floors": {
                    str(fl): {"enabled": tog.isChecked(),
                              "pack": self._ps_valid.get(fl, "")}
                    for fl, (tog, _e) in self._ps_rows.items()
                },
            },
        }

    def _save_state(self, *_):
        if self._loading:
            return
        state = self.state()
        save_section(_SECTION, state)
        self._refresh_identity(state)

    def _restore_state(self):
        self._origin = dict(load_section(_IDENTITY_SECTION) or {})
        self._restore_md_state()
        if hasattr(self, "_preset_marks"):
            self._refresh_basic()

    # --- which config the settings are ------------------------------
    def _preset_matches(self, key: str, state=None) -> bool:
        """Whether every setting the preset writes still holds, compared
        the way the preset lays them down: a dict one key at a time, so
        what it leaves alone does not count."""
        from . import presets
        preset = presets.get(key)
        if preset is None:
            return False
        state = state if state is not None else self.state()
        for name, value in preset["mirror"].items():
            value = value() if callable(value) else value
            if name == "packs" and hasattr(self, "_floor_packs"):
                value = self._floor_packs.offered(value)
            if isinstance(value, dict):
                current = _norm(state.get(name), name) or {}
                for k, v in value.items():
                    if _norm(v, str(k)) != current.get(str(k)):
                        return False
            elif _norm(value, name) != _norm(state.get(name), name):
                return False
        return True

    def _fingerprint(self, state=None) -> str:
        """The settings as one string, the run count left out: how many
        runs to do is not part of what a config is."""
        import hashlib
        import json
        state = state if state is not None else self.state()
        trimmed = {k: v for k, v in state.items() if k != "run_count"}
        return hashlib.sha1(json.dumps(_norm(trimmed), sort_keys=True,
                                       default=str).encode()).hexdigest()

    def _set_origin(self, name, fingerprint=None):
        """Remember the saved config the settings came from, or forget it
        (None). The fingerprint is taken at the next refresh when not
        given, once the loaded settings are on the page."""
        self._origin = ({"saved": str(name), "fingerprint": fingerprint}
                        if name else {})
        save_section(_IDENTITY_SECTION, dict(self._origin))

    def _identity(self, state, matches) -> tuple:
        """(kind, name): the saved config loaded or saved and untouched
        since, else the preset the settings are, else Custom."""
        from . import presets
        name = self._origin.get("saved")
        if name and self._origin.get("fingerprint") == self._fingerprint(state):
            return "saved", str(name)
        for preset in presets.PRESETS:
            if matches.get(preset["key"]):
                return "preset", preset["title"]
        return "custom", "Custom"

    def _refresh_identity(self, state=None):
        if not hasattr(self, "_config_plate"):
            return
        state = state if state is not None else self.state()
        if self._origin.get("saved") and not self._origin.get("fingerprint"):
            self._origin["fingerprint"] = self._fingerprint(state)
            save_section(_IDENTITY_SECTION, dict(self._origin))
        cards = getattr(self, "_preset_buttons", {})
        matches = {key: self._preset_matches(key, state) for key in cards}
        for key, card in cards.items():
            card.set_active(matches[key])
        self._config_plate.set_identity(*self._identity(state, matches))
        self._refresh_team_warning()

    def _restore_md_state(self):
        s = load_section(_SECTION)
        if not s:
            return
        self._loading = True
        try:
            diff = s.get("difficulty")
            if diff == "Extreme":
                diff = "Hard"                    # Extreme is work in progress
            if diff in ("Normal", "Hard"):
                self._difficulty.set_selected(diff)
            try:
                flip = int(s.get("hard_from_floor") or 0)
            except (TypeError, ValueError):
                flip = 0
            if diff == "Hard" or not (1 <= flip <= 5):
                flip = 1 if diff == "Hard" else 0      # an older save: Hard is floor 1
            self._hard_from = flip if 1 <= flip <= 5 else None
            self._apply_hard_switches()
            self._refresh_pools()
            strat = s.get("custom_strategy")
            if strat == "F3 Hard":
                # The retired F3 Hard custom run was Normal, then Hard from
                # floor 3: a save that used it loads as that flip, with no
                # custom run.
                strat = ""
                if s.get("custom_run"):
                    s = dict(s, custom_run=False)
                    self._hard_from = 3
                    self._apply_hard_switches()
                    self._refresh_pools()
            if strat:
                self._custom_strategy.set_selected(strat)
            gs = s.get("gift_search")
            if isinstance(gs, list) and hasattr(self, "_gift_gallery"):
                self._gift_gallery.set_selected(
                    [n for n in gs if isinstance(n, str)])
            if hasattr(self, "_market_gallery"):
                mkt = s.get("market_gifts")
                self._market_slots["normal"] = \
                    mkt if isinstance(mkt, dict) else {}
                sk = s.get("market_gifts_saikai")
                self._market_slots["saikai"] = \
                    sk if isinstance(sk, dict) else None
                hk = s.get("market_gifts_hollow")
                self._market_slots["hollow"] = \
                    hk if isinstance(hk, dict) else None
                saikai = (bool(s.get("custom_run"))
                          and s.get("custom_strategy") == SAIKAI_LABEL)
                hollow = (bool(s.get("custom_run"))
                          and s.get("custom_strategy") == HOLLOW_LABEL)
                self._market_slot = ("saikai" if saikai
                                     else "hollow" if hollow else "normal")
                self._gift_run = (
                    SAIKAI_LABEL if saikai else HOLLOW_LABEL if hollow
                    else None)
                self._market_floors = _clean_market_floors(s.get("market_floors"))
                if self._market_slot == "saikai" and self._market_slots["saikai"] is None:
                    self._market_slots["saikai"] = self._saikai_market_seed()
                if self._market_slot == "hollow":
                    self._seed_hollow_slot()
                self._load_floor_views()
            ps = s.get("pack_search_cfg")
            if hasattr(self, "_ps_rows"):
                floors = (ps or {}).get("floors") if isinstance(ps, dict) else {}
                floors = floors if isinstance(floors, dict) else {}
                for fl, (tog, edit) in self._ps_rows.items():
                    ent = floors.get(str(fl))
                    ent = ent if isinstance(ent, dict) else {}
                    name = ent.get("pack") or ""
                    if name not in _pack_search_names_for_floor(fl):
                        name = ""
                    self._ps_valid[fl] = name
                    edit.setText(name)
                    tog.setChecked(bool(ent.get("enabled", False)))
            mc = s.get("market_controls")
            if hasattr(self, "_default_market_workflow"):
                mc = mc if isinstance(mc, dict) else {}
                self._default_market_workflow.setChecked(
                    bool(mc.get("default_market_workflow", True)))
                self._market_refresh_count.setValue(
                    int(mc.get("refresh_count", 0) or 0))
                self._market_refresh_until_cost.setChecked(
                    bool(mc.get("refresh_until_cost", False)))
                self._buy_ego_fuel.setChecked(
                    bool(mc.get("buy_ego_fuel", False)))
                self._sync_market_controls()
            skill = s.get("skill_replace")
            if isinstance(skill, dict) and hasattr(self, "_skill_chips"):
                active = skill.get("active") or []
                if isinstance(active, list):
                    self._skill_active = {
                        n for n in active if n in self._skill_chips
                    }
                    for n, chip in self._skill_chips.items():
                        chip.set_active(n in self._skill_active)
                valid_keys = {k for k, _ in self._SKILL_REPLACE_SWAPS}
                order = skill.get("order")
                if isinstance(order, dict):
                    for n, entries in order.items():
                        if n not in self._skill_order:
                            continue
                        if not isinstance(entries, list):
                            continue
                        cleaned = [k for k in entries if k in valid_keys]
                        # Append any missing keys so all 3 swaps stay present.
                        for k in self._SKILL_REPLACE_DEFAULT_ORDER:
                            if k not in cleaned:
                                cleaned.append(k)
                        self._skill_order[n] = cleaned
                repeats = skill.get("repeats")
                if isinstance(repeats, dict):
                    for n, rep_map in repeats.items():
                        if n not in self._skill_repeats:
                            continue
                        if not isinstance(rep_map, dict):
                            continue
                        for k, v in rep_map.items():
                            if k in valid_keys:
                                try:
                                    self._skill_repeats[n][k] = int(v or 0)
                                except (TypeError, ValueError):
                                    pass
                self._render_skill_details()
            skipped = skill.get("skip_floors") if isinstance(skill, dict) else None
            self._swap_floors = set(self._PS_FLOORS) - skip_floor_set(skipped)
            self._sync_swap_floors()
            cr = bool(s.get("custom_run", False))
            self._custom_run.setChecked(cr)
            self._apply_custom_run(cr)
            for key, sb in (("run_count", self._run_count),
                            ("retry_count", self._retry_count),
                            ("pack_refreshes", self._pack_refreshes)):
                if key in s:
                    sb.setValue(int(s[key]))
            for k, v in (s.get("behaviour") or {}).items():
                if k in self._behaviour:
                    self._behaviour[k].setChecked(bool(v))
                elif k in self._shop_steps:
                    self._shop_steps[k].setChecked(not bool(v))
            self._behaviour["bonus_one"].setEnabled(self._behaviour["bonus"].isChecked())
            teams = s.get("teams")
            if isinstance(teams, list) and teams:
                self._teams = teams
                self._rebuild_team_rows()
            slots = s.get("grace_slots")
            if isinstance(slots, dict):
                for k in ("normal", "hollow"):
                    v = slots.get(k)
                    self._grace_slots[k] = v if isinstance(v, dict) else None
            self._grace_slot = ("hollow" if (bool(s.get("custom_run"))
                                             and s.get("custom_strategy") == HOLLOW_LABEL)
                                else "normal")
            for n, st in (s.get("grace") or {}).items():
                if n in self._grace_chips:
                    self._grace_chips[n].set_state(int(st))
            if self._grace_slot == "hollow" and not isinstance(slots, dict):
                # First start since Hollow got its own graces: the chips held
                # the other runs' picks, and Hollow starts from the sheet's pair.
                self._grace_slots["normal"] = {
                    n: c.state() for n, c in self._grace_chips.items()}
                for n, c in self._grace_chips.items():
                    c.set_state(int(HOLLOW_GRACE_SEED.get(n, 0)))
            self._refresh_grace_controls()
            self._set_starter_pick(s.get("starter_gift"))
            card = s.get("card")
            if isinstance(card, list) and card:
                self._card_priority.set_state(card, [])
            self._floor_packs.reset()
            if s.get("packs"):
                self._floor_packs.apply_state(s["packs"])
            if s.get("global_packs"):
                self._floor_packs.apply_global_state(s["global_packs"])
        except (TypeError, ValueError):
            pass
        finally:
            self._loading = False
        # Programmatic set_selected above does not emit selection_changed, so
        # re-derive what follows the run picked (market slot, graces, link).
        self._sync_run()

    # --- Basic view -------------------------------------------------
    def _build_basic_view(self) -> QWidget:
        page = QWidget()
        page.setObjectName("root")
        col = QVBoxLayout(page)
        col.setContentsMargins(0, 0, Sizing.SPACE_LG, Sizing.SPACE_XL)
        col.setSpacing(Sizing.SPACE_LG)
        col.addWidget(self._build_presets_section())
        col.addWidget(self._build_basic_run_section())
        col.addWidget(self._build_configs_section())
        col.addStretch(1)
        return page

    def _build_presets_section(self) -> QWidget:
        from . import presets
        self._team_button = GhostButton("Go to custom run settings", self)
        self._team_button.search_skip = True    # the Advanced link is the feature
        self._team_button.clicked.connect(self._open_team_settings)
        section = Card("PRESETS", self, trailing=self._team_button)
        self._team_warn = QLabel("", section, objectName="presetMark")
        self._team_warn.setWordWrap(True)
        self._team_warn.setVisible(False)
        section.body.addWidget(self._team_warn)
        self._preset_marks = {}
        self._preset_buttons = {}
        cards = QWidget(section)
        flow = FlowLayout(cards, spacing=Sizing.SPACE_MD)
        for preset in presets.PRESETS:
            card = _PresetCard(preset, cards)
            card.details_requested.connect(self._show_preset_details)
            card.apply_requested.connect(self._use_preset)
            flow.addWidget(card)
            self._preset_marks[preset["key"]] = card.mark
            self._preset_buttons[preset["key"]] = card
        section.body.addWidget(cards)
        self._custom_run.toggled.connect(self._refresh_preset_marks)
        self._custom_strategy.selection_changed.connect(self._refresh_preset_marks)
        self._refresh_team_warning()
        return section

    def _refresh_preset_marks(self, *_):
        self._refresh_identity()

    def _show_preset_details(self, key: str):
        from . import presets
        preset = presets.get(key)
        if preset is None:
            return
        if self._details is not None:
            try:
                self._details.close()
            except RuntimeError:
                pass
        dlg = PresetDetailsDialog(preset, self.window())
        dlg.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, True)
        dlg.apply_requested.connect(self._use_preset)
        dlg.finished.connect(lambda *_: setattr(self, "_details", None))
        self._details = dlg
        dlg.show()

    def _selected_team(self):
        """The scripted run the custom run controls have picked, by its
        Settings name, or None."""
        if not self._custom_run.isChecked():
            return None
        return {SAIKAI_LABEL: "SAIKAI", HOLLOW_LABEL: "Hollow"}.get(
            self._custom_strategy.selected())

    @staticmethod
    def _team_configured(run) -> bool:
        """Whether the run's team was ever set up under Settings: the saved
        flag, or an order from before the flag existed."""
        teams = (load_section("app_settings") or {}).get("custom_teams") or {}
        team = teams.get(run) or {}
        if "configured" in team:
            return bool(team["configured"])
        return bool(team.get("order"))

    def _refresh_team_warning(self):
        if not hasattr(self, "_team_warn"):
            return
        run = self._selected_team()
        text = ""
        if run and not self._team_configured(run):
            text = ("%s has not been configured. Default settings will be "
                    "used." % run.upper())
        self._team_warn.setText(text)
        self._team_warn.setVisible(bool(text))

    def _use_preset(self, key: str):
        """Write the preset, let the shell reload every page, then offer
        the custom run settings (sinner order, the swap list, the team's
        keyword) before the defaults stand."""
        from . import presets
        preset = presets.get(key)
        if preset is None or not presets.apply(key):
            return
        self._set_origin(None)
        self._basic_note(
            "%s is set up. Build the team in game, then start."
            % preset["title"])
        self.config_loaded.emit()
        run = next(iter(preset.get("teams") or {}), None)
        answer = ask_choice(self, MD_PRESET_APPLIED_TEXT, MD_PRESET_APPLIED_TITLE,
                            "Go to custom run settings", "Continue anyway")
        if answer == "primary" and run:
            self.open_team_settings.emit(run)

    def _build_basic_run_section(self) -> QWidget:
        section = Card("RUN COUNT", self)
        section.search_skip = True          # the General tab's card is the feature
        row = QHBoxLayout()
        row.setSpacing(Sizing.SPACE_SM)
        self._basic_runs = QSpinBox(section)
        self._basic_runs.setObjectName("runCount")
        self._basic_runs.setRange(1, 9999)
        self._basic_runs.setFixedWidth(120)
        self._basic_runs.setValue(self._run_count.value())
        self._basic_runs.valueChanged.connect(self._run_count.setValue)
        self._run_count.valueChanged.connect(self._basic_runs.setValue)
        row.addWidget(self._basic_runs)
        row.addWidget(QLabel("runs", section))
        row.addSpacing(Sizing.SPACE_LG)
        forever = LinkButton("Loop forever", section)
        forever.clicked.connect(lambda: self._run_count.setValue(9999))
        row.addWidget(forever)
        row.addStretch(1)
        section.body.addLayout(row)
        return section

    def _build_configs_section(self) -> QWidget:
        section = Card("YOUR CONFIGS", self)
        self._config_rows_box = QWidget(section)
        self._config_rows_box.search_skip = True      # the list changes
        self._config_rows = QVBoxLayout(self._config_rows_box)
        self._config_rows.setContentsMargins(0, 0, 0, 0)
        self._config_rows.setSpacing(Sizing.SPACE_XS)
        section.body.addWidget(self._config_rows_box)
        self._configs_empty = QLabel("Nothing saved yet.", section,
                                     objectName="inlineMeta")
        section.body.addWidget(self._configs_empty)
        self._config_load_buttons = {}
        save_row = QHBoxLayout()
        save_row.setSpacing(Sizing.SPACE_SM)
        self._config_name = QLineEdit(section)
        self._config_name.setObjectName("textField")
        self._config_name.setPlaceholderText("Name the current setup…")
        self._config_name.setMinimumWidth(260)
        self._config_name.setMaximumWidth(320)
        self._config_name.returnPressed.connect(self._save_basic_config)
        save_row.addWidget(self._config_name)
        save = GhostButton("Save current setup", section)
        save.clicked.connect(self._save_basic_config)
        save_row.addWidget(save)
        save_row.addStretch(1)
        section.body.addLayout(save_row)
        self._basic_status = QLabel("", section, objectName="inlineMeta")
        self._basic_status.setWordWrap(True)
        self._basic_status.setVisible(False)
        section.body.addWidget(self._basic_status)
        more = LinkButton("Import, export and delete configs in Settings", section)
        more.clicked.connect(self.open_settings.emit)
        section.body.addWidget(more, 0, Qt.AlignmentFlag.AlignLeft)
        self._refresh_configs()
        return section

    def _refresh_configs(self):
        from .settings import list_configs
        while self._config_rows.count():
            w = self._config_rows.takeAt(0).widget()
            if w is not None:
                w.setParent(None)
                w.deleteLater()
        self._config_load_buttons = {}
        names = list_configs()
        for name in names:
            row = QWidget(self._config_rows_box)
            line = QHBoxLayout(row)
            line.setContentsMargins(0, 0, 0, 0)
            line.setSpacing(Sizing.SPACE_MD)
            line.addWidget(QLabel(name, row, objectName="settingTitle"), 1)
            btn = GhostButton("Load", row)
            btn.clicked.connect(lambda _c=False, n=name: self._load_basic_config(n))
            line.addWidget(btn)
            self._config_rows.addWidget(row)
            self._config_load_buttons[name] = btn
        self._configs_empty.setVisible(not names)

    def _refresh_basic(self):
        self._refresh_configs()
        self._refresh_identity()

    def _basic_note(self, text: str):
        self._basic_status.setText(text)
        self._basic_status.setVisible(bool(text))

    def _load_basic_config(self, name: str):
        from .settings import load_config
        if load_config(name):
            self._set_origin(name)
            self._basic_note("Loaded '%s'." % name)
            self.config_loaded.emit()
        else:
            self._basic_note("'%s' is not there any more." % name)
            self._refresh_configs()

    def _save_basic_config(self):
        from .settings import list_configs, save_config
        name = self._config_name.text().strip()
        if not name:
            self._basic_note("Type a name for the setup first.")
            return
        existed = name in list_configs()
        save_config(name)
        self._set_origin(name, self._fingerprint())
        self._config_name.clear()
        self._refresh_configs()
        self._refresh_identity()
        self._basic_note(
            ("Replaced '%s'." if existed else "Saved '%s'.") % name)

    # --- Run count + general -------------------------------------
    def _build_run_section(self) -> QWidget:
        section = Card("RUN COUNT", self, collapsible=True)
        row = QHBoxLayout()
        row.setSpacing(Sizing.SPACE_SM)
        self._run_count = QSpinBox(self)
        self._run_count.setObjectName("runCount")
        self._run_count.setRange(1, 9999)
        self._run_count.setValue(1)
        self._run_count.setFixedWidth(120)
        row.addWidget(self._run_count)
        row.addWidget(QLabel("runs", self))
        row.addSpacing(Sizing.SPACE_LG)

        infinite_btn = LinkButton("Loop forever", self)
        infinite_btn.clicked.connect(lambda: self._run_count.setValue(9999))
        row.addWidget(infinite_btn)
        row.addStretch(1)
        section.body.addLayout(row)

        self._run_estimate = QLabel("", self, objectName="inlineMeta")
        self._run_estimate.setVisible(False)
        section.body.addWidget(self._run_estimate)
        self._run_count.valueChanged.connect(self._refresh_run_estimate)
        self._refresh_run_estimate()
        return section

    def _refresh_run_estimate(self, *_):
        """What the run count comes to at your average recorded run."""
        try:
            avg = float(stats.aggregate().get("avg_duration") or 0)
        except Exception:
            avg = 0.0
        count = self._run_count.value()
        if avg <= 0 or count >= 9999:
            self._run_estimate.setVisible(False)
            return
        self._run_estimate.setText("About %s at your average run of %s" % (
            stats.fmt_total(avg * count), stats.fmt_duration(avg)))
        self._run_estimate.setVisible(True)

    # --- Behaviour toggles ---------------------------------------
    def _build_behaviour_section(self) -> QWidget:
        section = Card("BEHAVIOUR", self, collapsible=True)
        self._behaviour = {}

        rows = [
            ("bonus", "Claim bonus", True),
            ("bonus_one", "One weekly bonus per run", False),
            ("restart", "Restart on failure", True),
            ("altf4", "Close Limbus when finished", False),
            # Drives NETZACH. Fires only when enkephalin is FULL; banks
            # the surplus into modules (not a low-fuel refill).
            ("enkephalin", "Convert enkephalin to modules", True),
            ("skip", "Skip dialogue", True),
            ("swap_max_energy", "Swap for max energy", False),
            ("winrate", "Always pick winrate", True),
            ("wishmaking", "Wishmaking", False),
            ("claim_on_defeat", "Claim rewards on defeat", False),
            # Reaches outside the macro into the OS - gets a Windows logo.
            ("logout_on_finish", "Log out of Windows when finished", False),
        ]
        # The two counts are rows of their groups like the switches, each
        # saying what it counts.
        self._retry_count = QSpinBox(section)
        self._retry_count.setObjectName("runCount")
        self._retry_count.setRange(0, 99)
        self._retry_count.setValue(0)
        self._retry_count.setFixedWidth(90)
        self._pack_refreshes = QSpinBox(section)
        self._pack_refreshes.setObjectName("runCount")
        self._pack_refreshes.setRange(0, 99)
        self._pack_refreshes.setValue(7)
        self._pack_refreshes.setFixedWidth(90)
        numbers = {
            "pack_refreshes": ("Pack refreshes", self._pack_refreshes, "dice"),
            "retry_count": ("Retry count on defeat", self._retry_count, "hash"),
        }

        # Three even columns, one per moment of the run, each row wearing a
        # pixel glyph for what it does. The shop steps have their own card
        # on Floor Packs/Market.
        from .pixel_icons import pixel_icon
        from .widgets import windows_logo_pixmap
        glyphs = {
            "bonus": "gift", "bonus_one": "one", "enkephalin": "bolt",
            "skip": "skip", "winrate": "trophy", "swap_max_energy": "swap",
            "wishmaking": "sparkle", "restart": "loop",
            "claim_on_defeat": "chest", "altf4": "close",
        }
        by_key = {r[0]: r for r in rows}
        groups = (
            ("RUN", ("bonus", "bonus_one", "enkephalin", "skip", "winrate",
                     "swap_max_energy", "wishmaking", "pack_refreshes")),
            ("ON DEFEAT", ("restart", "retry_count", "claim_on_defeat")),
            ("WHEN FINISHED", ("altf4", "logout_on_finish")),
        )
        cols = QHBoxLayout()
        cols.setSpacing(Sizing.SPACE_XXL)
        self._behaviour_groups = {}
        for name, keys in groups:
            colw = _EvenColumn(section)
            col = QVBoxLayout(colw)
            col.setContentsMargins(0, 0, 0, 0)
            col.setSpacing(0)
            group = CollapsibleSection(name, colw)
            self._behaviour_groups[name] = group
            for key in keys:
                if key in numbers:
                    title, control, glyph = numbers[key]
                    icon = pixel_icon(glyph)
                else:
                    _k, title, default = by_key[key]
                    control = Toggle(default=default, parent=section)
                    self._behaviour[key] = control
                    icon = (windows_logo_pixmap(18) if key == "logout_on_finish"
                            else pixel_icon(glyphs[key]))
                group.body.addWidget(SettingRow(
                    title, control, parent=section, leading_icon=icon))
            col.addWidget(group)
            col.addStretch(1)
            cols.addWidget(colw, 1)
        # One weekly bonus per run only means something while Claim bonus is on.
        self._behaviour["bonus"].toggled.connect(self._behaviour["bonus_one"].setEnabled)
        self._behaviour["bonus_one"].setEnabled(self._behaviour["bonus"].isChecked())
        section.body.addLayout(cols)
        return section

    def _build_egogifts_tab(self) -> QWidget:
        """The EGO Gift Search tab: a keyword-tab thumbnail gallery for picking up to
        3 gifts to auto-select at the start of a Mirror Dungeon run."""
        page = QWidget()
        # Paint the page background (only the page, via the id selector) so the
        # AnimatedStack slide snapshot is the dark page, not a grey transparent.
        page.setObjectName("egoGiftsPage")
        page.setStyleSheet(f"QWidget#egoGiftsPage {{ {page_fill_qss()} }}")
        col = QVBoxLayout(page)
        col.setContentsMargins(Sizing.SPACE_XL, Sizing.SPACE_LG,
                               Sizing.SPACE_XL, Sizing.SPACE_LG)
        col.setSpacing(Sizing.SPACE_MD)
        self._gift_gallery = _GiftGallery(max_picks=3, parent=page)
        self._gift_gallery.changed.connect(self._save_state)
        col.addWidget(self._gift_gallery, 1)
        return page

    def _build_market_controls_section(self) -> QWidget:
        """Buying-workflow card: master toggle + reroll controls. The reroll
        rows grey out when they don't apply (see _sync_market_controls)."""
        card = Card("MARKET BUYING", self)
        self._market_controls_card = card

        self._default_market_workflow = Toggle(default=True, parent=card)
        self._default_market_workflow.toggled.connect(self._save_state)
        self._default_market_workflow.toggled.connect(self._sync_market_controls)
        card.body.addWidget(SettingRow(
            "Default market workflow", self._default_market_workflow,
            parent=card))

        self._market_refresh_count = QSpinBox(card)
        self._market_refresh_count.setObjectName("runCount")
        self._market_refresh_count.setRange(0, 99)
        self._market_refresh_count.setValue(0)
        self._market_refresh_count.setFixedWidth(72)
        self._market_refresh_count.valueChanged.connect(self._save_state)
        self._market_count_row = SettingRow(
            "Refresh count", self._market_refresh_count, parent=card)
        card.body.addWidget(self._market_count_row)

        self._market_refresh_until_cost = Toggle(default=False, parent=card)
        self._market_refresh_until_cost.toggled.connect(self._save_state)
        self._market_refresh_until_cost.toggled.connect(self._sync_market_controls)
        self._market_until_row = SettingRow(
            "Refresh until cost available", self._market_refresh_until_cost,
            parent=card)
        card.body.addWidget(self._market_until_row)

        self._buy_ego_fuel = Toggle(default=False, parent=card)
        self._buy_ego_fuel.toggled.connect(self._save_state)
        self._buy_fuel_row = SettingRow(
            "Buy EGO fuel", self._buy_ego_fuel, parent=card)
        card.body.addWidget(self._buy_fuel_row)
        self._sync_market_controls()
        return card

    def _build_market_section(self) -> QWidget:
        """The per-gift tags, for All floors or the floor picked above."""
        self._market_scope = QLabel("All floors", self, objectName="inlineMeta")
        section = Card("MARKET GIFTS", self, trailing=self._market_scope)

        # Three independent tag configs: the normal one, a SAIKAI one seeded
        # from the preset the first time SAIKAI is selected, and Hollow's.
        # Each slot also holds its floors' own tags and shop steps. The
        # gallery edits whichever slot and floor are active.
        self._market_slot = "normal"
        self._market_slots = {"normal": {}, "saikai": None, "hollow": None}
        self._market_floors = {slot: {} for slot in _MARKET_SLOTS}
        self._grace_slot = "normal"
        self._grace_slots = {"normal": None, "hollow": None}

        self._market_gallery = _MarketGiftGallery(parent=section, scrollable=False)
        self._market_gallery.changed.connect(self._on_market_changed)
        section.body.addWidget(self._market_gallery)
        self._refresh_floor_captions()
        return section

    def _on_market_changed(self):
        """A tag change in the gallery. Hollow's run-wide slot cleared of
        every fuse, keep and uptie tag shows the sheet's plan again, since
        that is what the run then follows."""
        if self._market_slot == "hollow" and self._market_floor is None:
            from .run_config import hollow_seeded
            if not hollow_seeded(self._market_gallery.config()):
                self._stash_floor_views()
                self._seed_hollow_slot()
                self._load_floor_views()
        self._save_state()

    @staticmethod
    def _saikai_market_seed() -> dict:
        from wbcore.market_catalog import SAIKAI_MARKET_TAGS
        return {k: list(v) for k, v in SAIKAI_MARKET_TAGS.items()}

    def _seed_hollow_slot(self):
        """Hollow's slot while it holds no fuse, keep or uptie tag (never
        shown yet, or cleared): the sheet's plan as editable tags, run-wide
        and per floor, so the rows show what the run will do."""
        from .run_config import hollow_floor_tags, hollow_slot_tags
        slot = self._market_slots.get("hollow")
        floors = self._market_floors.get("hollow") or {}
        self._market_floors["hollow"] = {
            int(fl): ent for fl, ent in hollow_floor_tags(slot, floors).items()}
        self._market_slots["hollow"] = hollow_slot_tags(slot)

    def _market_slot_cfg(self, slot):
        """The run-wide tag dict for `slot`. None = a strategy slot never
        saved (each preset seeds its slot on first use)."""
        if not hasattr(self, "_market_gallery"):
            return {} if slot == "normal" else None
        self._stash_floor_views()
        return self._market_slots.get(slot)

    def _market_controls_config(self) -> dict:
        """Market workflow toggles + refresh count (MARKET BUYING)."""
        if not hasattr(self, "_default_market_workflow"):
            return {}
        return {
            "default_market_workflow": self._default_market_workflow.isChecked(),
            "refresh_count": self._market_refresh_count.value(),
            "refresh_until_cost": self._market_refresh_until_cost.isChecked(),
            "buy_ego_fuel": self._buy_ego_fuel.isChecked(),
        }

    def _sync_market_controls(self):
        """Reroll controls only apply when the default workflow is off; the
        count only applies when 'refresh until cost' is off. Grey out the rest."""
        if not hasattr(self, "_market_until_row"):
            return
        configured_only = not self._default_market_workflow.isChecked()
        self._market_until_row.setEnabled(configured_only)
        self._market_count_row.setEnabled(
            configured_only and not self._market_refresh_until_cost.isChecked())
        self._buy_fuel_row.setEnabled(configured_only)

    def _gift_search_selection(self) -> list:
        """Up-to-3 selected gift names from the EGO Gift Search gallery."""
        if hasattr(self, "_gift_gallery"):
            return self._gift_gallery.selected()
        return []

    # --- Shop: Skill Replacement ---------------------------------
    # Per-sinner skill replacements (1>2, 1>3, 2>3) fired in the shop.
    # Persisted state: {"active": [...], "order": {sinner: [keys]},
    # "repeats": {sinner: {key: cap}}}.
    _SKILL_REPLACE_SINNERS = [
        ["Yi Sang", "Faust", "Don Quixote", "Ryōshū", "Meursault", "Hong Lu"],
        ["Heathcliff", "Ishmael", "Rodion", "Sinclair", "Outis", "Gregor"],
    ]
    # Canonical swap keys + friendly labels (Unicode arrow for display).
    _SKILL_REPLACE_SWAPS = (
        ("1>2", "Skill 1 → Skill 2"),
        ("1>3", "Skill 1 → Skill 3"),
        ("2>3", "Skill 2 → Skill 3"),
    )
    _SKILL_REPLACE_DEFAULT_ORDER = ("1>3", "2>3", "1>2")

    def _build_skill_replace_section(self) -> QWidget:
        section = Card("SKILL REPLACEMENT", self, collapsible=True)
        section.body.addLayout(self._swap_floors_row(section))
        section.body.addSpacing(Sizing.SPACE_SM)

        # In-memory store per sinner: active set, priority order, repeats.
        flat_names = [n for row in self._SKILL_REPLACE_SINNERS for n in row]
        self._skill_active: set[str] = set()
        self._skill_order: dict[str, list[str]] = {
            n: list(self._SKILL_REPLACE_DEFAULT_ORDER) for n in flat_names
        }
        self._skill_repeats: dict[str, dict[str, int]] = {
            n: {k: 0 for k, _ in self._SKILL_REPLACE_SWAPS}
            for n in flat_names
        }
        self._skill_selected_name: str = flat_names[0]

        # The selected sinner's block on the left, the sinner picker on the
        # right, built so the two share their lines: a caption row each, then
        # three rows of the same height and spacing (swaps | names).
        body = QGridLayout()
        body.setContentsMargins(0, 0, 0, 0)
        body.setHorizontalSpacing(Sizing.SPACE_XL)
        body.setVerticalSpacing(Sizing.SPACE_SM)
        body.setColumnStretch(1, 1)

        self._skill_head = QWidget(section)
        self._skill_head.setFixedWidth(_SKILL_BLOCK_W)
        head_layout = QHBoxLayout(self._skill_head)
        head_layout.setContentsMargins(0, 0, Sizing.SPACE_XS + 1, 0)
        head_layout.setSpacing(Sizing.SPACE_SM)
        self._skill_head_layout = head_layout
        body.addWidget(self._skill_head, 0, 0)

        self._skill_details = QFrame(section)
        self._skill_details.setFixedWidth(_SKILL_BLOCK_W)
        details_layout = QVBoxLayout(self._skill_details)
        details_layout.setContentsMargins(0, 0, 0, 0)
        details_layout.setSpacing(Sizing.SPACE_XS)
        self._skill_details_layout = details_layout
        body.addWidget(self._skill_details, 1, 0, Qt.AlignmentFlag.AlignTop)

        picker = QWidget(section)
        picker_col = QVBoxLayout(picker)
        picker_col.setContentsMargins(0, 0, 0, 0)
        picker_col.setSpacing(Sizing.SPACE_XS)
        picker_col.addWidget(QLabel("SINNERS", picker,
                                    objectName="sectionLabel"),
                             0, Qt.AlignmentFlag.AlignLeft)
        sinner_grid = QGridLayout()
        sinner_grid.setContentsMargins(0, 0, 0, 0)
        sinner_grid.setHorizontalSpacing(Sizing.SPACE_SM)
        sinner_grid.setVerticalSpacing(Sizing.SPACE_XS)
        self._skill_chips: dict[str, _SinnerSkillChip] = {}
        for i, name in enumerate(flat_names):
            chip = _SinnerSkillChip(name, picker)
            chip.setFixedHeight(_skill_row_h())
            chip.selected.connect(self._on_skill_sinner_selected)
            chip.toggled_active.connect(self._on_skill_sinner_toggle_active)
            self._skill_chips[name] = chip
            sinner_grid.addWidget(chip, i // _SKILL_CHIP_COLS,
                                  i % _SKILL_CHIP_COLS)
        picker_col.addLayout(sinner_grid)
        body.addWidget(picker, 1, 1, Qt.AlignmentFlag.AlignTop)
        section.body.addLayout(body)

        self._skill_chips[self._skill_selected_name].set_selected(True)
        self._render_skill_details()
        return section

    def _on_skill_sinner_selected(self, name: str):
        """Switch the details view to `name` (does not toggle active)."""
        if name == self._skill_selected_name:
            return
        prev = self._skill_selected_name
        if prev in self._skill_chips:
            self._skill_chips[prev].set_selected(False)
        self._skill_chips[name].set_selected(True)
        self._skill_selected_name = name
        self._render_skill_details()

    def _on_skill_sinner_toggle_active(self, name: str):
        """Chip double-click: flip whether the bot visits `name`."""
        on = name not in self._skill_active
        self._set_skill_active(name, on)
        if name == self._skill_selected_name:
            try:
                self._skill_toggle.setChecked(on)
            except (AttributeError, RuntimeError):
                pass

    def _set_skill_active(self, name: str, on: bool):
        on = bool(on)
        if (name in self._skill_active) == on:
            return
        if on:
            self._skill_active.add(name)
        else:
            self._skill_active.discard(name)
        self._skill_chips[name].set_active(on)
        self._dim_skill_rows()
        self._save_state()

    def _dim_skill_rows(self):
        """A sinner that is switched off keeps its rows editable, but they
        read as inactive."""
        try:
            self._skill_priority_stack.set_dim(
                self._skill_selected_name not in self._skill_active)
        except (AttributeError, RuntimeError):
            pass

    def _render_skill_details(self):
        """Rebuild the selected sinner's block: name, on/off switch, and the
        priority rows."""
        for layout in (self._skill_head_layout, self._skill_details_layout):
            while layout.count() > 0:
                item = layout.takeAt(0)
                w = item.widget()
                if w is not None:
                    w.setParent(None)
                    w.deleteLater()

        name = self._skill_selected_name
        # A real switch: the state used to be a grey "(disabled)" in the
        # title, changed only by double-clicking the chip.
        head = self._skill_head_layout
        host = self._skill_head
        from .giftart import sinner_icon
        pm = QPixmap(sinner_icon(name))
        if not pm.isNull():
            emblem = QLabel(host)
            emblem.setFixedSize(28, 28)
            emblem.setPixmap(pm.scaled(28, 28, Qt.AspectRatioMode.KeepAspectRatio,
                                       Qt.TransformationMode.SmoothTransformation))
            head.addWidget(emblem)
        head.addWidget(QLabel(name, host, objectName="settingTitle"))
        head.addStretch(1)
        switch_label = QLabel("Replace skills", host)
        switch_label.setStyleSheet(f"color: {Colors.TEXT_SECONDARY};")
        head.addWidget(switch_label)
        self._skill_toggle = Toggle(default=name in self._skill_active,
                                    parent=host)
        self._skill_toggle.toggled.connect(
            lambda on, n=name: self._set_skill_active(n, on))
        head.addWidget(self._skill_toggle)

        block = self._skill_details
        layout = self._skill_details_layout
        self._skill_rows = QWidget(block)
        rows = QVBoxLayout(self._skill_rows)
        rows.setContentsMargins(0, 0, 0, 0)
        rows.setSpacing(Sizing.SPACE_XS)

        # Column captions once, not a "Repeats" label on every row.
        caps = QHBoxLayout()
        caps.setContentsMargins(Sizing.SPACE_MD, 0, Sizing.SPACE_XS + 1, 0)
        caps.addWidget(QLabel("PRIORITY", self._skill_rows,
                              objectName="sectionLabel"))
        caps.addStretch(1)
        caps.addWidget(QLabel("REPEATS", self._skill_rows,
                              objectName="sectionLabel"))
        rows.addLayout(caps)

        label_of = dict(self._SKILL_REPLACE_SWAPS)
        priority = self._skill_order[name]
        items = [(k, label_of[k],
                  self._skill_repeats[name].get(k, 0)) for k in priority]
        self._skill_priority_stack = _SkillPriorityStack(
            items, parent=self._skill_rows)
        # Bind the current sinner name into the (key, value) callback.
        sel = name
        self._skill_priority_stack.order_changed.connect(
            self._on_skill_order_changed_v2)
        self._skill_priority_stack.repeats_changed.connect(
            lambda key, val, n=sel: self._on_skill_repeats_v2(n, key, val))
        rows.addWidget(self._skill_priority_stack)
        layout.addWidget(self._skill_rows)
        self._dim_skill_rows()

    def _on_skill_order_changed_v2(self, new_order: list[str]):
        """Persist the new priority order after a drop."""
        name = self._skill_selected_name
        valid = {k for k, _ in self._SKILL_REPLACE_SWAPS}
        cleaned = [k for k in new_order if k in valid]
        # Defensive: keep all three swaps even if the drop math missed one.
        for k in self._SKILL_REPLACE_DEFAULT_ORDER:
            if k not in cleaned:
                cleaned.append(k)
        if cleaned == self._skill_order[name]:
            return
        self._skill_order[name] = cleaned
        self._save_state()

    def _on_skill_repeats_v2(self, sinner: str, swap_key: str, value: int):
        self._skill_repeats[sinner][swap_key] = int(value)
        self._save_state()

    # --- Pack preferences (per floor) ----------------------------
    def _build_packs_section(self) -> QWidget:
        section = Card("PACK PREFERENCES", self)
        # Default difficulty is Hard.
        start = "Hard"
        if hasattr(self, "_difficulty"):
            start = self._difficulty.selected()
        if start == "Normal":
            data, banned = _floors_for_picker(FLOORS, 5), BANNED
        else:
            max_floor = 15 if start == "Extreme" else 5
            data, banned = _floors_for_picker(HARD_FLOORS, max_floor), HARD_BANNED
        self._floor_packs = FloorPacks(data, banned, parent=section)
        self._floor_packs.set_tabs_visible(False)     # the floor bar drives it
        section.body.addWidget(self._floor_packs)
        return section

    # --- Pack Search fallback -------------------------------------
    _PS_FLOORS = (1, 2, 3, 4, 5)

    def _build_pack_search_section(self, fl: int) -> QWidget:
        """One floor's pack to secure through the in-game Pack Search, with
        its Search switch and the Hard switch for that floor."""
        section = Card("PACK SEARCH", self)

        row = QHBoxLayout()
        row.setSpacing(Sizing.SPACE_MD)
        # The pack's card follows the field as it is typed or completed.
        plate = _PackPlate(section)
        self._ps_art[fl] = plate
        row.addWidget(plate)
        edit = _PackSearchEdit(section)
        edit.setObjectName("textField")
        edit.setPlaceholderText("No pack configured")
        edit.setClearButtonEnabled(True)
        comp = QCompleter(_pack_search_names_for_floor(fl), edit)
        comp.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        comp.setCompletionMode(QCompleter.CompletionMode.InlineCompletion)
        edit.setCompleter(comp)
        edit.editingFinished.connect(lambda f=fl: self._ps_commit_edit(f))
        edit.textChanged.connect(
            lambda text, f=fl: self._ps_art[f].set_pack(self._ps_lookup(f, text)))
        row.addWidget(edit, 1)

        tog = Toggle(default=False, parent=section)
        tog.toggled.connect(self._save_state)
        row.addWidget(QLabel("Search", section, objectName="settingTitle"))
        row.addWidget(tog)
        row.addSpacing(Sizing.SPACE_MD)
        # Hard from this floor: the run starts on Normal and flips here.
        hard = Toggle(default=False, parent=section)
        hard.toggled.connect(lambda on, f=fl: self._on_hard_switch(f, on))
        row.addWidget(QLabel("Hard", section, objectName="settingTitle"))
        row.addWidget(hard)
        section.body.addLayout(row)
        self._ps_rows[fl] = (tog, edit)
        self._hard_rows[fl] = hard
        return section

    def _ps_lookup(self, floor: int, typed: str) -> str:
        """The pack `typed` names on `floor`, as the catalogue spells it,
        or "" for anything else."""
        typed = (typed or "").strip().lower()
        if not typed:
            return ""
        return next((n for n in _pack_search_names_for_floor(floor)
                     if n.lower() == typed), "")

    def _ps_commit_edit(self, floor: int):
        """Normalize the floor's edit to a valid pack name (one per floor)
        or revert to the last valid entry."""
        _tog, edit = self._ps_rows[floor]
        typed = edit.text().strip()
        if not typed:
            if self._ps_valid.get(floor):
                self._ps_valid[floor] = ""
                self._save_state()
            return
        match = next((n for n in _pack_search_names_for_floor(floor)
                      if n.lower() == typed.lower()), None)
        if match is None:
            edit.setText(self._ps_valid.get(floor, ""))
            return
        if match != edit.text():
            edit.setText(match)
        if self._ps_valid.get(floor) != match:
            self._ps_valid[floor] = match
            self._save_state()

    # --- Starting grace ------------------------------------------
    def _build_grace_section(self) -> QWidget:
        # The in-game side panel: take every grace, enhance every taken one.
        controls = QWidget(self)
        bar = QHBoxLayout(controls)
        bar.setContentsMargins(0, 0, 0, 0)
        bar.setSpacing(Sizing.SPACE_SM)
        self._grace_all = GhostButton("Select all graces", controls)
        self._grace_all.setToolTip(
            "Takes every grace. When all ten are taken, clears them.")
        self._grace_all.clicked.connect(self._select_all_graces)
        bar.addWidget(self._grace_all)
        bar.addSpacing(Sizing.SPACE_SM)
        bar.addWidget(QLabel("Enhance all", controls, objectName="inlineMeta"))
        self._grace_enhance = {}
        for level, text in _GraceCard._LEVELS:
            btn = QPushButton(text, controls, objectName="graceLevel")
            btn.setCheckable(True)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            btn.setToolTip("Every taken grace at %s. Press again for the "
                           "base level." % text)
            btn.clicked.connect(lambda _c=False, lv=level: self._enhance_all(lv))
            bar.addWidget(btn)
            self._grace_enhance[level] = btn

        section = Card("STARTING GRACE", self, trailing=controls)
        self._grace_total = QLabel("", section, objectName="inlineMeta")
        self._grace_total.setToolTip("Starlight the chosen graces cost on the grace screen.")
        self._grace_total.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignTop)
        section.body.addWidget(self._grace_total)
        grid_host = QWidget(section)
        grid = QGridLayout(grid_host)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setHorizontalSpacing(Sizing.SPACE_SM)
        grid.setVerticalSpacing(Sizing.SPACE_SM)
        self._grace_chips = {}
        # Default: first 4 graces at base tier (BUFF = [1,1,1,1,0,...]).
        for i, name in enumerate(_GRACE_NAMES):
            card = _GraceCard(name, grid_host)
            if i < 4:
                card.set_state(1)
            card.state_changed.connect(self._refresh_grace_controls)
            grid.addWidget(card, i // 5, i % 5)
            self._grace_chips[name] = card
        for c in range(5):
            grid.setColumnStretch(c, 1)
        section.body.addWidget(grid_host)
        self._refresh_grace_controls()
        return section

    def _refresh_grace_controls(self, *_):
        cards = self._grace_chips.values()
        taken = [c.state() for c in cards if c.state()]
        total = sum(GRACES[c.name()]["cost"] * c.state() for c in cards
                    if c.name() in GRACES)
        self._grace_total.setText("%d starlight" % total)
        for level, btn in self._grace_enhance.items():
            btn.setEnabled(bool(taken))
            btn.setChecked(bool(taken) and all(s == level for s in taken))

    def _select_all_graces(self):
        cards = list(self._grace_chips.values())
        clear = all(c.state() for c in cards)
        for c in cards:
            if clear:
                c.set_state(0)
            elif not c.state():
                c.set_state(1)
        self._refresh_grace_controls()
        self._save_state()

    def _enhance_all(self, level: int):
        taken = [c for c in self._grace_chips.values() if c.state()]
        back = bool(taken) and all(c.state() == level for c in taken)
        for c in taken:
            c.set_state(1 if back else level)
        self._refresh_grace_controls()
        self._save_state()

    # --- Card priority (Hard MD) ---------------------------------
    def _build_cards_section(self) -> QWidget:
        from .giftart import reward_icon
        section = Card("CARD PRIORITY", self)
        self._card_priority = OrderedList(
            _CARD_NAMES, icons={n: reward_icon(n) for n in _CARD_NAMES},
            parent=section)
        section.body.addWidget(self._card_priority)
        return section

    # --- Public state hooks --------------------------------------
    def set_running(self, running: bool):
        self._start_btn.setEnabled(not running)
        self._start_btn.setText(seasonal.title("Start Mirror Dungeon"))
        self._stop_btn.setEnabled(running)

    def set_arming(self, seconds: int):
        if seconds > 0:
            self._start_btn.setEnabled(False)
            self._start_btn.setText(f"Tab into game... {seconds}s")
            self._stop_btn.setEnabled(True)
        else:
            self._start_btn.setEnabled(True)
            self._start_btn.setText(
                seasonal.title("Start Mirror Dungeon"))
            self._stop_btn.setEnabled(False)
