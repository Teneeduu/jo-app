"""托盘图标。窗口关掉之后应用就活在这里，提醒照常。"""

from __future__ import annotations

from PySide6.QtCore import QObject, Signal
from PySide6.QtWidgets import QMenu, QSystemTrayIcon

from .. import i18n
from ..i18n import t
from .style import app_icon


class Tray(QObject):
    open_requested = Signal()
    activity_requested = Signal()
    test_requested = Signal()
    toggle_reminder = Signal()
    quit_requested = Signal()
    language_toggled = Signal()

    def __init__(self, parent: QObject | None = None):
        super().__init__(parent)
        self.icon = QSystemTrayIcon(app_icon(), self)
        self.icon.setToolTip("jo-app")

        self._menu = QMenu()
        self._enabled = True
        self.build_menu()
        self.icon.setContextMenu(self._menu)
        self.icon.activated.connect(self._on_activated)
        self.icon.show()

    def build_menu(self) -> None:
        """切语言时重建一遍。"""
        menu = self._menu
        menu.clear()
        menu.addAction(t("打开清单"), self.open_requested.emit)
        menu.addAction(t("活动记录"), self.activity_requested.emit)
        menu.addSeparator()
        menu.addAction(t("试一下提醒"), self.test_requested.emit)
        self.remind_action = menu.addAction("", self.toggle_reminder.emit)
        menu.addSeparator()
        menu.addAction(
            "English" if i18n.language() == "zh" else "中文", self.language_toggled.emit
        )
        menu.addSeparator()
        menu.addAction(t("退出（提醒一起关）"), self.quit_requested.emit)
        self.set_reminder(self._enabled)

    def _on_activated(self, reason) -> None:
        if reason in (QSystemTrayIcon.Trigger, QSystemTrayIcon.DoubleClick):
            self.open_requested.emit()

    def set_reminder(self, enabled: bool, detail: str = "") -> None:
        self._enabled = enabled
        self.remind_action.setText(t("暂停提醒") if enabled else t("开启提醒"))
        self.icon.setToolTip(f"jo-app · {detail}" if detail else "jo-app")

    def notify(self, title: str, body: str) -> None:
        self.icon.showMessage(title, body, app_icon(), 5000)

    def hide(self) -> None:
        self.icon.hide()
