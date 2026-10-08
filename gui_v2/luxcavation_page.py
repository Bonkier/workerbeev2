# SPDX-License-Identifier: GPL-3.0-or-later
"""Luxcavation page - EXP and Thread grinding, backed by lux.grind_lux."""

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QColor, QPainter, QPen, QPixmap
from PySide6.QtWidgets import (
    QComboBox, QHBoxLayout, QLabel, QSpinBox, QVBoxLayout, QWidget,
)

from . import luxrotation as _luxrot
from .settings import load_section, save_section
from .theme import Colors, Sizing
from .widgets import (
    AnimatedStack, Card, GhostButton, PageHeader, PrimaryButton, Segmented,
    _title_label, show_placeholder_notice,
)

_SECTION = "lux"


# Affinity teams (from lux.py's lux_list).
_LUX_AFFINITIES = (
    "Slash", "Pierce", "Blunt", "Wrath", "Lust",
    "Sloth", "Gluttony", "Gloom", "Pride", "Envy",
)

_EXP_STAGES = [str(i) for i in range(1, 10)]   # 1..9
_EXP_STAGE_DEFAULT = "6"
_THD_DIFFICULTIES = ["20", "30", "40", "50", "60"]
_THD_DIFFICULTY_DEFAULT = "40"


def _combo(items, parent=None):
    box = QComboBox(parent)
    box.setObjectName("combo")
    box.addItems(items)
    box.setCursor(Qt.CursorShape.PointingHandCursor)
    return box


def _spin(default, parent=None):
    sb = QSpinBox(parent)
    sb.setObjectName("runCount")
    sb.setRange(1, 999)
    sb.setValue(default)
    sb.setFixedWidth(84)
    return sb


def _icon_label(name: str, size: int, parent) -> QLabel:
    from .giftart import keyword_icon
    lbl = QLabel(parent)
    lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
    pm = QPixmap(keyword_icon(name))
    if not pm.isNull():
        lbl.setPixmap(pm.scaled(size, size,
                                Qt.AspectRatioMode.KeepAspectRatio,
                                Qt.TransformationMode.SmoothTransformation))
    # Shown explicitly: these are rebuilt on every refresh, and a child added
    # to a layout after its parent was already laid out does not reliably get
    # shown on its own.
    lbl.show()
    return lbl


class _RotationCell(QWidget):
    """One day of a rotation: weekday, icon(s), name."""

    def __init__(self, day: str, names: tuple, today: bool, parent=None):
        super().__init__(parent)
        self._today = today
        self.setToolTip(f"{day}: {chr(47).join(names)}")
        col = QVBoxLayout(self)
        col.setContentsMargins(Sizing.SPACE_SM, Sizing.SPACE_XS,
                               Sizing.SPACE_SM, Sizing.SPACE_XS)
        col.setSpacing(Sizing.SPACE_XXS)

        day_lbl = QLabel(day.upper(), self,
                         objectName="settingTitle" if today else "inlineMeta")
        day_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        col.addWidget(day_lbl)

        icons = QHBoxLayout()
        icons.setSpacing(1)
        icons.addStretch(1)
        for name in names:
            icons.addWidget(_icon_label(name, 24, self))
        icons.addStretch(1)
        col.addLayout(icons)

        text = "ALL" if len(names) > 2 else chr(47).join(names)
        name_lbl = QLabel(text, self,
                          objectName="settingTitle" if today else "inlineMeta")
        name_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        col.addWidget(name_lbl)

    def paintEvent(self, _event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, False)
        if self._today:
            p.fillRect(self.rect(), QColor(255, 255, 255, 26))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.setPen(QPen(QColor(Colors.ACCENT), 1))
            p.drawRect(self.rect().adjusted(0, 0, -1, -1))
        p.end()


class _RotationPanel(QWidget):
    """Today's type for one Luxcavation mode, plus the week ahead.

    The two modes rotate on different keys - Thread on sin affinity, EXP on
    damage type - so each gets its own panel rather than being crammed into
    one row where the two schedules read as a single thing."""

    apply_requested = Signal(str)

    def __init__(self, mode: str, parent=None):
        super().__init__(parent)
        self._mode = mode
        self._suggested = ""
        self._uses = {}
        col = QVBoxLayout(self)
        col.setContentsMargins(0, 0, 0, 0)
        col.setSpacing(Sizing.SPACE_MD)

        head = QHBoxLayout()
        head.setSpacing(Sizing.SPACE_MD)
        self._icons = QHBoxLayout()
        self._icons.setSpacing(Sizing.SPACE_XXS)
        head.addLayout(self._icons)
        text = QVBoxLayout()
        text.setSpacing(Sizing.SPACE_XXS)
        self._name = _title_label("", self, pixel=3, section=False)
        text.addWidget(self._name)
        self._meta = QLabel("", self, objectName="inlineMeta")
        text.addWidget(self._meta)
        head.addLayout(text)
        head.addStretch(1)
        self._apply_btn = GhostButton("", self)
        self._apply_btn.clicked.connect(
            lambda: self.apply_requested.emit(self._suggested))
        head.addWidget(self._apply_btn,
                       0, Qt.AlignmentFlag.AlignVCenter)
        col.addLayout(head)

        self._strip = QHBoxLayout()
        self._strip.setSpacing(Sizing.SPACE_XS)
        col.addLayout(self._strip)

        self._timer = QTimer(self)
        self._timer.setInterval(60_000)
        self._timer.timeout.connect(self.refresh)
        self.refresh()

    def showEvent(self, event):
        super().showEvent(event)
        self.refresh()
        self._timer.start()

    def hideEvent(self, event):
        super().hideEvent(event)
        self._timer.stop()

    @staticmethod
    def _clear(layout):
        while layout.count():
            item = layout.takeAt(0)
            w = item.widget()
            if w is not None:
                w.setParent(None)
                w.deleteLater()

    def set_uses(self, uses: dict):
        """Per-damage-type run counts, used to break Sunday's three-way tie."""
        self._uses = dict(uses or {})
        self.refresh()

    def refresh(self):
        from . import luxrotation as rot
        today = (rot.exp_types() if self._mode == "exp"
                 else (rot.thread_affinity(),))
        hours, rem = divmod(int(rot.next_change().total_seconds()), 3600)

        # Sunday opens all three EXP types, so the button has to choose one:
        # whichever the user runs most, Slash on a tie.
        self._suggested = (rot.preferred_exp_type(today, self._uses)
                           if self._mode == "exp" else today[0])
        self._apply_btn.setText(f"Use {self._suggested} team")
        self._apply_btn.setToolTip(
            f"Switch to {'EXP' if self._mode == 'exp' else 'Thread'} and set "
            f"the team to {self._suggested}")

        self._clear(self._icons)
        for name in today:
            self._icons.addWidget(_icon_label(name, 40, self))
        self._name.setText("ALL" if len(today) > 2 else " / ".join(today))
        self._meta.setText(
            ("Damage type" if self._mode == "exp" else "Sin affinity")
            + f"  ·  rotates in {hours}h {rem // 60}m")

        self._clear(self._strip)
        for day, affinity, exp_day, is_today in rot.week():
            names = exp_day if self._mode == "exp" else (affinity,)
            cell = _RotationCell(day, names, is_today, self)
            cell.show()
            self._strip.addWidget(cell)
        self._strip.addStretch(1)


class LuxcavationPage(QWidget):

    start_exp_requested = Signal()
    start_thread_requested = Signal()
    stop_requested = Signal()

    _TABS = ("EXP", "Thread")

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("root")
        self._loading = False
        self._exp_uses = {}
        self._build()
        self._restore_state()

    def _build(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(
            Sizing.SPACE_XXL, Sizing.SPACE_XL,
            Sizing.SPACE_XXL, Sizing.SPACE_XL,
        )
        outer.setSpacing(Sizing.SPACE_LG)

        header = PageHeader("Luxcavation", self)
        self._stop_btn = GhostButton("Stop", self)
        self._stop_btn.setEnabled(False)
        self._stop_btn.clicked.connect(self.stop_requested.emit)
        header.add_action(self._stop_btn)
        outer.addWidget(header)

        card = Card("RUN SETUP", self)
        card.body.setSpacing(Sizing.SPACE_MD)

        seg_row = QHBoxLayout()
        self._mode = Segmented(list(self._TABS), default="EXP", parent=card)
        self._mode.selection_changed.connect(self._on_mode)
        seg_row.addWidget(self._mode)
        seg_row.addStretch(1)
        card.body.addLayout(seg_row)

        self._tab_stack = AnimatedStack(card)
        # Slide snapshots must sit on the card colour, not the darker page
        # gradient, or the switch dims mid-animation then flashes back.
        from .style import voxel_panel_color
        from .skins import is_voxel
        surface = voxel_panel_color() if is_voxel() else Colors.BG_RAISED
        self._tab_stack.set_surface(f"background-color: {surface};")

        self._exp_runs = _spin(1, card)
        self._exp_stage = _combo(_EXP_STAGES, card)
        self._exp_stage.setCurrentText(_EXP_STAGE_DEFAULT)
        self._exp_team = _combo(list(_LUX_AFFINITIES), card)
        self._exp_start = PrimaryButton("Start EXP", card)
        self._exp_start.clicked.connect(self._on_lux_start)
        self._exp_start.clicked.connect(self._count_exp_use)
        self._exp_start.clicked.connect(self.start_exp_requested.emit)
        self._tab_stack.addWidget(self._mode_tab(
            "EXP", self._exp_runs, "Stage", self._exp_stage,
            self._exp_team, self._exp_start))

        self._thd_runs = _spin(1, card)
        self._thd_diff = _combo(_THD_DIFFICULTIES, card)
        self._thd_diff.setCurrentText(_THD_DIFFICULTY_DEFAULT)
        self._thd_team = _combo(list(_LUX_AFFINITIES), card)
        self._thd_start = PrimaryButton("Start Thread", card)
        self._thd_start.clicked.connect(self._on_lux_start)
        self._thd_start.clicked.connect(self.start_thread_requested.emit)
        self._tab_stack.addWidget(self._mode_tab(
            "Thread", self._thd_runs, "Difficulty", self._thd_diff,
            self._thd_team, self._thd_start))

        card.body.addWidget(self._tab_stack)

        for sb in (self._exp_runs, self._thd_runs):
            sb.valueChanged.connect(self._save_state)
        for cb in (self._exp_stage, self._exp_team,
                   self._thd_diff, self._thd_team):
            cb.currentTextChanged.connect(self._save_state)
        self._mode.selection_changed.connect(self._save_state)

        outer.addWidget(card)

        self._rotations = {}
        for title, mode in (("THREAD ROTATION", "thread"),
                            ("EXP ROTATION", "exp")):
            rot_card = Card(title, self, collapsible=True)
            panel = _RotationPanel(mode, rot_card)
            panel.apply_requested.connect(
                lambda name, m=mode: self._use_team(m, name))
            self._rotations[mode] = panel
            rot_card.body.addWidget(panel)
            outer.addWidget(rot_card)
        outer.addStretch(1)

    def _mode_tab(self, mode: str, runs_spin, extra_label: str, extra_combo,
                  team_combo, start_btn) -> QWidget:
        page = QWidget()
        page.setObjectName("root")
        v = QVBoxLayout(page)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(Sizing.SPACE_MD)

        # One inline row: label/control pairs left to right, launch button on
        # the far right. Three stacked centred rows read as a floating form.
        fields = QHBoxLayout()
        fields.setSpacing(Sizing.SPACE_LG)
        for text, ctrl in (("Runs", runs_spin),
                           (extra_label, extra_combo),
                           ("Team", team_combo)):
            pair = QHBoxLayout()
            pair.setSpacing(Sizing.SPACE_SM)
            lbl = QLabel(text, page, objectName="settingTitle")
            lbl.setAlignment(Qt.AlignmentFlag.AlignLeft
                             | Qt.AlignmentFlag.AlignVCenter)
            pair.addWidget(lbl)
            pair.addWidget(ctrl)
            fields.addLayout(pair)
        fields.addStretch(1)
        fields.addWidget(start_btn)
        v.addLayout(fields)

        # Live readout of what Start will launch.
        summary = QLabel(page, objectName="luxSummary")
        summary.setWordWrap(True)

        def _refresh():
            n = runs_spin.value()
            summary.setText(
                f"{mode}  ·  {extra_label} {extra_combo.currentText()}  ·  "
                f"Team {team_combo.currentText()}  ·  "
                f"{n} run{'s' if n != 1 else ''}"
            )

        runs_spin.valueChanged.connect(_refresh)
        extra_combo.currentTextChanged.connect(_refresh)
        team_combo.currentTextChanged.connect(_refresh)
        _refresh()
        v.addWidget(summary)

        return page

    def _use_team(self, mode: str, name: str):
        """Rotation button: switch to that mode and select its team."""
        if not name:
            return
        tab = "EXP" if mode == "exp" else "Thread"
        self._mode.set_selected(tab)
        self._on_mode(tab)
        combo = self._exp_team if mode == "exp" else self._thd_team
        if combo.findText(name) >= 0:
            combo.setCurrentText(name)

    def _count_exp_use(self):
        """Tally which damage type the user actually runs, so Sunday's
        three-way choice reflects their habit rather than a guess."""
        name = self._exp_team.currentText()
        if name not in _luxrot.EXP_PRIORITY:
            return
        self._exp_uses[name] = int(self._exp_uses.get(name, 0)) + 1
        self._rotations["exp"].set_uses(self._exp_uses)
        self._save_state()

    def _on_mode(self, label: str):
        if label in self._TABS:
            self._tab_stack.setCurrentIndex(self._TABS.index(label))

    # --- Persistence ----------------------------------------------
    def state(self) -> dict:
        return {
            "exp_type_uses": dict(self._exp_uses),
            "mode": self._mode.selected(),
            "exp_runs": self._exp_runs.value(),
            "exp_stage": self._exp_stage.currentText(),
            "exp_team": self._exp_team.currentText(),
            "thd_runs": self._thd_runs.value(),
            "thd_diff": self._thd_diff.currentText(),
            "thd_team": self._thd_team.currentText(),
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
            uses = s.get("exp_type_uses")
            if isinstance(uses, dict):
                self._exp_uses = {k: int(v) for k, v in uses.items()
                                  if k in _luxrot.EXP_PRIORITY}
                self._rotations["exp"].set_uses(self._exp_uses)
            if "exp_runs" in s:
                self._exp_runs.setValue(int(s["exp_runs"]))
            if s.get("exp_stage"):
                self._exp_stage.setCurrentText(str(s["exp_stage"]))
            if s.get("exp_team"):
                self._exp_team.setCurrentText(str(s["exp_team"]))
            if "thd_runs" in s:
                self._thd_runs.setValue(int(s["thd_runs"]))
            if s.get("thd_diff"):
                self._thd_diff.setCurrentText(str(s["thd_diff"]))
            if s.get("thd_team"):
                self._thd_team.setCurrentText(str(s["thd_team"]))
            if s.get("mode") in self._TABS:
                self._mode.set_selected(s["mode"])
                self._on_mode(s["mode"])
        except (TypeError, ValueError):
            pass
        finally:
            self._loading = False

    # --- Public hooks ---------------------------------------------
    def set_running(self, running: bool):
        self._exp_start.setEnabled(not running)
        self._thd_start.setEnabled(not running)
        self._exp_start.setText("Start EXP")
        self._thd_start.setText("Start Thread")
        self._stop_btn.setEnabled(running)

    def set_arming(self, seconds: int):
        if seconds > 0:
            primary = (self._exp_start
                       if self._mode.selected() == "EXP"
                       else self._thd_start)
            primary.setText(f"Tab into game... {seconds}s")
            self._exp_start.setEnabled(False)
            self._thd_start.setEnabled(False)
            self._stop_btn.setEnabled(True)
        else:
            self._exp_start.setText("Start EXP")
            self._thd_start.setText("Start Thread")
            self._exp_start.setEnabled(True)
            self._thd_start.setEnabled(True)
            self._stop_btn.setEnabled(False)

    def _on_lux_start(self):
        """No-op hook so the start signal still has a slot to connect to."""
        return

    def exp_runs(self) -> int:
        return self._exp_runs.value()

    def exp_stage(self) -> int:
        return int(self._exp_stage.currentText())

    def thread_runs(self) -> int:
        return self._thd_runs.value()

    def thread_difficulty(self) -> int:
        return int(self._thd_diff.currentText())
