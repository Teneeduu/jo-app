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


# 连上 Claude 时：随便说。没连上时：照格式写，保证拆得准。
ONLINE_HINT = "随便说，不用分条。比如「上午写完报告，下午看两章书，晚上跑步」"
ONLINE_PLACEHOLDER = "说吧……（Ctrl+Enter 提交）"

OFFLINE_HINT = (
    "离线模式 —— 现在读不懂口语，请<b>一行写一件事</b>，行尾可以写时长"
    "（<code>2小时</code> / <code>45分钟</code> / <code>1.5h</code>），不写按 30 分钟算。"
)
OFFLINE_PLACEHOLDER = (
    "写完季度报告 2小时\n读书第 3-4 章 50分钟\n跑步 5 公里 30分\n\n"
    "（一行一件事。Ctrl+Enter 提交）"
)


class MorningWindow(QWidget):
    """确认后发出 tasks_confirmed(list[Task])。"""

    tasks_confirmed = Signal(list)
    login_requested = Signal()

    def __init__(self, planner: Planner, greeting: str = "今天打算干点什么？"):
        super().__init__()
        self.planner = planner
        self.online = planner.use_llm
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

        self.hint = QLabel(ONLINE_HINT if self.online else OFFLINE_HINT)
        self.hint.setObjectName("Subtitle")
        self.hint.setWordWrap(True)
        self.hint.setTextFormat(Qt.RichText)
        root.addWidget(self.hint)

        self.input = QTextEdit()
        self.input.setPlaceholderText(
            ONLINE_PLACEHOLDER if self.online else OFFLINE_PLACEHOLDER
        )
        self.input.setFixedHeight(110 if self.online else 150)
        root.addWidget(self.input)

        # 离线时给一条当场去连的路，而不是让用户自己翻 README
        self.connect_row = QHBoxLayout()
        self.connect_hint = QLabel("想直接说人话？")
        self.connect_hint.setObjectName("Muted")
        self.connect_row.addWidget(self.connect_hint)
        self.connect_btn = QPushButton("连接 Claude")
        self.connect_btn.clicked.connect(self.login_requested.emit)
        self.connect_row.addWidget(self.connect_btn)
        self.connect_row.addStretch()
        if not self.online:
            root.addLayout(self.connect_row)
        else:
            self.connect_hint.setVisible(False)
            self.connect_btn.setVisible(False)

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
            self.hint.setText(
                "没拆出东西来。" + ("换个说法？" if self.online else OFFLINE_HINT)
            )
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
        self.hint.setText(ONLINE_HINT if self.online else OFFLINE_HINT)
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
