# SPDX-License-Identifier: GPL-3.0-or-later
"""Mirror Dungeon page - the full run-config surface."""

import os

from PySide6.QtCore import QMimeData, QPoint, QRect, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import (
    QColor, QDrag, QFont, QPainter, QPainterPath, QPen, QPixmap,
)
from PySide6.QtWidgets import (
    QAbstractButton, QApplication, QCompleter, QDialog, QDialogButtonBox,
    QFrame, QGridLayout, QHBoxLayout, QLabel, QLineEdit, QListWidgetItem,
    QPushButton, QScrollArea, QSizePolicy, QSpinBox, QVBoxLayout, QWidget,
)

from .run_config import HOLLOW_LABEL, HOLLOW_SEARCH_GIFTS, SAIKAI_LABEL

_MARKET_SLOT_HINTS = {
    "saikai": ("Editing the SAIKAI market config (used by SAIKAI runs only). "
               "Pick another strategy to edit your normal config."),
    "hollow": ("Editing the Hollow market config (used by Hollow runs only; "
               "its floor plan decides the fuses, the kept gifts and the "
               "upties, so only Buy and Sell tags matter here). Pick "
               "another strategy to edit your normal config."),
}
from .settings import load_section, save_section
from .copy import (
    MD_CUSTOM_RUN_HINT,
    MD_DIFFICULTY_HINT,
    MD_GRACE_HINT,
    MD_RUN_COUNT_HINT,
    MD_SKILL_REPLACEMENT_HINT_RICH,
)
from . import seasonal
from .theme import Colors, Sizing
from .widgets import (
    AnimatedStack, Card, ChipList, ClickOrderGrid, CycleChip, FloorPacks,
    FlowLayout, GhostButton, HRule, IconlessTabBar, LinkButton, OrderedList,
    CollapsibleSection, PageHeader, PrimaryButton, Segmented, SettingRow,
    Toggle, _rad, _title_label, page_fill_qss, show_placeholder_notice,
    tag_chip_qss,
)

_SECTION = "mirror"

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
        self._locked = False
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

    def set_locked(self, on):
        on = bool(on)
        if on != self._locked:
            self._locked = on
            self.setCursor(Qt.CursorShape.ArrowCursor if on
                           else Qt.CursorShape.PointingHandCursor)
            self.update()

    def is_selected(self):
        return self._selected

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
        if self._hover and not self._locked:
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
        dark = QColor("#0e0e10")
        if self._locked:
            p.setPen(QPen(dark, 1.4))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawArc(int(cx - 3), int(cy - 5), 6, 6, 0, 180 * 16)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(dark)
            p.drawRoundedRect(int(cx - 4), int(cy - 1), 8, 6,
                              _rad(1.5), _rad(1.5))
        else:
            p.setPen(QPen(dark, 2))
            p.drawLine(int(cx - 4), int(cy + 1), int(cx - 1), int(cy + 3))
            p.drawLine(int(cx - 1), int(cy + 3), int(cx + 4), int(cy - 3))


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


class _GiftGallery(QWidget):
    """In-game-style EGO gift picker: keyword tabs, the active keyword's gifts
    grouped by tier, pick up to `max_picks`, search across all keywords, reset.
    Emits `changed` on any selection change."""

    changed = Signal()

    def __init__(self, max_picks=3, parent=None):
        super().__init__(parent)
        self._max = max_picks
        self._order = []          # selected names, in pick order
        self._locked = set()      # mandatory, non-removable (e.g. SAIKAI Spiderweb)
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
        if name in self._locked:
            return                      # mandatory pick, can't be removed
        if name in self._order:
            self._order.remove(name)
        elif len(self._order) < self._max:
            self._order.append(name)
        else:
            return
        self._refresh()
        self.changed.emit()

    def reset(self):
        # Clear everything except the locked, mandatory picks.
        keep = [n for n in self._order if n in self._locked]
        if self._order == keep:
            return
        self._order = keep
        self._refresh()
        self.changed.emit()

    def selected(self):
        return list(self._order)

    def set_selected(self, names):
        order = [n for n in self._order if n in self._locked]   # keep locked
        for n in (names or []):
            if n in self._tiles and n not in order and len(order) < self._max:
                order.append(n)
        self._order = order
        self._refresh()

    def set_locked(self, names):
        """Mandatory, non-removable picks (always selected, counted in the cap).
        Used to pin SAIKAI's Spiderweb gift."""
        new = {n for n in (names or []) if n in self._tiles}
        # A released lock unequips its gift. Left selected, the SAIKAI gift
        # carried over to the next strategy and was searched for on every
        # Thrill run. It can still be picked by hand afterwards.
        released = self._locked - new
        self._order = [n for n in self._order if n not in released]
        self._locked = new
        # Locked picks go to the front and survive the cap.
        rest = [n for n in self._order if n not in self._locked]
        self._order = (list(self._locked) + rest)[:self._max]
        for n in self._locked:          # guarantee every locked pick is in
            if n not in self._order:
                self._order = ([n] + self._order)[:self._max]
        self._refresh()

    def _refresh(self):
        for n, tile in self._tiles.items():
            tile.set_locked(n in self._locked)
            tile.set_selected(n in self._order)
        self._count.setText(f"{len(self._order)} / {self._max} selected")
        self._reset_btn.setEnabled(any(n not in self._locked for n in self._order))
        self._rebuild_chips()

    def _rebuild_chips(self):
        while self._chips.count():
            it = self._chips.takeAt(0)
            w = it.widget() if it else None
            if w is not None:
                w.setParent(None)
                w.deleteLater()
        for name in self._order:
            locked = name in self._locked
            shown = name.replace("&", "&&")      # a bare & would be a mnemonic
            chip = QPushButton(f"{shown}  \U0001F512" if locked else f"{shown}   x",
                               self._chips_holder)
            border = Colors.ACCENT if locked else Colors.BORDER_STRONG
            chip.setStyleSheet(tag_chip_qss(border, locked=locked))
            if locked:
                chip.setToolTip("Mandatory for this run")
            else:
                chip.setCursor(Qt.CursorShape.PointingHandCursor)
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


# Tile tag badge colours.
_MARKET_KEEPFUSE_COL = "#5b8cff"   # F = keep (don't fuse), blue
_MARKET_KEEPSELL_COL = "#a371f7"   # K = keep (don't sell), purple
_MARKET_SELL_COL = "#f0883e"       # S = sell, amber
_MARKET_BUY_COL = "#3fb950"        # buy priority number, green
_MARKET_FUSE_COL = "#f85149"       # C = fuse target (craft), red
_MARKET_ENH1_COL = "#39c5cf"       # E1 = enhance once, cyan
_MARKET_ENH2_COL = "#76e3ea"       # E2 = enhance twice, light cyan
# Tag "brush" modes: with one active, clicking a gift toggles that tag.
_MARKET_MODES = (
    ("keep_fuse", "Keep · no fuse"),
    ("keep_sell", "Keep · no sell"),
    ("sell", "Sell"),
    ("buy", "Buy priority"),
    ("fuse", "Fuse target"),
    ("enhance1", "Enhance once"),
    ("enhance2", "Enhance twice"),
)


class _MarketGiftTile(QAbstractButton):
    """Market-config gift thumbnail. Draws small fuse/sell/buy role badges and
    an accent border when it is the gift currently being edited."""

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
        out = []
        if self._keep_fuse:
            out.append(("F", _MARKET_KEEPFUSE_COL))
        if self._keep_sell:
            out.append(("K", _MARKET_KEEPSELL_COL))
        if self._sell:
            out.append(("S", _MARKET_SELL_COL))
        if self._buy > 0:
            out.append((str(self._buy), _MARKET_BUY_COL))
        if self._fuse:
            out.append(("C", _MARKET_FUSE_COL))
        if self._enh1:
            out.append(("E1", _MARKET_ENH1_COL))
        if self._enh2:
            out.append(("E2", _MARKET_ENH2_COL))
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
        # Roles read as ONE bar across the bottom edge, split into a segment
        # per active role, rather than a scatter of stickers floating on the
        # artwork. It cannot wrap or overflow however many roles are set, and
        # each segment gets wider the fewer there are.
        badges = self._badges()
        if badges:
            bar_h = 13
            bx0 = int(r.left()) + 1
            bw = int(r.width()) - 2
            by0 = int(r.bottom()) - bar_h
            # Clip to the frame so the square bar cannot poke out past the
            # legacy skin's rounded bottom corners.
            clip = QPainterPath()
            clip.addRoundedRect(r, _rad(8), _rad(8))
            p.save()
            p.setClipPath(clip)
            # Scrim: keeps the letters legible over bright gift art and gives
            # the bar an edge to sit on.
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(0, 0, 0, 150))
            p.drawRect(bx0, by0 - 1, bw, bar_h + 1)
            seg = bw / float(len(badges))
            f = QFont(self.font())
            f.setPointSizeF(7.0 if seg >= 15 else 6.0)
            f.setBold(True)
            p.setFont(f)
            for i, (letter, col) in enumerate(badges):
                sx = bx0 + int(round(i * seg))
                sw = bx0 + int(round((i + 1) * seg)) - sx
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(QColor(col))
                p.drawRect(sx, by0, sw, bar_h)
                p.setPen(QColor("#0e0e10"))
                p.drawText(QRect(sx, by0, sw, bar_h),
                           int(Qt.AlignmentFlag.AlignCenter), letter)
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
    """Market gift config: keyword tabs + the active keyword's gifts grouped by
    tier (IV..I); click a gift to set its keep-from-fusion / sell / buy
    behaviour. Emits `changed` on any config change."""

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
        self._mode = None        # active tag brush, one of _MARKET_MODES keys
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

        tabholder = QWidget(self)
        tabrow = FlowLayout(tabholder, spacing=4)
        for kw in present:
            tab = _KeywordTab(kw, tab_path(kw), tabholder)
            tab.clicked.connect(lambda _=False, k=kw: self._on_tab(k))
            self._tabs[kw] = tab
            tabrow.addWidget(tab)
        outer.addWidget(tabholder)

        outer.addWidget(self._build_mode_selector())

        head = QHBoxLayout()
        head.setSpacing(Sizing.SPACE_MD)
        self._search = QLineEdit(self)
        self._search.setObjectName("textField")
        self._search.setPlaceholderText("Search all gifts by name...")
        self._search.setClearButtonEnabled(True)
        self._search.textChanged.connect(self._refresh_view)
        head.addWidget(self._search, 1)
        self._count = QLabel(self, objectName="inlineMeta")
        head.addWidget(self._count)
        self._reset_btn = GhostButton("Clear all", self)
        self._reset_btn.clicked.connect(self.reset)
        head.addWidget(self._reset_btn)
        outer.addLayout(head)

        # Summary of tagged gifts (grouped, removable chips) - lets you see
        # everything in keep/sell/buy at a glance without hunting tabs.
        self._summary_holder = QWidget(self)
        self._summary_col = QVBoxLayout(self._summary_holder)
        self._summary_col.setContentsMargins(0, 0, 0, 0)
        self._summary_col.setSpacing(Sizing.SPACE_XS)
        self._summary_holder.setVisible(False)
        outer.addWidget(self._summary_holder)

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

    def _build_mode_selector(self) -> QWidget:
        panel = QWidget(self)
        col = QVBoxLayout(panel)
        col.setContentsMargins(0, 0, 0, 0)
        col.setSpacing(Sizing.SPACE_XS)
        row = QHBoxLayout()
        row.setSpacing(Sizing.SPACE_SM)
        row.addWidget(QLabel("Tag mode", panel, objectName="settingTitle"),
                      0, Qt.AlignmentFlag.AlignTop)
        mode_qss = (
            f"QPushButton{{background:{Colors.BG_RAISED};"
            f"color:{Colors.TEXT_SECONDARY};"
            f"border:1px solid {Colors.BORDER_SUBTLE};"
            f"border-radius:{Sizing.RADIUS_PILL}px;"
            f"padding:5px 14px;font-weight:600;}}"
            f"QPushButton:hover{{border-color:{Colors.ACCENT};}}"
            f"QPushButton:checked{{background:{Colors.ACCENT};"
            f"color:{Colors.BG_BASE};border-color:{Colors.ACCENT};}}"
        )
        # Flowed, not boxed: a QHBoxLayout cannot wrap, so seven modes summed
        # to a hard minimum wider than the window and the last ones were laid
        # out past the right edge. The keyword tabs above already flow.
        btns = QWidget(panel)
        flow = FlowLayout(btns, spacing=Sizing.SPACE_SM)
        self._mode_btns = {}
        for key, label in _MARKET_MODES:
            b = QPushButton(label, btns)
            b.setCheckable(True)
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.setStyleSheet(mode_qss)
            b.clicked.connect(lambda _=False, k=key: self._on_mode(k))
            self._mode_btns[key] = b
            flow.addWidget(b)
        row.addWidget(btns, 1)
        col.addLayout(row)
        self._mode_hint = QLabel("Pick a mode, then click gifts to tag them.",
                                 panel, objectName="inlineHint")
        col.addWidget(self._mode_hint)
        return panel

    def _on_tab(self, kw):
        self._active_kw = kw
        self._tabs[kw].setChecked(True)
        if self._search.text():
            self._search.blockSignals(True)
            self._search.clear()
            self._search.blockSignals(False)
        self._refresh_view()

    def _on_mode(self, key):
        self._mode = None if key == self._mode else key
        for k, b in self._mode_btns.items():
            b.setChecked(k == self._mode)
        self._refresh_mode_hint()

    def _refresh_mode_hint(self):
        label = dict(_MARKET_MODES).get(self._mode)
        if label:
            self._mode_hint.setText(
                f"Click gifts to toggle the “{label}” tag.")
        else:
            self._mode_hint.setText(
                "Pick a mode, then click gifts to tag them.")

    def _on_tile(self, name):
        m = self._mode
        if m is None:
            return
        if m == "keep_fuse":
            if name in self._keep_fuse:
                self._keep_fuse.discard(name)
            else:
                self._keep_fuse.add(name)
        elif m == "keep_sell":
            if name in self._keep_sell:
                self._keep_sell.discard(name)
            else:
                self._keep_sell.add(name)
                self._sell.discard(name)            # keep-no-sell excludes sell
        elif m == "sell":
            if name in self._sell:
                self._sell.discard(name)
            else:
                self._sell.add(name)
                self._keep_sell.discard(name)        # sell excludes keep-no-sell
        elif m == "buy":
            if name in self._buy:
                self._buy.remove(name)
            else:
                self._buy.append(name)
        elif m == "fuse":
            if name in self._fuse:
                self._fuse.discard(name)
            else:
                self._fuse.add(name)
        elif m == "enhance1":
            if name in self._enh1:
                self._enh1.discard(name)
            else:
                self._enh1.add(name)
                self._enh2.discard(name)             # one enhance level only
        elif m == "enhance2":
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
    def _clear_layout(lay):
        while lay.count():
            item = lay.takeAt(0)
            w = item.widget()
            if w is not None:
                w.setParent(None)
                w.setParent(None)
                w.deleteLater()

    def _rebuild_summary(self):
        if not hasattr(self, "_summary_col"):
            return
        self._clear_layout(self._summary_col)
        groups = (
            ("keep_fuse", "Keep · no fuse", _MARKET_KEEPFUSE_COL,
             [(0, n) for n in sorted(self._keep_fuse)]),
            ("keep_sell", "Keep · no sell", _MARKET_KEEPSELL_COL,
             [(0, n) for n in sorted(self._keep_sell)]),
            ("sell", "Sell", _MARKET_SELL_COL,
             [(0, n) for n in sorted(self._sell)]),
            ("buy", "Buy priority", _MARKET_BUY_COL,
             list(enumerate(self._buy, 1))),
            ("fuse", "Fuse target", _MARKET_FUSE_COL,
             [(0, n) for n in sorted(self._fuse)]),
            ("enhance1", "Enhance once", _MARKET_ENH1_COL,
             [(0, n) for n in sorted(self._enh1)]),
            ("enhance2", "Enhance twice", _MARKET_ENH2_COL,
             [(0, n) for n in sorted(self._enh2)]),
        )
        shown = False
        for key, label, col, items in groups:
            if not items:
                continue
            shown = True
            roww = QWidget(self._summary_holder)
            rl = QHBoxLayout(roww)
            rl.setContentsMargins(0, 0, 0, 0)
            rl.setSpacing(Sizing.SPACE_SM)
            tag = QLabel(label, roww, objectName="inlineMeta")
            tag.setFixedWidth(104)
            tag.setStyleSheet(f"color:{col};")
            rl.addWidget(tag, 0, Qt.AlignmentFlag.AlignTop)
            chipholder = QWidget(roww)
            flow = FlowLayout(chipholder, spacing=4)
            for num, name in items:
                text = f"{num}.  {name}" if num else name
                chip = QPushButton(f"{text}   ×", chipholder)
                chip.setCursor(Qt.CursorShape.PointingHandCursor)
                chip.setStyleSheet(tag_chip_qss(col))
                chip.clicked.connect(
                    lambda _=False, k=key, nm=name: self._remove_tag(k, nm))
                flow.addWidget(chip)
            rl.addWidget(chipholder, 1)
            self._summary_col.addWidget(roww)
        self._summary_holder.setVisible(shown)

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
        total = len(self._keep_fuse | self._keep_sell | self._sell
                    | set(self._buy) | self._fuse | self._enh1 | self._enh2)
        self._count.setText(f"{total} configured")
        self._reset_btn.setEnabled(bool(self._keep_fuse or self._keep_sell
                                        or self._sell or self._buy
                                        or self._fuse or self._enh1
                                        or self._enh2))
        self._rebuild_summary()

    def reset(self):
        if not (self._keep_fuse or self._keep_sell or self._sell or self._buy
                or self._fuse or self._enh1 or self._enh2):
            return
        self._keep_fuse = set()
        self._keep_sell = set()
        self._sell = set()
        self._buy = []
        self._fuse = set()
        self._enh1 = set()
        self._enh2 = set()
        self._refresh_all_badges()
        self._refresh_counts()
        self.changed.emit()

    def config(self) -> dict:
        return {"keep_fuse": sorted(self._keep_fuse),
                "keep_sell": sorted(self._keep_sell),
                "sell": sorted(self._sell), "buy": list(self._buy),
                "fuse": sorted(self._fuse),
                "enhance1": sorted(self._enh1),
                "enhance2": sorted(self._enh2)}

    def set_config(self, cfg):
        cfg = cfg or {}
        def valid(key):
            return {n for n in (cfg.get(key) or []) if n in self._tiles}
        self._keep_fuse = valid("keep_fuse")
        self._keep_sell = valid("keep_sell")
        self._sell = valid("sell") - self._keep_sell   # enforce exclusivity
        self._fuse = valid("fuse")
        self._enh1 = valid("enhance1")
        self._enh2 = valid("enhance2") - self._enh1    # enforce exclusivity
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


class _SkillSwapCard(QFrame):
    """Drag-reorderable row: rank | grip | label | repeats spinbox."""

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
        for i, card in enumerate(self._cards):
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
    """Chip with two independent states: `selected` (yellow outline,
    exclusive) and `active` (yellow dot prefix, any number).

    Click emits `selected`; double-click emits `toggled_active`.
    """

    selected = Signal(str)
    toggled_active = Signal(str)

    def __init__(self, name: str, parent: QWidget | None = None):
        super().__init__(name, parent)
        self._name = name
        self._is_selected = False
        self._is_active = False
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
        # Yellow-dot prefix keeps the active state visible without colour.
        self.setText(f"●  {self._name}" if self._is_active else self._name)
        self._apply_state()

    def is_selected(self) -> bool:
        return self._is_selected

    def set_selected(self, on: bool):
        self._is_selected = bool(on)
        self._apply_state()

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
# Display suffixes per BUFF state.
_GRACE_TIERS = ("", "", "+", "++")

# Reward-card types in priority order (card0..card4).
_CARD_NAMES = (
    "Cost + Gift", "Cost", "Gift", "Resource", "Starlight",
)


def _floors_1_to_5(data: dict) -> dict:
    """Restrict a floor->packs dict to floors 1-5."""
    return {f: list(data[f]) for f in sorted(data) if 1 <= f <= 5}


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

        aff_lbl = QLabel("  ·  ".join(affinities), self)
        aff_lbl.setObjectName("teamRowAffinities")
        col.addWidget(aff_lbl)
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


class MirrorDungeonPage(QWidget):

    # Header + tab bar are pinned; each tab scrolls independently.
    manages_scroll = True

    start_requested = Signal()
    stop_requested = Signal()
    # Emitted by the "Go to SAIKAI / Thrill settings" link; the shell
    # navigates to the Settings page.
    open_stk_settings = Signal()

    _TABS = ("General", "Build", "Packs", "EGO Gift Search", "Market/Fuse")

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("root")
        self._loading = False
        self._build()
        self._connect_persistence()
        self._restore_state()

    def refresh_theme(self):
        """Re-apply the per-widget stylesheets that bake tokens in at build
        time. themes._restyle_running_app rebuilds the GLOBAL sheet on a skin
        or theme switch, but a string already stored on a widget keeps its old
        values until the app restarts - which is how pockets of the previous
        look survived a live switch."""
        from .widgets import page_fill_qss
        for name in ("egoGiftsPage", "marketPage"):
            w = self.findChild(QWidget, name)
            if w is not None:
                w.setStyleSheet(f"QWidget#{name} {{ {page_fill_qss()} }}")

    def _build(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(
            Sizing.SPACE_XXL, Sizing.SPACE_XL, Sizing.SPACE_XXL, 0,
        )
        root.setSpacing(Sizing.SPACE_MD)

        # Pinned header.
        header = PageHeader("Mirror Dungeon", self)
        self._start_btn = PrimaryButton(
            seasonal.title("Start Mirror Dungeon"), self)
        self._start_btn.clicked.connect(self.start_requested.emit)
        header.add_action(self._start_btn)
        self._stop_btn = GhostButton("Stop", self)
        self._stop_btn.setEnabled(False)
        self._stop_btn.clicked.connect(self.stop_requested.emit)
        header.add_action(self._stop_btn)
        root.addWidget(header)

        # Pinned tab bar.
        self._tabbar = IconlessTabBar(list(self._TABS), default="General", parent=self)
        self._tabbar.selection_changed.connect(self._on_tab)
        root.addWidget(self._tabbar)
        root.addWidget(HRule(self))

        # Tab content - each tab scrolls on its own.
        self._tab_stack = AnimatedStack(self)
        # No explicit surface: AnimatedStack keeps the snapshot's alpha and
        # leaves the overlay clear on voxel, so the page backdrop (grid and
        # twinkle) stays visible under a sliding tab. Forcing a flat colour
        # here is what made the background vanish mid-transition.
        self._tab_stack.addWidget(self._scroll(self._build_general_tab()))
        self._tab_stack.addWidget(self._scroll(self._build_build_tab()))
        self._tab_stack.addWidget(self._scroll(self._build_packs_tab()))
        # The EGO gift gallery manages its own internal scroll (pinned search/reset).
        self._tab_stack.addWidget(self._build_egogifts_tab())
        # Market tab scrolls as one page so the buying card scrolls with the grid.
        self._tab_stack.addWidget(self._scroll(self._build_market_tab()))
        root.addWidget(self._tab_stack, stretch=1)

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
            self._tab_stack.setCurrentIndex(self._TABS.index(label))

    # --- Tabs ------------------------------------------------------
    def _build_general_tab(self) -> QWidget:
        page = QWidget()
        page.setObjectName("root")
        col = QVBoxLayout(page)
        col.setContentsMargins(0, Sizing.SPACE_LG, Sizing.SPACE_LG, Sizing.SPACE_XL)
        col.setSpacing(Sizing.SPACE_LG)

        # 2x2 grid of equal-size cards above a full-width Behaviour card.
        grid = QGridLayout()
        grid.setHorizontalSpacing(Sizing.SPACE_XXL)
        grid.setVerticalSpacing(Sizing.SPACE_LG)
        cells = [
            (self._build_run_section(), 0, 0),
            (self._build_team_section(), 0, 1),
            (self._build_difficulty_section(), 1, 0),
            (self._build_custom_run_section(), 1, 1),
        ]
        for card, r, c in cells:
            card.setSizePolicy(QSizePolicy.Policy.Preferred,
                               QSizePolicy.Policy.Preferred)
            grid.addWidget(card, r, c, alignment=Qt.AlignmentFlag.AlignTop)
        # Columns share the width; rows do NOT share the height, or the two
        # short cards get stretched to match their taller neighbours and each
        # ends up mostly empty.
        grid.setColumnStretch(0, 1)
        grid.setColumnStretch(1, 1)
        col.addLayout(grid)

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
        cards.setMinimumWidth(260)
        cards.setMaximumWidth(440)
        right.addWidget(cards)
        right.addStretch(1)
        side.addLayout(right, stretch=2)

        # Centre the block vertically; stretches collapse when content overflows.
        col.addStretch(2)
        col.addLayout(side)
        col.addStretch(3)
        return page

    def _build_packs_tab(self) -> QWidget:
        page = QWidget()
        page.setObjectName("root")
        col = QVBoxLayout(page)
        col.setContentsMargins(0, Sizing.SPACE_LG, Sizing.SPACE_LG, Sizing.SPACE_XL)
        col.setSpacing(Sizing.SPACE_LG)
        col.addWidget(self._build_pack_search_section())
        col.addWidget(self._build_packs_section())
        col.addStretch(1)
        return page

    # --- Difficulty -----------------------------------------------
    def _build_difficulty_section(self) -> QWidget:
        section = Card("DIFFICULTY", self, collapsible=True)
        self._difficulty = Segmented(
            ["Normal", "Hard", "Extreme"], default="Hard", parent=section,
        )
        self._difficulty.selection_changed.connect(self._on_difficulty)
        # Pin the segmented to its natural width (left-aligned).
        row = QHBoxLayout()
        row.addWidget(self._difficulty)
        row.addStretch(1)
        section.body.addLayout(row)

        hint = QLabel(
            MD_DIFFICULTY_HINT,
            self, objectName="inlineHint",
        )
        hint.setWordWrap(True)
        section.body.addWidget(hint)
        return section

    def _on_difficulty(self, label: str):
        # Normal uses FLOORS; Hard and Extreme use HARD_FLOORS.
        if not hasattr(self, "_floor_packs"):
            return
        if label == "Normal":
            self._floor_packs.set_data(_floors_for_picker(FLOORS, 5), BANNED)
        else:
            # Normal/Hard are 5-floor; only Extreme goes to 15.
            max_floor = 15 if label == "Extreme" else 5
            self._floor_packs.set_data(
                _floors_for_picker(HARD_FLOORS, max_floor), HARD_BANNED)

    # --- Custom run -----------------------------------------------
    def _build_custom_run_section(self) -> QWidget:
        # On/off lives in the card header (top-right).
        self._custom_run = Toggle(default=False, parent=self)
        self._custom_run.toggled.connect(self._on_custom_run)
        section = Card("CUSTOM RUN", self, trailing=self._custom_run,
                       collapsible=True)

        hint = QLabel(
            MD_CUSTOM_RUN_HINT,
            self, objectName="inlineHint",
        )
        hint.setWordWrap(True)
        section.body.addWidget(hint)

        self._custom_strategy = Segmented(
            ["F3 Hard", SAIKAI_LABEL, "Thrill", HOLLOW_LABEL],
            default="F3 Hard", parent=section)
        # Thrill is unfinished: it stays on show but cannot be picked, and
        # a saved config that had it selected falls back to the default.
        self._custom_strategy.set_locked("Thrill", "W.I.P")
        self._custom_strategy.locked_clicked.connect(self._on_locked_strategy)
        section.body.addWidget(self._custom_strategy)

        self._stk_link = LinkButton("Go to custom run settings", section)
        self._stk_link.clicked.connect(self.open_stk_settings.emit)
        self._stk_link.setVisible(False)
        section.body.addWidget(self._stk_link)

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
        self._update_gift_lock()

    def _on_locked_strategy(self, _label: str):
        from .dialogs import show_notice
        show_notice(self, "Thrill runs are still being built, so they are "
                    "switched off for now.", title="W.I.P")

    def _update_gift_lock(self, *_):
        """SAIKAI pins its Spiderweb gift in the picker (mandatory, locked);
        Hollow pins Grand Welcome and Sharp Needle & Thread the same way
        (its Cigarette Holder comes from the starter screen, not from here).
        Each custom strategy edits its own Market/Fuse tag slot, and picking
        Hollow clears the gift search first, so no earlier config bleeds
        into its run."""
        if hasattr(self, "_stk_link"):
            self._stk_link.setVisible(
                self._custom_run.isChecked()
                and self._custom_strategy.selected() in (
                    SAIKAI_LABEL, "Thrill", HOLLOW_LABEL))
        saikai = (self._custom_run.isChecked()
                  and self._custom_strategy.selected() == SAIKAI_LABEL)
        hollow = (self._custom_run.isChecked()
                  and self._custom_strategy.selected() == HOLLOW_LABEL)
        if hasattr(self, "_market_gallery"):
            # Swap the gallery to the strategy's tag slot (state() serializes
            # the inactive slots from _market_slots, so no save is needed
            # here). Hollow's slot starts empty.
            want = "saikai" if saikai else "hollow" if hollow else "normal"
            if want != self._market_slot:
                self._market_slots[self._market_slot] = \
                    self._market_gallery.config()
                self._market_slot = want
                cfg = self._market_slots.get(want)
                if want == "saikai" and cfg is None:
                    cfg = self._saikai_market_seed()
                    self._market_slots["saikai"] = cfg
                if want == "hollow" and cfg is None:
                    cfg = {}
                    self._market_slots["hollow"] = cfg
                self._market_gallery.set_config(cfg or {})
            self._market_slot_hint.setText(_MARKET_SLOT_HINTS.get(want, ""))
            self._market_slot_hint.setVisible(want != "normal")
        if not hasattr(self, "_gift_gallery"):
            return
        strategy = (SAIKAI_LABEL if saikai else HOLLOW_LABEL if hollow
                    else None)
        if (hollow and strategy != getattr(self, "_gift_lock_strategy", None)
                and not self._loading):
            self._gift_gallery.set_selected([])
        self._gift_lock_strategy = strategy
        self._gift_gallery.set_locked(
            ["Spiderweb Entangled in Red"] if saikai
            else list(HOLLOW_SEARCH_GIFTS) if hollow else [])

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

        hint = QLabel(
            "Teams cycle in this order across runs. Add a team to "
            "include it in the rotation.",
            self,
        )
        hint.setObjectName("inlineHint")
        hint.setWordWrap(True)
        section.body.addSpacing(Sizing.SPACE_XS)
        section.body.addWidget(hint)
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
        self._custom_strategy.selection_changed.connect(self._save_state)
        self._custom_strategy.selection_changed.connect(self._update_gift_lock)
        for sb in (self._run_count, self._retry_count, self._pack_refreshes):
            sb.valueChanged.connect(self._save_state)
        for tog in self._behaviour.values():
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
            "custom_run": self._custom_run.isChecked(),
            "custom_strategy": self._custom_strategy.selected(),
            "gift_search": self._gift_search_selection(),
            "market_gifts": self._market_slot_cfg("normal"),
            "market_gifts_saikai": self._market_slot_cfg("saikai"),
            "market_gifts_hollow": self._market_slot_cfg("hollow"),
            "market_controls": self._market_controls_config(),
            "skill_replace": {
                "active":  sorted(self._skill_active),
                "order":   {n: list(order)
                            for n, order in self._skill_order.items()},
                "repeats": {n: dict(rep)
                            for n, rep in self._skill_repeats.items()},
            },
            "run_count": self._run_count.value(),
            "retry_count": self._retry_count.value(),
            "pack_refreshes": self._pack_refreshes.value(),
            "behaviour": {k: t.isChecked()
                          for k, t in self._behaviour.items()},
            "teams": self._teams,
            "grace": {n: c.state() for n, c in self._grace_chips.items()},
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
        save_section(_SECTION, self.state())

    def _restore_state(self):
        s = load_section(_SECTION)
        if not s:
            return
        self._loading = True
        try:
            diff = s.get("difficulty")
            if diff in ("Normal", "Hard", "Extreme"):
                self._difficulty.set_selected(diff)
                self._on_difficulty(diff)
            strat = s.get("custom_strategy")
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
                self._gift_lock_strategy = (
                    SAIKAI_LABEL if saikai else HOLLOW_LABEL if hollow
                    else None)
                cfg = self._market_slots[self._market_slot]
                if self._market_slot == "saikai" and cfg is None:
                    cfg = self._saikai_market_seed()
                    self._market_slots["saikai"] = cfg
                if self._market_slot == "hollow" and cfg is None:
                    cfg = {}
                    self._market_slots["hollow"] = cfg
                self._market_gallery.set_config(cfg or {})
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
            teams = s.get("teams")
            if isinstance(teams, list) and teams:
                self._teams = teams
                self._rebuild_team_rows()
            for n, st in (s.get("grace") or {}).items():
                if n in self._grace_chips:
                    self._grace_chips[n].set_state(int(st))
            card = s.get("card")
            if isinstance(card, list) and card:
                self._card_priority.set_state(card, [])
            if s.get("packs"):
                self._floor_packs.apply_state(s["packs"])
            if s.get("global_packs"):
                self._floor_packs.apply_global_state(s["global_packs"])
        except (TypeError, ValueError):
            pass
        finally:
            self._loading = False
        # Programmatic set_selected above does not emit selection_changed, so
        # re-derive the SAIKAI-dependent UI (gift lock, market auto-tags, link).
        self._update_gift_lock()

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

        hint = QLabel(
            MD_RUN_COUNT_HINT,
            self, objectName="inlineHint",
        )
        hint.setWordWrap(True)
        section.body.addWidget(hint)
        return section

    # --- Behaviour toggles ---------------------------------------
    def _build_behaviour_section(self) -> QWidget:
        section = Card("BEHAVIOUR", self, collapsible=True)
        self._behaviour = {}

        rows = [
            ("bonus", "Claim bonus",
             "Auto-claim the floor-end bonus reward.", True),
            ("restart", "Restart on failure",
             "If the run fails, immediately start another with the same team.", True),
            ("altf4", "Close Limbus when finished",
             "Sends Alt+F4 after the queue runs out.", False),
            # Drives NETZACH. Fires only when enkephalin is FULL; banks
            # the surplus into modules (not a low-fuel refill).
            ("enkephalin", "Convert enkephalin to modules",
             "When enkephalin is full at the run/stage entrance, bank the "
             "surplus into modules so it is not wasted.", True),
            ("skip", "Skip dialogue",
             "Click through pre-battle cutscenes and dialogue.", True),
            ("pack_search", "Pack search",
             "Refresh the floor's pack offering to hunt for your priority "
             "packs. Off: take a random available pack (or your configured "
             "priority/avoid picks) without refreshing.", True),
            ("swap_max_energy", "Swap for max energy",
             "At the squad screen (after team select, before entering), swap "
             "each 0-energy sinner for a +5 max-energy one. Leaves the sinners "
             "in your Sinner swap exclusion (Settings) alone.", False),
            ("winrate", "Always pick winrate",
             "Pick the highest win-rate clash even when damage roll is bigger.", True),
            ("wishmaking", "Wishmaking",
             "Use the wishmaking gift mechanic when available.", False),
            # Shop / EGO skip toggles - gated in shop.py.
            ("skip_restshop", "Skip rest shop",
             "Walk past the mid-run rest stop without shopping.", False),
            ("skip_ego_check", "Skip EGO check",
             "Don't review owned EGO gifts at the shop.", False),
            ("skip_ego_fusion", "Skip EGO fusion",
             "Don't fuse gifts into higher tiers.", False),
            ("skip_ego_enhancing", "Skip EGO enhancing",
             "Don't spend resources upgrading gifts.", False),
            ("skip_ego_buying", "Skip EGO buying",
             "Don't purchase gifts from the shop.", False),
            ("skip_sinner_healing", "Skip sinner healing",
             "Don't heal sinners at the rest stop.", False),
            ("claim_on_defeat", "Claim rewards on defeat",
             "Take the partial rewards when a run fails.", False),
            # Reaches outside the macro into the OS - gets a Windows logo.
            ("logout_on_finish", "Log out of Windows when finished",
             "Sends a Windows logout (shutdown /l) when the queue runs "
             "out. Closes Limbus first if Close Limbus when finished is "
             "also on.", False),
        ]
        # Numeric inputs go above the toggle grid.
        nums = QHBoxLayout()
        nums.setSpacing(Sizing.SPACE_XL)
        self._retry_count = QSpinBox(section)
        self._retry_count.setObjectName("runCount")
        self._retry_count.setRange(0, 99)
        self._retry_count.setValue(0)
        self._retry_count.setFixedWidth(90)
        retry_box = QVBoxLayout()
        retry_box.setSpacing(2)
        retry_box.addWidget(QLabel("Retry count on defeat", section,
                                   objectName="settingTitle"))
        retry_box.addWidget(self._retry_count)
        nums.addLayout(retry_box)

        self._pack_refreshes = QSpinBox(section)
        self._pack_refreshes.setObjectName("runCount")
        self._pack_refreshes.setRange(0, 99)
        self._pack_refreshes.setValue(7)
        self._pack_refreshes.setFixedWidth(90)
        refresh_box = QVBoxLayout()
        refresh_box.setSpacing(2)
        refresh_box.addWidget(QLabel("Pack refreshes", section,
                                     objectName="settingTitle"))
        refresh_box.addWidget(self._pack_refreshes)
        nums.addLayout(refresh_box)
        nums.addStretch(1)
        section.body.addLayout(nums)
        section.body.addSpacing(Sizing.SPACE_MD)

        # Grouped two-column layout. Previously the 17 rows were poured into a
        # grid row-major, so column 0 held rows 1,3,5,7... and the six related
        # shop/EGO skips were scattered across both columns - the toggles read
        # as randomly placed because, in reading order, they were.
        from .widgets import windows_logo_pixmap
        _icons = {
            "logout_on_finish": windows_logo_pixmap(18),
        }
        by_key = {r[0]: r for r in rows}
        groups = (
            ("RUN", ("bonus", "enkephalin", "skip", "winrate",
                     "swap_max_energy")),
            ("PACKS", ("pack_search",)),
            ("ON DEFEAT", ("restart", "claim_on_defeat")),
            ("SHOP AND EGO", ("skip_restshop", "skip_ego_check",
                              "skip_ego_fusion", "skip_ego_enhancing",
                              "skip_ego_buying", "skip_sinner_healing",
                              "wishmaking")),
            ("WHEN FINISHED", ("altf4", "logout_on_finish")),
        )
        columns = ((0, 1, 2), (3, 4))
        cols = QHBoxLayout()
        cols.setSpacing(Sizing.SPACE_XXL)
        self._behaviour_groups = {}
        for group_ids in columns:
            col = QVBoxLayout()
            col.setSpacing(0)
            for gid in group_ids:
                name, keys = groups[gid]
                if gid != group_ids[0]:
                    col.addSpacing(Sizing.SPACE_MD)
                group = CollapsibleSection(name, section)
                group.setMaximumWidth(_BEHAVIOUR_RAIL)
                self._behaviour_groups[name] = group
                for key in keys:
                    _k, title, subtitle, default = by_key[key]
                    tog = Toggle(default=default, parent=section)
                    self._behaviour[key] = tog
                    group.body.addWidget(SettingRow(
                        title, subtitle, tog, parent=section,
                        leading_icon=_icons.get(key), rail=_BEHAVIOUR_RAIL))
                col.addWidget(group, 0, Qt.AlignmentFlag.AlignLeft)
            col.addStretch(1)
            cols.addLayout(col, 1)
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
        hint = QLabel(
            "Pick up to 3 EGO gifts to auto-select at the start of each "
            "Mirror Dungeon run. Click a thumbnail to add or remove it; "
            "search by name or browse by keyword tab. (SAIKAI keeps Spiderweb "
            "locked in.)",
            page, objectName="inlineHint")
        hint.setWordWrap(True)
        col.addWidget(hint)
        self._gift_gallery = _GiftGallery(max_picks=3, parent=page)
        self._gift_gallery.changed.connect(self._save_state)
        col.addWidget(self._gift_gallery, 1)
        return page

    def _build_market_tab(self) -> QWidget:
        """The Market tab: buying-workflow controls + per-gift keep/sell/buy config."""
        page = QWidget()
        page.setObjectName("marketPage")
        page.setStyleSheet(f"QWidget#marketPage {{ {page_fill_qss()} }}")
        col = QVBoxLayout(page)
        col.setContentsMargins(Sizing.SPACE_XL, Sizing.SPACE_LG,
                               Sizing.SPACE_XL, Sizing.SPACE_LG)
        col.setSpacing(Sizing.SPACE_MD)

        # Buying-workflow card: master toggle + reroll controls. The reroll
        # rows grey out when they don't apply (see _sync_market_controls).
        card = Card("MARKET BUYING", page)
        self._market_controls_card = card

        self._default_market_workflow = Toggle(default=True, parent=card)
        self._default_market_workflow.toggled.connect(self._save_state)
        self._default_market_workflow.toggled.connect(self._sync_market_controls)
        card.body.addWidget(SettingRow(
            "Default market workflow",
            "On: buy by affinity and tier as usual. Off: buy only the gifts "
            "you tag Buy priority below, then reroll.",
            self._default_market_workflow, parent=card))

        self._market_refresh_count = QSpinBox(card)
        self._market_refresh_count.setObjectName("runCount")
        self._market_refresh_count.setRange(0, 99)
        self._market_refresh_count.setValue(0)
        self._market_refresh_count.setFixedWidth(72)
        self._market_refresh_count.valueChanged.connect(self._save_state)
        self._market_count_row = SettingRow(
            "Refresh count",
            "How many times to reroll the shop while buying your tagged gifts.",
            self._market_refresh_count, parent=card)
        card.body.addWidget(self._market_count_row)

        self._market_refresh_until_cost = Toggle(default=False, parent=card)
        self._market_refresh_until_cost.toggled.connect(self._save_state)
        self._market_refresh_until_cost.toggled.connect(self._sync_market_controls)
        self._market_until_row = SettingRow(
            "Refresh until cost available",
            "Keep rerolling while you can still afford it, ignoring the count.",
            self._market_refresh_until_cost, parent=card)
        card.body.addWidget(self._market_until_row)

        self._buy_ego_fuel = Toggle(default=False, parent=card)
        self._buy_ego_fuel.toggled.connect(self._save_state)
        self._buy_fuel_row = SettingRow(
            "Buy EGO fuel",
            "When crafting a Fuse target, buy the missing fuel gifts from the "
            "shop shelf. Off: fuse only from gifts you already own.",
            self._buy_ego_fuel, parent=card)
        card.body.addWidget(self._buy_fuel_row)

        col.addWidget(card)
        self._sync_market_controls()

        hint = QLabel(
            "Tag each EGO gift: Keep · no fuse (never fuse it), Keep · no sell "
            "(never sell it), Sell (sell it), or Buy priority (bought in the "
            "order you click, badged 1, 2, 3). Untouched gifts keep the bot's "
            "default behaviour.",
            page, objectName="inlineHint")
        hint.setWordWrap(True)
        col.addWidget(hint)

        # Two independent tag configs: the normal one and a SAIKAI one that is
        # seeded from the preset the first time SAIKAI is selected and stays
        # fully editable. The gallery edits whichever slot is active.
        self._market_slot = "normal"
        self._market_slots = {"normal": {}, "saikai": None, "hollow": None}
        self._market_slot_hint = QLabel(_MARKET_SLOT_HINTS["saikai"],
                                        page, objectName="inlineHint")
        self._market_slot_hint.setWordWrap(True)
        self._market_slot_hint.setVisible(False)
        col.addWidget(self._market_slot_hint)

        self._market_gallery = _MarketGiftGallery(parent=page, scrollable=False)
        self._market_gallery.changed.connect(self._save_state)
        col.addWidget(self._market_gallery)
        return page

    @staticmethod
    def _saikai_market_seed() -> dict:
        from wbcore.market_catalog import SAIKAI_MARKET_TAGS
        return {k: list(v) for k, v in SAIKAI_MARKET_TAGS.items()}

    def _market_slot_cfg(self, slot):
        """The tag dict for `slot`: live from the gallery when that slot is
        active, else the stored copy. None = a strategy slot never saved
        (SAIKAI's preset seeds it on first use; Hollow's starts empty)."""
        if not hasattr(self, "_market_gallery"):
            return {} if slot == "normal" else None
        if slot == self._market_slot:
            return self._market_gallery.config()
        return self._market_slots.get(slot)

    def _market_controls_config(self) -> dict:
        """Market workflow toggles + refresh count from the Market tab."""
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

        hint = QLabel(
            MD_SKILL_REPLACEMENT_HINT_RICH,
            self, objectName="inlineHint")
        hint.setWordWrap(True)
        hint.setTextFormat(Qt.TextFormat.RichText)
        section.body.addWidget(hint)
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
        section.body.addWidget(self._floor_packs)
        return section

    # --- Pack Search fallback -------------------------------------
    _PS_FLOORS = (1, 2, 3, 4, 5)

    def _build_pack_search_section(self) -> QWidget:
        section = Card("PACK SEARCH", self)
        hint = QLabel(
            "Per floor: when the pack below is not on offer after the "
            "refreshes, open the in-game Pack Search and secure it instead "
            "of settling for a fallback pick. Type a pack name - it "
            "autofills, Tab completes it.",
            section, objectName="inlineHint")
        hint.setWordWrap(True)
        section.body.addWidget(hint)

        self._ps_rows = {}
        self._ps_valid = {}
        grid = QGridLayout()
        grid.setHorizontalSpacing(Sizing.SPACE_MD)
        grid.setVerticalSpacing(Sizing.SPACE_XS)
        for i, fl in enumerate(self._PS_FLOORS):
            lbl = QLabel(f"Floor {fl}", section, objectName="settingTitle")
            grid.addWidget(lbl, i, 0)

            edit = _PackSearchEdit(section)
            edit.setObjectName("textField")
            edit.setPlaceholderText("No pack configured")
            edit.setClearButtonEnabled(True)
            comp = QCompleter(_pack_search_names_for_floor(fl), edit)
            comp.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
            comp.setCompletionMode(QCompleter.CompletionMode.InlineCompletion)
            edit.setCompleter(comp)
            edit.editingFinished.connect(
                lambda f=fl: self._ps_commit_edit(f))
            grid.addWidget(edit, i, 1)

            tog = Toggle(default=False, parent=section)
            tog.toggled.connect(self._save_state)
            grid.addWidget(tog, i, 2)

            self._ps_rows[fl] = (tog, edit)
        grid.setColumnStretch(1, 1)
        section.body.addLayout(grid)
        return section

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
        section = Card("STARTING GRACE", self)
        grace_hint = QLabel(
            MD_GRACE_HINT,
            self, objectName="inlineHint",
        )
        grace_hint.setWordWrap(True)
        section.body.addWidget(grace_hint)
        flow_host = QWidget(section)
        flow = FlowLayout(flow_host, spacing=Sizing.SPACE_XS)
        self._grace_chips = {}
        # Default: first 4 graces at base tier (BUFF = [1,1,1,1,0,...]).
        for i, name in enumerate(_GRACE_NAMES):
            chip = CycleChip(name, _GRACE_TIERS, flow_host)
            if i < 4:
                chip.set_state(1)
            flow.addWidget(chip)
            self._grace_chips[name] = chip
        section.body.addWidget(flow_host)
        return section

    # --- Card priority (Hard MD) ---------------------------------
    def _build_cards_section(self) -> QWidget:
        section = Card("CARD PRIORITY", self)
        card_hint = QLabel(
            "Reward-card preference order on Hard MD. The bot favours "
            "the type at the top. Reorder with the arrows.",
            self, objectName="inlineHint",
        )
        card_hint.setWordWrap(True)
        section.body.addWidget(card_hint)
        self._card_priority = OrderedList(_CARD_NAMES, parent=section)
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
