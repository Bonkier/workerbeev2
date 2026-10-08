# SPDX-License-Identifier: GPL-3.0-or-later
"""The title-bar feature search: what counts as a result, what is offered as
"Did you mean:", and that picking a result really lands on it."""

import pytest
from PySide6.QtWidgets import QApplication, QWidget

from gui_v2 import seasonal
from gui_v2 import search_engine as E

_app = QApplication.instance() or QApplication([])


# --- the ranking, on a hand-made list ---------------------------------

def _index():
    f = lambda fid, title, kind="setting", sub="", aliases=(): E.Feature(
        fid, title, kind, fid.split(":")[0], ("Settings",), sub, (), aliases)
    return E.Index([
        f("settings:settings", "Settings", "page"),
        f("settings:keyboard shortcuts", "KEYBOARD SHORTCUTS", "card",
          aliases=("hotkeys", "keybinds", "rebind keys")),
        f("settings:accent colour", "Accent colour",
          sub="The brand highlight: buttons, selection, links."),
        f("settings:mouse speed", "Mouse speed",
          sub="How fast the cursor moves.", aliases=("cursor speed",)),
        f("settings:mouse memory", "Mouse memory"),
        f("settings:humanized input", "HUMANIZED INPUT", "card",
          aliases=("natural mouse",)),
        f("md:skill replacement", "SKILL REPLACEMENT", "card",
          aliases=("swap skills",)),
        f("md:close limbus when finished", "Close Limbus when finished",
          sub="Sends Alt+F4 after the queue runs out.",
          aliases=("quit game",)),
        f("sched:add task", "ADD TASK", "card"),
        f("md:run count", "RUN COUNT", "card", aliases=("how many runs",)),
    ])


def _ids(hits):
    return [h.feature.id for h in hits]


def test_a_features_own_name_is_a_plain_result():
    r = _index().search("mouse speed")
    assert _ids(r.direct)[0] == "settings:mouse speed"
    assert r.heading == ""


def test_typing_part_of_a_name_already_finds_it():
    assert "md:skill replacement" in _ids(_index().search("skill rep").direct)
    assert _ids(_index().search("mou").direct)[:2] == [
        "settings:mouse speed", "settings:mouse memory"]


def test_a_misspelling_is_offered_as_did_you_mean():
    r = _index().search("skil replacment")
    assert r.direct == []
    assert r.heading == "Did you mean:"
    assert _ids(r.guesses)[0] == "md:skill replacement"


def test_swapped_letters_and_a_cut_ending_still_land():
    # "taks" loses its s to the plural rule; the word as typed must count.
    assert _ids(_index().search("add taks").guesses)[0] == "sched:add task"


def test_another_word_for_it_is_a_guess_not_a_result():
    r = _index().search("hotkeys")
    assert r.direct == []
    assert r.heading == "Did you mean:"
    assert _ids(r.guesses)[0] == "settings:keyboard shortcuts"


def test_two_words_typed_as_one_and_one_typed_as_two():
    assert _ids(_index().search("runcount").guesses)[0] == "md:run count"
    assert _ids(_index().search("hot keys").guesses)[0] == (
        "settings:keyboard shortcuts")


def test_either_spelling_of_colour_is_a_plain_result():
    for typed in ("accent color", "accent colour", "colors"):
        assert "settings:accent colour" in _ids(_index().search(typed).direct)


def test_a_request_in_a_sentence_still_finds_the_feature():
    r = _index().search("how do i change the hotkeys")
    assert _ids(r.guesses)[0] == "settings:keyboard shortcuts"
    r = _index().search("quit the game when done")
    assert "md:close limbus when finished" in _ids(r.guesses)[:2]


def test_words_spelled_out_in_the_description_are_found():
    r = _index().search("alt f4")
    assert "md:close limbus when finished" in _ids(r.direct + r.guesses)


def test_loose_matches_next_to_real_ones_are_labelled_related():
    r = _index().search("mouse")
    assert _ids(r.direct)[:2] == ["settings:mouse speed",
                                  "settings:mouse memory"]
    assert r.heading == "Related:"
    assert "settings:humanized input" in _ids(r.guesses)


def test_nonsense_and_single_letters_find_nothing():
    for typed in ("", "a", "zzzqqq", "    "):
        r = _index().search(typed)
        assert not r and r.heading == ""


def test_an_exact_name_beats_longer_names_containing_it():
    assert _ids(_index().search("settings").direct)[0] == "settings:settings"


def test_accents_and_punctuation_do_not_matter():
    assert E.normalise("Ryōshū's E.G.O  Gift!") == "ryoshus ego gift"
    assert E.stems("Skipping dialogues") == E.stems("skip dialogue")


# --- the real window ---------------------------------------------------

def _quiet(monkeypatch_setattr):
    """Stop every page from writing settings while a test drives it."""
    import importlib
    import pkgutil
    import gui_v2
    for m in pkgutil.iter_modules(gui_v2.__path__):
        if m.name.endswith("_test"):
            continue
        mod = importlib.import_module("gui_v2." + m.name)
        for name in ("save_settings", "save_section"):
            if hasattr(mod, name):
                monkeypatch_setattr(mod, name, lambda *a, **k: None)


@pytest.fixture(scope="module")
def window():
    from tests.conftest import destroy
    mp = pytest.MonkeyPatch()
    seasonal.force("off")
    _quiet(mp.setattr)
    from gui_v2.main_ui import MainUI
    from gui_v2.search_bar import FeatureSearch, SearchBox
    host = QWidget()
    host.resize(1280, 860)
    ui = MainUI(host)
    ui.setGeometry(0, 0, 1280, 860)
    box = SearchBox(host)
    search = FeatureSearch(box, ui, host)
    host.show()
    _app.processEvents()
    yield host, ui, box, search
    mp.undo()
    destroy(search, ui, host)


def _settle(ms=420):
    from PySide6.QtCore import QEventLoop, QTimer
    loop = QEventLoop()
    QTimer.singleShot(ms, loop.quit)
    loop.exec()


def _feature(search, fid):
    from gui_v2 import search_index
    search._index = search_index.build(search._ui)
    return next(f for f in search._index.features() if f.id == fid)


def test_every_alias_belongs_to_a_feature_that_exists(window):
    from gui_v2 import search_index
    from gui_v2.search_aliases import ALIASES
    _host, ui, _box, _search = window
    ids = {f.id for f in search_index.collect(ui)}
    assert sorted(set(ALIASES) - ids) == []
    for fid, aliases in ALIASES.items():
        assert aliases and all(a == E.normalise(a) for a in aliases), fid


def test_every_page_and_setting_is_listed(window):
    from gui_v2 import search_index
    from gui_v2.main_ui import _NAV_ITEMS
    _host, ui, _box, _search = window
    feats = search_index.collect(ui)
    ids = {f.id for f in feats}
    for key, label in _NAV_ITEMS:
        assert "%s:%s" % (key, E.normalise(label)) in ids
    for fid in ("settings:mouse speed", "settings:keyboard shortcuts",
                "mirror_dungeon:skill replacement", "mirror_dungeon:packs",
                "mirror_dungeon:hard", "stats:export csv",
                "luxcavation:thread rotation", "help:troubleshooting"):
        assert fid in ids
    assert len(ids) == len(feats)               # no id is used twice
    assert all(f.crumbs or f.kind == "page" for f in feats)


@pytest.mark.parametrize("typed, expected", [
    ("dashbord", "dashboard:dashboard"),
    ("luxcavasion", "luxcavation:luxcavation"),
    ("humanised imput", "settings:humanized input"),
    ("hotkeys", "settings:keyboard shortcuts"),
    ("second monitor", "settings:game monitor"),
    ("g hub", "settings:input backend"),
    ("how many runs", "mirror_dungeon:run count"),
    ("starlight", "mirror_dungeon:starting grace"),
    ("turn off animations", "settings:enable ui animations"),
    ("quit game when done", "mirror_dungeon:close limbus when finished"),
    ("report a bug", "help:join discord"),
    ("spreadsheet", "stats:export csv"),
])
def test_loose_and_misspelled_searches_reach_the_feature(window, typed,
                                                         expected):
    _host, _ui, _box, search = window
    r = search.search(typed)
    assert expected in _ids(r.direct + r.guesses)[:3]


def test_a_result_in_another_tab_opens_that_page_and_tab(window):
    _host, ui, _box, search = window
    ui.navigate_to("dashboard")
    search.go(_feature(search, "mirror_dungeon:pack search"))
    _settle()
    md = ui.page("mirror_dungeon")
    assert ui._stack.currentWidget() is ui._wrappers["mirror_dungeon"]
    assert md._tabbar.selected() == "Packs"
    assert md._tab_stack.currentIndex() == list(md._TABS).index("Packs")


def test_a_result_in_a_folded_panel_unfolds_it(window):
    from gui_v2.widgets import Card
    _host, ui, _box, search = window
    feature = _feature(search, "mirror_dungeon:skip dialogue")
    card = feature.widget
    while not isinstance(card, Card):
        card = card.parentWidget()
    card.set_expanded(False)
    search.go(feature)
    _settle()
    assert card.is_expanded()
    assert feature.widget.isVisible()


def test_finding_an_option_does_not_select_it(window):
    _host, ui, _box, search = window
    md = ui.page("mirror_dungeon")
    feature = _feature(search, "mirror_dungeon:extreme")
    seg = feature.widget.parentWidget()
    before = seg._current
    search.go(feature)
    _settle()
    assert seg._current == before


def test_the_outline_cleans_up_after_itself(window):
    from gui_v2.search_index import Spotlight
    _host, ui, _box, search = window
    search.go(_feature(search, "settings:mouse speed"))
    _settle(500)
    assert len(ui.findChildren(Spotlight)) == 1
    _settle(Spotlight._LIFE + 200)
    assert ui.findChildren(Spotlight) == []


def test_the_list_shows_did_you_mean_and_follows_the_arrow_keys(window):
    from PySide6.QtWidgets import QLabel
    _host, _ui, box, search = window
    popup = search._popup
    popup.show_results(search.search("hotkeys"))
    headings = [w.text() for w in popup.findChildren(QLabel)
                if w.objectName() == "searchHeading" and not w.isHidden()]
    assert headings == ["Did you mean:"]
    rows = popup.rows()
    assert rows and popup.current() is rows[0].feature
    assert "Settings" in rows[0].where()
    box.step.emit(1)
    assert popup.current() is rows[min(1, len(rows) - 1)].feature
    box.step.emit(-1)
    assert popup.current() is rows[0].feature

    popup.show_results(search.search("zzzqqq"))
    empty = [w.text() for w in popup.findChildren(QLabel)
             if w.objectName() == "searchEmpty" and not w.isHidden()]
    assert popup.rows() == [] and len(empty) == 1


def test_the_list_resizes_to_each_new_set_of_results(window):
    # Rows added to a list already on screen are shown a moment later; the
    # list used to size itself before that and collapse to a thin strip.
    _host, _ui, _box, search = window
    popup = search._popup
    popup.show_results(search.search("hotkeys"))
    search._place()
    popup.show()
    first = popup.height()
    popup.show_results(search.search("mouse"))
    search._place()
    rows = popup.rows()
    assert len(rows) >= 3
    assert popup.height() >= sum(r.height() for r in rows)
    assert first >= rows[0].height()
    popup.hide()


def test_enter_opens_the_highlighted_result_and_empties_the_field(window):
    _host, ui, box, search = window
    ui.navigate_to("dashboard")
    box.setText("keyboard shortcuts")
    search._timer.stop()
    search._popup.show_results(search.search(box.text()))
    search._popup.show()
    box.accept.emit()
    _settle()
    assert ui._stack.currentWidget() is ui._wrappers["settings"]
    assert box.text() == "" and not search._popup.isVisible()


def test_escape_clears_and_closes(window):
    _host, _ui, box, search = window
    box.setText("mouse")
    search._popup.show_results(search.search("mouse"))
    search._popup.show()
    box.dismiss.emit()
    assert box.text() == "" and not search._popup.isVisible()


def test_everyday_names_still_work_while_titles_are_seasonal(monkeypatch):
    from gui_v2 import search_index, themes
    from tests.conftest import destroy
    _quiet(monkeypatch.setattr)
    seasonal.force(seasonal.HALLOWEEN)
    try:
        from gui_v2.main_ui import MainUI
        ui = MainUI()
        index = search_index.build(ui)
        hit = index.search("mirror dungeon").direct[0].feature
        assert hit.id == "mirror_dungeon:mirror dungeon"
        assert hit.title == "EVIL Dungeon"
        assert index.search("evil dungeon").direct[0].feature.id == hit.id
        start = index.search("start mirror dungeon").direct
        assert any(h.feature.title == "Start EVIL Dungeon" for h in start)
        destroy(ui)
    finally:
        seasonal.force("off")
        themes.apply_saved_theme()


# --- found by review ---------------------------------------------------

def _named(*titles, aliases=None):
    return E.Index([
        E.Feature("p:" + E.normalise(t), t, "setting", "p", ("Page",), "",
                  (), tuple((aliases or {}).get(t, ())))
        for t in titles])


def test_a_typo_in_a_word_with_a_short_stem_is_still_recognised():
    # "settings" stems to "set", too short to tell a typo by.
    index = _named("Settings", "Reset settings", "Add task")
    for typed in ("setings", "settngs", "settinsg", "sttings"):
        r = index.search(typed)
        assert "p:settings" in _ids(r.guesses), typed


def test_one_typo_in_two_words_does_not_empty_the_results():
    index = _named("Mouse speed", "Market Fuse", "Audio alerts")
    assert _ids(index.search("muse speed").guesses)[0] == "p:mouse speed"


def test_a_cut_down_word_is_not_found_inside_other_names():
    index = _named("Settings", "Run setup", "Reset theme", "History",
                   "Skip rest shop", aliases={"Skip rest shop": ("store",)})
    assert _ids(index.search("settings").direct) == ["p:settings"]
    r = index.search("store")
    assert "p:history" not in _ids(r.direct)
    assert _ids(r.guesses)[0] == "p:skip rest shop"


def test_run_together_names_are_not_typo_targets():
    index = _named("Dashboard", aliases={"Dashboard": ("landing page",)})
    assert _ids(index.search("landingpage").guesses) == ["p:dashboard"]
    assert not index.search("language")


def test_pasted_text_is_cut_short_rather_than_ranked_in_full():
    import time
    from gui_v2.search_aliases import ALIASES
    index = E.Index([
        E.Feature(k, k.split(":")[1], "setting", k.split(":")[0], (), "",
                  (), v) for k, v in ALIASES.items()])
    started = time.time()
    index.search("run count hot keys pack search " * 120)
    assert time.time() - started < 2.0


def test_two_features_with_one_name_are_both_listed(window):
    from gui_v2 import search_index
    _host, ui, _box, _search = window
    feats = {f.id: f for f in search_index.collect(ui)}
    panel = feats["mirror_dungeon:pack search"]
    switch = feats["mirror_dungeon:pack search#setting"]
    assert panel.kind == "card" and switch.kind == "setting"
    assert panel.aliases and not switch.aliases
    assert "mirror_dungeon:packs#group" in feats
    # The same list whichever tab was looked at last.
    ui.page("mirror_dungeon")._tabbar._buttons["Packs"].click()
    _settle()
    again = [f.id for f in search_index.collect(ui)]
    ui.page("mirror_dungeon")._tabbar._buttons["General"].click()
    _settle()
    assert again == [f.id for f in search_index.collect(ui)]


def test_a_result_whose_widget_was_rebuilt_is_found_again(window):
    from gui_v2.search_index import Spotlight
    _host, ui, _box, search = window
    real = _feature(search, "settings:mouse speed")
    stale = E.Feature(real.id, real.title, real.kind, real.page,
                      real.crumbs, widget=QWidget())
    ui.navigate_to("dashboard")
    search.go(stale)
    _settle(520)
    assert ui._stack.currentWidget() is ui._wrappers["settings"]
    # The outline is drawn once the slide has ended; give it its moment.
    for _ in range(10):
        if ui.findChildren(Spotlight):
            break
        _settle(100)
    assert len(ui.findChildren(Spotlight)) == 1
    _settle(Spotlight._LIFE + 200)


def test_the_field_is_not_handed_focus_and_has_a_length_limit(window):
    from PySide6.QtCore import Qt
    _host, _ui, box, _search = window
    assert box.focusPolicy() == Qt.FocusPolicy.ClickFocus
    assert box.maxLength() == 80


def test_a_hotkey_being_recorded_outranks_the_search_shortcut():
    from PySide6.QtCore import QEvent, Qt
    from PySide6.QtGui import QKeyEvent
    from gui_v2.widgets import KeyCaptureButton
    button = KeyCaptureButton("Ctrl+Q")
    override = lambda: QKeyEvent(QEvent.Type.ShortcutOverride, Qt.Key.Key_K,
                                 Qt.KeyboardModifier.ControlModifier)
    idle = override()
    idle.ignore()
    button.event(idle)
    assert not idle.isAccepted()            # shortcuts work as usual
    button._start_capture()
    recording = override()
    recording.ignore()
    assert button.event(recording) and recording.isAccepted()
    button.focusOutEvent(__import__("PySide6.QtGui").QtGui.QFocusEvent(
        QEvent.Type.FocusOut))
    assert button._capturing is False       # never left stuck on "Press keys"
    button.deleteLater()


def test_a_combination_bound_to_a_run_does_not_also_open_search(monkeypatch):
    import gui_v2.settings as S
    from gui_v2.main_window import MainWindow
    calls = []

    class Fake:
        class _search:
            focus = staticmethod(lambda: calls.append("focus"))

    monkeypatch.setattr(S, "load_section",
                        lambda name: {"shortcuts": {"start_md": "Ctrl+K"}})
    MainWindow._search_shortcut(Fake, "Ctrl+K")
    assert calls == []
    MainWindow._search_shortcut(Fake, "Ctrl+F")
    assert calls == ["focus"]


def test_the_text_cursor_has_room_above_and_below(window):
    from gui_v2.theme import Sizing
    _host, _ui, box, _search = window
    line = box.fontMetrics().height()
    assert box.height() - line >= 8          # it used to touch the bottom edge
    assert box.height() <= Sizing.TITLEBAR_HEIGHT - 4
