"""主窗口：一个输入框 + 四个分组（每天 / 当天 / 每周 / 每年），底下是提醒状态。

每天 / 每周 / 每年分组里显示设好的奖励；勾任务勾到够线时弹框发奖励。
每天任务不按日历清零，「每天」标题旁的「重新开始」按一下才开新一轮；
每周 / 每年照常按日历重置，也有同样的按钮可以提前重来。
鼠标移到任务上，行尾出现 ↑ ↓，调整在分组里的顺序。

加任务就是打一行字回车，不估时间、不拆解。分组标题点一下折叠 / 展开。
关窗口只是缩回托盘 —— 提醒还要接着跑；真退出走「退出」按钮或托盘菜单。
左上角的 📌 把窗口钉在最上层（像 Snipaste 的贴图），再点一下取消。
"""

from __future__ import annotations

from datetime import date

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QCursor, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QButtonGroup,
    QCheckBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from .. import i18n
from ..core.models import REWARD_SCOPES, Reward, Scope, Todo
from ..i18n import t
from ..core.store import Store
from ..reminder import Status
from .rewards import EarnedDialog, RewardsDialog

ORDER = (Scope.DAILY, Scope.TODAY, Scope.WEEKLY, Scope.YEARLY)
OK_COLOR = "#5fb07a"


class _Row(QWidget):
    """一行任务。↑ ↓ 平时藏着，鼠标移上来才出现（位置照样占着，不会一晃一晃）。"""

    def __init__(self):
        super().__init__()
        self.tools = QWidget()
        policy = self.tools.sizePolicy()
        policy.setRetainSizeWhenHidden(True)
        self.tools.setSizePolicy(policy)
        self.tools.setVisible(False)

    def enterEvent(self, event):
        self.tools.setVisible(True)
        super().enterEvent(event)

    def leaveEvent(self, event):
        self.tools.setVisible(False)
        super().leaveEvent(event)

    def showEvent(self, event):
        # 点 ↑ ↓ 之后整个列表会重建，新的这一行就在鼠标底下，
        # 但不动鼠标就收不到 enterEvent —— 不补这一下，想连着往上挪就得晃一下鼠标
        QTimer.singleShot(0, self, self._sync_hover)  # 绑在自己身上：行先被删了就不调
        super().showEvent(event)

    def _sync_hover(self) -> None:
        if self.isVisible() and self.rect().contains(self.mapFromGlobal(QCursor.pos())):
            self.tools.setVisible(True)


class _Section(QWidget):
    """一个分组：可折叠的标题 + 任务行。"""

    toggled = Signal(object, bool)  # (Todo, 勾没勾)
    delete_requested = Signal(object)  # Todo
    collapsed_changed = Signal(object, bool)  # (Scope, 折叠没)
    reset_requested = Signal(object)  # Scope；每天 / 每周 / 每年有
    move_requested = Signal(object, int)  # (Todo, -1 上移 / +1 下移)

    def __init__(self, scope: Scope, collapsed: bool):
        super().__init__()
        self.scope = scope
        self.collapsed = collapsed

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(2)

        self.header = QPushButton()
        self.header.setObjectName("SectionHeader")
        self.header.setCursor(Qt.PointingHandCursor)
        self.header.clicked.connect(self._flip)
        self.round_label: QLabel | None = None
        if scope in REWARD_SCOPES:  # 每天 / 每周 / 每年：可以重来
            top = QHBoxLayout()
            top.setSpacing(6)
            top.addWidget(self.header, 1)
            self.round_label = QLabel("")
            self.round_label.setObjectName("Muted")
            top.addWidget(self.round_label)
            reset = QPushButton(t("↻ 重新开始"))
            reset.setObjectName("Reset")
            reset.setCursor(Qt.PointingHandCursor)
            reset.setToolTip(
                t("{scope}任务全部变回没做，{scope}的奖励可以重新拿", scope=scope.label)
            )
            reset.clicked.connect(lambda: self.reset_requested.emit(self.scope))
            top.addWidget(reset)
            layout.addLayout(top)
        else:
            layout.addWidget(self.header)

        self.body = QWidget()
        body = QVBoxLayout(self.body)
        body.setContentsMargins(4, 2, 0, 6)
        body.setSpacing(2)
        self.reward_label = QLabel("")
        self.reward_label.setObjectName("Reward")
        self.reward_label.setTextFormat(Qt.RichText)
        self.reward_label.setWordWrap(True)
        self.reward_label.setVisible(False)
        body.addWidget(self.reward_label)
        rows = QWidget()
        self._rows = QVBoxLayout(rows)
        self._rows.setContentsMargins(0, 0, 0, 0)
        self._rows.setSpacing(0)
        body.addWidget(rows)
        layout.addWidget(self.body)

        self._todos: list[Todo] = []
        self._apply_collapsed()

    def set_todos(self, todos: list[Todo], today: date) -> None:
        self._todos = todos
        while self._rows.count():
            item = self._rows.takeAt(0)
            if item.widget():
                # 立刻摘掉：光 deleteLater 的话，删之前这一轮还挂在界面上
                old = item.widget()
                old.hide()
                old.setParent(None)
                old.deleteLater()

        if not todos:
            empty = QLabel(t("还没有"))
            empty.setObjectName("Muted")
            self._rows.addWidget(empty)
        for i, todo in enumerate(todos):
            self._rows.addWidget(
                self._row(todo, today, first=i == 0, last=i == len(todos) - 1)
            )
        self._update_header()

    def set_round_started(self, started) -> None:
        """每周 / 每年没手动重来过时是 None —— 那就是按日历，不用写。"""
        if self.round_label is None:
            return
        if started is None:
            self.round_label.clear()
            self.round_label.setToolTip("")
            return
        self.round_label.setText(i18n.round_since(started))
        self.round_label.setToolTip(
            t("这一轮从 {when} 开始", when=f"{started:%Y-%m-%d %H:%M}")
        )

    def set_rewards(self, rewards: list[Reward]) -> None:
        """「🎁 50% 看一集剧 ✓ · 100% 吃顿好的」—— 拿到的标绿打勾。"""
        if not rewards:
            self.reward_label.setVisible(False)
            return
        parts = []
        for w in rewards:
            text = f"{w.percent}% {_escape(w.text)}"
            parts.append(
                f'<span style="color:{OK_COLOR}">{text} ✓</span>' if w.earned else text
            )
        self.reward_label.setText("🎁 " + "  ·  ".join(parts))
        self.reward_label.setVisible(True)

    def _row(self, todo: Todo, today: date, first: bool, last: bool) -> QWidget:
        row = _Row()
        h = QHBoxLayout(row)
        h.setContentsMargins(0, 0, 0, 0)

        box = QCheckBox(todo.title)
        box.setChecked(todo.done)
        _mark_done(box, todo.done)
        box.toggled.connect(lambda checked, t=todo: self.toggled.emit(t, checked))
        h.addWidget(box, 1)

        late = todo.overdue_days(today)
        if late:
            tail = QLabel(t("拖了 {n} 天", n=late))
            tail.setObjectName("Bad")
            h.addWidget(tail)

        tools = QHBoxLayout(row.tools)
        tools.setContentsMargins(0, 0, 0, 0)
        tools.setSpacing(0)
        for text, tip, offset, enabled in (
            ("↑", t("上移"), -1, not first),
            ("↓", t("下移"), +1, not last),
        ):
            btn = QToolButton()
            btn.setObjectName("Move")
            btn.setText(text)
            btn.setToolTip(tip)
            btn.setEnabled(enabled)
            btn.setCursor(Qt.PointingHandCursor)
            btn.clicked.connect(
                lambda _=False, tt=todo, o=offset: self.move_requested.emit(tt, o)
            )
            tools.addWidget(btn)
        h.addWidget(row.tools)

        delete = QToolButton()
        delete.setObjectName("Delete")
        delete.setText("×")
        delete.setToolTip(t("删除"))
        delete.setCursor(Qt.PointingHandCursor)
        delete.clicked.connect(lambda _=False, t=todo: self.delete_requested.emit(t))
        h.addWidget(delete)
        return row

    def _update_header(self) -> None:
        arrow = "▸" if self.collapsed else "▾"
        done = sum(1 for t in self._todos if t.done)
        count = ""
        if self._todos:
            count = f"   {done}/{len(self._todos)}"
            if self.scope in REWARD_SCOPES:
                count += f"  ·  {done * 100 // len(self._todos)}%"
        self.header.setText(f"{arrow}  {self.scope.label}{count}")

    def set_collapsed(self, collapsed: bool) -> None:
        if collapsed != self.collapsed:
            self.collapsed = collapsed
            self._apply_collapsed()
            self.collapsed_changed.emit(self.scope, collapsed)

    def _flip(self) -> None:
        self.set_collapsed(not self.collapsed)

    def _apply_collapsed(self) -> None:
        self.body.setVisible(not self.collapsed)
        self._update_header()


def _escape(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _mark_done(box: QCheckBox, done: bool) -> None:
    font = box.font()
    font.setStrikeOut(done)
    box.setFont(font)
    box.setProperty("done", done)
    box.style().unpolish(box)
    box.style().polish(box)


class MainWindow(QWidget):
    hidden_to_tray = Signal()
    quit_requested = Signal()
    test_reminder = Signal()
    reminder_enabled_changed = Signal(bool)
    reminder_minutes_changed = Signal(int)
    collapsed_changed = Signal(list)  # 当前折叠着的 scope 值列表
    language_toggled = Signal()
    pinned_changed = Signal(bool)
    activity_requested = Signal()
    changed = Signal()  # 勾 / 取消 / 删 / 重新开始之后，活动记录窗口要跟着刷新

    def __init__(
        self,
        store: Store,
        collapsed: list[str],
        minutes: int,
        enabled: bool,
        pinned: bool = False,
    ):
        super().__init__()
        self.store = store
        self.setWindowTitle("jo-app")
        # 还没显示之前设好，第一次出现就是置顶的，不闪
        self.setWindowFlag(Qt.WindowStaysOnTopHint, pinned)
        self.setMinimumSize(420, 480)
        self.resize(480, 720)

        root = QVBoxLayout(self)
        root.setContentsMargins(24, 20, 24, 16)
        root.setSpacing(12)

        top = QHBoxLayout()
        top.setSpacing(8)
        self.pin_btn = QToolButton()
        self.pin_btn.setObjectName("Pin")
        self.pin_btn.setText("📌")
        self.pin_btn.setCheckable(True)
        self.pin_btn.setChecked(pinned)
        self.pin_btn.setCursor(Qt.PointingHandCursor)
        self.pin_btn.toggled.connect(self.set_pinned)
        self._update_pin_tooltip()
        top.addWidget(self.pin_btn)
        title = QLabel("jo-app")
        title.setObjectName("Title")
        top.addWidget(title)
        top.addStretch()
        self.date_label = QLabel("")
        self.date_label.setObjectName("Subtitle")
        top.addWidget(self.date_label)
        # 语言按钮写的是「要切到的那种」，两种语言的人都认得出来
        lang = QPushButton("EN" if i18n.language() == "zh" else "中文")
        lang.setObjectName("Reset")
        lang.setCursor(Qt.PointingHandCursor)
        lang.setToolTip("Switch to English" if i18n.language() == "zh" else "切换到中文")
        lang.clicked.connect(self.language_toggled.emit)
        top.addWidget(lang)
        root.addLayout(top)

        # --- 加任务：一行字 + 选分组，回车就记 ---
        self.input = QLineEdit()
        self.input.setPlaceholderText(t("加个任务，回车记下"))
        self.input.returnPressed.connect(self._add)
        root.addWidget(self.input)

        scopes = QHBoxLayout()
        scopes.setSpacing(6)
        self._scope_group = QButtonGroup(self)
        self._scope_group.setExclusive(True)
        for i, scope in enumerate(ORDER):
            btn = QPushButton(scope.label)
            btn.setObjectName("Scope")
            btn.setCheckable(True)
            btn.setToolTip(f"Ctrl+{i + 1}")
            btn.setFocusPolicy(Qt.NoFocus)  # 焦点留在输入框，选完直接接着打字
            self._scope_group.addButton(btn, i)
            scopes.addWidget(btn)
            QShortcut(QKeySequence(f"Ctrl+{i + 1}"), self, activated=btn.click)
        self._scope_group.button(ORDER.index(Scope.TODAY)).setChecked(True)
        scopes.addStretch()
        add = QPushButton(t("添加"))
        add.setObjectName("Primary")
        add.clicked.connect(self._add)
        scopes.addWidget(add)
        root.addLayout(scopes)

        # --- 四个分组 ---
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        host = QWidget()
        body = QVBoxLayout(host)
        body.setContentsMargins(0, 0, 8, 0)
        body.setAlignment(Qt.AlignTop)
        body.setSpacing(4)
        self.sections: dict[Scope, _Section] = {}
        for scope in ORDER:
            section = _Section(scope, scope.value in collapsed)
            section.toggled.connect(self._toggle)
            section.delete_requested.connect(self._delete)
            section.collapsed_changed.connect(self._emit_collapsed)
            section.reset_requested.connect(self._reset)
            section.move_requested.connect(self._move)
            body.addWidget(section)
            self.sections[scope] = section
        scroll.setWidget(host)
        root.addWidget(scroll, 1)

        # --- 提醒 ---
        line = QFrame()
        line.setFrameShape(QFrame.HLine)
        line.setObjectName("Muted")
        root.addWidget(line)

        remind = QHBoxLayout()
        remind.addWidget(QLabel(t("提醒：每")))
        self.minutes = QSpinBox()
        self.minutes.setRange(1, 600)
        self.minutes.setValue(minutes)
        self.minutes.setSuffix(t(" 分钟"))
        self.minutes.editingFinished.connect(
            lambda: self.reminder_minutes_changed.emit(self.minutes.value())
        )
        remind.addWidget(self.minutes)
        remind.addStretch()
        test = QPushButton(t("试一下"))
        test.setToolTip(t("立刻念一遍、弹一次框"))
        test.clicked.connect(self.test_reminder.emit)
        remind.addWidget(test)
        self.enable_btn = QPushButton()
        self.enable_btn.clicked.connect(
            lambda: self.reminder_enabled_changed.emit(not self._enabled)
        )
        remind.addWidget(self.enable_btn)
        root.addLayout(remind)

        bottom = QHBoxLayout()
        self.status = QLabel("")
        self.status.setWordWrap(True)
        bottom.addWidget(self.status, 1)
        activity_btn = QPushButton(t("📅 记录"))
        activity_btn.setToolTip(t("活动记录：像 GitHub 那样看每天做了哪些事"))
        activity_btn.clicked.connect(self.activity_requested.emit)
        bottom.addWidget(activity_btn)
        rewards_btn = QPushButton(t("🎁 奖励"))
        rewards_btn.setToolTip(t("给每天 / 每周 / 每年的完成度设奖励"))
        rewards_btn.clicked.connect(self.open_rewards)
        bottom.addWidget(rewards_btn)
        quit_btn = QPushButton(t("退出"))
        quit_btn.setToolTip(t("退出 jo-app，后台提醒一起关掉"))
        quit_btn.clicked.connect(self.quit_requested.emit)
        bottom.addWidget(quit_btn)
        root.addLayout(bottom)

        self._enabled = enabled
        self.set_reminder_enabled(enabled)
        self.refresh()

    # ---------- 数据 ----------

    def refresh(self) -> None:
        today = date.today()
        self.date_label.setText(i18n.date_line(today))
        for scope, section in self.sections.items():
            section.set_todos(self.store.todos(scope, today), today)
            if scope in REWARD_SCOPES:
                section.set_rewards(self.store.rewards(scope, today))
        for scope in REWARD_SCOPES:
            self.sections[scope].set_round_started(self.store.round_started(scope, today))

    def _current_scope(self) -> Scope:
        return ORDER[max(0, self._scope_group.checkedId())]

    def _add(self) -> None:
        title = self.input.text().strip()
        if not title:
            return
        scope = self._current_scope()
        self.store.add(title, scope)
        self.input.clear()
        self.sections[scope].set_collapsed(False)  # 刚加的得看得见
        self.refresh()
        self.input.setFocus()

    def _toggle(self, todo: Todo, checked: bool) -> None:
        self.store.set_done(todo, checked)
        self.refresh()
        self.changed.emit()
        if checked and todo.scope in REWARD_SCOPES:
            self._celebrate(todo.scope)

    def _reset(self, scope: Scope) -> None:
        done, total = self.store.progress(scope)
        text = t(
            "开始新一轮{scope}任务？\n\n这一轮做完了 {done}/{total} 件。重新开始后：\n"
            "· {scope}任务全部变回没做\n· {scope}的奖励可以重新拿\n\n其他分组不受影响。",
            scope=scope.label,
            done=done,
            total=total,
        )
        if scope is Scope.WEEKLY:
            text += t("\n\n到了下周一也会照常自动重新开始。")
        elif scope is Scope.YEARLY:
            text += t("\n\n到了明年也会照常自动重新开始。")
        if QMessageBox.question(self, t("重新开始"), text) == QMessageBox.Yes:
            self.store.reset(scope)
            self.expand(scope)
            self.refresh()
            self.changed.emit()

    def _move(self, todo: Todo, offset: int) -> None:
        if self.store.move(todo, offset):
            self.refresh()

    # ---------- 奖励 ----------

    def open_rewards(self) -> None:
        RewardsDialog(self.store, self).exec()
        self.refresh()
        # 新设的奖励可能已经够线了（比如今天已经做完一半再设 50%）—— 当场发
        for scope in REWARD_SCOPES:
            self._celebrate(scope)

    def _celebrate(self, scope: Scope) -> None:
        earned = self.store.claim_reached(scope)
        if not earned:
            return
        self.refresh()  # 分组里的奖励要标成已拿到
        self.changed.emit()  # 奖励也记进活动记录
        EarnedDialog(earned, {scope: self.store.progress(scope)}, self).exec()

    def _delete(self, todo: Todo) -> None:
        note = (
            ""
            if todo.scope is Scope.TODAY
            else t("\n\n这是{scope}都会出现的任务，删了以后就不再出现。", scope=todo.scope.label)
        )
        answer = QMessageBox.question(
            self, t("删除任务"), t("删掉「{title}」？", title=todo.title) + note
        )
        if answer == QMessageBox.Yes:
            self.store.delete(todo.id)
            self.refresh()
            self.changed.emit()

    def _emit_collapsed(self, *_):
        self.collapsed_changed.emit(
            [s.value for s, sec in self.sections.items() if sec.collapsed]
        )

    def expand(self, scope: Scope) -> None:
        self.sections[scope].set_collapsed(False)

    # ---------- 提醒状态 ----------

    def set_reminder_enabled(self, enabled: bool) -> None:
        self._enabled = enabled
        self.enable_btn.setText(t("暂停") if enabled else t("开启"))
        self.minutes.setEnabled(enabled)

    def set_reminder_status(self, status: Status) -> None:
        if status.state == "off":
            self.status.setObjectName("Muted")
            self.status.setText(t("提醒已暂停"))
        elif status.ok:
            self.status.setObjectName("Ok")
            self.status.setText(t("● 提醒在后台运行 · {detail}", detail=status.detail))
        else:
            self.status.setObjectName("Bad")
            self.status.setText(t("✕ 提醒没跑起来：{detail}", detail=status.detail))
        self.status.style().unpolish(self.status)
        self.status.style().polish(self.status)

    # ---------- 窗口 ----------

    @property
    def pinned(self) -> bool:
        return bool(self.windowFlags() & Qt.WindowStaysOnTopHint)

    def set_pinned(self, pinned: bool) -> None:
        """钉在最上层 / 取消。

        用 Qt 的 WindowStaysOnTopHint 而不是直接调 SetWindowPos(HWND_TOPMOST)：
        Qt 自己在 raise / activate / 隐藏再显示时会重设 Z 序，绕开它设的置顶会被冲掉；
        走 Qt 的标志，这些情况下都能保持，从这个窗口弹出的确认框也跟着置顶。
        改这个标志会让 Qt 把窗口藏一下（句柄不变），所以原来显示着就马上再 show。
        """
        if self.pin_btn.isChecked() != pinned:
            self.pin_btn.setChecked(pinned)  # 会再进来一次，下面接着做
            return
        if pinned == self.pinned:
            return
        visible = self.isVisible()
        self.setWindowFlag(Qt.WindowStaysOnTopHint, pinned)
        if visible:
            self.show()
        self._update_pin_tooltip()
        self.pinned_changed.emit(pinned)

    def _update_pin_tooltip(self) -> None:
        self.pin_btn.setToolTip(
            t("取消置顶") if self.pin_btn.isChecked() else t("置顶：窗口一直浮在最上层")
        )

    # 真要退出（「退出」按钮、托盘、关机注销）时由 JoApp 打开，放行关窗口。
    # 不放行的话 Qt 6 的 quit() 会被这个窗口否决 —— 点了「退出」却时灵时不灵。
    allow_close = False

    def closeEvent(self, event):
        """关窗口 = 缩回托盘。提醒还要接着跑。"""
        if self.allow_close:
            event.accept()
            return
        event.ignore()
        self.hide()
        self.hidden_to_tray.emit()

    def bring_up(self) -> None:
        self.refresh()
        self.show()
        self.setWindowState(self.windowState() & ~Qt.WindowMinimized)
        self.raise_()
        self.activateWindow()
        self.input.setFocus()
