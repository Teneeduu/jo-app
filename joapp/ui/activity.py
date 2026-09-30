"""活动记录：跟 GitHub 贡献图一样的格子，点某一天看那天做了哪些事。

一格一天，颜色越深那天做完的事越多。右边切「过去一年」/ 某一年。
"""

from __future__ import annotations

from datetime import date

from PySide6.QtCore import QPoint, QRect, QSize, Qt, Signal
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import (
    QButtonGroup,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QToolTip,
    QVBoxLayout,
    QWidget,
)

from .. import i18n
from ..core import stats
from ..core.store import Store
from ..i18n import t
from .style import MUTED, TEXT

# 暗色主题下的 GitHub 绿，0 = 没有记录
COLORS = ["#232733", "#0e4429", "#006d32", "#26a641", "#39d353"]
REWARD_COLOR = "#d9a441"

CELL = 11
GAP = 3
STEP = CELL + GAP
LEFT = 30  # 左边写「一 三 五」/ Mon Wed Fri
TOP = 18  # 上边写月份


def _discard(widget: QWidget) -> None:
    """立刻从界面上拿掉。光 deleteLater 的话，删之前这一轮还会画出来。"""
    widget.hide()
    widget.setParent(None)
    widget.deleteLater()


class HeatMap(QWidget):
    day_clicked = Signal(object)  # date

    def __init__(self):
        super().__init__()
        self.setMouseTracking(True)
        self._columns: list[list[date | None]] = []
        self._counts: dict[date, int] = {}
        self._busiest = 0
        self.selected: date | None = None

    def set_data(self, start: date, end: date, counts: dict[date, int]) -> None:
        self._columns = stats.weeks(start, end)
        self._counts = counts
        self._busiest = max(counts.values(), default=0)
        self.updateGeometry()
        self.update()

    def set_selected(self, day: date | None) -> None:
        self.selected = day
        self.update()

    def sizeHint(self) -> QSize:
        return QSize(LEFT + len(self._columns) * STEP, TOP + 7 * STEP)

    def minimumSizeHint(self) -> QSize:
        return self.sizeHint()

    def _cell_rect(self, col: int, row: int) -> QRect:
        return QRect(LEFT + col * STEP, TOP + row * STEP, CELL, CELL)

    def _day_at(self, pos: QPoint) -> date | None:
        col = (pos.x() - LEFT) // STEP
        row = (pos.y() - TOP) // STEP
        if pos.x() < LEFT or pos.y() < TOP or not (0 <= col < len(self._columns)) or not (0 <= row < 7):
            return None
        if not self._cell_rect(col, row).contains(pos):
            return None  # 落在格子之间的缝里
        return self._columns[col][row]

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        font = p.font()
        font.setPixelSize(10)
        p.setFont(font)
        p.setPen(QColor(MUTED))

        for row in (0, 2, 4):
            name = i18n.weekday_short(row)
            p.drawText(QRect(0, TOP + row * STEP - 2, LEFT - 6, CELL + 4), Qt.AlignRight | Qt.AlignVCenter, name)

        # 月份：写在包含 1 号的那一列上；第一列的月份离下一个标签够远才写，免得挤在一起
        labels = []
        for col, days in enumerate(self._columns):
            first_of_month = next((d for d in days if d is not None and d.day == 1), None)
            if first_of_month is not None:
                labels.append((col, first_of_month.month))
        first = next((d for d in self._columns[0] if d), None) if self._columns else None
        if first is not None and (not labels or labels[0][0] >= 3) and first.day != 1:
            labels.insert(0, (0, first.month))
        for col, month in labels:
            p.drawText(QRect(LEFT + col * STEP, 0, 40, TOP - 4), Qt.AlignLeft | Qt.AlignBottom, i18n.month_short(month))

        p.setPen(Qt.NoPen)
        for col, days in enumerate(self._columns):
            for row, d in enumerate(days):
                if d is None:
                    continue
                lvl = stats.level(self._counts.get(d, 0), self._busiest)
                p.setBrush(QColor(COLORS[lvl]))
                p.drawRoundedRect(self._cell_rect(col, row), 2, 2)
                if d == self.selected:
                    p.setBrush(Qt.NoBrush)
                    p.setPen(QPen(QColor(TEXT), 1.5))
                    p.drawRoundedRect(self._cell_rect(col, row).adjusted(-1, -1, 1, 1), 3, 3)
                    p.setPen(Qt.NoPen)
        p.end()

    def mouseMoveEvent(self, event):
        d = self._day_at(event.position().toPoint())
        if d is None:
            QToolTip.hideText()
            self.setCursor(Qt.ArrowCursor)
            return
        n = self._counts.get(d, 0)
        QToolTip.showText(
            event.globalPosition().toPoint(),
            t("{day} · 完成 {n} 件", day=i18n.day_text(d), n=n)
            if n
            else t("{day} · 没有记录", day=i18n.day_text(d)),
            self,
        )
        self.setCursor(Qt.PointingHandCursor)

    def mousePressEvent(self, event):
        d = self._day_at(event.position().toPoint())
        if d is not None:
            self.day_clicked.emit(d)


class ActivityWindow(QWidget):
    def __init__(self, store: Store):
        super().__init__()
        self.store = store
        self.setWindowTitle(t("jo-app · 活动记录"))
        self.setMinimumSize(560, 480)
        self.resize(LEFT + 53 * STEP + 200, 580)  # 默认放得下一整年，不用横着滚

        self._year: int | None = None  # None = 过去一年
        self._selected = date.today()

        root = QVBoxLayout(self)
        root.setContentsMargins(24, 20, 24, 20)
        root.setSpacing(12)

        self.summary = QLabel("")
        self.summary.setObjectName("Title")
        root.addWidget(self.summary)

        top = QHBoxLayout()
        top.setSpacing(16)

        card = QFrame()
        card.setObjectName("Card")
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(16, 14, 16, 10)
        card_layout.setSpacing(8)
        self.heatmap = HeatMap()
        self.heatmap.day_clicked.connect(self.select_day)
        self._scroll = QScrollArea()
        self._scroll.setFrameShape(QFrame.NoFrame)
        self._scroll.setWidget(self.heatmap)
        self._scroll.setWidgetResizable(False)
        self._scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._scroll.setFixedHeight(TOP + 7 * STEP + 14)
        card_layout.addWidget(self._scroll)

        legend = QHBoxLayout()
        self.streak = QLabel("")
        self.streak.setObjectName("Muted")
        legend.addWidget(self.streak)
        legend.addStretch()
        less = QLabel(t("少"))
        less.setObjectName("Muted")
        legend.addWidget(less)
        for color in COLORS:
            swatch = QLabel()
            swatch.setFixedSize(CELL, CELL)
            swatch.setStyleSheet(f"background:{color}; border-radius:2px;")
            legend.addWidget(swatch)
        more = QLabel(t("多"))
        more.setObjectName("Muted")
        legend.addWidget(more)
        card_layout.addLayout(legend)
        top.addWidget(card, 1)

        # 右边的年份，跟 GitHub 一样
        self._years_box = QVBoxLayout()
        self._years_box.setSpacing(4)
        self._years_box.setAlignment(Qt.AlignTop)
        self._year_group = QButtonGroup(self)
        self._year_group.setExclusive(True)
        self._year_values: list[int | None] = []
        top.addLayout(self._years_box)
        root.addLayout(top)

        self.day_title = QLabel("")
        self.day_title.setObjectName("Subtitle")
        root.addWidget(self.day_title)

        day_scroll = QScrollArea()
        day_scroll.setWidgetResizable(True)
        day_scroll.setFrameShape(QFrame.NoFrame)
        host = QWidget()
        self._day_list = QVBoxLayout(host)
        self._day_list.setAlignment(Qt.AlignTop)
        self._day_list.setContentsMargins(0, 0, 8, 0)
        self._day_list.setSpacing(4)
        day_scroll.setWidget(host)
        root.addWidget(day_scroll, 1)

    # ---------- 数据 ----------

    def refresh(self) -> None:
        today = date.today()
        self._rebuild_year_buttons(today)
        if self._year is None:
            start, end = stats.last_year(today)
        else:
            start, end = stats.year_range(self._year, today)
        counts = self.store.activity_counts(start, end)
        self.heatmap.set_data(start, end, counts)
        self.heatmap.adjustSize()

        total = sum(counts.values())
        self.summary.setText(
            t("过去一年完成了 {total} 件事", total=total)
            if self._year is None
            else t("{year} 年完成了 {total} 件事", year=self._year, total=total)
        )
        current, longest = stats.streaks(self.store.activity_days(), today)
        self.streak.setText(
            t("当前连续 {current} 天 · 最长连续 {longest} 天", current=current, longest=longest)
        )

        if not (start <= self._selected <= end):
            self._selected = end
        self.heatmap.set_selected(self._selected)
        self._show_day(self._selected)

    def _rebuild_year_buttons(self, today: date) -> None:
        options = [None, *self.store.activity_years(today)]
        if options != self._year_values:
            for btn in self._year_group.buttons():
                self._year_group.removeButton(btn)
                _discard(btn)
            for value in options:
                btn = QPushButton(t("过去一年") if value is None else str(value))
                btn.setObjectName("Scope")
                btn.setCheckable(True)
                btn.setMinimumWidth(96)  # 「Past year」加粗后放得下
                btn.clicked.connect(lambda _=False, v=value: self._pick_year(v))
                self._year_group.addButton(btn)
                self._years_box.addWidget(btn)
            self._year_values = options
        for btn, value in zip(self._year_group.buttons(), self._year_values):
            btn.setChecked(value == self._year)

    def _pick_year(self, year: int | None) -> None:
        self._year = year
        today = date.today()
        # 切到某一年时，默认选那年最后一天（今年就是今天）
        self._selected = today if year in (None, today.year) else date(year, 12, 31)
        self.refresh()
        self._scroll_to_selected()

    def select_day(self, day: date) -> None:
        self._selected = day
        self.heatmap.set_selected(day)
        self._show_day(day)

    def _show_day(self, day: date) -> None:
        while self._day_list.count():
            item = self._day_list.takeAt(0)
            if item.widget():
                _discard(item.widget())

        items = self.store.activity_on(day)
        tasks = sum(1 for a in items if a.kind == "task")
        label = t("今天") if day == date.today() else i18n.day_text(day)
        self.day_title.setText(
            t("{day} · 完成 {n} 件", day=label, n=tasks)
            if tasks
            else t("{day} · 没有记录", day=label)
        )
        for a in items:
            row = QHBoxLayout()
            row.setSpacing(10)
            time = QLabel(f"{a.at:%H:%M}")
            time.setObjectName("Muted")
            time.setFixedWidth(40)
            row.addWidget(time)
            if a.kind == "reward":
                text = QLabel(
                    t("🎁 拿到奖励：{title}", title=a.title)
                    + (t("（{scope}）", scope=a.scope.label) if a.scope else "")
                )
                text.setStyleSheet(f"color: {REWARD_COLOR};")
            else:
                tag = f"[{a.scope.label}] " if a.scope else t("[旧版] ")
                text = QLabel(f"✓ {tag}{a.title}")
            text.setTextFormat(Qt.PlainText)  # 标题是用户写的，别当 HTML 解析
            text.setWordWrap(True)
            row.addWidget(text, 1)
            holder = QWidget()
            holder.setLayout(row)
            self._day_list.addWidget(holder)

    def _scroll_to_selected(self) -> None:
        bar = self._scroll.horizontalScrollBar()
        bar.setValue(bar.maximum() if self._year is None else 0)

    # ---------- 窗口 ----------

    def bring_up(self) -> None:
        self.refresh()
        self.show()
        self.setWindowState(self.windowState() & ~Qt.WindowMinimized)
        self.raise_()
        self.activateWindow()
        self._scroll_to_selected()

