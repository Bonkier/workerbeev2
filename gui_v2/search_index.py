# SPDX-License-Identifier: GPL-3.0-or-later
"""What the search bar can find, and how to get to it.

The list is read from the live window rather than kept by hand: every page,
tab, panel, group, setting, option and action button that is really there.
A feature added to a page is searchable without touching this file, and one
that is removed stops being offered."""

import re
import time

from PySide6.QtCore import QPoint, QRect, QTimer, QVariantAnimation, Qt
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import (
    QLabel, QScrollArea, QStackedWidget, QWidget,
)

from . import seasonal
from .search_aliases import ALIASES
from .search_engine import _KIND_RANK, Feature, Index, normalise
from .theme import Colors, Motion
from .widgets import (
    Card, CollapsibleSection, GhostButton, IconlessTabBar, LinkButton,
    PrimaryButton, Segmented, SettingRow,
)

# Buttons that mean nothing without their surroundings.
_BARE_BUTTONS = frozenset({
    "stop", "delete", "edit", "remove", "reset", "refresh", "view all",
    "load", "save", "test",
})
# Text that changes with the day or the data is not a feature name.
_VOLATILE = (re.compile(r"^use .* team$"), re.compile(r"^floor \d+$"))
_DESCRIPTION_CAP = 700


def feature_id(page: str, title: str) -> str:
    return "%s:%s" % (page, normalise(title))


def _valid(widget) -> bool:
    try:
        from shiboken6 import isValid
        return widget is not None and isValid(widget)
    except Exception:
        return widget is not None


def _stack_controller(page: QWidget, stack: QStackedWidget):
    """The tab strip or segmented control that drives `stack`, if any: the
    one with a button per page that sits nearest to it."""
    count = stack.count()
    best, best_depth = None, -1
    lineage = []
    w = stack
    while w is not None and w is not page.parentWidget():
        lineage.append(w)
        w = w.parentWidget()
    for ctrl in page.findChildren(QWidget):
        if not isinstance(ctrl, (IconlessTabBar, Segmented)):
            continue
        if len(ctrl._buttons) != count or stack.isAncestorOf(ctrl):
            continue
        w, depth = ctrl.parentWidget(), -1
        while w is not None:
            if w in lineage:
                depth = len(lineage) - lineage.index(w)
                break
            w = w.parentWidget()
        if depth > best_depth:
            best, best_depth = ctrl, depth
    return best


def _lineage(widget: QWidget, page: QWidget) -> list:
    """Ancestors of `widget` below `page`, outermost first, then itself."""
    out = []
    w = widget
    while w is not None and w is not page:
        out.append(w)
        w = w.parentWidget()
    out.reverse()
    return out


def _crumbs(widget: QWidget, page: QWidget, page_label: str,
            controllers: dict) -> tuple:
    out = [page_label]
    for a in _lineage(widget, page)[:-1]:
        parent = a.parentWidget()
        if isinstance(parent, QStackedWidget):
            ctrl = controllers.get(id(parent))
            if ctrl is not None:
                labels = list(ctrl._buttons)
                i = parent.indexOf(a)
                if 0 <= i < len(labels):
                    out.append(labels[i])
        title = getattr(a, "shown_title", None)
        if isinstance(a, (Card, CollapsibleSection)) and title:
            out.append(title)
    return tuple(out)


def _description(card: Card) -> str:
    """The explanatory text printed inside a panel."""
    parts = []
    for label in card.findChildren(QLabel):
        if label.objectName() in ("settingTitle", "settingSubtitle"):
            continue
        text = label.text()
        if label.wordWrap() and len(text) > 30 and "<" not in text[:1]:
            parts.append(text)
    return " ".join(parts)[:_DESCRIPTION_CAP]


def collect(ui) -> list:
    """Every findable feature in the main window, in page order."""
    from .main_ui import _NAV_ITEMS

    features, seen = [], set()

    def add(page_key, kind, shown, plain, widget, crumbs, subtitle=""):
        plain = (plain or shown or "").strip()
        shown = (shown or plain).strip()
        norm = normalise(plain)
        if not norm or any(p.match(norm) for p in _VOLATILE):
            return
        fid = feature_id(page_key, plain)
        if (fid, kind) in seen:
            return
        seen.add((fid, kind))
        names = (plain,) if normalise(shown) != norm else ()
        features.append(Feature(
            id=fid, title=shown, kind=kind, page=page_key, crumbs=crumbs,
            subtitle=subtitle, names=names, widget=widget))

    for page_key, label in _NAV_ITEMS:
        page = ui.page(page_key)
        if page is None:
            continue
        page_label = seasonal.title(label)
        add(page_key, "page", page_label, label, page, ())

        controllers = {}
        for stack in page.findChildren(QStackedWidget):
            controllers[id(stack)] = _stack_controller(page, stack)

        def inside_card(w):
            w = w.parentWidget()
            while w is not None and w is not page:
                if isinstance(w, Card):
                    return True
                w = w.parentWidget()
            return False

        for w in page.findChildren(QWidget):
            if isinstance(w, IconlessTabBar):
                if inside_card(w):
                    continue        # a panel's own sub-tabs (F1, F2, ...)
                crumbs = _crumbs(w, page, page_label, controllers)
                for text, btn in w._buttons.items():
                    add(page_key, "tab", text, text, btn, crumbs)
            elif isinstance(w, Card):
                if getattr(w, "plain_title", None):
                    add(page_key, "card", w.shown_title, w.plain_title, w,
                        _crumbs(w, page, page_label, controllers),
                        _description(w))
            elif isinstance(w, CollapsibleSection):
                if getattr(w, "plain_title", None):
                    add(page_key, "group", w.shown_title, w.plain_title, w,
                        _crumbs(w, page, page_label, controllers))
            elif isinstance(w, SettingRow):
                title = getattr(w, "title_text", "")
                add(page_key, "setting", title, title, w,
                    _crumbs(w, page, page_label, controllers),
                    getattr(w, "subtitle_text", ""))
            elif isinstance(w, Segmented):
                crumbs = _crumbs(w, page, page_label, controllers)
                for text, btn in w._buttons.items():
                    add(page_key, "option", text, text, btn, crumbs)
            elif isinstance(w, (PrimaryButton, GhostButton, LinkButton)):
                shown = w.text().strip()
                plain = seasonal.plain(shown)
                if normalise(plain) in _BARE_BUTTONS:
                    continue
                add(page_key, "action", shown, plain, w,
                    _crumbs(w, page, page_label, controllers))
    return _settle_ids(features)


def _settle_ids(features: list) -> list:
    """Two things on a page can share a name (the "Pack search" switch and
    the PACK SEARCH panel). Both stay findable: the broader one keeps the
    plain id and the other words for it, the narrower one gets its kind
    appended. The order is fixed here too, because the order widgets are
    read in changes with whichever tab was looked at last."""
    pages = {}
    for f in features:
        pages.setdefault(f.page, len(pages))
    features.sort(key=lambda f: (pages[f.page], _KIND_RANK.get(f.kind, 9),
                                 normalise(f.title), f.crumbs))
    taken = set()
    for f in features:
        if f.id in taken:
            f.id = "%s#%s" % (f.id, f.kind)
        else:
            f.aliases = tuple(ALIASES.get(f.id, ()))
        taken.add(f.id)
    return features


def build(ui) -> Index:
    return Index(collect(ui))


# --- getting there ----------------------------------------------------

def _current(ui, feature: Feature):
    """The widget for `feature` as its page has it now. A page can rebuild
    parts of itself when it is shown, which deletes the one that was read
    into the index."""
    widget, page = feature.widget, ui.page(feature.page)
    if _valid(widget) and (widget is page or page.isAncestorOf(widget)):
        return widget
    for f in collect(ui):
        if f.id == feature.id:
            return f.widget
    return None


def reveal(ui, feature: Feature, flash: bool = True) -> bool:
    """Bring `feature` on screen: its page, its tab, its panel unfolded,
    scrolled into view and outlined for a moment. False if it is gone."""
    page = ui.page(feature.page)
    if page is None:
        return False
    waited = False
    if getattr(ui, "_stack", None) is not None and \
            ui._stack.currentWidget() is not ui._wrappers.get(feature.page):
        waited = True
    ui.navigate_to(feature.page)
    if feature.kind == "page":
        return True
    widget = _current(ui, feature)
    if widget is None:
        return False

    target = widget
    for a in _lineage(widget, page):
        parent = a.parentWidget()
        if isinstance(parent, QStackedWidget) and \
                parent.currentWidget() is not a:
            ctrl = _stack_controller(page, parent)
            index = parent.indexOf(a)
            labels = list(ctrl._buttons) if ctrl is not None else []
            if not 0 <= index < len(labels) or \
                    labels[index] in getattr(ctrl, "_locked", ()):
                # A view only the page itself can switch to: stop at it.
                target = parent
                break
            ctrl._buttons[labels[index]].click()
            waited = True
        if isinstance(a, (Card, CollapsibleSection)) and not a.is_expanded():
            a.set_expanded(True)
            waited = True
    if feature.kind == "tab" and target is widget and not widget.isChecked():
        widget.click()
        waited = True

    whole = target is widget

    def settle():
        # The page is shown again when its slide ends, and may rebuild then.
        # A slide that runs late keeps it parked past its nominal length, so
        # look again shortly rather than measure a hidden page.
        if not page.isVisible() and time.monotonic() < deadline:
            QTimer.singleShot(60, ui, settle)
            return
        target = _current(ui, feature) if whole else parked
        if not _valid(target):
            return
        # Something shown only in certain states (a button that appears
        # after a check fails): point at the nearest thing that is there.
        shown = target
        while shown is not page and not shown.isVisible():
            shown = shown.parentWidget()
        w = shown.parentWidget()
        while w is not None:
            if isinstance(w, QScrollArea) and w.widget() is not None \
                    and w.widget().isAncestorOf(shown):
                w.ensureWidgetVisible(shown, 24, 90)
            w = w.parentWidget()
        if flash and shown is not page:
            Spotlight(ui, shown)

    parked = target
    deadline = time.monotonic() + 3.0
    # A page or tab switch slides, and the incoming page is parked until the
    # slide ends, so nothing can be scrolled or measured before then.
    QTimer.singleShot(Motion.NORMAL + 90 if waited else 0, ui, settle)
    return True


class Spotlight(QWidget):
    """A brief outline around the thing that was searched for, so the eye
    lands on it after the page has moved."""

    _PAD = 4
    _LIFE = 1700

    def __init__(self, host: QWidget, target: QWidget):
        super().__init__(host)
        self._target = target
        self._level = 1.0
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground)
        self._anim = QVariantAnimation(self)
        self._anim.setDuration(self._LIFE)
        self._anim.setStartValue(0.0)
        self._anim.setEndValue(1.0)
        self._anim.valueChanged.connect(self._tick)
        self._anim.finished.connect(self.deleteLater)
        if self._place():
            self.show()
            self.raise_()
            self._anim.start()
        else:
            self.deleteLater()

    def _place(self) -> bool:
        target, host = self._target, self.parentWidget()
        if not _valid(target) or host is None or not target.isVisible():
            return False
        top_left = target.mapTo(host, QPoint(0, 0))
        rect = QRect(top_left, target.size()).adjusted(
            -self._PAD, -self._PAD, self._PAD, self._PAD)
        rect = rect.intersected(host.rect())
        if rect.isEmpty():
            return False
        self.setGeometry(rect)
        return True

    def _tick(self, value):
        # Two pulses, then out.
        t = float(value)
        self._level = max(0.0, 1.0 - t) * (0.65 + 0.35 * abs(1 - 4 * t % 2))
        if not self._place():
            self._anim.stop()
            self.deleteLater()
            return
        self.update()

    def paintEvent(self, _event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, False)
        edge = QColor(Colors.ACCENT)
        edge.setAlphaF(min(1.0, 0.25 + self._level))
        fill = QColor(Colors.ACCENT)
        fill.setAlphaF(0.10 * self._level)
        p.fillRect(self.rect(), fill)
        p.setPen(QPen(edge, 2))
        p.drawRect(self.rect().adjusted(1, 1, -1, -1))
        p.end()
