# SPDX-License-Identifier: GPL-3.0-or-later
"""Luxcavation page - EXP and Thread grinding, backed by lux.grind_lux."""

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QComboBox, QGridLayout, QHBoxLayout, QLabel, QSpinBox,
    QVBoxLayout, QWidget,
)

from .settings import load_section, save_section
from .theme import Colors, Sizing
from .widgets import (
    AnimatedStack, Card, GhostButton, PageHeader, PrimaryButton, Segmented,
    show_placeholder_notice,
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
    sb.setFixedWidth(120)
    return sb


class LuxcavationPage(QWidget):

    start_exp_requested = Signal()
    start_thread_requested = Signal()
    stop_requested = Signal()

    _TABS = ("EXP", "Thread")

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("root")
        self._loading = False
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

        # Centre vertically so it reads as a panel, not a top-pinned form.
        outer.addStretch(2)

        card = Card(parent=self, padding=Sizing.SPACE_XL)
        card.setMaximumWidth(560)
        card.body.setSpacing(Sizing.SPACE_MD)

        seg_row = QHBoxLayout()
        seg_row.addStretch(1)
        self._mode = Segmented(list(self._TABS), default="EXP", parent=card)
        self._mode.selection_changed.connect(self._on_mode)
        seg_row.addWidget(self._mode)
        seg_row.addStretch(1)
        card.body.addLayout(seg_row)

        self._tab_stack = AnimatedStack(card)
        # Slide snapshots must sit on the card colour, not the darker page
        # gradient, or the switch dims mid-animation then flashes back.
        self._tab_stack.set_surface(f"background-color: {Colors.BG_RAISED};")

        self._exp_runs = _spin(1, card)
        self._exp_stage = _combo(_EXP_STAGES, card)
        self._exp_stage.setCurrentText(_EXP_STAGE_DEFAULT)
        self._exp_team = _combo(list(_LUX_AFFINITIES), card)
        self._exp_start = PrimaryButton("Start EXP", card)
        self._exp_start.clicked.connect(self._on_lux_start)
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

        card_row = QHBoxLayout()
        card_row.addStretch(1)
        card_row.addWidget(card)
        card_row.addStretch(1)
        outer.addLayout(card_row)

        outer.addStretch(3)

    def _mode_tab(self, mode: str, runs_spin, extra_label: str, extra_combo,
                  team_combo, start_btn) -> QWidget:
        page = QWidget()
        page.setObjectName("root")
        v = QVBoxLayout(page)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(Sizing.SPACE_LG)

        grid = QGridLayout()
        grid.setHorizontalSpacing(Sizing.SPACE_MD)
        grid.setVerticalSpacing(Sizing.SPACE_MD)
        for row, (text, ctrl) in enumerate((
            ("Runs", runs_spin),
            (extra_label, extra_combo),
            ("Team", team_combo),
        )):
            lbl = QLabel(text, page, objectName="settingTitle")
            lbl.setAlignment(Qt.AlignmentFlag.AlignRight
                             | Qt.AlignmentFlag.AlignVCenter)
            grid.addWidget(lbl, row, 0)
            grid.addWidget(ctrl, row, 1)

        grid_row = QHBoxLayout()
        grid_row.addStretch(1)
        grid_row.addLayout(grid)
        grid_row.addStretch(1)
        v.addLayout(grid_row)

        # Live readout of what Start will launch.
        summary = QLabel(page, objectName="luxSummary")
        summary.setAlignment(Qt.AlignmentFlag.AlignHCenter)

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

        btn_row = QHBoxLayout()
        btn_row.addStretch(1)
        btn_row.addWidget(start_btn)
        btn_row.addStretch(1)
        v.addLayout(btn_row)

        return page

    def _on_mode(self, label: str):
        if label in self._TABS:
            self._tab_stack.setCurrentIndex(self._TABS.index(label))

    # --- Persistence ----------------------------------------------
    def state(self) -> dict:
        return {
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
