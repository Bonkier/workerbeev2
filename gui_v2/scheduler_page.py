# SPDX-License-Identifier: GPL-3.0-or-later
"""Scheduler page - a SEQUENCE of tasks to walk through unattended.

The old "fire at HH:MM each day" model is gone. The user instead builds an
ordered queue of tasks: Mirror Dungeon, EXP Luxcavation, Thread Luxcavation,
Wait, or Convert Enkephalin. When the user starts the scheduler, the
executor runs the queue top-to-bottom; each task either calls the existing
bot entrypoint (the run-type tasks) or executes inline (Wait/Convert).

Lux tasks carry an extra `Skip` flag: when set, the bot configures the
consecutive-battle count as usual and then clicks lux_xpskip /
lux_threadskip instead of starting the battle, so the rewards screen fires
without actually playing the fight.
"""

from __future__ import annotations

import uuid

from PySide6.QtCore import QMimeData, QPoint, Qt, QTime, Signal
from PySide6.QtGui import QDrag, QPixmap
from PySide6.QtWidgets import (
    QApplication, QCheckBox, QComboBox, QFrame, QHBoxLayout, QLabel,
    QSpinBox, QStackedWidget, QTimeEdit, QVBoxLayout, QWidget,
)

from .copy import (
    SCHEDULER_CONVERT_TASK_HINT,
    SCHEDULER_EMPTY_BODY,
    SCHEDULER_EMPTY_TITLE,
    SCHEDULER_PAGE_HINT,
)
from .settings import load_section, save_section
from .theme import Colors, Sizing
from .widgets import (
    Card, LinkButton, PageHeader, PrimaryButton, Toggle,
)


_SECTION = "scheduler"

# Every input widget in the Add Task row pins to this height so the combo
# (task type), the per-type spinboxes / time edit, and the Add button all
# share the same baseline. Picked at 46 so the QSpinBox's styled
# min-height (32) + padding (6 top, 6 bottom) + border (1 each side)
# fits comfortably with no bottom-edge clipping; the QComboBox at the
# same height has a couple px of breathing room around its content,
# which Qt centers vertically.
_INPUT_HEIGHT = 46


# Task-type identifiers + their human labels. The identifier goes in
# v2_ui.json; the label is the dropdown / row caption.
TASK_TYPES = (
    ("md",      "Mirror Dungeon"),
    ("exp",     "EXP Luxcavation"),
    ("thread",  "Thread Luxcavation"),
    ("wait",    "Wait"),
    ("convert", "Convert Enkephalin"),
)
_TYPE_LABEL = dict(TASK_TYPES)
_LABEL_TYPE = {v: k for k, v in TASK_TYPES}


def _default_task(kind: str) -> dict:
    """Fresh task dict for a given type. `id` is a stable uuid so the
    drag-reorder layer can match payloads back to the source rows."""
    base = {"id": uuid.uuid4().hex, "type": kind, "enabled": True}
    if kind in ("md", "exp", "thread"):
        base["runs"] = 1
    if kind in ("exp", "thread"):
        base["skip"] = False
    if kind == "wait":
        base["duration"] = "00:05:00"
    return base


# ---------------------------------------------------------------------------
# Task row: a draggable card showing one queued task.
# ---------------------------------------------------------------------------


_MIME = "application/x-workerbee-scheduler-task"


class _TaskRow(QFrame):
    """One task in the queue. Shows enable toggle + caption + delete; the
    whole row is draggable to reorder the queue."""

    remove_requested = Signal(str)              # emits task id
    changed = Signal()
    reorder_requested = Signal(str, str)        # (dragged_id, target_id)

    def __init__(self, task: dict, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("teamRow")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setAcceptDrops(True)
        self.task = task
        self._drag_origin: QPoint | None = None

        row = QHBoxLayout(self)
        row.setContentsMargins(
            Sizing.SPACE_MD, Sizing.SPACE_SM, Sizing.SPACE_MD, Sizing.SPACE_SM,
        )
        row.setSpacing(Sizing.SPACE_MD)

        enable = Toggle(default=task.get("enabled", True), parent=self)
        enable.toggled.connect(self._on_enable)
        row.addWidget(enable)

        # 6-dot "drag handle" hint - the row IS the handle, but a visible
        # affordance helps users know it's reorderable.
        handle = QLabel("⋮⋮", self, objectName="dragHandle")
        handle.setFixedWidth(20)
        row.addWidget(handle)

        type_lbl = QLabel(_TYPE_LABEL[task["type"]], self, objectName="teamRowName")
        type_lbl.setFixedWidth(160)
        row.addWidget(type_lbl)

        desc = QLabel(self._describe(task), self, objectName="teamRowAffinities")
        row.addWidget(desc, stretch=1)
        self._desc_label = desc

        remove = LinkButton("Delete", self)
        remove.setProperty("danger", "true")
        remove.clicked.connect(
            lambda: self.remove_requested.emit(self.task["id"]))
        row.addWidget(remove)

    @staticmethod
    def _describe(task: dict) -> str:
        kind = task["type"]
        if kind == "md":
            return f"{task.get('runs', 1)} run(s)"
        if kind in ("exp", "thread"):
            note = "skip" if task.get("skip") else "play"
            return f"{task.get('runs', 1)} run(s) - {note}"
        if kind == "wait":
            return f"sleep {task.get('duration', '00:00:00')}"
        if kind == "convert":
            return "convert spare enkephalin to modules"
        return ""

    def refresh_desc(self):
        self._desc_label.setText(self._describe(self.task))

    def _on_enable(self, on: bool):
        self.task["enabled"] = bool(on)
        self.changed.emit()

    # --- drag source ------------------------------------------------------
    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_origin = event.position().toPoint()
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if (event.buttons() & Qt.MouseButton.LeftButton
                and self._drag_origin is not None
                and (event.position().toPoint() - self._drag_origin).manhattanLength()
                >= QApplication.startDragDistance()):
            self._start_drag()
        super().mouseMoveEvent(event)

    def _start_drag(self):
        drag = QDrag(self)
        mime = QMimeData()
        mime.setData(_MIME, self.task["id"].encode())
        drag.setMimeData(mime)
        pix = QPixmap(self.size())
        self.render(pix)
        drag.setPixmap(pix)
        drag.setHotSpot(self._drag_origin or QPoint(0, 0))
        drag.exec(Qt.DropAction.MoveAction)

    # --- drop target ------------------------------------------------------
    def dragEnterEvent(self, event):
        if event.mimeData().hasFormat(_MIME):
            event.acceptProposedAction()
        else:
            event.ignore()

    def dragMoveEvent(self, event):
        if event.mimeData().hasFormat(_MIME):
            event.acceptProposedAction()
        else:
            event.ignore()

    def dropEvent(self, event):
        if not event.mimeData().hasFormat(_MIME):
            event.ignore()
            return
        dragged_id = bytes(event.mimeData().data(_MIME)).decode()
        if dragged_id != self.task["id"]:
            self.reorder_requested.emit(dragged_id, self.task["id"])
        event.acceptProposedAction()


# ---------------------------------------------------------------------------
# Scheduler page.
# ---------------------------------------------------------------------------


class SchedulerPage(QWidget):

    # Emitted when the user clicks "Run scheduler". Carries the saved
    # task list so the runtime can walk it.
    run_requested = Signal(list)
    stop_requested = Signal()

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("root")
        self._loading = True
        saved = load_section(_SECTION)
        raw_tasks = saved.get("tasks") or []
        self._tasks: list[dict] = [self._coerce(t) for t in raw_tasks
                                   if isinstance(t, dict)]
        self._build()
        self._loading = False
        self._rebuild_list()

    # --- task data --------------------------------------------------------
    @staticmethod
    def _coerce(task: dict) -> dict:
        """Normalise an on-disk task back into the shape the UI expects.
        Tolerant of v1 entries (which had `time` / `action` keys) so an
        old config doesn't crash the page; v1 entries are silently dropped
        if their action doesn't map to a v2 task type."""
        kind = task.get("type")
        if not kind:
            # v1 had `action` as a friendly label.
            label = task.get("action") or ""
            if label not in _LABEL_TYPE:
                return _default_task("md")
            kind = _LABEL_TYPE[label]
        out = _default_task(kind)
        out["enabled"] = bool(task.get("enabled", True))
        if "id" in task:
            out["id"] = str(task["id"])
        for key in ("runs", "skip", "duration"):
            if key in task:
                out[key] = task[key]
        return out

    # --- build ------------------------------------------------------------
    def _build(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(
            Sizing.SPACE_XXL, Sizing.SPACE_XL,
            Sizing.SPACE_XXL, Sizing.SPACE_XL,
        )
        outer.setSpacing(Sizing.SPACE_LG)

        header = PageHeader("Scheduler", self)
        self._run_btn = PrimaryButton("Run scheduler", self)
        self._run_btn.clicked.connect(self._on_run)
        header.add_action(self._run_btn)
        self._stop_btn = LinkButton("Stop", self)
        self._stop_btn.setEnabled(False)
        self._stop_btn.clicked.connect(self.stop_requested.emit)
        header.add_action(self._stop_btn)
        outer.addWidget(header)

        outer.addWidget(QLabel(
            SCHEDULER_PAGE_HINT, self, objectName="inlineHint"))

        outer.addWidget(self._build_add_card())
        outer.addWidget(self._build_list_card(), stretch=1)

    def _build_add_card(self) -> QWidget:
        add = Card("ADD TASK", self)

        row = QHBoxLayout()
        row.setSpacing(Sizing.SPACE_MD)

        self._type = QComboBox(add)
        self._type.setObjectName("combo")
        self._type.setFixedHeight(_INPUT_HEIGHT)
        for _, label in TASK_TYPES:
            self._type.addItem(label)
        self._type.currentIndexChanged.connect(self._on_type_changed)
        row.addWidget(self._type)

        # Per-type input stack: each type gets its own QWidget inside a
        # QStackedWidget, so switching the dropdown swaps the visible
        # form bits without rebuilding the row.
        #
        # Don't fix the height: the QComboBox styled at min-height 30 px
        # actually paints ~42 px tall once the padding lands, and a fixed
        # 40 px stack would make the row taller than the stack so the
        # spinbox inside it sat visually lower than the combo. Letting
        # the stack size to its contents keeps every input widget on the
        # same baseline as the combo.
        self._inputs = QStackedWidget(add)

        # md
        md_page = QWidget()
        md_row = QHBoxLayout(md_page)
        md_row.setContentsMargins(0, 0, 0, 0)
        md_row.setSpacing(Sizing.SPACE_MD)
        self._md_runs = QSpinBox(md_page)
        self._md_runs.setObjectName("runCount")
        self._md_runs.setRange(1, 9999)
        self._md_runs.setValue(1)
        # 120 px so the up / down chevrons sit next to the number rather
        # than clipping past the right edge (90 was tight enough that
        # 4-digit values overlapped the chevrons).
        self._md_runs.setFixedWidth(120)
        self._md_runs.setFixedHeight(_INPUT_HEIGHT)
        md_row.addWidget(self._md_runs)
        md_row.addWidget(QLabel("runs", md_page))
        md_row.addStretch(1)
        self._inputs.addWidget(md_page)

        # exp
        exp_page = QWidget()
        exp_row = QHBoxLayout(exp_page)
        exp_row.setContentsMargins(0, 0, 0, 0)
        exp_row.setSpacing(Sizing.SPACE_MD)
        self._exp_runs = QSpinBox(exp_page)
        self._exp_runs.setObjectName("runCount")
        self._exp_runs.setRange(1, 9999)
        self._exp_runs.setValue(1)
        self._exp_runs.setFixedWidth(120)
        self._exp_runs.setFixedHeight(_INPUT_HEIGHT)
        exp_row.addWidget(self._exp_runs)
        exp_row.addWidget(QLabel("runs", exp_page))
        self._exp_skip = QCheckBox("Skip", exp_page)
        self._exp_skip.setToolTip(
            "Set up the consecutive-battle count and then click the EXP skip "
            "button instead of playing the fight. Rewards screen still fires.")
        exp_row.addWidget(self._exp_skip)
        exp_row.addStretch(1)
        self._inputs.addWidget(exp_page)

        # thread
        thd_page = QWidget()
        thd_row = QHBoxLayout(thd_page)
        thd_row.setContentsMargins(0, 0, 0, 0)
        thd_row.setSpacing(Sizing.SPACE_MD)
        self._thd_runs = QSpinBox(thd_page)
        self._thd_runs.setObjectName("runCount")
        self._thd_runs.setRange(1, 9999)
        self._thd_runs.setValue(1)
        self._thd_runs.setFixedWidth(120)
        self._thd_runs.setFixedHeight(_INPUT_HEIGHT)
        thd_row.addWidget(self._thd_runs)
        thd_row.addWidget(QLabel("runs", thd_page))
        self._thd_skip = QCheckBox("Skip", thd_page)
        self._thd_skip.setToolTip(
            "Set up the consecutive-battle count and then click the Thread "
            "skip button instead of playing the fight. Rewards screen still "
            "fires.")
        thd_row.addWidget(self._thd_skip)
        thd_row.addStretch(1)
        self._inputs.addWidget(thd_page)

        # wait
        wait_page = QWidget()
        wait_row = QHBoxLayout(wait_page)
        wait_row.setContentsMargins(0, 0, 0, 0)
        wait_row.setSpacing(Sizing.SPACE_MD)
        self._wait_dur = QTimeEdit(QTime(0, 5, 0), wait_page)
        self._wait_dur.setObjectName("runCount")
        self._wait_dur.setDisplayFormat("HH:mm:ss")
        # 140 px so the full HH:MM:SS reading fits next to the up/down
        # chevrons - 110 px cut off the trailing second.
        self._wait_dur.setFixedWidth(140)
        self._wait_dur.setFixedHeight(_INPUT_HEIGHT)
        wait_row.addWidget(QLabel("for", wait_page))
        wait_row.addWidget(self._wait_dur)
        wait_row.addStretch(1)
        self._inputs.addWidget(wait_page)

        # convert (nothing to configure)
        conv_page = QWidget()
        conv_row = QHBoxLayout(conv_page)
        conv_row.setContentsMargins(0, 0, 0, 0)
        conv_row.setSpacing(Sizing.SPACE_MD)
        conv_row.addWidget(QLabel(
            SCHEDULER_CONVERT_TASK_HINT,
            conv_page, objectName="inlineHint"))
        conv_row.addStretch(1)
        self._inputs.addWidget(conv_page)

        row.addWidget(self._inputs, stretch=1)

        add_btn = PrimaryButton("Add task", add)
        add_btn.clicked.connect(self._on_add_clicked)
        row.addWidget(add_btn)

        add.body.addLayout(row)
        return add

    def _build_list_card(self) -> QWidget:
        card = Card("SCHEDULED TASKS", self, fill=True)
        self._content = QStackedWidget(card)

        rows_page = QWidget(self._content)
        rows_page.setObjectName("root")
        rp = QVBoxLayout(rows_page)
        rp.setContentsMargins(0, 0, 0, 0)
        rp.setSpacing(Sizing.SPACE_SM)
        self._rows_box = QVBoxLayout()
        self._rows_box.setContentsMargins(0, 0, 0, 0)
        self._rows_box.setSpacing(Sizing.SPACE_SM)
        rp.addLayout(self._rows_box)
        rp.addStretch(1)
        self._content.addWidget(rows_page)

        self._empty_state = self._build_empty_state()
        self._content.addWidget(self._empty_state)

        card.body.addWidget(self._content, stretch=1)
        return card

    def _build_empty_state(self) -> QWidget:
        wrap = QWidget(self)
        wrap.setObjectName("root")
        col = QVBoxLayout(wrap)
        col.setContentsMargins(0, 0, 0, 0)
        col.setSpacing(Sizing.SPACE_XS)
        col.addStretch(1)
        title = QLabel(SCHEDULER_EMPTY_TITLE, wrap, objectName="emptyTitle")
        title.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        col.addWidget(title)
        hint = QLabel(
            SCHEDULER_EMPTY_BODY,
            wrap, objectName="inlineHint",
        )
        hint.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        col.addWidget(hint)
        col.addStretch(1)
        return wrap

    # --- type switch ------------------------------------------------------
    def _on_type_changed(self, idx: int):
        self._inputs.setCurrentIndex(idx)

    def _current_type(self) -> str:
        return TASK_TYPES[self._inputs.currentIndex()][0]

    # --- add / remove / reorder ------------------------------------------
    def _on_add_clicked(self):
        kind = self._current_type()
        task = _default_task(kind)
        if kind == "md":
            task["runs"] = self._md_runs.value()
        elif kind == "exp":
            task["runs"] = self._exp_runs.value()
            task["skip"] = self._exp_skip.isChecked()
        elif kind == "thread":
            task["runs"] = self._thd_runs.value()
            task["skip"] = self._thd_skip.isChecked()
        elif kind == "wait":
            task["duration"] = self._wait_dur.time().toString("HH:mm:ss")
        # convert: defaults
        self._tasks.append(task)
        self._rebuild_list()
        self._save_state()

    def _on_remove(self, task_id: str):
        self._tasks = [t for t in self._tasks if t.get("id") != task_id]
        self._rebuild_list()
        self._save_state()

    def _on_reorder(self, dragged_id: str, target_id: str):
        ids = [t["id"] for t in self._tasks]
        if dragged_id not in ids or target_id not in ids:
            return
        idx_d = ids.index(dragged_id)
        idx_t = ids.index(target_id)
        task = self._tasks.pop(idx_d)
        # Re-index target after pop; insert before target.
        if idx_d < idx_t:
            idx_t -= 1
        self._tasks.insert(idx_t, task)
        self._rebuild_list()
        self._save_state()

    def _rebuild_list(self):
        while self._rows_box.count():
            item = self._rows_box.takeAt(0)
            w = item.widget()
            if w is not None:
                w.deleteLater()
        for task in self._tasks:
            rowf = _TaskRow(task, parent=self)
            rowf.remove_requested.connect(self._on_remove)
            rowf.reorder_requested.connect(self._on_reorder)
            rowf.changed.connect(self._save_state)
            self._rows_box.addWidget(rowf)
        self._refresh_empty()

    def _refresh_empty(self):
        self._content.setCurrentIndex(0 if self._tasks else 1)

    # --- run / stop -------------------------------------------------------
    def _on_run(self):
        self.run_requested.emit(list(self._tasks))

    def set_running(self, running: bool):
        self._run_btn.setEnabled(not running)
        self._stop_btn.setEnabled(running)

    # --- persistence ------------------------------------------------------
    def _save_state(self, *_):
        if self._loading:
            return
        save_section(_SECTION, {"tasks": self._tasks})
