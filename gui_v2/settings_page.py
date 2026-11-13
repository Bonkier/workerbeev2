# SPDX-License-Identifier: GPL-3.0-or-later
"""Settings page - app preferences and configuration management.

Sections: Profiles (save/load/import/export named config sets),
Humanized Input (movement profile + rhythm - maps to the automation
backend's MACRO_PROFILE / MACRO_RHYTHM), Integrations (Discord, audio),
and Application (updates, theme, reset).

The controls here map to real backend params where one exists; nothing
fake is added. Persistence wiring lands with the settings_manager port.
"""

import logging
import os
import sys

from PySide6.QtCore import QSize, QThread, Qt, QTimer, Signal
from PySide6.QtGui import QGuiApplication, QIcon
from PySide6.QtWidgets import (
    QGraphicsOpacityEffect,
    QColorDialog, QComboBox, QHBoxLayout, QLabel, QLineEdit, QPushButton,
    QSlider, QSpinBox, QVBoxLayout, QWidget,
)

from .lghub_help import (
    DiagnoseWorker, FindingsView, copy_report, headline, level_color,
)
from .settings import load_section, save_section
from .theme import Colors, Sizing
from .widgets import (
    Card, ClickOrderGrid, GhostButton, KeyCaptureButton,
    PageHeader, Segmented, SettingRow, Toggle,
)

_SECTION = "app_settings"


# Bindable actions (key, label, default combo). exp/threads runners were
# dropped, so the set is Start MD / luxcavation + run control.
_SHORTCUTS = (
    ("start_md", "Start Mirror Dungeon", "Ctrl+Q"),
    ("start_exp", "Start EXP Luxcavation", "Ctrl+E"),
    ("start_thread", "Start Thread Luxcavation", "Ctrl+R"),
    ("pause", "Pause / Resume", "F9"),
    ("stop", "Stop all", "F2"),
)


# 12 sinners (v1 SINNER_LIST display names) and the team archetypes a
# sinner order can be configured for.
_SINNER_NAMES = (
    "Yi Sang", "Faust", "Don Quixote", "Ryōshū", "Meursault", "Hong Lu",
    "Heathcliff", "Ishmael", "Rodion", "Sinclair", "Outis", "Gregor",
)
_TEAM_TYPES = (
    # Mirror Dungeon status archetypes.
    "Burn", "Bleed", "Tremor", "Rupture", "Sinking",
    "Poise", "Charge",
    # Luxcavation damage types (EXP / Threads runs).
    "Slash", "Pierce", "Blunt",
    # Luxcavation sin affinities (EXP runs targeting a specific sin).
    "Wrath", "Lust", "Sloth", "Gluttony", "Gloom", "Pride", "Envy",
)
# Hollow heals one sinner other than Faust on floors 1 to 3.
_HOLLOW_HEAL_NAMES = tuple(n for n in _SINNER_NAMES if n != "Faust")
_HOLLOW_HEAL_DEFAULT = "Yi Sang"
_HOLLOW_EXCLUDE_DEFAULT = ["Faust"]
# Statuses with a Mirror Dungeon team-select icon (a custom run's keyword).
_STK_STATUSES = (
    "Burn", "Bleed", "Tremor", "Rupture", "Sinking", "Poise", "Charge",
)


# Holds the live Discord bot across page rebuilds.
_discord_bot = None


def discord_bot():
    """The live DiscordBot instance, or None when not configured/running."""
    return _discord_bot


def _project_root() -> str:
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _play_test_sound(volume_0_to_100: int):
    """Play the 'on' alert at the given volume via the shared
    AudioManager. Best-effort - silently no-ops if audio isn't set up."""
    try:
        base = _project_root()
        for p in (base, os.path.join(base, "src")):
            if p not in sys.path:
                sys.path.insert(0, p)
        from audio_manager import AudioManager
        mgr = AudioManager()
        if not getattr(mgr, "initialized", False):
            mgr.initialize(base)
        mgr.play_sound("on", volume_0_to_100 / 100.0, force=True)
    except Exception as exc:
        logging.warning("audio test failed: %s", exc)


def _combo(items, parent=None):
    box = QComboBox(parent)
    box.setObjectName("combo")
    box.addItems(items)
    box.setCursor(Qt.CursorShape.PointingHandCursor)
    return box


def _sinner_combo(names, parent=None):
    """A combo of sinners, each wearing their emblem."""
    from .giftart import sinner_icon
    box = _combo([], parent)
    for name in names:
        box.addItem(QIcon(sinner_icon(name)), name)
    box.setIconSize(QSize(18, 18))
    return box


class SettingsPage(QWidget):

    # Emitted (with {hud, vision, path}) when an overlay toggle changes,
    # so the run coordinator can update the live overlay immediately.
    overlay_changed = Signal(dict)
    # Discord bot test result, marshalled from the test thread to the GUI.
    _bot_test_result = Signal(bool, str)

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("root")
        self._loading = False
        # Supplied by the run coordinator: control callbacks + stats /
        # screenshot providers + log path that the Discord bot needs.
        self._discord_hooks = None
        self._build()
        self._connect_persistence()
        self._restore_state()

    def _build(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(
            Sizing.SPACE_XXL, Sizing.SPACE_XL,
            Sizing.SPACE_XXL, Sizing.SPACE_XL,
        )
        outer.setSpacing(Sizing.SPACE_LG)

        outer.addWidget(PageHeader("Settings", self))

        outer.addWidget(self._build_input_backend())
        outer.addWidget(self._build_display())
        outer.addWidget(self._build_appearance())
        outer.addWidget(self._build_profiles())
        outer.addWidget(self._build_sinners())
        self._init_custom_teams()
        outer.addWidget(self._build_custom_teams())
        outer.addWidget(self._build_humanization())
        outer.addWidget(self._build_advanced())
        outer.addWidget(self._build_overlay())
        outer.addWidget(self._build_shortcuts())
        outer.addWidget(self._build_integrations())
        outer.addWidget(self._build_application())
        outer.addStretch(1)

    # --- Display (monitor) ----------------------------------------
    def _build_display(self) -> QWidget:
        section = Card("DISPLAY", self)
        screens = QGuiApplication.screens()
        names = []
        for i, scr in enumerate(screens):
            geo = scr.geometry()
            names.append(f"Monitor {i + 1}  ·  {geo.width()}x{geo.height()}")
        if not names:
            names = ["Primary monitor"]
        self._monitor = _combo(names, section)
        section.body.addWidget(SettingRow(
            "Game monitor", self._monitor, parent=section,
        ))
        return section

    # --- Appearance (colour theme) --------------------------------
    def _build_appearance(self) -> QWidget:
        from . import themes
        section = Card("APPEARANCE", self)

        from . import skins
        self._legacy_ui = Toggle(default=(skins.current_skin() == skins.LEGACY),
                                 parent=section)
        self._legacy_ui.toggled.connect(self._on_legacy_ui)
        section.body.addWidget(SettingRow(
            "Legacy v2 UI", self._legacy_ui, parent=section,
        ))

        cur = themes.current_theme()
        names = list(themes.PRESETS.keys()) + ["Custom"]
        self._theme_combo = _combo(names, section)
        start = cur["preset"] if cur["preset"] in names else "WorkerBee Yellow"
        self._theme_combo.setCurrentText(start)
        # Connect AFTER setting the initial value so it doesn't re-fire.
        self._theme_combo.currentTextChanged.connect(self._on_theme_preset)
        section.body.addWidget(SettingRow(
            "Theme", self._theme_combo, parent=section,
        ))

        self._accent_swatch = self._make_swatch(cur["accent"], self._pick_accent)
        section.body.addWidget(SettingRow(
            "Accent colour", self._accent_swatch, parent=section,
        ))

        self._bg_swatch = self._make_swatch(cur["bg"], self._pick_background)
        section.body.addWidget(SettingRow(
            "Background", self._bg_swatch, parent=section,
        ))

        self._text_swatch = self._make_swatch(cur["text"], self._pick_text)
        section.body.addWidget(SettingRow(
            "Text colour", self._text_swatch, parent=section,
        ))

        reset = GhostButton("Reset theme", section)
        reset.clicked.connect(self._reset_theme)
        section.body.addWidget(SettingRow(
            "Reset theme", reset, parent=section,
        ))
        return section

    def _make_swatch(self, hex_color: str, on_click) -> QPushButton:
        btn = QPushButton(self)
        btn.setObjectName("colorSwatch")
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.setFixedSize(96, 30)
        btn.clicked.connect(on_click)
        self._style_swatch(btn, hex_color)
        return btn

    def _style_swatch(self, btn: QPushButton, hex_color: str):
        # Readable label colour over the swatch (dark text on light, etc.).
        h = hex_color.lstrip("#")
        try:
            r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
        except (ValueError, IndexError):
            r, g, b = 240, 240, 240
        fg = "#0d0d0e" if (0.299 * r + 0.587 * g + 0.114 * b) > 150 else "#f5f5f6"
        btn.setText(hex_color.upper())
        btn.setStyleSheet(
            f"QPushButton#colorSwatch {{ background-color:{hex_color}; "
            f"color:{fg}; border:1px solid rgba(255,255,255,0.25); "
            f"border-radius:{Sizing.RADIUS_SM}px; font-size:10pt; "
            f"font-weight:600; }}")

    def _on_legacy_ui(self, on: bool):
        if self._loading:
            return
        from . import skins
        skins.set_skin(skins.LEGACY if on else skins.VOXEL)

    def _on_theme_preset(self, name: str):
        if self._loading or name == "Custom":
            return
        from . import themes
        themes.set_preset(name)
        self._sync_theme_controls()

    def _pick_accent(self):
        from PySide6.QtGui import QColor
        from . import themes
        col = QColorDialog.getColor(
            QColor(themes.current_theme()["accent"]), self, "Accent colour")
        if col.isValid():
            themes.set_custom_accent(col.name())
            self._sync_theme_controls()

    def _pick_background(self):
        from PySide6.QtGui import QColor
        from . import themes
        col = QColorDialog.getColor(
            QColor(themes.current_theme()["bg"]), self, "Background colour")
        if col.isValid():
            themes.set_custom_background(col.name())
            self._sync_theme_controls()

    def _pick_text(self):
        from PySide6.QtGui import QColor
        from . import themes
        col = QColorDialog.getColor(
            QColor(themes.current_theme()["text"]), self, "Text colour")
        if col.isValid():
            themes.set_custom_text(col.name())
            self._sync_theme_controls()

    def _reset_theme(self):
        from . import themes
        themes.reset_theme()
        self._sync_theme_controls()

    def _sync_theme_controls(self):
        from . import themes
        cur = themes.current_theme()
        names = list(themes.PRESETS.keys()) + ["Custom"]
        self._loading = True
        try:
            self._theme_combo.setCurrentText(
                cur["preset"] if cur["preset"] in names else "Custom")
        finally:
            self._loading = False
        self._style_swatch(self._accent_swatch, cur["accent"])
        self._style_swatch(self._bg_swatch, cur["bg"])
        if hasattr(self, "_text_swatch"):
            self._style_swatch(self._text_swatch, cur["text"])

    # --- Advanced automation toggles ------------------------------
    def _build_advanced(self) -> QWidget:
        section = Card("ADVANCED", self)
        self._advanced = {}
        rows = [
            ("skip_ego_battle", "Skip EGO in battle"),
            ("good_pc", "Good PC mode"),
            ("debug_matches", "Debug image matches"),
            ("grayscale", "Grayscale speed-boost"),
            ("reconnect_online", "Reconnect only when online"),
            ("animations", "Enable UI animations"),
        ]
        for key, title in rows:
            default = key in ("reconnect_online", "animations")
            tog = Toggle(default=default, parent=section)
            self._advanced[key] = tog
            section.body.addWidget(SettingRow(title, tog, parent=section))
        return section

    # --- Run overlay + debug visualizers --------------------------
    def _build_overlay(self) -> QWidget:
        section = Card("RUN OVERLAY", self)
        self._overlay_toggles = {}
        rows = [
            ("hud", "Show run overlay"),
            ("vision", "Debug: show what the macro sees"),
            ("path", "Debug: show mouse target + path"),
        ]
        for key, title in rows:
            tog = Toggle(default=(key == "hud"), parent=section)
            self._overlay_toggles[key] = tog
            section.body.addWidget(SettingRow(title, tog, parent=section))

        op_cluster = QWidget(section)
        opc = QHBoxLayout(op_cluster)
        opc.setContentsMargins(0, 0, 0, 0)
        opc.setSpacing(Sizing.SPACE_MD)
        self._overlay_opacity = QSlider(Qt.Orientation.Horizontal, op_cluster)
        self._overlay_opacity.setObjectName("slider")
        self._overlay_opacity.setRange(20, 100)
        self._overlay_opacity.setValue(85)
        self._overlay_opacity.setFixedWidth(200)
        opc.addWidget(self._overlay_opacity)
        self._overlay_opacity_lbl = QLabel("85%", op_cluster,
                                           objectName="inlineMeta")
        self._overlay_opacity_lbl.setFixedWidth(48)
        opc.addWidget(self._overlay_opacity_lbl)
        self._overlay_opacity.valueChanged.connect(
            lambda v: self._overlay_opacity_lbl.setText(f"{v}%"))
        self._overlay_opacity.valueChanged.connect(self._save_state)
        section.body.addWidget(SettingRow(
            "Overlay background", op_cluster, parent=section,
        ))
        return section

    def overlay_settings(self) -> dict:
        """Current {hud, vision, path} overlay toggle states."""
        return {k: t.isChecked() for k, t in self._overlay_toggles.items()}

    def _emit_overlay_changed(self, *_):
        if self._loading:
            return
        self.overlay_changed.emit(self.overlay_settings())

    # --- Input backend (LGHub) ------------------------------------
    def _build_input_backend(self) -> QWidget:
        self._probe_thread = None
        self._probe = None
        section = Card("INPUT BACKEND", self)

        row = QHBoxLayout()
        row.setSpacing(Sizing.SPACE_MD)
        self._lghub_status = QLabel("Not checked yet", self,
                                    objectName="settingTitle")
        self._lghub_status.setWordWrap(True)
        row.addWidget(self._lghub_status, stretch=1)
        self._lghub_copy = GhostButton("Copy report", self)
        self._lghub_copy.setVisible(False)
        self._lghub_copy.clicked.connect(self._copy_lghub_report)
        row.addWidget(self._lghub_copy)
        refresh = GhostButton("Check connection", self)
        refresh.clicked.connect(self._check_lghub)
        row.addWidget(refresh)
        section.body.addLayout(row)

        # What is wrong and the steps that fix it, filled in by a check.
        self._lghub_report = {}
        self._lghub_findings = FindingsView(self)
        section.body.addWidget(self._lghub_findings)
        return section

    def _check_lghub(self):
        if self._probe_thread is not None:
            return
        self._lghub_status.setText("Checking LGHub connection…")
        self._lghub_status.setStyleSheet(f"color: {Colors.TEXT_SECONDARY};")
        self._probe_thread = QThread(self)
        self._probe = DiagnoseWorker()
        self._probe.moveToThread(self._probe_thread)
        self._probe.done.connect(self._on_lghub_done)
        self._probe_thread.started.connect(self._probe.run)
        self._probe_thread.start()

    def _on_lghub_done(self, report: dict):
        from bridge import lghub_check
        self._lghub_report = report
        found = lghub_check.findings(report) if report else []
        top = headline(found)
        if top is None:
            self._lghub_status.setText(
                "Not reachable - start LGHub, then check again")
            self._lghub_status.setStyleSheet(f"color: {Colors.WARNING};")
        else:
            # The findings below carry their own titles; the status line only
            # names the state, so the headline is not printed twice.
            state = {"fail": "Not connected - see below",
                     "warn": "Connected, with a warning - see below"}
            self._lghub_status.setText(state.get(top["level"], top["title"]))
            self._lghub_status.setStyleSheet(
                f"color: {level_color(top['level'])};")
        self._lghub_findings.set_findings(
            [f for f in found if f["level"] != "ok"],
            lghub_check.checks(report) if report else [])
        self._lghub_copy.setVisible(bool(report))
        if any(f["level"] == "fail" for f in found):
            # In the log too, so a log sent in for help already says why.
            for line in lghub_check.format_report(report).splitlines():
                logging.warning("LGHub: %s", line)
        if self._probe_thread is not None:
            self._probe_thread.quit()
            self._probe_thread.wait()
            self._probe_thread.deleteLater()
        self._probe = None
        self._probe_thread = None

    def _copy_lghub_report(self):
        if not self._lghub_report:
            return
        copy_report(self._lghub_report)
        self._lghub_copy.setText("Copied")
        QTimer.singleShot(
            1500, self, lambda: self._lghub_copy.setText("Copy report"))

    # --- Keyboard shortcuts ---------------------------------------
    def _build_shortcuts(self) -> QWidget:
        section = Card("KEYBOARD SHORTCUTS", self)
        self._shortcuts = {}
        for key, label, default in _SHORTCUTS:
            btn = KeyCaptureButton(default, parent=section)
            self._shortcuts[key] = btn
            section.body.addWidget(SettingRow(label, btn, parent=section))
        return section

    # --- Per-team sinner assignment -------------------------------
    def _build_sinners(self) -> QWidget:
        section = Card("SINNERS", self)

        # Independent {order, exclude} state per team type. Default: a
        # full default order (every sinner picked) and the first 7 as the
        # max-energy-swap exclusion list.
        default_order = list(_SINNER_NAMES)
        default_exclude = list(_SINNER_NAMES[:7])
        self._sinner_states = {
            team: {"order": list(default_order),
                   "exclude": list(default_exclude)}
            for team in _TEAM_TYPES
        }
        self._sinner_team = _TEAM_TYPES[0]

        picker = QHBoxLayout()
        picker.setSpacing(Sizing.SPACE_SM)
        picker.addWidget(QLabel("Team", self, objectName="settingTitle"))
        self._sinner_combo = _combo(list(_TEAM_TYPES), section)
        self._sinner_combo.currentTextChanged.connect(self._on_sinner_team)
        picker.addWidget(self._sinner_combo)
        self._sinner_count = QLabel("", self, objectName="inlineMeta")
        picker.addWidget(self._sinner_count)
        picker.addStretch(1)
        section.body.addLayout(picker)

        # 12 sinners as a 2x6 grid, like the in-game roster screen.
        section.body.addWidget(QLabel("Pick order", self,
                                      objectName="subSectionLabel"))
        self._sinner_order = ClickOrderGrid(
            list(_SINNER_NAMES), rows=2, cols=6, parent=section,
        )
        self._sinner_order.changed.connect(self._on_sinner_changed)
        section.body.addWidget(self._sinner_order)

        section.body.addSpacing(Sizing.SPACE_MD)
        section.body.addWidget(QLabel("Swap exclusion", self,
                                      objectName="subSectionLabel"))
        self._sinner_exclude = ClickOrderGrid(
            list(_SINNER_NAMES), rows=2, cols=6, parent=section,
        )
        self._sinner_exclude.changed.connect(self._on_sinner_changed)
        section.body.addWidget(self._sinner_exclude)

        state = self._sinner_states[self._sinner_team]
        self._sinner_order.set_order(state["order"])
        self._sinner_exclude.set_order(state["exclude"])
        self._update_sinner_count()
        return section

    def _on_sinner_team(self, team: str):
        # Save the current team's state, then load the newly selected.
        self._sinner_states[self._sinner_team] = {
            "order": self._sinner_order.order(),
            "exclude": self._sinner_exclude.order(),
        }
        self._sinner_team = team
        state = self._sinner_states[team]
        self._sinner_order.set_order(state["order"])
        self._sinner_exclude.set_order(state["exclude"])
        self._update_sinner_count()
        self._save_state()

    def _on_sinner_changed(self):
        self._sinner_states[self._sinner_team] = {
            "order": self._sinner_order.order(),
            "exclude": self._sinner_exclude.order(),
        }
        self._update_sinner_count()
        self._save_state()

    def sinner_selection(self) -> dict:
        """{team_type: [picked sinner display names, in click order]}.
        Consumed by run_config to build each team's sinner list."""
        self._sinner_states[self._sinner_team] = {
            "order": self._sinner_order.order(),
            "exclude": self._sinner_exclude.order(),
        }
        return {team: list(state["order"])
                for team, state in self._sinner_states.items()}

    def sinner_exclusion(self) -> dict:
        """{team_type: [sinner display names to exclude from max-energy
        swaps, in click order]}."""
        self._sinner_states[self._sinner_team] = {
            "order": self._sinner_order.order(),
            "exclude": self._sinner_exclude.order(),
        }
        return {team: list(state["exclude"])
                for team, state in self._sinner_states.items()}

    # --- Custom run teams: one card, a run at a time -----------------
    def _init_custom_teams(self):
        self._team_loading = False
        self._team_run = "SAIKAI"
        self._team_states = {
            "SAIKAI": {"order": [], "exclude": [], "keyword": "Poise",
                       "s3_only": False, "configured": False},
            "Hollow": {"order": [], "exclude": list(_HOLLOW_EXCLUDE_DEFAULT),
                       "keyword": "Poise", "heal": _HOLLOW_HEAL_DEFAULT,
                       "exclude_set": False, "configured": False},
        }
        self._team_card = None
        self._team_widgets = {}

    def _build_custom_teams(self) -> QWidget:
        """One card for both scripted runs; the shell's "Go to custom run
        settings" button scrolls it into view with the run selected."""
        section = Card("CUSTOM RUN TEAMS", self)
        self._team_card = section
        w = self._team_widgets
        self._team_loading = True

        row = QHBoxLayout()
        row.setSpacing(Sizing.SPACE_SM)
        row.addWidget(QLabel("Run", self, objectName="settingTitle"))
        w["run"] = Segmented(["SAIKAI", "Hollow"], default="SAIKAI",
                             parent=section)
        w["run"].selection_changed.connect(self._on_team_run)
        row.addWidget(w["run"])
        row.addStretch(1)
        section.body.addLayout(row)

        w["keyword"] = _combo(list(_STK_STATUSES), section)
        w["keyword"].currentTextChanged.connect(self._on_team_changed)
        section.body.addWidget(SettingRow(
            "Team keyword", w["keyword"], parent=section))

        w["s3_only"] = Toggle(default=False, parent=section)
        w["s3_only"].toggled.connect(self._on_team_changed)
        w["s3_only_row"] = SettingRow(
            "Choose Skill 3 only", w["s3_only"], parent=section)
        section.body.addWidget(w["s3_only_row"])

        w["heal"] = _sinner_combo(list(_HOLLOW_HEAL_NAMES), section)
        w["heal"].currentTextChanged.connect(self._on_team_changed)
        w["heal_row"] = SettingRow(
            "Sinner to heal", w["heal"], parent=section)
        section.body.addWidget(w["heal_row"])

        w["order_label"] = QLabel("Sinner order", self,
                                  objectName="subSectionLabel")
        section.body.addWidget(w["order_label"])
        w["order"] = ClickOrderGrid(list(_SINNER_NAMES), rows=2, cols=6,
                                    max_picks=12, parent=section)
        w["order"].changed.connect(self._on_team_changed)
        section.body.addWidget(w["order"])

        section.body.addWidget(QLabel("Swap exclusion", self,
                                      objectName="subSectionLabel"))
        w["exclude"] = ClickOrderGrid(list(_SINNER_NAMES), rows=2, cols=6,
                                      max_picks=12, parent=section)
        w["exclude"].changed.connect(self._on_team_changed)
        section.body.addWidget(w["exclude"])

        self._team_apply("SAIKAI")
        self._team_loading = False
        return section

    def show_team(self, run):
        """Put a run's team on the card (the shell's reveal does this)."""
        if run in self._team_states and self._team_widgets:
            self._team_widgets["run"].set_selected(run)
            self._on_team_run(run)

    def _on_team_run(self, run):
        if run not in self._team_states or run == self._team_run:
            return
        self._team_sync()
        self._team_run = run
        self._team_apply(run)

    def _team_sync(self):
        st, w = self._team_states[self._team_run], self._team_widgets
        st["order"] = w["order"].order()
        st["exclude"] = w["exclude"].order()
        st["keyword"] = w["keyword"].currentText()
        if self._team_run == "Hollow":
            st["heal"] = w["heal"].currentText()
            st["exclude_set"] = True
        else:
            st["s3_only"] = w["s3_only"].isChecked()

    def _team_apply(self, run):
        prev = self._team_loading
        self._team_loading = True
        try:
            st, w = self._team_states[run], self._team_widgets
            hollow = run == "Hollow"
            if hollow:
                # Faust is the run; she cannot also be her own fallback.
                st["order"] = [n for n in st["order"] if n != "Faust"]
            faust = w["order"]._chips.get("Faust")
            if faust is not None:
                faust.setEnabled(not hollow)
                faust.setToolTip("Faust is the run; she cannot be her own "
                                 "fallback." if hollow else "")
                if hollow:
                    dim = QGraphicsOpacityEffect(faust)
                    dim.setOpacity(0.35)
                    faust.setGraphicsEffect(dim)
                else:
                    faust.setGraphicsEffect(None)
            w["order"].set_order(st["order"])
            w["exclude"].set_order(st["exclude"])
            if st["keyword"] in _STK_STATUSES:
                w["keyword"].setCurrentText(st["keyword"])
            w["s3_only_row"].setVisible(not hollow)
            w["heal_row"].setVisible(hollow)
            w["order_label"].setText("Fallback sinners" if hollow
                                     else "Sinner order")
            if hollow:
                if st.get("heal") in _HOLLOW_HEAL_NAMES:
                    w["heal"].setCurrentText(st["heal"])
            else:
                w["s3_only"].setChecked(bool(st.get("s3_only")))
        finally:
            self._team_loading = prev

    def _on_team_changed(self, *_):
        if getattr(self, "_team_loading", False):
            return
        self._team_sync()
        self._team_states[self._team_run]["configured"] = True
        self._save_state()

    def custom_team_configured(self, run) -> bool:
        """Whether the run's card was ever set up: something changed on it,
        an order saved (a preset's too), or the user chose to go on without."""
        return bool(self._team_states.get(run, {}).get("configured"))

    def acknowledge_custom_team(self, run):
        """The user chose to run with the card untouched: not asked again."""
        if run in self._team_states:
            self._team_states[run]["configured"] = True
            self._save_state()

    def custom_teams_config(self) -> dict:
        """Flat md_state keys for run_config; merged in by the coordinator.
        An order left empty is the default one, the owner's."""
        if self._team_widgets:
            self._team_sync()
        s, h = self._team_effective("SAIKAI"), self._team_effective("Hollow")
        return {
            "saikai_order": list(s["order"]),
            "saikai_exclude": list(s["exclude"]),
            "saikai_status": s["keyword"],
            "saikai_s3_only": bool(s.get("s3_only")),
            "hollow_order": [n for n in h["order"] if n != "Faust"],
            "hollow_exclude": list(h["exclude"]),
            "hollow_status": h["keyword"],
            "hollow_heal": h.get("heal") or _HOLLOW_HEAL_DEFAULT,
        }

    def _team_effective(self, run) -> dict:
        from .presets import default_team
        st = dict(self._team_states[run])
        if not st.get("order"):
            st["order"] = list(default_team(run).get("order") or [])
        return st

    def _restore_teams(self, teams):
        if not isinstance(teams, dict):
            teams = self._migrate_teams_from_mirror()
        for run, st in (teams or {}).items():
            if run not in self._team_states or not isinstance(st, dict):
                continue
            cur = self._team_states[run]
            kw = st.get("keyword")
            order = [n for n in (st.get("order") or []) if n in _SINNER_NAMES]
            cur.update({
                "order": order,
                "exclude": [n for n in (st.get("exclude") or [])
                            if n in _SINNER_NAMES],
                "keyword": kw if kw in _STK_STATUSES else cur["keyword"],
                "configured": (bool(st["configured"]) if "configured" in st
                               else bool(order)),
            })
            if run == "SAIKAI":
                cur["s3_only"] = bool(st.get("s3_only"))
            else:
                heal = st.get("heal")
                cur["heal"] = (heal if heal in _HOLLOW_HEAL_NAMES
                               else _HOLLOW_HEAL_DEFAULT)
                cur["order"] = [n for n in order if n != "Faust"]
                if st.get("exclude_set"):
                    cur["exclude_set"] = True
                else:
                    # Saved while the grid was hidden for Hollow (before
                    # v2.5.2e): that empty list was never a choice.
                    cur["exclude"] = list(_HOLLOW_EXCLUDE_DEFAULT)
        if getattr(self, "_team_widgets", None):
            self._team_apply(self._team_run)

    def _migrate_teams_from_mirror(self) -> dict:
        """One-time: read the SAIKAI config from the MD page's old 'mirror'
        section so existing setups carry over after the move to Settings."""
        try:
            m = load_section("mirror") or {}
        except Exception:
            return {}
        if not m:
            return {}
        return {"SAIKAI": {
            "order": m.get("saikai_order") or [],
            "exclude": m.get("saikai_exclude") or [],
            "keyword": m.get("saikai_status") or "Poise",
        }}

    # --- Persistence ---------------------------------------------
    def _connect_persistence(self):
        self._monitor.currentIndexChanged.connect(self._save_state)
        self._macro_profile.selection_changed.connect(self._save_state)
        self._rhythm.toggled.connect(self._save_state)
        self._audio_alerts.toggled.connect(self._save_state)
        self._volume.valueChanged.connect(self._save_state)
        for tog in self._advanced.values():
            tog.toggled.connect(self._save_state)
        for tog in self._overlay_toggles.values():
            tog.toggled.connect(self._save_state)
            tog.toggled.connect(self._emit_overlay_changed)
        for btn in self._shortcuts.values():
            btn.binding_changed.connect(self._save_state)

    def _save_state(self, *_):
        if self._loading:
            return
        # Sync the live sinner grids into the per-team store first.
        self._sinner_states[self._sinner_team] = {
            "order": self._sinner_order.order(),
            "exclude": self._sinner_exclude.order(),
        }
        sinners = {team: {"order": list(state["order"]),
                          "exclude": list(state["exclude"])}
                   for team, state in self._sinner_states.items()}
        save_section(_SECTION, {
            "monitor": self._monitor.currentIndex(),
            "macro_profile": self._macro_profile.selected(),
            "rhythm": self._rhythm.isChecked(),
            "mouse_speed": self._mouse_speed.value(),
            "dxgi_capture": self._dxgi_capture.isChecked(),
            "audio_alerts": self._audio_alerts.isChecked(),
            "volume": self._volume.value(),
            "advanced": {k: t.isChecked() for k, t in self._advanced.items()},
            "overlay": {k: t.isChecked()
                        for k, t in self._overlay_toggles.items()},
            "overlay_opacity": self._overlay_opacity.value(),
            "shortcuts": {k: b.binding() for k, b in self._shortcuts.items()},
            "sinners": sinners,
            "custom_teams": {k: dict(v) for k, v in self._team_states.items()},
        })

    def _restore_state(self):
        s = load_section(_SECTION)
        if s:
            self._loading = True
            try:
                mon = s.get("monitor")
                if isinstance(mon, int) and 0 <= mon < self._monitor.count():
                    self._monitor.setCurrentIndex(mon)
                if s.get("macro_profile") in ("Safe", "Fast", "Chaotic"):
                    self._macro_profile.set_selected(s["macro_profile"])
                if "rhythm" in s:
                    self._rhythm.setChecked(bool(s["rhythm"]))
                if isinstance(s.get("mouse_speed"), int):
                    self._mouse_speed.setValue(s["mouse_speed"])
                if "dxgi_capture" in s:
                    self._dxgi_capture.setChecked(bool(s["dxgi_capture"]))
                if "audio_alerts" in s:
                    self._audio_alerts.setChecked(bool(s["audio_alerts"]))
                if isinstance(s.get("volume"), int):
                    self._volume.setValue(s["volume"])
                for k, v in (s.get("advanced") or {}).items():
                    if k in self._advanced:
                        self._advanced[k].setChecked(bool(v))
                for k, v in (s.get("overlay") or {}).items():
                    if k in self._overlay_toggles:
                        self._overlay_toggles[k].setChecked(bool(v))
                if isinstance(s.get("overlay_opacity"), int):
                    self._overlay_opacity.setValue(s["overlay_opacity"])
                for k, v in (s.get("shortcuts") or {}).items():
                    if k in self._shortcuts and isinstance(v, str):
                        self._shortcuts[k].set_binding(v)
                saved_sinners = s.get("sinners") or {}
                for team, entry in saved_sinners.items():
                    if team not in self._sinner_states:
                        continue
                    # New dict format: {"order": [...], "exclude": [...]}.
                    if isinstance(entry, dict):
                        order = entry.get("order") or []
                        exclude = entry.get("exclude") or []
                        self._sinner_states[team] = {
                            "order": [n for n in order if n in _SINNER_NAMES],
                            "exclude": [n for n in exclude
                                        if n in _SINNER_NAMES],
                        }
                    # Legacy [order, included] tuple/list format: map
                    # `included` to the new `order` (preserving the saved
                    # display order) and default `exclude` to the first
                    # 7 names of the old display order.
                    elif isinstance(entry, list) and len(entry) == 2:
                        legacy_order, included = entry
                        try:
                            inc_set = set(included)
                        except TypeError:
                            inc_set = set()
                        new_order = [n for n in legacy_order if n in inc_set
                                     and n in _SINNER_NAMES]
                        new_exclude = [n for n in list(legacy_order)[:7]
                                       if n in _SINNER_NAMES]
                        self._sinner_states[team] = {
                            "order": new_order,
                            "exclude": new_exclude,
                        }
                cur = self._sinner_states.get(self._sinner_team)
                if cur:
                    self._sinner_order.set_order(cur["order"])
                    self._sinner_exclude.set_order(cur["exclude"])
                    self._update_sinner_count()
            except (TypeError, ValueError):
                pass
            finally:
                self._loading = False
        # SAIKAI/Hollow: restored unconditionally so the one-time migration
        # from the old "mirror" section runs even when app_settings is empty
        # (SAIKAI set in the MD page, but no app settings saved yet). Saves
        # before v2.6.0 kept the teams under "saikai_thrill".
        s = s or {}
        self._restore_teams(s.get("custom_teams", s.get("saikai_thrill")))
        # Always re-sync the appearance + config controls (covers a config
        # load that swapped the whole settings file under us).
        if hasattr(self, "_sync_theme_controls"):
            self._sync_theme_controls()
        if hasattr(self, "_refresh_config_combo"):
            self._refresh_config_combo()

    def _update_sinner_count(self):
        n = len(self._sinner_order.order())
        self._sinner_count.setText(f"{n} selected")

    # --- Configs (save/load/import/export) ------------------------
    # Emitted after a config is loaded/imported so the shell can re-read
    # every page's state from the now-updated settings file.
    config_loaded = Signal()

    def _build_profiles(self) -> QWidget:
        from .copy import SETTINGS_CONFIG_COMBO_PLACEHOLDER
        section = Card("CONFIGS", self)

        row = QHBoxLayout()
        row.setSpacing(Sizing.SPACE_SM)
        # Editable combo so the user can EITHER pick an existing config
        # to overwrite OR type a fresh name to save a new one. Replaces
        # the old "Save as" button (which opened a QInputDialog that was
        # being eaten by the frameless main window and never appeared).
        self._config_combo = _combo([], section)
        self._config_combo.setEditable(True)
        self._config_combo.setMinimumWidth(160)
        self._config_combo.setInsertPolicy(
            QComboBox.InsertPolicy.NoInsert)   # editing doesn't auto-add
        self._config_combo.lineEdit().setPlaceholderText(
            SETTINGS_CONFIG_COMBO_PLACEHOLDER)
        row.addWidget(self._config_combo)
        for label, slot in (
            ("Load", self._config_load),
            ("Save", self._config_save),
            ("Import", self._config_import),
            ("Export", self._config_export),
            ("Delete", self._config_delete),
        ):
            btn = GhostButton(label, section)
            btn.clicked.connect(slot)
            row.addWidget(btn)
        row.addStretch(1)
        section.body.addLayout(row)

        self._config_status = QLabel("", section, objectName="inlineMeta")
        section.body.addWidget(self._config_status)
        self._refresh_config_combo()
        return section

    def _refresh_config_combo(self, select: str | None = None):
        from .settings import list_configs
        names = list_configs()
        keep = select or self._config_combo.currentText()
        self._loading = True
        try:
            self._config_combo.clear()
            self._config_combo.addItems(names or [])
            if keep and keep in names:
                self._config_combo.setCurrentText(keep)
        finally:
            self._loading = False

    def _config_status_msg(self, msg: str):
        self._config_status.setText(msg)

    def _config_save(self):
        """Save current settings under whatever name is in the combo's
        line edit. If the name matches an existing config, it's
        overwritten; otherwise a new config is created. Empty input
        bails with a status message instead of silently no-op'ing."""
        from .settings import save_config, list_configs
        name = self._config_combo.currentText().strip()
        if not name:
            self._config_status_msg(
                "Type a config name in the box first, then click Save.")
            return
        existed = name in list_configs()
        save_config(name)
        self._refresh_config_combo(select=name)
        self._config_status_msg(
            f"{'Overwrote' if existed else 'Saved as new'} "
            f"config '{name}'.")

    def _config_load(self):
        from .settings import load_config
        name = self._config_combo.currentText().strip()
        if not name:
            self._config_status_msg("No config selected.")
            return
        if load_config(name):
            self.config_loaded.emit()  # shell re-reads every page
            self._config_status_msg(f"Loaded '{name}'.")
        else:
            self._config_status_msg(f"Config '{name}' not found.")

    def _config_delete(self):
        from .settings import delete_config
        name = self._config_combo.currentText().strip()
        if not name:
            return
        delete_config(name)
        self._refresh_config_combo()
        self._config_status_msg(f"Deleted '{name}'.")

    def _config_export(self):
        from PySide6.QtWidgets import QFileDialog
        from .settings import export_config_to
        name = self._config_combo.currentText().strip() or "config"
        path, _ = QFileDialog.getSaveFileName(
            self, "Export config", f"{name}.json", "Config files (*.json)")
        if not path:
            return
        if export_config_to(name, path):
            self._config_status_msg(f"Exported '{name}'.")
        else:
            self._config_status_msg("Export failed.")

    def _config_import(self):
        from PySide6.QtWidgets import QFileDialog
        from .settings import import_config_from
        path, _ = QFileDialog.getOpenFileName(
            self, "Import config", "", "Config files (*.json)")
        if not path:
            return
        name = import_config_from(path)
        if name:
            self._refresh_config_combo(select=name)
            self._config_status_msg(f"Imported '{name}'. Click Load to apply.")
        else:
            self._config_status_msg("Import failed (not a valid config file).")

    # --- Humanized input ------------------------------------------
    def _build_humanization(self) -> QWidget:
        section = Card("HUMANIZED INPUT", self)

        self._macro_profile = Segmented(
            ["Safe", "Fast", "Chaotic"], default="Safe", parent=section,
        )
        section.body.addWidget(SettingRow(
            "Movement profile", self._macro_profile, parent=section,
        ))
        self._rhythm = Toggle(default=True, parent=section)
        section.body.addWidget(SettingRow(
            "Rhythm pauses", self._rhythm, parent=section,
        ))

        # Mouse speed: scales how fast the cursor moves (100% = default). A
        # confirm dialog fires past 200% since very fast movement is less
        # human-like (and easier to flag as automated).
        ms_cluster = QWidget(section)
        msc = QHBoxLayout(ms_cluster)
        msc.setContentsMargins(0, 0, 0, 0)
        msc.setSpacing(Sizing.SPACE_MD)
        self._mouse_speed = QSlider(Qt.Orientation.Horizontal, ms_cluster)
        self._mouse_speed.setObjectName("slider")
        self._mouse_speed.setRange(0, 500)
        self._mouse_speed.setValue(100)
        self._mouse_speed.setFixedWidth(200)
        msc.addWidget(self._mouse_speed)
        self._mouse_speed_lbl = QLabel("100%", ms_cluster, objectName="inlineMeta")
        self._mouse_speed_lbl.setFixedWidth(48)
        msc.addWidget(self._mouse_speed_lbl)
        self._mouse_speed.valueChanged.connect(self._on_mouse_speed_changed)
        self._mouse_speed.sliderReleased.connect(self._on_mouse_speed_released)
        section.body.addWidget(SettingRow(
            "Mouse speed", ms_cluster, parent=section,
        ))
        self._dxgi_capture = Toggle(default=True, parent=section)
        self._dxgi_capture.toggled.connect(self._save_state)
        section.body.addWidget(SettingRow(
            "Capture through DXGI", self._dxgi_capture, parent=section,
        ))
        return section

    def _on_mouse_speed_changed(self, val: int):
        self._mouse_speed_lbl.setText(f"{val}%")
        self._save_state()

    def _on_mouse_speed_released(self):
        # Warn once the user lets go above 200%; revert to 200 if they decline.
        if self._mouse_speed.value() > 200:
            from PySide6.QtWidgets import QMessageBox
            resp = QMessageBox.question(
                self, "High mouse speed",
                "Are you sure you want to increase the mouse speed that high?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if resp != QMessageBox.StandardButton.Yes:
                self._mouse_speed.setValue(200)

    # --- Integrations ---------------------------------------------
    def _build_integrations(self) -> QWidget:
        section = Card("INTEGRATIONS", self)
        cfg = self._load_discord()

        # Discord bot: the single Discord integration. It posts run summaries
        # and screenshots to a channel AND adds buttons to start/stop runs
        # from Discord, so a separate webhook would be redundant.
        self._discord_enable = Toggle(default=bool(cfg.get("enabled")),
                                      parent=section)
        section.body.addWidget(SettingRow(
            "Discord bot", self._discord_enable, parent=section,
        ))

        self._discord_token = QLineEdit(cfg.get("token", ""), section)
        self._discord_token.setObjectName("textField")
        self._discord_token.setEchoMode(QLineEdit.EchoMode.Password)
        self._discord_token.setPlaceholderText("Bot token")
        section.body.addWidget(self._field_row("Bot token", self._discord_token))

        self._discord_channel = QLineEdit(str(cfg.get("channel_id", "")), section)
        self._discord_channel.setObjectName("textField")
        self._discord_channel.setPlaceholderText("Channel ID")
        section.body.addWidget(self._field_row("Channel ID", self._discord_channel))

        self._discord_interval = QSpinBox(section)
        self._discord_interval.setObjectName("runCount")
        self._discord_interval.setRange(1, 180)
        self._discord_interval.setValue(int(cfg.get("interval", 15)))
        self._discord_interval.setFixedWidth(90)
        section.body.addWidget(self._field_row("Interval (min)",
                                               self._discord_interval))

        save_row = QHBoxLayout()
        save_row.setSpacing(Sizing.SPACE_MD)
        self._discord_status = QLabel("", section, objectName="inlineMeta")
        save_row.addWidget(self._discord_status)
        save_row.addStretch(1)
        test_btn = GhostButton("Test", section)
        test_btn.clicked.connect(self._test_bot)
        save_row.addWidget(test_btn)
        save_btn = GhostButton("Save and apply", section)
        save_btn.clicked.connect(self._save_discord)
        save_row.addWidget(save_btn)
        section.body.addLayout(save_row)
        self._bot_test_result.connect(self._on_bot_test_result)
        self._refresh_discord_status()

        section.body.addSpacing(Sizing.SPACE_SM)
        self._audio_alerts = Toggle(default=True, parent=section)
        section.body.addWidget(SettingRow(
            "Audio alerts", self._audio_alerts, parent=section,
        ))

        # Volume slider + Test button as one control cluster.
        vol_cluster = QWidget(section)
        vc = QHBoxLayout(vol_cluster)
        vc.setContentsMargins(0, 0, 0, 0)
        vc.setSpacing(Sizing.SPACE_MD)
        self._volume = QSlider(Qt.Orientation.Horizontal, vol_cluster)
        self._volume.setObjectName("slider")
        self._volume.setRange(0, 100)
        self._volume.setValue(70)
        self._volume.setFixedWidth(160)
        vc.addWidget(self._volume)
        test_btn = GhostButton("Test", vol_cluster)
        test_btn.clicked.connect(
            lambda: _play_test_sound(self._volume.value())
        )
        vc.addWidget(test_btn)
        section.body.addWidget(SettingRow(
            "Alert volume", vol_cluster, parent=section,
        ))
        return section

    # --- Discord helpers ------------------------------------------
    def _field_row(self, label: str, widget: QWidget) -> QWidget:
        wrap = QWidget(self)
        row = QHBoxLayout(wrap)
        row.setContentsMargins(0, Sizing.SPACE_XXS, 0, Sizing.SPACE_XXS)
        row.setSpacing(Sizing.SPACE_MD)
        lbl = QLabel(label, wrap, objectName="settingTitle")
        lbl.setMinimumWidth(110)
        row.addWidget(lbl)
        # Minimums, not fixed widths: a fixed 110+340 pushed the row past a
        # narrow window and the field was drawn off the right edge.
        if isinstance(widget, QLineEdit):
            widget.setMinimumWidth(200)
            widget.setMaximumWidth(340)
        row.addWidget(widget, 1)
        return wrap

    def _discord_paths(self):
        base = _project_root()
        for p in (base, os.path.join(base, "src")):
            if p not in sys.path:
                sys.path.insert(0, p)

    def _load_discord(self) -> dict:
        from .settings import load_settings
        cfg = dict(load_settings().get("discord", {}))
        token_enc = cfg.get("token_enc", "")
        if token_enc:
            try:
                self._discord_paths()
                import secret_store
                cfg["token"] = secret_store.decrypt(token_enc)
            except Exception:
                cfg["token"] = ""
        return cfg

    def _save_discord(self):
        from .settings import save_settings
        token = self._discord_token.text().strip()
        token_enc = ""
        if token:
            try:
                self._discord_paths()
                import secret_store
                token_enc = secret_store.encrypt(token)
            except Exception as exc:
                self._discord_status.setText(f"token encrypt failed: {exc}")
                return
        save_settings({"discord": {
            "enabled": self._discord_enable.isChecked(),
            "token_enc": token_enc,
            "channel_id": self._discord_channel.text().strip(),
            "interval": self._discord_interval.value(),
        }})
        self._apply_discord(token)
        self._discord_status.setText("Saved.")

    def _test_bot(self):
        """Post a one-off test message to the configured channel using the
        bot token (Discord REST API). Validates the token, the channel ID and
        the bot's permission to post there, without needing the live gateway
        connection, so it works before the bot is enabled."""
        token = self._discord_token.text().strip()
        channel = self._discord_channel.text().strip()
        if not token:
            self._discord_status.setText("Enter a bot token first.")
            return
        if not channel.isdigit():
            self._discord_status.setText("Enter a valid channel ID first.")
            return
        self._discord_status.setText("Testing bot...")
        import threading
        from . import discord_bot_test

        def _run():
            ok, msg = discord_bot_test.test_post(token, channel)
            self._bot_test_result.emit(ok, msg)

        threading.Thread(target=_run, name="DiscordBotTest",
                         daemon=True).start()

    def _on_bot_test_result(self, ok: bool, msg: str):
        self._discord_status.setText(
            msg if ok else f"Bot test failed: {msg}")

    def set_discord_hooks(self, hooks: dict):
        """Called by the run coordinator to supply the control callbacks,
        stats / screenshot providers, and log path the Discord bot needs."""
        self._discord_hooks = hooks or {}

    def autostart_discord(self):
        """Connect the Discord bot on launch if it is enabled and configured.
        Previously the gateway connect only ran from the Save handler, so users
        had to open Settings and Save every launch. Idempotent; no-op when
        disabled or unconfigured."""
        try:
            if not self._discord_enable.isChecked():
                return
            token = self._discord_token.text().strip()
            channel = self._discord_channel.text().strip()
            if token and channel:
                self._apply_discord(token)
        except Exception as exc:
            logging.warning("Discord autostart skipped: %s", exc)

    def _apply_discord(self, token: str):
        """Best-effort start/stop the bot. The bot instance is held at
        module scope so it survives across rebuilds."""
        global _discord_bot
        try:
            self._discord_paths()
            from discord_integration import DiscordBot
        except Exception as exc:
            self._discord_status.setText(f"discord unavailable: {exc}")
            return
        try:
            if _discord_bot is not None and _discord_bot.is_running():
                _discord_bot.stop()
            _discord_bot = None
            if self._discord_enable.isChecked() and token and \
                    self._discord_channel.text().strip():
                from wbcore.utils.datadir import wb_data_dir
                hooks = self._discord_hooks or {}
                _discord_bot = DiscordBot(
                    token,
                    int(self._discord_channel.text().strip() or 0),
                    self._discord_interval.value(),
                    hooks.get("callbacks", {}),
                    hooks.get("get_stats", lambda: {}),
                    hooks.get("get_screenshot", lambda: None),
                    hooks.get("log_path")
                    or os.path.join(wb_data_dir(), "game.log"),
                )
                _discord_bot.start()
        except Exception as exc:
            self._discord_status.setText(f"error: {exc}")
            return
        self._refresh_discord_status()

    def _refresh_discord_status(self):
        running = _discord_bot is not None and getattr(
            _discord_bot, "is_running", lambda: False)()
        if running:
            self._discord_status.setText("Connected")
        elif self._discord_enable.isChecked():
            self._discord_status.setText("Enabled (not connected)")
        else:
            self._discord_status.setText("Disabled")

    # --- Application ----------------------------------------------
    def _build_application(self) -> QWidget:
        section = Card("APPLICATION", self)
        section.body.addWidget(SettingRow(
            "Check for updates on launch",
            Toggle(default=True, parent=section), parent=section,
        ))
        section.body.addWidget(SettingRow(
            "Don't ask about updates",
            Toggle(default=False, parent=section), parent=section,
        ))
        reset = GhostButton("Reset to defaults", section)
        reset.setProperty("danger", "true")
        section.body.addWidget(SettingRow(
            "Reset settings", reset, parent=section,
        ))
        return section
