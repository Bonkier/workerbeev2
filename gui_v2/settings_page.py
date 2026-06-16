# SPDX-License-Identifier: GPL-3.0-or-later
"""Settings page - app preferences and configuration management.

Sections: Profiles (save/load/import/export named config sets),
Humanized Input (movement profile + rhythm - maps to the automation
backend's MACRO_PROFILE / MACRO_RHYTHM), Integrations (Discord, audio),
and Application (updates, theme, reset).

The controls here map to real backend params where one exists; nothing
fake is added. Persistence wiring lands with the settings_manager port.
"""

import os
import sys

from PySide6.QtCore import QObject, QThread, Qt, Signal, Slot
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import (
    QColorDialog, QComboBox, QHBoxLayout, QLabel, QLineEdit, QPushButton,
    QSlider, QSpinBox, QVBoxLayout, QWidget,
)

from .settings import load_section, save_section
from .theme import Colors, Sizing
from .widgets import (
    Card, ClickOrderGrid, GhostButton, KeyCaptureButton, OrderedList,
    PageHeader, Segmented, SettingRow, Toggle,
)

_SECTION = "app_settings"


class _BridgeProbe(QObject):
    """Off-thread LGHub liveness probe. open() is a no-op when the
    bridge is already up but raises / blocks when LGHub is gone, so it
    catches both cold-start and mid-session disconnects without freezing
    the GUI thread."""

    done = Signal(bool, str)

    @Slot()
    def run(self):
        try:
            base = _project_root()
            for p in (base, os.path.join(base, "src")):
                if p not in sys.path:
                    sys.path.insert(0, p)
            from bridge.bridge import Bridge
            b = Bridge(auto_open=False)
            b.open()
            ok = bool(b.is_open())
            self.done.emit(ok, "" if ok else "bridge reported not open")
        except Exception as exc:
            self.done.emit(False, f"{type(exc).__name__}: {exc}")


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


# Holds the live Discord bot across page rebuilds.
_discord_bot = None


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
        print(f"audio test failed: {exc}")


def _combo(items, parent=None):
    box = QComboBox(parent)
    box.setObjectName("combo")
    box.addItems(items)
    box.setCursor(Qt.CursorShape.PointingHandCursor)
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
        outer.addWidget(self._build_sinner_exclusion())
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
            "Game monitor",
            "Which display the Limbus window is on.",
            self._monitor, parent=section,
        ))
        return section

    # --- Appearance (colour theme) --------------------------------
    def _build_appearance(self) -> QWidget:
        from . import themes
        section = Card("APPEARANCE", self)
        section.body.addWidget(self._wrap_hint(
            "Pick a colour theme, or customise the accent and background "
            "with the colour picker. Changes apply instantly."))

        cur = themes.current_theme()
        names = list(themes.PRESETS.keys()) + ["Custom"]
        self._theme_combo = _combo(names, section)
        start = cur["preset"] if cur["preset"] in names else "WorkerBee Yellow"
        self._theme_combo.setCurrentText(start)
        # Connect AFTER setting the initial value so it doesn't re-fire.
        self._theme_combo.currentTextChanged.connect(self._on_theme_preset)
        section.body.addWidget(SettingRow(
            "Theme", "Built-in colour schemes.",
            self._theme_combo, parent=section,
        ))

        self._accent_swatch = self._make_swatch(cur["accent"], self._pick_accent)
        section.body.addWidget(SettingRow(
            "Accent colour",
            "The brand highlight: buttons, selection, links, the overlay bee.",
            self._accent_swatch, parent=section,
        ))

        self._bg_swatch = self._make_swatch(cur["bg"], self._pick_background)
        section.body.addWidget(SettingRow(
            "Background",
            "Base window colour; cards and borders are derived from it.",
            self._bg_swatch, parent=section,
        ))

        self._text_swatch = self._make_swatch(cur["text"], self._pick_text)
        section.body.addWidget(SettingRow(
            "Text colour",
            "Primary text colour; dimmer labels are derived from it.",
            self._text_swatch, parent=section,
        ))

        reset = GhostButton("Reset theme", section)
        reset.clicked.connect(self._reset_theme)
        section.body.addWidget(SettingRow(
            "Reset theme", "Back to the default yellow-on-dark scheme.",
            reset, parent=section,
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
            f"border-radius:6px; font-size:10pt; font-weight:600; }}")

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
            ("skip_ego_battle", "Skip EGO in battle",
             "Never spend an EGO during clashes (faster, riskier)."),
            ("good_pc", "Good PC mode",
             "Trim transition waits - only if your PC keeps up."),
            ("debug_matches", "Debug image matches",
             "Save match debug images while running."),
            ("grayscale", "Grayscale speed-boost",
             "Match in grayscale for a small speed gain."),
            ("reconnect_online", "Reconnect only when online",
             "Wait for internet before retrying a dropped connection."),
            ("animations", "Enable UI animations",
             "Page crossfades and the splash morph."),
        ]
        for key, title, subtitle in rows:
            default = key in ("reconnect_online", "animations")
            tog = Toggle(default=default, parent=section)
            self._advanced[key] = tog
            section.body.addWidget(SettingRow(title, subtitle, tog, parent=section))
        return section

    # --- Run overlay + debug visualizers --------------------------
    def _build_overlay(self) -> QWidget:
        section = Card("RUN OVERLAY", self)
        section.body.addWidget(self._wrap_hint(
            "A translucent, click-through overlay drawn over the game "
            "during a run. It is not interactive and hides itself whenever "
            "WorkerBee is the focused window."))
        self._overlay_toggles = {}
        rows = [
            ("hud", "Show run overlay",
             "Current phase, run counter, cursor target, path-tracer "
             "state, and the last few actions."),
            ("vision", "Debug: show what the macro sees",
             "Box and label every template the bot locates on screen."),
            ("path", "Debug: show mouse target + path",
             "Mark where the cursor is heading and the path it will "
             "trace; clears when the bot picks its next target."),
        ]
        for key, title, subtitle in rows:
            tog = Toggle(default=(key == "hud"), parent=section)
            self._overlay_toggles[key] = tog
            section.body.addWidget(SettingRow(title, subtitle, tog, parent=section))
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
        section.body.addWidget(self._wrap_hint(
            "WorkerBee routes input through Logitech G Hub (v2021.11.1775). "
            "LGHub must be running and must NOT auto-update to a newer "
            "version."))

        row = QHBoxLayout()
        row.setSpacing(Sizing.SPACE_MD)
        self._lghub_status = QLabel("Not checked yet", self,
                                    objectName="settingTitle")
        row.addWidget(self._lghub_status)
        row.addStretch(1)
        refresh = GhostButton("Check connection", self)
        refresh.clicked.connect(self._check_lghub)
        row.addWidget(refresh)
        section.body.addLayout(row)
        return section

    def _wrap_hint(self, text: str) -> QLabel:
        lbl = QLabel(text, self, objectName="inlineHint")
        lbl.setWordWrap(True)
        return lbl

    def _check_lghub(self):
        if self._probe_thread is not None:
            return
        self._lghub_status.setText("Checking LGHub connection…")
        self._lghub_status.setStyleSheet(f"color: {Colors.TEXT_SECONDARY};")
        self._probe_thread = QThread(self)
        self._probe = _BridgeProbe()
        self._probe.moveToThread(self._probe_thread)
        self._probe.done.connect(self._on_lghub_done)
        self._probe_thread.started.connect(self._probe.run)
        self._probe_thread.start()

    def _on_lghub_done(self, ok: bool, detail: str):
        if ok:
            self._lghub_status.setText("Connected to LGHub")
            self._lghub_status.setStyleSheet(f"color: {Colors.SUCCESS};")
        else:
            self._lghub_status.setText(
                "Not reachable - start LGHub, then check again"
            )
            self._lghub_status.setStyleSheet(f"color: {Colors.WARNING};")
        if self._probe_thread is not None:
            self._probe_thread.quit()
            self._probe_thread.wait()
            self._probe_thread.deleteLater()
        self._probe = None
        self._probe_thread = None

    # --- Keyboard shortcuts ---------------------------------------
    def _build_shortcuts(self) -> QWidget:
        section = Card("KEYBOARD SHORTCUTS", self)
        section.body.addWidget(self._wrap_hint(
            "Click a binding, then press the key combo. Esc cancels, "
            "Backspace clears."))
        self._shortcuts = {}
        for key, label, default in _SHORTCUTS:
            btn = KeyCaptureButton(default, parent=section)
            self._shortcuts[key] = btn
            section.body.addWidget(SettingRow(label, "", btn, parent=section))
        return section

    # --- Per-team sinner assignment -------------------------------
    def _build_sinners(self) -> QWidget:
        section = Card("SINNERS", self)
        section.body.addWidget(self._wrap_hint(
            "Sinner selection and order, per team. Click sinners in the "
            "order you want the bot to pick them; click again to remove "
            "(everything after shifts up)."))

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
        self._sinner_order = ClickOrderGrid(
            list(_SINNER_NAMES), rows=2, cols=6, parent=section,
        )
        self._sinner_order.changed.connect(self._on_sinner_changed)
        section.body.addWidget(self._sinner_order)

        state = self._sinner_states[self._sinner_team]
        self._sinner_order.set_order(state["order"])
        self._update_sinner_count()
        return section

    def _build_sinner_exclusion(self) -> QWidget:
        section = Card("SINNER SWAP EXCLUSION", self)
        section.body.addWidget(self._wrap_hint(
            "Sinners to leave alone during max-energy swaps. Click in "
            "the order you want them excluded."))
        self._sinner_exclude = ClickOrderGrid(
            list(_SINNER_NAMES), rows=2, cols=6, parent=section,
        )
        self._sinner_exclude.changed.connect(self._on_sinner_changed)
        section.body.addWidget(self._sinner_exclude)
        state = self._sinner_states[self._sinner_team]
        self._sinner_exclude.set_order(state["exclude"])
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

    # --- Persistence ---------------------------------------------
    def _connect_persistence(self):
        self._monitor.currentIndexChanged.connect(self._save_state)
        self._macro_profile.selection_changed.connect(self._save_state)
        self._rhythm.toggled.connect(self._save_state)
        self._audio_alerts.toggled.connect(self._save_state)
        self._volume.valueChanged.connect(self._save_state)
        self._show_descriptions.toggled.connect(self._save_state)
        self._show_descriptions.toggled.connect(self._on_descriptions_toggled)
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
            "audio_alerts": self._audio_alerts.isChecked(),
            "volume": self._volume.value(),
            "show_descriptions": self._show_descriptions.isChecked(),
            "advanced": {k: t.isChecked() for k, t in self._advanced.items()},
            "overlay": {k: t.isChecked()
                        for k, t in self._overlay_toggles.items()},
            "shortcuts": {k: b.binding() for k, b in self._shortcuts.items()},
            "sinners": sinners,
        })

    def _on_descriptions_toggled(self, on: bool):
        """Live-apply the description visibility when the user flips it. The
        startup / config-load apply (in MainUI) covers the initial state, so
        skip the partial apply while restoring saved settings."""
        if self._loading:
            return
        from . import help_text
        help_text.apply(bool(on))

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
                if "audio_alerts" in s:
                    self._audio_alerts.setChecked(bool(s["audio_alerts"]))
                if isinstance(s.get("volume"), int):
                    self._volume.setValue(s["volume"])
                if "show_descriptions" in s:
                    self._show_descriptions.setChecked(
                        bool(s["show_descriptions"]))
                for k, v in (s.get("advanced") or {}).items():
                    if k in self._advanced:
                        self._advanced[k].setChecked(bool(v))
                for k, v in (s.get("overlay") or {}).items():
                    if k in self._overlay_toggles:
                        self._overlay_toggles[k].setChecked(bool(v))
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
        from .copy import (
            SETTINGS_CONFIG_COMBO_PLACEHOLDER,
            SETTINGS_CONFIGS_HINT,
        )
        section = Card("CONFIGS", self)
        section.body.addWidget(self._wrap_hint(SETTINGS_CONFIGS_HINT))

        row = QHBoxLayout()
        row.setSpacing(Sizing.SPACE_SM)
        # Editable combo so the user can EITHER pick an existing config
        # to overwrite OR type a fresh name to save a new one. Replaces
        # the old "Save as" button (which opened a QInputDialog that was
        # being eaten by the frameless main window and never appeared).
        self._config_combo = _combo([], section)
        self._config_combo.setEditable(True)
        self._config_combo.setMinimumWidth(220)
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
            "Movement profile",
            "Safe is the most human-like timing; Chaotic adds the most "
            "variance. Fast trims pauses for speed.",
            self._macro_profile,
            parent=section,
        ))
        self._rhythm = Toggle(default=True, parent=section)
        section.body.addWidget(SettingRow(
            "Rhythm pauses",
            "Occasional natural pauses and micro-drift between actions.",
            self._rhythm,
            parent=section,
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
            "Mouse speed",
            "How fast the cursor moves. 100% is the default human-like speed; "
            "higher is faster, but above 200% looks less human.",
            ms_cluster, parent=section,
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
        section.body.addWidget(self._wrap_hint(
            "Discord bot: posts run summaries and screenshots to a channel, "
            "and adds buttons to start or stop runs right from Discord. "
            "Create a bot in the Discord Developer Portal, invite it to your "
            "server, then paste its token and the channel ID below."))

        self._discord_enable = Toggle(default=bool(cfg.get("enabled")),
                                      parent=section)
        section.body.addWidget(SettingRow(
            "Discord bot",
            "Posts run summaries + screenshots, and adds remote start/stop "
            "buttons. Needs a bot token and channel ID.",
            self._discord_enable, parent=section,
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
            "Audio alerts",
            "Play a sound when a run finishes or fails.",
            self._audio_alerts,
            parent=section,
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
            "Alert volume", "Preview the alert sound at this level.",
            vol_cluster, parent=section,
        ))
        return section

    # --- Discord helpers ------------------------------------------
    def _field_row(self, label: str, widget: QWidget) -> QWidget:
        wrap = QWidget(self)
        row = QHBoxLayout(wrap)
        row.setContentsMargins(0, Sizing.SPACE_XXS, 0, Sizing.SPACE_XXS)
        row.setSpacing(Sizing.SPACE_MD)
        lbl = QLabel(label, wrap, objectName="settingTitle")
        lbl.setFixedWidth(110)
        row.addWidget(lbl)
        if isinstance(widget, QLineEdit):
            widget.setFixedWidth(340)
        row.addWidget(widget)
        row.addStretch(1)
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
                hooks = self._discord_hooks or {}
                _discord_bot = DiscordBot(
                    token,
                    int(self._discord_channel.text().strip() or 0),
                    self._discord_interval.value(),
                    hooks.get("callbacks", {}),
                    hooks.get("get_stats", lambda: {}),
                    hooks.get("get_screenshot", lambda: None),
                    hooks.get("log_path")
                    or os.path.join(_project_root(), "game.log"),
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
        self._show_descriptions = Toggle(default=True, parent=section)
        section.body.addWidget(SettingRow(
            "Show descriptions",
            "Show the gray helper text under settings and features. Turn off "
            "for a denser, text-light UI.",
            self._show_descriptions,
            parent=section,
        ))
        section.body.addWidget(SettingRow(
            "Check for updates on launch",
            "Looks at GitHub releases when the splash opens.",
            Toggle(default=True, parent=section),
            parent=section,
        ))
        section.body.addWidget(SettingRow(
            "Don't ask about updates",
            "Skip the update prompt even when one is available.",
            Toggle(default=False, parent=section),
            parent=section,
        ))
        reset = GhostButton("Reset to defaults", section)
        reset.setProperty("danger", "true")
        section.body.addWidget(SettingRow(
            "Reset settings",
            "Restore every setting to its default value.",
            reset,
            parent=section,
        ))
        return section
