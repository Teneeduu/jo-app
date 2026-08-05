"""提醒气泡：右下角淡入，超时自动消失，点按钮回传选择。"""

from __future__ import annotations

from PySide6.QtCore import QEasingCurve, QPropertyAnimation, Qt, QTimer, Signal
from PySide6.QtWidgets import (
    QApplication,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from ..core.models import Nudge

MARGIN = 24


class NudgeToast(QWidget):
    """action_chosen 传出被点的按钮文案；超时或关闭传出空串。"""

    action_chosen = Signal(str, object)  # (按钮文案, Nudge)

    def __init__(self, nudge: Nudge, seconds: int = 12):
        super().__init__()
        self.nudge = nudge
        self._answered = False

        self.setWindowFlags(
            Qt.Tool | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint
        )
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_DeleteOnClose)  # 关掉就销毁，别攒着
        self.setFixedWidth(360)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)

        card = QFrame()
        card.setObjectName("Card")
        outer.addWidget(card)

        inner = QVBoxLayout(card)
        inner.setContentsMargins(18, 16, 18, 16)
        inner.setSpacing(8)

        title = QLabel(nudge.title)
        title.setObjectName("Title")
        title.setWordWrap(True)
        inner.addWidget(title)

        if nudge.body:
            body = QLabel(nudge.body)
            body.setWordWrap(True)
            inner.addWidget(body)

        row = QHBoxLayout()
        row.addStretch()
        for i, label in enumerate(nudge.actions or ["知道了"]):
            btn = QPushButton(label)
            if i == 0:
                btn.setObjectName("Primary")
            btn.clicked.connect(lambda _=False, t=label: self._choose(t))
            row.addWidget(btn)
        inner.addLayout(row)

        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(lambda: self._choose(""))
        self._timer.start(max(3, seconds) * 1000)

        self._fade = QPropertyAnimation(self, b"windowOpacity", self)
        self._fade.setDuration(220)
        self._fade.setStartValue(0.0)
        self._fade.setEndValue(1.0)
        self._fade.setEasingCurve(QEasingCurve.OutCubic)

    def show_at_corner(self) -> None:
        self.adjustSize()
        screen = QApplication.primaryScreen().availableGeometry()
        self.move(
            screen.right() - self.width() - MARGIN,
            screen.bottom() - self.height() - MARGIN,
        )
        self.setWindowOpacity(0.0)
        self.show()
        self._fade.start()

    def enterEvent(self, event):  # 鼠标悬停时别急着消失
        self._timer.stop()
        super().enterEvent(event)

    def leaveEvent(self, event):
        if not self._answered:
            self._timer.start(4000)
        super().leaveEvent(event)

    def _choose(self, action: str) -> None:
        if self._answered:
            return
        self._answered = True
        self._timer.stop()
        self.action_chosen.emit(action, self.nudge)
        self.close()
