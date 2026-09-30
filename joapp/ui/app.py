"""应用装配：store / 提醒进程 / 窗口 / 托盘接到一起。

启动时：弹出主窗口（每天任务每次打开都要看见），后台拉起提醒进程。
退出时：先把提醒进程杀掉再走。崩溃的情况由 reminder.py 里的 job object 兜底。
"""

from __future__ import annotations

import ctypes
import hashlib
import logging
import os
import sys
from datetime import date

from PySide6.QtCore import QLibraryInfo, QLocale, QObject, QSharedMemory, QTimer, QTranslator
from PySide6.QtNetwork import QLocalServer, QLocalSocket
from PySide6.QtWidgets import QApplication, QSystemTrayIcon

from .. import APP_NAME, config
from ..core.models import Scope
from ..core.store import Store
from ..reminder import Reminder
from .activity import ActivityWindow
from .style import QSS, app_icon
from .tray import Tray
from .window import MainWindow

log = logging.getLogger(__name__)

def _instance_suffix() -> str:
    """平时全机一个实例。设了 JOAPP_HOME（开发 / 测试用另一份数据）时按数据目录分开，
    不然测试版一启动就被正在用的那个挡回去。"""
    home = os.environ.get("JOAPP_HOME")
    if not home:
        return ""
    return "-" + hashlib.sha1(os.path.abspath(home).lower().encode()).hexdigest()[:8]


SINGLE_INSTANCE_KEY = "jo-app-single-instance" + _instance_suffix()
SHOW_SERVER = "jo-app-show-window" + _instance_suffix()
# 安装程序（packaging/installer.iss 的 AppMutex）靠这个名字判断 jo-app 还开着没，
# 开着就先请用户退出再装 / 卸 —— 不然 exe 被占着，覆盖不了。两边的名字要一致。
INSTALLER_MUTEX = "jo-app-running"
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


def _hold_installer_mutex():
    if os.name != "nt":
        return None
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.CreateMutexW.restype = ctypes.c_void_p
    return kernel32.CreateMutexW(None, False, INSTALLER_MUTEX)


def _setup_logging() -> None:
    """打包成 exe（无控制台）时 stderr 是 None，日志写进数据目录，别的电脑上出问题有据可查。"""
    fmt = "%(asctime)s %(levelname)s %(name)s: %(message)s"
    if sys.stderr is None or getattr(sys, "frozen", False):
        logging.basicConfig(
            level=logging.INFO,
            format=fmt,
            filename=config.data_dir() / "jo-app.log",
            filemode="w",  # 每次启动重写，别无限长大
            encoding="utf-8",
        )
    else:
        logging.basicConfig(level=logging.INFO, format=fmt)


def _install_chinese_qt(app: QApplication) -> None:
    """Qt 自带的按钮（确认框的 Yes / No 之类）换成中文。找不到翻译文件就算了，不影响用。"""
    translator = QTranslator(app)
    path = QLibraryInfo.path(QLibraryInfo.TranslationsPath)
    if translator.load(QLocale(QLocale.Chinese, QLocale.China), "qtbase", "_", path):
        app.installTranslator(translator)
    else:
        log.info("没找到 qtbase 中文翻译（%s），Qt 自带按钮保持英文", path)


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
        self.tray.activity_requested.connect(self.open_activity)
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
        self.window.activity_requested.connect(self.open_activity)
        self.window.changed.connect(self._refresh_activity)
        self._activity: ActivityWindow | None = None

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
        # 关机 / 注销时 Windows 会来问能不能关：放行，别让缩回托盘的逻辑挡着
        app.commitDataRequest.connect(self._allow_close)

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
            self._refresh_activity()

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

    def open_activity(self) -> None:
        if self._activity is None:
            self._activity = ActivityWindow(self.store)
        self._activity.bring_up()

    def _refresh_activity(self) -> None:
        if self._activity is not None and self._activity.isVisible():
            self._activity.refresh()

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

    def _allow_close(self, *_) -> None:
        self.window.allow_close = True

    def quit(self) -> None:
        self._allow_close()
        self.timer.stop()
        self._show_server.close()
        self.reminder.stop()
        self.tray.hide()
        if self._activity is not None:
            self._activity.close()
        self.window.close()
        self.store.close()
        # exit() 而不是 quit()：Qt 6 的 quit() 只是「请求」，会先挨个问窗口能不能关，
        # 有一个不同意就作罢。这里已经收拾完了，直接结束事件循环。
        self.app.exit(0)


def run(argv: list[str] | None = None) -> int:
    _setup_logging()
    app = QApplication(argv if argv is not None else sys.argv)

    lock = _claim_single_instance()
    if lock is None:
        log.info("已经有一个 jo-app 在跑了，叫它把窗口拿出来")
        _ask_running_instance_to_show()
        return 0
    app._instance_lock = lock  # 挂在 app 上，别被 GC 掉
    app._installer_mutex = _hold_installer_mutex()  # 进程退出时系统自动释放

    app.setApplicationName(APP_NAME)
    _install_chinese_qt(app)
    app.setWindowIcon(app_icon())
    app.setStyleSheet(QSS)
    app.setQuitOnLastWindowClosed(False)  # 关窗口不退出，缩回托盘

    if not QSystemTrayIcon.isSystemTrayAvailable():
        log.warning("系统托盘不可用，仍然继续启动")

    jo = JoApp(app)
    app._jo = jo  # 防止被 GC
    return app.exec()
