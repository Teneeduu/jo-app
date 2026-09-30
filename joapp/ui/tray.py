"""托盘图标。窗口关掉之后应用就活在这里，提醒照常。"""

from __future__ import annotations

from PySide6.QtCore import QObject, Signal
from PySide6.QtWidgets import QMenu, QSystemTrayIcon

from .style import app_icon


class Tray(QObject):
    open_requested = Signal()
    activity_requested = Signal()
    test_requested = Signal()
    toggle_reminder = Signal()
    quit_requested = Signal()

    def __init__(self, parent: QObject | None = None):
        super().__init__(parent)
        self.icon = QSystemTrayIcon(app_icon(), self)
        self.icon.setToolTip("jo-app")

        menu = QMenu()
        menu.addAction("打开清单", self.open_requested.emit)
        menu.addAction("活动记录", self.activity_requested.emit)
        menu.addSeparator()
        menu.addAction("试一下提醒", self.test_requested.emit)
        self.remind_action = menu.addAction("暂停提醒", self.toggle_reminder.emit)
        menu.addSeparator()
        menu.addAction("退出（提醒一起关）", self.quit_requested.emit)
        self._menu = menu

        self.icon.setContextMenu(menu)
        self.icon.activated.connect(self._on_activated)
        self.icon.show()

    def _on_activated(self, reason) -> None:
        if reason in (QSystemTrayIcon.Trigger, QSystemTrayIcon.DoubleClick):
            self.open_requested.emit()

    def set_reminder(self, enabled: bool, detail: str = "") -> None:
        self.remind_action.setText("暂停提醒" if enabled else "开启提醒")
        self.icon.setToolTip(f"jo-app · {detail}" if detail else "jo-app")

    def notify(self, title: str, body: str) -> None:
        self.icon.showMessage(title, body, app_icon(), 5000)

    def hide(self) -> None:
        self.icon.hide()
