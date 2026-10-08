# SPDX-License-Identifier: GPL-3.0-or-later
"""The search bar in the title bar: type a feature's name, or roughly what
it does, and jump to it.

Results that match a feature's own name are listed plainly. When nothing
does, or the wording was loose or misspelled, the closest features are
offered under "Did you mean:"."""

from PySide6.QtCore import QEvent, QObject, QPoint, QRect, QSize, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QFont, QFontMetrics, QPainter
from PySide6.QtWidgets import (
    QAbstractButton, QApplication, QFrame, QLabel, QLineEdit, QVBoxLayout,
    QWidget,
)

from . import search_index
from .search_engine import Results
from .theme import Colors, Fonts, Sizing

PLACEHOLDER = "Search features  (Ctrl+K)"
_SEPARATOR = "  %s  " % chr(0x203A)
_KIND_LABEL = {"page": "Page", "tab": "Tab", "card": "Panel",
               "group": "Group", "setting": "Setting", "option": "Option",
               "action": "Button"}


def _voxel() -> bool:
    try:
        from .skins import is_voxel
        return is_voxel()
    except Exception:
        return False


class SearchBox(QLineEdit):
    """The field itself. Arrow keys, Enter and Escape are passed on rather
    than handled here, because they act on the list under it."""

    step = Signal(int)          # arrow up / down
    accept = Signal()           # Enter
    dismiss = Signal()          # Escape
    focused = Signal(bool)

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("titleSearch")
        self.setPlaceholderText(PLACEHOLDER)
        # Reached by a click or by Ctrl+K only. As the first widget in the
        # window it would otherwise be handed the focus whenever something
        # else gives it up, and open its list with nobody typing.
        self.setFocusPolicy(Qt.FocusPolicy.ClickFocus)
        self.setMaxLength(80)
        self.setClearButtonEnabled(False)
        self.setMinimumWidth(160)
        self.setMaximumWidth(380)
        self.setToolTip("Find a setting, page or button by name")
        self._fit_height()

    def _fit_height(self):
        """Tall enough that the text cursor, which is as tall as a line of
        text, stands clear of both edges, without outgrowing the title bar."""
        self.ensurePolished()
        height = min(Sizing.TITLEBAR_HEIGHT - 4,
                     max(28, self.fontMetrics().height() + 10))
        if self.minimumHeight() != height or self.maximumHeight() != height:
            self.setFixedHeight(height)

    def changeEvent(self, event):
        super().changeEvent(event)
        if event.type() in (QEvent.Type.FontChange, QEvent.Type.StyleChange):
            self._fit_height()

    def sizeHint(self) -> QSize:
        return QSize(340, self.minimumHeight())

    def keyPressEvent(self, event):
        key = event.key()
        if key == Qt.Key.Key_Down:
            self.step.emit(1)
        elif key == Qt.Key.Key_Up:
            self.step.emit(-1)
        elif key in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            self.accept.emit()
        elif key == Qt.Key.Key_Escape:
            self.dismiss.emit()
        else:
            super().keyPressEvent(event)
            return
        event.accept()

    def focusInEvent(self, event):
        super().focusInEvent(event)
        self.focused.emit(True)

    def focusOutEvent(self, event):
        super().focusOutEvent(event)
        self.focused.emit(False)


class _ResultRow(QAbstractButton):
    """One feature: its name, and where it lives."""

    def __init__(self, feature, parent: QWidget | None = None):
        super().__init__(parent)
        self.feature = feature
        self._current = False
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFixedHeight(30 if _voxel() else 34)
        self.setMouseTracking(True)

    def set_current(self, on: bool):
        if on != self._current:
            self._current = on
            self.update()

    def enterEvent(self, event):
        self.update()
        super().enterEvent(event)

    def leaveEvent(self, event):
        self.update()
        super().leaveEvent(event)

    def where(self) -> str:
        kind = _KIND_LABEL.get(self.feature.kind, "")
        path = _SEPARATOR.join(self.feature.crumbs)
        return "%s  %s  %s" % (kind, chr(0x00B7), path) if path else kind

    def paintEvent(self, _event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.TextAntialiasing, True)
        rect = self.rect()
        if self._current or self.underMouse():
            fill = QColor(Colors.BG_HOVER)
            if not self._current:
                fill.setAlpha(120)
            p.fillRect(rect, fill)
        if self._current:
            p.fillRect(QRect(0, 0, 3, rect.height()), QColor(Colors.ACCENT))

        pad = Sizing.SPACE_MD
        family = Fonts.FAMILY.split(",")[0].strip()
        title_font = QFont(family)
        title_font.setPointSize(Fonts.SIZE_SM)
        title_font.setWeight(QFont.Weight.DemiBold)
        where_font = QFont(family)
        where_font.setPointSize(Fonts.SIZE_XS)

        inner = rect.adjusted(pad, 0, -pad, 0)
        title_fm = QFontMetrics(title_font)
        where_fm = QFontMetrics(where_font)
        title = self.feature.title
        title_w = min(title_fm.horizontalAdvance(title),
                      int(inner.width() * 0.6))
        p.setFont(title_font)
        p.setPen(QColor(Colors.TEXT_PRIMARY))
        p.drawText(QRect(inner.left(), inner.top(), title_w, inner.height()),
                   int(Qt.AlignmentFlag.AlignVCenter
                       | Qt.AlignmentFlag.AlignLeft),
                   title_fm.elidedText(title, Qt.TextElideMode.ElideRight,
                                       title_w))
        room = inner.width() - title_w - Sizing.SPACE_LG
        if room > 40:
            p.setFont(where_font)
            p.setPen(QColor(Colors.TEXT_TERTIARY))
            p.drawText(QRect(inner.right() - room, inner.top(), room,
                             inner.height()),
                       int(Qt.AlignmentFlag.AlignVCenter
                           | Qt.AlignmentFlag.AlignRight),
                       where_fm.elidedText(self.where(),
                                           Qt.TextElideMode.ElideLeft, room))
        p.end()


class SearchPopup(QFrame):
    """The list under the search box. A child of the window, not a window of
    its own, so it never takes focus from the field being typed in."""

    chosen = Signal(object)

    def __init__(self, host: QWidget):
        super().__init__(host)
        self.setObjectName("searchPopup")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self._col = QVBoxLayout(self)
        self._col.setContentsMargins(1, Sizing.SPACE_XS, 1, Sizing.SPACE_XS)
        self._col.setSpacing(0)
        self._rows: list = []
        self._at = -1
        self.hide()

    def rows(self) -> list:
        return list(self._rows)

    def current(self):
        return self._rows[self._at].feature if 0 <= self._at < len(
            self._rows) else None

    def _clear(self):
        while self._col.count():
            item = self._col.takeAt(0)
            w = item.widget()
            if w is not None:
                w.hide()
                w.deleteLater()
        self._rows = []
        self._at = -1

    def _add_rows(self, hits):
        for hit in hits:
            row = _ResultRow(hit.feature, self)
            row.clicked.connect(
                lambda _c=False, f=hit.feature: self.chosen.emit(f))
            self._col.addWidget(row)
            self._rows.append(row)

    def show_results(self, results: Results):
        self._clear()
        self._add_rows(results.direct)
        if results.guesses:
            self._col.addWidget(QLabel(results.heading, self,
                                       objectName="searchHeading"))
            self._add_rows(results.guesses)
        if not self._rows:
            self._col.addWidget(QLabel(
                "No feature matches \"%s\"" % results.query, self,
                objectName="searchEmpty"))
        self.move_to(0)
        self.fit()

    def fit(self):
        """Size to the rows. A widget added to a list that is already on
        screen is only shown on the next pass of the event loop, and until
        then the layout does not count it, so they are shown here first."""
        for i in range(self._col.count()):
            w = self._col.itemAt(i).widget()
            if w is not None:
                w.show()
        self._col.activate()
        self.setFixedHeight(self._col.sizeHint().height())

    def move_by(self, delta: int):
        if self._rows:
            self.move_to((self._at + delta) % len(self._rows))

    def move_to(self, index: int):
        self._at = index if 0 <= index < len(self._rows) else -1
        for i, row in enumerate(self._rows):
            row.set_current(i == self._at)


class _ClickAway(QObject):
    """Closes the list on a click anywhere outside it. Installed on the
    application only while the list is open."""

    def __init__(self, owner):
        super().__init__(owner)
        self._owner = owner

    def eventFilter(self, _obj, event):
        try:
            if event.type() == QEvent.Type.MouseButtonPress:
                self._owner._clicked_at(event.globalPosition().toPoint())
        except (RuntimeError, AttributeError):
            pass                # the window is being torn down
        return False


class FeatureSearch(QObject):
    """Ties the field, the list and the window together."""

    def __init__(self, box: SearchBox, ui, host: QWidget):
        super().__init__(host)
        self._box = box
        self._ui = ui
        self._host = host
        self._index = None
        self._popup = SearchPopup(host)
        self._away = _ClickAway(self)
        self._watching = False

        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(90)
        self._timer.timeout.connect(self._run)

        box.textChanged.connect(self._queue)
        box.step.connect(self._popup.move_by)
        box.accept.connect(self._accept)
        box.dismiss.connect(self.close)
        box.focused.connect(self._on_focus)
        self._popup.chosen.connect(self.go)

    # --- public ------------------------------------------------------

    def focus(self):
        """Ctrl+K: put the cursor in the field with its text selected."""
        if not self._box.isVisible():
            return
        self._box.setFocus(Qt.FocusReason.ShortcutFocusReason)
        self._box.selectAll()

    def close(self):
        """Empty the field, hide the list, hand focus back to the page."""
        self._timer.stop()
        self._box.blockSignals(True)
        self._box.clear()
        self._box.blockSignals(False)
        self._hide()
        self._box.clearFocus()

    def search(self, text: str) -> Results:
        if self._index is None:
            self._index = search_index.build(self._ui)
        return self._index.search(text)

    def go(self, feature):
        self.close()
        if feature is not None:
            search_index.reveal(self._ui, feature)

    def reposition(self):
        if self._popup.isVisible():
            self._place()

    # --- internals ---------------------------------------------------

    def _queue(self, _text: str = ""):
        self._timer.start()

    def _on_focus(self, on: bool):
        if on:
            # Pages rebuild parts of themselves, so read them afresh each
            # time the field is entered rather than trusting an old list.
            self._index = search_index.build(self._ui)
            if self._box.text().strip():
                self._run()
        else:
            self._hide()

    def _run(self):
        text = self._box.text().strip()
        if len(text) < 2 or not self._box.hasFocus():
            self._hide()
            return
        self._popup.show_results(self.search(text))
        self._place()
        self._popup.show()
        self._popup.raise_()
        self._watch(True)

    def _accept(self):
        if self._timer.isActive():
            self._timer.stop()
            self._run()
        feature = self._popup.current() if self._popup.isVisible() else None
        if feature is not None:
            self.go(feature)

    def _place(self):
        box, host = self._box, self._host
        origin = box.mapTo(host, QPoint(0, box.height() + 4))
        width = max(box.width(), 460)
        x = max(Sizing.SPACE_SM,
                min(origin.x() - (width - box.width()) // 2,
                    host.width() - width - Sizing.SPACE_SM))
        self._popup.setFixedWidth(min(width, host.width() - 2 * Sizing.SPACE_SM))
        self._popup.fit()
        self._popup.move(x, origin.y())

    def _hide(self):
        self._popup.hide()
        self._watch(False)

    def _watch(self, on: bool):
        app = QApplication.instance()
        if app is None or on == self._watching:
            return
        self._watching = on
        if on:
            app.installEventFilter(self._away)
        else:
            app.removeEventFilter(self._away)

    def _clicked_at(self, point):
        for w in (self._box, self._popup):
            if QRect(w.mapToGlobal(QPoint(0, 0)), w.size()).contains(point):
                return
        self._hide()
        self._box.clearFocus()
