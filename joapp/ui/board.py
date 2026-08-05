"""今日面板：勾任务、看目标进度、看今天专注了多久。"""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from ..agent.planner import Planner
from ..core.models import TaskStatus
from ..core.store import Store


class DayBoard(QWidget):
    plan_requested = Signal()
    login_requested = Signal()

    def __init__(self, store: Store, planner: Planner):
        super().__init__()
        self.store = store
        self.planner = planner
        self.setWindowTitle("jo-app · 今天")
        self.setMinimumSize(420, 480)

        root = QVBoxLayout(self)
        root.setContentsMargins(24, 24, 24, 24)
        root.setSpacing(12)

        self.heading = QLabel("今天")
        self.heading.setObjectName("Title")
        root.addWidget(self.heading)

        self.summary = QLabel("")
        self.summary.setObjectName("Subtitle")
        root.addWidget(self.summary)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        self._host = QWidget()
        self._body = QVBoxLayout(self._host)
        self._body.setAlignment(Qt.AlignTop)
        self._body.setSpacing(6)
        scroll.setWidget(self._host)
        root.addWidget(scroll, 1)

        # 凭据状态：告诉用户现在是 Claude 在答还是本地规则在答
        self.auth_label = QLabel("")
        self.auth_label.setObjectName("Muted")
        self.auth_label.setWordWrap(True)
        root.addWidget(self.auth_label)

        row = QHBoxLayout()
        self.login = QPushButton("连接 Claude")
        self.login.clicked.connect(self.login_requested.emit)
        row.addWidget(self.login)
        row.addStretch()
        add = QPushButton("加点事")
        add.setObjectName("Primary")
        add.clicked.connect(self.plan_requested.emit)
        row.addWidget(add)
        root.addLayout(row)

    def refresh(self) -> None:
        self._refresh_auth()
        while self._body.count():
            item = self._body.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        tasks = self.store.tasks_for()
        done = sum(1 for t in tasks if t.status is TaskStatus.DONE)
        focus = self.store.focus_minutes_today()
        self.summary.setText(
            f"完成 {done}/{len(tasks)} · 专注 {focus:.0f} 分钟"
            if tasks
            else "今天还没定计划"
        )

        for task in tasks:
            box = QCheckBox(f"{task.title}   ·   {task.estimate_minutes} 分钟")
            box.setChecked(task.status is TaskStatus.DONE)
            box.toggled.connect(
                lambda checked, tid=task.id: self._toggle(tid, checked)
            )
            self._body.addWidget(box)

        goals = self.store.goals()
        if goals:
            label = QLabel("长期目标")
            label.setObjectName("Subtitle")
            self._body.addSpacing(12)
            self._body.addWidget(label)
        for goal in goals:
            days = goal.days_left
            tail = f"还剩 {days} 天" if days is not None else "无期限"
            if days is not None and days < 0:
                tail = f"过期 {-days} 天"
            self._body.addWidget(QLabel(f"{goal.title} · {tail}"))
            bar = QProgressBar()
            bar.setRange(0, 100)
            bar.setValue(int(goal.percent))
            bar.setFormat(f"{goal.percent:.0f}%")
            self._body.addWidget(bar)

    def _refresh_auth(self) -> None:
        creds = self.planner.credentials
        text = self.planner.status_line
        if creds.warning:
            text += f"\n⚠ {creds.warning}"
        self.auth_label.setText(text)
        self.login.setVisible(not creds.available)

    def _toggle(self, task_id: int, checked: bool) -> None:
        self.store.set_task_status(
            task_id, TaskStatus.DONE if checked else TaskStatus.TODO
        )
        self.refresh()

    def showEvent(self, event):
        self.refresh()
        super().showEvent(event)
