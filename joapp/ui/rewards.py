"""奖励：设置窗口 + 拿到奖励时弹的那个框。

规则很简单：每天 / 每周 / 每年任务在一个周期里完成到 N% 就发一个奖励，
每个奖励每个周期只发一次。N 自己定，50% / 100% 只是快捷按钮。
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QButtonGroup,
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from ..core.models import REWARD_SCOPES, Reward
from ..core.store import Store


class RewardsDialog(QDialog):
    """列出所有奖励，底下加新的。关掉之后由调用方检查一遍有没有已经够线的。"""

    def __init__(self, store: Store, parent: QWidget | None = None):
        super().__init__(parent)
        self.store = store
        self.setWindowTitle("给自己的奖励")
        self.setMinimumSize(440, 460)

        root = QVBoxLayout(self)
        root.setContentsMargins(24, 20, 24, 20)
        root.setSpacing(12)

        title = QLabel("完成到多少，奖励自己什么")
        title.setObjectName("Title")
        root.addWidget(title)
        hint = QLabel("每个奖励每个周期只发一次：每天的第二天重来，每周的下周一重来，每年的明年重来。")
        hint.setObjectName("Subtitle")
        hint.setWordWrap(True)
        root.addWidget(hint)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        host = QWidget()
        self._list = QVBoxLayout(host)
        self._list.setAlignment(Qt.AlignTop)
        self._list.setContentsMargins(0, 0, 8, 0)
        self._list.setSpacing(2)
        scroll.setWidget(host)
        root.addWidget(scroll, 1)

        # --- 新加一个 ---
        line = QFrame()
        line.setFrameShape(QFrame.HLine)
        root.addWidget(line)

        scopes = QHBoxLayout()
        scopes.setSpacing(6)
        scopes.addWidget(QLabel("分组"))
        self._scope_group = QButtonGroup(self)
        for i, scope in enumerate(REWARD_SCOPES):
            btn = QPushButton(scope.label)
            btn.setObjectName("Scope")
            btn.setCheckable(True)
            self._scope_group.addButton(btn, i)
            scopes.addWidget(btn)
        self._scope_group.button(0).setChecked(True)
        scopes.addStretch()
        root.addLayout(scopes)

        pct = QHBoxLayout()
        pct.setSpacing(6)
        pct.addWidget(QLabel("完成到"))
        self.percent = QSpinBox()
        self.percent.setRange(1, 100)
        self.percent.setValue(100)
        self.percent.setSuffix(" %")
        pct.addWidget(self.percent)
        for value in (50, 100):
            quick = QPushButton(f"{value}%")
            quick.clicked.connect(lambda _=False, v=value: self.percent.setValue(v))
            pct.addWidget(quick)
        pct.addStretch()
        root.addLayout(pct)

        add_row = QHBoxLayout()
        self.text = QLineEdit()
        self.text.setPlaceholderText("奖励自己……比如「看一集剧」「买杯奶茶」")
        self.text.returnPressed.connect(self._add)
        add_row.addWidget(self.text, 1)
        add = QPushButton("添加")
        add.setObjectName("Primary")
        add.clicked.connect(self._add)
        add_row.addWidget(add)
        root.addLayout(add_row)

        bottom = QHBoxLayout()
        bottom.addStretch()
        done = QPushButton("完成")
        done.clicked.connect(self.accept)
        bottom.addWidget(done)
        root.addLayout(bottom)

        self.refresh()
        self.text.setFocus()

    def refresh(self) -> None:
        while self._list.count():
            item = self._list.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        rewards = self.store.rewards()
        if not rewards:
            empty = QLabel("还没设奖励。在下面加一个。")
            empty.setObjectName("Muted")
            self._list.addWidget(empty)
        for reward in rewards:
            self._list.addWidget(self._row(reward))

    def _row(self, reward: Reward) -> QWidget:
        row = QWidget()
        h = QHBoxLayout(row)
        h.setContentsMargins(0, 2, 0, 2)
        label = QLabel(f"{reward.scope.label}完成 {reward.percent}%   →   {reward.text}")
        label.setWordWrap(True)
        h.addWidget(label, 1)
        if reward.earned:
            got = QLabel("这期已拿到")
            got.setObjectName("Ok")
            h.addWidget(got)
        delete = QToolButton()
        delete.setObjectName("Delete")
        delete.setText("×")
        delete.setToolTip("删除这个奖励")
        delete.setCursor(Qt.PointingHandCursor)
        delete.clicked.connect(lambda _=False, rid=reward.id: self._delete(rid))
        h.addWidget(delete)
        return row

    def _add(self) -> None:
        text = self.text.text().strip()
        if not text:
            self.text.setFocus()
            return
        scope = REWARD_SCOPES[max(0, self._scope_group.checkedId())]
        self.store.add_reward(scope, self.percent.value(), text)
        self.text.clear()
        self.refresh()
        self.text.setFocus()

    def _delete(self, reward_id: int) -> None:
        self.store.delete_reward(reward_id)
        self.refresh()


class EarnedDialog(QDialog):
    """够线了：弹一个置顶的框，把奖励念给你看。"""

    def __init__(self, earned: list[Reward], progress: dict, parent: QWidget | None = None):
        super().__init__(parent)
        self.setWindowTitle("拿到奖励了")
        self.setWindowFlags(self.windowFlags() | Qt.WindowStaysOnTopHint)
        self.setMinimumWidth(380)

        root = QVBoxLayout(self)
        root.setContentsMargins(28, 24, 28, 20)
        root.setSpacing(10)

        top = earned[-1]  # 一次跨过好几档时，标题报最高的那档
        done, total = progress[top.scope]
        head = QLabel(f"🎉 {top.scope.label}任务完成了 {done}/{total}")
        head.setObjectName("Title")
        root.addWidget(head)

        for reward in earned:
            line = QLabel(f"达到 {reward.percent}%  →  <b>{_escape(reward.text)}</b>")
            line.setTextFormat(Qt.RichText)
            line.setWordWrap(True)
            root.addWidget(line)

        sub = QLabel("去兑现吧，这是你自己挣的。")
        sub.setObjectName("Subtitle")
        root.addWidget(sub)

        row = QHBoxLayout()
        row.addStretch()
        ok = QPushButton("收下")
        ok.setObjectName("Primary")
        ok.clicked.connect(self.accept)
        row.addWidget(ok)
        root.addLayout(row)


def _escape(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
