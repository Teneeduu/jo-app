"""应用装配：store / 提醒进程 / 窗口 / 托盘接到一起。

启动时：弹出主窗口（每天任务每次打开都要看见），后台拉起提醒进程。
退出时：先把提醒进程杀掉再走。崩溃的情况由 reminder.py 里的 job object 兜底。
"""

from __future__ import annotations

import logging
import sys
from datetime import date

from PySide6.QtCore import QObject, QSharedMemory, QTimer
from PySide6.QtNetwork import QLocalServer, QLocalSocket
from PySide6.QtWidgets import QApplication, QSystemTrayIcon

from .. import APP_NAME, config
from ..core.models import Scope
from ..core.store import Store
from ..reminder import Reminder
from .style import QSS, app_icon
from .tray import Tray
from .window import MainWindow

log = logging.getLogger(__name__)

SINGLE_INSTANCE_KEY = "jo-app-single-instance"
SHOW_SERVER = "jo-app-show-window"
STATUS_POLL_SECONDS = 5


def _claim_single_instance() -> QSharedMemory | None:
    """占住一块共享内存当锁。占不到说明已经有一个在跑了。

    没有这个的话，开机自启撞上手动启动就会变成两个实例 ——
    两个托盘图标、两套提醒一起念，还同时往一个 SQLite 里写。
    """
    lock = QSharedMemory(SINGLE_INSTANCE_KEY)
    if lock.attach():  # 已经有实例持有
        lock.detach()
        return None
    if not lock.create(1):
        return None
    return lock


def _ask_running_instance_to_show() -> None:
    """再双击一次快捷方式 = 把已经在托盘里的那个叫出来，而不是什么都不发生。"""
    sock = QLocalSocket()
    sock.connectToServer(SHOW_SERVER)
    if sock.waitForConnected(1000):
        sock.write(b"show")
        sock.flush()
        sock.waitForBytesWritten(1000)
        sock.disconnectFromServer()


class JoApp(QObject):
    def __init__(self, app: QApplication):
        super().__init__()
        self.app = app
        self.cfg = config.load()
        self.store = Store()
        self.reminder = Reminder(config.REMINDER_LOG)
        self._told_about_tray = False
        self._last_state = ""
        self._day = date.today()

        self.tray = Tray(self)
        self.tray.open_requested.connect(self.open_window)
        self.tray.test_requested.connect(self.test_reminder)
        self.tray.toggle_reminder.connect(
            lambda: self.set_reminder_enabled(not self.cfg.remind_enabled)
        )
        self.tray.quit_requested.connect(self.quit)

        self.window = MainWindow(
            self.store,
            collapsed=list(self.cfg.collapsed),
            minutes=self.cfg.remind_minutes,
            enabled=self.cfg.remind_enabled,
        )
        self.window.hidden_to_tray.connect(self._on_hidden)
        self.window.quit_requested.connect(self.quit)
        self.window.test_reminder.connect(self.test_reminder)
        self.window.reminder_enabled_changed.connect(self.set_reminder_enabled)
        self.window.reminder_minutes_changed.connect(self.set_reminder_minutes)
        self.window.collapsed_changed.connect(self._save_collapsed)

        # 每天任务每次打开都得看见 —— 上次折叠了也展开
        self.window.expand(Scope.DAILY)

        if self.cfg.remind_enabled:
            self.reminder.start(
                self.cfg.remind_voice, self.cfg.remind_popup, self.cfg.remind_minutes
            )
        self._poll()

        self.timer = QTimer(self)
        self.timer.timeout.connect(self._poll)
        self.timer.start(STATUS_POLL_SECONDS * 1000)

        app.aboutToQuit.connect(self.reminder.stop)  # 不管从哪条路退出都收干净

        QLocalServer.removeServer(SHOW_SERVER)  # 上次崩溃留下的同名管道
        self._show_server = QLocalServer(self)
        self._show_server.newConnection.connect(self._on_show_request)
        self._show_server.listen(SHOW_SERVER)
        self.window.bring_up()

    # ---------- 周期检查 ----------

    def _poll(self) -> None:
        # 跨天了：每天任务重置、当天任务换一天，重画一遍
        if date.today() != self._day:
            self._day = date.today()
            self.window.refresh()

        status = self.reminder.status()
        self.window.set_reminder_status(status)
        self.tray.set_reminder(self.cfg.remind_enabled, status.detail)
        if status.state == "failed" and self._last_state != "failed":
            log.warning("提醒进程失败: %s", status.detail)
            self.tray.notify("提醒没跑起来", status.detail)
        self._last_state = status.state

    # ---------- 提醒 ----------

    def set_reminder_enabled(self, enabled: bool) -> None:
        self.cfg.remind_enabled = enabled
        config.save(self.cfg)
        if enabled:
            self.reminder.start(
                self.cfg.remind_voice, self.cfg.remind_popup, self.cfg.remind_minutes
            )
        else:
            self.reminder.stop()
        self.window.set_reminder_enabled(enabled)
        self._poll()

    def set_reminder_minutes(self, minutes: int) -> None:
        if minutes == self.cfg.remind_minutes:
            return
        self.cfg.remind_minutes = minutes
        config.save(self.cfg)
        if self.cfg.remind_enabled:  # 重启一下，从现在开始重新计时
            self.reminder.start(
                self.cfg.remind_voice, self.cfg.remind_popup, minutes
            )
        self._poll()

    def test_reminder(self) -> None:
        self.reminder.fire_now(self.cfg.remind_voice, self.cfg.remind_popup)

    # ---------- 窗口 ----------

    def open_window(self) -> None:
        self.window.bring_up()

    def _on_show_request(self) -> None:
        while self._show_server.hasPendingConnections():
            self._show_server.nextPendingConnection().deleteLater()
        self.window.expand(Scope.DAILY)
        self.open_window()

    def _on_hidden(self) -> None:
        if not self._told_about_tray:
            self._told_about_tray = True
            self.tray.notify(
                "jo-app 还在托盘里", "提醒照常。要彻底退出，右键托盘图标 →「退出」。"
            )

    def _save_collapsed(self, collapsed: list) -> None:
        self.cfg.collapsed = collapsed
        config.save(self.cfg)

    def quit(self) -> None:
        self.timer.stop()
        self._show_server.close()
        self.reminder.stop()
        self.tray.hide()
        self.store.close()
        self.app.quit()


def run(argv: list[str] | None = None) -> int:
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s"
    )
    app = QApplication(argv if argv is not None else sys.argv)

    lock = _claim_single_instance()
    if lock is None:
        log.info("已经有一个 jo-app 在跑了，叫它把窗口拿出来")
        _ask_running_instance_to_show()
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
