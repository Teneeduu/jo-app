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


ICON_SIZES = (16, 24, 32, 48, 64, 128, 256)


def icon_pixmap(size: int = 64) -> QPixmap:
    """画一个 "jo" 圆角方块。所有比例按 size 缩放，小尺寸下也不糊。"""
    pix = QPixmap(size, size)
    pix.fill(Qt.transparent)
    p = QPainter(pix)
    p.setRenderHint(QPainter.Antialiasing)
    p.setBrush(QColor(ACCENT))
    p.setPen(Qt.NoPen)
    margin = max(1, round(size * 0.031))
    radius = size * 0.22
    p.drawRoundedRect(
        QRect(margin, margin, size - margin * 2, size - margin * 2), radius, radius
    )
    p.setPen(QColor("#ffffff"))
    # 小图标上「jo」两个字母会糊成一团，缩到 24 以下只留一个 j
    text = "jo" if size >= 24 else "j"
    p.setFont(QFont("Segoe UI", max(6, round(size * 0.44)), QFont.Bold))
    p.drawText(QRect(0, 0, size, size), Qt.AlignCenter, text)
    p.end()
    return pix


def app_icon() -> QIcon:
    """多尺寸图标 —— 托盘用 16/24，任务栏用 32/48，通知用大的。"""
    icon = QIcon()
    for size in ICON_SIZES:
        icon.addPixmap(icon_pixmap(size))
    return icon


def write_ico(path) -> str:
    """导出 .ico 给快捷方式用（Qt 自带 ico 写入器）。"""
    from pathlib import Path

    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    if not icon_pixmap(256).save(str(target), "ico"):
        raise RuntimeError(f"写图标失败: {target}")
    return str(target)
