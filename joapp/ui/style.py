"""视觉：一份 QSS + 一个程序生成的托盘图标（不带二进制资源文件）。"""

from __future__ import annotations

from PySide6.QtCore import QRect, Qt
from PySide6.QtGui import QColor, QFont, QIcon, QPainter, QPixmap

BG = "#12141a"
PANEL = "#1a1d26"
TEXT = "#e8e6e3"
MUTED = "#8b90a0"
ACCENT = "#e0533d"
ACCENT_DIM = "#a33d2d"
BORDER = "#2a2e3a"

QSS = f"""
QWidget {{
    background: {BG};
    color: {TEXT};
    font-family: "Microsoft YaHei UI", "Segoe UI", sans-serif;
    font-size: 14px;
}}
#Card {{
    background: {PANEL};
    border: 1px solid {BORDER};
    border-radius: 12px;
}}
#Title {{
    font-size: 20px;
    font-weight: 600;
}}
#Subtitle, #Muted {{
    color: {MUTED};
    font-size: 12px;
}}
QTextEdit, QLineEdit {{
    background: {BG};
    border: 1px solid {BORDER};
    border-radius: 8px;
    padding: 10px;
    selection-background-color: {ACCENT_DIM};
}}
QTextEdit:focus, QLineEdit:focus {{
    border: 1px solid {ACCENT};
}}
QPushButton {{
    background: transparent;
    color: {TEXT};
    border: 1px solid {BORDER};
    border-radius: 8px;
    padding: 8px 16px;
}}
QPushButton:hover {{
    border-color: {ACCENT};
    color: {ACCENT};
}}
QPushButton#Primary {{
    background: {ACCENT};
    border-color: {ACCENT};
    color: #ffffff;
    font-weight: 600;
}}
QPushButton#Primary:hover {{
    background: {ACCENT_DIM};
    border-color: {ACCENT_DIM};
    color: #ffffff;
}}
QListWidget {{
    background: {BG};
    border: 1px solid {BORDER};
    border-radius: 8px;
    padding: 4px;
}}
QListWidget::item {{
    padding: 8px;
    border-radius: 6px;
}}
QListWidget::item:selected {{
    background: {BORDER};
    color: {TEXT};
}}
QProgressBar {{
    background: {BG};
    border: 1px solid {BORDER};
    border-radius: 6px;
    height: 8px;
    text-align: center;
}}
QProgressBar::chunk {{
    background: {ACCENT};
    border-radius: 5px;
}}
QCheckBox {{ spacing: 8px; }}
"""


def app_icon() -> QIcon:
    """画一个 32×32 的 "jo" 方块当图标，省掉打包资源文件。"""
    pix = QPixmap(64, 64)
    pix.fill(Qt.transparent)
    p = QPainter(pix)
    p.setRenderHint(QPainter.Antialiasing)
    p.setBrush(QColor(ACCENT))
    p.setPen(Qt.NoPen)
    p.drawRoundedRect(QRect(2, 2, 60, 60), 14, 14)
    p.setPen(QColor("#ffffff"))
    font = QFont("Segoe UI", 28, QFont.Bold)
    p.setFont(font)
    p.drawText(QRect(0, 0, 64, 64), Qt.AlignCenter, "jo")
    p.end()
    return QIcon(pix)
