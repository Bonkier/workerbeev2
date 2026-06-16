# SPDX-License-Identifier: GPL-3.0-or-later
"""Reusable building blocks for the v2 main UI."""

from PySide6.QtCore import (
    Property, QEasingCurve, QParallelAnimationGroup, QPoint,
    QPropertyAnimation, QRect, QRectF, QSize, Qt, Signal,
)
from PySide6.QtGui import QColor, QFont, QKeySequence, QPainter, QPen
from PySide6.QtWidgets import (
    QAbstractButton, QFrame, QGraphicsDropShadowEffect,
    QGraphicsOpacityEffect, QGridLayout, QHBoxLayout, QLabel, QLayout,
    QLineEdit, QListWidget, QListWidgetItem, QPushButton, QScrollArea,
    QSizePolicy, QStackedWidget, QStyle, QStyledItemDelegate,
    QVBoxLayout, QWidget,
)

from .theme import Colors, Fonts, Motion, Sizing


# Once-per-feature W.I.P. notice; suppressed after the first call per session.
_PLACEHOLDER_SEEN: set[str] = set()


def show_placeholder_notice(parent: QWidget | None, feature: str,
                            blurb: str | None = None) -> None:
    """Show a "Work in progress" notice the first time `feature` is poked."""
    if feature in _PLACEHOLDER_SEEN:
        return
    _PLACEHOLDER_SEEN.add(feature)
    # Deferred import keeps widgets.py importable headless.
    from PySide6.QtWidgets import QMessageBox
    body = blurb or (
        f"{feature} is a work-in-progress placeholder. The UI is in "
        "place so you can capture your preferences now, but the "
        "macro-side logic ships in a follow-up release. Anything you "
        "set here will be persisted and picked up automatically once "
        "the backend lands."
    )
    box = QMessageBox(parent)
    box.setIcon(QMessageBox.Icon.Information)
    box.setWindowTitle("Work in progress")
    from .copy import PLACEHOLDER_NOTICE_TEMPLATE
    box.setText(PLACEHOLDER_NOTICE_TEMPLATE.format(feature=feature))
    box.setInformativeText(body)
    box.setStandardButtons(QMessageBox.StandardButton.Ok)
    box.exec()


def _lerp_color(a: QColor, b: QColor, t: float) -> QColor:
    t = max(0.0, min(1.0, t))
    return QColor(
        int(a.red() + (b.red() - a.red()) * t),
        int(a.green() + (b.green() - a.green()) * t),
        int(a.blue() + (b.blue() - a.blue()) * t),
        int(a.alpha() + (b.alpha() - a.alpha()) * t),
    )


class FlowLayout(QLayout):
    """Wrapping left-to-right layout used for chip flows."""

    def __init__(self, parent=None, spacing=6):
        super().__init__(parent)
        self._items = []
        self.setContentsMargins(0, 0, 0, 0)
        self.setSpacing(spacing)

    def addItem(self, item):
        self._items.append(item)

    def count(self):
        return len(self._items)

    def itemAt(self, index):
        if 0 <= index < len(self._items):
            return self._items[index]
        return None

    def takeAt(self, index):
        if 0 <= index < len(self._items):
            return self._items.pop(index)
        return None

    def expandingDirections(self):
        return Qt.Orientation(0)

    def hasHeightForWidth(self):
        return True

    def heightForWidth(self, width):
        return self._do_layout(QRect(0, 0, width, 0), True)

    def setGeometry(self, rect):
        super().setGeometry(rect)
        self._do_layout(rect, False)

    def sizeHint(self):
        return self.minimumSize()

    def minimumSize(self):
        size = QSize()
        for item in self._items:
            size = size.expandedTo(item.minimumSize())
        return size + QSize(2, 2)

    def _do_layout(self, rect, test_only):
        x, y = rect.x(), rect.y()
        line_height = 0
        spacing = self.spacing()
        for item in self._items:
            hint = item.sizeHint()
            next_x = x + hint.width() + spacing
            if next_x - spacing > rect.right() and line_height > 0:
                x = rect.x()
                y = y + line_height + spacing
                next_x = x + hint.width() + spacing
                line_height = 0
            if not test_only:
                item.setGeometry(QRect(QPoint(x, y), hint))
            x = next_x
            line_height = max(line_height, hint.height())
        return y + line_height - rect.y()


# Opaque page backdrop for the slide transition (matches the themed window).
def _page_gradient_qss() -> str:
    return ("background-color: qlineargradient(x1:0, y1:0, x2:0, y2:1, "
            f"stop:0 {Colors.BG_WINDOW_TOP}, stop:0.45 {Colors.BG_WINDOW_MID}, "
            f"stop:1 {Colors.BG_WINDOW_BOT});")


class AnimatedStack(QStackedWidget):
    """QStackedWidget with a horizontal slide between pages. Animates two
    snapshot overlays so the layout is never fought and text stays sharp."""

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self._group: QParallelAnimationGroup | None = None
        self._overlays: list = []
        # Backdrop QSS for the slide snapshots. None = themed page gradient;
        # override via set_surface when the stack lives inside a Card.
        self._surface_qss = None

    def set_surface(self, qss: str):
        """Override the snapshot backdrop QSS."""
        self._surface_qss = qss

    # setCurrentWidget calls setCurrentIndex in C++ - reroute it.
    def setCurrentWidget(self, widget):
        self.setCurrentIndex(self.indexOf(widget))

    def setCurrentIndex(self, index: int):
        if (index < 0 or index == self.currentIndex()
                or not self.isVisible() or self.currentWidget() is None):
            self._cleanup()
            return super().setCurrentIndex(index)
        self._push(index)

    def _push(self, index: int):
        self._cleanup()
        cur = self.currentWidget()
        old_idx = self.currentIndex()
        direction = 1 if index > old_idx else -1
        w, h = self.width(), self.height()

        old_pix = cur.grab()
        super().setCurrentIndex(index)
        nxt = self.currentWidget()
        new_pix = nxt.grab()

        old_lbl = self._make_overlay(old_pix, 0, w, h)
        new_lbl = self._make_overlay(new_pix, direction * w, w, h)
        self._overlays = [old_lbl, new_lbl]

        a_old = QPropertyAnimation(old_lbl, b"pos", self)
        a_old.setDuration(Motion.NORMAL)
        a_old.setStartValue(QPoint(0, 0))
        a_old.setEndValue(QPoint(-direction * w, 0))
        a_old.setEasingCurve(QEasingCurve.Type.OutCubic)

        a_new = QPropertyAnimation(new_lbl, b"pos", self)
        a_new.setDuration(Motion.NORMAL)
        a_new.setStartValue(QPoint(direction * w, 0))
        a_new.setEndValue(QPoint(0, 0))
        a_new.setEasingCurve(QEasingCurve.Type.OutCubic)

        self._group = QParallelAnimationGroup(self)
        self._group.addAnimation(a_old)
        self._group.addAnimation(a_new)
        self._group.finished.connect(self._cleanup)
        self._group.start()

    def _make_overlay(self, pix, x: int, w: int, h: int) -> QLabel:
        lbl = QLabel(self)
        lbl.setStyleSheet(self._surface_qss or _page_gradient_qss())
        lbl.setPixmap(pix)
        lbl.setGeometry(x, 0, w, h)
        lbl.show()
        lbl.raise_()
        return lbl

    def _cleanup(self):
        if self._group is not None:
            self._group.stop()
            self._group = None
        for lbl in self._overlays:
            lbl.hide()
            lbl.deleteLater()
        self._overlays = []

    def resizeEvent(self, event):
        super().resizeEvent(event)
        # A resize mid-slide would leave stale overlays; finish now.
        if self._overlays:
            self._cleanup()


class Section(QWidget):
    """Vertical container with an uppercase label header. Add children to
    `section.body`."""

    def __init__(self, label: str, parent: QWidget | None = None,
                 trailing: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("section")
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(Sizing.SPACE_SM)

        head = QHBoxLayout()
        head.setContentsMargins(0, 0, 0, 0)
        head.setSpacing(Sizing.SPACE_SM)
        title = QLabel(label, self)
        title.setObjectName("sectionLabel")
        head.addWidget(title)
        head.addStretch(1)
        if trailing is not None:
            head.addWidget(trailing)
        outer.addLayout(head)

        self.body = QVBoxLayout()
        self.body.setContentsMargins(0, 0, 0, 0)
        self.body.setSpacing(Sizing.SPACE_XS)
        outer.addLayout(self.body)


class Card(QFrame):
    """Elevated surface panel: lighter background, soft border, rounded
    corners, drop shadow. Add content to `self.body`."""

    def __init__(self, title: str | None = None,
                 parent: QWidget | None = None,
                 trailing: QWidget | None = None,
                 padding: int | None = None,
                 fill: bool = False):
        super().__init__(parent)
        self.setObjectName("card")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)

        pad = Sizing.SPACE_LG if padding is None else padding
        outer = QVBoxLayout(self)
        outer.setContentsMargins(pad, pad, pad, pad)
        outer.setSpacing(Sizing.SPACE_MD)

        if title is not None:
            head = QHBoxLayout()
            head.setContentsMargins(0, 0, 0, 0)
            head.setSpacing(Sizing.SPACE_SM)
            lbl = QLabel(title, self)
            lbl.setObjectName("sectionLabel")
            head.addWidget(lbl)
            head.addStretch(1)
            if trailing is not None:
                head.addWidget(trailing)
            outer.addLayout(head)

        self.body = QVBoxLayout()
        self.body.setContentsMargins(0, 0, 0, 0)
        self.body.setSpacing(Sizing.SPACE_SM)
        # fill=True lets the body soak the card's extra height.
        outer.addLayout(self.body, 1 if fill else 0)
        # Keep content pinned to the top when the card stretches taller.
        if not fill:
            outer.addStretch(1)

        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(26)
        shadow.setXOffset(0)
        shadow.setYOffset(6)
        shadow.setColor(QColor(0, 0, 0, 120))
        self.setGraphicsEffect(shadow)


class HRule(QFrame):
    """Thin horizontal divider."""

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("hrule")
        self.setFixedHeight(1)


class StatLine(QWidget):
    """Single 'label ... value' row."""

    def __init__(self, label: str, value: str, accent: bool = False,
                 parent: QWidget | None = None):
        super().__init__(parent)
        row = QHBoxLayout(self)
        row.setContentsMargins(0, Sizing.SPACE_XS, 0, Sizing.SPACE_XS)
        row.setSpacing(Sizing.SPACE_LG)

        self._label = QLabel(label, self)
        self._label.setObjectName("statRowLabel")
        row.addWidget(self._label, stretch=1)

        self._value = QLabel(value, self)
        self._value.setObjectName("statRowValueAccent" if accent
                                  else "statRowValue")
        self._value.setAlignment(
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
        )
        row.addWidget(self._value)

    def set_value(self, value: str):
        self._value.setText(value)


class StatTiles(QWidget):
    """Horizontal stat strip: each cell is a value over an uppercase label,
    separated by thin dividers. Pass (label, value) or (label, value, accent)."""

    def __init__(self, stats, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("statTiles")
        row = QHBoxLayout(self)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(0)
        self._values: dict[str, QLabel] = {}

        for i, spec in enumerate(stats):
            label, value = spec[0], spec[1]
            accent = spec[2] if len(spec) > 2 else False
            if i > 0:
                div = QFrame(self)
                div.setObjectName("statTileDivider")
                div.setFixedWidth(1)
                row.addWidget(div)

            cell = QWidget(self)
            cell.setObjectName("statTile")
            cv = QVBoxLayout(cell)
            left = 0 if i == 0 else Sizing.SPACE_XL
            cv.setContentsMargins(left, Sizing.SPACE_XS,
                                  Sizing.SPACE_XL, Sizing.SPACE_XS)
            cv.setSpacing(Sizing.SPACE_XXS)

            val = QLabel(value, cell)
            val.setObjectName("statTileValueAccent" if accent
                              else "statTileValue")
            cv.addWidget(val)

            lab = QLabel(label.upper(), cell)
            lab.setObjectName("statTileLabel")
            cv.addWidget(lab)

            row.addWidget(cell, stretch=1)
            self._values[label] = val

    def set_value(self, label: str, value: str):
        if label in self._values:
            self._values[label].setText(value)


class PrimaryButton(QPushButton):
    """Yellow accent CTA button."""

    def __init__(self, text: str, parent: QWidget | None = None):
        super().__init__(text, parent)
        self.setObjectName("primaryCta")
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setMinimumHeight(30)


class GhostButton(QPushButton):
    """Outlined secondary action button."""

    def __init__(self, text: str, parent: QWidget | None = None):
        super().__init__(text, parent)
        self.setObjectName("ghostBtn")
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setMinimumHeight(30)


class LinkButton(QPushButton):
    """Inline text-only link button (accent on hover)."""

    def __init__(self, text: str, parent: QWidget | None = None):
        super().__init__(text, parent)
        self.setObjectName("linkBtn")
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFlat(True)


class KeyCaptureButton(QPushButton):
    """Click to record a hotkey. Esc cancels, Backspace/Delete clears."""

    binding_changed = Signal(str)

    def __init__(self, binding: str = "", parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("keyCapture")
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setMinimumWidth(140)
        self._binding = binding
        self._capturing = False
        self._render()
        self.clicked.connect(self._start_capture)

    def _start_capture(self):
        self._capturing = True
        self.setText("Press keys…")
        self.setProperty("capturing", "true")
        self.style().unpolish(self)
        self.style().polish(self)
        self.setFocus()

    def _stop_capture(self):
        self._capturing = False
        self.setProperty("capturing", "false")
        self.style().unpolish(self)
        self.style().polish(self)
        self._render()

    def _render(self):
        self.setText(self._binding or "Unbound")

    def binding(self) -> str:
        return self._binding

    def set_binding(self, binding: str):
        self._binding = binding
        self._render()

    def keyPressEvent(self, event):
        if not self._capturing:
            return super().keyPressEvent(event)
        key = event.key()
        if key == Qt.Key.Key_Escape:
            self._stop_capture()
            return
        if key in (Qt.Key.Key_Backspace, Qt.Key.Key_Delete):
            self._binding = ""
            self._stop_capture()
            self.binding_changed.emit(self._binding)
            return
        # Need a non-modifier key.
        if key in (Qt.Key.Key_Control, Qt.Key.Key_Shift, Qt.Key.Key_Alt,
                   Qt.Key.Key_Meta):
            return
        mods = event.modifiers()
        parts = []
        if mods & Qt.KeyboardModifier.ControlModifier:
            parts.append("Ctrl")
        if mods & Qt.KeyboardModifier.AltModifier:
            parts.append("Alt")
        if mods & Qt.KeyboardModifier.ShiftModifier:
            parts.append("Shift")
        key_name = QKeySequence(key).toString()
        if key_name:
            parts.append(key_name)
        self._binding = "+".join(parts)
        self._stop_capture()
        self.binding_changed.emit(self._binding)


class PageHeader(QWidget):
    """Page title on the left, optional action buttons on the right."""

    def __init__(self, title: str, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("pageHeader")

        row = QHBoxLayout(self)
        row.setContentsMargins(0, 0, 0, Sizing.SPACE_LG)
        row.setSpacing(Sizing.SPACE_MD)

        self._title = QLabel(title, self)
        self._title.setObjectName("pageTitle")
        row.addWidget(self._title)
        row.addStretch(1)

        self._actions_row = QHBoxLayout()
        self._actions_row.setSpacing(Sizing.SPACE_SM)
        row.addLayout(self._actions_row)

    def add_action(self, widget: QWidget):
        self._actions_row.addWidget(widget)


class ActivityRow(QFrame):
    """Hover-highlighted row: status dot + title + subtitle + meta."""

    def __init__(self, status_color: str, title: str, subtitle: str,
                 meta: str, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("activityRow")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

        row = QHBoxLayout(self)
        row.setContentsMargins(
            Sizing.SPACE_SM, Sizing.SPACE_SM,
            Sizing.SPACE_SM, Sizing.SPACE_SM,
        )
        row.setSpacing(Sizing.SPACE_MD)

        dot = QLabel("●", self)
        dot.setObjectName("activityDot")
        dot.setFixedWidth(12)
        dot.setStyleSheet(f"color: {status_color};")
        row.addWidget(dot)

        text_col = QVBoxLayout()
        text_col.setSpacing(2)
        title_lbl = QLabel(title, self)
        title_lbl.setObjectName("activityTitle")
        text_col.addWidget(title_lbl)
        sub_lbl = QLabel(subtitle, self)
        sub_lbl.setObjectName("activitySubtitle")
        text_col.addWidget(sub_lbl)
        row.addLayout(text_col, stretch=1)

        meta_lbl = QLabel(meta, self)
        meta_lbl.setObjectName("activityMeta")
        meta_lbl.setAlignment(
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
        )
        row.addWidget(meta_lbl)


def windows_logo_pixmap(size: int = 18) -> "QPixmap":
    """Painter-drawn Windows 4-pane logo (no PNG/SVG asset needed)."""
    from PySide6.QtCore import QRectF, Qt as _Qt
    from PySide6.QtGui import QColor, QPainter, QPixmap

    pix = QPixmap(size, size)
    pix.fill(_Qt.GlobalColor.transparent)
    p = QPainter(pix)
    p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    p.setPen(_Qt.PenStyle.NoPen)
    p.setBrush(QColor("#00A4EF"))                       # Microsoft blue
    gap = max(1.0, size / 14.0)
    pane = (size - gap) / 2.0
    p.drawRect(QRectF(0,            0,            pane, pane))
    p.drawRect(QRectF(pane + gap,   0,            pane, pane))
    p.drawRect(QRectF(0,            pane + gap,   pane, pane))
    p.drawRect(QRectF(pane + gap,   pane + gap,   pane, pane))
    p.end()
    return pix


class SettingRow(QWidget):
    """Preference row: title + control on one line, description below.
    `leading_icon` flags rows that reach outside the macro."""

    def __init__(self, title: str, subtitle: str, control: QWidget,
                 parent: QWidget | None = None,
                 leading_icon=None):
        super().__init__(parent)
        self.setObjectName("settingRow")
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, Sizing.SPACE_SM, 0, Sizing.SPACE_SM)
        outer.setSpacing(2)

        title_row = QHBoxLayout()
        title_row.setContentsMargins(0, 0, 0, 0)
        title_row.setSpacing(Sizing.SPACE_LG)

        if leading_icon is not None:
            icon_lbl = QLabel(self)
            icon_lbl.setPixmap(leading_icon)
            icon_lbl.setFixedSize(leading_icon.size())
            icon_lbl.setAlignment(Qt.AlignmentFlag.AlignVCenter)
            title_row.addWidget(icon_lbl,
                                alignment=Qt.AlignmentFlag.AlignVCenter)
            # Tighter gap so icon+title read as one unit.
            title_row.setSpacing(Sizing.SPACE_SM)

        title_lbl = QLabel(title, self)
        title_lbl.setObjectName("settingTitle")
        title_row.addWidget(title_lbl, stretch=1)
        title_row.addWidget(control, alignment=Qt.AlignmentFlag.AlignVCenter)
        outer.addLayout(title_row)

        if subtitle:
            sub_lbl = QLabel(subtitle, self)
            sub_lbl.setObjectName("settingSubtitle")
            sub_lbl.setWordWrap(True)
            outer.addWidget(sub_lbl)


class Toggle(QAbstractButton):
    """Sliding switch: painted track + animated circular thumb."""

    _W, _H, _MARGIN = 46, 26, 3

    def __init__(self, default: bool = False,
                 parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("toggle")
        self.setCheckable(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFixedSize(self._W, self._H)

        self._pos = 1.0 if default else 0.0
        self.setChecked(default)

        # Monochrome on-state; accent is reserved for primary actions.
        self._track_off = QColor(Colors.BG_HOVER)
        self._track_on = QColor("#d8d8dc")
        self._thumb_off = QColor(Colors.TEXT_TERTIARY)
        self._thumb_on = QColor(Colors.BG_BASE)

        self._anim = QPropertyAnimation(self, b"thumbPos", self)
        self._anim.setDuration(160)
        self._anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self.toggled.connect(self._animate)

    def refresh_theme(self):
        """Re-read theme colours after a live theme change."""
        self._track_off = QColor(Colors.BG_HOVER)
        self._thumb_off = QColor(Colors.TEXT_TERTIARY)
        self._thumb_on = QColor(Colors.BG_BASE)
        self.update()

    def _animate(self, checked: bool):
        self._anim.stop()
        self._anim.setStartValue(self._pos)
        self._anim.setEndValue(1.0 if checked else 0.0)
        self._anim.start()

    def _get_pos(self) -> float:
        return self._pos

    def _set_pos(self, value: float):
        self._pos = value
        self.update()

    thumbPos = Property(float, _get_pos, _set_pos)

    def paintEvent(self, _event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setPen(Qt.PenStyle.NoPen)

        radius = self._H / 2.0
        track = _lerp_color(self._track_off, self._track_on, self._pos)
        p.setBrush(track)
        p.drawRoundedRect(QRectF(0, 0, self._W, self._H), radius, radius)

        thumb_d = self._H - 2 * self._MARGIN
        travel = self._W - 2 * self._MARGIN - thumb_d
        x = self._MARGIN + self._pos * travel
        thumb = _lerp_color(self._thumb_off, self._thumb_on, self._pos)
        p.setBrush(thumb)
        p.drawEllipse(QRectF(x, self._MARGIN, thumb_d, thumb_d))


class IconlessTabBar(QWidget):
    """Horizontal text-only tab strip; active tab has a sliding underline."""

    selection_changed = Signal(str)

    def __init__(self, tabs, default=None, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("iconlessTabBar")
        self._buttons: dict[str, QPushButton] = {}
        self._current: str | None = None
        self._underline = QRectF()

        self._row = QHBoxLayout(self)
        self._row.setContentsMargins(0, 0, 0, 0)
        self._row.setSpacing(0)
        self._row.addStretch(1)

        self._anim = QPropertyAnimation(self, b"underlineGeom", self)
        self._anim.setDuration(Motion.QUICK)
        self._anim.setEasingCurve(QEasingCurve.Type.OutCubic)

        self.set_tabs(tabs, default)

    def set_tabs(self, tabs, default=None):
        """Rebuild the tab buttons (for dynamic tab sets)."""
        for btn in self._buttons.values():
            self._row.removeWidget(btn)
            btn.deleteLater()
        self._buttons = {}

        for i, label in enumerate(tabs):
            btn = QPushButton(label, self)
            btn.setObjectName("tabBtn")
            btn.setCheckable(True)
            btn.setAutoExclusive(True)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.clicked.connect(lambda _c=False, k=label: self._emit(k))
            self._row.insertWidget(i, btn)  # before trailing stretch
            self._buttons[label] = btn

        target = default if default in self._buttons else (tabs[0] if tabs else None)
        if target is not None:
            self._buttons[target].setChecked(True)
            self._current = target

    def _emit(self, label: str):
        self._current = label
        self._animate_to(label)
        self.selection_changed.emit(label)

    def _underline_rect(self, label: str) -> QRectF:
        b = self._buttons[label]
        g = b.geometry()
        return QRectF(g.x(), g.bottom() - 1, g.width(), 2)

    def _animate_to(self, label: str):
        if label not in self._buttons:
            return
        self._anim.stop()
        self._anim.setStartValue(self._underline)
        self._anim.setEndValue(self._underline_rect(label))
        self._anim.start()

    def _get_underline(self) -> QRectF:
        return self._underline

    def _set_underline(self, r: QRectF):
        self._underline = r
        self.update()

    underlineGeom = Property(QRectF, _get_underline, _set_underline)

    def showEvent(self, event):
        super().showEvent(event)
        if self._current and self._current in self._buttons:
            self._underline = self._underline_rect(self._current)
            self.update()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if (self._current and self._current in self._buttons
                and self._anim.state() != QPropertyAnimation.State.Running):
            self._underline = self._underline_rect(self._current)
            self.update()

    def paintEvent(self, _event):
        if self._underline.isNull():
            return
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(Colors.ACCENT))
        p.drawRoundedRect(self._underline, 1, 1)

    def selected(self) -> str:
        for label, btn in self._buttons.items():
            if btn.isChecked():
                return label
        return ""


class Segmented(QWidget):
    """Mutually-exclusive selector: rounded track + sliding highlight pill."""

    selection_changed = Signal(str)

    _INSET = 3  # gap between track edge and pill

    def __init__(self, options, default=None, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("segmented")
        # Fixed size policy so neighbours can't squeeze button labels off.
        self.setSizePolicy(QSizePolicy.Policy.Fixed,
                           QSizePolicy.Policy.Fixed)
        row = QHBoxLayout(self)
        row.setContentsMargins(self._INSET, self._INSET,
                               self._INSET, self._INSET)
        row.setSpacing(0)
        self._buttons: dict[str, QPushButton] = {}
        self._current: str | None = None
        self._pill = QRectF()

        for label in options:
            btn = QPushButton(label, self)
            btn.setObjectName("segmentedItem")
            btn.setCheckable(True)
            btn.setAutoExclusive(True)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.clicked.connect(lambda _c=False, k=label: self._on_click(k))
            row.addWidget(btn)
            self._buttons[label] = btn

        self._anim = QPropertyAnimation(self, b"pillGeom", self)
        self._anim.setDuration(Motion.NORMAL)
        self._anim.setEasingCurve(QEasingCurve.Type.OutCubic)

        target = default if default in self._buttons else (
            options[0] if options else None)
        if target is not None:
            self._buttons[target].setChecked(True)
            self._current = target

    def _on_click(self, label: str):
        if label == self._current:
            return
        self._current = label
        self._animate_to(label)
        self.selection_changed.emit(label)

    def _pill_rect(self, label: str) -> QRectF:
        return QRectF(self._buttons[label].geometry())

    def _animate_to(self, label: str):
        if label not in self._buttons:
            return
        self._anim.stop()
        self._anim.setStartValue(self._pill)
        self._anim.setEndValue(self._pill_rect(label))
        self._anim.start()

    def _get_pill(self) -> QRectF:
        return self._pill

    def _set_pill(self, r: QRectF):
        self._pill = r
        self.update()

    pillGeom = Property(QRectF, _get_pill, _set_pill)

    def showEvent(self, event):
        super().showEvent(event)
        if self._current:
            self._pill = self._pill_rect(self._current)
            self.update()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if (self._current
                and self._anim.state() != QPropertyAnimation.State.Running):
            self._pill = self._pill_rect(self._current)
            self.update()

    def paintEvent(self, _event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setPen(Qt.PenStyle.NoPen)

        # Track.
        track = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        p.setBrush(QColor(Colors.BG_OVERLAY))
        p.drawRoundedRect(track, track.height() / 2.0, track.height() / 2.0)

        # Sliding pill.
        if not self._pill.isNull():
            p.setBrush(QColor("#e8e8ea"))
            p.drawRoundedRect(self._pill, self._pill.height() / 2.0,
                              self._pill.height() / 2.0)

    def selected(self) -> str:
        for label, btn in self._buttons.items():
            if btn.isChecked():
                return label
        return ""

    def set_selected(self, label: str):
        if label in self._buttons and label != self._current:
            self._buttons[label].setChecked(True)
            self._current = label
            self._animate_to(label)

    def set_interactive(self, on: bool):
        """Enable at full opacity, or disable and dim."""
        self.setEnabled(bool(on))
        if on:
            self.setGraphicsEffect(None)
        else:
            eff = QGraphicsOpacityEffect(self)
            eff.setOpacity(0.38)
            self.setGraphicsEffect(eff)


class _AnimatedChip(QAbstractButton):
    """Chip that fades between colour states. `_go(bg, bd, fg, bold)`
    animates; `_set(...)` snaps instantly."""

    _HPAD = 14
    _VPAD = 4
    _MIN_H = 26

    def __init__(self, text: str = "", parent: QWidget | None = None):
        super().__init__(parent)
        self.setText(text)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        f = self.font()
        f.setPointSize(Fonts.SIZE_SM)
        self.setFont(f)
        self._hover = False
        self._bg = QColor(Colors.BG_OVERLAY)
        self._bd = QColor(Colors.BORDER_SUBTLE)
        self._fg = QColor(Colors.TEXT_SECONDARY)
        self._bold = False
        self._from = (QColor(self._bg), QColor(self._bd), QColor(self._fg))
        self._to = self._from
        self._anim = QPropertyAnimation(self, b"chipBlend", self)
        self._anim.setDuration(150)
        self._anim.setEasingCurve(QEasingCurve.Type.OutCubic)

    def _go(self, bg, bd, fg, bold: bool = False):
        self._from = (QColor(self._bg), QColor(self._bd), QColor(self._fg))
        self._to = (QColor(bg), QColor(bd), QColor(fg))
        self._bold = bold
        self._anim.stop()
        self._anim.setStartValue(0.0)
        self._anim.setEndValue(1.0)
        self._anim.start()

    def _set(self, bg, bd, fg, bold: bool = False):
        self._bg, self._bd, self._fg = QColor(bg), QColor(bd), QColor(fg)
        self._from = self._to = (QColor(bg), QColor(bd), QColor(fg))
        self._bold = bold
        self.update()

    def _current_colors(self):
        """Subclasses return current (bg, bd, fg, bold) for theme refresh."""
        return None

    def refresh_theme(self):
        cols = self._current_colors()
        if cols:
            self._set(*cols)

    def _get_blend(self) -> float:
        return 0.0

    def _set_blend(self, t: float):
        self._bg = _lerp_color(self._from[0], self._to[0], t)
        self._bd = _lerp_color(self._from[1], self._to[1], t)
        self._fg = _lerp_color(self._from[2], self._to[2], t)
        self.update()

    chipBlend = Property(float, _get_blend, _set_blend)

    def enterEvent(self, event):
        self._hover = True
        self.update()
        super().enterEvent(event)

    def leaveEvent(self, event):
        self._hover = False
        self.update()
        super().leaveEvent(event)

    def sizeHint(self) -> QSize:
        fm = self.fontMetrics()
        return QSize(fm.horizontalAdvance(self.text()) + 2 * self._HPAD + 2,
                     max(self._MIN_H, fm.height() + 2 * self._VPAD))

    def paintEvent(self, _event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = QRectF(0.5, 0.5, self.width() - 1, self.height() - 1)
        radius = 0.0  # sharp corners
        bg = QColor(self._bg)
        bd = QColor(self._bd)
        if self._hover:
            bg = bg.lighter(118)
            bd = bd.lighter(130)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(bg)
        p.drawRoundedRect(r, radius, radius)
        pen = QPen(bd)
        pen.setWidthF(1.0)
        p.setPen(pen)
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawRoundedRect(r, radius, radius)
        f = self.font()
        f.setWeight(QFont.Weight.DemiBold if self._bold
                    else QFont.Weight.Medium)
        p.setFont(f)
        p.setPen(self._fg)
        p.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, self.text())


class _CheckChip(_AnimatedChip):
    """Checkable animated chip - fades to the 'on' colours when checked."""

    @staticmethod
    def _off_cols():
        return (Colors.BG_OVERLAY, Colors.BORDER_SUBTLE,
                Colors.TEXT_SECONDARY, False)

    @staticmethod
    def _on_cols():
        return (Colors.BG_HOVER, Colors.TEXT_TERTIARY, Colors.TEXT_PRIMARY, True)

    def __init__(self, text: str, parent: QWidget | None = None):
        super().__init__(text, parent)
        self.setCheckable(True)
        self._set(*self._off_cols())
        self.toggled.connect(self._on_toggle)

    def _on_toggle(self, on: bool):
        self._go(*(self._on_cols() if on else self._off_cols()))

    def _current_colors(self):
        return self._on_cols() if self.isChecked() else self._off_cols()


class _OrderChip(_AnimatedChip):
    """Chip used by ClickOrderGrid. Behaves like a non-checkable button
    that the grid drives between off (plain name) and on (numbered) by
    setting the label text + animating to the on/off colours from
    _CheckChip's palette. The grid handles the ordinal renumbering."""

    def __init__(self, name: str, parent: QWidget | None = None):
        super().__init__(name, parent)
        self._name = name
        self._rank: int | None = None
        self._set(*_CheckChip._off_cols())

    def name(self) -> str:
        return self._name

    def rank(self) -> int | None:
        return self._rank

    def set_rank(self, rank: int | None):
        """rank=None deselects, any positive int turns the chip on with
        a leading 'N. ' prefix on the label."""
        self._rank = rank
        if rank is None:
            self.setText(self._name)
            self._go(*_CheckChip._off_cols())
        else:
            self.setText(f"{rank}. {self._name}")
            self._go(*_CheckChip._on_cols())

    def _current_colors(self):
        return (_CheckChip._on_cols() if self._rank is not None
                else _CheckChip._off_cols())


class ClickOrderGrid(QWidget):
    """Fixed grid of name chips that records the click order. Each chip
    is initially off; clicking an off chip turns it on and assigns the
    next ordinal (1, 2, ...). Clicking an on chip removes it and
    renumbers every higher-ranked chip down by 1 so the order stays
    1..N with no gaps.

    Layout is `rows x cols` (default 2x6). `names` is a flat list filled
    row-major; if it is shorter than rows*cols the remaining cells stay
    empty. `max_picks=None` means no cap; an explicit cap reverts any
    click that would push the count past it."""

    changed = Signal()

    def __init__(self, names, rows: int = 2, cols: int = 6,
                 max_picks: int | None = None,
                 parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("clickOrderGrid")
        self._rows = max(1, int(rows))
        self._cols = max(1, int(cols))
        self._max = max_picks if max_picks is None else max(0, int(max_picks))
        # Preserve insertion order so order() walks chips in the same
        # visual layout the grid presents.
        self._chips: dict[str, _OrderChip] = {}
        self._order: list[str] = []
        self._restoring = False  # suppress changed emits during set_order

        grid = QGridLayout(self)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setHorizontalSpacing(Sizing.SPACE_SM)
        grid.setVerticalSpacing(Sizing.SPACE_XS)

        flat = list(names)
        for r in range(self._rows):
            for c in range(self._cols):
                i = r * self._cols + c
                if i >= len(flat):
                    break
                name = flat[i]
                chip = _OrderChip(name, self)
                chip.clicked.connect(lambda _c=False, n=name:
                                     self._toggle(n))
                grid.addWidget(chip, r, c)
                self._chips[name] = chip

    def _toggle(self, name: str):
        chip = self._chips.get(name)
        if chip is None:
            return
        if chip.rank() is not None:
            # ON -> OFF: drop from the order and renumber the rest.
            self._order.remove(name)
            chip.set_rank(None)
            for i, n in enumerate(self._order):
                self._chips[n].set_rank(i + 1)
        else:
            # OFF -> ON, but respect the cap by reverting silently.
            if self._max is not None and len(self._order) >= self._max:
                return
            self._order.append(name)
            chip.set_rank(len(self._order))
        if not self._restoring:
            self.changed.emit()

    def order(self) -> list:
        """Picked names in click order (length 0..max_picks)."""
        return list(self._order)

    def set_order(self, names):
        """Clear, then re-click each name in the given order. Unknown
        names are skipped; anything past max_picks (if set) is dropped.
        Programmatic - does not emit `changed`."""
        self._restoring = True
        try:
            self.clear()
            for n in names or []:
                if n in self._chips and self._chips[n].rank() is None:
                    if self._max is not None and len(self._order) >= self._max:
                        break
                    self._toggle(n)
        finally:
            self._restoring = False

    def clear(self):
        """Deselect every chip. Programmatic - does not emit `changed`."""
        for n in list(self._order):
            self._chips[n].set_rank(None)
        self._order.clear()


class ChipList(QWidget):
    """Horizontal list of pill chips for tag-like selections. Click a
    chip to toggle inclusion. Used for pack priority/avoid and the
    keywordless gift list."""

    selection_changed = Signal(list)

    def __init__(self, items, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("chipList")
        self._buttons: dict[str, QPushButton] = {}

        row = QHBoxLayout(self)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(Sizing.SPACE_XS)
        for label in items:
            btn = _CheckChip(label, self)
            btn.toggled.connect(self._notify)
            row.addWidget(btn)
            self._buttons[label] = btn
        row.addStretch(1)

    def _notify(self):
        self.selection_changed.emit(
            [label for label, btn in self._buttons.items() if btn.isChecked()]
        )

    def selected(self) -> list:
        return [label for label, btn in self._buttons.items() if btn.isChecked()]


class _GridChipDelegate(QStyledItemDelegate):
    """Paints a fixed-column OrderedList cell as a rounded chip: a checkbox
    on the left and the label on the right, word-wrapping a long label to a
    second line instead of eliding it. The default list-mode delegate cuts
    names like "1. Don Quixote" to "1. Don ..."; this draws everything by
    hand so it wraps. The look mirrors the #orderedList QSS."""

    def paint(self, painter, option, index):
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        cell = option.rect.adjusted(3, 2, -4, -2)

        checkable = bool(index.flags() & Qt.ItemFlag.ItemIsUserCheckable)
        cs = index.data(Qt.ItemDataRole.CheckStateRole)
        # CheckStateRole comes back as an int (2) or the enum depending on the
        # binding; accept either without converting (int() on some values can
        # fault) so the comparison is reliable.
        checked = cs == Qt.CheckState.Checked or cs == 2
        st = option.state
        hover = bool(st & QStyle.StateFlag.State_MouseOver)
        selected = bool(st & QStyle.StateFlag.State_Selected)

        # Chip body.
        bg = QColor(Colors.BG_OVERLAY if (hover or selected) else Colors.BG_RAISED)
        if selected:
            bd = QColor(Colors.ACCENT)
        elif hover:
            bd = QColor(Colors.BORDER_STRONG)
        else:
            bd = QColor(Colors.BORDER_SUBTLE)
        painter.setPen(QPen(bd, 1))
        painter.setBrush(bg)
        painter.drawRoundedRect(
            QRectF(cell).adjusted(0.5, 0.5, -0.5, -0.5),
            Sizing.RADIUS_SM, Sizing.RADIUS_SM)

        # Checkbox indicator.
        text_left = cell.left() + 12
        if checkable:
            box = QRect(cell.left() + 10, cell.center().y() - 8, 16, 16)
            if checked:
                painter.setPen(QPen(QColor("#d8d8dc"), 1))
                painter.setBrush(QColor("#d8d8dc"))
                painter.drawRoundedRect(box, 4, 4)
                painter.setPen(QPen(QColor(Colors.BG_BASE), 2))
                painter.drawLine(box.left() + 3, box.center().y() + 1,
                                 box.center().x(), box.bottom() - 3)
                painter.drawLine(box.center().x(), box.bottom() - 3,
                                 box.right() - 2, box.top() + 4)
            else:
                painter.setPen(QPen(QColor(Colors.BORDER_STRONG), 1))
                painter.setBrush(QColor(Colors.BG_OVERLAY))
                painter.drawRoundedRect(box, 4, 4)
            text_left = box.right() + 8

        # Label, word-wrapped, vertically centred. Excluded (unchecked)
        # sinners read dimmer so the ticked, ordered ones stand out.
        text_rect = QRect(text_left, cell.top(),
                          cell.right() - text_left - 6, cell.height())
        painter.setPen(QColor(Colors.TEXT_PRIMARY if (checked or not checkable)
                              else Colors.TEXT_TERTIARY))
        painter.setFont(option.font)
        flags = (int(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft)
                 | int(Qt.TextFlag.TextWordWrap))
        painter.drawText(text_rect, flags,
                         index.data(Qt.ItemDataRole.DisplayRole) or "")
        painter.restore()


class OrderedList(QListWidget):
    """Drag-to-reorder list backed by QListWidget's internal move. Drag
    a row up or down to reprioritise. Optionally checkable (for
    include/exclude, e.g. sinners). Auto-renumbers and sizes to its
    content so the page scroll - not an internal scrollbar - handles
    overflow."""

    changed = Signal()

    def __init__(self, items, checkable: bool = False, checked=None,
                 wrap: bool = False, cols: int = 0,
                 parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("orderedList")
        self._checkable = checkable
        self._wrap = wrap or bool(cols)
        # Preferred fixed column count (e.g. 6 for the 12 sinners -> a 2x6
        # grid like the in-game roster). 0 means auto (pick from width).
        self._wrap_cols = cols
        self.setDragDropMode(QListWidget.DragDropMode.InternalMove)
        self.setDefaultDropAction(Qt.DropAction.MoveAction)
        self.setSelectionMode(QListWidget.SelectionMode.SingleSelection)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.setCursor(Qt.CursorShape.OpenHandCursor)
        # Fixed-grid cells are narrower, so allow text to wrap to two lines
        # (taller rows) instead of eliding long names like "Don Quixote".
        self._relaying = False     # re-entrancy guard for _relayout_wrap
        self._wrap_row_h = 52 if cols else 38
        self._wrap_min_cw = 150 if cols else 150  # floor width per cell
        self._wrap_pref_cw = 230   # auto mode: aim for roughly this
        if self._wrap:
            # Multi-column grid: items flow left-to-right and wrap, so a
            # long list fills the available width instead of forming a tall,
            # narrow column with empty space beside it. Cell width is
            # recomputed from the viewport (see _relayout_wrap) so columns
            # stretch to consume the full width evenly. Order is row-major.
            self.setFlow(QListWidget.Flow.LeftToRight)
            self.setWrapping(True)
            self.setResizeMode(QListWidget.ResizeMode.Adjust)
            self.setGridSize(QSize(self._wrap_pref_cw, self._wrap_row_h))
            if cols:
                # A custom delegate draws each cell and word-wraps long names
                # (e.g. "1. Don Quixote") to a second line; the default list
                # delegate would elide them. Per-item sizing (not uniform) so
                # the pinned cell sizes from _relayout_wrap take effect.
                self.setUniformItemSizes(False)
                self.setItemDelegate(_GridChipDelegate(self))
            else:
                self.setUniformItemSizes(True)
        self._populate(items, checked)
        self.itemChanged.connect(self._after)
        self.model().rowsMoved.connect(self._after)
        # InternalMove drag swallows the checkbox-indicator click, so
        # toggle inclusion explicitly on a plain click instead.
        if checkable:
            self.itemClicked.connect(self._toggle_item)

    def _toggle_item(self, item):
        new = (Qt.CheckState.Unchecked
               if item.checkState() == Qt.CheckState.Checked
               else Qt.CheckState.Checked)
        item.setCheckState(new)

    def _populate(self, items, checked):
        self.clear()
        for name in items:
            it = QListWidgetItem()
            it.setData(Qt.ItemDataRole.UserRole, name)
            if self._checkable:
                it.setFlags(it.flags() | Qt.ItemFlag.ItemIsUserCheckable)
                inc = checked is None or name in checked
                it.setCheckState(Qt.CheckState.Checked if inc
                                 else Qt.CheckState.Unchecked)
            self.addItem(it)
        self._renumber()
        self._fit_height()

    def _after(self, *args):
        self._renumber()
        self._fit_height()
        self.changed.emit()

    def _renumber(self):
        self.blockSignals(True)
        rank = 0
        # Fixed-grid cells are tight and the custom delegate word-wraps, so
        # use a compact "1. Name" prefix (no padding spaces). Included sinners
        # get the rank number that the bot picks in; excluded ones show just
        # the name. The single-column list keeps the roomier format.
        compact = bool(self._wrap_cols)
        for i in range(self.count()):
            it = self.item(i)
            name = it.data(Qt.ItemDataRole.UserRole)
            if self._checkable:
                if it.checkState() == Qt.CheckState.Checked:
                    rank += 1
                    it.setText(f"{rank}. {name}" if compact
                               else f"  {rank}.   {name}")
                else:
                    it.setText(name if compact else f"  ·    {name}")
            else:
                it.setText(f"{i + 1}. {name}" if compact
                           else f"  {i + 1}.   {name}")
        self.blockSignals(False)

    def _fit_height(self):
        if self.count() == 0:
            return
        if self._wrap:
            self._relayout_wrap()
            return
        row_h = self.sizeHintForRow(0)
        if row_h <= 0:
            row_h = 34
        self.setFixedHeight(row_h * self.count() + 2 * self.frameWidth() + 6)

    def _relayout_wrap(self):
        """Recompute the grid so cells fill the viewport width evenly and
        the row has no trailing gap.

        Fixed-column mode (cols set, e.g. sinners): use that many columns so
        the layout reads as a tidy NxM grid (2x6 like the in-game roster).
        If the window is too narrow to give each cell a sane width, step down
        to a smaller divisor of the item count so the rows stay even.

        Auto mode: pick a column count near the preferred cell width."""
        if self._relaying:  # setSizeHint below re-fires itemChanged; guard it
            return
        vw = self.viewport().width()
        if vw <= 1:
            return
        n = self.count()
        # Reserve a few px so a row whose cells sum to exactly the viewport
        # width does not wrap the last cell (an off-by-one in the view's fit).
        avail = vw - 6
        if self._wrap_cols:
            # Largest divisor of n that is <= the preferred count and still
            # leaves cells at/above the floor width (keeps rows even).
            cols = 1
            for c in range(self._wrap_cols, 0, -1):
                if n % c == 0 and avail // c >= self._wrap_min_cw:
                    cols = c
                    break
        else:
            cols = max(1, (vw + self._wrap_pref_cw // 2) // self._wrap_pref_cw)
            cols = min(cols, n)
        cell_w = max(self._wrap_min_cw, avail // cols)
        self._relaying = True
        try:
            self._apply_grid(cell_w)
        finally:
            self._relaying = False
        # Trust the laid-out result for the height so the last row is never
        # clipped, even if the view placed a different number of columns.
        actual = self._actual_cols() or cols
        rows = (n + actual - 1) // actual
        self.setFixedHeight(rows * self._wrap_row_h + 2 * self.frameWidth() + 6)

    def _apply_grid(self, cell_w: int):
        self.setGridSize(QSize(cell_w, self._wrap_row_h))
        if self._wrap_cols:
            # Pin every item to the cell size (with word wrap on) so cells are
            # uniform and text wraps instead of eliding. Block signals: setting
            # a size hint emits itemChanged, which would recurse into here.
            hint = QSize(cell_w, self._wrap_row_h)
            self.blockSignals(True)
            for i in range(self.count()):
                self.item(i).setSizeHint(hint)
            self.blockSignals(False)
        self.doItemsLayout()

    def _actual_cols(self) -> int:
        """How many items the view actually placed on the first row."""
        if self.count() == 0:
            return 0
        y0 = self.visualItemRect(self.item(0)).y()
        cols = 0
        for i in range(self.count()):
            if self.visualItemRect(self.item(i)).y() == y0:
                cols += 1
            else:
                break
        return cols

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self._wrap:
            # Column count depends on width; refit when it changes.
            self._relayout_wrap()

    def order(self) -> list:
        return [self.item(i).data(Qt.ItemDataRole.UserRole)
                for i in range(self.count())]

    def selection(self) -> list:
        return [self.item(i).data(Qt.ItemDataRole.UserRole)
                for i in range(self.count())
                if self.item(i).checkState() == Qt.CheckState.Checked]

    def count_included(self) -> int:
        return len(self.selection())

    def get_state(self) -> tuple:
        return (self.order(), set(self.selection()))

    def set_state(self, order, included):
        self.blockSignals(True)
        self._populate(order, included)
        self.blockSignals(False)


class TriChip(_AnimatedChip):
    """Tri-state pack chip. Clicking cycles neutral -> prioritise ->
    avoid -> neutral, fading between the colour states."""

    STATES = ("neutral", "priority", "avoid")
    state_changed = Signal(str, str)  # (pack_name, new_state)

    @staticmethod
    def _cols(state):
        # Read fresh from Colors so the chips follow a live theme change.
        return {
            "neutral":  (Colors.BG_OVERLAY, Colors.BORDER_SUBTLE,
                         Colors.TEXT_SECONDARY, False),
            "priority": (QColor(62, 213, 152, 40), Colors.SUCCESS,
                         Colors.SUCCESS, True),
            "avoid":    (QColor(245, 94, 94, 36), Colors.ERROR,
                         Colors.ERROR, True),
        }[state]

    def __init__(self, label: str, parent: QWidget | None = None):
        super().__init__(label, parent)
        self._idx = 0
        self._set(*self._cols("neutral"))
        self.clicked.connect(self._cycle)

    def _cycle(self):
        self._idx = (self._idx + 1) % len(self.STATES)
        self._go(*self._cols(self.STATES[self._idx]))
        self.state_changed.emit(self.text(), self.STATES[self._idx])

    def state(self) -> str:
        return self.STATES[self._idx]

    def set_state(self, state: str):
        if state in self.STATES:
            self._idx = self.STATES.index(state)
            self._set(*self._cols(self.STATES[self._idx]))

    def _current_colors(self):
        return self._cols(self.STATES[self._idx])


def humanize_pack(name: str) -> str:
    """CamelCase pack key -> spaced label. 'TheForgotten' ->
    'The Forgotten', 'toClaimTheirBones' -> 'To Claim Their Bones'."""
    import re
    s = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", " ", name)
    s = re.sub(r"(?<=[A-Z])(?=[A-Z][a-z])", " ", s)
    return s[:1].upper() + s[1:] if s else s


class CycleChip(_AnimatedChip):
    """Chip that cycles through an ordered list of states on click,
    fading on/off. The label shows '<name>' on state[0], else
    '<name> <suffix>'. Used for grace tiers (Off / I / II / III)."""

    state_changed = Signal(str, int)  # (name, state_index)

    @staticmethod
    def _off_cols():
        return (Colors.BG_OVERLAY, Colors.BORDER_SUBTLE,
                Colors.TEXT_SECONDARY, False)

    @staticmethod
    def _on_cols():
        return (Colors.BG_HOVER, Colors.TEXT_TERTIARY, Colors.TEXT_PRIMARY, True)

    def __init__(self, name: str, states, parent: QWidget | None = None):
        super().__init__(name, parent)
        self._name = name
        self._states = list(states)  # e.g. ["", "I", "II", "III"]
        self._idx = 0
        self._set(*self._off_cols())
        self.clicked.connect(self._cycle)

    def _label(self) -> str:
        suffix = self._states[self._idx]
        return f"{self._name}  {suffix}".rstrip() if suffix else self._name

    def _cycle(self):
        self._idx = (self._idx + 1) % len(self._states)
        self.setText(self._label())
        self.updateGeometry()
        self._go(*(self._on_cols() if self._idx > 0 else self._off_cols()))
        self.state_changed.emit(self._name, self._idx)

    def _current_colors(self):
        return self._on_cols() if self._idx > 0 else self._off_cols()

    def state(self) -> int:
        return self._idx

    def set_state(self, idx: int):
        if 0 <= idx < len(self._states):
            self._idx = idx
            self.setText(self._label())
            self.updateGeometry()
            self._set(*(self._on_cols() if idx > 0 else self._off_cols()))


class FloorPacks(QWidget):
    """Per-floor pack selector with a Global layer. A tab row switches
    between a "Global" tab and one tab per floor; each floor only lists the
    packs that can actually appear there. Each pack is a TriChip (neutral /
    prioritise / avoid).

    The Global tab is a living default: a Global choice applies to every
    floor the pack can appear on, while an explicit (non-neutral) choice on a
    floor tab overrides the Global default for that one floor. A floor chip
    left neutral inherits the Global choice.

    `floor_data` maps floor number -> iterable of raw pack keys.
    Call set_data() to swap the dataset (e.g. on difficulty change).
    Selections (floor and Global) survive a swap where the pack still exists.

    `state()`        -> {floor: {raw_pack_key: 'priority'|'avoid'}} (per-floor)
    `global_state()` -> {raw_pack_key: 'priority'|'avoid'}          (Global)."""

    changed = Signal()

    def __init__(self, floor_data: dict, banned=(),
                 parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("floorPacks")
        # chips: {floor: {raw_pack_key: TriChip}}; Global chips are tracked
        # separately so the per-floor state() stays floor-only.
        self._chips: dict[int, dict[str, TriChip]] = {}
        self._global_chips: dict[str, TriChip] = {}

        col = QVBoxLayout(self)
        col.setContentsMargins(0, 0, 0, 0)
        col.setSpacing(Sizing.SPACE_MD)

        self._tabs = IconlessTabBar([], default=None, parent=self)
        self._tabs.selection_changed.connect(self._on_tab)
        # Wrap the floor tabs in a horizontal scroller so a long floor list
        # (Extreme = 15 floors) stays fully reachable at any window width
        # instead of clipping the last tabs.
        tab_scroll = QScrollArea(self)
        tab_scroll.setObjectName("floorTabScroll")
        tab_scroll.setWidgetResizable(True)
        tab_scroll.setFrameShape(QFrame.Shape.NoFrame)
        tab_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        tab_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        tab_scroll.setWidget(self._tabs)
        tab_scroll.setFixedHeight(46)
        col.addWidget(tab_scroll)

        self._legend = QLabel("", self)
        self._legend.setObjectName("inlineHint")
        self._legend.setWordWrap(True)
        col.addWidget(self._legend)

        self._search = QLineEdit(self)
        self._search.setObjectName("textField")
        self._search.setPlaceholderText("Filter packs on this floor…")
        self._search.setMaximumWidth(320)
        self._search.textChanged.connect(self._apply_filter)
        col.addWidget(self._search)

        self._stack = QStackedWidget(self)
        col.addWidget(self._stack)

        self.set_data(floor_data, banned)

    def _current_chips(self) -> dict:
        """Chips shown on the active tab. Stack index 0 is the Global tab;
        indices 1.. map to floors in _floor_order."""
        idx = self._stack.currentIndex()
        if idx <= 0:
            return self._global_chips
        order = getattr(self, "_floor_order", [])
        if 1 <= idx <= len(order):
            return self._chips.get(order[idx - 1], {})
        return {}

    def _apply_filter(self):
        q = self._search.text().strip().lower()
        for chip in self._current_chips().values():
            chip.setVisible(q in chip.text().lower() if q else True)

    def _update_legend(self, is_global: bool):
        if is_global:
            self._legend.setText(
                "Global preferences apply to every floor. Set a pack on a "
                "specific floor tab to override it there. Click to cycle: "
                "neutral  >  prioritise  >  avoid")
        else:
            self._legend.setText(
                "Click a pack to cycle: neutral  >  prioritise  >  avoid. "
                "Packs left neutral inherit the Global preference.")

    def set_data(self, floor_data: dict, banned=()):
        """Rebuild the Global + floor tabs and chips from a new dataset.
        Preserves prior non-neutral selections (floor and Global) for packs
        that still exist."""
        prior = self.state() if self._chips else {}
        prior_global = self.global_state() if self._global_chips else {}
        banned_set = set(banned)

        # Tear down the existing stack + tabs.
        while self._stack.count():
            w = self._stack.widget(0)
            self._stack.removeWidget(w)
            w.deleteLater()
        self._floor_order = sorted(floor_data)
        # "Global" first, then compact "F1".."F15" floor labels.
        self._tabs.set_tabs(
            ["Global"] + [f"F{f}" for f in self._floor_order],
            default="Global",
        )

        # Global page (stack index 0): the union of every pack that can appear
        # on any floor, in first-seen order. Starts all-neutral; the user opts
        # packs into a global default.
        union, seen = [], set()
        for floor in self._floor_order:
            for pack in floor_data[floor]:
                if pack not in seen:
                    seen.add(pack)
                    union.append(pack)
        global_page = QWidget(self._stack)
        gflow = FlowLayout(global_page, spacing=Sizing.SPACE_XS)
        self._global_chips = {}
        for pack in union:
            chip = TriChip(humanize_pack(pack), global_page)
            chip._raw = pack
            if pack in prior_global:
                chip.set_state(prior_global[pack])
            chip.state_changed.connect(lambda *_: self.changed.emit())
            gflow.addWidget(chip)
            self._global_chips[pack] = chip
        self._stack.addWidget(global_page)

        # Floor pages (stack indices 1..N).
        self._chips = {}
        for floor in self._floor_order:
            page = QWidget(self._stack)
            flow = FlowLayout(page, spacing=Sizing.SPACE_XS)
            self._chips[floor] = {}
            for pack in floor_data[floor]:
                chip = TriChip(humanize_pack(pack), page)
                chip._raw = pack  # stash the original key for state()
                # Restore prior selection, else default banned -> avoid.
                if floor in prior and pack in prior[floor]:
                    chip.set_state(prior[floor][pack])
                elif pack in banned_set:
                    chip.set_state("avoid")
                chip.state_changed.connect(lambda *_: self.changed.emit())
                flow.addWidget(chip)
                self._chips[floor][pack] = chip
            self._stack.addWidget(page)

        # Land on the Global tab.
        self._stack.setCurrentIndex(0)
        self._update_legend(is_global=True)

    def _on_tab(self, label: str):
        # "Global" (no floor number) is the first tab at stack index 0.
        digits = "".join(ch for ch in label if ch.isdigit())
        if not digits:
            self._stack.setCurrentIndex(0)
            self._update_legend(is_global=True)
            self._apply_filter()
            return
        floor = int(digits)
        if floor in self._floor_order:
            self._stack.setCurrentIndex(1 + self._floor_order.index(floor))
            self._update_legend(is_global=False)
            self._apply_filter()

    def state(self) -> dict:
        # Per-floor picks only; the Global layer is returned by global_state().
        return {
            floor: {pack: chip.state()
                    for pack, chip in chips.items()
                    if chip.state() != "neutral"}
            for floor, chips in self._chips.items()
        }

    def global_state(self) -> dict:
        """The Global layer: {raw_pack_key: 'priority'|'avoid'} for packs the
        user set on the Global tab. Applies to every floor the pack appears
        on, unless a floor tab overrides it."""
        return {pack: chip.state()
                for pack, chip in self._global_chips.items()
                if chip.state() != "neutral"}

    def apply_global_state(self, saved: dict):
        """Restore the Global layer from a saved global_state() dict."""
        if not isinstance(saved, dict):
            return
        for pack, st in saved.items():
            chip = self._global_chips.get(pack)
            if chip is not None and st in ("priority", "avoid", "neutral"):
                chip.set_state(st)

    def apply_state(self, saved: dict):
        """Restore selections from a saved state() dict. Floor keys may be
        ints or (JSON-round-tripped) strings."""
        if not isinstance(saved, dict):
            return
        for floor_key, packs in saved.items():
            try:
                floor = int(floor_key)
            except (TypeError, ValueError):
                continue
            chips = self._chips.get(floor, {})
            if not isinstance(packs, dict):
                continue
            for pack, st in packs.items():
                chip = chips.get(pack)
                if chip is not None and st in ("priority", "avoid", "neutral"):
                    chip.set_state(st)
