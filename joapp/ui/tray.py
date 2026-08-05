"""托盘图标。应用平时就活在这里，没有任务栏窗口。"""

from __future__ import annotations

from PySide6.QtCore import QObject, Signal
from PySide6.QtWidgets import QMenu, QSystemTrayIcon

from .style import app_icon


class Tray(QObject):
    plan_requested = Signal()
    board_requested = Signal()
    break_requested = Signal()
    login_requested = Signal()
    quit_requested = Signal()

    def __init__(self, parent: QObject | None = None):
        super().__init__(parent)
        self.icon = QSystemTrayIcon(app_icon(), self)
        self.icon.setToolTip("jo-app")

        menu = QMenu()
        menu.addAction("今天的清单", self.board_requested.emit)
        menu.addAction("现在规划", self.plan_requested.emit)
        menu.addSeparator()
        self.break_action = menu.addAction("开始休息", self.break_requested.emit)
        menu.addSeparator()
        self.login_action = menu.addAction("连接 Claude…", self.login_requested.emit)
        menu.addSeparator()
        menu.addAction("退出", self.quit_requested.emit)
        self._menu = menu

        self.icon.setContextMenu(menu)
        self.icon.activated.connect(self._on_activated)
        self.icon.show()

    def _on_activated(self, reason) -> None:
        if reason == QSystemTrayIcon.Trigger:  # 左键单击
            self.board_requested.emit()

    def set_on_break(self, on_break: bool) -> None:
        self.break_action.setText("结束休息" if on_break else "开始休息")

    def set_connected(self, connected: bool, detail: str = "") -> None:
        self.login_action.setText("Claude 已连接" if connected else "连接 Claude…")
        self.login_action.setEnabled(not connected)
        self.icon.setToolTip(f"jo-app · {detail}" if detail else "jo-app")

    def notify(self, title: str, body: str) -> None:
        self.icon.showMessage(title, body, app_icon(), 5000)
