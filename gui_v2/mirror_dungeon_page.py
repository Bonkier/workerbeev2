# SPDX-License-Identifier: GPL-3.0-or-later
"""Mirror Dungeon page - the full run-config surface."""

from PySide6.QtCore import QMimeData, QPoint, Qt, QTimer, Signal
from PySide6.QtGui import QDrag
from PySide6.QtWidgets import (
    QApplication, QDialog, QDialogButtonBox, QFrame, QGridLayout, QHBoxLayout,
    QLabel, QLineEdit, QListWidgetItem, QPushButton, QScrollArea, QSizePolicy,
    QSpinBox, QVBoxLayout, QWidget,
)

from .run_config import SAIKAI_LABEL
from .settings import load_section, save_section
from .copy import (
    MD_CUSTOM_RUN_HINT,
    MD_DIFFICULTY_HINT,
    MD_GRACE_HINT,
    MD_RUN_COUNT_HINT,
    MD_SAIKAI_EXCLUSION_HINT,
    MD_SAIKAI_ORDER_HINT,
    MD_SKILL_REPLACEMENT_HINT_RICH,
    MD_THRILL_EXCLUSION_HINT,
    MD_THRILL_ORDER_HINT,
)
from .theme import Colors, Sizing
from .widgets import (
    AnimatedStack, Card, ChipList, ClickOrderGrid, CycleChip, FloorPacks,
    FlowLayout, GhostButton, HRule, IconlessTabBar, LinkButton, OrderedList,
    PageHeader, PrimaryButton, Segmented, SettingRow, Toggle,
    show_placeholder_notice,
)

_SECTION = "mirror"

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


class _SkillSwapCard(QFrame):
    """Drag-reorderable card: handle | label | repeats spinbox."""

    repeats_changed = Signal(str, int)

    def __init__(self, swap_key: str, label: str, repeats: int,
                 parent: QWidget | None = None):
        super().__init__(parent)
        self._swap = swap_key
        self._drag_press: QPoint | None = None
        self.setObjectName("skillSwapCard")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setCursor(Qt.CursorShape.OpenHandCursor)
        # setFixedHeight (not min-height) prevents QVBoxLayout collapsing.
        self.setFixedHeight(56)
        self.setStyleSheet(
            f"QFrame#skillSwapCard {{"
            f"  background-color: {Colors.BG_OVERLAY};"
            f"  border: 1px solid {Colors.BORDER_SUBTLE};"
            f"  border-radius: {Sizing.RADIUS_SM}px;"
            f"}}"
            f"QFrame#skillSwapCard:hover {{"
            f"  background-color: {Colors.BG_HOVER};"
            f"}}"
        )

        h = QHBoxLayout(self)
        # Asymmetric margins (4/8) compensate for the QSpinBox baseline.
        h.setContentsMargins(Sizing.SPACE_MD, 4,
                             Sizing.SPACE_MD, 8)
        h.setSpacing(Sizing.SPACE_MD)

        handle = QLabel("⠇", self)   # braille dots-1237 (grip)
        handle.setStyleSheet(
            f"color: {Colors.TEXT_TERTIARY};"
            f" background: transparent;"
            f" border: none;"
            f" font-size: 18pt;"
        )
        handle.setFixedWidth(18)
        h.addWidget(handle)

        text = QLabel(label, self, objectName="settingTitle")
        text.setStyleSheet(
            "background: transparent; border: none;")
        h.addWidget(text)
        h.addStretch(1)

        rep_lbl = QLabel("Repeats", self, objectName="inlineHint")
        rep_lbl.setStyleSheet(
            "background: transparent; border: none;")
        h.addWidget(rep_lbl)

        self._spin = QSpinBox(self)
        self._spin.setObjectName("runCount")
        self._spin.setRange(0, 99)
        self._spin.setValue(int(repeats or 0))
        self._spin.setFixedSize(110, 34)
        self._spin.valueChanged.connect(
            lambda v: self.repeats_changed.emit(self._swap, int(v)))
        h.addWidget(self._spin, 0, Qt.AlignmentFlag.AlignVCenter)

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


class MirrorDungeonPage(QWidget):

    # Header + tab bar are pinned; each tab scrolls independently.
    manages_scroll = True

    start_requested = Signal()
    stop_requested = Signal()

    _TABS = ("General", "Build", "Packs")

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("root")
        self._loading = False
        self._build()
        self._connect_persistence()
        self._restore_state()

    def _build(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(
            Sizing.SPACE_XXL, Sizing.SPACE_XL, Sizing.SPACE_XXL, 0,
        )
        root.setSpacing(Sizing.SPACE_MD)

        # Pinned header.
        header = PageHeader("Mirror Dungeon", self)
        self._start_btn = PrimaryButton("Start Mirror Dungeon", self)
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
        self._tab_stack.addWidget(self._scroll(self._build_general_tab()))
        self._tab_stack.addWidget(self._scroll(self._build_build_tab()))
        self._tab_stack.addWidget(self._scroll(self._build_packs_tab()))
        root.addWidget(self._tab_stack, stretch=1)

    def _scroll(self, content: QWidget) -> QScrollArea:
        sa = QScrollArea(self)
        sa.setObjectName("pageScroll")
        sa.setWidgetResizable(True)
        sa.setFrameShape(QScrollArea.Shape.NoFrame)
        sa.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
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
                               QSizePolicy.Policy.Expanding)
            grid.addWidget(card, r, c)
        grid.setColumnStretch(0, 1)
        grid.setColumnStretch(1, 1)
        grid.setRowStretch(0, 1)
        grid.setRowStretch(1, 1)
        col.addLayout(grid)

        col.addWidget(self._build_behaviour_section())
        col.addWidget(self._build_thrill_order_section())
        col.addWidget(self._build_thrill_exclusion_section())
        col.addWidget(self._build_saikai_options_section())
        col.addWidget(self._build_saikai_order_section())
        col.addWidget(self._build_saikai_exclusion_section())
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
        col.addWidget(self._build_packs_section())
        col.addStretch(1)
        return page

    # --- Difficulty -----------------------------------------------
    def _build_difficulty_section(self) -> QWidget:
        section = Card("DIFFICULTY", self)
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
        section = Card("CUSTOM RUN", self, trailing=self._custom_run)

        hint = QLabel(
            MD_CUSTOM_RUN_HINT,
            self, objectName="inlineHint",
        )
        hint.setWordWrap(True)
        section.body.addWidget(hint)

        self._custom_strategy = Segmented(
            ["F3 Hard", SAIKAI_LABEL, "Thrill"], default="F3 Hard", parent=section)
        section.body.addWidget(self._custom_strategy)

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
        self._update_thrill_visibility()

    # --- Team rotation --------------------------------------------
    def _build_team_section(self) -> QWidget:
        add_btn = LinkButton("+ Add team", self)
        add_btn.clicked.connect(self._add_team)
        section = Card("TEAM ROTATION", self, trailing=add_btn)
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
        self._custom_strategy.selection_changed.connect(self._update_thrill_visibility)
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
            "thrill_exclude": [n for n, c in self._thrill_excl_chips.items()
                               if c.isChecked()],
            "thrill_order": self._thrill_order.order(),
            "saikai_exclude": [n for n, c in self._saikai_excl_chips.items()
                               if c.isChecked()],
            "saikai_order": self._saikai_order.order(),
            "saikai_only_hard": self._saikai_only_hard.isChecked(),
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
            excl = s.get("thrill_exclude")
            if isinstance(excl, list) and hasattr(self, "_thrill_excl_chips"):
                for n, c in self._thrill_excl_chips.items():
                    c.setChecked(n in excl)
            order = s.get("thrill_order") or []
            if isinstance(order, list) and hasattr(self, "_thrill_order"):
                self._thrill_order.set_order(order)
            saikai_excl = s.get("saikai_exclude")
            if isinstance(saikai_excl, list) and hasattr(self, "_saikai_excl_chips"):
                for n, c in self._saikai_excl_chips.items():
                    c.setChecked(n in saikai_excl)
            saikai_order = s.get("saikai_order") or []
            if isinstance(saikai_order, list) and hasattr(self, "_saikai_order"):
                self._saikai_order.set_order(saikai_order)
            saikai_only_hard = s.get("saikai_only_hard")
            if isinstance(saikai_only_hard, bool) \
                    and hasattr(self, "_saikai_only_hard"):
                self._saikai_only_hard.setChecked(saikai_only_hard)
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

    # --- Run count + general -------------------------------------
    def _build_run_section(self) -> QWidget:
        section = Card("RUN COUNT", self)
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
        section = Card("BEHAVIOUR", self)
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

        # Two-column toggle grid.
        grid = QGridLayout()
        grid.setHorizontalSpacing(Sizing.SPACE_XXL)
        grid.setVerticalSpacing(0)
        grid.setColumnStretch(0, 1)
        grid.setColumnStretch(1, 1)
        from .widgets import windows_logo_pixmap
        # Per-key leading icons for OS-reaching toggles.
        _icons = {
            "logout_on_finish": windows_logo_pixmap(18),
        }
        for i, (key, title, subtitle, default) in enumerate(rows):
            tog = Toggle(default=default, parent=section)
            self._behaviour[key] = tog
            grid.addWidget(
                SettingRow(title, subtitle, tog, parent=section,
                           leading_icon=_icons.get(key)),
                i // 2, i % 2,
            )
        section.body.addLayout(grid)
        return section

    # --- [THRILL] Sinner swap exclusion --------------------------
    # The in-game squad screen is a fixed 6x2 grid in canonical sinner order.
    _THRILL_SQUAD = [
        ["Yi Sang", "Faust", "Don Quixote", "Ryōshū", "Meursault", "Hong Lu"],
        ["Heathcliff", "Ishmael", "Rodion", "Sinclair", "Outis", "Gregor"],
    ]

    def _build_thrill_order_section(self) -> QWidget:
        section = Card("[THRILL] SINNER ORDER", self)
        hint = QLabel(
            MD_THRILL_ORDER_HINT,
            self, objectName="inlineHint")
        hint.setWordWrap(True)
        section.body.addWidget(hint)
        flat = [n for row in self._THRILL_SQUAD for n in row]
        # 12 picks allowed; backend caps the squad at 6 with the rest as fallback.
        self._thrill_order = ClickOrderGrid(
            flat, rows=2, cols=6, max_picks=12, parent=section,
        )
        self._thrill_order.changed.connect(self._save_state)
        section.body.addWidget(self._thrill_order)
        section.setVisible(False)
        self._thrill_order_section = section
        return section

    def _build_thrill_exclusion_section(self) -> QWidget:
        from .widgets import _CheckChip
        section = Card("[THRILL] SINNER SWAP EXCLUSION", self)
        hint = QLabel(
            MD_THRILL_EXCLUSION_HINT, self, objectName="inlineHint")
        hint.setWordWrap(True)
        section.body.addWidget(hint)
        grid = QGridLayout()
        grid.setHorizontalSpacing(Sizing.SPACE_SM)
        grid.setVerticalSpacing(Sizing.SPACE_XS)
        self._thrill_excl_chips = {}
        for r, names in enumerate(self._THRILL_SQUAD):
            for c, name in enumerate(names):
                chip = _CheckChip(name, section)
                chip.toggled.connect(self._on_thrill_exclude_toggled)
                self._thrill_excl_chips[name] = chip
                grid.addWidget(chip, r, c)
        section.body.addLayout(grid)
        section.setVisible(False)
        self._thrill_excl_section = section
        return section

    def _on_thrill_exclude_toggled(self, _on: bool):
        # No cap: battle.py handles 0-12 exclusions natively.
        self._save_state()

    # --- [SAIKAI] Sinner order + exclusion -----------------------
    # Order overrides _SAIKAI_SINNERS; exclusion subtracts from that order.
    _SAIKAI_SQUAD = _THRILL_SQUAD

    def _build_saikai_options_section(self) -> QWidget:
        """SAIKAI run-tuning toggles, gated like the order/exclusion cards."""
        section = Card("[SAIKAI] OPTIONS", self)
        self._saikai_only_hard = Toggle(default=False, parent=section)
        self._saikai_only_hard.toggled.connect(self._save_state)
        row = SettingRow(
            "Hard from F1",
            "Run every floor on Hard difficulty. Default flips Normal -> "
            "Hard at Floor 4 to match the scripted SAIKAI build; tick this "
            "to start Hard from Floor 1 instead.",
            self._saikai_only_hard,
            parent=section,
        )
        section.body.addWidget(row)
        section.setVisible(False)
        self._saikai_options_section = section
        return section

    def _build_saikai_order_section(self) -> QWidget:
        section = Card("[SAIKAI] SINNER ORDER", self)
        hint = QLabel(
            MD_SAIKAI_ORDER_HINT,
            self, objectName="inlineHint")
        hint.setWordWrap(True)
        section.body.addWidget(hint)
        flat = [n for row in self._SAIKAI_SQUAD for n in row]
        self._saikai_order = ClickOrderGrid(
            flat, rows=2, cols=6, max_picks=12, parent=section,
        )
        self._saikai_order.changed.connect(self._save_state)
        section.body.addWidget(self._saikai_order)
        section.setVisible(False)
        self._saikai_order_section = section
        return section

    def _build_saikai_exclusion_section(self) -> QWidget:
        from .widgets import _CheckChip
        section = Card("[SAIKAI] SINNER EXCLUSION", self)
        hint = QLabel(
            MD_SAIKAI_EXCLUSION_HINT,
            self, objectName="inlineHint")
        hint.setWordWrap(True)
        section.body.addWidget(hint)
        grid = QGridLayout()
        grid.setHorizontalSpacing(Sizing.SPACE_SM)
        grid.setVerticalSpacing(Sizing.SPACE_XS)
        self._saikai_excl_chips = {}
        for r, names in enumerate(self._SAIKAI_SQUAD):
            for c, name in enumerate(names):
                chip = _CheckChip(name, section)
                chip.toggled.connect(self._on_saikai_exclude_toggled)
                self._saikai_excl_chips[name] = chip
                grid.addWidget(chip, r, c)
        section.body.addLayout(grid)
        section.setVisible(False)
        self._saikai_excl_section = section
        return section

    def _on_saikai_exclude_toggled(self, _on: bool):
        # No cap; set_team skips out-of-range entries.
        self._save_state()

    def _update_thrill_visibility(self, *_):
        """Toggle Thrill AND SAIKAI section visibility. Legacy name retained
        so existing signal connections still wire up."""
        strategy = self._custom_strategy.selected()
        custom_on = self._custom_run.isChecked()
        thrill_on = custom_on and strategy == "Thrill"
        saikai_on = custom_on and strategy == SAIKAI_LABEL
        if hasattr(self, "_thrill_excl_section"):
            self._thrill_excl_section.setVisible(thrill_on)
        if hasattr(self, "_thrill_order_section"):
            self._thrill_order_section.setVisible(thrill_on)
        if hasattr(self, "_saikai_excl_section"):
            self._saikai_excl_section.setVisible(saikai_on)
        if hasattr(self, "_saikai_order_section"):
            self._saikai_order_section.setVisible(saikai_on)
        if hasattr(self, "_saikai_options_section"):
            self._saikai_options_section.setVisible(saikai_on)

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
        section = Card("SHOP: SKILL REPLACEMENT", self)

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

        # 6x2 sinner chip grid (dual-state chip).
        sinner_grid = QGridLayout()
        sinner_grid.setHorizontalSpacing(Sizing.SPACE_SM)
        sinner_grid.setVerticalSpacing(Sizing.SPACE_XS)
        self._skill_chips: dict[str, _SinnerSkillChip] = {}
        for r, names in enumerate(self._SKILL_REPLACE_SINNERS):
            for c, name in enumerate(names):
                chip = _SinnerSkillChip(name, section)
                chip.selected.connect(self._on_skill_sinner_selected)
                chip.toggled_active.connect(self._on_skill_sinner_toggle_active)
                self._skill_chips[name] = chip
                sinner_grid.addWidget(chip, r, c)
        section.body.addLayout(sinner_grid)

        section.body.addSpacing(Sizing.SPACE_MD)
        section.body.addWidget(HRule(section))
        section.body.addSpacing(Sizing.SPACE_SM)

        # Per-sinner details: title + drag-orderable priority list.
        self._skill_details = QFrame(section)
        details_layout = QVBoxLayout(self._skill_details)
        details_layout.setContentsMargins(0, 0, 0, 0)
        details_layout.setSpacing(Sizing.SPACE_SM)
        self._skill_details_layout = details_layout
        section.body.addWidget(self._skill_details)

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
        """Toggle whether the bot visits `name`."""
        if name in self._skill_active:
            self._skill_active.discard(name)
            self._skill_chips[name].set_active(False)
        else:
            self._skill_active.add(name)
            self._skill_chips[name].set_active(True)
        self._render_skill_details()
        self._save_state()

    def _render_skill_details(self):
        """Rebuild the per-sinner priority list."""
        layout = self._skill_details_layout
        while layout.count() > 0:
            item = layout.takeAt(0)
            w = item.widget()
            if w is not None:
                w.deleteLater()

        name = self._skill_selected_name
        active = name in self._skill_active
        status = "enabled" if active else "disabled"
        title = QLabel(
            f"{name} - Skill Replacement  "
            f"<span style='color: {Colors.TEXT_TERTIARY};'>({status})</span>",
            self._skill_details, objectName="settingTitle")
        title.setTextFormat(Qt.TextFormat.RichText)
        layout.addWidget(title)

        label_of = dict(self._SKILL_REPLACE_SWAPS)

        priority = self._skill_order[name]
        items = [(k, label_of[k],
                  self._skill_repeats[name].get(k, 0)) for k in priority]
        self._skill_priority_stack = _SkillPriorityStack(
            items, parent=self._skill_details)
        # Bind the current sinner name into the (key, value) callback.
        sel = name
        self._skill_priority_stack.order_changed.connect(
            self._on_skill_order_changed_v2)
        self._skill_priority_stack.repeats_changed.connect(
            lambda key, val, n=sel: self._on_skill_repeats_v2(n, key, val))
        layout.addWidget(self._skill_priority_stack)

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
        self._start_btn.setText("Start Mirror Dungeon")
        self._stop_btn.setEnabled(running)

    def set_arming(self, seconds: int):
        if seconds > 0:
            self._start_btn.setEnabled(False)
            self._start_btn.setText(f"Tab into game... {seconds}s")
            self._stop_btn.setEnabled(True)
        else:
            self._start_btn.setEnabled(True)
            self._start_btn.setText("Start Mirror Dungeon")
            self._stop_btn.setEnabled(False)
