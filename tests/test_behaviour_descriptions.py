# SPDX-License-Identifier: GPL-3.0-or-later
"""The descriptions under the Behaviour toggles get the height their text
needs at the width they are laid out at (they were cut after a line and a
half when the column was wider than the rail)."""
import time

import pytest
from PySide6.QtWidgets import QApplication, QLabel, QWidget


def _quiet(setattr_):
    import importlib
    import pkgutil
    import gui_v2
    for m in pkgutil.iter_modules(gui_v2.__path__):
        if m.name.endswith("_test"):
            continue
        mod = importlib.import_module("gui_v2." + m.name)
        for name in ("save_settings", "save_section"):
            if hasattr(mod, name):
                setattr_(mod, name, lambda *a, **k: None)


def _settle(app, seconds=0.4):
    end = time.time() + seconds
    while time.time() < end:
        app.processEvents()
        time.sleep(0.005)


@pytest.fixture(scope="module")
def shown():
    from tests.conftest import destroy
    mp = pytest.MonkeyPatch()
    _quiet(mp.setattr)
    app = QApplication.instance() or QApplication([])
    from gui_v2.main_ui import MainUI, _TAGS
    host = QWidget()
    host.resize(1280, 860)
    main = MainUI(host)
    main.setGeometry(0, 0, 1280, 860)
    host.show()
    _settle(app)
    settings = main.page(next(k for k, v in _TAGS.items() if v == "SE"))
    settings._show_descriptions.setChecked(True)
    md_key = next(k for k, v in _TAGS.items() if v == "MD")
    main.navigate_to(md_key)
    _settle(app, 0.8)
    yield app, main.page(md_key)
    host.hide()
    destroy(main, host)
    mp.undo()


def test_every_behaviour_description_is_fully_tall(shown):
    app, page = shown
    from gui_v2.widgets import SettingRow
    groups = page._behaviour_groups
    assert set(groups) == {"RUN", "ON DEFEAT", "SHOP AND EGO", "WHEN FINISHED"}
    for group in groups.values():
        if not group._folder._expanded:
            group._folder.set(True)
    _settle(app, 0.8)
    short, seen = [], 0
    for group in groups.values():
        for row in group.findChildren(SettingRow):
            labels = [l for l in row.findChildren(QLabel) if l.objectName() == "settingSubtitle"]
            if not labels or not row.isVisible():
                continue
            label = labels[0]
            seen += 1
            need = label.heightForWidth(label.width())
            if label.height() < need - 1:
                short.append((row.title_text, label.height(), need))
    assert seen >= 15, "the behaviour rows were not shown"
    assert short == []
