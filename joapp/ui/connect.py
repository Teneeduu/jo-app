"""连接 Claude 的对话框。

之前这里是一句托盘气泡通知 —— 而气泡会被专注助手吞掉、也可能一闪而过，
用户看到的就是「按钮点了没反应」。主 CTA 必须弹出一个一定看得见的东西，
并且把两条路都做成能当场点完的，而不是让人自己去翻文档。
"""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QDesktopServices
from PySide6.QtCore import QUrl
from PySide6.QtWidgets import (
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
)

from ..agent import auth


class ConnectDialog(QDialog):
    """连上了就发 connected()，让上层去刷新状态。"""

    connected = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("连接 Claude")
        self.setMinimumWidth(460)
        self.setModal(True)

        root = QVBoxLayout(self)
        root.setContentsMargins(24, 24, 24, 20)
        root.setSpacing(14)

        title = QLabel("连接 Claude")
        title.setObjectName("Title")
        root.addWidget(title)

        blurb = QLabel(
            "连上之后就能直接说人话 —— 「上午写完报告，下午看两章书」这种，"
            "它会自己拆成任务。不连也能用，但得按格式一行写一件事。"
        )
        blurb.setObjectName("Subtitle")
        blurb.setWordWrap(True)
        root.addWidget(blurb)

        root.addWidget(self._rule())

        # --- 路线一：浏览器登录 ---
        has_cli = auth.cli_path() is not None
        way1 = QLabel("① 浏览器登录（推荐）")
        way1.setObjectName("Title")
        way1.setStyleSheet("font-size: 15px;")
        root.addWidget(way1)

        desc1 = QLabel(
            "凭据存在系统里、会自动续期，不用管密钥。"
            + ("" if has_cli else "\n还需要装一个 ant CLI，我可以帮你装（约 1 分钟）。")
        )
        desc1.setObjectName("Subtitle")
        desc1.setWordWrap(True)
        root.addWidget(desc1)

        row1 = QHBoxLayout()
        self.login_btn = QPushButton("登录" if has_cli else "自动安装并登录")
        self.login_btn.setObjectName("Primary")
        self.login_btn.clicked.connect(self._on_login)
        row1.addWidget(self.login_btn)
        manual = QPushButton("手动下载")
        manual.clicked.connect(
            lambda: QDesktopServices.openUrl(QUrl(auth.DOWNLOAD_URL))
        )
        row1.addWidget(manual)
        row1.addStretch()
        root.addLayout(row1)

        root.addWidget(self._rule())

        # --- 路线二：API key ---
        way2 = QLabel("② 直接粘 API key")
        way2.setObjectName("Title")
        way2.setStyleSheet("font-size: 15px;")
        root.addWidget(way2)

        desc2 = QLabel("存进用户环境变量，不会写进 jo-app 的配置文件。")
        desc2.setObjectName("Subtitle")
        desc2.setWordWrap(True)
        root.addWidget(desc2)

        row2 = QHBoxLayout()
        self.key_input = QLineEdit()
        self.key_input.setPlaceholderText("sk-ant-...")
        self.key_input.setEchoMode(QLineEdit.Password)
        self.key_input.returnPressed.connect(self._on_save_key)
        row2.addWidget(self.key_input, 1)
        save = QPushButton("保存")
        save.clicked.connect(self._on_save_key)
        row2.addWidget(save)
        root.addLayout(row2)

        get_key = QPushButton("去控制台拿一个")
        get_key.setFlat(True)
        get_key.setObjectName("Muted")
        get_key.clicked.connect(
            lambda: QDesktopServices.openUrl(QUrl(auth.CONSOLE_URL))
        )
        root.addWidget(get_key, 0, Qt.AlignLeft)

        self.status = QLabel("")
        self.status.setObjectName("Subtitle")
        self.status.setWordWrap(True)
        root.addWidget(self.status)

        close_row = QHBoxLayout()
        close_row.addStretch()
        close = QPushButton("关闭")
        close.clicked.connect(self.reject)
        close_row.addWidget(close)
        root.addLayout(close_row)

    def _rule(self) -> QFrame:
        line = QFrame()
        line.setFrameShape(QFrame.HLine)
        line.setStyleSheet("color: #2a2e3a;")
        return line

    # --- 动作 ---

    def _on_login(self) -> None:
        if auth.cli_path():
            ok = auth.launch_login()
            msg = (
                "已经打开浏览器，完成登录就行 —— 登录完不用重启，我会自己发现。"
                if ok
                else "启动 ant 失败了，试试手动下载。"
            )
        else:
            ok = auth.launch_install_and_login()
            msg = (
                "已经开了一个窗口在装 ant，装完会自动跳转登录。整个过程大概一分钟。"
                if ok
                else "自动安装没能启动，点「手动下载」吧。"
            )
        self.status.setText(msg)
        self.login_btn.setEnabled(not ok)

    def _on_save_key(self) -> None:
        value = self.key_input.text().strip()
        if not value:
            self.status.setText("先把 key 粘进来。")
            return
        if not auth.looks_like_api_key(value):
            self.status.setText(
                "这不太像一个 API key（正常以 sk-ant- 开头）。确认一下再存。"
            )
            return
        try:
            auth.save_api_key(value)
        except OSError as e:
            self.status.setText(f"保存失败：{e}")
            return
        self.key_input.clear()
        self.status.setText("存好了，已经生效。")
        self.connected.emit()
        self.accept()
