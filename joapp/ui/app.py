"""应用装配：把 store / planner / tracker / 界面接到一起。

主循环很简单 —— 每 TICK_SECONDS 秒取一次空闲时长喂给 FocusTracker，
然后拍一张 Snapshot 问 Planner「现在该说点什么吗」。
问的过程可能走网络，所以放后台线程。
"""

from __future__ import annotations

import logging
import sys
from datetime import date, datetime, timedelta

from PySide6.QtCore import QObject, QSharedMemory, QThread, QTimer, Signal
from PySide6.QtWidgets import QApplication, QSystemTrayIcon

from .. import APP_NAME, config
from ..agent import auth
from ..agent.planner import Planner
from ..agent.rules import COOLDOWN, Snapshot
from ..core.models import Nudge, NudgeKind, TaskStatus
from ..core.store import Store
from ..scheduler import FocusTracker, Phase, idle_minutes
from .board import DayBoard
from .connect import ConnectDialog
from .morning import MorningWindow
from .nudge import NudgeToast
from .style import QSS, app_icon
from .tray import Tray

log = logging.getLogger(__name__)

TICK_SECONDS = 20
SINGLE_INSTANCE_KEY = "jo-app-single-instance"


def _claim_single_instance() -> QSharedMemory | None:
    """占住一块共享内存当锁。占不到说明已经有一个在跑了。

    没有这个的话，开机自启撞上手动启动就会变成两个实例 ——
    两个托盘图标、两个定时器，还同时往一个 SQLite 里写。
    """
    lock = QSharedMemory(SINGLE_INSTANCE_KEY)
    if lock.attach():  # 已经有实例持有
        lock.detach()
        return None
    if not lock.create(1):
        return None
    return lock


class _NudgeWorker(QThread):
    """在后台问 Planner 要不要提醒（可能触发一次 API 调用）。"""

    ready = Signal(object)

    def __init__(self, planner: Planner, snapshot: Snapshot):
        super().__init__()
        self.planner = planner
        self.snapshot = snapshot

    def run(self) -> None:  # pragma: no cover - 线程体
        try:
            self.ready.emit(self.planner.next_nudge(self.snapshot))
        except Exception:
            log.exception("生成提醒时出错")
            self.ready.emit(None)


class JoApp(QObject):
    def __init__(self, app: QApplication):
        super().__init__()
        self.app = app
        self.cfg = config.load()
        self.store = Store()
        self.planner = Planner(self.cfg, self.store)
        self.tracker = FocusTracker(
            idle_threshold_minutes=self.cfg.idle_threshold_minutes
        )

        self.tray = Tray(self)
        self.tray.plan_requested.connect(self.open_morning)
        self.tray.board_requested.connect(self.open_board)
        self.tray.break_requested.connect(self.toggle_break)
        self.tray.login_requested.connect(self.connect_claude)
        self.tray.quit_requested.connect(self.quit)

        self.board = DayBoard(self.store, self.planner)
        self.board.plan_requested.connect(self.open_morning)
        self.board.login_requested.connect(self.connect_claude)

        self._morning: MorningWindow | None = None
        self._connect_dialog: ConnectDialog | None = None
        self._toast: NudgeToast | None = None
        self._worker: _NudgeWorker | None = None
        self._day = date.today()
        self._was_connected = False
        self._refresh_auth_state(notify=False)  # 启动时别为「本来就连着」弹通知

        self.timer = QTimer(self)
        self.timer.timeout.connect(self.tick)
        self.timer.start(TICK_SECONDS * 1000)

        # 开机启动时如果今天还没规划，直接把晨间窗口顶上来
        QTimer.singleShot(1500, self._greet_if_needed)

    # ---------- 主循环 ----------

    def tick(self) -> None:
        now = datetime.now()
        if now.date() != self._day:  # 跨天了，重置计时
            self._day = now.date()
            self.tracker.reset()

        self.tracker.tick(idle_minutes(), now)
        self.tray.set_on_break(self.tracker.phase is Phase.BREAK)
        self._refresh_auth_state()

        if self._toast is not None or self._worker is not None:
            return  # 上一条还没处理完，不叠加

        snapshot = self._snapshot(now)
        self._worker = _NudgeWorker(self.planner, snapshot)
        self._worker.ready.connect(self._on_nudge)
        self._worker.finished.connect(self._clear_worker)
        self._worker.start()

    def _clear_worker(self) -> None:
        self._worker = None

    def _snapshot(self, now: datetime) -> Snapshot:
        return Snapshot(
            now=now,
            cfg=self.cfg,
            tasks=self.store.tasks_for(now.date()),
            goals=self.store.goals(),
            planned_today=self.store.planned_today(),
            focus_streak_minutes=self.tracker.focus_minutes,
            idle_minutes=idle_minutes(),
            on_break=self.tracker.phase is Phase.BREAK,
            break_elapsed_minutes=self.tracker.break_minutes,
            last_nudge={
                kind: at
                for kind in COOLDOWN
                if (at := self.store.last_nudge_at(kind.value)) is not None
            },
        )

    # ---------- 提醒 ----------

    def _on_nudge(self, nudge: Nudge | None) -> None:
        if nudge is None:
            return
        if nudge.kind is NudgeKind.PLAN:
            self.open_morning()
            return
        toast = NudgeToast(nudge, self.cfg.nudge_seconds)
        toast.action_chosen.connect(self._on_action)
        toast.show_at_corner()
        self._toast = toast

    def _on_action(self, action: str, nudge: Nudge) -> None:
        self._toast = None  # 气泡设了 WA_DeleteOnClose，这里必须自己松手
        kind = nudge.kind
        if kind is NudgeKind.BREAK:
            if action.startswith("好"):
                self.tracker.start_break()
            else:
                self.tracker.snooze(10)
        elif kind is NudgeKind.RESUME:
            if action.startswith("开始"):
                self.tracker.end_break()
            else:
                self.tracker.break_minutes = max(0.0, self.tracker.break_minutes - 5)
        elif kind is NudgeKind.REVIEW and action.startswith("顺延"):
            self.carry_over()
        elif kind is NudgeKind.GOAL and action.startswith(("更新", "改个", "今天推")):
            self.open_board()
        elif kind is NudgeKind.IDLE and action.startswith("今天到此"):
            self.tracker.reset()
        self.tray.set_on_break(self.tracker.phase is Phase.BREAK)

    # ---------- 动作 ----------

    def _greet_if_needed(self) -> None:
        if not self.store.planned_today():
            self.open_morning()

    def open_morning(self) -> None:
        if self._morning is not None and self._morning.isVisible():
            self._morning.raise_()
            self._morning.activateWindow()
            return
        greeting = (
            "今天打算干点什么？"
            if not self.store.planned_today()
            else "还想加点什么？"
        )
        window = MorningWindow(self.planner, greeting)
        window.tasks_confirmed.connect(self._save_tasks)
        window.login_requested.connect(self.connect_claude)
        window.show()
        window.raise_()
        window.activateWindow()
        self._morning = window

    def _save_tasks(self, tasks: list) -> None:
        for task in tasks:
            self.store.add_task(task)
        self.board.refresh()
        total = sum(t.estimate_minutes for t in tasks)
        self.tray.notify(
            f"记下了 {len(tasks)} 件事", f"预计 {total} 分钟。慢慢来，我盯着时间。"
        )

    def open_board(self) -> None:
        self.board.refresh()
        self.board.show()
        self.board.raise_()
        self.board.activateWindow()

    def _refresh_auth_state(self, notify: bool = True) -> None:
        """凭据可能在应用跑着的时候才出现（用户去 ant auth login 了）。"""
        creds = self.planner.credentials
        connected = creds.available and self.cfg.llm_enabled
        self.tray.set_connected(connected, creds.detail)
        if self._morning is not None and self._morning.isVisible():
            self._morning.set_online(self.planner.llm_working)
        if self.board.isVisible():
            self.board._refresh_auth()
        if notify and connected and not self._was_connected:
            self.tray.notify("Claude 接上了", creds.detail)
        self._was_connected = connected

    def connect_claude(self) -> None:
        """弹对话框。以前这里只发一条托盘气泡 —— 气泡会被吞，用户看到的就是
        「按钮点了没反应」。主 CTA 必须弹出一定看得见的东西。"""
        creds = self.planner.credentials
        if creds.available:
            self.tray.notify("已经连上了", creds.detail)
            return
        if self._connect_dialog is not None and self._connect_dialog.isVisible():
            self._connect_dialog.raise_()
            self._connect_dialog.activateWindow()
            return
        dialog = ConnectDialog()
        dialog.connected.connect(lambda: self._refresh_auth_state())
        dialog.finished.connect(lambda _: self._refresh_auth_state())
        dialog.show()
        dialog.raise_()
        dialog.activateWindow()
        self._connect_dialog = dialog

    def toggle_break(self) -> None:
        if self.tracker.phase is Phase.BREAK:
            self.tracker.end_break()
        else:
            self.tracker.start_break()
        self.tray.set_on_break(self.tracker.phase is Phase.BREAK)

    def carry_over(self) -> None:
        """把今天没做完的顺延到明天。"""
        tomorrow = date.today() + timedelta(days=1)
        moved = 0
        for task in self.store.open_tasks():
            self.store.set_task_status(task.id, TaskStatus.DROPPED)
            task.id, task.day = None, tomorrow
            self.store.add_task(task)
            moved += 1
        if moved:
            self.tray.notify("已顺延", f"{moved} 件事挪到了明天。")

    def quit(self) -> None:
        self.timer.stop()
        self.store.close()
        self.app.quit()


def run(argv: list[str] | None = None) -> int:
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s"
    )
    app = QApplication(argv if argv is not None else sys.argv)

    lock = _claim_single_instance()
    if lock is None:
        log.info("已经有一个 jo-app 在跑了，退出")
        return 0
    app._instance_lock = lock  # 挂在 app 上，别被 GC 掉

    app.setApplicationName(APP_NAME)
    app.setWindowIcon(app_icon())
    app.setStyleSheet(QSS)
    app.setQuitOnLastWindowClosed(False)  # 关窗口不退出，缩回托盘

    if not QSystemTrayIcon.isSystemTrayAvailable():
        log.warning("系统托盘不可用，仍然继续启动")

    jo = JoApp(app)
    app._jo = jo  # 防止被 GC
    return app.exec()
