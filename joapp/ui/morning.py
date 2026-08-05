"""开机后弹的那个小窗：问今天干什么，把回答变成任务清单。

两步：输入 → 确认。拆解可能要走网络，所以放在后台线程里，
主线程只负责显示「正在拆解…」。
"""

from __future__ import annotations

from datetime import date

from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from ..agent.planner import Planner
from ..core.models import Task
from .style import MUTED


class _PlanWorker(QThread):
    done = Signal(list, str)
    failed = Signal(str)

    def __init__(self, planner: Planner, raw: str):
        super().__init__()
        self.planner = planner
        self.raw = raw

    def run(self) -> None:  # pragma: no cover - 线程体
        try:
            tasks, comment = self.planner.plan_from_text(self.raw, date.today())
            self.done.emit(tasks, comment)
        except Exception as e:
            self.failed.emit(str(e))


class MorningWindow(QWidget):
    """确认后发出 tasks_confirmed(list[Task])。"""

    tasks_confirmed = Signal(list)

    def __init__(self, planner: Planner, greeting: str = "今天打算干点什么？"):
        super().__init__()
        self.planner = planner
        self._worker: _PlanWorker | None = None
        self._tasks: list[Task] = []
        self._checks: list[QCheckBox] = []

        self.setWindowTitle("jo-app")
        self.setWindowFlags(Qt.Window | Qt.WindowStaysOnTopHint)
        self.setMinimumWidth(460)

        root = QVBoxLayout(self)
        root.setContentsMargins(24, 24, 24, 24)
        root.setSpacing(14)

        self.title = QLabel(greeting)
        self.title.setObjectName("Title")
        root.addWidget(self.title)

        self.hint = QLabel("随便说，不用分条。比如「上午写完报告，下午看两章书，晚上跑步」")
        self.hint.setObjectName("Subtitle")
        self.hint.setWordWrap(True)
        root.addWidget(self.hint)

        self.input = QTextEdit()
        self.input.setPlaceholderText("说吧……（Ctrl+Enter 提交）")
        self.input.setFixedHeight(110)
        root.addWidget(self.input)

        self.busy = QProgressBar()
        self.busy.setRange(0, 0)
        self.busy.setVisible(False)
        root.addWidget(self.busy)

        # 第二步：确认清单
        self.review = QScrollArea()
        self.review.setWidgetResizable(True)
        self.review.setVisible(False)
        self.review.setFixedHeight(220)
        self._list_host = QWidget()
        self._list_layout = QVBoxLayout(self._list_host)
        self._list_layout.setAlignment(Qt.AlignTop)
        self.review.setWidget(self._list_host)
        root.addWidget(self.review)

        self.comment = QLabel("")
        self.comment.setObjectName("Muted")
        self.comment.setWordWrap(True)
        self.comment.setVisible(False)
        root.addWidget(self.comment)

        buttons = QHBoxLayout()
        buttons.addStretch()
        self.later = QPushButton("待会儿再说")
        self.later.clicked.connect(self.close)
        buttons.addWidget(self.later)
        self.submit = QPushButton("排一下")
        self.submit.setObjectName("Primary")
        self.submit.clicked.connect(self._on_submit)
        buttons.addWidget(self.submit)
        root.addLayout(buttons)

    def keyPressEvent(self, event):  # Ctrl+Enter 提交
        if event.key() in (Qt.Key_Return, Qt.Key_Enter) and (
            event.modifiers() & Qt.ControlModifier
        ):
            self._on_submit()
            return
        super().keyPressEvent(event)

    # --- 步骤一：拆解 ---

    def _on_submit(self) -> None:
        if self._tasks:  # 已经在确认阶段了
            self._confirm()
            return
        raw = self.input.toPlainText().strip()
        if not raw:
            return
        self.submit.setEnabled(False)
        self.busy.setVisible(True)
        self.hint.setText("正在拆解……")
        self._worker = _PlanWorker(self.planner, raw)
        self._worker.done.connect(self._on_planned)
        self._worker.failed.connect(self._on_failed)
        self._worker.start()

    def _on_failed(self, message: str) -> None:
        self.busy.setVisible(False)
        self.submit.setEnabled(True)
        self.hint.setText(f"拆解出了点问题：{message}")

    def _on_planned(self, tasks: list, comment: str) -> None:
        self.busy.setVisible(False)
        self.submit.setEnabled(True)
        if not tasks:
            self.hint.setText("没听出具体的事，换个说法？")
            return

        self._tasks = tasks
        self.input.setVisible(False)
        self.title.setText("这样排行吗？")
        total = sum(t.estimate_minutes for t in tasks)
        src = "Claude 拆的" if self.planner.last_source == "llm" else "本地规则拆的"
        self.hint.setText(f"{len(tasks)} 件事，预计 {total} 分钟 · {src}")

        for t in tasks:
            box = QCheckBox(f"{t.title}   ·   {t.estimate_minutes} 分钟")
            box.setChecked(True)
            self._checks.append(box)
            self._list_layout.addWidget(box)
        self.review.setVisible(True)

        if comment:
            self.comment.setText(comment)
            self.comment.setVisible(True)

        self.submit.setText("就这样")
        self.later.setText("重说")
        self.later.clicked.disconnect()
        self.later.clicked.connect(self._restart)
        self.adjustSize()

    def _restart(self) -> None:
        for box in self._checks:
            box.setParent(None)
        self._checks.clear()
        self._tasks.clear()
        self.review.setVisible(False)
        self.comment.setVisible(False)
        self.input.setVisible(True)
        self.input.clear()
        self.title.setText("今天打算干点什么？")
        self.hint.setText("再说一遍，说具体点。")
        self.submit.setText("排一下")
        self.later.setText("待会儿再说")
        self.later.clicked.disconnect()
        self.later.clicked.connect(self.close)

    # --- 步骤二：确认入库 ---

    def _confirm(self) -> None:
        chosen = [t for t, box in zip(self._tasks, self._checks) if box.isChecked()]
        if chosen:
            self.tasks_confirmed.emit(chosen)
        self.close()
